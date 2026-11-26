"""CLI.

  python -m src.main run [--dry-run]      forecast -> risk -> Telegram (if needed) -> state + docs/status.json
  python -m src.main preview              print the alert that WOULD be sent now (no Telegram, no state change)
  python -m src.main test-message         send one test message to check the bot token / chat id
  python -m src.main backtest --start 2010-01-01 --end 2024-12-31
                                          how often each level would have fired in past years (reanalysis rain)
"""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from . import messages, openmeteo, risk, state, telegram
from .settings import ROOT, load

log = logging.getLogger("rainbot")


def now_local(tz: str) -> pd.Timestamp:
    return pd.Timestamp.now(tz=tz).tz_localize(None)


def evaluate(s, get=None, now=None):
    now = now or now_local(s.timezone)
    fc = openmeteo.forecast(s.areas, s.models, s.hours_ahead, s.timezone, get)
    sea = None
    if s.tide.get("enabled"):
        try:
            sea = openmeteo.sea_level(s.tide["lat"], s.tide["lon"], s.timezone, get)
        except Exception as e:                       # tide is a bonus: never block an alert because of it
            log.warning("tide unavailable: %s", e)
    return risk.assess(fc, sea, now, s), now


def status_json(res, now, s) -> dict:
    w = res["worst"]
    hourly = w.hourly_likely if w is not None and w.hourly_likely is not None else pd.Series(dtype=float)
    city = pd.concat([a.hourly_likely for a in res["areas"] if a.hourly_likely is not None], axis=1).max(axis=1) \
        if res["areas"] else hourly
    return {"updated": now.isoformat(timespec="minutes"), "timezone": s.timezone, "city": s.city,
            "level": res["level"], "level_name": risk.NAMES[res["level"]],
            "areas": [{"name": a.name, "level": a.level, "r3": round(a.r3_likely, 1), "r3_worst": round(a.r3_worst, 1),
                       "r24": round(a.r24_likely, 1), "r24_worst": round(a.r24_worst, 1),
                       "peak": a.peak_time.isoformat(timespec="minutes") if a.peak_time is not None else None,
                       "tide_at_peak": a.tide_at_peak} for a in res["areas"]],
            "tides": [t.isoformat(timespec="minutes") for t in res["tides"]],
            "hourly": [{"t": t.isoformat(timespec="minutes"), "mm": round(float(v), 2)} for t, v in city.items()],
            "models": s.models}


def cmd_run(s, dry=False, get=None, post=None, now=None, state_path=None, docs=None):
    res, now = evaluate(s, get, now)
    sp = Path(state_path or ROOT / "state" / "state.json")
    st = state.load(sp)
    kinds = state.decide(res["level"], now, st, s.alert)
    texts = {"alert": messages.alert, "all_clear": messages.all_clear, "morning": messages.morning}
    sent = []
    for k in kinds:
        msg = texts[k](res, now, s.city)
        if dry:
            print(msg, "\n---")
        else:
            telegram.send(msg, post=post)
        sent.append(k)
    if not dry:
        state.save(sp, state.update(st, res["level"], now, kinds, s.alert))
    d = Path(docs or ROOT / "docs")
    d.mkdir(parents=True, exist_ok=True)
    (d / "status.json").write_text(json.dumps(status_json(res, now, s), ensure_ascii=False, indent=1))
    log.info("level %d (%s) | sent: %s", res["level"], risk.NAMES[res["level"]], sent or "nothing")
    return res, sent


def backtest(s, start, end, get=None, out_dir=None) -> pd.DataFrame:
    """Day-level maximum risk from hourly reanalysis rain at the city centre (no tide, no forecast error)."""
    lat = float(np.mean([a.lat for a in s.areas]))
    lon = float(np.mean([a.lon for a in s.areas]))
    p = openmeteo.archive(lat, lon, start, end, s.timezone, get).fillna(0)
    r3 = p.rolling(3, min_periods=1).sum()                       # rain that HAS fallen in the last 3 h
    daily = pd.DataFrame({"max_3h_mm": r3.resample("D").max(), "day_total_mm": p.resample("D").sum()})
    day = pd.Series(risk.level_of(daily.max_3h_mm, daily.day_total_mm, np.zeros(len(daily), bool), s.levels),
                    index=daily.index)                           # BMD categories are per calendar day
    tab = pd.DataFrame({f"days_{risk.NAMES[k]}": (day == k).groupby(day.index.year).sum() for k in (1, 2, 3)})
    tab.index.name = "year"
    tab["alert_days_(>=min_level)"] = (day >= s.alert["min_level"]).groupby(day.index.year).sum()
    month = (day >= s.alert["min_level"]).groupby(day.index.month).mean().rename("share_of_days_with_alert")
    top = daily.sort_values("max_3h_mm", ascending=False).head(15)
    top.index = top.index.date
    out = Path(out_dir or ROOT / "results")
    out.mkdir(parents=True, exist_ok=True)
    md = (f"# Back-test {start} – {end}\n\nHourly precipitation from the Open-Meteo historical archive (reanalysis, "
          f"about 10–25 km grid) at {lat:.3f}, {lon:.3f}. Reanalysis smooths short, intense storms, so real 3-hour peaks are "
          f"usually higher: treat these counts as a lower bound. Tide not included.\n\n## Days per year at each level\n\n"
          f"{tab.to_markdown()}\n\n## Share of days with an alert, by month\n\n{month.to_frame().to_markdown()}\n\n"
          f"## Wettest days (max 3-hour rain)\n\n{top.round(1).to_markdown()}\n")
    (out / "backtest.md").write_text(md, encoding="utf-8")
    return tab


def main(argv=None):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["run", "preview", "test-message", "backtest"])
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--config", default=str(ROOT / "config.toml"))
    ap.add_argument("--start", default="2015-01-01")
    ap.add_argument("--end", default=str(pd.Timestamp.now().year - 1) + "-12-31")
    a = ap.parse_args(argv)
    s = load(a.config)
    if a.cmd == "run":
        cmd_run(s, dry=a.dry_run)
    elif a.cmd == "preview":
        res, now = evaluate(s)
        print(messages.alert(res, now, s.city) if res["worst"] else "no data")
    elif a.cmd == "test-message":
        telegram.send(f"✅ {s.city} বৃষ্টি-সতর্কতা বট চালু আছে। (test)")
    else:
        print(backtest(s, a.start, a.end).to_string())


if __name__ == "__main__":
    main()

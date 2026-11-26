"""Open-Meteo and Telegram are mocked: no network, no secrets."""
import json

import numpy as np
import pandas as pd
import pytest

from src import main, messages, openmeteo, risk, state
from src.settings import load

NOW = pd.Timestamp("2026-07-10 08:30")


class Resp:
    def __init__(self, js, code=200):
        self.js, self.status_code, self.text = js, code, "ok"

    def json(self):
        return self.js

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


def hourly_block(rain_by_model: dict, start="2026-07-09 00:00", hours=96, prob=60):
    t = pd.date_range(start, periods=hours, freq="h")
    h = {"time": [x.strftime("%Y-%m-%dT%H:%M") for x in t]}
    for m, f in rain_by_model.items():
        h[f"precipitation_{m}"] = [float(f(x)) for x in t]
        h[f"precipitation_probability_{m}"] = [prob] * hours
    return {"hourly": h}


def fake_get(rain_fn, tide=True, single=False):
    s = load()

    def get(url, params=None, timeout=None):
        if "marine" in url:
            t = pd.date_range("2026-07-09 00:00", periods=96, freq="h")
            sea = np.sin(2 * np.pi * (np.arange(96) - 15) / 12.42)          # high tide ~06:30 and ~19:00 on 10 July
            return Resp({"hourly": {"time": [x.strftime("%Y-%m-%dT%H:%M") for x in t], "sea_level_height_msl": sea.tolist()}})
        if "archive" in url:
            t = pd.date_range(params["start_date"], params["end_date"] + " 23:00", freq="h")
            return Resp({"hourly": {"time": [x.strftime("%Y-%m-%dT%H:%M") for x in t],
                                    "precipitation": [30.0 if (x.month == 7 and x.day == 1 and 10 <= x.hour < 12) else 0.0 for x in t]}})
        n = len(params["latitude"].split(","))
        if single:
            b = hourly_block({"x": rain_fn})
            b["hourly"]["precipitation"] = b["hourly"].pop("precipitation_x")
            b["hourly"]["precipitation_probability"] = b["hourly"].pop("precipitation_probability_x")
            return Resp(b if n == 1 else [b] * n)
        return Resp([hourly_block({m: rain_fn for m in s.models})] * n)
    return get


def burst(mm_per_hour, start="2026-07-10 15:00", hours=3):
    a, b = pd.Timestamp(start), pd.Timestamp(start) + pd.Timedelta(hours=hours)
    return lambda t: mm_per_hour if a <= t < b else 0.0


def test_multimodel_parsing_does_not_confuse_probability():
    s = load()
    fc = openmeteo.forecast(s.areas, s.models, 48, s.timezone, fake_get(burst(5)))
    df = fc[s.areas[0].name]
    assert {f"precip_{m}" for m in s.models} <= set(df.columns)
    assert not any(c == "precip_probability" for c in df.columns)
    one = openmeteo.forecast(s.areas[:1], ["best_match"], 48, s.timezone, fake_get(burst(5), single=True))
    assert "precip_best_match" in one[s.areas[0].name]


@pytest.mark.parametrize("rate,start,expect", [
    (20, "2026-07-10 20:00", 3),     # 60 mm in 3 h -> high
    (10, "2026-07-10 10:00", 2),     # 30 mm in 3 h, no high tide (mock tide peaks ~06:30 / ~19:00) -> medium
    (10, "2026-07-10 17:00", 3),     # 30 mm in 3 h around high tide -> high
    (2, "2026-07-10 20:00", 0),      # 6 mm -> nothing
    (1.0, "2026-07-10 10:00", 1),    # 1 mm/h for 48 h: 24 mm per day -> low (24-hour rule)
])
def test_risk_levels(rate, start, expect):
    s = load()
    hours = 48 if rate == 1.0 else 3
    res, _ = main.evaluate(s, fake_get(burst(rate, start, hours)), NOW)
    assert res["level"] == expect


def test_state_logic():
    cfg = load().alert
    st = {}
    assert state.decide(3, NOW, st, cfg) == ["alert"]
    st = state.update(st, 3, NOW, ["alert"], cfg)
    assert state.decide(3, NOW + pd.Timedelta(hours=2), st, cfg) == []                      # no spam
    assert state.decide(3, NOW + pd.Timedelta(hours=6), st, cfg) == ["alert"]               # reminder
    st2 = state.update(st, 2, NOW + pd.Timedelta(hours=1), [], cfg)
    assert state.decide(3, NOW + pd.Timedelta(hours=2), st2, cfg) == ["alert"]              # risk went up again
    assert state.decide(0, NOW + pd.Timedelta(hours=3), st, cfg) == ["all_clear"]
    calm = state.update({}, 0, NOW, [], cfg)
    assert state.decide(0, NOW + pd.Timedelta(hours=3), calm, cfg) == []                     # no repeated all-clear
    m = state.decide(1, pd.Timestamp("2026-07-11 07:10"), calm, cfg)
    assert m == ["morning"]
    after = state.update(calm, 1, pd.Timestamp("2026-07-11 07:10"), m, cfg)
    assert state.decide(1, pd.Timestamp("2026-07-11 10:10"), after, cfg) == []               # once per day


def test_run_sends_bengali_alert_and_writes_status(tmp_path):
    s = load()
    posts = []
    post = lambda url, data=None, timeout=None: posts.append(data) or Resp({}, 200)
    import os
    os.environ.update(TELEGRAM_BOT_TOKEN="x", TELEGRAM_CHAT_ID="111,@channel")
    res, sent = main.cmd_run(s, get=fake_get(burst(20, "2026-07-10 20:00")), post=post, now=NOW,
                             state_path=tmp_path / "state.json", docs=tmp_path / "docs")
    assert sent == ["alert"] and len(posts) == 2                                          # two chats
    txt = posts[0]["text"]
    assert "উচ্চ" in txt and "৬০ মিমি" in txt and "মুরাদপুর" in txt and posts[1]["chat_id"] == "@channel"
    st = json.loads((tmp_path / "state.json").read_text())
    assert st["last_level"] == 3
    status = json.loads((tmp_path / "docs" / "status.json").read_text())
    assert status["level"] == 3 and len(status["areas"]) == len(s.areas) and status["hourly"]
    posts.clear()
    main.cmd_run(s, get=fake_get(burst(20, "2026-07-10 20:00")), post=post, now=NOW + pd.Timedelta(hours=1),
                 state_path=tmp_path / "state.json", docs=tmp_path / "docs")
    assert posts == []                                                                     # already alerted


def test_messages_time_words():
    assert messages.when(pd.Timestamp("2026-07-10 16:00"), NOW) == "আজ বিকেল ৪টা"
    assert messages.when(pd.Timestamp("2026-07-11 02:00"), NOW) == "আগামীকাল রাত ২টা"


def test_backtest(tmp_path):
    s = load()
    tab = main.backtest(s, "2024-06-01", "2024-07-31", get=fake_get(None), out_dir=tmp_path)
    assert tab.loc[2024, "days_উচ্চ"] == 1 and tab.loc[2024, "days_মাঝারি"] == 0           # one 60 mm-in-2-h day
    assert (tmp_path / "backtest.md").read_text().startswith("# Back-test")

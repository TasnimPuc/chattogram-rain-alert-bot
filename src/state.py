"""When to send: new or higher risk, a reminder while risk lasts, an all-clear, and one morning summary per day.
State lives in state/state.json and is committed back by the workflow, so runs remember what was already sent."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


def load(path: Path) -> dict:
    return json.loads(path.read_text()) if path.exists() and path.read_text().strip() else {}


def save(path: Path, st: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(st, ensure_ascii=False, indent=1))


def decide(level: int, now: pd.Timestamp, st: dict, cfg: dict) -> list[str]:
    """-> list of message kinds to send now: 'alert', 'all_clear', 'morning'."""
    out = []
    last = int(st.get("last_level", 0))
    sent = pd.Timestamp(st["last_sent"]) if st.get("last_sent") else None
    if level >= cfg["min_level"]:
        if level > last or sent is None or now - sent >= pd.Timedelta(hours=cfg["repeat_hours"]) or last < cfg["min_level"]:
            out.append("alert")
    elif last >= cfg["min_level"] and cfg.get("all_clear", True):
        out.append("all_clear")
    h = cfg.get("morning_summary_hour", -1)
    if h >= 0 and now.hour >= h and st.get("summary_date") != str(now.date()) and "alert" not in out \
            and level >= cfg.get("morning_summary_min_level", 1):
        out.append("morning")
    return out


def update(st: dict, level: int, now: pd.Timestamp, kinds: list, cfg: dict) -> dict:
    st = dict(st)
    if "alert" in kinds:
        st["last_sent"] = now.isoformat()
    if "morning" in kinds or (cfg.get("morning_summary_hour", -1) >= 0 and now.hour >= cfg["morning_summary_hour"]):
        st["summary_date"] = str(now.date())                       # at most one summary per day
    st["last_level"] = level
    st["last_run"] = now.isoformat()
    return st

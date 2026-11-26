"""Rain amounts -> waterlogging risk level (0 none, 1 low, 2 medium, 3 high).

For each model: forward-looking rolling sums (next 3 h and next 24 h from every hour). Across models: the median is the
"likely" value used for the level; the maximum is shown as the worst case. High tide in the 3-hour window lowers the
3-hour threshold for "high", because drains cannot empty into the Karnaphuli at high tide.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

NAMES = {0: "নেই", 1: "কম", 2: "মাঝারি", 3: "উচ্চ"}
ICON = {0: "🟢", 1: "🟡", 2: "🟠", 3: "🔴"}


def forward_sum(s: pd.Series, hours: int) -> pd.Series:
    """Sum of s over [t, t + hours)."""
    return s[::-1].rolling(hours, min_periods=1).sum()[::-1]


def level_of(r3, r24, tide_high, lv: dict) -> np.ndarray:
    r3, r24, tide_high = np.asarray(r3, float), np.asarray(r24, float), np.asarray(tide_high, bool)
    lev = np.zeros(len(r3), int)
    lev[(r3 >= lv["low_3h"]) | (r24 >= lv["low_24h"])] = 1
    lev[(r3 >= lv["medium_3h"]) | (r24 >= lv["medium_24h"])] = 2
    lev[(r3 >= lv["high_3h"]) | (r24 >= lv["high_24h"]) | (tide_high & (r3 >= lv["tide_high_3h"]))] = 3
    return lev


def high_tides(sea: pd.Series, percentile: float) -> list:
    """Times of local maxima above the given percentile."""
    if sea is None or sea.dropna().empty:
        return []
    v = sea.to_numpy()
    thr = np.nanpercentile(v, percentile)
    return [sea.index[i] for i in range(1, len(v) - 1) if v[i] >= v[i - 1] and v[i] > v[i + 1] and v[i] >= thr]


def tide_flag(index, tides, window_h, span_h=3) -> np.ndarray:
    """True if a high tide falls within ± window_h of the window [t, t + span_h)."""
    f = np.zeros(len(index), bool)
    for t in tides:
        lo, hi = t - pd.Timedelta(hours=window_h + span_h), t + pd.Timedelta(hours=window_h)
        f |= (index > lo) & (index <= hi)
    return f


@dataclass
class AreaRisk:
    name: str
    level: int
    peak_time: pd.Timestamp | None
    r3_likely: float
    r3_worst: float
    r24_likely: float
    r24_worst: float
    prob: float | None
    tide_at_peak: bool
    hourly_likely: pd.Series = field(repr=False, default=None)


def assess_area(name, df: pd.DataFrame, now, hours_ahead, tides, s) -> AreaRisk:
    df = df[(df.index >= now.floor("h")) & (df.index < now.floor("h") + pd.Timedelta(hours=hours_ahead))]
    pc = [c for c in df if c.startswith("precip_")]
    if df.empty or not pc:
        return AreaRisk(name, 0, None, 0, 0, 0, 0, None, False, pd.Series(dtype=float))
    P = df[pc].clip(lower=0)
    r3 = pd.concat({c: forward_sum(P[c].fillna(0), 3) for c in pc}, axis=1)
    r24 = pd.concat({c: forward_sum(P[c].fillna(0), 24) for c in pc}, axis=1)
    r3m, r24m = r3.median(axis=1), r24.median(axis=1)
    tf = tide_flag(df.index, tides, s.tide.get("window_hours", 2)) if s.tide.get("enabled") else np.zeros(len(df), bool)
    lev = level_of(r3m, r24m, tf, s.levels)
    i = int(np.argmax(r3m.to_numpy()))
    probs = df[[c for c in df if c.startswith("prob_")]]
    prob = float(np.nanmax(probs.iloc[: max(1, min(24, len(probs)))].to_numpy())) if probs.notna().any().any() else None
    return AreaRisk(name=name, level=int(lev.max()), peak_time=df.index[i] if r3m.iloc[i] > 0 else None,
                    r3_likely=float(r3m.max()), r3_worst=float(r3.max().max()), r24_likely=float(r24m.max()),
                    r24_worst=float(r24.max().max()), prob=prob, tide_at_peak=bool(tf[i]),
                    hourly_likely=P.median(axis=1))


def assess(fc: dict, sea, now, s) -> dict:
    tides = high_tides(sea, s.tide.get("high_percentile", 70)) if s.tide.get("enabled") else []
    tides = [t for t in tides if t >= now.floor("h") - pd.Timedelta(hours=3)]
    areas = [assess_area(a.name, fc[a.name], now, s.hours_ahead, tides, s) for a in s.areas if a.name in fc]
    worst = max(areas, key=lambda r: (r.level, r.r3_likely)) if areas else None
    return {"level": worst.level if worst else 0, "areas": areas, "worst": worst, "tides": tides}

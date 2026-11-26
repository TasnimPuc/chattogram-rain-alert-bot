"""Open-Meteo clients (free, no API key, non-commercial use): forecast (several models in one call), marine
sea level incl. tides, and the historical archive for back-testing. `get` can be replaced in tests."""
from __future__ import annotations

import time

import numpy as np
import pandas as pd
import requests

FORECAST = "https://api.open-meteo.com/v1/forecast"
MARINE = "https://marine-api.open-meteo.com/v1/marine"
ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"


def _get(url, params, get=None, tries=4):
    get = get or requests.get
    for i in range(tries):
        try:
            r = get(url, params=params, timeout=30)
            r.raise_for_status()
            return r.json()
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(2 ** i)


def _by_model(hourly: dict, var: str, models: list) -> dict:
    """{model: array} from an hourly block. Several models -> keys '<var>_<model>'; one model -> '<var>'."""
    out = {m: np.asarray(hourly[f"{var}_{m}"], float) for m in models if f"{var}_{m}" in hourly}
    if not out and var in hourly:
        out[models[0] if len(models) == 1 else "best_match"] = np.asarray(hourly[var], float)
    return out


def forecast(areas, models, hours_ahead, tz, get=None) -> dict:
    """-> {area_name: DataFrame(index=local time, columns=[precip_<model>..., prob_<model>...])}"""
    p = {"latitude": ",".join(str(a.lat) for a in areas), "longitude": ",".join(str(a.lon) for a in areas),
         "hourly": "precipitation,precipitation_probability", "models": ",".join(models), "timezone": tz,
         "forecast_days": min(16, hours_ahead // 24 + 2), "past_days": 1}
    js = _get(FORECAST, p, get)
    js = js if isinstance(js, list) else [js]
    out = {}
    for a, j in zip(areas, js):
        h = j["hourly"]
        df = pd.DataFrame(index=pd.to_datetime(h["time"]))
        for m, v in _by_model(h, "precipitation", models).items():
            df[f"precip_{m}"] = v
        for m, v in _by_model(h, "precipitation_probability", models).items():
            df[f"prob_{m}"] = v
        out[a.name] = df
    return out


def sea_level(lat, lon, tz, get=None) -> pd.Series:
    js = _get(MARINE, {"latitude": lat, "longitude": lon, "hourly": "sea_level_height_msl", "timezone": tz,
                       "forecast_days": 3, "past_days": 1}, get)
    h = js["hourly"]
    return pd.Series(np.asarray(h["sea_level_height_msl"], float), index=pd.to_datetime(h["time"]))


def archive(lat, lon, start: str, end: str, tz, get=None) -> pd.Series:
    """Hourly precipitation (reanalysis) for back-testing, fetched year by year."""
    parts = []
    for y in range(int(start[:4]), int(end[:4]) + 1):
        s, e = max(start, f"{y}-01-01"), min(end, f"{y}-12-31")
        js = _get(ARCHIVE, {"latitude": lat, "longitude": lon, "start_date": s, "end_date": e,
                            "hourly": "precipitation", "timezone": tz}, get)
        h = js["hourly"]
        parts.append(pd.Series(np.asarray(h["precipitation"], float), index=pd.to_datetime(h["time"])))
    return pd.concat(parts) if parts else pd.Series(dtype=float)

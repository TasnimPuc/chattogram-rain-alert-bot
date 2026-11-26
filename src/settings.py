from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@dataclass
class Area:
    name: str
    lat: float
    lon: float


@dataclass
class Settings:
    city: str
    timezone: str
    areas: list
    models: list
    hours_ahead: int
    tide: dict
    levels: dict
    alert: dict
    raw: dict = field(default_factory=dict)


def load(path: Path | str = ROOT / "config.toml") -> Settings:
    c = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    return Settings(city=c["city"]["name"], timezone=c["city"]["timezone"],
                    areas=[Area(**a) for a in c["areas"]], models=list(c["forecast"]["models"]),
                    hours_ahead=int(c["forecast"]["hours_ahead"]), tide=c.get("tide", {"enabled": False}),
                    levels=c["levels"], alert=c["alert"], raw=c)

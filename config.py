"""Runtime configuration for solarcontrol.

Defaults live here. Override any field by setting an environment variable of
the same name (uppercased), e.g. HOYMILES_INTERVAL_S=30. The systemd unit
loads /home/scott/solarcontrol/.env via EnvironmentFile=, so editing that
file on the Pi is the canonical way to override values without redeploying.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, fields


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError as e:
        raise ValueError(f"env {name}={raw!r} is not an int") from e


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except ValueError as e:
        raise ValueError(f"env {name}={raw!r} is not a float") from e


@dataclass(frozen=True)
class Config:
    # ---- Polling intervals (seconds). Each source loops independently. ----
    hoymiles_interval_s: int = 60
    vue_interval_s: int = 60
    weather_interval_s: int = 3600

    # ---- Hoymiles inverter ----
    dtu_host: str = "192.168.1.5"

    # ---- Emporia Vue ----
    # Tokens are stored in this file; pyemvue rotates them in place.
    emporia_keys_file: str = "emporia_keys.json"

    # ---- Weather (NWS, api.weather.gov) ----
    # Coordinates of the site. Default is Jamestown, MO.
    weather_lat: float = 38.7587
    weather_lon: float = -92.4877
    # Friendly name used as the Influx `location` tag.
    weather_location_name: str = "Jamestown, Missouri"
    # NWS requires a descriptive User-Agent. Identify the app and a contact.
    weather_user_agent: str = "solarcontrol/1.0 (set WEATHER_USER_AGENT to your contact info)"

    # ---- InfluxDB ----
    influx_url: str = "http://127.0.0.1:8086"
    influx_org: str = "solarcontrol"
    influx_bucket: str = "solarcontrol"
    # Required at runtime. Leave empty here so `from_env()` can produce a
    # clearer error than KeyError when the .env on the Pi is missing.
    influx_token: str = ""

    @classmethod
    def from_env(cls) -> "Config":
        kwargs: dict[str, object] = {}
        for f in fields(cls):
            envname = f.name.upper()
            if f.type is int or f.type == "int":
                kwargs[f.name] = _env_int(envname, f.default)  # type: ignore[arg-type]
            elif f.type is float or f.type == "float":
                kwargs[f.name] = _env_float(envname, f.default)  # type: ignore[arg-type]
            else:
                kwargs[f.name] = _env(envname, f.default)  # type: ignore[arg-type]
        return cls(**kwargs)  # type: ignore[arg-type]

    def require_influx_token(self) -> str:
        if not self.influx_token:
            raise RuntimeError(
                "INFLUX_TOKEN is empty. Put it in /home/scott/solarcontrol/.env"
            )
        return self.influx_token

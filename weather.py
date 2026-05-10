"""Weather reads via python_weather (weather.com scrape).

Imperial units. We pull current conditions + a brief forecast (today, +1d, +2d).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import python_weather

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class WeatherReading:
    location: str
    metrics: dict[str, float]
    """Flat numeric metrics (e.g. current.temperature_f, forecast_d1.high_f)."""
    text: dict[str, str]
    """Non-numeric attributes (e.g. current.kind, forecast_d1.kind)."""


async def read(location: str) -> WeatherReading | None:
    try:
        async with python_weather.Client(unit=python_weather.IMPERIAL) as client:
            w = await client.get(location)
    except Exception:  # network/parse errors from the upstream scrape
        log.exception("weather: fetch failed for %s", location)
        return None

    metrics: dict[str, float] = {
        "current.temperature_f": float(w.temperature),
    }
    text: dict[str, str] = {
        "current.kind": str(w.kind),
    }

    for i, daily in enumerate(w):
        if i > 2:
            break
        # python_weather DailyForecast exposes .highest_temperature, .lowest_temperature, .kind, .date
        prefix = f"forecast_d{i}"
        try:
            metrics[f"{prefix}.high_f"] = float(daily.highest_temperature)
            metrics[f"{prefix}.low_f"] = float(daily.lowest_temperature)
        except AttributeError:
            pass
        text[f"{prefix}.kind"] = str(getattr(daily, "kind", ""))

    return WeatherReading(location=location, metrics=metrics, text=text)

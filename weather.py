"""Weather reads via the U.S. National Weather Service (NWS) API.

api.weather.gov is free, no API key, but requires a descriptive User-Agent.

Two-step lookup:
  1. /points/{lat},{lon}        ->  metadata: forecast URL, station list URL
  2. {forecast URL}             ->  7-day forecast (alternating day/night periods)
  3. {stations URL}/observations/latest  ->  current observation

Result schema (Influx-friendly):
  metrics:
    current.temperature_f, current.dewpoint_f, current.relative_humidity,
    current.wind_speed_mph,
    forecast_d{N}.high_f, forecast_d{N}.low_f, forecast_d{N}.precip_probability
  text:
    current.kind, forecast_d{N}.kind, forecast_d{N}.detailed
"""

from __future__ import annotations

import asyncio
import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass

log = logging.getLogger(__name__)

_NWS_BASE = "https://api.weather.gov"
_TIMEOUT_S = 15

# Cached gridpoint metadata so we don't hit /points/ every poll.
_points_cache: dict[tuple[float, float], dict] = {}


@dataclass(frozen=True)
class WeatherReading:
    location: str
    metrics: dict[str, float]
    text: dict[str, str]


def _http_get_json(url: str, user_agent: str) -> dict:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": user_agent,
            "Accept": "application/geo+json",
        },
    )
    with urllib.request.urlopen(req, timeout=_TIMEOUT_S) as resp:  # noqa: S310 (https only)
        return json.load(resp)


def _c_to_f(c: float | None) -> float | None:
    return None if c is None else c * 9.0 / 5.0 + 32.0


def _ms_to_mph(ms: float | None) -> float | None:
    return None if ms is None else ms * 2.23693629


def _put(d: dict[str, float], k: str, v: float | None) -> None:
    if v is not None:
        d[k] = float(v)


def _read_blocking(lat: float, lon: float, user_agent: str, location_name: str) -> WeatherReading | None:
    cache_key = (round(lat, 4), round(lon, 4))
    pts = _points_cache.get(cache_key)
    if pts is None:
        pts = _http_get_json(f"{_NWS_BASE}/points/{lat},{lon}", user_agent)["properties"]
        _points_cache[cache_key] = pts

    metrics: dict[str, float] = {}
    text: dict[str, str] = {}

    # ---- Current observation ----
    try:
        stations = _http_get_json(pts["observationStations"], user_agent)["features"]
        if stations:
            station_id = stations[0]["properties"]["stationIdentifier"]
            obs = _http_get_json(
                f"{_NWS_BASE}/stations/{station_id}/observations/latest",
                user_agent,
            )["properties"]
            _put(metrics, "current.temperature_f", _c_to_f(_val(obs.get("temperature"))))
            _put(metrics, "current.dewpoint_f", _c_to_f(_val(obs.get("dewpoint"))))
            _put(metrics, "current.relative_humidity", _val(obs.get("relativeHumidity")))
            # Wind speed comes in km/h *not* m/s on the API. Convert to mph.
            wind_kmh = _val(obs.get("windSpeed"))
            _put(metrics, "current.wind_speed_mph", None if wind_kmh is None else wind_kmh * 0.621371)
            if obs.get("textDescription"):
                text["current.kind"] = obs["textDescription"]
    except Exception:
        log.exception("nws: current observation fetch failed (continuing with forecast only)")

    # ---- Forecast (daytime periods only -> d0/d1/d2/...) ----
    try:
        fc = _http_get_json(pts["forecast"], user_agent)["properties"]
        periods = fc.get("periods", [])
        # Pair daytime periods with their following night to derive a low.
        day_idx = 0
        i = 0
        while i < len(periods) and day_idx < 4:
            p = periods[i]
            if not p.get("isDaytime"):
                # Forecast may start with a "Tonight" period; record its low under d-1
                # only if we haven't yet emitted any day. Otherwise skip (it pairs with prior day).
                if day_idx == 0:
                    night = p
                    _put(metrics, f"forecast_d{day_idx}.low_f", _maybe_f(night.get("temperature"), night.get("temperatureUnit")))
                i += 1
                continue
            day = p
            night = periods[i + 1] if i + 1 < len(periods) and not periods[i + 1].get("isDaytime") else None
            prefix = f"forecast_d{day_idx}"
            _put(metrics, f"{prefix}.high_f", _maybe_f(day.get("temperature"), day.get("temperatureUnit")))
            if night:
                _put(metrics, f"{prefix}.low_f", _maybe_f(night.get("temperature"), night.get("temperatureUnit")))
            pop = (day.get("probabilityOfPrecipitation") or {}).get("value")
            _put(metrics, f"{prefix}.precip_probability", float(pop) if pop is not None else None)
            if day.get("shortForecast"):
                text[f"{prefix}.kind"] = day["shortForecast"]
            if day.get("detailedForecast"):
                text[f"{prefix}.detailed"] = day["detailedForecast"]
            day_idx += 1
            i += 2 if night else 1
    except Exception:
        log.exception("nws: forecast fetch failed")
        if not metrics and not text:
            return None

    return WeatherReading(location=location_name, metrics=metrics, text=text)


def _val(field) -> float | None:
    """NWS observation fields look like {'value': X, 'unitCode': '...'}."""
    if field is None:
        return None
    v = field.get("value")
    return None if v is None else float(v)


def _maybe_f(temp, unit) -> float | None:
    if temp is None:
        return None
    if str(unit).upper() == "F":
        return float(temp)
    return _c_to_f(float(temp))


async def read(lat: float, lon: float, user_agent: str, location_name: str) -> WeatherReading | None:
    """Async wrapper. NWS is fast enough that running in a thread is fine."""
    try:
        return await asyncio.to_thread(_read_blocking, lat, lon, user_agent, location_name)
    except urllib.error.URLError:
        log.exception("nws: network error")
        return None
    except Exception:
        log.exception("nws: unexpected error")
        return None

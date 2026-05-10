"""Time-series storage backends.

`Storage` is the protocol the polling loop talks to. `InfluxStorage` is the
production backend; `MemoryStorage` is for unit tests / dev.

Schema (Influx line protocol):
  hoymiles,inverter_sn=<sn> battery.state_of_charge=92.3,flow.pv_to_load=2300, ...
  vue,gid=<gid>,channel=<num>,name=<channel_name> usage_kwh=0.0234
  weather,location=<loc> current.temperature_f=72.0,forecast_d0.high_f=78.0
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Iterable, Protocol

from influxdb_client import InfluxDBClient, Point, WriteOptions
from influxdb_client.client.write_api import SYNCHRONOUS

log = logging.getLogger(__name__)


class Storage(Protocol):
    def write(self, points: Iterable[Point]) -> None: ...

    def close(self) -> None: ...


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def hoymiles_point(inverter_sn: str, metrics: dict[str, float], ts: datetime | None = None) -> Point:
    p = Point("hoymiles").tag("inverter_sn", inverter_sn).time(ts or now_utc())
    for k, v in metrics.items():
        p = p.field(k, float(v))
    return p


def vue_points(channels, ts: datetime | None = None) -> list[Point]:
    t = ts or now_utc()
    out: list[Point] = []
    for c in channels:
        p = (
            Point("vue")
            .tag("gid", str(c.gid))
            .tag("channel", c.channel_num)
            .tag("is_main", "1" if c.is_main else "0")
            .tag("device", c.device_name)
            .tag("name", c.channel_name)
            .field("usage_kwh", float(c.usage_kwh))
            # Convert to instantaneous-equivalent watts (kWh/min * 60 -> kW * 1000).
            .field("power_w", float(c.usage_kwh) * 60_000.0)
            .time(t)
        )
        out.append(p)
    return out


def charger_points(chargers, ts: datetime | None = None) -> list[Point]:
    """One point per charger, written to the `evse` measurement."""
    t = ts or now_utc()
    out: list[Point] = []
    for c in chargers:
        p = (
            Point("evse")
            .tag("gid", str(c.gid))
            .tag("device", c.device_name or str(c.gid))
            .field("on", 1.0 if c.on else 0.0)
            .field("charging_rate_a", float(c.charging_rate_a))
            .field("max_charging_rate_a", float(c.max_charging_rate_a))
            .field("status", c.status)
            .field("fault_text", c.fault_text)
            .time(t)
        )
        out.append(p)
    return out


def weather_point(location: str, metrics: dict[str, float], text: dict[str, str], ts: datetime | None = None) -> Point:
    p = Point("weather").tag("location", location).time(ts or now_utc())
    for k, v in metrics.items():
        p = p.field(k, float(v))
    for k, v in text.items():
        p = p.field(k, str(v))
    return p


class InfluxStorage:
    """Synchronous Influx writer. Cheap because writes happen at most every minute."""

    def __init__(self, url: str, token: str, org: str, bucket: str) -> None:
        self._client = InfluxDBClient(url=url, token=token, org=org)
        self._bucket = bucket
        self._org = org
        # SYNCHRONOUS: each write_api.write() call blocks until the server ACKs.
        # Fine at our write rate; surfaces errors immediately.
        self._write_api = self._client.write_api(write_options=SYNCHRONOUS)

    def write(self, points: Iterable[Point]) -> None:
        pts = list(points)
        if not pts:
            return
        self._write_api.write(bucket=self._bucket, org=self._org, record=pts)

    def close(self) -> None:
        try:
            self._write_api.close()
        finally:
            self._client.close()


class MemoryStorage:
    """In-memory storage, for tests and dry runs."""

    def __init__(self) -> None:
        self.points: list[Point] = []

    def write(self, points: Iterable[Point]) -> None:
        self.points.extend(points)

    def close(self) -> None:
        pass

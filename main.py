"""solarcontrol service entry point.

Three independent polling coroutines write to InfluxDB. Each tolerates its
own failures so one source going dark doesn't kill the others.
"""

from __future__ import annotations

import asyncio
import logging
import signal
import sys

import hoymiles
import vue
import weather
from config import Config
from storage import (
    InfluxStorage,
    Storage,
    charger_points,
    hoymiles_point,
    vue_points,
    weather_point,
)

log = logging.getLogger("solarcontrol")


def _setup_logging() -> None:
    # journald already adds timestamps, so keep our format simple.
    logging.basicConfig(
        level=logging.INFO,
        format="%(name)s %(levelname)s %(message)s",
        stream=sys.stdout,
    )
    # Quiet noisy libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("influxdb_client").setLevel(logging.WARNING)


async def _poll_hoymiles(cfg: Config, storage: Storage, stop: asyncio.Event) -> None:
    log.info("hoymiles poller started: dtu=%s every %ds", cfg.dtu_host, cfg.hoymiles_interval_s)
    while not stop.is_set():
        try:
            r = await hoymiles.read(cfg.dtu_host)
            if r is not None:
                storage.write([hoymiles_point(r.inverter_sn, r.metrics)])
                log.info(
                    "hoymiles ok soc=%.1f%% pv=%.0fW grid_to_load=%.0fW",
                    r.metrics.get("battery.state_of_charge", float("nan")),
                    r.metrics.get("pv.production", float("nan")),
                    r.metrics.get("flow.grid_to_load", float("nan")),
                )
        except Exception:
            log.exception("hoymiles poll failed")

        await _sleep_or_stop(cfg.hoymiles_interval_s, stop)


async def _poll_vue(cfg: Config, storage: Storage, stop: asyncio.Event) -> None:
    log.info("vue poller started: every %ds", cfg.vue_interval_s)
    while not stop.is_set():
        try:
            # pyemvue is sync; run in a thread so we don't block other pollers.
            channels = await asyncio.to_thread(
                vue.read, cfg.emporia_keys_file, cfg.included_vue_devices()
            )
            storage.write(vue_points(channels))
            # Per-device "Mains" reading — the only one that's an authoritative
            # device-level total. Summing all channels would double-count (Mains
            # already equals individual circuits + Balance for that device).
            mains = [(c.device_name, c.usage_kwh * 60_000.0) for c in channels if c.is_main]
            mains_str = ", ".join(f"{name}={w:.0f}W" for name, w in mains) or "(none)"
            log.info("vue ok channels=%d mains: %s", len(channels), mains_str)

            # EVSE state — separate API call. Includes commanded rate (A) and on/off.
            chargers = await asyncio.to_thread(vue.read_chargers)
            if chargers:
                storage.write(charger_points(chargers))
                ev_str = ", ".join(
                    f"{c.device_name or c.gid}={'ON' if c.on else 'OFF'}@{c.charging_rate_a}A"
                    f"/{c.max_charging_rate_a}A ({c.status or '-'})"
                    for c in chargers
                )
                log.info("evse ok: %s", ev_str)
        except FileNotFoundError:
            log.error("vue: %s not found; skipping until present", cfg.emporia_keys_file)
        except Exception:
            log.exception("vue poll failed")

        await _sleep_or_stop(cfg.vue_interval_s, stop)


async def _poll_weather(cfg: Config, storage: Storage, stop: asyncio.Event) -> None:
    log.info("weather poller started: every %ds", cfg.weather_interval_s)
    while not stop.is_set():
        try:
            r = await weather.read(
                lat=cfg.weather_lat,
                lon=cfg.weather_lon,
                user_agent=cfg.weather_user_agent,
                location_name=cfg.weather_location_name,
            )
            if r is not None:
                storage.write([weather_point(r.location, r.metrics, r.text)])
                log.info(
                    "weather ok temp=%.1fF kind=%s d1_high=%.0fF",
                    r.metrics.get("current.temperature_f", float("nan")),
                    r.text.get("current.kind", ""),
                    r.metrics.get("forecast_d1.high_f", float("nan")),
                )
        except Exception:
            log.exception("weather poll failed")

        await _sleep_or_stop(cfg.weather_interval_s, stop)


async def _sleep_or_stop(seconds: float, stop: asyncio.Event) -> None:
    """Sleep up to `seconds`, but wake immediately if stop is set."""
    try:
        await asyncio.wait_for(stop.wait(), timeout=seconds)
    except asyncio.TimeoutError:
        pass


def _install_signal_handlers(loop: asyncio.AbstractEventLoop, stop: asyncio.Event) -> None:
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)


async def amain() -> int:
    _setup_logging()
    cfg = Config.from_env()
    log.info(
        "starting solarcontrol intervals(s) hoy=%d vue=%d weather=%d",
        cfg.hoymiles_interval_s,
        cfg.vue_interval_s,
        cfg.weather_interval_s,
    )

    token = cfg.require_influx_token()
    storage: Storage = InfluxStorage(
        url=cfg.influx_url, token=token, org=cfg.influx_org, bucket=cfg.influx_bucket
    )

    stop = asyncio.Event()
    _install_signal_handlers(asyncio.get_running_loop(), stop)

    try:
        await asyncio.gather(
            _poll_hoymiles(cfg, storage, stop),
            _poll_vue(cfg, storage, stop),
            _poll_weather(cfg, storage, stop),
        )
    finally:
        storage.close()

    return 0


def main() -> None:
    sys.exit(asyncio.run(amain()))


if __name__ == "__main__":
    main()

"""Hoymiles HYS (hybrid) inverter reads via the local DTU.

Returns a flat dict[str, float] of metrics suitable for writing to a TSDB.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from hoymiles_wifi.dtu import DTU

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class HoymilesReading:
    inverter_sn: str
    metrics: dict[str, float]
    """Flat metric_name -> value. Keys are namespaced (e.g. battery.state_of_charge)."""


def _flatten_power_flow(pf) -> dict[str, float]:
    # DFlowMO: pv_to_load, pv_to_battery, pv_to_grid, battery_to_load,
    # grid_to_load, battery_to_grid, state_of_charge.
    return {
        f"flow.{name}": float(getattr(pf, name))
        for name in (
            "pv_to_load",
            "pv_to_battery",
            "pv_to_grid",
            "battery_to_load",
            "grid_to_load",
            "battery_to_grid",
        )
    }


def _flatten_battery(bms) -> dict[str, float]:
    # DBmsMO: state_of_charge, voltage, current, power, etc.
    return {
        f"battery.{name}": float(getattr(bms, name))
        for name in (
            "state_of_charge",
            "state_of_health",
            "voltage",
            "current",
            "power",
            "energy_charged",
            "energy_discharged",
        )
    }


async def read(dtu_host: str) -> HoymilesReading | None:
    """Single read of inverter state. Returns None if the DTU didn't answer."""
    dtu = DTU(dtu_host)

    gw = await dtu.async_get_gateway_info()
    if gw is None or not gw.mdevinfo:
        log.warning("hoymiles: no gateway/mdev info from %s", dtu_host)
        return None

    dtu_sn = gw.serial_number
    inverter_sn = gw.mdevinfo[0].serial_number

    es = await dtu.async_get_energy_storage_data(dtu_sn, inverter_sn)
    if es is None:
        log.warning("hoymiles: no energy storage data from %s", dtu_host)
        return None

    metrics: dict[str, float] = {}
    metrics.update(_flatten_battery(es.battery_management))
    metrics.update(_flatten_power_flow(es.power_flow))

    # Computed convenience: net PV production (W) = sum of pv_to_*
    metrics["pv.production"] = (
        metrics["flow.pv_to_load"]
        + metrics["flow.pv_to_battery"]
        + metrics["flow.pv_to_grid"]
    )
    # Net grid (W). Positive = importing, negative = exporting.
    metrics["grid.net"] = metrics["flow.grid_to_load"] - metrics["flow.battery_to_grid"]

    return HoymilesReading(inverter_sn=inverter_sn, metrics=metrics)

"""Emporia Vue reads via pyemvue.

Caches the PyEmVue client across calls (it holds refresh tokens that pyemvue
rotates in place into emporia_keys_file).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

import pyemvue
from pyemvue.enums import Scale, Unit

log = logging.getLogger(__name__)

# Module-level cache of the logged-in client + device list.
_client: pyemvue.PyEmVue | None = None
_device_gids: list[int] | None = None
_device_info: dict[int, object] | None = None


@dataclass(frozen=True)
class ChannelReading:
    gid: int
    channel_num: str        # e.g. "1,2,3" (Mains), "1", "Balance"
    is_main: bool           # True iff channel_num == "1,2,3" (the device's own total)
    device_name: str
    channel_name: str       # display label
    usage_kwh: float


@dataclass(frozen=True)
class ChargerReading:
    gid: int
    device_name: str        # resolved from the device list; "" if unknown
    on: bool                # charger_on
    charging_rate_a: int    # commanded rate in amps
    max_charging_rate_a: int
    status: str             # e.g. "ChargingComplete", "InProgress", "" if absent
    fault_text: str


def _login(keys_path: str) -> pyemvue.PyEmVue:
    with open(keys_path) as f:
        data = json.load(f)
    client = pyemvue.PyEmVue()
    client.login(
        id_token=data["id_token"],
        access_token=data["access_token"],
        refresh_token=data["refresh_token"],
        token_storage_file=keys_path,
    )
    return client


def _refresh_devices(client: pyemvue.PyEmVue) -> tuple[list[int], dict[int, object]]:
    devices = client.get_devices()
    gids: list[int] = []
    info: dict[int, object] = {}
    for d in devices:
        if d.device_gid not in gids:
            gids.append(d.device_gid)
            info[d.device_gid] = d
        else:
            # Same gid reported twice with different channel sets; merge.
            info[d.device_gid].channels += d.channels
    return gids, info


def read(keys_path: str, include_devices: set[str] | None = None) -> list[ChannelReading]:
    """Single read of all Vue devices/channels. Returns minute-scale kWh per channel.

    If `include_devices` is non-empty, only channels from those device_names
    are returned (allowlist). If None or empty, all devices are included.
    """
    global _client, _device_gids, _device_info

    if _client is None:
        log.info("vue: logging in via %s", keys_path)
        _client = _login(keys_path)
        _device_gids, _device_info = _refresh_devices(_client)

    assert _device_gids is not None and _device_info is not None

    usage = _client.get_device_list_usage(
        deviceGids=_device_gids,
        instant=None,
        scale=Scale.MINUTE.value,
        unit=Unit.KWH.value,
    )

    out: list[ChannelReading] = []
    _walk(usage, _device_info, out)

    if include_devices:
        before = len(out)
        out = [c for c in out if c.device_name in include_devices]
        dropped = before - len(out)
        if dropped:
            log.debug("vue: dropped %d channels not on the allowlist", dropped)

    return out


def read_chargers() -> list[ChargerReading]:
    """Read EVSE state for every charger on the account.

    Requires that `read()` has been called at least once in this process (so the
    PyEmVue client is logged in and the device name lookup is populated).
    """
    if _client is None or _device_info is None:
        # Defer to read() which both logs in and refreshes device_info.
        raise RuntimeError("vue.read() must be called before vue.read_chargers()")

    _, chargers = _client.get_devices_status()
    out: list[ChargerReading] = []
    for ch in chargers:
        dev = _device_info.get(ch.device_gid)
        name = getattr(dev, "device_name", "") if dev else ""
        out.append(
            ChargerReading(
                gid=ch.device_gid,
                device_name=name,
                on=bool(ch.charger_on),
                charging_rate_a=int(ch.charging_rate or 0),
                max_charging_rate_a=int(ch.max_charging_rate or 0),
                status=str(ch.status or ""),
                fault_text=str(ch.fault_text or ""),
            )
        )
    return out


def _walk(usage_dict, info, out: list[ChannelReading]) -> None:
    for gid, device in usage_dict.items():
        # Sub-devices may not be in `info` — fall back to gid as a label.
        device_name = (
            getattr(info[gid], "device_name", str(gid)) if gid in info else str(gid)
        )
        for channelnum, channel in device.channels.items():
            ch_str = str(channelnum)
            channel_name = channel.name
            if channel_name == "Main":
                channel_name = device_name
            out.append(
                ChannelReading(
                    gid=gid,
                    channel_num=ch_str,
                    is_main=(ch_str == "1,2,3"),
                    device_name=device_name,
                    channel_name=channel_name,
                    usage_kwh=float(channel.usage) if channel.usage is not None else 0.0,
                )
            )
            if channel.nested_devices:
                _walk(channel.nested_devices, info, out)

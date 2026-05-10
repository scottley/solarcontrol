#!/usr/bin/env python3
"""One-shot Vue inspector.

Prints the device tree, every channel, and current minute-scale usage in both
kWh-per-minute and equivalent watts. Use this to diagnose what Vue actually
sees vs. what you expect (e.g. circuits that aren't on a CT, branches that
bypass the Mains CT clamps, EVSE reported as a separate device, etc.).

Usage on the Pi:
    cd ~/solarcontrol
    .venv/bin/python tools/vue_list.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running from repo root or anywhere; ensure repo modules are importable.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import vue  # noqa: E402


def main() -> int:
    keys_path = "emporia_keys.json"
    channels = vue.read(keys_path)

    if not channels:
        print("no channels returned")
        return 1

    # Group by device for readable output.
    by_device: dict[str, list] = {}
    for c in channels:
        by_device.setdefault(c.device_name, []).append(c)

    grand_main = 0.0
    grand_circuits = 0.0  # individual + Balance, per device

    for device_name, rows in by_device.items():
        # Sort: main first, then numeric channels, then Balance/others.
        def sort_key(c):
            if c.is_main:
                return (0, "")
            if c.channel_num.isdigit():
                return (1, int(c.channel_num))
            return (2, c.channel_num)
        rows.sort(key=sort_key)

        print(f"\n=== {device_name} (gid={rows[0].gid}) ===")
        print(f"{'channel':<10} {'name':<28} {'kWh/min':>10} {'≈ watts':>10}")
        print(f"{'-'*10} {'-'*28} {'-'*10} {'-'*10}")

        device_main = 0.0
        device_circuits = 0.0
        for c in rows:
            watts = c.usage_kwh * 60_000.0
            mark = "*" if c.is_main else " "
            print(f"{mark}{c.channel_num:<9} {c.channel_name:<28} {c.usage_kwh:>10.4f} {watts:>10.0f}")
            if c.is_main:
                device_main += c.usage_kwh
            elif c.channel_num != "Balance":
                device_circuits += c.usage_kwh

        print(f"{'':<10} {'(* = device Mains)':<28}")
        print(f"{'':<10} {'device Mains':<28} {device_main:>10.4f} {device_main*60_000:>10.0f}")
        print(f"{'':<10} {'sum of individual circuits':<28} {device_circuits:>10.4f} {device_circuits*60_000:>10.0f}")
        unaccounted = device_main - device_circuits
        if abs(unaccounted) > 1e-6:
            print(
                f"{'':<10} {'(Mains - circuits = unaccounted)':<28}"
                f" {unaccounted:>10.4f} {unaccounted*60_000:>10.0f}"
            )

        grand_main += device_main
        grand_circuits += device_circuits

    print()
    print(f"All-device Mains total:                {grand_main*60_000:>10.0f} W")
    print(f"All-device sum of individual circuits: {grand_circuits*60_000:>10.0f} W")
    print()
    print("If a known load (hot tub, etc.) doesn't appear, it's either:")
    print("  - on a circuit without a Vue CT clamp,")
    print("  - on a feed that bypasses the Mains CTs (separate sub-panel /")
    print("    meter-side tap), in which case Mains itself underreports.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

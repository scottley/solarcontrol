# Brief: build "Prepper Mode" for solarcontrol

Hand-off from an earlier Opus task. Build the feature using the hand-maintained
schedule (option B). Library extension to *read* the live schedule is a separate
side quest tracked in `docs/side-quests/hoymiles-protocol-re.md` — do not block
on it.

## What Prepper Mode is

A user-toggled mode for "expecting bad weather or grid trouble; fill the battery
fast, then defend it." Eventually wired to a physical GPIO toggle switch; for
now, software activation via a flag file.

State machine (re-evaluated every Hoymiles poll, every 60s):

- If Prepper is ON and SoC < 95 → set inverter mode `FORCED_CHARGING` (BMSWorkingMode value 5).
- If Prepper is ON and SoC ≥ 95 → set inverter mode `BACKUP_POWER` (value 3).
- If Prepper is OFF → set inverter mode `ECONOMIC` (value 2) with the hand-maintained schedule below.

Idempotent: only call `async_set_energy_storage_working_mode(...)` when the
target mode differs from the last one we set (track in-process; re-derive on
service start).

## Activation method

Flag file: `~/solarcontrol/state/prepper.on`. Present = ON, absent = OFF. The
prepper poller stats the file once per tick. Future GPIO handler will
`touch`/`rm` the same file.

Add a `Makefile` convenience: `make prepper-on` / `make prepper-off` that SSH
into the Pi and touch/rm.

## Hoymiles library calls

`DTU.async_set_energy_storage_working_mode(...)` is in `hoymiles-wifi`:

- For `FORCED_CHARGING` and `BACKUP_POWER`: just pass `bms_working_mode`. No
  schedule needed.
- For `ECONOMIC`: pass `bms_working_mode=BMSWorkingMode.ECONOMIC` and
  `time_settings=ECONOMY_SCHEDULE` (defined below).

## ECONOMY_SCHEDULE (hand-maintained; matches Scott's utility tariff)

Three seasonal `DateBean`s. Weekday and weekend groups identical (utility
doesn't differentiate). All time ranges end at `:59` to match Scott's working
S-Miles app convention. Export prices all 0.0 (no net metering).

Tier prices:
- On Peak (PEAK):       $0.2056/kWh
- Off Peak (OFF_PEAK):  $0.0429/kWh
- Regular (PARTIAL_PEAK): $0.0887/kWh

Time windows:
- Winter (Oct–Apr): PEAK 06:00–08:59, OFF_PEAK 21:00–05:59, PARTIAL 09:00–20:59.
- Summer (May–Sep): PEAK 17:00–19:59, OFF_PEAK 20:00–04:59, PARTIAL 05:00–16:59.

Library enforces: exactly 2 `TimeBean` groups per `DateBean`, exactly 3
`DurationBean`s per group in order `[PEAK, OFF_PEAK, PARTIAL_PEAK]`.

```python
from hoymiles_wifi.hoymiles import DateBean, TimeBean, DurationBean, TariffType

WEEKDAYS = [1, 2, 3, 4, 5]
WEEKENDS = [6, 7]

def _winter() -> list[DurationBean]:
    return [
        DurationBean(start_time="06:00", end_time="08:59",
                     in_price=0.2056, out_price=0.0, type=TariffType.PEAK),
        DurationBean(start_time="21:00", end_time="05:59",
                     in_price=0.0429, out_price=0.0, type=TariffType.OFF_PEAK),
        DurationBean(start_time="09:00", end_time="20:59",
                     in_price=0.0887, out_price=0.0, type=TariffType.PARTIAL_PEAK),
    ]

def _summer() -> list[DurationBean]:
    return [
        DurationBean(start_time="17:00", end_time="19:59",
                     in_price=0.2056, out_price=0.0, type=TariffType.PEAK),
        DurationBean(start_time="20:00", end_time="04:59",
                     in_price=0.0429, out_price=0.0, type=TariffType.OFF_PEAK),
        DurationBean(start_time="05:00", end_time="16:59",
                     in_price=0.0887, out_price=0.0, type=TariffType.PARTIAL_PEAK),
    ]

ECONOMY_SCHEDULE: list[DateBean] = [
    DateBean(start_date="01.01", end_date="04.30",
             time=[TimeBean(week=WEEKDAYS, durations=_winter()),
                   TimeBean(week=WEEKENDS, durations=_winter())]),
    DateBean(start_date="05.01", end_date="09.30",
             time=[TimeBean(week=WEEKDAYS, durations=_summer()),
                   TimeBean(week=WEEKENDS, durations=_summer())]),
    DateBean(start_date="10.01", end_date="12.31",
             time=[TimeBean(week=WEEKDAYS, durations=_winter()),
                   TimeBean(week=WEEKENDS, durations=_winter())]),
]
```

Put it in its own module (`economy_schedule.py`) — too bulky for `config.py`.

## What's already in the repo

- `hoymiles.py` — has `read(dtu_host)` returning `HoymilesReading` (battery + flow metrics). Add a `set_mode(...)` here.
- `main.py` — async loop with three pollers (hoymiles, vue, weather). Add a Prepper poller (or fold into the hoymiles poller since they share SoC).
- `storage.py` — `InfluxStorage` with helpers per measurement. Add a `prepper_point()` helper.
- `config.py` — env-overridable dataclass. Add fields for the prepper file path and soc threshold.
- Dashboard: at `grafana/dashboards/solarcontrol.json`. After the code change, add a "Prepper" stat + "Commanded inverter mode" timeseries.

## What to build

1. `economy_schedule.py` containing the data above.
2. `prepper.py` — state machine. Functions:
   - `requested(path: Path) -> bool`: `path.exists()`.
   - `decide(requested: bool, soc: float, soc_threshold: int) -> BMSWorkingMode`: returns the desired mode.
   - A class `Prepper` that holds the last-applied mode in memory and calls `set_mode` only when changing.
3. `hoymiles.set_mode(dtu_host, mode)` — wraps `async_set_energy_storage_working_mode`. Pass `ECONOMY_SCHEDULE` for ECONOMIC; pass max_power=100 (or omit) for the others.
4. `main.py` — call `prepper.tick(soc)` once per Hoymiles poll, after a successful read. Write the resulting state to Influx via a new `prepper_point` (fields: `requested` 0/1, `commanded_mode` numeric, `soc`).
5. `config.py` — add `prepper_state_file: str = "state/prepper.on"` (relative to repo dir), `prepper_soc_threshold: int = 95`.
6. `scripts/` — add `prepper-on.sh` and `prepper-off.sh` that ssh and touch/rm. Wire into Makefile.
7. Dashboard: a stat showing current Prepper requested (text mapping 1→ON green, 0→OFF gray) and a "commanded inverter mode" stat using value mapping (2→Economy, 3→Backup, 5→Forced charge).

## Constraints

- Always commit with `-m "..."` (Scott's standing feedback rule).
- Verify with `make deploy` (which pushes, pulls on Pi, restarts service).
- Mode changes affect a real inverter. Add a `PREPPER_ENABLED=0` safety default in config; only when set to `1` does the prepper actually call `set_mode`. If disabled, log what it would have done but make no API call. Helps Scott test the wiring before letting it actuate.
- Log line per tick: `prepper req=<bool> soc=<f> -> mode=<name>` whether actuating or not.
- One-tick idempotence: the in-memory "last applied" survives the process; service restart re-derives by setting whatever the state file says.

## Don't break what works

- Vue polling (devices allowlisted to `Main Panel`) and EVSE state polling are working; don't touch.
- The hoymiles poll's existing log format is `hoymiles ok soc=… pv=… grid_to_load=…`. Keep it; add prepper info on its own line.
- Weather poller exists with retries and the NWS hourly forecast for `current.kind`. Leave alone.

## Definition of done

- `make deploy` runs cleanly; `make logs` shows a `prepper ok` line each minute.
- `make prepper-on` flips the inverter into FORCED_CHARGING (verifiable in S-Miles app).
- At SoC ≥ 95 the prepper auto-transitions to BACKUP_POWER (test by setting threshold low temporarily).
- `make prepper-off` reverts to ECONOMIC with the hand-maintained schedule, and Scott's existing tariff windows look right in the inverter UI.
- Dashboard shows current Prepper state and commanded mode.

## Side-quest awareness

When `hoymiles-wifi` upstream gains a "get energy storage user set" method,
swap the `ECONOMY_SCHEDULE` source from this module's literal to a startup
capture of the inverter's actual current schedule. State machine doesn't
change.

# solarcontrol

Raspberry Pi service that monitors a Hoymiles HYS hybrid inverter, an Emporia Vue power monitor, and an Emporia EVSE, and adjusts charging / inverter modes based on solar production, home load, battery SoC, and weather.

## Architecture (workflow)

```
Mac (edit + git)  --push-->  GitHub (scottley/solarcontrol)  <--pull--  Pi (run)
        |                                                                   ^
        +-------- ssh over Tailscale: deploy / logs / restart --------------+
```

- Edits happen on the Mac. Pi never holds uncommitted code.
- Pi pulls from GitHub on every deploy and runs the app under `systemd`.
- Mac and Pi both sit on the user's tailnet, so the workflow is identical at home or remote.

## One-time setup

### 1. Pi: SSH + Tailscale

Standard Pi OS install, with `scott` as the login user. Install Tailscale and bring it up:

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```

Note the Tailscale name (e.g., `solarpi`). From the Mac, confirm:

```bash
ssh scott@solarpi   # using Tailscale MagicDNS
```

If MagicDNS isn't enabled, use the tailnet's `*.ts.net` name or the tailnet IP.

### 2. Pi: bootstrap solarcontrol

On the Pi:

```bash
curl -fsSL https://raw.githubusercontent.com/scottley/solarcontrol/main/deploy/install-on-pi.sh | bash
```

That script installs `git`, `uv`, clones the repo to `~/solarcontrol`, runs `uv sync`, and installs+enables the systemd unit at `/etc/systemd/system/solarcontrol.service`. It does **not** start the service.

### 2a. Pi: install InfluxDB + Grafana

The app writes telemetry to a local InfluxDB v2 instance, and Grafana reads from it. Both run on the Pi.

```bash
cd ~/solarcontrol
bash deploy/install-services.sh
```

That installs `influxdb2` and `grafana` from their official apt repos, runs `influx setup` (creates org `solarcontrol`, bucket `solarcontrol`, admin user, and a write-scoped token for the app), and writes the connection details to `~/solarcontrol/.env`. It prints the InfluxDB admin password once — save it.

Reach the UIs over Tailscale:
- Grafana: `http://raspberrypi:3000` (initial creds: `admin / admin`, prompted to change on first login)
- InfluxDB: `http://raspberrypi:8086`

### 2b. Pi: drop in `emporia_keys.json` and start

```bash
# from Mac, copy your existing keys file:
scp emporia_keys.json scott@raspberrypi:~/solarcontrol/

# then on the Pi:
sudo systemctl start solarcontrol
journalctl -u solarcontrol -f
```

### 2c. Grafana: add the InfluxDB datasource

In Grafana → Connections → Data sources → Add data source → InfluxDB:
- Query language: **Flux**
- URL: `http://127.0.0.1:8086`
- Organization: `solarcontrol`
- Default Bucket: `solarcontrol`
- Token: the value of `INFLUX_TOKEN` from `~/solarcontrol/.env`

Then Save & Test. From there, build dashboards against the `hoymiles`, `vue`, and `weather` measurements.

### 3. Mac: configure deploy scripts

```bash
cp deploy/.env.example deploy/.env.local
$EDITOR deploy/.env.local      # set PI_HOST=<tailscale-name>
```

### 4. Mac: passwordless sudo for restart (optional but convenient)

Each `make deploy` calls `sudo systemctl restart solarcontrol` on the Pi. To avoid being prompted, on the Pi add to `/etc/sudoers.d/solarcontrol`:

```
scott ALL=(root) NOPASSWD: /bin/systemctl restart solarcontrol, /bin/systemctl status solarcontrol
```

(Use `sudo visudo -f /etc/sudoers.d/solarcontrol`.)

## Daily loop

```bash
# edit on the Mac, then:
make deploy        # push + pi pull + uv sync + restart
make logs          # tail journalctl on the Pi
make status        # systemctl status on the Pi
make restart       # restart without redeploy
make ssh           # interactive ssh
```

`make deploy` will refuse to run if there's no `deploy/.env.local`.

## Layout

```
.
├── deploy/
│   ├── solarcontrol.service     systemd unit installed to /etc/systemd/system/
│   ├── install-on-pi.sh         one-shot Pi bootstrap
│   ├── .env.example             template for Pi host config
│   └── .env.local               (gitignored) PI_HOST etc.
├── scripts/
│   ├── _lib.sh                  loads .env.local, shared helpers
│   ├── deploy.sh                push + remote pull + restart
│   ├── logs.sh, status.sh, restart.sh, ssh.sh
├── Makefile                     thin wrapper over scripts/
├── main.py                      service entry point (run by systemd)
├── config.py                    runtime configuration (env-overridable)
├── hoymiles.py                  Hoymiles DTU read
├── vue.py                       Emporia Vue read
├── weather.py                   weather read
├── storage.py                   InfluxDB writer + Storage protocol
└── pyproject.toml               uv-managed Python 3.13 project
```

## Secrets and configuration

Two files live on the Pi only (both gitignored):

- `~/solarcontrol/emporia_keys.json` — Emporia OAuth tokens. `pyemvue` rotates them in place.
- `~/solarcontrol/.env` — `INFLUX_TOKEN`, `INFLUX_URL`, `INFLUX_ORG`, `INFLUX_BUCKET`, plus any optional overrides for the values defined in `config.py` (e.g. `HOYMILES_INTERVAL_S=30`). The systemd unit reads it via `EnvironmentFile=`.

Generated by `deploy/install-services.sh`; safe to edit by hand. After editing, `make restart` to pick up changes.

### Tunable config (in `config.py`, env-overridable)

| Variable                | Default                              | What it controls                          |
| ----------------------- | ------------------------------------ | ----------------------------------------- |
| `HOYMILES_INTERVAL_S`   | `60`                                 | Hoymiles inverter poll period             |
| `VUE_INTERVAL_S`        | `60`                                 | Emporia Vue poll period                   |
| `WEATHER_INTERVAL_S`    | `3600`                               | Weather fetch period                      |
| `DTU_HOST`              | `192.168.1.5`                        | Hoymiles DTU IP                           |
| `WEATHER_LOCATION`      | `Jamestown, Missouri, United States` | python_weather query                      |
| `EMPORIA_KEYS_FILE`     | `emporia_keys.json`                  | Vue token store (relative to cwd)         |
| `INFLUX_URL`            | `http://127.0.0.1:8086`              | InfluxDB endpoint                         |
| `INFLUX_ORG`            | `solarcontrol`                       | InfluxDB org                              |
| `INFLUX_BUCKET`         | `solarcontrol`                       | InfluxDB bucket                           |
| `INFLUX_TOKEN`          | (empty — required)                   | App token; populated by `install-services.sh` |

## Goals

### Production maximizing by adding load

- Detect when there's excess solar potential that isn't being used.
- Activate the EVSE.
- Adjust EVSE charging rate to avoid grid import, recomputing each minute.
- Notify (push/SMS) that there's excess production so household load can be added (laundry, etc.).

### Off-peak battery charge optimization

- If tomorrow is forecast to be high production, reduce overnight off-peak battery charge target.

### Prepper mode

- Force-charge the house battery, then switch to backup mode after 100% SoC.
- Toggle via switch, pushbutton, or web control panel.

## Notes

### Hoymiles power flow conventions

- `battery_to_grid` — negative = charging
- `grid_to_load` — negative = exporting (should not happen in normal operation)

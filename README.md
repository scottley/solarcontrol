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

That script installs `git`, `uv`, clones the repo to `~/solarcontrol`, runs `uv sync`, and installs+enables the systemd unit at `/etc/systemd/system/solarcontrol.service`. It does **not** start the service — copy `emporia_keys.json` into `~/solarcontrol/` first, then:

```bash
sudo systemctl start solarcontrol
journalctl -u solarcontrol -f
```

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
├── pv.py                        Emporia / Hoymiles / weather query helpers
└── pyproject.toml               uv-managed Python 3.13 project
```

## Secrets

`emporia_keys.json` is gitignored and lives only on the Pi at `~/solarcontrol/emporia_keys.json`. The Mac never holds production tokens. If you also need a `.env`, drop it in `~/solarcontrol/.env` on the Pi — the systemd unit picks it up via `EnvironmentFile=`.

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

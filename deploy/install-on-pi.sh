#!/usr/bin/env bash
# Run this ONCE on the Pi to bootstrap solarcontrol.
# Usage (on the Pi):
#   curl -fsSL https://raw.githubusercontent.com/scottley/solarcontrol/main/deploy/install-on-pi.sh | bash
# or, if the repo is already cloned:
#   bash deploy/install-on-pi.sh

set -euo pipefail

REPO_URL="https://github.com/scottley/solarcontrol.git"
REPO_DIR="${HOME}/solarcontrol"
SERVICE_NAME="solarcontrol"

log() { printf '\033[1;34m[install]\033[0m %s\n' "$*"; }

# 1) System packages we rely on
log "Installing apt prerequisites"
sudo apt-get update -y
sudo apt-get install -y --no-install-recommends git curl ca-certificates

# 2) Make sure scott can read GPIO without sudo
if ! id -nG "$USER" | tr ' ' '\n' | grep -qx gpio; then
    log "Adding $USER to gpio group (re-login required for it to take effect)"
    sudo usermod -aG gpio "$USER"
fi

# 3) uv (fast Python package manager, also installs Python 3.13 if missing)
if ! command -v uv >/dev/null 2>&1; then
    log "Installing uv"
    curl -LsSf https://astral.sh/uv/install.sh | sh
fi
export PATH="${HOME}/.local/bin:${PATH}"

# 4) Clone or update the repo
if [[ ! -d "${REPO_DIR}/.git" ]]; then
    log "Cloning ${REPO_URL} -> ${REPO_DIR}"
    git clone "${REPO_URL}" "${REPO_DIR}"
else
    log "Repo already present at ${REPO_DIR}; pulling"
    git -C "${REPO_DIR}" pull --ff-only
fi

# 5) Sync Python deps into .venv
log "Installing Python toolchain + project deps via uv"
cd "${REPO_DIR}"
uv sync

# 6) Install systemd unit
log "Installing systemd unit"
sudo install -m 0644 "${REPO_DIR}/deploy/${SERVICE_NAME}.service" "/etc/systemd/system/${SERVICE_NAME}.service"
sudo systemctl daemon-reload
sudo systemctl enable "${SERVICE_NAME}.service"

log "Done. Start with:  sudo systemctl start ${SERVICE_NAME}"
log "Watch logs with:   journalctl -u ${SERVICE_NAME} -f"
log "NOTE: copy your emporia_keys.json into ${REPO_DIR} before starting the service."

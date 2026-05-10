#!/usr/bin/env bash
# Deploy: push current branch to GitHub, then on the Pi pull + uv sync + (maybe) refresh
# systemd unit + restart service.
# Requires: deploy/.env.local configured.

set -euo pipefail
# shellcheck source=_lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"

BRANCH="$(git -C "${REPO_ROOT}" rev-parse --abbrev-ref HEAD)"

info "Pushing ${BRANCH} to origin"
git -C "${REPO_ROOT}" push origin "${BRANCH}"

info "Deploying to ${PI_TARGET}:${PI_REPO}"
ssh -o ConnectTimeout=5 "${PI_TARGET}" \
    PI_REPO="${PI_REPO}" \
    SERVICE_NAME="${SERVICE_NAME}" \
    BRANCH="${BRANCH}" \
    bash -se <<'EOF'
set -euo pipefail
cd "${PI_REPO}"

echo "[pi] git pull"
git fetch --all --prune
git checkout "${BRANCH}"
git pull --ff-only origin "${BRANCH}"

echo "[pi] uv sync"
export PATH="${HOME}/.local/bin:${PATH}"
uv sync

# Refresh the systemd unit if the file in the repo differs from the installed one.
UNIT_SRC="${PI_REPO}/deploy/${SERVICE_NAME}.service"
UNIT_DST="/etc/systemd/system/${SERVICE_NAME}.service"
if ! sudo cmp -s "${UNIT_SRC}" "${UNIT_DST}"; then
    echo "[pi] updating ${UNIT_DST}"
    sudo install -m 0644 "${UNIT_SRC}" "${UNIT_DST}"
    sudo systemctl daemon-reload
fi

echo "[pi] restart ${SERVICE_NAME}"
sudo systemctl restart "${SERVICE_NAME}"
sudo systemctl --no-pager --lines=0 status "${SERVICE_NAME}" || true
EOF

ok "deploy complete"

#!/usr/bin/env bash
# Tail the systemd journal for the service on the Pi.
# Pass extra args through to journalctl, e.g.:  scripts/logs.sh --since "10 min ago"

set -euo pipefail
# shellcheck source=_lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"

# -t to allocate a TTY so Ctrl-C cleanly tears down journalctl.
ssh -t "${PI_TARGET}" journalctl -u "${SERVICE_NAME}" -f --output=short-iso "$@"

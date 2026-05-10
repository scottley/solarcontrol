#!/usr/bin/env bash
# Convenience: open an interactive SSH session to the Pi.

set -euo pipefail
# shellcheck source=_lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"

exec ssh "${PI_TARGET}" "$@"

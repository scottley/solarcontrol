#!/usr/bin/env bash
# Show service status on the Pi.

set -euo pipefail
# shellcheck source=_lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"

ssh "${PI_TARGET}" systemctl --no-pager status "${SERVICE_NAME}"

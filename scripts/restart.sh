#!/usr/bin/env bash
# Restart the service on the Pi without redeploying.

set -euo pipefail
# shellcheck source=_lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"

ssh "${PI_TARGET}" sudo systemctl restart "${SERVICE_NAME}"
ssh "${PI_TARGET}" systemctl --no-pager --lines=0 status "${SERVICE_NAME}"

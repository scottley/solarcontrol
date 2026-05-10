#!/usr/bin/env bash
# Shared helpers for Mac-side deploy/logs/ssh scripts. Sourced, not executed.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

ENV_LOCAL="${REPO_ROOT}/deploy/.env.local"
ENV_EXAMPLE="${REPO_ROOT}/deploy/.env.example"

if [[ ! -f "${ENV_LOCAL}" ]]; then
    cat >&2 <<EOF
error: ${ENV_LOCAL} not found.
       cp ${ENV_EXAMPLE} ${ENV_LOCAL}  and fill in PI_HOST.
EOF
    exit 1
fi

# shellcheck disable=SC1090
source "${ENV_LOCAL}"

: "${PI_HOST:?PI_HOST not set in deploy/.env.local}"
: "${PI_USER:?PI_USER not set in deploy/.env.local}"
: "${PI_REPO:?PI_REPO not set in deploy/.env.local}"
: "${SERVICE_NAME:?SERVICE_NAME not set in deploy/.env.local}"

PI_TARGET="${PI_USER}@${PI_HOST}"

color() { printf '\033[1;%dm%s\033[0m\n' "$1" "$2"; }
info()  { color 34 "[$(basename "$0")] $*"; }
ok()    { color 32 "[$(basename "$0")] $*"; }
warn()  { color 33 "[$(basename "$0")] $*"; }
fail()  { color 31 "[$(basename "$0")] $*"; exit 1; }

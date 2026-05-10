#!/usr/bin/env python3
"""Pull the live solarcontrol dashboard from Grafana into the repo.

Writes grafana/dashboards/solarcontrol.json from whatever Grafana currently
has for the dashboard with UID "solarcontrol".

Reads GRAFANA_URL and GRAFANA_TOKEN from deploy/.env.local. Process env
overrides the file. Create the token in Grafana:
    Administration -> Users and access -> Service accounts -> Add service
    account -> role Editor -> Add service account token.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = REPO_ROOT / "deploy" / ".env.local"
DASHBOARD_PATH = REPO_ROOT / "grafana" / "dashboards" / "solarcontrol.json"
DASHBOARD_UID = "solarcontrol"


def load_env(path: Path) -> dict[str, str]:
    """Minimal .env loader (KEY=VALUE per line, # comments, quotes stripped)."""
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def main() -> int:
    env = load_env(ENV_FILE)
    base = os.environ.get("GRAFANA_URL") or env.get("GRAFANA_URL", "")
    token = os.environ.get("GRAFANA_TOKEN") or env.get("GRAFANA_TOKEN", "")
    if not base:
        print("error: GRAFANA_URL not set in deploy/.env.local or environment", file=sys.stderr)
        return 1
    if not token:
        print(
            "error: GRAFANA_TOKEN not set.\n"
            "       Create one in Grafana -> Administration -> Users and access ->\n"
            "       Service accounts -> Add service account (role: Editor) ->\n"
            "       Add service account token. Paste into deploy/.env.local.",
            file=sys.stderr,
        )
        return 1

    url = f"{base.rstrip('/')}/api/dashboards/uid/{DASHBOARD_UID}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = json.load(resp)
    except urllib.error.HTTPError as e:
        print(f"error: HTTP {e.code} from {url}: {e.read().decode(errors='replace')[:200]}", file=sys.stderr)
        return 1
    except urllib.error.URLError as e:
        print(f"error: cannot reach {url}: {e.reason}", file=sys.stderr)
        return 1

    dashboard = body.get("dashboard")
    if not dashboard:
        print(f"error: no 'dashboard' field in response from {url}", file=sys.stderr)
        return 1

    # Pretty-print so diffs are readable. 2-space matches Grafana's UI export.
    text = json.dumps(dashboard, indent=2, ensure_ascii=False) + "\n"
    DASHBOARD_PATH.parent.mkdir(parents=True, exist_ok=True)
    DASHBOARD_PATH.write_text(text)
    print(f"wrote {DASHBOARD_PATH.relative_to(REPO_ROOT)} ({len(text)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

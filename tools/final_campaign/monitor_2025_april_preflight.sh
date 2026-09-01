#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
exec "$ROOT/.venv-v28-win/Scripts/python.exe" "$ROOT/tools/final_campaign/monitor_month_campaign.py" --campaign april "$@"

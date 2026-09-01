#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
exec "$ROOT/.venv-v28-win/Scripts/python.exe" "$ROOT/tools/final_campaign/run_month_campaign.py" --campaign april "$@"

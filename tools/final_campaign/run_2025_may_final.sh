#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
[[ -f "$ROOT/frozen_artifacts/v28_may_final_science/MAY_FINAL_SCIENCE_PREEXECUTION_FREEZE.json" ]] || { echo "MAY_FREEZE_REQUIRED" >&2; exit 2; }
exec "$ROOT/.venv-v28-win/Scripts/python.exe" "$ROOT/tools/final_campaign/run_month_campaign.py" --campaign may "$@"

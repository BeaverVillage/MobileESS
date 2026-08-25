#!/usr/bin/env bash
set -Eeuo pipefail

repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
python_bin="${PFR_PYTHON:-/home/jaewon/miniconda3/envs/power_v61_gpu/bin/python}"
run_root=""
risk_calibration=""
preflight_only=0

stop_run() {
    trap - INT TERM
    echo "INTERRUPTED: January-to-April execution stopped; partial results are preserved." >&2
    exit 130
}
trap stop_run INT TERM

while (($#)); do
    case "$1" in
        --run-root) (($# >= 2)) || exit 64; run_root="$2"; shift 2 ;;
        --risk-calibration) (($# >= 2)) || exit 64; risk_calibration="$2"; shift 2 ;;
        --preflight-only) preflight_only=1; shift ;;
        *) echo "Usage: $0 --run-root ABSOLUTE_PATH --risk-calibration FILE [--preflight-only]" >&2; exit 64 ;;
    esac
done
if [[ -z "$run_root" || "$run_root" != /* || -z "$risk_calibration" || ! -f "$risk_calibration" ]]; then
    echo "An absolute --run-root and existing frozen --risk-calibration are required." >&2
    exit 2
fi

cd "$repo_dir"
common=(--run-root "$run_root" --risk-calibration "$risk_calibration")
if ((preflight_only)); then
    bash "$repo_dir/pfr/tools/run_january_to_march_2025_local.sh" \
        "${common[@]}" --preflight-only
    bash "$repo_dir/pfr/tools/prepare_april_2025_local.sh" --plan-only
    echo "JANUARY_TO_APRIL_PREFLIGHT_STATUS=PASS_NO_EPISODES_STARTED"
    exit 0
fi

bash "$repo_dir/pfr/tools/run_january_to_march_2025_local.sh" \
    "${common[@]}"
echo "JANUARY_TO_MARCH_FROZEN_EXECUTION=PASS; STARTING_APRIL_PREPROCESSING"
bash "$repo_dir/pfr/tools/prepare_april_2025_local.sh"
echo "APRIL_PREPROCESSING=PASS; STARTING_APRIL_EXECUTION"
bash "$repo_dir/pfr/tools/run_april_2025_local.sh" "${common[@]}"
"$python_bin" -m pfr.tools.audit_january_to_april_consistency \
    --run-root "$run_root" --risk-calibration "$risk_calibration" \
    --report "$run_root/JANUARY_TO_APRIL_CONSISTENCY_AUDIT.json"
echo "JANUARY_TO_APRIL_EXECUTION_STATUS=PASS"

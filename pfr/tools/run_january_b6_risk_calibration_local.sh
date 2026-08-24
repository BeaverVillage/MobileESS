#!/usr/bin/env bash
set -Eeuo pipefail

repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
python_bin="${PFR_PYTHON:-/home/jaewon/miniconda3/envs/power_v61_gpu/bin/python}"
run_root=""
preflight_only=0

stop_run() {
    trap - INT TERM
    echo "INTERRUPTED: January B6 calibration stopped; partial results are preserved." >&2
    exit 130
}
trap stop_run INT TERM

while (($#)); do
    case "$1" in
        --run-root)
            (($# >= 2)) || { echo "Missing --run-root value" >&2; exit 64; }
            run_root="$2"; shift 2 ;;
        --preflight-only) preflight_only=1; shift ;;
        *) echo "Usage: $0 --run-root ABSOLUTE_PATH [--preflight-only]" >&2; exit 64 ;;
    esac
done
if [[ -z "$run_root" || "$run_root" != /* ]]; then
    echo "--run-root must be an absolute isolated path." >&2
    exit 2
fi

calibration_root="$run_root/january_b6_raw"
artifact="$run_root/calibration/PFR5_EVENT_RISK_CALIBRATION_JAN2025.json"
common=(
    --start-day 1 --end-day 31 --day-workers 4 --gurobi-threads 4
    --diagnostic-method B6 --output-root "$calibration_root"
)
if ((preflight_only)); then common+=(--preflight-only); fi

cd "$repo_dir"
bash "$repo_dir/pfr/tools/run_january_2025_local.sh" "${common[@]}"
if ((preflight_only)); then
    echo "JANUARY_B6_CALIBRATION_PREFLIGHT=PASS_NO_EPISODES_STARTED"
    exit 0
fi

"$python_bin" -m pfr.tools.verify_daily_campaign_storage \
    --repo "$repo_dir" --root "$calibration_root" \
    --start-date 2025-01-01 --days 31 --diagnostic-method B6 \
    --report "$calibration_root/STORAGE_VERIFICATION.json"
"$python_bin" -m pfr.tools.build_january_b6_risk_calibration \
    --source-root "$calibration_root" --output "$artifact"
"$python_bin" -c 'from pathlib import Path; import sys; from pfr.risk_calibration import load_frozen_risk_calibration; x=load_frozen_risk_calibration(Path(sys.argv[1])); print("RISK_CALIBRATION_FROZEN", x.authority_id, x.normalized_joint_quantile, x.artifact_sha256)' "$artifact"
echo "JANUARY_B6_CALIBRATION_STATUS=FROZEN"
echo "RISK_CALIBRATION_ARTIFACT=$artifact"

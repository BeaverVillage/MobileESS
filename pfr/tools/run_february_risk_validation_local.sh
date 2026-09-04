#!/usr/bin/env bash
set -Eeuo pipefail

repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
python_bin="${PFR_PYTHON:-/home/jaewon/miniconda3/envs/power_v61_gpu/bin/python}"
work="/home/jaewon/mobile_ess_work"
base="$work/frozen_artifacts"
period_contract="$repo_dir/pfr/contracts/FROZEN_2025_FULL_MONTH_VALIDATION_PERIODS_V1.json"
period_id="FEB2025_FULL"
shared="$base/PFR_FEB2025_FULL_SHARED_EXOGENOUS_V13_13"
inputs="$base/PFR_FEB2025_FULL_V13_13_DAILY_INPUTS"
canonical="$base/stage_kestrel_f30_resource_aware_job_power_policy_v2_0_32_r6c_20260806T122335/CANONICAL_F30_RACK_POWER_JOB_BASE_PREFROZEN_R6C.parquet"
run_root=""
calibration=""
preflight_only=0

stop_run() {
    trap - INT TERM
    echo "INTERRUPTED: February risk validation stopped; partial results are preserved." >&2
    exit 130
}
trap stop_run INT TERM

while (($#)); do
    case "$1" in
        --run-root)
            (($# >= 2)) || { echo "Missing --run-root value" >&2; exit 64; }
            run_root="$2"; shift 2 ;;
        --risk-calibration)
            (($# >= 2)) || { echo "Missing --risk-calibration value" >&2; exit 64; }
            calibration="$2"; shift 2 ;;
        --preflight-only) preflight_only=1; shift ;;
        *) echo "Usage: $0 --run-root ABSOLUTE_PATH --risk-calibration FILE [--preflight-only]" >&2; exit 64 ;;
    esac
done
if [[ -z "$run_root" || "$run_root" != /* || ! -f "$calibration" ]]; then
    echo "An absolute --run-root and existing --risk-calibration are required." >&2
    exit 2
fi

expected_full_commit_sha="${PFR_EXPECTED_FULL_COMMIT_SHA:-}"
expected_branch="${PFR_EXPECTED_BRANCH:-codex/feb03-predictive-native}"
if [[ ! "$expected_full_commit_sha" =~ ^[0-9a-f]{40}$ ]]; then
    echo "Set PFR_EXPECTED_FULL_COMMIT_SHA to the frozen implementation commit." >&2
    exit 2
fi
mkdir -p "$run_root/preflight"
cd "$repo_dir"
"$python_bin" -m pfr.tools.assert_experiment_source_freeze \
    --repo "$repo_dir" --expected-full-commit-sha "$expected_full_commit_sha" \
    --expected-branch "$expected_branch" \
    --migration-authority "$repo_dir/pfr/contracts/IDC_MIGRATION_AUTHORITY_V1.json" \
    --report "$run_root/preflight/SOURCE_FREEZE_GATE.json"
"$python_bin" -m pfr.tools.preflight_full_month_2025 \
    --repo "$repo_dir" --period-id "$period_id" --shared-root "$shared" \
    --input-root "$inputs" \
    --route-catalog "$base/PFR3_FIXED_K3_PHYSICS_CURRENT/FROZEN_K3_PHYSICS_GEOMETRY.json" \
    --report "$run_root/preflight/PREFLIGHT_REPORT.json"
"$python_bin" -c 'from pathlib import Path; import sys; from pfr.risk_calibration import load_frozen_risk_calibration; load_frozen_risk_calibration(Path(sys.argv[1]))' "$calibration"
if ((preflight_only)); then
    echo "FEBRUARY_RISK_VALIDATION_PREFLIGHT=PASS_NO_EPISODES_STARTED"
    exit 0
fi

common=(
    --repo "$repo_dir" --period-id "$period_id" --period-contract "$period_contract"
    --day-workers 4 --capture-day-logs --continue-after-failure
    --shared-root "$shared"
    --exact-package-root /mnt/c/Users/kjw39/Downloads/stage_mess_grid_v2038_exact_sweep_power_v70_final_v1_package
    --authority-package-root "$work/run_packages/K9H7_V2044R11R1_20260807T191351"
    --primary-root "$work/processed/power_v70_3ph"
    --initial-state "$inputs/pre/DAILY_CANONICAL_PRE_MANIFEST.json"
    --independent-jobs "$inputs/jobs/INDEPENDENT_JOB_COHORT.parquet"
    --canonical-jobs "$canonical"
    --power-curve "$repo_dir/pfr/contracts/H100_UTILIZATION_POWER_CURVE.json"
    --mobility-root "$shared/mobility"
    --route-catalog "$base/PFR3_FIXED_K3_PHYSICS_CURRENT/FROZEN_K3_PHYSICS_GEOMETRY.json"
    --mobility-template-bank "$shared/mobility/E4B_FULLFIT_TEMPLATE_BANK_129.parquet"
    --workload-uncertainty "$base/PFR3_V13_2_WORKLOAD_UNCERTAINTY_CURRENT/PFR3_WORKLOAD_UNCERTAINTY_V13_2.json"
    --factorized-uncertainty "$base/PFR3_V13_2_FACTORIZED_UNCERTAINTY_CURRENT/PFR3_FACTORIZED_UNCERTAINTY_V13_2.json"
    --migration-authority "$repo_dir/pfr/contracts/IDC_MIGRATION_AUTHORITY_V1.json"
)

export PFR_GUROBI_THREADS=4 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONHASHSEED=0
"$python_bin" -m pfr.tools.run_frozen_rep_week_daily_campaign \
    "${common[@]}" --diagnostic-method B6 --output "$run_root/B6_RAW"
"$python_bin" -m pfr.tools.run_frozen_rep_week_daily_campaign \
    "${common[@]}" --diagnostic-method B7 \
    --risk-calibration "$calibration" --output "$run_root/B7_CALIBRATED"
"$python_bin" -m pfr.tools.verify_daily_campaign_storage \
    --repo "$repo_dir" --root "$run_root/B6_RAW" --start-date 2025-02-01 \
    --days 28 --diagnostic-method B6 --report "$run_root/B6_RAW/STORAGE_VERIFICATION.json"
"$python_bin" -m pfr.tools.verify_daily_campaign_storage \
    --repo "$repo_dir" --root "$run_root/B7_CALIBRATED" --start-date 2025-02-01 \
    --days 28 --diagnostic-method B7 --report "$run_root/B7_CALIBRATED/STORAGE_VERIFICATION.json"
"$python_bin" -m pfr.tools.validate_february_risk_calibration \
    --b6-root "$run_root/B6_RAW" --b7-root "$run_root/B7_CALIBRATED" \
    --risk-calibration "$calibration" \
    --report "$run_root/FEBRUARY_RISK_CALIBRATION_VALIDATION.json"
echo "FEBRUARY_RISK_VALIDATION_STATUS=PASS"

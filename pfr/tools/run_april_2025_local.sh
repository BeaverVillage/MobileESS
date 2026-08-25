#!/usr/bin/env bash
set -Eeuo pipefail

repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
python_bin="${PFR_PYTHON:-/home/jaewon/miniconda3/envs/power_v61_gpu/bin/python}"
work="/home/jaewon/mobile_ess_work"
base="$work/frozen_artifacts"
period_id="APR2025_FULL"
contract="$repo_dir/pfr/contracts/FROZEN_2025_APRIL_VALIDATION_PERIOD_V1.json"
shared="$base/PFR_${period_id}_SHARED_EXOGENOUS_V13_13"
input_root="$base/PFR_${period_id}_V13_13_DAILY_INPUTS"
canonical="$base/stage_kestrel_f30_resource_aware_job_power_policy_v2_0_32_r6c_20260806T122335/CANONICAL_F30_RACK_POWER_JOB_BASE_PREFROZEN_R6C.parquet"
run_root=""
risk_calibration=""
preflight_only=0

stop_run() {
    trap - INT TERM
    echo "INTERRUPTED: April execution stopped; partial results are preserved." >&2
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
if [[ -z "$run_root" || "$run_root" != /* ]]; then
    echo "ABORT_ISOLATION: --run-root must be an authorized absolute path." >&2
    exit 2
fi
if [[ -z "$risk_calibration" || ! -f "$risk_calibration" ]]; then
    echo "ABORT_CALIBRATION: an existing frozen --risk-calibration is required." >&2
    exit 2
fi

output="$run_root/april/B00_B09"
gate_root="$run_root/preflight/APR2025_FULL"
expected_full_commit_sha="${PFR_EXPECTED_FULL_COMMIT_SHA:-}"
expected_branch="${PFR_EXPECTED_BRANCH:-codex/feb03-predictive-native}"
if [[ ! "$expected_full_commit_sha" =~ ^[0-9a-f]{40}$ ]]; then
    echo "ABORT_APRIL_CAMPAIGN: PFR_EXPECTED_FULL_COMMIT_SHA must be frozen." >&2
    exit 64
fi

cd "$repo_dir"
"$python_bin" -m pfr.tools.jfm_isolation --run-root "$run_root" --check
"$python_bin" -c 'from pathlib import Path; import sys; from pfr.risk_calibration import load_frozen_risk_calibration; load_frozen_risk_calibration(Path(sys.argv[1]))' "$risk_calibration"
mkdir -p "$gate_root"
"$python_bin" -m pfr.tools.assert_experiment_source_freeze \
    --repo "$repo_dir" --expected-full-commit-sha "$expected_full_commit_sha" \
    --expected-branch "$expected_branch" \
    --migration-authority "$repo_dir/pfr/contracts/IDC_MIGRATION_AUTHORITY_V1.json" \
    --report "$gate_root/SOURCE_FREEZE_GATE.json"
"$python_bin" -m pfr.tools.preflight_full_month_2025 \
    --repo "$repo_dir" --period-id "$period_id" --period-contract "$contract" \
    --shared-root "$shared" --input-root "$input_root" \
    --route-catalog "$base/PFR3_FIXED_K3_PHYSICS_CURRENT/FROZEN_K3_PHYSICS_GEOMETRY.json" \
    --electrical-stress-campaign \
    --report "$gate_root/PREFLIGHT_REPORT.json"
if ((preflight_only)); then
    echo "APRIL_2025_EXECUTION_PREFLIGHT=PASS_NO_EPISODES_STARTED"
    exit 0
fi

export PFR_GUROBI_THREADS=4 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONHASHSEED=0
common=(
    --repo "$repo_dir" --period-id "$period_id" --period-contract "$contract"
    --day-workers 4 --capture-day-logs --continue-after-failure
    --electrical-stress-campaign
    --shared-root "$shared"
    --exact-package-root /mnt/c/Users/kjw39/Downloads/stage_mess_grid_v2038_exact_sweep_power_v70_final_v1_package
    --authority-package-root "$work/run_packages/K9H7_V2044R11R1_20260807T191351"
    --primary-root "$work/processed/power_v70_3ph"
    --initial-state "$input_root/pre/DAILY_CANONICAL_PRE_MANIFEST.json"
    --independent-jobs "$input_root/jobs/INDEPENDENT_JOB_COHORT.parquet"
    --canonical-jobs "$canonical"
    --power-curve "$repo_dir/pfr/contracts/H100_UTILIZATION_POWER_CURVE.json"
    --mobility-root "$shared/mobility"
    --route-catalog "$base/PFR3_FIXED_K3_PHYSICS_CURRENT/FROZEN_K3_PHYSICS_GEOMETRY.json"
    --mobility-template-bank "$shared/mobility/E4B_FULLFIT_TEMPLATE_BANK_129.parquet"
    --workload-uncertainty "$base/PFR3_V13_2_WORKLOAD_UNCERTAINTY_CURRENT/PFR3_WORKLOAD_UNCERTAINTY_V13_2.json"
    --factorized-uncertainty "$base/PFR3_V13_2_FACTORIZED_UNCERTAINTY_CURRENT/PFR3_FACTORIZED_UNCERTAINTY_V13_2.json"
    --migration-authority "$repo_dir/pfr/contracts/IDC_MIGRATION_AUTHORITY_V1.json"
    --risk-calibration "$risk_calibration"
)

campaign_rc=0
"$python_bin" -m pfr.tools.run_frozen_rep_week_daily_campaign \
    "${common[@]}" --output "$output" || campaign_rc=$?
if ((campaign_rc == 130 || campaign_rc == 143)); then exit "$campaign_rc"; fi

verify_rc=0
"$python_bin" -m pfr.tools.verify_daily_campaign_storage \
    --repo "$repo_dir" --root "$output" --start-date 2025-04-01 --days 30 \
    --electrical-stress-campaign \
    --report "$output/STORAGE_VERIFICATION.json" || verify_rc=$?
if ((campaign_rc != 0 || verify_rc != 0)); then
    echo "APRIL_2025_EXECUTION_STATUS=COMPLETE_WITH_RECORDED_FAILURES campaign_rc=$campaign_rc verify_rc=$verify_rc" >&2
    exit 1
fi
echo "APRIL_2025_EXECUTION_STATUS=PASS"

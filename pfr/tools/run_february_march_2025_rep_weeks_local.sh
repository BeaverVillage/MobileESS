#!/usr/bin/env bash
set -uo pipefail

repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
python_bin="${PFR_PYTHON:-/home/jaewon/miniconda3/envs/power_v61_gpu/bin/python}"
base="/home/jaewon/mobile_ess_work"
workers=4
gurobi_threads=4
mode="run"

while (($#)); do
    case "$1" in
        --day-workers) workers="$2"; shift 2 ;;
        --gurobi-threads) gurobi_threads="$2"; shift 2 ;;
        --prepare-only) mode="prepare"; shift ;;
        -h|--help)
            echo "Usage: $0 [--day-workers N] [--gurobi-threads N] [--prepare-only]"
            exit 0
            ;;
        *) echo "Unknown option: $1" >&2; exit 64 ;;
    esac
done
if ! [[ "$workers" =~ ^[1-7]$ ]]; then
    echo "--day-workers must be in [1,7]" >&2
    exit 64
fi
if ! [[ "$gurobi_threads" =~ ^[1-9][0-9]*$ ]]; then
    echo "--gurobi-threads must be positive" >&2
    exit 64
fi

contract="$repo_dir/pfr/contracts/FROZEN_2025_REP_WEEK_VALIDATION_PERIODS_V1.json"
authority_sha="$($python_bin -c 'import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())' "$contract")"
canonical="$base/frozen_artifacts/stage_kestrel_f30_resource_aware_job_power_policy_v2_0_32_r6c_20260806T122335/CANONICAL_F30_RACK_POWER_JOB_BASE_PREFROZEN_R6C.parquet"

prepare_period() {
    local period_id="$1" start_date="$2"
    local input_root="$base/frozen_artifacts/PFR_${period_id}_V13_13_DAILY_INPUTS"
    mkdir -p "$input_root"
    "$python_bin" -m pfr.tools.build_calendar_daily_pre \
        --start-date "$start_date" --days 7 --campaign-id "$period_id" \
        --authority-sha256 "$authority_sha" --output-root "$input_root/pre" || return
    "$python_bin" -m pfr.tools.build_calendar_job_cohort \
        --canonical "$canonical" --start-date "$start_date" --days 7 \
        --campaign-id "$period_id" \
        --output "$input_root/jobs/INDEPENDENT_JOB_COHORT.parquet" \
        --authority-output "$input_root/jobs/INDEPENDENT_JOB_COHORT_AUTHORITY.json" || return
    "$python_bin" -m pfr.tools.preflight_frozen_rep_week \
        --repo "$repo_dir" --period-id "$period_id" \
        --shared-root "$base/frozen_artifacts/B_${period_id}_SHARED_EXOGENOUS_SOURCE_CURRENT" \
        --input-root "$input_root" \
        --report "$input_root/PREFLIGHT_REPORT.json"
}

cd "$repo_dir"
prepare_status=0
if ! prepare_period "W07_2025-02-17" "2025-02-17"; then prepare_status=1; fi
if ! prepare_period "W10_2025-03-10" "2025-03-10"; then prepare_status=1; fi
if [[ "$mode" == "prepare" ]]; then
    if ((prepare_status == 0)); then
        echo "REP_WEEK_INPUT_PREPARATION_AND_PREFLIGHT_STATUS=PASS"
    else
        echo "REP_WEEK_INPUT_PREPARATION_AND_PREFLIGHT_STATUS=FAIL" >&2
    fi
    exit "$prepare_status"
fi

export PFR_GUROBI_THREADS="$gurobi_threads"
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1
export PYTHONHASHSEED=0

run_period() {
    local period_id="$1" start_date="$2"
    local input_root="$base/frozen_artifacts/PFR_${period_id}_V13_13_DAILY_INPUTS"
    local shared="$base/frozen_artifacts/B_${period_id}_SHARED_EXOGENOUS_SOURCE_CURRENT"
    local output="$base/frozen_artifacts/CODEX_PR6_V13_13_${period_id}_DAILY_20260823"
    local campaign_rc=0 verify_rc=0
    "$python_bin" -m pfr.tools.preflight_frozen_rep_week \
        --repo "$repo_dir" --period-id "$period_id" \
        --shared-root "$shared" --input-root "$input_root" \
        --report "$input_root/PREFLIGHT_REPORT.json" || return
    "$python_bin" -m pfr.tools.run_frozen_rep_week_daily_campaign \
        --repo "$repo_dir" --period-id "$period_id" \
        --day-workers "$workers" --capture-day-logs --continue-after-failure \
        --shared-root "$shared" \
        --exact-package-root /mnt/c/Users/kjw39/Downloads/stage_mess_grid_v2038_exact_sweep_power_v70_final_v1_package \
        --authority-package-root "$base/run_packages/K9H7_V2044R11R1_20260807T191351" \
        --primary-root "$base/processed/power_v70_3ph" \
        --initial-state "$input_root/pre/DAILY_CANONICAL_PRE_MANIFEST.json" \
        --independent-jobs "$input_root/jobs/INDEPENDENT_JOB_COHORT.parquet" \
        --canonical-jobs "$canonical" \
        --power-curve "$repo_dir/pfr/contracts/H100_UTILIZATION_POWER_CURVE.json" \
        --mobility-root "$shared/mobility" \
        --route-catalog "$base/frozen_artifacts/PFR3_FIXED_K3_PHYSICS_CURRENT/FROZEN_K3_PHYSICS_GEOMETRY.json" \
        --mobility-template-bank "$shared/mobility/E4B_FULLFIT_TEMPLATE_BANK_129.parquet" \
        --workload-uncertainty "$base/frozen_artifacts/PFR3_V13_2_WORKLOAD_UNCERTAINTY_CURRENT/PFR3_WORKLOAD_UNCERTAINTY_V13_2.json" \
        --factorized-uncertainty "$base/frozen_artifacts/PFR3_V13_2_FACTORIZED_UNCERTAINTY_CURRENT/PFR3_FACTORIZED_UNCERTAINTY_V13_2.json" \
        --output "$output" || campaign_rc=$?
    "$python_bin" -m pfr.tools.verify_daily_campaign_storage \
        --repo "$repo_dir" --root "$output" --start-date "$start_date" --days 7 \
        --report "$output/STORAGE_VERIFICATION.json" || verify_rc=$?
    if ((campaign_rc != 0 || verify_rc != 0)); then
        echo "PERIOD_COMPLETED_WITH_RECORDED_FAILURE period=$period_id campaign_rc=$campaign_rc verify_rc=$verify_rc" >&2
        return 1
    fi
    echo "PERIOD_STATUS=PASS period=$period_id"
}

# Each B is isolated by the matrix runtime; a failed B continues to the next B.
# Each failed day/period is preserved and execution continues chronologically.
overall_status="$prepare_status"
if ! run_period "W07_2025-02-17" "2025-02-17"; then overall_status=1; fi
if ! run_period "W10_2025-03-10" "2025-03-10"; then overall_status=1; fi
if ((overall_status == 0)); then
    echo "FEBRUARY_MARCH_REP_WEEK_EXECUTION_STATUS=PASS"
else
    echo "FEBRUARY_MARCH_REP_WEEK_EXECUTION_STATUS=COMPLETE_WITH_RECORDED_FAILURES" >&2
fi
exit "$overall_status"

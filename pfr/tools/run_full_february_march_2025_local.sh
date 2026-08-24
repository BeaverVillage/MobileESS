#!/usr/bin/env bash
set -uo pipefail

repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
python_bin="${PFR_PYTHON:-/home/jaewon/miniconda3/envs/power_v61_gpu/bin/python}"
work="/home/jaewon/mobile_ess_work"
base="$work/frozen_artifacts"
contract="$repo_dir/pfr/contracts/FROZEN_2025_FULL_MONTH_VALIDATION_PERIODS_V1.json"
canonical="$base/stage_kestrel_f30_resource_aware_job_power_policy_v2_0_32_r6c_20260806T122335/CANONICAL_F30_RACK_POWER_JOB_BASE_PREFROZEN_R6C.parquet"
prepare_only=0
run_root=""

interrupt_run() {
    trap - INT TERM
    echo "INTERRUPTED_BY_USER: stopping February-March execution; partial results are preserved." >&2
    exit 130
}
terminate_run() {
    trap - INT TERM
    echo "TERMINATED: stopping February-March execution; partial results are preserved." >&2
    exit 143
}
trap interrupt_run INT
trap terminate_run TERM

abort_if_interrupted() {
    local rc="$1"
    local phase="$2"
    if ((rc == 130 || rc == 143)); then
        echo "EXECUTION_STOPPED phase=$phase rc=$rc" >&2
        exit "$rc"
    fi
}
while (($#)); do
    case "$1" in
        --prepare-only) prepare_only=1; shift ;;
        --run-root)
            if (($# < 2)); then echo "Missing value for --run-root" >&2; exit 64; fi
            run_root="$2"
            shift 2
            ;;
        *) echo "Usage: $0 --run-root ABSOLUTE_PATH [--prepare-only]" >&2; exit 64 ;;
    esac
done
if [[ -z "$run_root" || "$run_root" != /* ]]; then
    echo "ABORT_ISOLATION: --run-root must be an authorized absolute path." >&2
    exit 2
fi

authority_sha="$($python_bin -c 'import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())' "$contract")"

prepare_inputs() {
    local period_id="$1" start_date="$2" days="$3"
    local input_root="$base/PFR_${period_id}_V13_13_DAILY_INPUTS"
    mkdir -p "$input_root"
    "$python_bin" -m pfr.tools.build_calendar_daily_pre \
        --start-date "$start_date" --days "$days" --campaign-id "$period_id" \
        --authority-sha256 "$authority_sha" --output-root "$input_root/pre" || return
    "$python_bin" -m pfr.tools.build_calendar_job_cohort \
        --canonical "$canonical" --start-date "$start_date" --days "$days" \
        --campaign-id "$period_id" \
        --output "$input_root/jobs/INDEPENDENT_JOB_COHORT.parquet" \
        --authority-output "$input_root/jobs/INDEPENDENT_JOB_COHORT_AUTHORITY.json"
}

cd "$repo_dir"
overall=0
expected_full_commit_sha="${PFR_EXPECTED_FULL_COMMIT_SHA:-}"
expected_branch="${PFR_EXPECTED_BRANCH:-codex/feb03-predictive-native}"
if [[ ! "$expected_full_commit_sha" =~ ^[0-9a-f]{40}$ ]]; then
    echo "ABORT_ISOLATION: set PFR_EXPECTED_FULL_COMMIT_SHA to the frozen 40-character commit." >&2
    exit 2
fi
"$python_bin" -m pfr.tools.jfm_isolation \
    --run-root "$run_root" --initialize \
    --expected-full-commit-sha "$expected_full_commit_sha" \
    --expected-branch "$expected_branch" || exit 2
if ! prepare_inputs FEB2025_FULL 2025-02-01 28; then overall=1; fi
if ! prepare_inputs MAR2025_FULL 2025-03-01 31; then overall=1; fi

if ((prepare_only)); then
    if ! bash "$repo_dir/pfr/tools/prepare_full_february_march_2025_sources.sh" --plan-only; then overall=1; fi
    for row in "FEB2025_FULL 2025-02-01 28" "MAR2025_FULL 2025-03-01 31"; do
        read -r period_id start_date days <<<"$row"
        shared="$base/PFR_${period_id}_SHARED_EXOGENOUS_V13_13"
        input_root="$base/PFR_${period_id}_V13_13_DAILY_INPUTS"
        gate_root="$run_root/preflight/$period_id"
        mkdir -p "$gate_root"
        "$python_bin" -m pfr.tools.preflight_full_month_2025 \
            --repo "$repo_dir" --period-id "$period_id" \
            --shared-root "$shared" --input-root "$input_root" \
            --route-catalog "$base/PFR3_FIXED_K3_PHYSICS_CURRENT/FROZEN_K3_PHYSICS_GEOMETRY.json" \
            --report "$gate_root/PREFLIGHT_REPORT.json" \
            --allow-unmaterialized || overall=1
    done
    if ((overall == 0)); then
        echo "FULL_FEBRUARY_MARCH_PREPARATION_STATUS=READY_NO_EPISODES_STARTED"
    else
        echo "FULL_FEBRUARY_MARCH_PREPARATION_STATUS=FAIL_NO_EPISODES_STARTED" >&2
    fi
    exit "$overall"
fi

source_rc=0
bash "$repo_dir/pfr/tools/prepare_full_february_march_2025_sources.sh" || source_rc=$?
if ((source_rc != 0)); then overall=1; fi

export PFR_GUROBI_THREADS=4
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1
export PYTHONHASHSEED=0

run_period() {
    local period_id="$1" start_date="$2" days="$3"
    local shared="$base/PFR_${period_id}_SHARED_EXOGENOUS_V13_13"
    local input_root="$base/PFR_${period_id}_V13_13_DAILY_INPUTS"
    local month_name=""
    case "$period_id" in
        FEB2025_FULL) month_name="february" ;;
        MAR2025_FULL) month_name="march" ;;
        *) echo "Unsupported isolated period: $period_id" >&2; return 1 ;;
    esac
    local output="$run_root/$month_name/B0_B7"
    local b8_output="$run_root/$month_name/B8"
    local campaign_rc=0 verify_rc=0 b8_campaign_rc=0 b8_verify_rc=0
    local gate_root="$run_root/preflight/$period_id"
    mkdir -p "$gate_root"
    "$python_bin" -m pfr.tools.assert_experiment_source_freeze \
        --repo "$repo_dir" \
        --expected-full-commit-sha "$expected_full_commit_sha" \
        --expected-branch "$expected_branch" \
        --migration-authority "$repo_dir/pfr/contracts/IDC_MIGRATION_AUTHORITY_V1.json" \
        --report "$gate_root/SOURCE_FREEZE_GATE.json" || return 1
    "$python_bin" -m pfr.tools.preflight_full_month_2025 \
        --repo "$repo_dir" --period-id "$period_id" \
        --shared-root "$shared" --input-root "$input_root" \
        --route-catalog "$base/PFR3_FIXED_K3_PHYSICS_CURRENT/FROZEN_K3_PHYSICS_GEOMETRY.json" \
        --report "$gate_root/PREFLIGHT_REPORT.json" || return 1
    "$python_bin" -m pfr.tools.run_frozen_rep_week_daily_campaign \
        --repo "$repo_dir" --period-id "$period_id" --period-contract "$contract" \
        --day-workers 4 --capture-day-logs --continue-after-failure \
        --shared-root "$shared" \
        --exact-package-root /mnt/c/Users/kjw39/Downloads/stage_mess_grid_v2038_exact_sweep_power_v70_final_v1_package \
        --authority-package-root "$work/run_packages/K9H7_V2044R11R1_20260807T191351" \
        --primary-root "$work/processed/power_v70_3ph" \
        --initial-state "$input_root/pre/DAILY_CANONICAL_PRE_MANIFEST.json" \
        --independent-jobs "$input_root/jobs/INDEPENDENT_JOB_COHORT.parquet" \
        --canonical-jobs "$canonical" \
        --power-curve "$repo_dir/pfr/contracts/H100_UTILIZATION_POWER_CURVE.json" \
        --mobility-root "$shared/mobility" \
        --route-catalog "$base/PFR3_FIXED_K3_PHYSICS_CURRENT/FROZEN_K3_PHYSICS_GEOMETRY.json" \
        --mobility-template-bank "$shared/mobility/E4B_FULLFIT_TEMPLATE_BANK_129.parquet" \
        --workload-uncertainty "$base/PFR3_V13_2_WORKLOAD_UNCERTAINTY_CURRENT/PFR3_WORKLOAD_UNCERTAINTY_V13_2.json" \
        --factorized-uncertainty "$base/PFR3_V13_2_FACTORIZED_UNCERTAINTY_CURRENT/PFR3_FACTORIZED_UNCERTAINTY_V13_2.json" \
        --migration-authority "$repo_dir/pfr/contracts/IDC_MIGRATION_AUTHORITY_V1.json" \
        --output "$output" || campaign_rc=$?
    abort_if_interrupted "$campaign_rc" "${period_id}_b0_b7"
    "$python_bin" -m pfr.tools.run_frozen_rep_week_daily_campaign \
        --repo "$repo_dir" --period-id "$period_id" --period-contract "$contract" \
        --day-workers 4 --capture-day-logs --continue-after-failure \
        --supplementary-b8-periodic-5min \
        --shared-root "$shared" \
        --exact-package-root /mnt/c/Users/kjw39/Downloads/stage_mess_grid_v2038_exact_sweep_power_v70_final_v1_package \
        --authority-package-root "$work/run_packages/K9H7_V2044R11R1_20260807T191351" \
        --primary-root "$work/processed/power_v70_3ph" \
        --initial-state "$input_root/pre/DAILY_CANONICAL_PRE_MANIFEST.json" \
        --independent-jobs "$input_root/jobs/INDEPENDENT_JOB_COHORT.parquet" \
        --canonical-jobs "$canonical" \
        --power-curve "$repo_dir/pfr/contracts/H100_UTILIZATION_POWER_CURVE.json" \
        --mobility-root "$shared/mobility" \
        --route-catalog "$base/PFR3_FIXED_K3_PHYSICS_CURRENT/FROZEN_K3_PHYSICS_GEOMETRY.json" \
        --mobility-template-bank "$shared/mobility/E4B_FULLFIT_TEMPLATE_BANK_129.parquet" \
        --workload-uncertainty "$base/PFR3_V13_2_WORKLOAD_UNCERTAINTY_CURRENT/PFR3_WORKLOAD_UNCERTAINTY_V13_2.json" \
        --factorized-uncertainty "$base/PFR3_V13_2_FACTORIZED_UNCERTAINTY_CURRENT/PFR3_FACTORIZED_UNCERTAINTY_V13_2.json" \
        --migration-authority "$repo_dir/pfr/contracts/IDC_MIGRATION_AUTHORITY_V1.json" \
        --output "$b8_output" || b8_campaign_rc=$?
    abort_if_interrupted "$b8_campaign_rc" "${period_id}_b8"
    "$python_bin" -m pfr.tools.verify_daily_campaign_storage \
        --repo "$repo_dir" --root "$output" --start-date "$start_date" --days "$days" \
        --report "$output/STORAGE_VERIFICATION.json" || verify_rc=$?
    "$python_bin" -m pfr.tools.verify_daily_campaign_storage \
        --repo "$repo_dir" --root "$b8_output" --start-date "$start_date" --days "$days" \
        --supplementary-b8-periodic-5min \
        --report "$b8_output/STORAGE_VERIFICATION.json" || b8_verify_rc=$?
    if ((campaign_rc != 0 || verify_rc != 0 || b8_campaign_rc != 0 || b8_verify_rc != 0)); then
        echo "PERIOD_COMPLETED_WITH_RECORDED_FAILURE period=$period_id campaign_rc=$campaign_rc verify_rc=$verify_rc b8_campaign_rc=$b8_campaign_rc b8_verify_rc=$b8_verify_rc" >&2
        return 1
    fi
    echo "PERIOD_STATUS=PASS period=$period_id"
}

# Never short-circuit on a scientific B/day/period failure.
if ! run_period FEB2025_FULL 2025-02-01 28; then overall=1; fi
if ! run_period MAR2025_FULL 2025-03-01 31; then overall=1; fi
if ((overall == 0)); then
    echo "FULL_FEBRUARY_MARCH_EXECUTION_STATUS=PASS"
else
    echo "FULL_FEBRUARY_MARCH_EXECUTION_STATUS=COMPLETE_WITH_RECORDED_FAILURES" >&2
fi
exit "$overall"

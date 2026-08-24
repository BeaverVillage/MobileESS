#!/usr/bin/env bash
set -uo pipefail

repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
python_bin="${PFR_PYTHON:-/home/jaewon/miniconda3/envs/power_v61_gpu/bin/python}"
work="/home/jaewon/mobile_ess_work"
base="$work/frozen_artifacts"
period_id="APR2025_FULL"
contract="$repo_dir/pfr/contracts/FROZEN_2025_APRIL_VALIDATION_PERIOD_V1.json"
shared="$base/PFR_${period_id}_SHARED_EXOGENOUS_V13_13"
input_root="$base/PFR_${period_id}_V13_13_DAILY_INPUTS"
canonical="$base/stage_kestrel_f30_resource_aware_job_power_policy_v2_0_32_r6c_20260806T122335/CANONICAL_F30_RACK_POWER_JOB_BASE_PREFROZEN_R6C.parquet"
output="${PFR_APRIL_OUTPUT_ROOT:-$base/CODEX_PR6_V13_13_APR2025_FULL_DAILY_20260824}"
b8_output="${PFR_APRIL_B8_OUTPUT_ROOT:-$base/CODEX_PR6_V13_13_APR2025_FULL_B8_PERIODIC5_20260824}"
expected_full_commit_sha="${PFR_EXPECTED_FULL_COMMIT_SHA:-}"
expected_branch="${PFR_EXPECTED_BRANCH:-codex/pr6-b8-periodic5}"

if (($#)); then echo "Usage: $0" >&2; exit 64; fi
if [[ ! "$expected_full_commit_sha" =~ ^[0-9a-f]{40}$ ]]; then
    echo "ABORT_APRIL_CAMPAIGN: PFR_EXPECTED_FULL_COMMIT_SHA must be the frozen 40-character commit." >&2
    exit 64
fi

cd "$repo_dir"
"$python_bin" -m pfr.tools.assert_experiment_source_freeze \
    --repo "$repo_dir" \
    --expected-full-commit-sha "$expected_full_commit_sha" \
    --expected-branch "$expected_branch" \
    --migration-authority "$repo_dir/pfr/contracts/IDC_MIGRATION_AUTHORITY_V1.json" \
    --report "$input_root/SOURCE_FREEZE_GATE.json" || exit 1
"$python_bin" -m pfr.tools.preflight_full_month_2025 \
    --repo "$repo_dir" --period-id "$period_id" \
    --period-contract "$contract" --shared-root "$shared" \
    --input-root "$input_root" \
    --report "$input_root/PREFLIGHT_REPORT.json" || exit 1

export PFR_GUROBI_THREADS=4
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1
export PYTHONHASHSEED=0

campaign_rc=0
b8_campaign_rc=0
verify_rc=0
b8_verify_rc=0
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

"$python_bin" -m pfr.tools.verify_daily_campaign_storage \
    --repo "$repo_dir" --root "$output" --start-date 2025-04-01 --days 30 \
    --report "$output/STORAGE_VERIFICATION.json" || verify_rc=$?
"$python_bin" -m pfr.tools.verify_daily_campaign_storage \
    --repo "$repo_dir" --root "$b8_output" --start-date 2025-04-01 --days 30 \
    --supplementary-b8-periodic-5min \
    --report "$b8_output/STORAGE_VERIFICATION.json" || b8_verify_rc=$?

if ((campaign_rc != 0 || b8_campaign_rc != 0 || verify_rc != 0 || b8_verify_rc != 0)); then
    echo "APRIL_2025_EXECUTION_STATUS=COMPLETE_WITH_RECORDED_FAILURES campaign_rc=$campaign_rc b8_campaign_rc=$b8_campaign_rc verify_rc=$verify_rc b8_verify_rc=$b8_verify_rc" >&2
    exit 1
fi
echo "APRIL_2025_EXECUTION_STATUS=PASS"

#!/usr/bin/env bash
set -Eeuo pipefail

repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
python_bin="${PFR_PYTHON:-/home/jaewon/miniconda3/envs/power_v61_gpu/bin/python}"
output_root="${PFR_MIGRATION_SENSITIVITY_OUTPUT:-/home/jaewon/mobile_ess_work/frozen_artifacts/JAN2025_IDC_MIGRATION_RHO_SENSITIVITY_V1}"
day_workers="${PFR_DAY_WORKERS:-1}"
gurobi_threads="${PFR_GUROBI_THREADS:-4}"

expected_full_commit_sha="${PFR_EXPECTED_FULL_COMMIT_SHA:-}"
expected_branch="${PFR_EXPECTED_BRANCH:-codex/pr6-b8-periodic5}"
if [[ ! "$expected_full_commit_sha" =~ ^[0-9a-f]{40}$ ]]; then
    echo "ABORT_MAIN_CAMPAIGN: set PFR_EXPECTED_FULL_COMMIT_SHA to the frozen 40-character commit." >&2
    exit 2
fi

common_arguments=(
    --shared-root /home/jaewon/mobile_ess_work/frozen_artifacts/PFR_JAN2025_SHARED_EXOGENOUS_CURRENT
    --exact-package-root /mnt/c/Users/kjw39/Downloads/stage_mess_grid_v2038_exact_sweep_power_v70_final_v1_package
    --authority-package-root /home/jaewon/mobile_ess_work/run_packages/K9H7_V2044R11R1_20260807T191351
    --primary-root /home/jaewon/mobile_ess_work/processed/power_v70_3ph
    --initial-state /home/jaewon/mobile_ess_work/frozen_artifacts/PFR_JAN2025_DAILY_PRE_CURRENT/JAN2025_DAILY_CANONICAL_PRE_MANIFEST.json
    --independent-jobs /home/jaewon/mobile_ess_work/frozen_artifacts/PFR_JAN2025_JOB_COHORT_FIXED_AEST_CURRENT/JAN2025_INDEPENDENT_JOB_COHORT.parquet
    --canonical-jobs /home/jaewon/mobile_ess_work/frozen_artifacts/stage_kestrel_f30_resource_aware_job_power_policy_v2_0_32_r6c_20260806T122335/CANONICAL_F30_RACK_POWER_JOB_BASE_PREFROZEN_R6C.parquet
    --power-curve "$repo_dir/pfr/contracts/H100_UTILIZATION_POWER_CURVE.json"
    --mobility-root /home/jaewon/mobile_ess_work/frozen_artifacts/PFR_JAN2025_SOURCE_CHUNK_0000/mobility
    --mobility-root /home/jaewon/mobile_ess_work/frozen_artifacts/PFR_JAN2025_SOURCE_CHUNK_2304/mobility
    --mobility-root /home/jaewon/mobile_ess_work/frozen_artifacts/PFR_JAN2025_SOURCE_CHUNK_4608/mobility
    --mobility-root /home/jaewon/mobile_ess_work/frozen_artifacts/PFR_JAN2025_SOURCE_CHUNK_6912/mobility
    --route-catalog /home/jaewon/mobile_ess_work/frozen_artifacts/PFR3_FIXED_K3_PHYSICS_CURRENT/FROZEN_K3_PHYSICS_GEOMETRY.json
    --mobility-template-bank /home/jaewon/mobile_ess_work/frozen_artifacts/PFR_JAN2025_SOURCE_CHUNK_0000/mobility/E4B_FULLFIT_TEMPLATE_BANK_129.parquet
    --workload-uncertainty /home/jaewon/mobile_ess_work/frozen_artifacts/PFR3_V13_2_WORKLOAD_UNCERTAINTY_CURRENT/PFR3_WORKLOAD_UNCERTAINTY_V13_2.json
    --factorized-uncertainty /home/jaewon/mobile_ess_work/frozen_artifacts/PFR3_V13_2_FACTORIZED_UNCERTAINTY_CURRENT/PFR3_FACTORIZED_UNCERTAINTY_V13_2.json
    --migration-authority "$repo_dir/pfr/contracts/IDC_MIGRATION_AUTHORITY_V1.json"
)

export PFR_GUROBI_THREADS="$gurobi_threads"
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1 PYTHONHASHSEED=0

cd "$repo_dir"
"$python_bin" -m pfr.tools.assert_experiment_source_freeze \
    --repo "$repo_dir" \
    --expected-full-commit-sha "$expected_full_commit_sha" \
    --expected-branch "$expected_branch" \
    --migration-authority "$repo_dir/pfr/contracts/IDC_MIGRATION_AUTHORITY_V1.json" \
    --report "$output_root/SOURCE_FREEZE_GATE.json"

"$python_bin" -m pfr.tools.preflight_january_2025 \
    --repo "$repo_dir" \
    "${common_arguments[@]}" \
    --report "$output_root/PREFLIGHT_REPORT.json"

for factor in 0.25 0.5 1.0; do
    factor_key="rho$(printf '%03d' "$(awk -v value="$factor" 'BEGIN {print value * 100}')")"
    for method in B3 B4 B5 B6 B7 B8; do
        "$python_bin" -m pfr.tools.run_pfr_daily_campaign \
            --repo "$repo_dir" \
            --start-day 1 --end-day 31 \
            --day-workers "$day_workers" --capture-day-logs \
            --no-reuse-passed-days \
            --diagnostic-method "$method" \
            --checkpoint-payload-occupancy-factor "$factor" \
            "${common_arguments[@]}" \
            --output "$output_root/$factor_key/$method"
    done
done

"$python_bin" -m pfr.tools.analyze_january_migration_sensitivity \
    --root "$output_root" \
    --output "$output_root/JAN2025_IDC_MIGRATION_RHO_SENSITIVITY.json"

#!/usr/bin/env bash
set -Eeuo pipefail

repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
python_bin="${PFR_PYTHON:-/home/jaewon/miniconda3/envs/power_v61_gpu/bin/python}"
output_root="/home/jaewon/mobile_ess_work/frozen_artifacts/CODEX_PR6_V13_13_JAN2025_B8_PERIODIC5_SUPPLEMENTARY_20260823"
start_day=1
end_day=31
day_workers=1
gurobi_threads=4

usage() {
    printf '%s\n' \
        "Usage: bash pfr/tools/run_january_2025_b8_periodic5_local.sh [options]" \
        "  --start-day N" \
        "  --end-day N" \
        "  --day-workers N" \
        "  --gurobi-threads N" \
        "  --output-root PATH"
}

while (($#)); do
    case "$1" in
        --start-day) start_day="$2"; shift 2 ;;
        --end-day) end_day="$2"; shift 2 ;;
        --day-workers) day_workers="$2"; shift 2 ;;
        --gurobi-threads) gurobi_threads="$2"; shift 2 ;;
        --output-root) output_root="$2"; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) echo "Unknown option: $1" >&2; usage >&2; exit 64 ;;
    esac
done

if ! [[ "$start_day" =~ ^[0-9]+$ && "$end_day" =~ ^[0-9]+$ && \
        "$day_workers" =~ ^[0-9]+$ && "$gurobi_threads" =~ ^[0-9]+$ ]]; then
    echo "Day and worker/thread arguments must be integers." >&2
    exit 64
fi
if ((start_day < 1 || end_day > 31 || start_day > end_day)); then
    echo "Day range must satisfy 1 <= start-day <= end-day <= 31." >&2
    exit 64
fi
if ((day_workers < 1 || gurobi_threads < 1)); then
    echo "day-workers and gurobi-threads must be positive." >&2
    exit 64
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
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1
export PYTHONHASHSEED=0

cd "$repo_dir"
"$python_bin" -m pfr.tools.preflight_january_2025 \
    --repo "$repo_dir" \
    "${common_arguments[@]}" \
    --report "$output_root/PREFLIGHT_REPORT.json"

"$python_bin" -m pfr.tools.run_pfr_daily_campaign \
    --repo "$repo_dir" \
    --start-day "$start_day" \
    --end-day "$end_day" \
    --day-workers "$day_workers" \
    --capture-day-logs \
    --supplementary-b8-periodic-5min \
    "${common_arguments[@]}" \
    --output "$output_root"

"$python_bin" -m pfr.tools.verify_daily_campaign_storage \
    --repo "$repo_dir" \
    --root "$output_root" \
    --start-date "2025-01-$(printf '%02d' "$start_day")" \
    --days "$((end_day - start_day + 1))" \
    --supplementary-b8-periodic-5min

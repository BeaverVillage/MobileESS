#!/usr/bin/env bash
set -Eeuo pipefail

repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
python_bin="${PFR_PYTHON:-/home/jaewon/miniconda3/envs/power_v61_gpu/bin/python}"
day=1
method="B0"
count=1
output_root=""
gurobi_threads=1

usage() {
    cat <<'EOF'
Usage: bash pfr/tools/run_native_grid_control_diagnostic.sh [options]

Single-method diagnostic under the frozen January post-hoc authority.
The Python process stays in the foreground. Ctrl+C terminates the whole run.

  --day N               January day whose canonical cold start is used (1-31).
  --method B0..B7       One diagnostic method only (default: B0).
  --count N             Number of 5-minute issues from the day start (1-288).
  --gurobi-threads N    Gurobi threads (default: 1).
  --output-root PATH    Diagnostic output root.
  -h, --help            Show this help.
EOF
}

require_value() {
    if (($# < 2)); then
        echo "Missing value for $1" >&2
        exit 64
    fi
}

while (($#)); do
    case "$1" in
        --day|--method|--count|--gurobi-threads|--output-root)
            require_value "$@"
            option="$1"
            value="$2"
            shift 2
            case "$option" in
                --day) day="$value" ;;
                --method) method="$value" ;;
                --count) count="$value" ;;
                --gurobi-threads) gurobi_threads="$value" ;;
                --output-root) output_root="$value" ;;
            esac
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            usage >&2
            exit 64
            ;;
    esac
done

if ! [[ "$day" =~ ^[0-9]+$ && "$count" =~ ^[0-9]+$ && \
        "$gurobi_threads" =~ ^[0-9]+$ ]]; then
    echo "day, count, and gurobi-threads must be integers." >&2
    exit 64
fi
if ((day < 1 || day > 31 || count < 1 || count > 288 || gurobi_threads < 1)); then
    echo "Require day in [1,31], count in [1,288], and positive threads." >&2
    exit 64
fi
if [[ ! "$method" =~ ^B[0-7]$ ]]; then
    echo "method must be one of B0..B7." >&2
    exit 64
fi
if [[ ! -x "$python_bin" ]]; then
    echo "Python runtime is not executable: $python_bin" >&2
    exit 66
fi

start_issue=$(((day - 1) * 288))
if [[ -z "$output_root" ]]; then
    output_root="/home/jaewon/mobile_ess_work/frozen_artifacts/PFR13_NATIVE_GRID_ENGINEERING_DIAGNOSTIC_DAY$(printf '%02d' "$day")_${method}"
fi

export PFR_GUROBI_THREADS="$gurobi_threads"
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1
export PYTHONHASHSEED=0

echo "JANUARY POST-HOC DIAGNOSTIC: not an independent holdout evaluation."
echo "Foreground run: day=$day method=$method issues=$count output=$output_root"
echo "Ctrl+C terminates this Python process; no background worker is created."

cd "$repo_dir"
exec "$python_bin" -m pfr.tools.run_pfr_matrix \
    --repo "$repo_dir" \
    --candidate-id "NATIVE_GRID_DIAGNOSTIC_DAY$(printf '%02d' "$day")_${method}" \
    --diagnostic-method "$method" \
    --start-issue "$start_issue" \
    --count "$count" \
    --shared-root /home/jaewon/mobile_ess_work/frozen_artifacts/PFR_JAN2025_SHARED_EXOGENOUS_CURRENT \
    --exact-package-root /mnt/c/Users/kjw39/Downloads/stage_mess_grid_v2038_exact_sweep_power_v70_final_v1_package \
    --authority-package-root /home/jaewon/mobile_ess_work/run_packages/K9H7_V2044R11R1_20260807T191351 \
    --primary-root /home/jaewon/mobile_ess_work/processed/power_v70_3ph \
    --initial-state /home/jaewon/mobile_ess_work/frozen_artifacts/PFR_JAN2025_DAILY_PRE_CURRENT/JAN2025_DAILY_CANONICAL_PRE_MANIFEST.json \
    --independent-jobs /home/jaewon/mobile_ess_work/frozen_artifacts/PFR_JAN2025_JOB_COHORT_FIXED_AEST_CURRENT/JAN2025_INDEPENDENT_JOB_COHORT.parquet \
    --canonical-jobs /home/jaewon/mobile_ess_work/frozen_artifacts/stage_kestrel_f30_resource_aware_job_power_policy_v2_0_32_r6c_20260806T122335/CANONICAL_F30_RACK_POWER_JOB_BASE_PREFROZEN_R6C.parquet \
    --power-curve "$repo_dir/pfr/contracts/H100_UTILIZATION_POWER_CURVE.json" \
    --mobility-root /home/jaewon/mobile_ess_work/frozen_artifacts/PFR_JAN2025_SOURCE_CHUNK_0000/mobility \
    --mobility-root /home/jaewon/mobile_ess_work/frozen_artifacts/PFR_JAN2025_SOURCE_CHUNK_2304/mobility \
    --mobility-root /home/jaewon/mobile_ess_work/frozen_artifacts/PFR_JAN2025_SOURCE_CHUNK_4608/mobility \
    --mobility-root /home/jaewon/mobile_ess_work/frozen_artifacts/PFR_JAN2025_SOURCE_CHUNK_6912/mobility \
    --route-catalog /home/jaewon/mobile_ess_work/frozen_artifacts/PFR3_FIXED_K3_PHYSICS_CURRENT/FROZEN_K3_PHYSICS_GEOMETRY.json \
    --mobility-template-bank /home/jaewon/mobile_ess_work/frozen_artifacts/PFR_JAN2025_SOURCE_CHUNK_0000/mobility/E4B_FULLFIT_TEMPLATE_BANK_129.parquet \
    --workload-uncertainty /home/jaewon/mobile_ess_work/frozen_artifacts/PFR3_V13_2_WORKLOAD_UNCERTAINTY_CURRENT/PFR3_WORKLOAD_UNCERTAINTY_V13_2.json \
    --factorized-uncertainty /home/jaewon/mobile_ess_work/frozen_artifacts/PFR3_V13_2_FACTORIZED_UNCERTAINTY_CURRENT/PFR3_FACTORIZED_UNCERTAINTY_V13_2.json \
    --output "$output_root"

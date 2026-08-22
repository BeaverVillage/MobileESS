#!/usr/bin/env bash
set -Eeuo pipefail

repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
python_bin="${PFR_PYTHON:-/home/jaewon/miniconda3/envs/power_v61_gpu/bin/python}"
output_root="/home/jaewon/mobile_ess_work/frozen_artifacts/JAN2025_POST_HOC_V13_3_FINAL_VALIDATION_20260822"
start_day=1
end_day=31
day_workers=4
gurobi_threads=4
watch_seconds=10
mode="run"
skip_preflight=0

usage() {
    cat <<'EOF'
Usage: bash pfr/tools/run_january_2025_local.sh [options]

Modes:
  --preflight-only       Validate the frozen design and inputs; start no episode.
  --monitor-only         Show campaign progress; start no episode.

Run options:
  --start-day N          First January day (default: 1).
  --end-day N            Last January day (default: 31).
  --day-workers N        Concurrent daily processes (default: 4).
  --gurobi-threads N     Gurobi threads per daily process (default: 4).
  --output-root PATH     Campaign output root.
  --skip-preflight       Skip the automatic preflight (not recommended).
  --watch-seconds N      Monitor refresh interval; 0 prints once (default: 10).
  -h, --help             Show this help.
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
        --preflight-only)
            mode="preflight"
            shift
            ;;
        --monitor-only)
            mode="monitor"
            shift
            ;;
        --skip-preflight)
            skip_preflight=1
            shift
            ;;
        --start-day|--end-day|--day-workers|--gurobi-threads|--output-root|--watch-seconds)
            require_value "$@"
            option="$1"
            value="$2"
            shift 2
            case "$option" in
                --start-day) start_day="$value" ;;
                --end-day) end_day="$value" ;;
                --day-workers) day_workers="$value" ;;
                --gurobi-threads) gurobi_threads="$value" ;;
                --output-root) output_root="$value" ;;
                --watch-seconds) watch_seconds="$value" ;;
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

if [[ ! -x "$python_bin" ]]; then
    echo "Python runtime is not executable: $python_bin" >&2
    exit 66
fi
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

if [[ "$mode" == "monitor" ]]; then
    cd "$repo_dir"
    exec "$python_bin" -m pfr.tools.show_january_progress \
        --root "$output_root" \
        --start-day "$start_day" \
        --end-day "$end_day" \
        --watch-seconds "$watch_seconds"
fi

available_cpu="$(nproc)"
logical_cpu="$(nproc --all 2>/dev/null || printf '%s' "$available_cpu")"
if ((day_workers * gurobi_threads > available_cpu)); then
    echo "WARNING: requested solver concurrency exceeds CPUs currently visible to "\
"this shell: $day_workers x $gurobi_threads > $available_cpu." >&2
    echo "The run will continue; reduce --day-workers or --gurobi-threads if the "\
"machine becomes unresponsive." >&2
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
)

export PFR_GUROBI_THREADS="$gurobi_threads"
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1
export PYTHONHASHSEED=0

cd "$repo_dir"
echo "Classification: JANUARY-2025 POST-HOC FINAL VALIDATION (not an independent holdout)."
if ((skip_preflight == 0)); then
    echo "Running fail-closed January authority/source/design preflight."
    "$python_bin" -m pfr.tools.preflight_january_2025 \
        --repo "$repo_dir" \
        "${common_arguments[@]}" \
        --report "$output_root/PREFLIGHT_REPORT.json"
fi

if [[ "$mode" == "preflight" ]]; then
    echo "Preflight complete. No January episode was started."
    echo "Report: $output_root/PREFLIGHT_REPORT.json"
    exit 0
fi

echo "Starting days $start_day-$end_day with $day_workers processes x "\
"$gurobi_threads Gurobi threads (visible CPUs=$available_cpu, system CPUs=$logical_cpu)."
echo "Monitor in another shell:"
printf 'bash %q --monitor-only --output-root %q\n' \
    "$repo_dir/pfr/tools/run_january_2025_local.sh" "$output_root"

exec "$python_bin" -m pfr.tools.run_pfr_daily_campaign \
    --repo "$repo_dir" \
    --start-day "$start_day" \
    --end-day "$end_day" \
    --day-workers "$day_workers" \
    --capture-day-logs \
    "${common_arguments[@]}" \
    --output "$output_root"

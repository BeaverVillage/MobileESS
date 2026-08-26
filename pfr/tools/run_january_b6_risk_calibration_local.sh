#!/usr/bin/env bash
set -Eeuo pipefail

repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
python_bin="${PFR_PYTHON:-/home/jaewon/miniconda3/envs/power_v61_gpu/bin/python}"
run_root=""
preflight_only=0
day_workers="${PFR_DAY_WORKERS:-6}"
gurobi_threads="${PFR_GUROBI_THREADS:-2}"
cpu_affinity="${PFR_CPU_AFFINITY:-disjoint}"
reuse_verified_pass_fingerprints=()

stop_run() {
    trap - INT TERM
    echo "INTERRUPTED: January B07 electrical-stress calibration stopped; partial results are preserved." >&2
    exit 130
}
trap stop_run INT TERM

while (($#)); do
    case "$1" in
        --run-root)
            (($# >= 2)) || { echo "Missing --run-root value" >&2; exit 64; }
            run_root="$2"; shift 2 ;;
        --day-workers) day_workers="$2"; shift 2 ;;
        --gurobi-threads) gurobi_threads="$2"; shift 2 ;;
        --cpu-affinity) cpu_affinity="$2"; shift 2 ;;
        --reuse-verified-pass-fingerprint)
            (($# >= 2)) || { echo "Missing --reuse-verified-pass-fingerprint value" >&2; exit 64; }
            reuse_verified_pass_fingerprints+=("$2"); shift 2 ;;
        --preflight-only) preflight_only=1; shift ;;
        *) echo "Usage: $0 --run-root ABSOLUTE_PATH [--day-workers N] [--gurobi-threads N] [--cpu-affinity none|disjoint] [--reuse-verified-pass-fingerprint SHA256] [--preflight-only]" >&2; exit 64 ;;
    esac
done
if [[ -z "$run_root" || "$run_root" != /* ]]; then
    echo "--run-root must be an absolute isolated path." >&2
    exit 2
fi
if ! [[ "$day_workers" =~ ^[1-9][0-9]*$ && "$gurobi_threads" =~ ^[1-9][0-9]*$ ]]; then
    echo "worker and Gurobi thread counts must be positive integers." >&2
    exit 64
fi
if [[ "$cpu_affinity" != none && "$cpu_affinity" != disjoint ]]; then
    echo "--cpu-affinity must be none or disjoint." >&2
    exit 64
fi
for fingerprint in "${reuse_verified_pass_fingerprints[@]}"; do
    if [[ ! "$fingerprint" =~ ^[0-9a-f]{64}$ ]]; then
        echo "--reuse-verified-pass-fingerprint must be a lowercase SHA-256." >&2
        exit 64
    fi
done

mkdir -p "$run_root"
calibration_lock="$run_root/.january_b07_calibration.lock"
exec 9>"$calibration_lock"
if ! flock -n 9; then
    echo "FAIL_CLOSED_DUPLICATE_CALIBRATION: another January B07 calibration already owns $run_root" >&2
    exit 73
fi

calibration_root="$run_root/january_b07_electrical_stress_raw"
artifact="$run_root/calibration/ELECTRICAL_STRESS_EVENT_RISK_CALIBRATION_JAN2025.json"
common=(
    --start-day 1 --end-day 31
    --day-workers "$day_workers" --gurobi-threads "$gurobi_threads"
    --cpu-affinity "$cpu_affinity"
    --diagnostic-method B07 --output-root "$calibration_root" --fail-fast
)
if ((preflight_only)); then common+=(--preflight-only); fi
for fingerprint in "${reuse_verified_pass_fingerprints[@]}"; do
    common+=(--reuse-verified-pass-fingerprint "$fingerprint")
done

cd "$repo_dir"
bash "$repo_dir/pfr/tools/run_january_2025_local.sh" "${common[@]}"
if ((preflight_only)); then
    echo "JANUARY_B07_CALIBRATION_PREFLIGHT=PASS_NO_EPISODES_STARTED"
    exit 0
fi

"$python_bin" -m pfr.tools.verify_daily_campaign_storage \
    --repo "$repo_dir" --root "$calibration_root" \
    --start-date 2025-01-01 --days 31 --diagnostic-method B07 \
    --report "$calibration_root/STORAGE_VERIFICATION.json"
"$python_bin" -m pfr.tools.build_january_b6_risk_calibration \
    --source-root "$calibration_root" --source-method B07 --output "$artifact"
"$python_bin" -c 'from pathlib import Path; import json,sys; from pfr.risk_calibration import load_frozen_risk_calibration; x=load_frozen_risk_calibration(Path(sys.argv[1])); print("RISK_CALIBRATION_FROZEN", x.authority_id, json.dumps(dict(x.normalized_family_quantiles), sort_keys=True), x.artifact_sha256)' "$artifact"
echo "JANUARY_B07_ELECTRICAL_STRESS_CALIBRATION_STATUS=FROZEN"
echo "RISK_CALIBRATION_ARTIFACT=$artifact"

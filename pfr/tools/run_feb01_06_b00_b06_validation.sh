#!/usr/bin/env bash
set -Eeuo pipefail

repo_dir=${PFR_REPO_DIR:-/home/jaewon/pfr_march_validity_fix}
output_root=${OUTPUT_ROOT:?set OUTPUT_ROOT to a new artifact directory}
methods=${METHODS:-"B00 B01 B02 B03 B04 B05 B06"}
count=${COUNT:-288}
h0_every=${H0_AUDIT_EVERY:-12}

mkdir -p "$output_root/logs"
pids=()

terminate_workers() {
    for pid in "${pids[@]:-}"; do
        kill -TERM -- "-$pid" 2>/dev/null || true
    done
}
trap terminate_workers INT TERM

for day_index in $(seq 1 6); do
    printf -v day_number '%02d' "$day_index"
    calendar_date="2025-02-$day_number"
    start_issue=$((8928 + (day_index - 1) * 288))
    day_root="$output_root/$calendar_date"
    log="$output_root/logs/$calendar_date.log"

    setsid env \
        PFR_REPO_DIR="$repo_dir" \
        OUTPUT_ROOT="$day_root" \
        COUNT="$count" \
        H0_AUDIT_EVERY="$h0_every" \
        METHODS="$methods" \
        CALENDAR_DATE="$calendar_date" \
        START_ISSUE="$start_issue" \
        CANDIDATE_ID="FEB2025_FULL_DAY$day_number" \
        PFR_GUROBI_THREADS="${PFR_GUROBI_THREADS:-4}" \
        bash "$repo_dir/pfr/tools/run_feb01_b00_b06_validation.sh" \
        >"$log" 2>&1 &
    pids+=("$!")
done

status=0
for pid in "${pids[@]}"; do
    if ! wait "$pid"; then
        status=1
    fi
done

if ((status != 0)); then
    echo "FEB01_06_B00_B06_VALIDATION=FAIL"
    exit "$status"
fi

echo "FEB01_06_B00_B06_VALIDATION=PASS"

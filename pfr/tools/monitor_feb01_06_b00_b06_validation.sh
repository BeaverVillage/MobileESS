#!/usr/bin/env bash
set -u

root="$1"
total_expected=$((6 * 7 * 288))
markers=$(find "$root" -path '*/issue_*/COMMIT_MARKER.json' -type f 2>/dev/null | wc -l)
methods=$(find "$root" -name SUMMARY.json -type f -exec grep -l '"status": "PASS"' {} + 2>/dev/null | wc -l)
fails=$(find "$root" \( -name FAILURE.json -o -name FAILURE_EVIDENCE.json -o -name ORCHESTRATION_FAILURE.json \) -type f 2>/dev/null | wc -l)
workers=$(pgrep -af 'pfr.tools.run_pfr_matrix' | grep -F "$root" | grep -v 'bash -lc' | wc -l)
percent=$(awk -v done="$markers" -v total="$total_expected" 'BEGIN { printf "%.1f", 100.0 * done / total }')

printf 'PASS methods:   %s / 42\n' "$methods"
printf 'Commit markers: %s / %s (%s%%)\n' "$markers" "$total_expected" "$percent"
printf 'Failures:       %s\n' "$fails"
printf 'Active workers: %s / 6\n' "$workers"
printf '\n%-12s %10s %13s %18s\n' 'AEST date' 'methods' 'issues' 'current method'
printf '%-12s %10s %13s %18s\n' '------------' '----------' '-------------' '------------------'

for day_index in $(seq 1 6); do
    printf -v day_number '%02d' "$day_index"
    day="2025-02-$day_number"
    day_root="$root/$day"
    method_count=$(find "$day_root" -name SUMMARY.json -type f -exec grep -l '"status": "PASS"' {} + 2>/dev/null | wc -l)
    issue_count=$(find "$day_root" -path '*/issue_*/COMMIT_MARKER.json' -type f 2>/dev/null | wc -l)
    current='-'
    for method_index in $(seq 0 6); do
        printf -v method_number '%02d' "$method_index"
        method="B$method_number"
        issue_progress=$(find "$day_root/$method" -path '*/issue_*/COMMIT_MARKER.json' -type f 2>/dev/null | wc -l)
        if ((issue_progress > 0 && issue_progress < 288)); then
            current="$method $issue_progress/288"
        elif ((issue_progress == 288)); then
            current="$method 288/288"
        fi
    done
    ((method_count == 7)) && current='DONE'
    printf '%-12s %4s / 7 %6s / 2016 %18s\n' "$day" "$method_count" "$issue_count" "$current"
done

printf '\nCPU / memory:\n'
top -bn1 | sed -n '3,4p'
free -h | sed -n '1,3p'

if ((fails > 0)); then
    printf '\nFailure files:\n'
    find "$root" \( -name FAILURE.json -o -name FAILURE_EVIDENCE.json -o -name ORCHESTRATION_FAILURE.json \) -type f -print 2>/dev/null
fi

((workers > 0))

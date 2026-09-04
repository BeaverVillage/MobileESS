#!/usr/bin/env bash
set -u

jan_root="$1"
march_root="$2"
jan_campaign="$jan_root/january_b07_electrical_stress_raw"
march_campaign="$march_root/march/B00_B09"
calibration="$jan_root/calibration/ELECTRICAL_STRESS_EVENT_RISK_CALIBRATION_JAN2025.json"
process_list=$(pgrep -af 'pfr.tools.run_pfr_matrix' || true)
master_active=$(pgrep -af 'run_january_calibration_then_march_final.sh' | grep -v 'bash -lc' | wc -l)

show_resources() {
    printf '\nCPU / memory:\n'
    top -bn1 | sed -n '3,4p'
    free -h | sed -n '1,3p'
}

if [[ ! -f "$calibration" ]]; then
    markers=$(find "$jan_campaign" -path '*/B07/issue_*/COMMIT_MARKER.json' -type f 2>/dev/null | wc -l)
    passes=$(find "$jan_campaign" -path '*/B07/METHOD_SUMMARY.json' -type f -exec grep -l '"execution_status": "PASS"' {} + 2>/dev/null | wc -l)
    fails=$(find "$jan_campaign" \( -name FAILURE.json -o -name FAILURE_EVIDENCE.json \) -type f 2>/dev/null | wc -l)
    workers=$(printf '%s\n' "$process_list" | grep -F "$jan_campaign" | grep -v 'bash -lc' | wc -l)
    percent=$(awk -v done="$markers" 'BEGIN { printf "%.1f", 100.0 * done / 4032.0 }')
    printf 'Phase:          JANUARY B07 CALIBRATION\n'
    printf 'PASS days:      %s / 14\n' "$passes"
    printf 'Commit markers: %s / 4032 (%s%%)\n' "$markers" "$percent"
    printf 'Failures:       %s\n' "$fails"
    printf 'Active workers: %s / 6\n' "$workers"
    printf '\n%-12s %13s %18s\n' 'AEST date' 'issues' 'active method'
    printf '%-12s %13s %18s\n' '------------' '-------------' '------------------'
    visible=0
    for day_number in $(seq -w 1 14); do
        day="2025-01-$day_number"
        day_root="$jan_campaign/$day/B07"
        summary="$day_root/METHOD_SUMMARY.json"
        if [[ -f "$summary" ]] && grep -q '"execution_status": "PASS"' "$summary"; then
            continue
        fi
        count=$(find "$day_root" -path '*/issue_*/COMMIT_MARKER.json' -type f 2>/dev/null | wc -l)
        active=$(printf '%s\n' "$process_list" | grep -F -- "--output $jan_campaign/$day" | head -n 1 || true)
        failure=$(find "$day_root" \( -name FAILURE.json -o -name FAILURE_EVIDENCE.json \) -type f -print -quit 2>/dev/null)
        [[ -n "$active" || -n "$failure" || "$count" -gt 0 ]] || continue
        if [[ -n "$failure" ]]; then state='FAILED'
        elif ((count == 0)); then state='B07 startup'
        else state="B07 $count/288"
        fi
        printf '%-12s %6s / 288 %18s\n' "$day" "$count" "$state"
        visible=$((visible + 1))
    done
    ((visible > 0)) || printf '%s\n' '(No unfinished started days)'
    show_resources
    ((workers > 0 || master_active > 0))
    exit $?
fi

markers=$(find "$march_campaign" -path '*/issue_*/COMMIT_MARKER.json' -type f 2>/dev/null | wc -l)
methods=$(find "$march_campaign" -name METHOD_SUMMARY.json -type f -exec grep -l '"execution_status": "PASS"' {} + 2>/dev/null | wc -l)
fails=$(find "$march_campaign" \( -name FAILURE.json -o -name FAILURE_EVIDENCE.json -o -name ORCHESTRATION_FAILURE.json \) -type f 2>/dev/null | wc -l)
workers=$(printf '%s\n' "$process_list" | grep -F "$march_campaign" | grep -v 'bash -lc' | wc -l)
percent=$(awk -v done="$markers" 'BEGIN { printf "%.1f", 100.0 * done / 89280.0 }')
printf 'Phase:          MARCH FINAL B00-B09\n'
printf 'PASS methods:   %s / 310\n' "$methods"
printf 'Commit markers: %s / 89280 (%s%%)\n' "$markers" "$percent"
printf 'Failures:       %s\n' "$fails"
printf 'Active workers: %s / 6\n' "$workers"
printf '\n%-12s %10s %13s %18s\n' 'AEST date' 'methods' 'issues' 'active method'
printf '%-12s %10s %13s %18s\n' '------------' '----------' '-------------' '------------------'
visible=0
for day_number in $(seq -w 1 31); do
    day="2025-03-$day_number"
    day_root="$march_campaign/$day"
    method_count=$(find "$day_root" -name METHOD_SUMMARY.json -type f -exec grep -l '"execution_status": "PASS"' {} + 2>/dev/null | wc -l)
    ((method_count < 10)) || continue
    issue_count=$(find "$day_root" -path '*/issue_*/COMMIT_MARKER.json' -type f 2>/dev/null | wc -l)
    active_cmd=$(printf '%s\n' "$process_list" | grep -F -- "--output $day_root" | head -n 1 || true)
    failure=$(find "$day_root" \( -name FAILURE.json -o -name FAILURE_EVIDENCE.json -o -name ORCHESTRATION_FAILURE.json \) -type f -print -quit 2>/dev/null)
    [[ -n "$active_cmd" || -n "$failure" || "$issue_count" -gt 0 ]] || continue
    active_method=$(printf '%s\n' "$active_cmd" | sed -n 's/.*--diagnostic-method \([^ ]*\).*/\1/p')
    if [[ -n "$failure" && -z "$active_method" ]]; then
        state='FAILED'
    elif [[ -n "$active_method" ]]; then
        method_issues=$(find "$day_root/$active_method" -path '*/issue_*/COMMIT_MARKER.json' -type f 2>/dev/null | wc -l)
        if ((method_issues == 0)); then state="$active_method startup"
        else state="$active_method $method_issues/288"
        fi
    else
        state='WAITING/FINALIZING'
    fi
    printf '%-12s %4s / 10 %6s / 2880 %18s\n' "$day" "$method_count" "$issue_count" "$state"
    visible=$((visible + 1))
done
((visible > 0)) || printf '%s\n' '(No unfinished started days)'
show_resources
((workers > 0 || master_active > 0))

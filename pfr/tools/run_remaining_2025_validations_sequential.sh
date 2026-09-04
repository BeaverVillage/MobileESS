#!/usr/bin/env bash
set -Eeuo pipefail

repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
jan_output="${PFR_JAN_OUTPUT:-/home/jaewon/mobile_ess_work/frozen_artifacts/CODEX_PR6_V13_13_JAN2025_DAILY_20260823}"
workers=4

usage() {
    echo "Usage: $0 [--day-workers 4]"
}

while (($#)); do
    case "$1" in
        --day-workers) workers="$2"; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) echo "Unknown option: $1" >&2; usage >&2; exit 64 ;;
    esac
done
if [[ "$workers" != "4" ]]; then
    echo "This frozen validation launcher requires exactly four day workers." >&2
    exit 64
fi

cd "$repo_dir"

# Fail closed and in chronological order: remaining January first, then the
# frozen February and March representative weeks.  Every date cold-starts and
# an already-complete PASS with the same implementation fingerprint is reused.
bash pfr/tools/run_january_2025_local.sh \
    --start-day 16 --end-day 31 \
    --day-workers 4 --gurobi-threads 4 \
    --output-root "$jan_output"

bash pfr/tools/run_february_march_2025_rep_weeks_local.sh \
    --day-workers 4

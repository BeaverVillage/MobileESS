#!/usr/bin/env bash
set -uo pipefail

repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
python_bin="${PFR_PYTHON:-/home/jaewon/miniconda3/envs/power_v61_gpu/bin/python}"
base="/home/jaewon/mobile_ess_work/frozen_artifacts"
jan_root="$base/CODEX_PR6_V13_13_JAN2025_FULL_DAILY_20260823"
preflight_only=0

while (($#)); do
    case "$1" in
        --preflight-only) preflight_only=1; shift ;;
        -h|--help)
            echo "Usage: $0 [--preflight-only]"
            echo "Runs 4 daily processes x 4 Gurobi threads."
            exit 0
            ;;
        *) echo "Unknown option: $1" >&2; exit 64 ;;
    esac
done

cd "$repo_dir"
overall=0

run_january_preflight() {
    bash "$repo_dir/pfr/tools/run_january_2025_local.sh" \
        --preflight-only --start-day 1 --end-day 31 \
        --day-workers 4 --gurobi-threads 4 --output-root "$jan_root"
}

if ((preflight_only)); then
    if ! run_january_preflight; then overall=1; fi
    if ! bash "$repo_dir/pfr/tools/run_full_february_march_2025_local.sh" \
        --prepare-only; then
        overall=1
    fi
    if ((overall == 0)); then
        echo "JANUARY_TO_MARCH_PREFLIGHT_STATUS=PASS_NO_EPISODES_STARTED"
    else
        echo "JANUARY_TO_MARCH_PREFLIGHT_STATUS=FAIL_NO_EPISODES_STARTED" >&2
    fi
    exit "$overall"
fi

echo "Execution policy: B failure -> save evidence -> next B; day failure -> next day; period failure -> next period."
echo "No scientific failure automatically stops the full local campaign."

jan_campaign_rc=0
bash "$repo_dir/pfr/tools/run_january_2025_local.sh" \
    --start-day 1 --end-day 31 --day-workers 4 --gurobi-threads 4 \
    --output-root "$jan_root" || jan_campaign_rc=$?

jan_verify_rc=0
"$python_bin" -m pfr.tools.verify_daily_campaign_storage \
    --repo "$repo_dir" --root "$jan_root" --start-date 2025-01-01 --days 31 \
    --report "$jan_root/STORAGE_VERIFICATION.json" || jan_verify_rc=$?
if ((jan_campaign_rc != 0 || jan_verify_rc != 0)); then
    overall=1
    echo "JANUARY_COMPLETED_WITH_RECORDED_FAILURE campaign_rc=$jan_campaign_rc verify_rc=$jan_verify_rc" >&2
else
    echo "JANUARY_STATUS=PASS"
fi

rep_rc=0
bash "$repo_dir/pfr/tools/run_full_february_march_2025_local.sh" || rep_rc=$?
if ((rep_rc != 0)); then overall=1; fi

if ((overall == 0)); then
    echo "JANUARY_TO_MARCH_EXECUTION_STATUS=PASS"
else
    echo "JANUARY_TO_MARCH_EXECUTION_STATUS=COMPLETE_WITH_RECORDED_FAILURES" >&2
fi
echo "All requested periods were attempted. See each STORAGE_VERIFICATION.json and CAMPAIGN_SUMMARY.json."
exit "$overall"

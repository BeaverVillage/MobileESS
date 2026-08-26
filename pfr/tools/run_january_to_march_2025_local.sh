#!/usr/bin/env bash
set -uo pipefail

repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
python_bin="${PFR_PYTHON:-/home/jaewon/miniconda3/envs/power_v61_gpu/bin/python}"
base="/home/jaewon/mobile_ess_work/frozen_artifacts"
run_root=""
preflight_only=0
january_only=0
risk_calibration=""

interrupt_run() {
    trap - INT TERM
    echo "INTERRUPTED_BY_USER: stopping January-to-March execution; partial results are preserved." >&2
    exit 130
}
terminate_run() {
    trap - INT TERM
    echo "TERMINATED: stopping January-to-March execution; partial results are preserved." >&2
    exit 143
}
trap interrupt_run INT
trap terminate_run TERM

abort_if_interrupted() {
    local rc="$1"
    local phase="$2"
    if ((rc == 130 || rc == 143)); then
        echo "EXECUTION_STOPPED phase=$phase rc=$rc" >&2
        exit "$rc"
    fi
}

while (($#)); do
    case "$1" in
        --preflight-only) preflight_only=1; shift ;;
        --run-root)
            if (($# < 2)); then echo "Missing value for --run-root" >&2; exit 64; fi
            run_root="$2"
            shift 2
            ;;
        --risk-calibration)
            if (($# < 2)); then echo "Missing value for --risk-calibration" >&2; exit 64; fi
            risk_calibration="$2"
            shift 2
            ;;
        --january-only)
            january_only=1
            shift
            ;;
        -h|--help)
            echo "Usage: $0 --run-root ABSOLUTE_PATH --risk-calibration FILE [--preflight-only] [--january-only]"
            echo "Runs 4 daily processes x 4 Gurobi threads."
            echo "Default: attempt January, February, and March in order; preserve failures and continue."
            exit 0
            ;;
        *) echo "Unknown option: $1" >&2; exit 64 ;;
    esac
done

cd "$repo_dir"
overall=0
expected_full_commit_sha="${PFR_EXPECTED_FULL_COMMIT_SHA:-}"
expected_branch="${PFR_EXPECTED_BRANCH:-codex/feb03-predictive-native}"
if [[ -z "$run_root" || "$run_root" != /* ]]; then
    echo "ABORT_ISOLATION: --run-root must be a new or previously authorized absolute path." >&2
    exit 2
fi
if [[ -z "$risk_calibration" || ! -f "$risk_calibration" ]]; then
    echo "ABORT_CALIBRATION: an existing frozen --risk-calibration is required." >&2
    exit 2
fi
"$python_bin" -c 'from pathlib import Path; import sys; from pfr.risk_calibration import load_frozen_risk_calibration; load_frozen_risk_calibration(Path(sys.argv[1]))' "$risk_calibration" || exit 2
if [[ ! "$expected_full_commit_sha" =~ ^[0-9a-f]{40}$ ]]; then
    echo "ABORT_ISOLATION: set PFR_EXPECTED_FULL_COMMIT_SHA to the frozen 40-character commit." >&2
    exit 2
fi
"$python_bin" -m pfr.tools.jfm_isolation \
    --run-root "$run_root" --initialize \
    --expected-full-commit-sha "$expected_full_commit_sha" \
    --expected-branch "$expected_branch" || exit 2
jan_root="$run_root/january/B00_B09"
export PFR_JFM_RUN_ROOT="$run_root"
echo "ISOLATED_JFM_RUN_ROOT=$run_root"

run_january_preflight() {
    bash "$repo_dir/pfr/tools/run_january_2025_local.sh" \
        --preflight-only --start-day 1 --end-day 31 \
        --day-workers 4 --gurobi-threads 4 --output-root "$jan_root" \
        --risk-calibration "$risk_calibration"
}

if ((preflight_only)); then
    if ! run_january_preflight; then overall=1; fi
    if ((january_only == 0)); then
        if ! bash "$repo_dir/pfr/tools/run_full_february_march_2025_local.sh" \
            --prepare-only --run-root "$run_root" \
            --risk-calibration "$risk_calibration"; then
            overall=1
        fi
    fi
    if ((overall == 0)); then
        echo "JANUARY_TO_MARCH_PREFLIGHT_STATUS=PASS_NO_EPISODES_STARTED"
    else
        echo "JANUARY_TO_MARCH_PREFLIGHT_STATUS=FAIL_NO_EPISODES_STARTED" >&2
    fi
    exit "$overall"
fi

echo "Execution policy: every failure is preserved and recorded, then the next method/day/month continues."
echo "February and March continue even if January fails; --january-only explicitly stops after January."

jan_campaign_rc=0
bash "$repo_dir/pfr/tools/run_january_2025_local.sh" \
    --start-day 1 --end-day 31 --day-workers 4 --gurobi-threads 4 \
    --output-root "$jan_root" --risk-calibration "$risk_calibration" \
    || jan_campaign_rc=$?
abort_if_interrupted "$jan_campaign_rc" "january_b00_b09"

jan_verify_rc=0
"$python_bin" -m pfr.tools.verify_daily_campaign_storage \
    --repo "$repo_dir" --root "$jan_root" --start-date 2025-01-01 --days 31 \
    --electrical-stress-campaign \
    --report "$jan_root/STORAGE_VERIFICATION.json" || jan_verify_rc=$?
if ((jan_campaign_rc != 0 || jan_verify_rc != 0)); then
    overall=1
    echo "JANUARY_COMPLETED_WITH_RECORDED_FAILURE campaign_rc=$jan_campaign_rc verify_rc=$jan_verify_rc" >&2
else
    echo "JANUARY_STATUS=PASS"
fi

if ((january_only)); then
    if ((overall == 0)); then
        echo "JANUARY_IDC_REFREEZE_STATUS=PASS_OUT_OF_MONTH_NOT_STARTED"
    else
        echo "JANUARY_IDC_REFREEZE_STATUS=FAILURES_RECORDED_OUT_OF_MONTH_NOT_STARTED" >&2
    fi
    exit "$overall"
fi

if ((overall != 0)); then
    echo "JANUARY_FAILURES_RECORDED_CONTINUING_TO_FEBRUARY_MARCH" >&2
fi

rep_rc=0
bash "$repo_dir/pfr/tools/run_full_february_march_2025_local.sh" \
    --run-root "$run_root" --risk-calibration "$risk_calibration" || rep_rc=$?
abort_if_interrupted "$rep_rc" "february_march"
if ((rep_rc != 0)); then overall=1; fi

if ((overall == 0)); then
    echo "JANUARY_TO_MARCH_EXECUTION_STATUS=PASS"
else
    echo "JANUARY_TO_MARCH_EXECUTION_STATUS=COMPLETE_WITH_RECORDED_FAILURES" >&2
fi
echo "All requested periods were attempted. See each STORAGE_VERIFICATION.json and CAMPAIGN_SUMMARY.json."
exit "$overall"

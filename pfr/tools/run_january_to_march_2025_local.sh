#!/usr/bin/env bash
set -uo pipefail

repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
python_bin="${PFR_PYTHON:-/home/jaewon/miniconda3/envs/power_v61_gpu/bin/python}"
base="/home/jaewon/mobile_ess_work/frozen_artifacts"
jan_root="$base/JAN2025_IDC_REFREEZE_V1_B0_B7"
b8_root="$base/JAN2025_IDC_REFREEZE_V1_B8"
preflight_only=0
skip_migration_sensitivity=0
january_only=0

while (($#)); do
    case "$1" in
        --preflight-only) preflight_only=1; shift ;;
        --skip-migration-sensitivity) skip_migration_sensitivity=1; shift ;;
        --january-only)
            january_only=1
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [--preflight-only] [--skip-migration-sensitivity] [--january-only]"
            echo "Runs 4 daily processes x 4 Gurobi threads."
            echo "Default: attempt January, February, and March in order; preserve failures and continue."
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
    if ((january_only == 0)); then
        if ! bash "$repo_dir/pfr/tools/run_full_february_march_2025_local.sh" \
            --prepare-only; then
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

if ((skip_migration_sensitivity == 0)); then
    sensitivity_rc=0
    PFR_DAY_WORKERS=4 PFR_GUROBI_THREADS=4 \
        bash "$repo_dir/pfr/tools/run_january_2025_migration_sensitivity_local.sh" \
        || sensitivity_rc=$?
    if ((sensitivity_rc != 0)); then
        overall=1
        echo "JANUARY_MIGRATION_SENSITIVITY_FAILED_BUT_CONTINUING rc=$sensitivity_rc" >&2
    fi
fi

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

b8_campaign_rc=0
bash "$repo_dir/pfr/tools/run_january_2025_b8_periodic5_local.sh" \
    --start-day 1 --end-day 31 --day-workers 4 --gurobi-threads 4 \
    --output-root "$b8_root" || b8_campaign_rc=$?
if ((b8_campaign_rc != 0)); then
    overall=1
    echo "JANUARY_B8_COMPLETED_WITH_RECORDED_FAILURE rc=$b8_campaign_rc" >&2
fi

episode_args=()
b8_episode_args=()
for day in $(seq 0 30); do
    calendar_date=$(date -d "2025-01-01 +${day} days" +%F)
    episode_args+=(--episode "$calendar_date=$jan_root/$calendar_date")
    b8_episode_args+=(--b8-episode "$calendar_date=$b8_root/$calendar_date")
done

jan_artifact_rc=0
"$python_bin" -m pfr.tools.validate_january_artifacts \
    "${episode_args[@]}" \
    --output "$jan_root/JANUARY_ARTIFACT_VALIDATION.json" || jan_artifact_rc=$?

jan_analysis_rc=0
"$python_bin" -m pfr.tools.analyze_january_daily \
    "${episode_args[@]}" \
    --output "$jan_root/JANUARY_DAILY_ANALYSIS.json" || jan_analysis_rc=$?

main_episode_args=()
for day in $(seq 0 30); do
    calendar_date=$(date -d "2025-01-01 +${day} days" +%F)
    main_episode_args+=(--main-episode "$calendar_date=$jan_root/$calendar_date")
done
b8_analysis_rc=0
"$python_bin" -m pfr.tools.analyze_january_b8_timing \
    "${main_episode_args[@]}" \
    "${b8_episode_args[@]}" \
    --output "$jan_root/JANUARY_B7_VS_B8_TIMING.json" || b8_analysis_rc=$?

if ((jan_artifact_rc != 0 || jan_analysis_rc != 0 || b8_analysis_rc != 0)); then
    overall=1
    echo "JANUARY_VALIDATION_FAIL artifact_rc=$jan_artifact_rc analysis_rc=$jan_analysis_rc b8_analysis_rc=$b8_analysis_rc" >&2
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
bash "$repo_dir/pfr/tools/run_full_february_march_2025_local.sh" || rep_rc=$?
if ((rep_rc != 0)); then overall=1; fi

if ((overall == 0)); then
    echo "JANUARY_TO_MARCH_EXECUTION_STATUS=PASS"
else
    echo "JANUARY_TO_MARCH_EXECUTION_STATUS=COMPLETE_WITH_RECORDED_FAILURES" >&2
fi
echo "All requested periods were attempted. See each STORAGE_VERIFICATION.json and CAMPAIGN_SUMMARY.json."
exit "$overall"

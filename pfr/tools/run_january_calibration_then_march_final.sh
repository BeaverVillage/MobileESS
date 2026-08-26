#!/usr/bin/env bash
set -Eeuo pipefail

repo=${PFR_REPO_DIR:-/home/jaewon/pfr_march_validity_fix}
python_bin=${PFR_PYTHON:-/home/jaewon/miniconda3/envs/power_v61_gpu/bin/python}
work=/home/jaewon/mobile_ess_work
base=$work/frozen_artifacts
expected_sha=${PFR_EXPECTED_FULL_COMMIT_SHA:?set PFR_EXPECTED_FULL_COMMIT_SHA}
expected_branch=${PFR_EXPECTED_BRANCH:-codex/march-validity-fixes}
git_dir=${PFR_GIT_DIR:-/mnt/c/Users/kjw39/OneDrive/문서/ChatGPT/Mobile\ ESS/github_MobileESS/.git/worktrees/github_MobileESS_march_validity_fix}
jan_root=${JAN_RUN_ROOT:?set JAN_RUN_ROOT}
march_root=${MARCH_RUN_ROOT:?set MARCH_RUN_ROOT}
log_file=${RUN_LOG_FILE:-$work/logs/january_calibration_then_march_final.log}
calibration=$jan_root/calibration/ELECTRICAL_STRESS_EVENT_RISK_CALIBRATION_JAN2025.json
contract=$repo/pfr/contracts/FROZEN_2025_FULL_MONTH_VALIDATION_PERIODS_V1.json
shared=$base/PFR_MAR2025_FULL_SHARED_EXOGENOUS_V13_13
input_root=$base/PFR_MAR2025_FULL_V13_13_DAILY_INPUTS
output=$march_root/march/B00_B09
gate_root=$march_root/preflight/MAR2025_FULL
canonical=$base/stage_kestrel_f30_resource_aware_job_power_policy_v2_0_32_r6c_20260806T122335/CANONICAL_F30_RACK_POWER_JOB_BASE_PREFROZEN_R6C.parquet
child_pid=""

mkdir -p "$(dirname "$log_file")" "$jan_root" "$march_root"

stop_child() {
    local rc=$1
    trap - INT TERM
    if [[ -n "$child_pid" ]] && kill -0 "$child_pid" 2>/dev/null; then
        kill -TERM -- "-$child_pid" 2>/dev/null || true
        wait "$child_pid" 2>/dev/null || true
    fi
    echo "SEQUENTIAL_FINAL_RUN=INTERRUPTED_ALL_WORKERS_STOPPED"
    exit "$rc"
}
trap 'stop_child 130' INT
trap 'stop_child 143' TERM

run_child() {
    setsid "$@" &
    child_pid=$!
    local rc=0
    wait "$child_pid" || rc=$?
    child_pid=""
    return "$rc"
}

main() {
    cd "$repo"
    export PFR_EXPECTED_FULL_COMMIT_SHA="$expected_sha"
    export PFR_EXPECTED_BRANCH="$expected_branch"
    export GIT_DIR="$git_dir" GIT_WORK_TREE="$repo"
    export PFR_DAY_WORKERS=6 PFR_GUROBI_THREADS=2
    export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
    export NUMEXPR_NUM_THREADS=1 PYTHONHASHSEED=0

    if [[ -f "$calibration" ]]; then
        "$python_bin" -c 'import json,sys; from pathlib import Path; p=Path(sys.argv[1]); r=json.loads(p.read_text()); assert r.get("status") == "PASS" and r.get("storage_integrity") == "PASS", r; print("JANUARY_STORAGE_VERIFIED", p)' \
            "$jan_root/january_b07_electrical_stress_raw/STORAGE_VERIFICATION.json"
        echo "=== JANUARY B07 CALIBRATION ALREADY FROZEN; SKIP $(date -Is) ==="
    else
        echo "=== JANUARY B07 CALIBRATION START $(date -Is) ==="
        run_child bash "$repo/pfr/tools/run_january_b07_risk_calibration_local.sh" \
            --run-root "$jan_root" --day-workers 6 --gurobi-threads 2 \
            --cpu-affinity disjoint
        test -f "$calibration"
    fi
    "$python_bin" -c 'from pathlib import Path; import sys; from pfr.risk_calibration import load_frozen_risk_calibration; x=load_frozen_risk_calibration(Path(sys.argv[1])); print("JANUARY_CALIBRATION_VERIFIED", x.artifact_sha256)' "$calibration"
    echo "=== JANUARY B07 CALIBRATION PASS $(date -Is) ==="

    echo "=== MARCH FINAL START $(date -Is) ==="
    "$python_bin" -m pfr.tools.jfm_isolation \
        --run-root "$march_root" --initialize \
        --expected-full-commit-sha "$expected_sha" \
        --expected-branch "$expected_branch"

    authority_sha=$(
        "$python_bin" -c 'import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())' "$contract"
    )
    mkdir -p "$input_root"
    "$python_bin" -m pfr.tools.build_calendar_daily_pre \
        --start-date 2025-03-01 --days 31 --campaign-id MAR2025_FULL \
        --authority-sha256 "$authority_sha" --output-root "$input_root/pre" \
        --electrical-stress-campaign
    "$python_bin" -m pfr.tools.build_calendar_job_cohort \
        --canonical "$canonical" --start-date 2025-03-01 --days 31 \
        --campaign-id MAR2025_FULL \
        --output "$input_root/jobs/INDEPENDENT_JOB_COHORT.parquet" \
        --authority-output "$input_root/jobs/INDEPENDENT_JOB_COHORT_AUTHORITY.json"
    "$python_bin" -m pfr.tools.prepare_full_month_source_view \
        --repo "$repo" --period-id MAR2025_FULL --period-contract "$contract" \
        --shared-root "$shared" \
        --generated-mobility-root "$base/PFR_V13_13_FULL_MONTH_SOURCE_CHUNKS/MAR2025_FULL/16992/mobility" \
        --generated-mobility-root "$base/PFR_V13_13_FULL_MONTH_SOURCE_CHUNKS/MAR2025_FULL/19296/mobility" \
        --generated-mobility-root "$base/PFR_V13_13_FULL_MONTH_SOURCE_CHUNKS/MAR2025_FULL/21600/mobility" \
        --generated-mobility-root "$base/PFR_V13_13_FULL_MONTH_SOURCE_CHUNKS/MAR2025_FULL/23904/mobility"

    mkdir -p "$gate_root"
    "$python_bin" -m pfr.tools.assert_experiment_source_freeze \
        --repo "$repo" --expected-full-commit-sha "$expected_sha" \
        --expected-branch "$expected_branch" \
        --migration-authority "$repo/pfr/contracts/IDC_MIGRATION_AUTHORITY_V1.json" \
        --report "$gate_root/SOURCE_FREEZE_GATE.json"
    "$python_bin" -m pfr.tools.preflight_full_month_2025 \
        --repo "$repo" --period-id MAR2025_FULL --period-contract "$contract" \
        --shared-root "$shared" --input-root "$input_root" \
        --route-catalog "$base/PFR3_FIXED_K3_PHYSICS_CURRENT/FROZEN_K3_PHYSICS_GEOMETRY.json" \
        --electrical-stress-campaign --report "$gate_root/PREFLIGHT_REPORT.json"

    run_child "$python_bin" -m pfr.tools.run_frozen_rep_week_daily_campaign \
        --repo "$repo" --period-id MAR2025_FULL --period-contract "$contract" \
        --day-workers 6 --cpu-affinity disjoint --capture-day-logs \
        --continue-after-failure --electrical-stress-campaign \
        --h0-fidelity-audit-every-steps 12 \
        --shared-root "$shared" \
        --exact-package-root /mnt/c/Users/kjw39/Downloads/stage_mess_grid_v2038_exact_sweep_power_v70_final_v1_package \
        --authority-package-root "$work/run_packages/K9H7_V2044R11R1_20260807T191351" \
        --primary-root "$work/processed/power_v70_3ph" \
        --initial-state "$input_root/pre/DAILY_CANONICAL_PRE_MANIFEST.json" \
        --independent-jobs "$input_root/jobs/INDEPENDENT_JOB_COHORT.parquet" \
        --canonical-jobs "$canonical" \
        --power-curve "$repo/pfr/contracts/H100_UTILIZATION_POWER_CURVE.json" \
        --mobility-root "$shared/mobility" \
        --route-catalog "$base/PFR3_FIXED_K3_PHYSICS_CURRENT/FROZEN_K3_PHYSICS_GEOMETRY.json" \
        --mobility-template-bank "$shared/mobility/E4B_FULLFIT_TEMPLATE_BANK_129.parquet" \
        --workload-uncertainty "$base/PFR3_V13_2_WORKLOAD_UNCERTAINTY_CURRENT/PFR3_WORKLOAD_UNCERTAINTY_V13_2.json" \
        --factorized-uncertainty "$base/PFR3_V13_2_FACTORIZED_UNCERTAINTY_CURRENT/PFR3_FACTORIZED_UNCERTAINTY_V13_2.json" \
        --migration-authority "$repo/pfr/contracts/IDC_MIGRATION_AUTHORITY_V1.json" \
        --risk-calibration "$calibration" --output "$output"

    "$python_bin" -m pfr.tools.verify_daily_campaign_storage \
        --repo "$repo" --root "$output" --start-date 2025-03-01 --days 31 \
        --electrical-stress-campaign \
        --report "$output/STORAGE_VERIFICATION.json"
    "$python_bin" -m pfr.tools.audit_h0_surrogate_fidelity \
        --campaign-root "$output" \
        --contract "$repo/pfr/contracts/H0_SURROGATE_FIDELITY_GATE_V1.json" \
        --phase march --output "$output/H0_SURROGATE_FIDELITY_AUDIT.json"
    echo "MARCH_FINAL=PASS"
}

exec > >(tee -a "$log_file") 2>&1
main
echo "JANUARY_CALIBRATION_THEN_MARCH_FINAL=PASS"

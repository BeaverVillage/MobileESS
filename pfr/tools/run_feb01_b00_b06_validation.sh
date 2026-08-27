#!/usr/bin/env bash
set -euo pipefail

repo_dir=${PFR_REPO_DIR:-/home/jaewon/pfr_march_validity_fix}
python_bin=${PFR_PYTHON_BIN:-/home/jaewon/miniconda3/envs/power_v61_gpu/bin/python}
output_root=${OUTPUT_ROOT:?set OUTPUT_ROOT to a new artifact directory}
count=${COUNT:-288}
h0_every=${H0_AUDIT_EVERY:-12}
methods=${METHODS:-"B00 B01 B02 B03 B04 B05 B06"}
calendar_date=${CALENDAR_DATE:-2025-02-01}
start_issue=${START_ISSUE:-8928}
candidate_id=${CANDIDATE_ID:-FEB2025_FULL_DAY01}

cd "$repo_dir"
export PFR_GUROBI_THREADS=${PFR_GUROBI_THREADS:-4}

for method in $methods; do
    if [[ -f "$output_root/$method/SUMMARY.json" ]] && \
       grep -q '"status": "PASS"' "$output_root/$method/SUMMARY.json"; then
        echo "SKIP completed PASS $method"
        continue
    fi
    "$python_bin" -m pfr.tools.run_pfr_matrix \
        --repo "$repo_dir" \
        --count "$count" \
        --shared-root /home/jaewon/mobile_ess_work/frozen_artifacts/PFR_FEB2025_FULL_SHARED_EXOGENOUS_V13_13 \
        --exact-package-root /mnt/c/Users/kjw39/Downloads/stage_mess_grid_v2038_exact_sweep_power_v70_final_v1_package \
        --authority-package-root /home/jaewon/mobile_ess_work/run_packages/K9H7_V2044R11R1_20260807T191351 \
        --primary-root /home/jaewon/mobile_ess_work/processed/power_v70_3ph \
        --initial-state /home/jaewon/mobile_ess_work/frozen_artifacts/PFR_FEB2025_FULL_V13_13_DAILY_INPUTS/pre/DAILY_CANONICAL_PRE_MANIFEST.json \
        --independent-jobs /home/jaewon/mobile_ess_work/frozen_artifacts/PFR_FEB2025_FULL_V13_13_DAILY_INPUTS/jobs/INDEPENDENT_JOB_COHORT.parquet \
        --canonical-jobs /home/jaewon/mobile_ess_work/frozen_artifacts/stage_kestrel_f30_resource_aware_job_power_policy_v2_0_32_r6c_20260806T122335/CANONICAL_F30_RACK_POWER_JOB_BASE_PREFROZEN_R6C.parquet \
        --power-curve "$repo_dir/pfr/contracts/H100_UTILIZATION_POWER_CURVE.json" \
        --route-catalog /home/jaewon/mobile_ess_work/frozen_artifacts/PFR3_FIXED_K3_PHYSICS_CURRENT/FROZEN_K3_PHYSICS_GEOMETRY.json \
        --mobility-template-bank /home/jaewon/mobile_ess_work/frozen_artifacts/PFR_FEB2025_FULL_SHARED_EXOGENOUS_V13_13/mobility/E4B_FULLFIT_TEMPLATE_BANK_129.parquet \
        --workload-uncertainty /home/jaewon/mobile_ess_work/frozen_artifacts/PFR3_V13_2_WORKLOAD_UNCERTAINTY_CURRENT/PFR3_WORKLOAD_UNCERTAINTY_V13_2.json \
        --factorized-uncertainty /home/jaewon/mobile_ess_work/frozen_artifacts/PFR3_V13_2_FACTORIZED_UNCERTAINTY_CURRENT/PFR3_FACTORIZED_UNCERTAINTY_V13_2.json \
        --migration-authority "$repo_dir/pfr/contracts/IDC_MIGRATION_AUTHORITY_V1.json" \
        --mobility-root /home/jaewon/mobile_ess_work/frozen_artifacts/PFR_FEB2025_FULL_SHARED_EXOGENOUS_V13_13/mobility \
        --risk-calibration /home/jaewon/mobile_ess_work/frozen_artifacts/HIERARCHICAL_ELECTRICAL_STRESS_JAN2025_CALIBRATION_7147D56_20260826_R14/calibration/ELECTRICAL_STRESS_EVENT_RISK_CALIBRATION_JAN2025.json \
        --h0-fidelity-audit-every-steps "$h0_every" \
        --candidate-id "$candidate_id" \
        --calendar-date "$calendar_date" \
        --start-issue "$start_issue" \
        --output "$output_root" \
        --diagnostic-method "$method" \
        --electrical-stress-campaign
done

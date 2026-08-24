#!/usr/bin/env bash
set -uo pipefail

repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
python_bin="${PFR_PYTHON:-/home/jaewon/miniconda3/envs/power_v61_gpu/bin/python}"
base="/home/jaewon/mobile_ess_work/frozen_artifacts"
period_id="APR2025_FULL"
contract="$repo_dir/pfr/contracts/FROZEN_2025_APRIL_VALIDATION_PERIOD_V1.json"
input_root="$base/PFR_${period_id}_V13_13_DAILY_INPUTS"
shared="$base/PFR_${period_id}_SHARED_EXOGENOUS_V13_13"
canonical="$base/stage_kestrel_f30_resource_aware_job_power_policy_v2_0_32_r6c_20260806T122335/CANONICAL_F30_RACK_POWER_JOB_BASE_PREFROZEN_R6C.parquet"
plan_only=0
if [[ "${1:-}" == "--plan-only" ]]; then plan_only=1; shift; fi
if (($#)); then echo "Usage: $0 [--plan-only]" >&2; exit 64; fi

cd "$repo_dir"
authority_sha="$($python_bin -c 'import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())' "$contract")"
mkdir -p "$input_root"
"$python_bin" -m pfr.tools.build_calendar_daily_pre \
    --start-date 2025-04-01 --days 30 --campaign-id "$period_id" \
    --authority-sha256 "$authority_sha" --output-root "$input_root/pre" || exit 1
"$python_bin" -m pfr.tools.build_calendar_job_cohort \
    --canonical "$canonical" --start-date 2025-04-01 --days 30 \
    --campaign-id "$period_id" \
    --output "$input_root/jobs/INDEPENDENT_JOB_COHORT.parquet" \
    --authority-output "$input_root/jobs/INDEPENDENT_JOB_COHORT_AUTHORITY.json" || exit 1

if ((plan_only)); then
    bash "$repo_dir/pfr/tools/prepare_april_2025_sources.sh" --plan-only || exit 1
    "$python_bin" -m pfr.tools.preflight_full_month_2025 \
        --repo "$repo_dir" --period-id "$period_id" \
        --period-contract "$contract" --shared-root "$shared" \
        --input-root "$input_root" --allow-unmaterialized \
        --report "$input_root/PREFLIGHT_REPORT.json"
    exit $?
fi

bash "$repo_dir/pfr/tools/prepare_april_2025_sources.sh" || exit 1
"$python_bin" -m pfr.tools.preflight_full_month_2025 \
    --repo "$repo_dir" --period-id "$period_id" \
    --period-contract "$contract" --shared-root "$shared" \
    --input-root "$input_root" \
    --report "$input_root/PREFLIGHT_REPORT.json" || exit 1
echo "APRIL_2025_PREPARATION_STATUS=PASS_READY_TO_RUN"

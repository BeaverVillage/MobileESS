#!/usr/bin/env bash
set -uo pipefail

repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
python_bin="${PFR_PYTHON:-/home/jaewon/miniconda3/envs/power_v61_gpu/bin/python}"
base="/home/jaewon/mobile_ess_work/frozen_artifacts"
plan_only=0
if [[ "${1:-}" == "--plan-only" ]]; then plan_only=1; shift; fi
if (($#)); then echo "Usage: $0 [--plan-only]" >&2; exit 64; fi

contract="$repo_dir/pfr/contracts/FROZEN_2025_FULL_MONTH_VALIDATION_PERIODS_V1.json"
power_generator="$repo_dir/performance/post_stage15_runtime_acceleration/package/scripts/PREPARE_W02_POWER_PRICE_SOURCE.py"
mobility_generator="$repo_dir/performance/post_stage15_runtime_acceleration/package/scripts/PREPARE_W02_MOBILITY_SOURCE.py"

period_value() {
    "$python_bin" -c 'import json,sys; c=json.load(open(sys.argv[1])); p=next(x for x in c["periods"] if x["period_id"]==sys.argv[2]); print(p[sys.argv[3]])' "$contract" "$1" "$2"
}

generated_roots() {
    local period_id="$1"
    "$python_bin" -c 'import json,sys; c=json.load(open(sys.argv[1])); p=next(x for x in c["periods"] if x["period_id"]==sys.argv[2]); [print("/home/jaewon/mobile_ess_work/frozen_artifacts/PFR_V13_13_FULL_MONTH_SOURCE_CHUNKS/{}/{}/mobility".format(sys.argv[2],x["start"])) for x in p["mobility_generation_chunks"]]' "$contract" "$period_id"
}

source_view_command() {
    local period_id="$1" shared="$2"
    local args=(
        "$python_bin" -m pfr.tools.prepare_full_month_source_view
        --repo "$repo_dir" --period-id "$period_id" --shared-root "$shared"
    )
    while IFS= read -r root; do
        args+=(--generated-mobility-root "$root")
    done < <(generated_roots "$period_id")
    if ((plan_only)); then args+=(--plan-only); fi
    "${args[@]}"
}

if ((plan_only)); then
    overall=0
    for period_id in FEB2025_FULL MAR2025_FULL; do
        shared="$base/PFR_${period_id}_SHARED_EXOGENOUS_V13_13"
        if ! source_view_command "$period_id" "$shared"; then overall=1; fi
    done
    exit "$overall"
fi

gpu_python="${PFR_MOBILITY_PYTHON:-}"
if [[ -z "$gpu_python" ]]; then
    for candidate in \
        /home/jaewon/miniconda3/envs/scats_parser/bin/python3.12 \
        /home/jaewon/miniconda3/envs/scats_parser/bin/python \
        /home/jaewon/miniconda3/envs/power_v61_gpu/bin/python; do
        [[ -x "$candidate" ]] || continue
        if "$candidate" -c 'import torch,numpy,pandas,scipy,sklearn,pyarrow; assert torch.cuda.is_available()' >/dev/null 2>&1; then
            gpu_python="$candidate"
            break
        fi
    done
fi
if [[ -z "$gpu_python" ]]; then
    echo "No CUDA-capable frozen mobility Python was found." >&2
    exit 66
fi

prepare_period() {
    local period_id="$1"
    local shared="$base/PFR_${period_id}_SHARED_EXOGENOUS_V13_13"
    mkdir -p "$shared/power_price"
    while IFS= read -r start; do
        if ! "$python_bin" "$power_generator" \
            --repo "$repo_dir" --output-root "$shared/power_price" \
            --candidate-id "$period_id" --start-index "$start" --scored-count 2304; then
            return 1
        fi
    done < <("$python_bin" -c 'import json,sys; c=json.load(open(sys.argv[1])); p=next(x for x in c["periods"] if x["period_id"]==sys.argv[2]); [print(x) for x in p["power_generation_starts"]]' "$contract" "$period_id")

    while IFS= read -r start; do
        root="$base/PFR_V13_13_FULL_MONTH_SOURCE_CHUNKS/$period_id/$start/mobility"
        mkdir -p "$root"
        if ! "$python_bin" -c 'import json,sys; x=json.load(open(sys.argv[1])); assert x["status"]=="PASS" and x["scored_issue_count"]==2304 and x["padding_issue_count"]==0' "$root/REP_WEEK_MOBILITY_FULL_AUTHORITY.json" >/dev/null 2>&1; then
            "$gpu_python" "$mobility_generator" --repo "$repo_dir" \
                --output-root "$root" --candidate-id "${period_id}_SOURCE_$start" \
                --start-index "$start" --scored-count 2304 --phase traffic --cpu-workers 4 || return 1
            "$gpu_python" "$mobility_generator" --repo "$repo_dir" \
                --output-root "$root" --candidate-id "${period_id}_SOURCE_$start" \
                --start-index "$start" --scored-count 2304 --phase full --cpu-workers 4 || return 1
        fi
    done < <("$python_bin" -c 'import json,sys; c=json.load(open(sys.argv[1])); p=next(x for x in c["periods"] if x["period_id"]==sys.argv[2]); [print(x["start"]) for x in p["mobility_generation_chunks"]]' "$contract" "$period_id")
    source_view_command "$period_id" "$shared"
}

overall=0
if ! prepare_period FEB2025_FULL; then overall=1; fi
if ! prepare_period MAR2025_FULL; then overall=1; fi
exit "$overall"

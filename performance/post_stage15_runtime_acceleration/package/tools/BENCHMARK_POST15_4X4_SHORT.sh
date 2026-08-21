#!/usr/bin/env bash
set -Eeuo pipefail
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
PY="/home/jaewon/miniconda3/envs/power_v61/bin/python"
REPO="/home/jaewon/mobile_ess_work/post_stage15_runtime_acceleration"
OUT="${1:?usage: BENCHMARK_POST15_4X4_SHORT.sh NEW_OUTPUT_DIRECTORY [ISSUES_PER_POLICY]}"
ISSUES="${2:-1}"
if [[ ! "$ISSUES" =~ ^[1-9][0-9]*$ ]] || (( ISSUES > 54 )); then
  echo "FAIL_CLOSED: ISSUES_PER_POLICY must be an integer in [1,54]" >&2
  exit 2
fi
if [[ -e "$OUT" ]]; then
  echo "FAIL_CLOSED: output already exists: $OUT" >&2
  exit 2
fi
mkdir -p "$OUT/logs"
export PYTHONHASHSEED=0 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
mapfile -t groups < <($PY "$HERE/tools/CPU_AFFINITY_4X4.py" --plain)
slots=(M1_PROPOSED M2_FIXED30 M3_EVENT_NO_REPAIR M4_FIXED_LOCATION)
configs=(
  "$HERE/configs/P1_PROPOSED_EVENT30_LOCAL_REPAIR.json"
  "$HERE/configs/P2_FIXED30.json"
  "$HERE/configs/P3_EVENT30_NO_LOCAL_REPAIR.json"
  "$HERE/configs/M4_FIXED_LOCATION_ESS_MOBILITY_ABLATION.json"
)
SECONDS=0
pids=()
for idx in 0 1 2 3; do
  mkdir -p "$OUT/${slots[$idx]}"
  taskset -c "${groups[$idx]}" "$PY" -u "$HERE/runtime/W02_POLICY_EPISODE_RUNNER.py" \
    --repo "$REPO" --config "${configs[$idx]}" --output "$OUT/${slots[$idx]}" --benchmark-issues "$ISSUES" \
    >"$OUT/logs/${slots[$idx]}.log" 2>&1 &
  pids+=("$!")
done
status=0
for pid in "${pids[@]}"; do
  if ! wait "$pid"; then status=2; fi
done
elapsed=$SECONDS
printf '{"status":"%s","wall_seconds":%d,"outer_processes":4,"threads_per_process":4,"python_hash_seed":"0","issues_per_process":%d}\n' \
  "$([[ $status == 0 ]] && echo PASS || echo FAIL)" "$elapsed" "$ISSUES" >"$OUT/FOUR_PROCESS_WALL.json"
echo "FOUR_PROCESS_WALL_SECONDS=$elapsed"
exit "$status"

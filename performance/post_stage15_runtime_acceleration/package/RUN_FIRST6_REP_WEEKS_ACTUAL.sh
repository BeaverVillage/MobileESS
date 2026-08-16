#!/usr/bin/env bash
set -Eeuo pipefail
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PY="/home/jaewon/miniconda3/envs/power_v61/bin/python"
REPO="/home/jaewon/mobile_ess_work/post_stage15_runtime_acceleration"
DELIVERY="/home/jaewon/mobile_ess_work/frozen_artifacts/B_FIRST6_REP_WEEKS_ACTUAL_CURRENT"
LOGROOT="/home/jaewon/mobile_ess_work/logs/B_FIRST6_REP_WEEKS_ACTUAL_CURRENT"
mkdir -p "$DELIVERY" "$LOGROOT"
exec 9>"$DELIVERY/.FIRST6_RUN.lock"
flock -n 9 || { echo "FAIL_CLOSED: another first-six launcher is active" >&2; exit 2; }
export PYTHONHASHSEED=0 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1

mapfile -t groups < <($PY "$HERE/tools/CPU_AFFINITY_4X4.py" --plain)
[[ ${#groups[@]} -eq 4 ]] || { echo "FAIL_CLOSED: CPU 4x4 topology unavailable" >&2; exit 2; }
$PY "$HERE/tools/PREFLIGHT_W02_4POLICY.py" --repo "$REPO"
$PY "$HERE/tools/PREFLIGHT_FIRST6_REP_WEEKS.py" --repo "$REPO"

weeks=(W02_2025-01-13 W07_2025-02-17 W10_2025-03-10 W17_2025-04-28 W18_2025-05-05 W25_2025-06-23)
starts=(3456 13536 19584 33696 35712 49824)
slots=(M1_PROPOSED_EVENT30_LOCAL_REPAIR_MOBILE M2_FIXED30_MOBILE M3_EVENT30_NO_LOCAL_REPAIR_MOBILE M4_FIXED_LOCATION_ESS_MOBILITY_ABLATION)
configs=(
 "$HERE/configs/P1_PROPOSED_EVENT30_LOCAL_REPAIR.json"
 "$HERE/configs/P2_FIXED30.json"
 "$HERE/configs/P3_EVENT30_NO_LOCAL_REPAIR.json"
 "$HERE/configs/M4_FIXED_LOCATION_ESS_MOBILITY_ABLATION.json"
)
active_pids=()
cleanup() {
  if (( ${#active_pids[@]} )); then kill "${active_pids[@]}" 2>/dev/null || true; wait "${active_pids[@]}" 2>/dev/null || true; fi
}
trap cleanup INT TERM

for wi in 0 1 2 3 4 5; do
  week="${weeks[$wi]}"; start="${starts[$wi]}"; weekroot="$DELIVERY/$week"; weeklog="$LOGROOT/$week"
  mkdir -p "$weekroot" "$weeklog"
  if [[ -f "$weekroot/WEEK_STATUS.json" ]] && grep -q '"status":"PASS"' "$weekroot/WEEK_STATUS.json"; then
    echo "[FIRST6] skip completed $week"; continue
  fi
  echo "[FIRST6] prepare/reuse source $week start=$start"
  bash "$HERE/scripts/PREPARE_REP_WEEK_SHARED_SOURCES.sh" "$week" "$start" "$REPO"
  if [[ "$week" == "W02_2025-01-13" ]]; then shared="/home/jaewon/mobile_ess_work/frozen_artifacts/B_W02_SHARED_EXOGENOUS_SOURCE_CURRENT";
  else shared="/home/jaewon/mobile_ess_work/frozen_artifacts/B_${week}_SHARED_EXOGENOUS_SOURCE_CURRENT"; fi
  active_pids=()
  for mi in 0 1 2 3; do
    out="$weekroot/${slots[$mi]}"; mkdir -p "$out"
    taskset -c "${groups[$mi]}" "$PY" -u "$HERE/runtime/W02_POLICY_EPISODE_RUNNER.py" \
      --repo "$REPO" --config "${configs[$mi]}" --output "$out" --candidate-id "$week" --shared-root "$shared" \
      >"$weeklog/${slots[$mi]}.log" 2>&1 &
    active_pids+=("$!")
  done
  failed=0
  for pid in "${active_pids[@]}"; do if ! wait "$pid"; then failed=1; fi; done
  active_pids=()
  (( failed == 0 )) || { echo "[FIRST6] FAIL $week; partial results preserved" >&2; exit 2; }
  "$PY" "$HERE/authority/D/tools/validate_B_W02_4POLICY_delivery_structure.py" \
    --delivery-root "$weekroot" --candidate-id "$week" --start-index "$start" >"$weeklog/STRUCTURE_VALIDATION.json"
  printf '{"status":"PASS","candidate_id":"%s","start_index":%s,"methods":4,"issues_per_method":2016}\n' "$week" "$start" >"$weekroot/WEEK_STATUS.json"
  echo "[FIRST6] PASS $week"
done
trap - INT TERM
echo "FIRST6_REP_WEEKS_STATUS=PASS"
echo "FIRST6_DELIVERY_ROOT=$DELIVERY"
echo "FIRST6_LOG_ROOT=$LOGROOT"

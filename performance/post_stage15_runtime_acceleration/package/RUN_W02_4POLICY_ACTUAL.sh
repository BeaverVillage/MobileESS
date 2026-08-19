#!/usr/bin/env bash
set -Eeuo pipefail
PREFLIGHT_ONLY=0
if [[ "${1:-}" == "--preflight-only" ]]; then PREFLIGHT_ONLY=1; shift; fi
[[ $# -eq 0 ]] || { echo "usage: bash RUN_W02_4POLICY_ACTUAL.sh [--preflight-only]" >&2; exit 2; }
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PY="/home/jaewon/miniconda3/envs/power_v61/bin/python"
BASE="/home/jaewon/mobile_ess_work"
WORKTREE="$BASE/post_stage15_runtime_acceleration"
RUN_ID="B_W02_4POLICY_ACTUAL_FINAL_R20"
DELIVERY="$BASE/frozen_artifacts/$RUN_ID"
LOGROOT="$BASE/logs/$RUN_ID"
export PYTHONHASHSEED=0
AUTH="$HERE/authority/PRE_W02_FINAL_RELEASE_AUTHORIZATION.json"
[[ -f "$AUTH" ]] || { echo "BLOCKED: PRE_W02 final release authorization is missing" >&2; exit 2; }
"$PY" - "$AUTH" <<'PY'
import json,sys
d=json.load(open(sys.argv[1],encoding="utf-8"))
if d.get("status")!="AUTHORIZED_FOR_W02" or d.get("full_w02_executed") is not False:
    raise SystemExit("BLOCKED: PRE_W02 authorization is not PASS")
PY
echo "[A→B 10] use frozen post-Stage15 scientific worktree"
echo "WORKTREE=$WORKTREE"

echo "[A→B 10] static preflight"
$PY "$HERE/tools/PREFLIGHT_W02_4POLICY.py" --repo "$WORKTREE"

echo "[A→B 10] prepare/reuse one shared W02 exogenous realization"
bash "$HERE/scripts/PREPARE_W02_SHARED_SOURCES.sh"

echo "[A→B 10] post-source preflight"
$PY "$HERE/tools/PREFLIGHT_W02_4POLICY.py" --repo "$WORKTREE" --require-shared-source

if (( PREFLIGHT_ONLY )); then
  echo "W02_4POLICY_PREFLIGHT_ONLY_STATUS=PASS"
  exit 0
fi

echo "[A→B 10] bind immutable W02 execution source"
"$PY" "$HERE/tools/BIND_W02_RUN_SOURCE.py" --package "$HERE" --repo "$WORKTREE" \
  --delivery-root "$DELIVERY" --run-id "$RUN_ID"
mkdir -p "$LOGROOT"

mapfile -t groups < <($PY "$HERE/tools/CPU_AFFINITY_4X4.py" --plain)
if (( ${#groups[@]} != 4 )); then
  echo "FAIL_CLOSED: topology-aware CPU group generation failed" >&2
  exit 2
fi
printf '[A→B 10] CPU groups: M1=%s M2=%s M3=%s M4=%s\n' "${groups[@]}"

slots=(
 "M1_PROPOSED_EVENT30_LOCAL_REPAIR_MOBILE"
 "M2_FIXED30_MOBILE"
 "M3_EVENT30_NO_LOCAL_REPAIR_MOBILE"
 "M4_FIXED_LOCATION_ESS_MOBILITY_ABLATION"
)
configs=(
 "$HERE/configs/P1_PROPOSED_EVENT30_LOCAL_REPAIR.json"
 "$HERE/configs/P2_FIXED30.json"
 "$HERE/configs/P3_EVENT30_NO_LOCAL_REPAIR.json"
 "$HERE/configs/M4_FIXED_LOCATION_ESS_MOBILITY_ABLATION.json"
)

pids=()
active_pids=()
declare -A pid_slot pid_out
stop_children() {
  local rc="$1"
  trap - INT TERM
  echo "[A→B 10] interrupt received; forwarding SIGINT to W02 policy workers" >&2
  local pid
  for pid in "${active_pids[@]}"; do
    kill -INT "$pid" 2>/dev/null || true
  done
  for pid in "${active_pids[@]}"; do
    wait "$pid" 2>/dev/null || true
  done
  echo "W02_4POLICY_STATUS=INTERRUPTED_RESUMABLE" >&2
  exit "$rc"
}
trap 'stop_children 130' INT
trap 'stop_children 143' TERM

for idx in 0 1 2 3; do
  slot="${slots[$idx]}"; cfg="${configs[$idx]}"; cpuset="${groups[$idx]}"
  out="$DELIVERY/$slot"; log="$LOGROOT/${slot}.log"
  mkdir -p "$out"
  echo "[A→B 10] launch $slot cpus=$cpuset"
  (
    export PYTHONHASHSEED=0 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
    export GUROBI_NUM_THREADS=4
    exec taskset -c "$cpuset" "$PY" -u "$HERE/runtime/W02_POLICY_EPISODE_RUNNER.py" \
      --repo "$WORKTREE" --config "$cfg" --output "$out"
  ) >"$log" 2>&1 &
  pid="$!";pids+=("$pid");active_pids+=("$pid")
  pid_slot["$pid"]="$slot";pid_out["$pid"]="$out"
  echo "$pid" > "$out/POLICY_PID.txt"
  printf '%s\n' "$cpuset" > "$out/CPU_AFFINITY.txt"
  printf '%s W02_barrier_worker cpus=%s fixed_threads=4\n' "$(date -Iseconds)" "$cpuset" > "$out/WORKER_ASSIGNMENT.log"
done

overall=0
while (( ${#active_pids[@]} )); do
  done_pid=""
  if wait -n -p done_pid "${active_pids[@]}"; then rc=0; else rc=$?; fi
  next_active=()
  for pid in "${active_pids[@]}"; do [[ "$pid" == "$done_pid" ]] || next_active+=("$pid"); done
  active_pids=("${next_active[@]}")
  if (( rc != 0 )); then
    overall=2
    echo "[A→B 10] FAIL ${pid_slot[$done_pid]} rc=$rc; interrupting peers with resumable checkpoints" >&2
    for pid in "${active_pids[@]}"; do kill -INT "$pid" 2>/dev/null || true; done
    for pid in "${active_pids[@]}"; do wait "$pid" 2>/dev/null || true; done
    active_pids=()
    break
  fi
  echo "[A→B 10] PASS ${pid_slot[$done_pid]}"
done

echo "[A→B 10] D structure validation"
if ! "$PY" "$HERE/authority/D/tools/validate_B_W02_4POLICY_delivery_structure.py" --delivery-root "$DELIVERY" \
  | tee "$LOGROOT/D_STRUCTURE_VALIDATION.log"; then
  overall=2
fi

if (( overall == 0 )); then
  echo "[A→B 10] build B→D W02 handoff"
  bash "$HERE/authority/D/tools/build_B_TO_D_W02_handoff.sh" "$DELIVERY" | tee "$LOGROOT/B_TO_D_BUILD.log"
  echo "W02_4POLICY_STATUS=PASS"
else
  echo "W02_4POLICY_STATUS=INCOMPLETE_OR_FAIL_CLOSED_RESUMABLE"
fi

echo "W02_DELIVERY_ROOT=$DELIVERY"
echo "W02_LOG_ROOT=$LOGROOT"
exit "$overall"

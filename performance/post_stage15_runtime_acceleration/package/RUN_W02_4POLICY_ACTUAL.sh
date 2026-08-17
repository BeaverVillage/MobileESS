#!/usr/bin/env bash
set -Eeuo pipefail
PREFLIGHT_ONLY=0
if [[ "${1:-}" == "--preflight-only" ]]; then PREFLIGHT_ONLY=1; shift; fi
[[ $# -eq 0 ]] || { echo "usage: bash RUN_W02_4POLICY_ACTUAL.sh [--preflight-only]" >&2; exit 2; }
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PY="/home/jaewon/miniconda3/envs/power_v61/bin/python"
BASE="/home/jaewon/mobile_ess_work"
WORKTREE="$BASE/post_stage15_runtime_acceleration"
DELIVERY="$BASE/frozen_artifacts/B_W02_4POLICY_ACTUAL_PILOT_CURRENT"
LOGROOT="$BASE/logs/B_W02_4POLICY_ACTUAL_PILOT_CURRENT"
export PYTHONHASHSEED=0
AUTH="$HERE/authority/PRE_W02_FINAL_RELEASE_AUTHORIZATION.json"
[[ -f "$AUTH" ]] || { echo "BLOCKED: PRE_W02 final release authorization is missing" >&2; exit 2; }
"$PY" - "$AUTH" <<'PY'
import json,sys
d=json.load(open(sys.argv[1],encoding="utf-8"))
if d.get("status")!="AUTHORIZED_FOR_W02" or d.get("full_w02_executed") is not False:
    raise SystemExit("BLOCKED: PRE_W02 authorization is not PASS")
PY
mkdir -p "$DELIVERY" "$LOGROOT"

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
  pids+=("$!")
  echo "$!" > "$out/POLICY_PID.txt"
  printf '%s\n' "$cpuset" > "$out/CPU_AFFINITY.txt"
done

overall=0
for idx in 0 1 2 3; do
  pid="${pids[$idx]}";slot="${slots[$idx]}"
  if wait "$pid"; then
    echo "[A→B 10] PASS $slot"
  else
    rc=$?;overall=2
    echo "[A→B 10] FAIL $slot rc=$rc; partial results preserved" >&2
  fi
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

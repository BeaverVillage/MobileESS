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
AUTH="$HERE/authority/PRE_W02_FINAL_RELEASE_AUTHORIZATION.json"
[[ -f "$AUTH" ]] || { echo "BLOCKED: PRE_W02 final release authorization is missing" >&2; exit 2; }
"$PY" - "$AUTH" <<'PY'
import json,sys
d=json.load(open(sys.argv[1],encoding="utf-8"))
if d.get("status")!="AUTHORIZED_FOR_W02" or d.get("full_w02_executed") is not False:
    raise SystemExit("BLOCKED: PRE_W02 authorization is not PASS")
PY

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
  if (( wi == 0 )); then
    token="$weekroot/W02_ACCEPTANCE_TOKEN.json"
    if [[ ! -f "$token" ]]; then
      echo "[FIRST6] W02 complete; waiting for external scientific/result acceptance token. W07 was not started."
      echo "FIRST6_STATUS=WAITING_W02_ACCEPTANCE"
      echo "W02_ACCEPTANCE_TOKEN_REQUIRED=$token"
      exit 0
    fi
    "$PY" - "$token" "$weekroot/WEEK_STATUS.json" <<'PY'
import hashlib,json,sys
token_path,status_path=sys.argv[1:]
token=json.load(open(token_path,encoding="utf-8")); status=json.load(open(status_path,encoding="utf-8"))
digest=hashlib.sha256(open(status_path,"rb").read()).hexdigest()
ok=(token.get("status")=="ACCEPTED_FOR_REMAINING_WEEKS"
    and token.get("candidate_id")=="W02_2025-01-13"
    and token.get("w02_week_status_sha256")==digest
    and token.get("outcome_blind_protocol_audit") is True
    and token.get("technical_integrity_pass") is True)
if not ok: raise SystemExit("FAIL_CLOSED: invalid W02 acceptance token")
PY
    echo "[FIRST6] W02 external acceptance token PASS; W07 is now authorized"
  fi
done
trap - INT TERM
echo "FIRST6_REP_WEEKS_STATUS=PASS"
echo "FIRST6_DELIVERY_ROOT=$DELIVERY"
echo "FIRST6_LOG_ROOT=$LOGROOT"

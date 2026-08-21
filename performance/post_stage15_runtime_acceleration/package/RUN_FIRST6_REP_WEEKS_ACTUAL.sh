#!/usr/bin/env bash
set -Eeuo pipefail
PREFLIGHT_ONLY=0
if [[ "${1:-}" == "--preflight-only" ]]; then PREFLIGHT_ONLY=1;shift;fi
[[ $# -eq 0 ]] || { echo "usage: bash RUN_12_REP_WEEKS_ACTUAL.sh [--preflight-only]" >&2;exit 2; }
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PY="/home/jaewon/miniconda3/envs/power_v61/bin/python"
REPO="/home/jaewon/mobile_ess_work/post_stage15_runtime_acceleration"
DELIVERY="/home/jaewon/mobile_ess_work/frozen_artifacts/B_12_REP_WEEKS_ACTUAL_FINAL_R20"
LOGROOT="/home/jaewon/mobile_ess_work/logs/B_12_REP_WEEKS_ACTUAL_FINAL_R20"
mkdir -p "$DELIVERY" "$LOGROOT"
exec 9>"$DELIVERY/.REP12_RUN.lock"
flock -n 9 || { echo "FAIL_CLOSED: another 12-week launcher is active" >&2; exit 2; }
export PYTHONHASHSEED=0 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1

mapfile -t groups < <($PY "$HERE/tools/CPU_AFFINITY_4X4.py" --plain)
[[ ${#groups[@]} -eq 4 ]] || { echo "FAIL_CLOSED: CPU 4x4 topology unavailable" >&2; exit 2; }
$PY "$HERE/tools/PREFLIGHT_W02_4POLICY.py" --repo "$REPO"
$PY "$HERE/tools/PREFLIGHT_12_REP_WEEKS.py" --repo "$REPO"
$PY "$HERE/tools/VALIDATE_REP12_GLOBAL_QUEUE.py" --package "$HERE"
if (( PREFLIGHT_ONLY )); then echo "REP12_PREFLIGHT_ONLY_STATUS=PASS";exit 0;fi

$PY - "$HERE" "$DELIVERY/REP12_RUN_SOURCE_AUTHORITY.json" <<'PY'
import hashlib,json,sys
from datetime import datetime,timezone
from pathlib import Path
here,authority=map(Path,sys.argv[1:])
runner=here/'runtime/W02_POLICY_EPISODE_RUNNER.py'
runner_sha=hashlib.sha256(runner.read_bytes()).hexdigest()
launcher=here/'RUN_FIRST6_REP_WEEKS_ACTUAL.sh'
launcher_sha=hashlib.sha256(launcher.read_bytes()).hexdigest()
weeks=['W02_2025-01-13','W07_2025-02-17','W10_2025-03-10','W17_2025-04-28',
       'W18_2025-05-05','W25_2025-06-23','W26_2025-06-30','W32_2025-08-11',
       'W38_2025-09-22','W41_2025-10-13','W44_2025-11-03','W51_2025-12-22']
payload={'schema_version':'mobileess.rep12.run_source_authority.v2','status':'FROZEN_BEFORE_FIRST_EPISODE',
         'run_id':'B_12_REP_WEEKS_ACTUAL_FINAL_R20','runner_sha256':runner_sha,
         'launcher_sha256':launcher_sha,'representative_weeks':weeks,'episode_count':48,
         'w02_preacceptance_barrier':False,'same_source_resume_only':True,
         'created_utc':datetime.now(timezone.utc).isoformat()}
if authority.is_file():
    old=json.loads(authority.read_text())
    for key in ('run_id','runner_sha256','launcher_sha256','representative_weeks','episode_count','w02_preacceptance_barrier'):
        if old.get(key)!=payload.get(key):raise SystemExit('FAIL_CLOSED: 12-week source binding drift')
else:
    tmp=authority.with_suffix('.json.tmp');tmp.write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n');tmp.replace(authority)
PY

weeks=(W02_2025-01-13 W07_2025-02-17 W10_2025-03-10 W17_2025-04-28 W18_2025-05-05 W25_2025-06-23 W26_2025-06-30 W32_2025-08-11 W38_2025-09-22 W41_2025-10-13 W44_2025-11-03 W51_2025-12-22)
starts=(3456 13536 19584 33696 35712 49824 51840 63936 76032 82080 88128 102240)
slots=(M1_PROPOSED_EVENT30_LOCAL_REPAIR_MOBILE M2_FIXED30_MOBILE M3_EVENT30_NO_LOCAL_REPAIR_MOBILE M4_FIXED_LOCATION_ESS_MOBILITY_ABLATION)
configs=(
 "$HERE/configs/P1_PROPOSED_EVENT30_LOCAL_REPAIR.json"
 "$HERE/configs/P2_FIXED30.json"
 "$HERE/configs/P3_EVENT30_NO_LOCAL_REPAIR.json"
 "$HERE/configs/M4_FIXED_LOCATION_ESS_MOBILITY_ABLATION.json"
)
active_pids=()
idle_workers=()
declare -A pid_kind pid_week pid_method pid_worker pid_out prepared_week preparing_week week_done week_start week_finalize_failed
queue_week=();queue_method=();queue_cursor=0
session_id="$(date -u +%Y%m%dT%H%M%SZ)-$$"
failure_log="$LOGROOT/FAILED_TASKS_${session_id}.jsonl"
campaign_summary="$LOGROOT/CAMPAIGN_SUMMARY_${session_id}.json"
failure_count=0
failed_episode_count=0
failed_source_count=0
blocked_episode_count=0
: >"$failure_log"

cleanup() {
  local pid
  trap - INT TERM
  for pid in "${active_pids[@]}"; do kill -TERM -- "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true; done
  for pid in "${active_pids[@]}"; do wait "$pid" 2>/dev/null || true; done
}
interrupt_run() {
  local rc="$1" signal_name="$2"
  echo "[REP12] $signal_name received; stopping every active task resumably" >&2
  cleanup
  echo "REP12_STATUS=INTERRUPTED_RESUMABLE" >&2
  exit "$rc"
}
trap 'interrupt_run 130 SIGINT' INT
trap 'interrupt_run 143 SIGTERM' TERM

record_task_failure() {
  local kind="$1" week="$2" mi="$3" worker="$4" rc="$5" action="$6" output="$7" slot
  if [[ "$mi" =~ ^[0-3]$ ]]; then slot="${slots[$mi]}";else slot="SOURCE_PREPARATION";fi
  failure_count=$((failure_count+1))
  "$PY" - "$failure_log" "$kind" "$week" "$slot" "$worker" "$rc" "$action" "$output" <<'PY'
import json,sys
from datetime import datetime,timezone
from pathlib import Path
path=Path(sys.argv[1])
row={"timestamp_utc":datetime.now(timezone.utc).isoformat(),"kind":sys.argv[2],
     "week":sys.argv[3],"policy":sys.argv[4],"worker":int(sys.argv[5]),
     "return_code":int(sys.argv[6]),"action":sys.argv[7],"output":sys.argv[8]}
with path.open("a",encoding="utf-8") as f:f.write(json.dumps(row,sort_keys=True)+"\n")
PY
}

skip_failed_source_week() {
  local week="$1" worker="$2" rc="$3" mi output
  failed_source_count=$((failed_source_count+1))
  preparing_week["$week"]=0
  record_task_failure "source" "$week" -1 "$worker" "$rc" \
    "SKIP_BLOCKED_WEEK_AND_CONTINUE_GLOBAL_QUEUE" "$(shared_root_for_week "$week")"
  while (( queue_cursor < ${#queue_week[@]} )) && [[ "${queue_week[$queue_cursor]}" == "$week" ]]; do
    mi="${queue_method[$queue_cursor]}";output="$DELIVERY/$week/${slots[$mi]}"
    blocked_episode_count=$((blocked_episode_count+1))
    record_task_failure "episode_blocked_by_source" "$week" "$mi" "$worker" 91 \
      "NOT_STARTED_CONTINUE_GLOBAL_QUEUE" "$output"
    queue_cursor=$((queue_cursor+1))
  done
}

finalize_week_if_complete() {
  local week="$1" start="${week_start[$1]}" weekroot="$DELIVERY/$1" weeklog="$LOGROOT/$1"
  (( ${week_done[$week]:-0} == 4 )) || return 0
  [[ -f "$weekroot/WEEK_STATUS.json" ]] && grep -q '"status":"PASS"' "$weekroot/WEEK_STATUS.json" && return 0
  if ! "$PY" "$HERE/authority/D/tools/validate_B_W02_4POLICY_delivery_structure.py" \
    --delivery-root "$weekroot" --candidate-id "$week" --start-index "$start" >"$weeklog/STRUCTURE_VALIDATION.json"; then
    return 2
  fi
  printf '{"status":"PASS","candidate_id":"%s","start_index":%s,"methods":4,"issues_per_method":2016}\n' \
    "$week" "$start" >"$weekroot/WEEK_STATUS.json"
  echo "[REP12] PASS complete week $week"
}

attempt_finalize_week() {
  local week="$1" worker="${2:--1}"
  [[ "${week_finalize_failed[$week]:-0}" != 1 ]] || return 0
  if ! finalize_week_if_complete "$week"; then
    week_finalize_failed["$week"]=1
    echo "[REP12] ISOLATED_FAIL kind=week_validation $week; continue global queue" >&2
    record_task_failure "week_validation" "$week" -1 "$worker" 92 \
      "WEEK_PASS_BLOCKED_CONTINUE_GLOBAL_QUEUE" "$LOGROOT/$week/STRUCTURE_VALIDATION.json"
  fi
}

shared_root_for_week() {
  local week="$1"
  if [[ "$week" == "W02_2025-01-13" ]]; then
    printf '%s\n' "/home/jaewon/mobile_ess_work/frozen_artifacts/B_W02_SHARED_EXOGENOUS_SOURCE_CURRENT"
  else
    printf '%s\n' "/home/jaewon/mobile_ess_work/frozen_artifacts/B_${week}_SHARED_EXOGENOUS_SOURCE_CURRENT"
  fi
}

source_ready() {
  local shared
  shared="$(shared_root_for_week "$1")"
  [[ -f "$shared/SHARED_EXOGENOUS_AUTHORITY.json" ]] || return 1
  "$PY" -c 'import json,sys; raise SystemExit(0 if json.load(open(sys.argv[1])).get("status")=="PASS" else 1)' \
    "$shared/SHARED_EXOGENOUS_AUTHORITY.json"
}

mark_worker_idle() {
  local worker="$1" existing
  for existing in "${idle_workers[@]}"; do [[ "$existing" == "$worker" ]] && return 0; done
  idle_workers+=("$worker")
  echo "[REP12] worker=$worker waiting only for shared-source prerequisite"
}

launch_next_episode() {
  local worker="$1" week mi slot cpuset out weeklog shared pid
  (( queue_cursor < ${#queue_week[@]} )) || return 1
  week="${queue_week[$queue_cursor]}";mi="${queue_method[$queue_cursor]}"
  slot="${slots[$mi]}";cpuset="${groups[$worker]}";out="$DELIVERY/$week/$slot";weeklog="$LOGROOT/$week"
  mkdir -p "$out" "$weeklog"
  if [[ "${prepared_week[$week]:-0}" != 1 ]]; then
    if source_ready "$week"; then
      prepared_week["$week"]=1
    elif [[ "${preparing_week[$week]:-0}" == 1 ]]; then
      return 2
    else
      preparing_week["$week"]=1
      echo "[REP12] worker=$worker prepare source $week start=${week_start[$week]}"
      if [[ "$week" == "W02_2025-01-13" ]]; then
        setsid bash "$HERE/scripts/PREPARE_W02_SHARED_SOURCES.sh" >"$weeklog/SHARED_SOURCE_PREP.log" 2>&1 &
      else
        setsid bash "$HERE/scripts/PREPARE_REP_WEEK_SHARED_SOURCES.sh" "$week" "${week_start[$week]}" "$REPO" \
          >"$weeklog/SHARED_SOURCE_PREP.log" 2>&1 &
      fi
      pid="$!";active_pids+=("$pid")
      pid_kind["$pid"]="source";pid_week["$pid"]="$week";pid_method["$pid"]="$mi"
      pid_worker["$pid"]="$worker";pid_out["$pid"]="$(shared_root_for_week "$week")"
      return 0
    fi
  fi
  queue_cursor=$((queue_cursor+1));shared="$(shared_root_for_week "$week")"
  echo "[REP12] worker=$worker launch $week $slot cpus=$cpuset queue=$queue_cursor/${#queue_week[@]}"
  setsid taskset -c "$cpuset" "$PY" -u "$HERE/runtime/W02_POLICY_EPISODE_RUNNER.py" \
    --repo "$REPO" --config "${configs[$mi]}" --output "$out" --candidate-id "$week" --shared-root "$shared" \
    >"$weeklog/$slot.log" 2>&1 &
  pid="$!";active_pids+=("$pid")
  pid_kind["$pid"]="episode";pid_week["$pid"]="$week";pid_method["$pid"]="$mi"
  pid_worker["$pid"]="$worker";pid_out["$pid"]="$out"
  printf '%s\n' "$pid" >"$out/POLICY_PID.txt";printf '%s\n' "$cpuset" >"$out/CPU_AFFINITY.txt"
  printf '%s worker=%s cpus=%s fixed_threads=4\n' "$(date -Iseconds)" "$worker" "$cpuset" >"$out/WORKER_ASSIGNMENT.log"
}

dispatch_worker() {
  local worker="$1" rc
  if launch_next_episode "$worker"; then return 0; else rc=$?; fi
  if (( rc == 2 )); then mark_worker_idle "$worker";fi
  return 0
}

dispatch_prerequisite_waiters() {
  local waiting=("${idle_workers[@]}") worker
  idle_workers=()
  for worker in "${waiting[@]}"; do dispatch_worker "$worker"; done
}

# Build one global FIFO queue for all 12 weeks x 4 policies. There is no W02
# pre-acceptance barrier: four fixed 4-CPU workers continuously take the next
# not-yet-complete episode, and final PASS exists only after all 48 episodes and
# all twelve per-week structure validations pass.
for wi in {0..11}; do
  week="${weeks[$wi]}";week_start["$week"]="${starts[$wi]}";week_done["$week"]=0
  weekroot="$DELIVERY/$week";weeklog="$LOGROOT/$week";mkdir -p "$weekroot" "$weeklog"
  if [[ -f "$weekroot/WEEK_STATUS.json" ]] && grep -q '"status":"PASS"' "$weekroot/WEEK_STATUS.json"; then
    week_done["$week"]=4;echo "[REP12] skip completed week $week";continue
  fi
  for mi in 0 1 2 3; do
    out="$weekroot/${slots[$mi]}"
    if [[ -f "$out/RUNTIME_CHARACTERIZATION.json" ]]; then
      week_done["$week"]=$(( ${week_done[$week]}+1 ))
    else
      queue_week+=("$week");queue_method+=("$mi")
    fi
  done
  attempt_finalize_week "$week"
done

for worker in 0 1 2 3; do dispatch_worker "$worker"; done
while (( ${#active_pids[@]} )); do
  done_pid=""
  if wait -n -p done_pid "${active_pids[@]}"; then rc=0; else rc=$?; fi
  # bash unsets the -p destination when wait is interrupted before it can
  # reap a child.  With nounset enabled, indexing the PID maps below then used
  # to raise an unrelated "done_pid: unbound variable" during Ctrl+C cleanup.
  # Treat that race as a resumable campaign interruption and never mutate the
  # worker queue without a positively identified completed child.
  if [[ -z "${done_pid:-}" ]]; then
    echo "[REP12] wait interrupted rc=$rc; stopping every active task resumably" >&2
    cleanup
    echo "REP12_STATUS=INTERRUPTED_RESUMABLE" >&2
    exit "$rc"
  fi
  next_active=();for pid in "${active_pids[@]}"; do [[ "$pid" == "$done_pid" ]] || next_active+=("$pid");done
  active_pids=("${next_active[@]}")
  kind="${pid_kind[$done_pid]}";week="${pid_week[$done_pid]}";mi="${pid_method[$done_pid]}";worker="${pid_worker[$done_pid]}"
  if (( rc != 0 )); then
    if [[ "$kind" == "source" ]]; then
      echo "[REP12] ISOLATED_FAIL kind=source $week rc=$rc; skip blocked week and continue queue" >&2
      skip_failed_source_week "$week" "$worker" "$rc"
      dispatch_worker "$worker"
      dispatch_prerequisite_waiters
    else
      failed_episode_count=$((failed_episode_count+1))
      echo "[REP12] ISOLATED_FAIL kind=episode $week ${slots[$mi]} rc=$rc; worker=$worker takes next queued task" >&2
      record_task_failure "episode" "$week" "$mi" "$worker" "$rc" \
        "FAILED_EPISODE_NOT_RETRIED_THIS_CAMPAIGN_WORKER_CONTINUES" "${pid_out[$done_pid]}"
      dispatch_worker "$worker"
    fi
    continue
  fi
  if [[ "$kind" == "source" ]]; then
    if ! source_ready "$week"; then
      echo "[REP12] ISOLATED_FAIL source authority not PASS $week; skip blocked week and continue queue" >&2
      skip_failed_source_week "$week" "$worker" 90
      dispatch_worker "$worker"
      dispatch_prerequisite_waiters
      continue
    fi
    prepared_week["$week"]=1;preparing_week["$week"]=0
    echo "[REP12] worker=$worker PASS shared source $week"
    dispatch_worker "$worker"
    dispatch_prerequisite_waiters
    continue
  fi
  if [[ ! -f "${pid_out[$done_pid]}/RUNTIME_CHARACTERIZATION.json" ]]; then
    failed_episode_count=$((failed_episode_count+1))
    echo "[REP12] ISOLATED_FAIL kind=episode_postcondition $week ${slots[$mi]}; worker=$worker takes next queued task" >&2
    record_task_failure "episode_postcondition" "$week" "$mi" "$worker" 93 \
      "MISSING_COMPLETION_ARTIFACT_WORKER_CONTINUES" "${pid_out[$done_pid]}"
    dispatch_worker "$worker"
    continue
  fi
  week_done["$week"]=$(( ${week_done[$week]}+1 ))
  echo "[REP12] worker=$worker PASS $week ${slots[$mi]}"
  attempt_finalize_week "$week" "$worker"
  dispatch_worker "$worker"
done

incomplete_weeks=()
for wi in {0..11}; do
  week="${weeks[$wi]}"
  if [[ "${week_done[$week]:-0}" == 4 ]]; then
    attempt_finalize_week "$week"
  else
    incomplete_weeks+=("$week:${week_done[$week]:-0}/4")
  fi
done
trap - INT TERM
if (( failure_count > 0 || ${#incomplete_weeks[@]} > 0 )); then
  incomplete_csv="$(IFS=,;echo "${incomplete_weeks[*]}")"
  "$PY" - "$campaign_summary" "$failure_log" "$failure_count" "$failed_episode_count" \
    "$failed_source_count" "$blocked_episode_count" "$incomplete_csv" "$DELIVERY" <<'PY'
import json,sys
from datetime import datetime,timezone
from pathlib import Path
out=Path(sys.argv[1])
failure_count=int(sys.argv[3])
record={"schema_version":"mobileess.rep12.campaign_completion.v2",
 "status":"COMPLETE_WITH_ISOLATED_FAILURES_RESUMABLE" if failure_count else "FAIL_CLOSED_INCOMPLETE_WITHOUT_RECORDED_TASK_FAILURE",
 "completed_utc":datetime.now(timezone.utc).isoformat(),"failure_log":sys.argv[2],
 "failure_count":failure_count,"failed_episode_count":int(sys.argv[4]),
 "failed_source_count":int(sys.argv[5]),"blocked_episode_count":int(sys.argv[6]),
 "incomplete_weeks":[x for x in sys.argv[7].split(",") if x],"delivery_root":sys.argv[8],
 "other_workers_continued_after_task_failure":True,"campaign_pass":False,
 "resume_rule":"rerun same launcher; atomic committed prefixes are preserved and only incomplete episodes are queued"}
tmp=out.with_suffix(out.suffix+".tmp");tmp.write_text(json.dumps(record,indent=2,sort_keys=True)+"\n");tmp.replace(out)
PY
  echo "REP12_REP_WEEKS_STATUS=COMPLETE_WITH_ISOLATED_FAILURES_RESUMABLE" >&2
  echo "REP12_FAILURE_LOG=$failure_log" >&2
  echo "REP12_CAMPAIGN_SUMMARY=$campaign_summary" >&2
  exit 2
fi
echo "REP12_REP_WEEKS_STATUS=PASS"
echo "REP12_DELIVERY_ROOT=$DELIVERY"
echo "REP12_LOG_ROOT=$LOGROOT"

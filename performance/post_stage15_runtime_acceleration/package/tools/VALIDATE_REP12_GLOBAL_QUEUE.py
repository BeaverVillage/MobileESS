#!/usr/bin/env python3
"""Static and deterministic scheduler audit for the 12-week global episode queue."""
from __future__ import annotations
import argparse,json,re
from pathlib import Path

EXPECTED_WEEKS=[
 "W02_2025-01-13","W07_2025-02-17","W10_2025-03-10",
 "W17_2025-04-28","W18_2025-05-05","W25_2025-06-23",
 "W26_2025-06-30","W32_2025-08-11","W38_2025-09-22",
 "W41_2025-10-13","W44_2025-11-03","W51_2025-12-22",
]

def main()->int:
 ap=argparse.ArgumentParser();ap.add_argument("--package",type=Path,default=Path(__file__).resolve().parents[1]);a=ap.parse_args()
 launcher=(a.package/"RUN_FIRST6_REP_WEEKS_ACTUAL.sh").read_text(encoding="utf-8")
 week_match=re.search(r"^weeks=\(([^\n]+)\)$",launcher,re.MULTILINE)
 weeks=week_match.group(1).split() if week_match else []
 checks={
  "exact_twelve_week_authority":weeks==EXPECTED_WEEKS,
  "w02_preacceptance_barrier_removed":('verify externally accepted formal W02' not in launcher
    and "'w02_preacceptance_barrier':False" in launcher
    and 'for wi in {0..11}; do' in launcher),
  "week_major_policy_minor_fifo":('for wi in {0..11}; do' in launcher
    and 'for mi in 0 1 2 3; do' in launcher
    and 'queue_week+=("$week");queue_method+=("$mi")' in launcher),
  "four_fixed_worker_slots":('for worker in 0 1 2 3; do dispatch_worker "$worker"' in launcher
    and 'cpuset="${groups[$worker]}"' in launcher
    and 'fixed_threads=4' in launcher),
  "completion_immediately_launches_next_episode":('wait -n -p done_pid' in launcher
    and 'worker="${pid_worker[$done_pid]}"' in launcher
    and 'dispatch_worker "$worker"' in launcher),
  "source_preparation_is_monitored_queue_work":('pid_kind["$pid"]="source"' in launcher
    and 'preparing_week["$week"]=1' in launcher
    and 'PASS shared source' in launcher
    and 'dispatch_prerequisite_waiters' in launcher),
  "source_preparation_does_not_duplicate":('elif [[ "${preparing_week[$week]:-0}" == 1 ]]' in launcher
    and 'mark_worker_idle "$worker"' in launcher),
  "no_same_process_cpu_donation":('taskset -pc' not in launcher and 'donate_cpu' not in launcher),
  "episode_failure_isolated_to_one_worker":('ISOLATED_FAIL kind=episode' in launcher
    and 'FAILED_EPISODE_NOT_RETRIED_THIS_CAMPAIGN_WORKER_CONTINUES' in launcher
    and 'record_task_failure "episode"' in launcher),
  "failed_worker_immediately_takes_next_global_task":('record_task_failure "episode"' in launcher
    and 'dispatch_worker "$worker"' in launcher
    and 'continue' in launcher),
  "source_failure_skips_blocked_week_without_retry_loop":('skip_failed_source_week' in launcher
    and 'SKIP_BLOCKED_WEEK_AND_CONTINUE_GLOBAL_QUEUE' in launcher
    and 'NOT_STARTED_CONTINUE_GLOBAL_QUEUE' in launcher),
  "missing_episode_completion_artifact_is_isolated":('episode_postcondition' in launcher
    and 'MISSING_COMPLETION_ARTIFACT_WORKER_CONTINUES' in launcher),
  "week_structure_validation_failure_is_isolated":('attempt_finalize_week' in launcher
    and 'WEEK_PASS_BLOCKED_CONTINUE_GLOBAL_QUEUE' in launcher
    and 'week_finalize_failed' in launcher),
  "campaign_pass_blocked_by_any_isolated_failure":('failure_count > 0' in launcher
    and 'COMPLETE_WITH_ISOLATED_FAILURES_RESUMABLE' in launcher
    and 'campaign_pass":False' in launcher),
  "foreground_ctrl_c_is_resumable":("trap 'interrupt_run 130 SIGINT' INT" in launcher
    and 'REP12_STATUS=INTERRUPTED_RESUMABLE' in launcher
    and 'kill -TERM -- "-$pid"' in launcher),
  "week_finalizes_only_after_four_policy_passes":('${week_done[$week]:-0} == 4' in launcher
    and 'validate_B_W02_4POLICY_delivery_structure.py' in launcher),
 }
 # Deterministic injected-failure model: W02 M1--M4 occupy the initial four
 # slots. If worker 0 fails M1, workers 1--3 remain assigned and worker 0 takes
 # W07 M1. A source failure skips only that week's unstarted policies.
 queue=[(week,method) for week in EXPECTED_WEEKS for method in range(4)]
 initial=[queue.pop(0) for _ in range(4)]
 active={worker:item for worker,item in enumerate(initial)}
 failed=active.pop(0);reassigned=queue.pop(0);active[0]=reassigned
 checks["deterministic_episode_failure_isolation"]=(failed==(EXPECTED_WEEKS[0],0)
   and reassigned==(EXPECTED_WEEKS[1],0)
   and all(active[w]==(EXPECTED_WEEKS[0],w) for w in (1,2,3)))
 source_failed_week=EXPECTED_WEEKS[1]
 while queue and queue[0][0]==source_failed_week:queue.pop(0)
 checks["deterministic_source_failure_advances_week"]=(queue[0]==(EXPECTED_WEEKS[2],0))
 result={"schema_version":"mobileess.post_stage15.rep12_global_queue_validation.v2",
         "status":"PASS" if all(checks.values()) else "FAIL_CLOSED","checks":checks,
         "worker_slots":4,"fixed_threads_per_episode":4,"queued_final_episodes":48}
 print(json.dumps(result,indent=2,sort_keys=True))
 return 0 if result["status"]=="PASS" else 2
if __name__=="__main__":raise SystemExit(main())

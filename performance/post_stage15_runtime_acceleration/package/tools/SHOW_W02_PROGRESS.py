#!/usr/bin/env python3
from __future__ import annotations
import json
import re
from pathlib import Path
HERE=Path(__file__).resolve().parents[1]
BASE=Path("/home/jaewon/mobile_ess_work")
match=re.search(r'^RUN_ID="([^"]+)"$',(HERE/"RUN_W02_4POLICY_ACTUAL.sh").read_text(encoding="utf-8"),re.MULTILINE)
if match is None:raise RuntimeError("RUN_ID not found in W02 launcher")
RUN_ID=match.group(1)
ROOT=BASE/"frozen_artifacts"/RUN_ID
LOG=BASE/"logs"/RUN_ID
POLICIES=["M1_PROPOSED_EVENT30_LOCAL_REPAIR_MOBILE","M2_FIXED30_MOBILE","M3_EVENT30_NO_LOCAL_REPAIR_MOBILE","M4_FIXED_LOCATION_ESS_MOBILITY_ABLATION"]
ISSUE_MINUTES=5
REQUIRED_ISSUES=2016
ISSUES_PER_SIMULATED_DAY=24*60//ISSUE_MINUTES

def progress_fields(completed):
 if completed is None:
  return {
   "completed":None,
   "completed_issues":None,
   "required_issues":REQUIRED_ISSUES,
   "completed_over_required":None,
   "completion_percent":None,
   "completed_full_days":None,
   "completed_simulated_days":None,
   "completed_simulated_time":None,
   "remaining_issues":None,
  }
 completed=int(completed)
 total_minutes=completed*ISSUE_MINUTES
 days,day_minutes=divmod(total_minutes,24*60)
 hours,minutes=divmod(day_minutes,60)
 return {
  # Retain the original field for compatibility with existing readers.
  "completed":completed,
  "completed_issues":completed,
  "required_issues":REQUIRED_ISSUES,
  "completed_over_required":f"{completed}/{REQUIRED_ISSUES}",
  "completion_percent":round(100.0*completed/REQUIRED_ISSUES,4),
  "completed_full_days":completed//ISSUES_PER_SIMULATED_DAY,
  "completed_simulated_days":round(completed/ISSUES_PER_SIMULATED_DAY,6),
  "completed_simulated_time":f"{days}d {hours:02d}h {minutes:02d}m",
  "remaining_issues":max(0,REQUIRED_ISSUES-completed),
 }

def policy_process_alive(policy_root):
 pid_path=policy_root/"POLICY_PID.txt"
 try:pid=int(pid_path.read_text().strip())
 except (FileNotFoundError,ValueError):return False,None
 cmd_path=Path("/proc")/str(pid)/"cmdline"
 try:cmd=cmd_path.read_bytes().replace(b"\0",b" ").decode(errors="replace")
 except (FileNotFoundError,PermissionError):return False,pid
 alive=("W02_POLICY_EPISODE_RUNNER.py" in cmd and str(policy_root) in cmd)
 return alive,pid

rows=[]
for p in POLICIES:
 d=ROOT/p
 alive,pid=policy_process_alive(d)
 prog=d/"progress/W02_PROGRESS.json"
 fail=d/"FAILURE.json"
 rt=d/"RUNTIME_CHARACTERIZATION.json"
 if rt.is_file():
  x=json.loads(rt.read_text());status="PASS";completed=2016;last=5471
 elif fail.is_file():
  x=json.loads(fail.read_text());status="FAIL_CLOSED"
  if prog.is_file():
   prior=json.loads(prog.read_text());completed=prior.get("completed",0);last=prior.get("last_issue")
  else:
   markers=sorted(d.glob("engine/issue_*/A_B10_COMMIT_MARKER.json"))
   completed=len(markers);last=(int(markers[-1].parent.name.split("_")[-1]) if markers else None)
 elif prog.is_file():
  x=json.loads(prog.read_text());status=x.get("status");completed=x.get("completed");last=x.get("last_issue")
  if str(status).startswith("RUNNING") and not alive:status="RESUMABLE_STOPPED"
 else:
  status="NOT_STARTED";completed=0;last=None
 row={"policy":p,"status":status,"process_alive":alive,"pid":pid if alive else None}
 row.update(progress_fields(completed))
 row.update({"last_issue":last,"log":str(LOG/f"{p}.log")})
 rows.append(row)

completed_values=[row["completed_issues"] for row in rows]
common_completed=(min(completed_values)
                  if all(value is not None for value in completed_values)
                  else None)
total_completed=(sum(completed_values)
                 if all(value is not None for value in completed_values)
                 else None)
total_required=REQUIRED_ISSUES*len(POLICIES)
aggregate_progress={
 "completed_issues":total_completed,
 "required_issues":total_required,
 "completed_over_required":(f"{total_completed}/{total_required}"
                            if total_completed is not None else None),
 "completion_percent":(round(100.0*total_completed/total_required,4)
                       if total_completed is not None else None),
 "remaining_issues":(max(0,total_required-total_completed)
                     if total_completed is not None else None),
}
print(json.dumps({
 "delivery_root":str(ROOT),
 "progress_semantics":"One completed issue is one 5-minute simulation interval, not one day.",
 "issue_duration_minutes":ISSUE_MINUTES,
 "issues_per_simulated_day":ISSUES_PER_SIMULATED_DAY,
 "required_issues_per_policy":REQUIRED_ISSUES,
 "required_simulated_days_per_policy":7,
 "four_policy_aggregate_progress":aggregate_progress,
 "four_policy_common_progress":progress_fields(common_completed),
 "policies":rows,
},indent=2))

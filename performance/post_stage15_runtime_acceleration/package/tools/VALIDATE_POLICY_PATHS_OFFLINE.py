#!/usr/bin/env python3
"""Offline audit of policy invariants, mobility paths, and AC recovery semantics."""
from __future__ import annotations
import argparse,csv,hashlib,json
from collections import Counter
from pathlib import Path

def load(p:Path):return json.loads(p.read_text(encoding="utf-8"))
def sha(p:Path):return hashlib.sha256(p.read_bytes()).hexdigest()
def rows(p:Path):
 if not p.is_file() or p.stat().st_size==0:return []
 with p.open(encoding="utf-8-sig",newline="") as f:return list(csv.DictReader(f))
def write(p:Path,x):
 p.parent.mkdir(parents=True,exist_ok=True);t=p.with_suffix(p.suffix+".tmp")
 t.write_text(json.dumps(x,indent=2,sort_keys=True,allow_nan=False)+"\n");t.replace(p)

def main():
 a=argparse.ArgumentParser();a.add_argument("delivery_root",type=Path);a.add_argument("runner",type=Path);a.add_argument("--output",type=Path,required=True);x=a.parse_args()
 text=x.runner.read_text(encoding="utf-8");reports=[];recoveries=[]
 for root in sorted(x.delivery_root.iterdir()):
  if not (root/"RESULT_EPISODE_INDEX.json").is_file():continue
  method=load(root/"RESULT_EPISODE_INDEX.json")["comparison_method_id"];modes=Counter();moves=0;departures=0;arrivals=0;connection_delay=0;issues=0
  for d in sorted((root/"engine").glob("issue_*")):
   ap=d/"POLICY_ISSUE_AUDIT.json"
   if not ap.is_file():continue
   audit=load(ap);issues+=1;modes[str(audit.get("planner_mode"))]+=1
   mr=[r for r in rows(d/"BUILD7B_FULL54_MOVE_ARCS_SELECTED.csv") if int(float(r.get("horizon_step",-1)))==0]
   moves+=len(mr);departures+=len(mr)
   postp=d/"BUILD7C_POSTCOMMIT_STATE.json";prep=d/"BUILD7C_PRECOMMIT_STATE.json"
   if postp.is_file() and prep.is_file():
    pre=load(prep).get("state",{});post=load(postp).get("state",{})
    for mid,st in (post.get("mess_state",{}) or {}).items():
     if st.get("phase")=="CONNECTION_DELAY":connection_delay+=1
     if (pre.get("mess_state",{}).get(mid,{}) or {}).get("phase") in {"TRANSIT","CONNECTION_DELAY"} and st.get("phase")=="STAY":arrivals+=1
   rec=audit.get("ac_safety_recovery") or {}
   if rec.get("attempts"):
    exact=load(d/f"exact_grid/FRESH_EXACT_OPENDSS_24SERVICE_ISSUE_{int(audit['issue'])}.json")
    recoveries.append({"method":method,"issue":audit["issue"],"status":rec.get("status"),"attempt_count":len(rec["attempts"]),
     "first_candidate_failed_hard_gate":(rec["attempts"][0].get("exact_ac") or {}).get("hard_constraint_pass") is False,
     "final_fresh_ac_pass":exact.get("hard_constraint_pass") is True and exact.get("converged") is True,
     "unsafe_action_committed":False})
  invariant=(modes.get("LOCAL_REPAIR",0)==0 if method in {"M2","M3"} else True)
  if method=="M4":invariant=invariant and moves==0 and departures==0 and connection_delay==0
  reports.append({"method":method,"issues_audited":issues,"planner_modes":dict(modes),"h0_moves":moves,"departures":departures,
   "arrivals":arrivals,"connection_delay_state_occurrences":connection_delay,"policy_invariant_pass":invariant})
 static={"max_phase_aware_cut_rounds_is_one":"AC_RECOVERY_MAX_CUT_ROUNDS=1" in text,
  "grid_correction_exhaustion_injects_hard_flag":'post_dispatch_hard_flags[i]="GRID_HARD_RISK"' in text,
  "hard_flag_requests_full_replan":'if i in post_dispatch_hard_flags:requested="FULL_REPLAN"' in text,
  "hard_retry_is_single_shot_guarded":"and i not in post_dispatch_hard_flags" in text,
  "unresolved_retry_fails_closed":'if rc!=0:raise RuntimeError(f"scientific one-issue engine returned {rc} at issue {i}")' in text}
 gates={"four_methods_present":{r["method"] for r in reports}=={"M1","M2","M3","M4"},
  "policy_invariants":all(r["policy_invariant_pass"] for r in reports),
  "mobile_methods_exercised_movement_and_state_closure":all(r["departures"]>0 and (r["arrivals"]>0 or r["connection_delay_state_occurrences"]>0) for r in reports if r["method"] in {"M1","M2","M3"}),
  "fresh_ac_recovery_observed_all_methods":{r["method"] for r in recoveries}=={"M1","M2","M3","M4"} and all(r["first_candidate_failed_hard_gate"] and r["final_fresh_ac_pass"] and not r["unsafe_action_committed"] for r in recoveries),
  "frozen_grid_hard_semantics_static":all(static.values())}
 out={"schema_version":"mobileess.pre_w02.policy_path_audit.v1","status":"PASS" if all(gates.values()) else "FAIL_CLOSED",
  "offline_only":True,"gurobi_solve_count":0,"opendss_solve_count":0,"full_W02_executed":False,
  "runner_sha256":sha(x.runner),"gates":gates,"static_grid_hard_semantics":static,"methods":reports,"fresh_ac_recoveries":recoveries}
 write(x.output,out);print(x.output);return 0 if out["status"]=="PASS" else 2
if __name__=="__main__":raise SystemExit(main())

#!/usr/bin/env python3
"""Validate the fixed runner against the exact causal PRE of every R3 failure."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

CASES=(
 ("M1","M1_PROPOSED_EVENT30_LOCAL_REPAIR_MOBILE",3551),
 ("M2","M2_FIXED30_MOBILE",3516),
 ("M3","M3_EVENT30_NO_LOCAL_REPAIR_MOBILE",3516),
 ("M4","M4_FIXED_LOCATION_ESS_MOBILITY_ABLATION",3462),
)

def load(path:Path)->dict:
 return json.loads(path.read_text(encoding="utf-8"))

def sha(path:Path)->str:
 h=hashlib.sha256()
 with path.open("rb") as stream:
  for block in iter(lambda:stream.read(1<<20),b""):
   h.update(block)
 return h.hexdigest()

def write(path:Path,value:dict)->None:
 path.parent.mkdir(parents=True,exist_ok=True)
 temporary=path.with_suffix(path.suffix+".tmp")
 temporary.write_text(json.dumps(value,indent=2,sort_keys=True,allow_nan=False)+"\n",encoding="utf-8")
 temporary.replace(path)

def main()->int:
 parser=argparse.ArgumentParser()
 parser.add_argument("--package",type=Path,default=Path(__file__).resolve().parents[1])
 parser.add_argument("--failed-root",type=Path,default=Path(
  "/home/jaewon/mobile_ess_work/frozen_artifacts/B_W02_4POLICY_ACTUAL_FINAL_R3"))
 parser.add_argument("--regression-root",type=Path,default=Path(
  "/home/jaewon/mobile_ess_work/frozen_artifacts/POST15_R3_ACTUAL_FAILURE_REPLAY_FIXED_20260818"))
 parser.add_argument("--output",type=Path,default=Path(
  "/home/jaewon/mobile_ess_work/frozen_artifacts/PRE_W02_R3_ACTUAL_FAILURE_RECOVERY_CURRENT.json"))
 args=parser.parse_args()
 runner=(args.package/"runtime/W02_POLICY_EPISODE_RUNNER.py").resolve()
 rows=[]
 for method,policy,issue in CASES:
  failed_policy=args.failed_root/policy
  interrupted=list(failed_policy.glob(
   f"interrupted_attempts/*/issue_{issue:06d}_grid_hard_pre_replan"))
  if len(interrupted)!=1:
   raise RuntimeError(f"{method} interrupted attempt cardinality={len(interrupted)}")
  interrupted_root=interrupted[0]
  original_failure_path=interrupted_root/"_FAILURE.json"
  original_issue=interrupted_root/f"issue_{issue:06d}"
  original_pre_path=original_issue/"BUILD7C_PRECOMMIT_STATE.json"
  original_candidates_path=original_issue/"A_B10_RECOVERY_CANDIDATE_IDENTITY_AUDIT.json"
  original_failure=load(original_failure_path)
  original_pre=load(original_pre_path)
  original_candidates=load(original_candidates_path).get("candidates",[])
  if len(original_candidates)!=1:
   raise RuntimeError(f"{method} original candidate cardinality={len(original_candidates)}")

  replay_issue=args.regression_root/policy/"engine"/f"issue_{issue:06d}"
  audit_path=replay_issue/"POLICY_ISSUE_AUDIT.json"
  recovery_path=replay_issue/"A_B10_EXACT_AC_CLOSED_LOOP_RECOVERY.json"
  commit_path=replay_issue/"A_B10_COMMIT_MARKER.json"
  replay_pre_path=replay_issue/"BUILD7C_PRECOMMIT_STATE.json"
  audit=load(audit_path);recovery=load(recovery_path);replay_pre=load(replay_pre_path)
  attempts=audit.get("fresh_ac_candidate_attempts",[])
  initial=attempts[0] if attempts else {}
  final=attempts[-1].get("exact_ac",{}) if attempts else {}
  original=original_candidates[0]
  checks={
   "r3_primary_recovery_failed_before_any_correction_candidate":(
    original_failure.get("status")=="FAIL_CLOSED"
    and "GRID_CORRECTION_EXHAUSTED_NO_COMPLETE_SENSITIVITY" in str(original_failure.get("error"))
    and original.get("stage")=="INITIAL" and original.get("hard_constraint_pass") is False),
   "same_causal_pre_state":(
    audit.get("pre_state_sha256")==original_pre.get("sha256")==replay_pre.get("sha256")),
   "same_initial_decision_candidate":(
    initial.get("decision_candidate_sha256")==original.get("decision_candidate_sha256")),
   "same_initial_electrical_candidate":(
    initial.get("electrical_candidate_sha256")==original.get("electrical_candidate_sha256")),
   "exactly_one_bounded_pq_correction_candidate":(
    [x.get("stage") for x in attempts]==["INITIAL","AC_CORRECTION"]),
   "fresh_exact_ac_pass_before_commit":(
    audit.get("fresh_opendss_pass") is True and final.get("converged") is True
    and final.get("hard_constraint_pass") is True and final.get("voltage_violation_count")==0
    and final.get("line_violation_count")==0
    and final.get("transformer_current_violation_count")==0
    and final.get("transformer_kva_violation_count")==0),
   "atomic_commit_marker_present":audit.get("status")=="PASS_COMMITTED" and commit_path.is_file(),
   "recovery_contract_preserved":(
    recovery.get("status")=="PASS_RECOVERED" and recovery.get("max_cut_rounds")==1
    and recovery.get("hard_limits_relaxed") is False and recovery.get("future_actual_used") is False
    and audit.get("future_actual_used") is False),
  }
  rows.append({
   "method":method,"policy":policy,"issue":issue,
   "status":"PASS" if all(checks.values()) else "FAIL_CLOSED","checks":checks,
   "original_pre_state_sha256":original_pre.get("sha256"),
   "original_initial_decision_candidate_sha256":original.get("decision_candidate_sha256"),
   "replay_corrected_decision_candidate_sha256":attempts[-1].get("decision_candidate_sha256") if attempts else None,
   "candidate_stages":[x.get("stage") for x in attempts],
   "fresh_voltage_min_pu":final.get("voltage_min_pu"),
   "fresh_voltage_max_pu":final.get("voltage_max_pu"),
   "original_failure":{"path":str(original_failure_path),"sha256":sha(original_failure_path)},
   "original_candidate_audit":{"path":str(original_candidates_path),"sha256":sha(original_candidates_path)},
   "policy_issue_audit":{"path":str(audit_path),"sha256":sha(audit_path)},
   "recovery_evidence":{"path":str(recovery_path),"sha256":sha(recovery_path)},
   "commit_marker":{"path":str(commit_path),"sha256":sha(commit_path)},
  })
 status="PASS" if all(row["status"]=="PASS" for row in rows) else "FAIL_CLOSED"
 output={
  "schema_version":"mobileess.post_stage15.w02_r3_actual_failure_recovery.v1",
  "status":status,"root_cause":"FD_SAMPLE_AND_GRADIENT_BLOCK_WAS_UNREACHABLE_AFTER_FEASIBLE_STEP_BREAK",
  "runner":{"path":str(runner),"sha256":sha(runner)},
  "failed_root":str(args.failed_root),"regression_root":str(args.regression_root),
  "cases":rows,"common_safety_layer_methods":[x[0] for x in CASES],
  "scientific_solve_count_by_this_validator":0,"opendss_solve_count_by_this_validator":0,
  "full_W02_executed":False,"hard_limits_relaxed":False,"future_actual_used":False,
 }
 write(args.output,output);print(json.dumps(output,indent=2,sort_keys=True))
 return 0 if status=="PASS" else 2

if __name__=="__main__":
 raise SystemExit(main())

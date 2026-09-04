#!/usr/bin/env python3
"""Fail-closed audit for the W02 Fresh-AC sensitivity-key recovery correction."""
from __future__ import annotations

import argparse,ast,hashlib,json
from pathlib import Path

CASES=(
 ("M1_PROPOSED_EVENT30_LOCAL_REPAIR_MOBILE",3516),
 ("M2_FIXED30_MOBILE",3516),
 ("M4_FIXED_LOCATION_ESS_MOBILITY_ABLATION",3462),
)

def sha(path:Path)->str:return hashlib.sha256(path.read_bytes()).hexdigest()
def load(path:Path)->dict:return json.loads(path.read_text(encoding="utf-8"))
def write(path:Path,value:dict)->None:
 path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix(path.suffix+".tmp")
 tmp.write_text(json.dumps(value,indent=2,sort_keys=True,allow_nan=False)+"\n",encoding="utf-8");tmp.replace(path)
def function_source(text:str,tree:ast.Module,name:str)->str:
 node=next(x for x in tree.body if isinstance(x,(ast.FunctionDef,ast.AsyncFunctionDef)) and x.name==name)
 lines=text.splitlines();return "\n".join(lines[node.lineno-1:node.end_lineno])

def fd_sampling_follows_step_selection(tree:ast.Module)->bool:
 recovery=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=="exact_ac_cut_recovery")
 step_loop=next((x for x in ast.walk(recovery)
                 if isinstance(x,ast.For) and isinstance(x.target,ast.Name) and x.target.id=="step"),None)
 samples_assign=next((x for x in ast.walk(recovery) if isinstance(x,ast.Assign)
                      and any(isinstance(t,ast.Name) and t.id=="samples" for t in x.targets)),None)
 gradient_assign=next((x for x in ast.walk(recovery) if isinstance(x,ast.Assign)
                       and any(isinstance(t,ast.Subscript) and isinstance(t.value,ast.Name)
                               and t.value.id=="gradients" for t in x.targets)),None)
 exhaustion=next((x for x in ast.walk(recovery) if isinstance(x,ast.Raise)
                  and "GRID_CORRECTION_EXHAUSTED_NO_COMPLETE_SENSITIVITY" in ast.unparse(x)),None)
 return bool(step_loop and samples_assign and gradient_assign and exhaustion
             and step_loop.end_lineno<samples_assign.lineno<gradient_assign.lineno<exhaustion.lineno)

def main()->int:
 ap=argparse.ArgumentParser()
 ap.add_argument("--package",type=Path,default=Path(__file__).resolve().parents[1])
 ap.add_argument("--failed-root",type=Path,required=True)
 ap.add_argument("--regression-root",type=Path,required=True)
 ap.add_argument("--r2-failed-root",type=Path)
 ap.add_argument("--r2-regression-root",type=Path)
 ap.add_argument("--output",type=Path,required=True)
 a=ap.parse_args();runner=(a.package/"runtime/W02_POLICY_EPISODE_RUNNER.py").resolve()
 text=runner.read_text(encoding="utf-8");tree=ast.parse(text)
 recovery=function_source(text,tree,"exact_ac_cut_recovery");policy_loop=function_source(text,tree,"main")
 checks={
  "violating_voltage_keys_are_the_only_fd_targets":(
   'target_voltage_keys=sorted({(str(r["bus"]),int(r["node"])) for r in violations})' in recovery),
  "fd_topology_presence_is_checked_before_gradient_build":(
   "vk not in baseline" in recovery and "vk not in samples[delta]" in recovery
   and "GRID_CORRECTION_EXHAUSTED_FD_TOPOLOGY_DRIFT" in recovery),
  "cut_assembly_uses_guarded_gradient_lookup":(
   'gradients.get((c["mess_id"],"P",vk))' in recovery
   and 'gradients.get((c["mess_id"],"Q",vk))' in recovery
   and 'float(gradients[(c["mess_id"],"P",vk)])' not in recovery),
  "incomplete_coordinate_is_fixed_before_zero_gradient_use":(
   'model.addLConstr(c[expr_key]==float(c[value_key])' in recovery
   and '"recovery_feasible_set_expanded":False' in recovery
   and 'gp_=0.0 if gp_ is None else float(gp_)' in recovery
   and 'gq=0.0 if gq is None else float(gq)' in recovery),
  "conditional_r24_refinement_keeps_the_same_primary_and_gate":(
   'R24_NUMERICAL_REFINEMENT_GATE_FAILED' in text
   and '"same_primary_objective":True' in text and '"hard_gate_relaxed":False' in text),
  "topology_or_sensitivity_exhaustion_routes_to_same_pre_full_replan":(
   '"GRID_CORRECTION_EXHAUSTED" in str(failure.get("error",""))' in policy_loop),
  "both_feasible_fd_directions_are_collected":(
   "for sign in (-1.0,1.0)" in recovery and "deltas.append(delta)" in recovery),
  "fd_sampling_executes_after_feasible_step_selection":fd_sampling_follows_step_selection(tree),
  "hard_limits_remain_unchanged":all(x in text for x in (
   "PCS_ACTIVE_LIMIT_KW=550.0","PCS_APPARENT_LIMIT_KVA=700.0")),
 }
 failures=[];regressions=[]
 for method,issue in CASES:
  fail_path=a.failed_root/method/"engine/_FAILURE.json";failure=load(fail_path)
  failures.append({"method":method,"issue":issue,"path":str(fail_path),"sha256":sha(fail_path),
   "status":failure.get("status"),"error":failure.get("error"),
   "common_missing_gradient_keyerror":str(failure.get("error","")).startswith("KeyError(("),
   "future_actual_used":bool(failure.get("future_actual_jobs_used_for_optimizer",False))})
  issue_dir=a.regression_root/method/"engine"/f"issue_{issue:06d}"
  audit_path=issue_dir/"POLICY_ISSUE_AUDIT.json";commit_path=issue_dir/"A_B10_COMMIT_MARKER.json"
  audit=load(audit_path);attempts=audit.get("fresh_ac_candidate_attempts",[])
  exact=attempts[-1].get("exact_ac",{}) if attempts else {}
  regressions.append({"method":method,"issue":issue,"policy_issue_audit":str(audit_path),
   "policy_issue_audit_sha256":sha(audit_path),"commit_marker_sha256":sha(commit_path),
   "status":audit.get("status"),"fresh_opendss_pass":audit.get("fresh_opendss_pass"),
   "exact_ac_converged":exact.get("converged"),"exact_ac_hard_constraint_pass":exact.get("hard_constraint_pass"),
   "voltage_min_pu":exact.get("voltage_min_pu"),"voltage_max_pu":exact.get("voltage_max_pu"),
   "future_actual_used":audit.get("future_actual_used"),"candidate_count":len(attempts)})
 checks["three_r1_failures_share_the_same_software_keyerror"]=all(
  r["status"]=="FAIL_CLOSED" and r["common_missing_gradient_keyerror"] and not r["future_actual_used"] for r in failures)
 checks["three_stopped_issue_regressions_commit_with_fresh_exact_ac"]=all(
  r["status"]=="PASS_COMMITTED" and r["fresh_opendss_pass"] is True
  and r["exact_ac_converged"] is True and r["exact_ac_hard_constraint_pass"] is True
  and r["future_actual_used"] is False for r in regressions)
 r2_failure=None;r2_regression=None
 if a.r2_failed_root and a.r2_regression_root:
  failure_path=a.r2_failed_root/"M4_FIXED_LOCATION_ESS_MOBILITY_ABLATION/engine/_FAILURE.json"
  failure=load(failure_path)
  audit_path=a.r2_regression_root/"M4_FIXED_LOCATION_ESS_MOBILITY_ABLATION/engine/issue_003462/POLICY_ISSUE_AUDIT.json"
  audit=load(audit_path);attempts=audit.get("fresh_ac_candidate_attempts",[])
  exact=attempts[-1].get("exact_ac",{}) if attempts else {}
  r2_failure={"path":str(failure_path),"sha256":sha(failure_path),"error":failure.get("error"),
   "status":failure.get("status")}
  r2_regression={"path":str(audit_path),"sha256":sha(audit_path),"status":audit.get("status"),
   "fresh_opendss_pass":audit.get("fresh_opendss_pass"),"exact_ac":exact,
   "conditional_numerical_refinement":audit.get("fast_solver",{}).get("conditional_numerical_refinement")}
  checks["r2_m4_duplicate_fail_is_preserved_and_current_runner_commits_safely"]=(
   r2_failure["status"]=="FAIL_CLOSED"
   and "DUPLICATE_RECOVERY_CANDIDATE_NO_SECOND_OPENDSS" in str(r2_failure["error"])
   and r2_regression["status"]=="PASS_COMMITTED" and r2_regression["fresh_opendss_pass"] is True
   and exact.get("converged") is True and exact.get("hard_constraint_pass") is True)
 status="PASS" if all(checks.values()) else "FAIL_CLOSED"
 out={"schema_version":"mobileess.post_stage15.w02_sensitivity_keyerror_correction_audit.v2",
  "status":status,"runner":str(runner),"runner_sha256":sha(runner),"checks":checks,
  "forensic_r1_failures":failures,"bounded_regressions":regressions,
  "forensic_r2_failure":r2_failure,"r2_bounded_regression":r2_regression,
  "scientific_solve_count_by_this_validator":0,"opendss_solve_count_by_this_validator":0,
  "full_W02_executed":False,"document_files_modified":False}
 write(a.output,out);print(json.dumps(out,indent=2,sort_keys=True));return 0 if status=="PASS" else 2

if __name__=="__main__":raise SystemExit(main())

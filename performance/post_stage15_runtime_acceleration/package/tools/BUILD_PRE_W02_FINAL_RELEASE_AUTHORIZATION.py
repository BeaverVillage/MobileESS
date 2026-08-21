#!/usr/bin/env python3
"""Fail-closed assembler for the outcome-blind Pre-W02 release certificate."""
from __future__ import annotations
import argparse,hashlib,json,subprocess,sys
from pathlib import Path

def load(p:Path):return json.loads(p.read_text(encoding="utf-8"))
def sha(p:Path)->str:
 h=hashlib.sha256()
 with p.open("rb") as f:
  for b in iter(lambda:f.read(8<<20),b""):h.update(b)
 return h.hexdigest()
def write(p:Path,x):
 p.parent.mkdir(parents=True,exist_ok=True);t=p.with_suffix(p.suffix+".tmp")
 t.write_text(json.dumps(x,indent=2,sort_keys=True,allow_nan=False)+"\n",encoding="utf-8");t.replace(p)
def evidence(path:Path,accepted:tuple[str,...])->dict:
 d=load(path);return {"path":str(path),"sha256":sha(path),"status":d.get("status"),"pass":str(d.get("status")) in accepted}

def main():
 a=argparse.ArgumentParser();a.add_argument("--package",type=Path,default=Path(__file__).resolve().parents[1])
 a.add_argument("--artifact-root",type=Path,default=Path("/home/jaewon/mobile_ess_work/frozen_artifacts"));x=a.parse_args();pkg=x.package.resolve();art=x.artifact_root
 static_checks=[]
 for p in sorted(pkg.rglob("*.py")):
  if "__pycache__" in p.parts:continue
  try:compile(p.read_text(encoding="utf-8"),str(p),"exec");ok=True;detail=None
  except Exception as exc:ok=False;detail=repr(exc)
  static_checks.append({"kind":"PYTHON_COMPILE","path":str(p.relative_to(pkg)),"pass":ok,"detail":detail})
 for p in sorted(pkg.rglob("*.sh")):
  r=subprocess.run(["bash","-n",str(p)],capture_output=True,text=True)
  static_checks.append({"kind":"BASH_PARSE","path":str(p.relative_to(pkg)),"pass":r.returncode==0,"detail":r.stderr.strip() or None})
 critical_json=[pkg/"authority/RERUN_ELIGIBILITY_CONTRACT.json",pkg/"authority/TRANSFORMER_SCENARIO_AUTHORITY.json",
  pkg/"authority/K9H7_OBSERVABILITY_V1_MANIFEST.json",pkg/"episode_bindings/MANIFEST.json"]
 for p in critical_json:
  try:load(p);ok=True;detail=None
  except Exception as exc:ok=False;detail=repr(exc)
  static_checks.append({"kind":"JSON_PARSE","path":str(p.relative_to(pkg)),"pass":ok,"detail":detail})
 static={"schema_version":"mobileess.pre_w02.static_validation.v1","status":"PASS" if all(r["pass"] for r in static_checks) else "FAIL_CLOSED",
  "checks":static_checks,"scientific_solve_count":0,"full_W02_executed":False}
 write(pkg/"STATIC_VALIDATION.json",static)
 ev=[]
 ev.append(evidence(art/"B_W02_4POLICY_PREFLIGHT.json",("PASS",)))
 ev.append(evidence(art/"PRE_W02_FIRST6_PREFLIGHT_CURRENT.json",("PASS",)))
 ev.append(evidence(art/"PRE_W02_REPEATABILITY_M4_CURRENT/PRE_W02_REPEATABILITY_EVIDENCE.json",("PASS",)))
 ev.append(evidence(art/"PRE_W02_KILL_RESTART_4X4_CURRENT/PRE_W02_KILL_RESTART_4X4_EVIDENCE.json",("PASS",)))
 ev.append(evidence(art/"PRE_W02_LIGHTWEIGHT_FAIRNESS_CURRENT.json",("PASS",)))
 ev.append(evidence(art/"PRE_W02_POLICY_PATHS_CURRENT.json",("PASS",)))
 ev.append(evidence(art/"PRE_W02_SAFETY_RECOVERY_CONTRACT_CURRENT.json",("PASS",)))
 ev.append(evidence(art/"PRE_W02_SENSITIVITY_KEYERROR_CORRECTION_CURRENT.json",("PASS",)))
 ev.append(evidence(art/"PRE_W02_R3_ACTUAL_FAILURE_RECOVERY_CURRENT.json",("PASS",)))
 ev.append(evidence(art/"PRE_W02_R3_ACTUAL_FAILURE_RECOVERY_4X4_CURRENT.json",("PASS",)))
 ev.append(evidence(art/"PRE_W02_R4_M4_ISSUE3518_RECOVERY_CURRENT.json",("PASS",)))
 ev.append(evidence(art/"PRE_W02_M4_ADAPTIVE_GRID_RECOVERY_CURRENT.json",("PASS",)))
 ev.append(evidence(art/"PRE_W02_OBSERVABILITY_OVERHEAD_CURRENT.json",("PASS",)))
 ev.append(evidence(art/"PRE_W02_ANALYSIS_DRYRUN_CURRENT/MANIFEST.json",("PASS",)))
 for method in ("M1","M2","M3","M4"):
  ev.append(evidence(art/f"PRE_W02_OBSERVABILITY_FINITE_CURRENT/{method}/MANIFEST.json",("PASS",)))
  ev.append(evidence(art/f"PRE_W02_OFFLINE_RECALCULATOR_CURRENT/{method}.json",("PASS_BOUNDED_INDIVIDUAL_EVIDENCE",)))
 binding=load(pkg/"episode_bindings/MANIFEST.json");bindings=binding.get("bindings",[])
 binding_gate=(binding.get("binding_count")==48 and len(bindings)==48 and len({r["candidate_id"] for r in bindings})==12
  and {r["comparison_method_id"] for r in bindings}=={"M1","M2","M3","M4"} and all(r.get("status")=="FROZEN_PRE_OUTCOME" for r in bindings))
 rerun=load(pkg/"authority/RERUN_ELIGIBILITY_CONTRACT.json");obs=load(pkg/"authority/K9H7_OBSERVABILITY_V1_MANIFEST.json")
 kill=load(art/"PRE_W02_KILL_RESTART_4X4_CURRENT/PRE_W02_KILL_RESTART_4X4_EVIDENCE.json")
 r3_recovery=load(art/"PRE_W02_R3_ACTUAL_FAILURE_RECOVERY_CURRENT.json")
 r3_recovery_4x4=load(art/"PRE_W02_R3_ACTUAL_FAILURE_RECOVERY_4X4_CURRENT.json")
 r4_issue3518=load(art/"PRE_W02_R4_M4_ISSUE3518_RECOVERY_CURRENT.json")
 adaptive_grid=load(art/"PRE_W02_M4_ADAPTIVE_GRID_RECOVERY_CURRENT.json")
 r20_issue4499=load(pkg/"authority/POST_STAGE15_W02_R20_M1_ISSUE4499_CONTINUOUS_COMMIT_ROOTCAUSE_CORRECTION.json")
 r20_boundary=load(pkg/"authority/POST_STAGE15_W02_R20_1_PLANNER_TRANSFER_BOUND_CANONICALIZATION_ROOTCAUSE_CORRECTION.json")
 r20_numerical=load(pkg/"authority/POST_STAGE15_W02_R20_2_NUMERICAL_REFINEMENT_CERTIFICATE_RETRY_ROOTCAUSE_CORRECTION.json")
 r20_scheduler=load(pkg/"authority/POST_STAGE15_REP12_R20_3_ISOLATED_TASK_FAILURE_CONTINUATION_ROOTCAUSE_CORRECTION.json")
 r20_route=load(pkg/"authority/POST_STAGE15_REP12_R20_4_CAUSAL_ROUTE_TAIL_ROOTCAUSE_CORRECTION.json")
 r20_pcc_polish=load(pkg/"authority/POST_STAGE15_REP12_R20_5_PCC_BALANCE_NUMERICAL_POLISH_ROOTCAUSE_CORRECTION.json")
 r20_sparse_dense=load(pkg/"authority/POST_STAGE15_REP12_R20_6_SPARSE_DENSE_EQUIVALENCE_FALLBACK_ROOTCAUSE_CORRECTION.json")
 r20_vtype_restore=load(pkg/"authority/POST_STAGE15_REP12_R20_7_LOCAL_REPAIR_VTYPE_RESTORE_ROOTCAUSE_CORRECTION.json")
 gates={"all_evidence_pass":all(r["pass"] for r in ev),"static_validation_pass":static["status"]=="PASS",
  "resolved_episode_bindings_12x4":binding_gate,"rerun_eligibility_frozen_pre_outcome":rerun.get("status")=="FROZEN_PRE_OUTCOME",
  "observability_contract_frozen_pre_outcome":obs.get("status")=="FROZEN_PRE_OUTCOME",
  "bounded_4process_x_4thread_pass":kill.get("status")=="PASS" and kill.get("processes")==4 and kill.get("gurobi_threads_per_process")==4,
  "r3_actual_failure_recovery_m1_m4_pass":(
   r3_recovery.get("status")=="PASS" and r3_recovery.get("common_safety_layer_methods")==["M1","M2","M3","M4"]),
  "r3_actual_failure_recovery_4x4_pass":(
   r3_recovery_4x4.get("status")=="PASS"
   and r3_recovery_4x4.get("common_safety_layer_methods")==["M1","M2","M3","M4"]
   and "FIXED_4X4" in str(r3_recovery_4x4.get("regression_root",""))),
  "r4_m4_issue3518_trust_region_recovery_pass":(
   r4_issue3518.get("status")=="PASS"
   and r4_issue3518.get("checks",{}).get("finite_difference_matched_trust_region") is True
   and r4_issue3518.get("checks",{}).get("fresh_exact_ac_pass") is True
   and r4_issue3518.get("checks",{}).get("atomic_commit") is True),
  "m4_adaptive_voltage_line_grid_recovery_pass":(
   adaptive_grid.get("status")=="PASS"
   and adaptive_grid.get("design_checks",{}).get("all_nine_exact_failure_boundaries_pass") is True
   and adaptive_grid.get("design_checks",{}).get("power_scale_1000_kw_per_model_unit_unchanged") is True
   and adaptive_grid.get("design_checks",{}).get("severe_voltage_uses_tap_aware_two_stage_q_policy") is True
   and [row.get("boundary_id") for row in adaptive_grid.get("boundaries",[])]==[
    "R4_ISSUE3518_LOCAL_VOLTAGE","R5_ISSUE3573_COUPLED_VOLTAGE_LINE",
    "R6_ISSUE3574_SEVERE_VOLTAGE","R7_ISSUE3573_SEVERE_VOLTAGE_LINE_TWO_STAGE",
    "R8_ISSUE3577_VOLTAGE_ONLY_TAP_RISK",
    "R9_ISSUE3577_VOLTAGE_ONLY_TWO_STAGE_TAP_RELINEARIZATION",
    "R10_ISSUE3580_VOLTAGE_ONLY_THREE_STAGE_TAP_RELINEARIZATION",
    "R11_ISSUE3580_COMBINED_BOUNDED_ITERATIVE_TAP_RECOVERY",
    "R12_ISSUE3582_SUBTHRESHOLD_UNIFIED_ITERATIVE_RECOVERY"]
   and all(row.get("checks",{}).get("fresh_exact_ac_pass") is True for row in adaptive_grid.get("boundaries",[]))
   and all(row.get("checks",{}).get("atomic_commit") is True for row in adaptive_grid.get("boundaries",[]))),
  "r20_m1_issue4499_continuous_commit_pass":(
   r20_issue4499.get("status")=="PASS_ROOT_CAUSE_CORRECTED_AND_TARGET_REPRODUCED"
   and r20_issue4499.get("target_regression",{}).get("target_issue")==4499
   and r20_issue4499.get("target_regression",{}).get("target_status")=="COMMITTED"
   and r20_issue4499.get("target_regression",{}).get("fresh_exact_ac_pass") is True
   and r20_issue4499.get("target_regression",{}).get("unsafe_action_committed") is False
   and r20_issue4499.get("root_cause",{}).get("continuous_move_arc_count_at_issue_4499")==94726),
  "r20_1_planner_transfer_boundary_canonicalization_pass":(
   r20_boundary.get("status")=="PASS_ROOT_CAUSE_CORRECTED_ALL_TARGETS_REPRODUCED_AND_PREFIX_PRESERVED"
   and r20_boundary.get("runner",{}).get("corrected_sha256")=="c8c885d886f7b56b9b8e2e17161a9c653256277456232b9191e1883ac9e51ac6"
   and r20_boundary.get("root_cause",{}).get("solver_value")==-8.793077895625385e-07
   and r20_boundary.get("root_cause",{}).get("scientific_infeasibility") is False
   and r20_boundary.get("correction",{}).get("scientific_objective_changed") is False
   and r20_boundary.get("correction",{}).get("hard_constraint_relaxed") is False
   and r20_boundary.get("actual_regressions",{}).get("failed_target_issue_3872",{}).get("status")=="COMMITTED"
   and r20_boundary.get("actual_regressions",{}).get("failed_target_issue_3872",{}).get("fresh_exact_ac_pass") is True
   and r20_boundary.get("actual_regressions",{}).get("m1_contiguous_follow_on_3872_through_3885",{}).get("count")==14
   and all(r20_boundary.get("actual_regressions",{}).get(key,{}).get("status")=="COMMITTED" for key in (
    "m2_next_issue_3986","m3_next_issue_3783","m4_next_issue_5271","prior_continuous_arc_regression_issue_4499"))),
  "r20_2_numerical_refinement_certificate_retry_pass":(
   r20_numerical.get("status")=="PASS_ROOT_CAUSE_CORRECTED_TARGET_AND_NEXT_ISSUE_REPRODUCED_PREFIX_PRESERVED"
   and r20_numerical.get("runner",{}).get("corrected_sha256")=="90488dea741dd9b3f196f5806c93f182422d3f9c47123fa368a3019c44f6d458"
   and r20_numerical.get("failure",{}).get("failed_issue")==4172
   and r20_numerical.get("root_cause",{}).get("strict_refinement_status")==13
   and r20_numerical.get("root_cause",{}).get("strict_refinement_gap",0)>0.03
   and r20_numerical.get("original_failure_predicate_proof",{}).get("old_predicate_retry") is False
   and r20_numerical.get("original_failure_predicate_proof",{}).get("new_predicate_retry") is True
   and r20_numerical.get("correction",{}).get("fallback_feasibility_tolerance")==5e-7
   and r20_numerical.get("correction",{}).get("final_constraint_gate")==1e-6
   and r20_numerical.get("correction",{}).get("hard_gate_relaxed") is False
   and r20_numerical.get("actual_regressions",{}).get("failed_target_issue_4172",{}).get("status")=="COMMITTED"
   and r20_numerical.get("actual_regressions",{}).get("failed_target_issue_4172",{}).get("fresh_exact_ac_pass") is True
   and r20_numerical.get("actual_regressions",{}).get("next_chain_issue_4173",{}).get("status")=="COMMITTED"
   and r20_numerical.get("actual_regressions",{}).get("next_chain_issue_4173",{}).get("fresh_exact_ac_pass") is True),
  "r20_3_rep12_isolated_task_failure_continuation_pass":(
   r20_scheduler.get("status")=="PASS_ROOT_CAUSE_CORRECTED_DETERMINISTIC_FAILURE_INJECTION_PASSED"
   and r20_scheduler.get("correction",{}).get("episode_failure_isolated_to_worker_slot") is True
   and r20_scheduler.get("correction",{}).get("failed_worker_immediately_takes_next_global_fifo_task") is True
   and r20_scheduler.get("correction",{}).get("other_active_workers_continue_untouched") is True
   and r20_scheduler.get("correction",{}).get("source_failure_skips_only_blocked_week_pending_policies") is True
   and r20_scheduler.get("correction",{}).get("missing_episode_completion_artifact_is_isolated") is True
   and r20_scheduler.get("correction",{}).get("week_structure_validation_failure_is_isolated") is True
   and r20_scheduler.get("correction",{}).get("ctrl_c_still_stops_all_active_process_groups_resumably") is True
   and r20_scheduler.get("correction",{}).get("campaign_pass_blocked_when_any_task_failed") is True
   and r20_scheduler.get("scientific_contract",{}).get("episode_runner_changed") is False
   and r20_scheduler.get("scientific_contract",{}).get("power_scale_changed") is False),
  "r20_4_causal_route_tail_canonicalization_pass":(
   r20_route.get("status")=="PASS_ROOT_CAUSE_CORRECTED_TARGET_AND_NEXT_BOUNDARY_REPRODUCED_PREFIX_PRESERVED"
   and r20_route.get("failure",{}).get("failed_issue")==13662
   and r20_route.get("root_cause",{}).get("scientific_solver_failure") is False
   and r20_route.get("root_cause",{}).get("bad_report_row_count")==50
   and r20_route.get("correction",{}).get("load_time_causal_route_reconstruction") is True
   and r20_route.get("correction",{}).get("commit_time_causal_route_canonicalization") is True
   and r20_route.get("correction",{}).get("legacy_committed_plan_mutated") is False
   and r20_route.get("correction",{}).get("hard_constraint_relaxed") is False
   and r20_route.get("correction",{}).get("power_scale_changed") is False
   and r20_route.get("actual_target_regression",{}).get("status")=="COMMITTED"
   and r20_route.get("actual_target_regression",{}).get("fresh_exact_ac_pass") is True
   and r20_route.get("actual_target_regression",{}).get("unsafe_action_committed") is False
   and r20_route.get("actual_target_regression",{}).get("next_issue_13663_reference_load_pass") is True
   and r20_route.get("actual_target_regression",{}).get("new_plan_report_correction_count_at_next_boundary")==0
  and r20_route.get("preserved_production_prefix",{}).get("total_committed_issues")==5651
  and r20_route.get("preserved_production_prefix",{}).get("ctrl_c_corrupted_committed_result") is False),
  "r20_5_pcc_balance_numerical_polish_pass":(
   r20_pcc_polish.get("status")=="PASS_ROOT_CAUSE_CORRECTED_TARGET_AND_NEXT_ISSUE_REPRODUCED_PREFIX_PRESERVED"
   and r20_pcc_polish.get("failure",{}).get("failed_issue")==13706
   and r20_pcc_polish.get("root_cause",{}).get("max_residual_constraint")=="pbal_12_mess_idc02_pcc"
   and r20_pcc_polish.get("root_cause",{}).get("power_scale_failure") is False
   and r20_pcc_polish.get("correction",{}).get("fallback_inner_feasibility_tolerance")==2e-7
   and r20_pcc_polish.get("correction",{}).get("final_constraint_gate")==1e-6
   and r20_pcc_polish.get("correction",{}).get("hard_gate_relaxed") is False
   and r20_pcc_polish.get("correction",{}).get("scientific_objective_changed") is False
   and r20_pcc_polish.get("correction",{}).get("scientific_feasible_set_changed") is False
   and r20_pcc_polish.get("correction",{}).get("power_scale_changed") is False
   and r20_pcc_polish.get("actual_regression",{}).get("target_issue_13706",{}).get("status")=="COMMITTED"
   and r20_pcc_polish.get("actual_regression",{}).get("target_issue_13706",{}).get("constraint_violation",1)>0
   and r20_pcc_polish.get("actual_regression",{}).get("target_issue_13706",{}).get("constraint_violation",1)<=1e-6
   and r20_pcc_polish.get("actual_regression",{}).get("target_issue_13706",{}).get("fresh_exact_ac_pass") is True
   and r20_pcc_polish.get("actual_regression",{}).get("next_issue_13707",{}).get("status")=="COMMITTED"
   and r20_pcc_polish.get("actual_regression",{}).get("next_issue_13707",{}).get("fresh_exact_ac_pass") is True
  and r20_pcc_polish.get("preserved_production_prefix",{}).get("total_committed_issues")==6003
  and r20_pcc_polish.get("preserved_production_prefix",{}).get("ctrl_c_corrupted_committed_result") is False),
  "r20_6_sparse_dense_equivalence_fallback_pass":(
   r20_sparse_dense.get("status")=="PASS_ROOT_CAUSE_CORRECTED_TARGET_AND_NEXT_ISSUE_REPRODUCED_PREFIX_PRESERVED"
   and r20_sparse_dense.get("failure",{}).get("failed_issue")==4777
   and r20_sparse_dense.get("failure",{}).get("restored_rows")==576
   and r20_sparse_dense.get("root_cause",{}).get("power_scale_failure") is False
   and r20_sparse_dense.get("correction",{}).get("same_pre_full_domain_restored") is True
   and r20_sparse_dense.get("correction",{}).get("dense_exact_full_row_planner_retry_limit")==1
   and r20_sparse_dense.get("correction",{}).get("hard_constraint_relaxed") is False
   and r20_sparse_dense.get("correction",{}).get("scientific_objective_changed") is False
   and r20_sparse_dense.get("correction",{}).get("scientific_feasible_set_changed") is False
   and r20_sparse_dense.get("correction",{}).get("power_scale_changed") is False
   and r20_sparse_dense.get("actual_regression",{}).get("target_issue_4777",{}).get("status")=="PASS_COMMITTED"
   and r20_sparse_dense.get("actual_regression",{}).get("target_issue_4777",{}).get("fresh_exact_ac_pass") is True
   and r20_sparse_dense.get("actual_regression",{}).get("next_issue_4778",{}).get("status")=="PASS_COMMITTED"
   and r20_sparse_dense.get("actual_regression",{}).get("next_issue_4778",{}).get("fresh_exact_ac_pass") is True
   and r20_sparse_dense.get("preserved_production_prefix",{}).get("total_committed_issues")==7203
   and r20_sparse_dense.get("preserved_production_prefix",{}).get("ctrl_c_corrupted_committed_result") is False),
  "r20_7_local_repair_variable_type_restore_pass":(
   r20_vtype_restore.get("status")=="PASS_ROOT_CAUSE_CORRECTED_TARGET_AND_NEXT_ISSUE_REPRODUCED_PREFIX_PRESERVED"
   and r20_vtype_restore.get("failure",{}).get("failed_issue")==13975
   and r20_vtype_restore.get("failure",{}).get("failed_full_planner_integer_variable_count")==276
   and r20_vtype_restore.get("root_cause",{}).get("power_scale_failure") is False
   and r20_vtype_restore.get("correction",{}).get("snapshot_fields")==["LB","UB","VType"]
   and r20_vtype_restore.get("correction",{}).get("restored_integer_variable_type_count_at_target")==8512
   and r20_vtype_restore.get("correction",{}).get("corrected_full_planner_integer_variable_count")==8728
   and r20_vtype_restore.get("correction",{}).get("hard_constraint_relaxed") is False
   and r20_vtype_restore.get("correction",{}).get("scientific_objective_changed") is False
   and r20_vtype_restore.get("correction",{}).get("scientific_feasible_set_changed") is False
   and r20_vtype_restore.get("correction",{}).get("power_scale_changed") is False
   and r20_vtype_restore.get("actual_regression",{}).get("target_issue_13975",{}).get("status")=="PASS_COMMITTED"
   and r20_vtype_restore.get("actual_regression",{}).get("target_issue_13975",{}).get("transit_mess_all_zero_pq") is True
   and r20_vtype_restore.get("actual_regression",{}).get("target_issue_13975",{}).get("fresh_exact_ac_pass") is True
   and r20_vtype_restore.get("actual_regression",{}).get("next_issue_13976",{}).get("status")=="PASS_COMMITTED"
   and r20_vtype_restore.get("actual_regression",{}).get("next_issue_13976",{}).get("fresh_exact_ac_pass") is True
   and r20_vtype_restore.get("preserved_production_prefix",{}).get("total_committed_issues")==7297
   and r20_vtype_restore.get("preserved_production_prefix",{}).get("ctrl_c_corrupted_committed_result") is False),
  "rep12_source_preparation_monitored_queue":(
   'pid_kind["$pid"]="source"' in (pkg/"RUN_FIRST6_REP_WEEKS_ACTUAL.sh").read_text(encoding="utf-8")
   and 'dispatch_prerequisite_waiters' in (pkg/"RUN_FIRST6_REP_WEEKS_ACTUAL.sh").read_text(encoding="utf-8")
   and 'kill -TERM -- "-$pid"' in (pkg/"RUN_FIRST6_REP_WEEKS_ACTUAL.sh").read_text(encoding="utf-8")),
  "full_W02_not_executed_by_hardening":all(load(Path(r["path"])).get("full_W02_executed",False) is False for r in ev if Path(r["path"]).suffix==".json"),
  "outcome_blind_acceptance":True}
 source_files=[]
 include=[pkg/"runtime/W02_POLICY_EPISODE_RUNNER.py",pkg/"RUN_W02_4POLICY_ACTUAL.sh",
  pkg/"RUN_FIRST6_REP_WEEKS_ACTUAL.sh",pkg/"RUN_12_REP_WEEKS_ACTUAL.sh",
  pkg/"STATIC_VALIDATION.json",pkg/"episode_bindings/MANIFEST.json"]
 include+=sorted((pkg/"configs").glob("*.json"))+sorted((pkg/"tools").glob("*.py"))+sorted((pkg/"tools").glob("*.sh"))
 include+=sorted((pkg/"authority").glob("*.json"))
 for p in include:
  if p.is_file() and p.name!="PRE_W02_FINAL_RELEASE_AUTHORIZATION.json":source_files.append({"path":str(p.relative_to(pkg)),"sha256":sha(p)})
 tree_sha=hashlib.sha256("\n".join(f"{r['sha256']}  {r['path']}" for r in source_files).encode()).hexdigest()
 ok=all(gates.values())
 out={"schema_version":"mobileess.pre_w02.final_release_authorization.v1","status":"AUTHORIZED_FOR_W02" if ok else "BLOCKED_FAIL_CLOSED",
  "authorization_scope":"Twelve representative weeks x four policies; one global queue with no W02 preacceptance barrier",
  "full_w02_executed":False,"full_first6_executed":False,"full_12week_executed":False,
  "scientific_outcome_examined_for_authorization":False,"proposed_method_win_required":False,
  "gates":gates,"evidence":ev,"release_source_tree_sha256":tree_sha,"release_source_files":source_files,
  "production_topology":{"worker_slots":4,"fixed_gurobi_threads_per_episode":4,
   "global_week_policy_episode_queue_all_48":True,"w02_preacceptance_barrier":False,
   "completed_worker_starts_next_pending_episode":True,"shared_source_preparation_is_monitored_queue_work":True,
   "episode_failure_isolated_to_worker_slot":True,"failed_episode_not_retried_in_same_campaign":True,
   "other_workers_continue_after_episode_failure":True,"source_failure_skips_blocked_week_and_continues":True,
   "campaign_pass_blocked_by_any_isolated_failure":True,
   "causal_route_report_canonicalized_before_commit":True,
   "ctrl_c_accepts_only_final_atomic_commit_markers":True,
   "foreground_ctrl_c_resumable_process_group_cleanup":True,"total_logical_cpu_budget":16,
   "rolling_policy_state_split_across_processes":False},
  "post_run_only_tools":["OFFLINE_RESULT_RECALCULATOR.py","MATERIALIZE_OBSERVABILITY_OFFLINE.py","PRE_W02_ANALYSIS_DRYRUN.py"],
  "forbidden_inside_issue_loop":["VALIDATION_GUROBI_SOLVE","VALIDATION_OPENDSS_SOLVE","PAPER_STATISTICS","FIGURE_GENERATION","FULL_SOURCE_REHASH"]}
 write(pkg/"authority/PRE_W02_FINAL_RELEASE_AUTHORIZATION.json",out);print(pkg/"authority/PRE_W02_FINAL_RELEASE_AUTHORIZATION.json")
 return 0 if ok else 2
if __name__=="__main__":raise SystemExit(main())

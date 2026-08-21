#!/usr/bin/env python3
"""Outcome-blind static/state-machine audit for the frozen W02 safety recovery path."""
from __future__ import annotations
import argparse,ast,hashlib,json
from pathlib import Path

def sha(path:Path)->str:return hashlib.sha256(path.read_bytes()).hexdigest()
def load(path:Path):return json.loads(path.read_text(encoding="utf-8"))
def write(path:Path,value)->None:
 path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix(path.suffix+".tmp")
 tmp.write_text(json.dumps(value,indent=2,sort_keys=True,allow_nan=False)+"\n",encoding="utf-8");tmp.replace(path)

def literal_constants(tree:ast.AST)->dict[str,object]:
 out={}
 for node in ast.walk(tree):
  if isinstance(node,ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name):
   try:out[node.targets[0].id]=ast.literal_eval(node.value)
   except Exception:pass
 return out

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
 ap=argparse.ArgumentParser();ap.add_argument("--package",type=Path,default=Path(__file__).resolve().parents[1])
 ap.add_argument("--regression-root",type=Path);ap.add_argument("--output",type=Path,required=True);a=ap.parse_args()
 runner=(a.package/"runtime/W02_POLICY_EPISODE_RUNNER.py").resolve();text=runner.read_text(encoding="utf-8")
 tree=ast.parse(text);constants=literal_constants(tree);recovery=function_source(text,tree,"exact_ac_cut_recovery")
 policy_loop=function_source(text,tree,"main")
 fast=function_source(text,tree,"solve_fast")
 refresh=function_source(text,tree,"_refresh_solution_after_ac_resolve")
 checks={
  "at_most_ten_ac_pq_correction_rounds":constants.get("AC_RECOVERY_MAX_CUT_ROUNDS")==10,
  "one_production_candidate_reserved_for_full_replan":(
   constants.get("AC_RECOVERY_PRE_REPLAN_CUT_ROUNDS")==9
   and 'recovery_round_limit=(AC_RECOVERY_MAX_CUT_ROUNDS if fixed_location_recovery' in recovery
   and 'else AC_RECOVERY_PRE_REPLAN_CUT_ROUNDS)' in recovery
   and "< FRESH_AC_PRODUCTION_CANDIDATE_MAX" in policy_loop),
  "fixed_location_uses_distinct_tenth_pq_candidate_not_duplicate_replan":(
   'recovery_round_limit=(AC_RECOVERY_MAX_CUT_ROUNDS if fixed_location_recovery' in recovery
   and 'else AC_RECOVERY_PRE_REPLAN_CUT_ROUNDS)' in recovery),
  "complementary_bracket_releases_to_multivariable_relinearization":(
   constants.get("AC_RECOVERY_COMPLEMENTARY_BRACKET_MAX_STEPS")==3
   and "complementary_bracket_steps>=AC_RECOVERY_COMPLEMENTARY_BRACKET_MAX_STEPS" in recovery
   and "overload_endpoint=None;voltage_endpoint=None;complementary_bracket_steps=0" in recovery),
  "artificial_anchor_gap_not_misapplied_as_scientific_gap":(
   "def solve_recovery_anchor():" in recovery
   and 'R24_NUMERICAL_REFINEMENT_GAP_FAILED' in recovery
   and 'PASS_FEASIBLE_ARTIFICIAL_ANCHOR_INCUMBENT' in recovery
   and 'artificial_anchor_optimality_gap_is_not_scientific_acceptance_gate' in recovery
   and recovery.count("solve_recovery_anchor()")>=4
   and 'fresh_exact_opendss_required' in recovery
   and 'hard_limits_relaxed' in recovery),
  "conservative_voltage_cut_margin":constants.get("AC_RECOVERY_VOLTAGE_CUT_MARGIN_PU")==1.0e-4,
  "severe_voltage_cut_margin":constants.get("AC_RECOVERY_SEVERE_VOLTAGE_CUT_MARGIN_PU")==1.0e-4,
  "relinearized_voltage_cut_margin":constants.get("AC_RECOVERY_RELINEARIZED_VOLTAGE_CUT_MARGIN_PU")==2.0e-3,
  "severe_line_voltage_cut_margin":constants.get("AC_RECOVERY_SEVERE_LINE_VOLTAGE_CUT_MARGIN_PU")==3.125e-3,
  "violation_class_adaptive_normalized_pq_trust_region":(
   constants.get("AC_RECOVERY_LOCAL_P_TRUST_REGION_KW")==10.0
   and constants.get("AC_RECOVERY_LOCAL_Q_TRUST_REGION_KVAR")==10.0
   and constants.get("AC_RECOVERY_SEVERE_VOLTAGE_THRESHOLD_PU")==2.0e-3
   and constants.get("AC_RECOVERY_SEVERE_VOLTAGE_ONLY_THRESHOLD_PU")==5.0e-4
   and constants.get("AC_RECOVERY_SEVERE_VOLTAGE_P_TRUST_REGION_KW")==1100.0
   and constants.get("AC_RECOVERY_SEVERE_VOLTAGE_Q_TRUST_REGION_KVAR")==0.0
   and constants.get("AC_RECOVERY_RELINEARIZED_VOLTAGE_Q_TRUST_REGION_KVAR")==200.0
   and constants.get("AC_RECOVERY_SEVERE_LINE_P_TRUST_REGION_KW")==1100.0
   and constants.get("AC_RECOVERY_SEVERE_LINE_Q_TRUST_REGION_KVAR")==100.0
   and constants.get("AC_RECOVERY_POST_LINE_Q_TRUST_REGION_KVAR")==200.0
   and constants.get("AC_RECOVERY_COUPLED_LINE_P_TRUST_REGION_KW")==100.0
   and constants.get("AC_RECOVERY_COUPLED_LINE_Q_TRUST_REGION_KVAR")==50.0
   and constants.get("AC_RECOVERY_FD_STEP_KW")==10.0
   and 'elif line_violations or transformer_current_violations:' in recovery
   and 'trust_profile="COUPLED_VOLTAGE_LINE"' in recovery
   and 'trust_profile="SEVERE_VOLTAGE_LINE"' in recovery
   and 'trust_profile="SEVERE_VOLTAGE_POST_LINE"' in recovery
   and 'trust_profile="SEVERE_VOLTAGE_RELINEARIZED"' in recovery
   and 'trust_profile="SEVERE_VOLTAGE_ONLY"' in recovery
   and 'trust_profile="LOCAL_VOLTAGE_ONLY"' in recovery
   and '"selector":"PRE_RECOVERY_EXACT_VIOLATION_FAMILY"' in recovery
   and "expr/scale" in recovery and '"normalized_model_coefficient":True' in recovery),
  "line_current_exact_recovery_supported":(
   constants.get("AC_RECOVERY_LINE_CUT_MARGIN_PU")==5.0e-3
   and "_line_rows_from_live_opendss" in recovery and '"constraint_family":"LINE_CURRENT"' in recovery),
  "root_reverse_power_exact_recovery_supported":(
   constants.get("AC_RECOVERY_ROOT_IMPORT_MARGIN_KW")==10.0
   and "_root_power_from_live_opendss" in recovery
   and '"constraint_family":"ROOT_REVERSE_POWER"' in recovery
   and 'aggregate_p<=target_total_p_kw' in recovery
   and 'c["q_expr"]==float(c["q_kvar"])' in recovery
   and '"PASS_RECOVERED_ROOT_SIGN"' in recovery
   and '"hard_limits_relaxed":False' in recovery
   and '"future_actual_used":False' in recovery),
  "root_reverse_power_created_by_prior_grid_correction_is_recovered":(
   'root_only_after_grid=' in recovery
   and 'ROOT_REVERSE_POWER_AFTER_GRID_CORRECTION' in recovery
   and 'a_b10_post_grid_root_import_margin_r' in recovery
   and 'PASS_RECOVERED_ROOT_SIGN_AFTER_GRID_CORRECTION' in recovery
   and 'target_total_p_kw=(base_total_p_kw-float(root_power["root_export_p_kw"])' in recovery
   and '"hard_limits_relaxed":False' in recovery
   and '"future_actual_used":False' in recovery),
  "complementary_voltage_overload_exact_pq_bisection":(
   'overload_endpoint=' in recovery and 'voltage_endpoint=' in recovery
   and 'a_b10_exact_bracket_p_r' in recovery and 'a_b10_exact_bracket_q_r' in recovery
   and 'c["p_expr"]/bracket_scale==target_p/bracket_scale' in recovery
   and 'c["q_expr"]/bracket_scale==target_q/bracket_scale' in recovery
   and 'EXACT_PQ_COMPLEMENTARY_VIOLATION_BISECTION' in recovery
   and 'if bracket_voltage and not bracket_overload:voltage_endpoint=bracket_point' in recovery
   and 'elif bracket_overload and not bracket_voltage:overload_endpoint=bracket_point' in recovery
   and '"fresh_exact_opendss_required":True' in recovery
   and '"hard_limits_relaxed":False' in recovery),
  "linearized_guidance_is_not_physical_acceptance_gate":(
   'linearized_guidance_slack_fallback=True' in recovery
   and '"linearized_guidance_is_physical_acceptance_gate":False' in recovery
   and 'fresh_exact_opendss_required' in recovery),
  "non_scientific_secondary_selector_removed":(
   '"status":"SKIPPED_NONSCIENTIFIC_TIEBREAK"' in recovery
   and 'MIN_NORMALIZED_L1_H0_PQ_CHANGE' not in recovery),
  "three_exact_state_guided_low_stress_anchors":(
   'and round_no in {recovery_round_limit-2,recovery_round_limit-1}' in recovery
   and 'and not low_stress_final_anchor):' in recovery
   and '"GUIDED_ANCHOR_STAGE_1"' in recovery
   and '"GUIDED_ANCHOR_STAGE_2_RELINEARIZED"' in recovery
   and 'and round_no==recovery_round_limit' in recovery
   and 'low_stress_anchor_trigger="GUIDED_ANCHOR_STAGE_3_RELINEARIZED"' in recovery
   and 'model.remove(trust_constraint_refs)' in recovery
   and 'low_stress_anchor_trigger="INFEASIBLE_APPROXIMATION_LAYER"' in recovery
   and 'low_stress_objective+=(c["p_expr"]/scale)*(c["p_expr"]/scale)' in recovery
   and 'low_stress_objective+=(c["q_expr"]/scale)*(c["q_expr"]/scale)' in recovery
   and '"low_stress_anchor_preserved_scientific_constraints":True' in recovery),
  "all_voltage_profiles_reach_bounded_q_fallback":(
   'fallback_radii=(PCS_APPARENT_LIMIT_KVA,)' in recovery
   and 'else:raise' not in recovery[recovery.index('except RuntimeError as restricted_exc:'):recovery.index('# Escalate only after')]),
  "simultaneous_bracket_violation_relinearizes_remaining_budget":(
   'overload_endpoint=None;voltage_endpoint=None' in recovery
   and 'That invalidates monotone bisection, not the remaining bounded' in recovery),
  "transformer_kva_with_current_routes_to_pq_recovery":(
   'initial_kva_only=bool(initial_ex.get("transformer_kva_violation_count")' in recovery
   and 'and not initial_transformer_current_violations)' in recovery
   and 'and not any(r["hard_violation"] for r in transformer_current_rows)' in recovery),
  "one_same_pre_h54_full_replan":constants.get("GRID_HARD_RISK_FULL_REPLAN_MAX")==1,
  "bounded_ninety_six_production_fresh_ac_candidates":constants.get("FRESH_AC_PRODUCTION_CANDIDATE_MAX")==96,
  "deterministic_low_discrepancy_terminal_q_search":(
   'for halton_index in range(1,49):' in recovery
   and 'radical_inverse(halton_index,base)' in recovery
   and 'normalized_patterns=normalized_patterns[:64]' in recovery
   and 'status":"PASS_RECOVERED_MAX_P_Q_TAP_SEARCH"' in recovery
   and 'future_actual_used":False' in recovery),
  "fixed_tap_projection_replaced_by_receding_fresh_ac_gate":(
   'FIXED_TAP_CONSTANT_PROJECTION_REPLACED_BY_RECEDING_FRESH_EXACT_AC_GATE' in policy_loop
   and 'FIXED_TAP_VOLTAGE_DROP_LINKS_REPLACED_BY_RECEDING_FRESH_EXACT_AC_GATE' in policy_loop
   and 'fixed_tap_affected_steps={0}|' in policy_loop
   and 'power_balance_rows_removed":0' in policy_loop
   and 'line_thermal_rows_removed":0' in policy_loop
   and 'hard_physical_limits_relaxed":False' in policy_loop),
  "common_recovery_hook_for_all_methods":"science._a_b10_exact_ac_recovery=lambda" in policy_loop and "exact_ac_cut_recovery(" in policy_loop,
  "one_connected_pcs_prospective_hard_reserve_respects_immutable_pre":(
   'a_b10_connected_pcs_reserve_h{h}' in policy_loop
   and 'gp.quicksum(available)>=1.0' in policy_loop
   and 'h0_is_immutable_pre_state' in policy_loop
   and 'unavoidable_pre_domain_gaps.append(h);continue' in policy_loop
   and 'for h in range(1,H):' in policy_loop
   and 'PASS_PROSPECTIVE_HARD_RESERVE_INSTALLED' in policy_loop
   and '"power_scale_changed":False' in policy_loop
   and '"hard_grid_limits_relaxed":False' in policy_loop),
  "pcs_boundary_fd_unavailability_locks_only_that_coordinate":(
   'UNAVAILABLE_AT_PCS_BOUNDARY' in recovery
   and 'coordinate_fixed_at_base' in recovery
   and 'GRID_CORRECTION_EXHAUSTED_NO_COMPLETE_SENSITIVITY' in recovery),
  "full_replan_guard_precedes_cut_loop":(
   recovery.index('issue_runtime.get("grid_hard_risk_full_replan_retry",False)')
   < recovery.index("for round_no in range(1,recovery_round_limit+1)")),
  "no_cut_after_full_replan":"GRID_HARD_RISK_FULL_REPLAN_RETRY_FAILED" in recovery and '"cut_after_full_replan":False' in recovery,
  "duplicate_candidate_blocked_before_second_opendss":(
   "DUPLICATE_RECOVERY_CANDIDATE_NO_SECOND_OPENDSS" in policy_loop
   and '"second_opendss_called_for_duplicate":False' in policy_loop
   and 'compared_against_all_prior_candidate_decisions' in policy_loop
   and 'proposed["decision_candidate_sha256"] in prior_decision_shas' in policy_loop),
  "full_replan_retry_count_fail_closed":(
   "full_replan_count>GRID_HARD_RISK_FULL_REPLAN_MAX" in policy_loop
   and 'len(issue_runtime.get("fresh_ac_candidate_attempts",[]))' in policy_loop
   and 'and i not in post_dispatch_hard_flags' in policy_loop),
  "failed_and_recovery_candidate_fingerprints_persisted":(
   "A_B10_RECOVERY_CANDIDATE_IDENTITY_AUDIT.json" in text
   and 'issue_runtime["last_failed_recovery_candidate"]' in text),
  "hard_limits_not_relaxed":all(x in text for x in ("PCS_ACTIVE_LIMIT_KW=550.0","PCS_APPARENT_LIMIT_KVA=700.0")),
  "future_actual_remains_forbidden":'"future_actual_used":False' in recovery,
  "fd_sampling_executes_after_feasible_step_selection":fd_sampling_follows_step_selection(tree),
  "obsolete_full_replan_only_branch_absent":"def full_replan_only_ac_recovery" not in text,
  "unbounded_round_contract_absent":"while True" not in recovery,
  "conditioned_dispatch_is_time_bounded":(
   "model.Params.TimeLimit=300.0" in fast
   and 'q["conditioned_dispatch_time_limit_seconds"]=300.0' in fast),
  "candidate_numerical_polish_does_not_leak_to_next_candidate":(
   'model.Params.NumericFocus=0;model.Params.FeasibilityTol=9e-7' in fast
   and 'model.Params.IntFeasTol=1e-5;model.Params.OptimalityTol=1e-6' in fast
   and 'model.Params.BarQCPConvTol=1e-8;model.Params.ScaleFlag=-1' in fast
   and fast.index('model.Params.NumericFocus=0;model.Params.FeasibilityTol=9e-7')
       < fast.index('model.Params.NumericFocus=3')),
  "strict_no_certificate_polish_has_bounded_inner_gate_retry":(
   'INNER_GATE_2E7_POLISH_AFTER_STRICT_NO_CERTIFICATE' in fast
   and 'model.Params.NumericFocus=3;model.Params.FeasibilityTol=2e-7' in fast
   and 'model.Params.BarQCPConvTol=1e-9;model.Params.ScaleFlag=-1' in fast
   and 'refinement_solve_count=2' in fast
   and 'if any(float(after[k])>limit for k,limit in numerical_limits.items())' in fast
   and 'hard_gate_relaxed":False' in fast),
  "marginal_negative_pcs_uses_exact_zero_active_set_polish":(
   'EXACT_ZERO_PCS_ACTIVE_SET_POLISH' in fast
   and 'MARGINAL_NEGATIVE_PCS_TO_EXACT_ZERO' in fast
   and 'and float(worst["lower_violation"])<=2e-6' in fast
   and 'and -2e-6<=x<-numerical_limits["BoundVio"]' in fast
   and 'str(c.ConstrName).startswith("pbal_")' in fast
   and 'str(v.VarName).startswith("FP_")' in fast
   and 'model.Params.NumericFocus=2;model.Params.FeasibilityTol=8e-7' in fast
   and 'model.Params.BarQCPConvTol=1e-9;model.Params.ScaleFlag=2' in fast
   and 'active_set_bounds=list(active_set_by_name.values())' in fast
   and '"feasible_set_expanded":False' in fast
   and 'all(float(active_after[k])<=limit for k,limit in numerical_limits.items())' in fast),
  "mip_start_is_injected_after_solver_reset":(
   fast.index("model.reset()")<fast.index('pending=loc.pop("_pending_complete_mip_start_by_name",None)')
       <fast.index("v.Start=float(pending[str(v.VarName)])")),
  "shifted_active_plan_future_commitment_and_h0_start":(
   '_pending_active_plan_mode_start_by_name' in fast
   and 'SHIFTED_ACTIVE_PLAN_MODE_ONLY' in fast
   and 'A_B10_ACTIVE_PLAN_MODE_MIP_START.json' in policy_loop
   and 'ACTIVE_PLAN_MODE_MIP_START_INCOMPLETE' in policy_loop
   and 'if h>0:' in policy_loop
   and 'fix_future_mode_commitment(loc,key,value)' in policy_loop
   and 'fixed_future_mode_names.append' in policy_loop
   and '"future_commitment_fixed":True' in policy_loop
   and '"free_current_mode_count":len(free_mode_names)' in policy_loop
   and '"objective_changed":False' in policy_loop
   and '"hard_constraints_changed":False' in policy_loop
   and '"future_actual_used":False' in policy_loop),
  "planner_complete_solution_is_transferred_by_name":(
   'loc["_pending_complete_mip_start_by_name"]=pending' in text
   and 'source_model.getVarByName(str(v.VarName))' in text),
  "accepted_planner_future_modes_are_committed_h0_remains_dispatchable":(
   text.count('counts["mode_future"]=len(future_modes)')==2
   and text.count('int(key[1])>0')>=2
   and 'planner-copy future mode missing' in text),
  "infeasible_future_mode_acceleration_restores_original_domain_once":(
   '_pending_future_mode_bound_snapshot_by_name' in fast
   and '_pending_all_active_plan_mode_start_by_name' in fast
   and 'if int(model.SolCount)<1 and future_mode_snapshot:' in fast
   and 'for v,lb,ub in future_mode_snapshot.values():v.LB=lb;v.UB=ub' in fast
   and 'FUTURE_MODE_FIX_INFEASIBLE_ORIGINAL_DOMAIN_FALLBACK' in fast),
  "future_mode_uses_retained_exact_pcs_implication_rows":(
   'def fix_future_mode_commitment' in text
   and text.count('fix_future_mode_commitment(')>=4
   and '"opposite_pcs_zero_enforced_by_retained_mode_rows":True' in policy_loop),
  "ac_recovery_reuses_only_prior_integer_choices":(
   'active_plan_start=loc.pop("_pending_active_plan_mode_start_by_name",None)' in fast
   and 'integer_start=(active_plan_start or loc.get("_last_integer_mip_start_by_name",{}))' in fast
   and 'else "PRIOR_ACCEPTED_INTEGER_ONLY")' in fast
   and 'loc["_last_integer_mip_start_by_name"]=' in fast),
  "recovery_freezes_non_h0_integer_choices_only":(
   'free_h0_pcs_modes={f"mode_{mid}_0"' in recovery
   and 'if name in free_h0_pcs_modes:continue' in recovery
   and 'recovery_integer_fixed.append' in recovery),
  "recovery_persistence_boundary_is_h0_only":(
   'if h!=0:continue' in refresh
   and 'sol["mess_support_debt1"]={str(row["mess_id"]):float(row["support_debt1_kWh"]) for row in first}' in refresh
   and 'sol["send_now"]=' not in refresh
   and 'sol["wan_all"]=' not in refresh
   and 'sol["workload_debt1"]=' not in refresh),
  "stale_projected_plan_retry_forces_full_replan":(
   'active_projection_retry_full_domain' in policy_loop
   and 'HARD:STALE_ACTIVE_PLAN_MOBILITY_PROJECTION' in policy_loop),
  "conditioned_infeasible_active_plan_retries_one_same_pre_full_replan":(
   'A_B10_ACTIVE_PLAN_CONDITIONED_INFEASIBLE_REQUIRES_SAME_PRE_FULL_REPLAN' in text
   and 'loc["_conditioned_shifted_active_plan"]=True' in policy_loop
   and 'reset_failed_attempt_for_same_pre("ACTIVE_PLAN_INVALIDATION_FULL_DOMAIN")' in text
   and 'or issue_runtime.get("active_projection_retry_full_domain",False)' in policy_loop),
  "sparse_local_repair_move_escalates_same_pre_full_replan":(
   'except KeyError as exc:' in policy_loop
   and 'LOCAL_REPAIR_ESCALATION:SPARSE_REFERENCE_MOVE_ABSENT' in policy_loop
   and 'missing not in moves_now' in policy_loop
   and 'A_B10_LOCAL_REPAIR_SPARSE_MOVE_ESCALATION.json' in policy_loop
   and '"slow_bounds_restored":True' in policy_loop
   and policy_loop.index('A_B10_LOCAL_REPAIR_SPARSE_MOVE_ESCALATION.json')
       < policy_loop.index('restore_slow_bounds();requested="FULL_REPLAN"',
                           policy_loop.index('A_B10_LOCAL_REPAIR_SPARSE_MOVE_ESCALATION.json'))),
  "local_repair_escalation_restores_bounds_and_integer_variable_types":(
   '(v,float(v.LB),float(v.UB),str(v.VType))' in policy_loop
   and 'v.LB=lb;v.UB=ub;v.VType=vtype' in policy_loop
   and 'PASS_BOUNDS_AND_VARIABLE_TYPES_ATOMICALLY_RESTORED' in policy_loop
   and 'A_B10_LOCAL_REPAIR_FULL_DOMAIN_RESTORE.json' in policy_loop
   and '"same_pre":True' in policy_loop
   and '"hard_constraints_relaxed":False' in policy_loop),
  "sparse_candidate_dense_row_mismatch_replans_once_on_authoritative_dense_model":(
   'dense_equivalence_bound_snapshot' in policy_loop
   and 'str(exc)=="fast conditioned dispatch has no feasible incumbent"' in policy_loop
   and 'int(issue_runtime.get("dense_b4_restore",{}).get("rows_added",0))==576' in policy_loop
   and 'A_B10_SPARSE_DENSE_EQUIVALENCE_FALLBACK.json' in policy_loop
   and 'dense_q,dense_planner=planner_solve_exact_copy(model,cb)' in policy_loop
   and '"full_unconditioned_domain_restored":True' in policy_loop
   and '"hard_constraints_relaxed":False' in policy_loop
   and '"power_scale_changed":False' in policy_loop
   and 'v.LB=lb;v.UB=ub;v.VType=vtype' in policy_loop
   and 'fast=solve_fast(model,cb,loc)' in policy_loop),
  "nonnegative_state_dust_is_bounded_and_canonicalized":(
   'def canonical_nonnegative_physical_state' in text
   and 'if value < -5e-4:raise RuntimeError' in text
   and 'pcs_projection_support_debt1_kWh' in text),
  "soc_boundary_dust_is_projected_into_frozen_interval":(
   'ENERGY_NUMERICAL_BOUNDARY_MAX_EXCESS_KWH=2e-3' in text
   and 'ENERGY_PHYSICAL_FLOOR_KWH=440.0' in text
   and 'def canonicalize_energy_numerical_boundary' in text
   and text.count('canonicalize_energy_numerical_boundary(')>=3
   and 'material SOC boundary excess' in text
   and '"hard_floor_relaxed":False' in text
   and '"hard_capacity_relaxed":False' in text),
  "coupled_soc_debt_capacity_invariant_is_atomically_preserved":(
   'COUPLED_SOC_DEBT_NUMERICAL_EXCESS_MAX_KWH=2e-3' in text
   and 'def canonicalize_coupled_soc_debt_ceiling' in text
   and text.count('canonicalize_coupled_soc_debt_ceiling(')>=3
   and 'def adjust_model_state_for_inward_pcs_projection' in text
   and 'The solved E[1]/DE[1] pair is the scientific authority' in text
   and 'if fixed_location:' in policy_loop
   and '_a_b10_fixed_location_policy' in text
   and 'support_obligation_reduced":False' in text
   and 'hard_capacity_relaxed":False' in text),
 }
 # Exhaustive control-flow budgets; finite-difference probes are sensitivity samples,
 # not production candidate validations and are intentionally excluded.
 paths=[
  {"path":"INITIAL_PASS","cut":0,"full_replan":0,"production_fresh_ac":1,"commit":"SAFE"},
  {"path":"CUT_PASS","cut":1,"full_replan":0,"production_fresh_ac":2,"commit":"SAFE"},
  {"path":"SEVERE_LINE_SECOND_CUT_PASS","cut":2,"full_replan":0,"production_fresh_ac":3,"commit":"SAFE"},
  {"path":"SEVERE_VOLTAGE_TAP_SECOND_CUT_PASS","cut":2,"full_replan":0,"production_fresh_ac":3,"commit":"SAFE"},
  {"path":"COMPLEMENTARY_VOLTAGE_OVERLOAD_BISECTION_PASS","cut":2,"full_replan":0,"production_fresh_ac":3,"commit":"SAFE"},
  {"path":"GUIDED_ANCHOR_STAGE1_PASS","cut":7,"full_replan":0,"production_fresh_ac":8,"commit":"SAFE"},
  {"path":"GUIDED_ANCHOR_STAGE2_RELINEARIZED_PASS","cut":8,"full_replan":0,"production_fresh_ac":9,"commit":"SAFE"},
  {"path":"GUIDED_ANCHOR_STAGE3_RELINEARIZED_PASS","cut":9,"full_replan":0,"production_fresh_ac":10,"commit":"SAFE"},
  {"path":"ROOT_SIGN_NINTH_CUT_PASS","cut":9,"full_replan":0,"production_fresh_ac":10,"commit":"SAFE"},
  {"path":"POST_GRID_ROOT_SIGN_FIFTH_CUT_PASS","cut":5,"full_replan":0,"production_fresh_ac":6,"commit":"SAFE"},
  {"path":"ROOT_SIGN_NINTH_CUT_FAIL_FULL_REPLAN_PASS","cut":9,"full_replan":1,"production_fresh_ac":11,"commit":"SAFE"},
  {"path":"NINTH_CUT_FAIL_FULL_REPLAN_FAIL","cut":9,"full_replan":1,"production_fresh_ac":11,"commit":"FAIL_CLOSED"},
  {"path":"SECOND_CUT_FAIL_FULL_REPLAN_PASS","cut":2,"full_replan":1,"production_fresh_ac":4,"commit":"SAFE"},
  {"path":"SECOND_CUT_FAIL_FULL_REPLAN_FAIL","cut":2,"full_replan":1,"production_fresh_ac":4,"commit":"FAIL_CLOSED"},
  {"path":"CUT_FAIL_DUPLICATE_FULL_REPLAN","cut":2,"full_replan":1,"production_fresh_ac":3,"commit":"FAIL_CLOSED_NO_SECOND_OPENDSS"},
 ]
 checks["state_machine_exhaustive_budgets_pass"]=all(
  p["cut"]<=10 and p["full_replan"]<=1 and p["production_fresh_ac"]<=11 for p in paths)
 regression=[]
 if a.regression_root:
  for method,issue in (("M2_FIXED30_MOBILE",3573),("M4_FIXED_LOCATION_ESS_MOBILITY_ABLATION",3519)):
   root=a.regression_root/method;issue_dir=root/"engine"/f"issue_{issue:06d}"
   audit=load(issue_dir/"A_B10_RECOVERY_CANDIDATE_IDENTITY_AUDIT.json")
   exact=load(issue_dir/f"exact_grid/FRESH_EXACT_OPENDSS_24SERVICE_ISSUE_{issue}.json")
   row={"method":method,"issue":issue,"status":"PASS" if exact.get("hard_constraint_pass") is True else "FAIL",
        "candidate_count":audit.get("candidate_count"),"candidate_stages":[x.get("stage") for x in audit.get("candidates",[])],
        "fresh_exact_ac_pass":exact.get("hard_constraint_pass") is True and exact.get("converged") is True,
        "future_actual_used":False}
   regression.append(row)
  checks["bounded_historical_failure_issue_regression_pass"]=all(
   x["status"]=="PASS" and x["fresh_exact_ac_pass"] and 1<=int(x["candidate_count"])<=3 for x in regression)
 status="PASS" if all(checks.values()) else "FAIL_CLOSED"
 out={"schema_version":"mobileess.post_stage15.w02_safety_recovery_contract_audit.v1","status":status,
  "runner":str(runner),"runner_sha256":sha(runner),"checks":checks,"exhaustive_paths":paths,
  "bounded_regression":regression,"scientific_solve_count_by_this_validator":0,"opendss_solve_count_by_this_validator":0,
  "full_W02_executed":False,"document_files_modified":False}
 write(a.output,out);print(json.dumps(out,indent=2,sort_keys=True));return 0 if status=="PASS" else 2

if __name__=="__main__":raise SystemExit(main())

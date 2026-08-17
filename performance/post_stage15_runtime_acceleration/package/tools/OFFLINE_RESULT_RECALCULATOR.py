#!/usr/bin/env python3
"""Independent post-run arithmetic audit. It never imports or executes simulator code."""
from __future__ import annotations
import argparse,csv,hashlib,json,math
from pathlib import Path

def load(p:Path):return json.loads(p.read_text(encoding="utf-8"))
def digest(p:Path):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p:Path,x):
 p.parent.mkdir(parents=True,exist_ok=True);t=p.with_suffix(p.suffix+".tmp")
 t.write_text(json.dumps(x,indent=2,sort_keys=True,allow_nan=False)+"\n");t.replace(p)

def csvrows(p:Path)->list[dict]:
 if not p.is_file() or p.stat().st_size==0:return []
 with p.open(encoding="utf-8-sig",newline="") as fh:return list(csv.DictReader(fh))

def finite(v)->bool:return isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(float(v))

def policy(root:Path,allow_partial:bool,issue_first:int|None=None,issue_last:int|None=None)->dict:
 manifest=load(root/"episode_manifest.json");engine=root/"engine";issues=[];prior_post=None;prior_issue=None
 for d in sorted(engine.glob("issue_*")):
  marker=d/"A_B10_COMMIT_MARKER.json"
  if not marker.is_file():continue
  m=load(marker);i=int(m["issue"])
  if issue_first is not None and i<issue_first:continue
  if issue_last is not None and i>issue_last:continue
  post=load(d/"BUILD7C_POSTCOMMIT_STATE.json");pre=load(d/"BUILD7C_PRECOMMIT_STATE.json")
  tr=load(d/"BUILD7C_FIRSTSTEP_TRANSITION_CERTIFICATE.json");ac=load(d/f"exact_grid/FRESH_EXACT_OPENDSS_24SERVICE_ISSUE_{i}.json")
  audit=load(d/"POLICY_ISSUE_AUDIT.json")
  model_obs_path=d/"A_B10_COMMITTED_MODEL_OBSERVABILITY.json";exact_obs_path=d/"exact_grid/A_B10_FRESH_EXACT_AC_OBSERVABILITY.json"
  model_obs=load(model_obs_path) if model_obs_path.is_file() else {};exact_obs=load(exact_obs_path) if exact_obs_path.is_file() else {}
  checks={"marker_status":m.get("status")=="COMMITTED","post_sha":post.get("sha256")==tr.get("post_state_sha256")==m.get("post_state_sha256"),
   "pre_sha":pre.get("sha256")==tr.get("pre_state_sha256")==m.get("pre_state_sha256"),
   "transition_file_sha":digest(d/"BUILD7C_FIRSTSTEP_TRANSITION_CERTIFICATE.json")==m.get("transition_certificate_sha256"),
   "exact_file_sha":digest(d/f"exact_grid/FRESH_EXACT_OPENDSS_24SERVICE_ISSUE_{i}.json")==m.get("fresh_exact_ac_sha256"),
   "audit_file_sha":digest(d/"POLICY_ISSUE_AUDIT.json")==m.get("policy_issue_audit_sha256"),
   "model_observability_sha":(m.get("schema_version","").endswith(".v1") or (model_obs_path.is_file() and digest(model_obs_path)==m.get("model_observability_sha256"))),
   "exact_observability_sha":(m.get("schema_version","").endswith(".v1") or (exact_obs_path.is_file() and digest(exact_obs_path)==m.get("exact_ac_observability_sha256"))),
   "exact_ac":ac.get("converged") is True and ac.get("hard_constraint_pass") is True,
   "chain":prior_post is None or i!=prior_issue+1 or prior_post==pre.get("sha256")}
  ps=pre.get("state",pre);qs=post.get("state",post)
  soc0=sum(map(float,ps.get("mess_E_kWh",{}).values()));soc1=sum(map(float,qs.get("mess_E_kWh",{}).values()))
  f0=(model_obs.get("forecast_issued") or [{}])[0];root_kw=float(ac.get("root_import_p_kw") or 0.0);rrp=float(f0.get("rrp_q50") or 0.0)
  move_rows=[r for r in csvrows(d/"BUILD7B_FULL54_MOVE_ARCS_SELECTED.csv") if int(float(r["horizon_step"]))==0]
  h0={str(r["mess_id"]):r for r in csvrows(d/"BUILD7B_FULL54_MESS_PLAN.csv") if int(float(r["horizon_step"]))==0}
  repayment=(model_obs.get("debt_repayment_h0") or {}).get("support_energy_kWh",{}) or {}
  balances=[]
  for mid,e0raw in sorted((ps.get("mess_E_kWh",{}) or {}).items()):
   e0=float(e0raw);e1=float((qs.get("mess_E_kWh",{}) or {})[mid]);r=h0.get(str(mid),{})
   pchg=float(r.get("P_charge_kW") or 0.0);pdis=float(r.get("P_discharge_kW") or 0.0)
   mobility=e0+0.95*(5/60)*pchg-(5/60)*pdis/0.95-e1
   d0=float((ps.get("mess_support_debt_kWh",{}) or {}).get(mid,0.0));d1=float((qs.get("mess_support_debt_kWh",{}) or {}).get(mid,0.0))
   repaid=float(repayment.get(mid,0.0));debt_expected=d0+(5/60)*pdis/0.95-repaid
   balances.append({"mess_id":str(mid),"P_charge_kW":pchg,"P_discharge_kW":pdis,
    "mobility_energy_realized_signed_kWh":mobility,"energy_balance_residual_kWh":e1-(e0+0.95*(5/60)*pchg-(5/60)*pdis/0.95-mobility),
    "support_debt_expected_kWh":debt_expected,"support_debt_actual_kWh":d1,"support_debt_residual_kWh":d1-debt_expected})
  rack_rows=model_obs.get("rack_pool_h0",[])
  rack_pass=len(rack_rows)==48 and all(finite(r.get("gpu_used")) and finite(r.get("gpu_capacity")) and float(r["gpu_used"])<=float(r["gpu_capacity"])+1e-7
   and finite(r.get("it_power_kw")) and finite(r.get("it_power_limit_kw")) and float(r["it_power_kw"])<=float(r["it_power_limit_kw"])+1e-7 for r in rack_rows)
  volt=[float(r["voltage_pu"]) for r in exact_obs.get("bus_phase_voltage",[]) if finite(r.get("voltage_pu"))]
  line=[float(r["loading_pu"]) for r in exact_obs.get("line_terminal_phase",[]) if finite(r.get("loading_pu"))]
  tx=[float(r["loading_pu"]) for r in exact_obs.get("transformer_terminal_current",[]) if finite(r.get("loading_pu"))]
  detailed_grid_pass=bool(volt and line and tx and abs(min(volt)-float(ac["voltage_min_pu"]))<=1e-9 and abs(max(volt)-float(ac["voltage_max_pu"]))<=1e-9
   and abs(max(line)-float(ac["line_max_loading_pu"]))<=1e-9 and abs(max(tx)-float(ac["transformer_max_current_loading_pu"]))<=1e-9)
  queue=list((qs.get("queue") or {}).values()) if isinstance(qs.get("queue"),dict) else list(qs.get("queue") or [])
  late_queue=sum(1 for j in queue if isinstance(j,dict) and int(j.get("latest_start_step",i+1))<i+1)
  balance_pass=all(abs(x["energy_balance_residual_kWh"])<=1e-8 and abs(x["support_debt_residual_kWh"])<=1e-6 for x in balances)
  checks.update({"mess_energy_and_support_debt_balance":balance_pass,"rack_capacity_recalculation":rack_pass,
                 "detailed_grid_extrema_recalculation":detailed_grid_pass,
                 "transition_contract":tr.get("status")=="PASS" and tr.get("h0_only_committed") is True and tr.get("future_actual_arrivals_read") is False})
  issues.append({"issue":i,"pass":all(checks.values()),"checks":checks,"pre_sha256":pre.get("sha256"),"post_sha256":post.get("sha256"),
   "soc_total_pre_kWh":soc0,"soc_total_post_kWh":soc1,"soc_delta_kWh":soc1-soc0,
   "voltage_min_pu":ac.get("voltage_min_pu"),"voltage_max_pu":ac.get("voltage_max_pu"),
   "line_max_loading_pu":ac.get("line_max_loading_pu"),"transformer_max_loading_pu":ac.get("transformer_max_kva_loading_pu"),
   "started_jobs":len(tr.get("started_jobs",[])),"completed_jobs":len(tr.get("completed_jobs",[])),
   "ac_recovered":bool((audit.get("ac_safety_recovery") or {}).get("status")=="PASS_RECOVERED"),
   "energy_procurement_cost_AUD":root_kw*(5/60)/1000*rrp,"rack_rows":len(rack_rows),"rack_capacity_pass":rack_pass,
   "wan_sent_GB":sum(float(x.get("gb_sent",0.0)) for x in model_obs.get("wan_send_h0",[])),"h0_move_count":len(move_rows),
   "mess_balances":balances,"queue_post_count":len(queue),"late_queue_post_count":late_queue,"running_post_count":len(qs.get("running",{})),
   "completed_total_post_count":len(qs.get("completed",{})),"workload_debt_pre_GPUh":sum(map(float,(ps.get("workload_debt_GPUh",{}) or {}).values())),
   "workload_debt_post_GPUh":sum(map(float,(qs.get("workload_debt_GPUh",{}) or {}).values())),
   "support_debt_pre_kWh":sum(map(float,(ps.get("mess_support_debt_kWh",{}) or {}).values())),
   "support_debt_post_kWh":sum(map(float,(qs.get("mess_support_debt_kWh",{}) or {}).values())),
   "commit_critical_runtime_s":audit.get("commit_critical_runtime_s"),"full_issue_wall_s":audit.get("full_issue_wall_s"),
   "planner_mode":audit.get("planner_mode"),"comparison_method_id":audit.get("comparison_method_id"),
   "causal_exogenous_identity":audit.get("causal_exogenous_identity")})
  prior_post=post.get("sha256");prior_issue=i
 required=int(manifest.get("scored_issues",2016));complete=len(issues)==required
 passed=bool(issues and all(x["pass"] for x in issues) and (allow_partial or complete))
 policy_id=manifest.get("policy_id");method=load(root/"RESULT_EPISODE_INDEX.json").get("comparison_method_id")
 invariant=(all(x["planner_mode"]!="LOCAL_REPAIR" for x in issues) if method in {"M2","M3"} else True)
 if method=="M4":invariant=invariant and all(x["h0_move_count"]==0 for x in issues)
 return {"policy_root":str(root),"candidate_id":manifest.get("candidate_id"),"policy_id":policy_id,
  "comparison_method_id":method,"committed_issues":len(issues),"policy_invariant_pass":invariant,
  "required_issues":required,"complete":complete,"pass":passed and invariant,"vmin":min((x["voltage_min_pu"] for x in issues),default=None),
  "vmax":max((x["voltage_max_pu"] for x in issues),default=None),"recovery_count":sum(x["ac_recovered"] for x in issues),
  "controller_action_counts":{"NONE":sum(x["planner_mode"]=="NONE" for x in issues),"LOCAL_REPAIR":sum(x["planner_mode"]=="LOCAL_REPAIR" for x in issues),
   "FULL_REPLAN":sum(x["planner_mode"]=="FULL_REPLAN" for x in issues),"h0_moves":sum(x["h0_move_count"] for x in issues)},
  "runtime_summary":{"commit_critical_total_s":sum(float(x["commit_critical_runtime_s"] or 0) for x in issues),
   "full_issue_total_s":sum(float(x["full_issue_wall_s"] or 0) for x in issues)},"issues":issues}

def main():
 a=argparse.ArgumentParser();a.add_argument("delivery_root",type=Path);a.add_argument("--allow-partial",action="store_true");a.add_argument("--output",type=Path)
 a.add_argument("--issue-first",type=int);a.add_argument("--issue-last",type=int);x=a.parse_args()
 roots=[p for p in sorted(x.delivery_root.iterdir()) if (p/"episode_manifest.json").is_file()]
 if not roots and (x.delivery_root/"episode_manifest.json").is_file():roots=[x.delivery_root]
 reports=[policy(p,x.allow_partial,x.issue_first,x.issue_last) for p in roots];by_issue={}
 for r in reports:
  for i in r["issues"]:by_issue.setdefault(i["issue"],{})[r["policy_id"]]=i.get("causal_exogenous_identity")
 policy_ids=[r["policy_id"] for r in reports]
 fairness={}
 for issue,values in sorted(by_issue.items()):
  aligned=all(p in values for p in policy_ids)
  if aligned:
   identities=[values[p] for p in policy_ids]
   passed=None not in identities and len(set(identities))==1
   fairness[str(issue)]={"status":"PASS" if passed else "FAIL","pass":passed,"aligned_policy_count":len(identities),"required_policy_count":len(policy_ids)}
  else:
   fairness[str(issue)]={"status":"NOT_EVALUATED_IN_UNALIGNED_BOUNDED_SAMPLE","pass":None,"aligned_policy_count":len(values),"required_policy_count":len(policy_ids)}
 evaluated=[v["pass"] for v in fairness.values() if v["pass"] is not None]
 fairness_pass=all(evaluated) if evaluated else None
 individual_pass=bool(reports and all(r["pass"] for r in reports))
 complete=bool(reports and all(r["complete"] for r in reports))
 if individual_pass and complete and fairness_pass is True:status="PASS"
 elif individual_pass and x.allow_partial and fairness_pass is not False:status="PASS_BOUNDED_INDIVIDUAL_EVIDENCE"
 else:status="FAIL_CLOSED"
 out={"schema_version":"mobileess.offline_independent_recalculator.v1","status":status,
  "production_result_writer_imported":False,"gurobi_solve_count":0,"opendss_solve_count":0,"simulation_rerun_count":0,
  "production_authority":status=="PASS","bounded_partial_authority":status=="PASS_BOUNDED_INDIVIDUAL_EVIDENCE",
  "cross_method_exogenous_identity":{"overall_pass":fairness_pass,"evaluated_issue_count":len(evaluated),"issues":fairness},"policies":reports}
 out["issue_filter"]={"first":x.issue_first,"last":x.issue_last}
 target=x.output or x.delivery_root/"OFFLINE_INDEPENDENT_RECALCULATION.json";write(target,out);print(target);return 0 if status.startswith("PASS") else 2
if __name__=="__main__":raise SystemExit(main())

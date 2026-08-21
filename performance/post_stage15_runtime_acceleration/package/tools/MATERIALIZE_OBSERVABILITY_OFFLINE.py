#!/usr/bin/env python3
"""Materialize committed same-solve evidence; never invokes Gurobi or OpenDSS."""
from __future__ import annotations
import argparse,csv,hashlib,json,math,time
from pathlib import Path
from typing import Any
import pandas as pd

def load(p:Path):return json.loads(p.read_text(encoding="utf-8"))
def digest(p:Path):return hashlib.sha256(p.read_bytes()).hexdigest()
def csvrows(p:Path):
 if not p.is_file() or p.stat().st_size==0:return []
 with p.open(encoding="utf-8-sig",newline="") as f:return list(csv.DictReader(f))
def f(v,default=None):
 try:return float(v)
 except (TypeError,ValueError):return default
def atomic_json(p:Path,x:Any):
 p.parent.mkdir(parents=True,exist_ok=True);t=p.with_suffix(p.suffix+".tmp")
 t.write_text(json.dumps(x,indent=2,sort_keys=True,allow_nan=False)+"\n",encoding="utf-8");t.replace(p)

REQUIRED_FINITE={
 "grid_bus_phase":("voltage_pu","angle_deg"),
 "grid_line_terminal_phase":("p_kw","q_kvar","current_a","angle_deg","norm_amps","loading_pu"),
 "grid_transformer_terminal_phase":("p_kw","q_kvar","current_a","angle_deg","rated_kva","rated_kv","rated_phase_current_a","loading_pu"),
 "mess_physical_step":("P_charge_kW","P_discharge_kW","P_net_kW","Q_kvar","SOC_pre_kWh","SOC_post_kWh","mobility_energy_realized_signed_kWh","support_debt_post_kWh"),
 "rack_pool_step":("fixed_gpu","fixed_it_power_kw","gpu_used","it_power_kw","facility_power_kw","gpu_capacity","it_power_limit_kw","transformer_limit_kw","gpu_headroom","it_power_headroom_kw"),
 "forecast_issued":("gross_background_p_q90_kw","pv_available_q10_kw","net_background_p_q50_kw","background_q_q50_kvar","background_q_q90_kvar","rrp_q10","rrp_q50","rrp_q90"),
 "debt_rebound_step":("workload_debt_pre_GPUh","workload_debt_post_GPUh","support_debt_pre_kWh","support_debt_post_kWh"),
 "objective_breakdown":("economic_projected_AUD","model_obj_val"),
}

UNITS={
 "voltage_pu":"pu","angle_deg":"degree","p_kw":"kW","q_kvar":"kvar","current_a":"A","rated_kva":"kVA","rated_kv":"kV",
 "P_charge_kW":"kW","P_discharge_kW":"kW","P_net_kW":"kW","Q_kvar":"kvar","SOC_pre_kWh":"kWh","SOC_post_kWh":"kWh",
 "mobility_energy_realized_signed_kWh":"kWh","support_debt_post_kWh":"kWh","fixed_it_power_kw":"kW","it_power_kw":"kW",
 "facility_power_kw":"kW","it_power_limit_kw":"kW","transformer_limit_kw":"kW","it_power_headroom_kw":"kW",
 "gross_background_p_q90_kw":"kW","pv_available_q10_kw":"kW","net_background_p_q50_kw":"kW","background_q_q50_kvar":"kvar",
 "background_q_q90_kvar":"kvar","rrp_q10":"AUD/MWh","rrp_q50":"AUD/MWh","rrp_q90":"AUD/MWh",
 "workload_debt_pre_GPUh":"GPUh","workload_debt_post_GPUh":"GPUh","support_debt_pre_kWh":"kWh","support_debt_post_kWh":"kWh",
 "economic_projected_AUD":"AUD","model_obj_val":"AUD","loading_pu":"pu","norm_amps":"A","rated_phase_current_a":"A",
 "fixed_gpu":"GPU","gpu_used":"GPU","gpu_capacity":"GPU","gpu_headroom":"GPU"
}

def finite_audit(name:str,rows:list[dict])->dict[str,Any]:
 cols=REQUIRED_FINITE.get(name,());bad={}
 for col in cols:
  count=sum(1 for row in rows if isinstance(row.get(col),bool) or not isinstance(row.get(col),(int,float)) or not math.isfinite(float(row[col])))
  if count:bad[col]=count
 return {"required_numeric_columns":list(cols),"invalid_or_missing":bad,"pass":not bad}
def valid_marker(d:Path)->dict:
 m=load(d/"A_B10_COMMIT_MARKER.json");i=int(m["issue"])
 required={"transition_certificate_sha256":d/"BUILD7C_FIRSTSTEP_TRANSITION_CERTIFICATE.json",
  "fresh_exact_ac_sha256":d/f"exact_grid/FRESH_EXACT_OPENDSS_24SERVICE_ISSUE_{i}.json",
  "policy_issue_audit_sha256":d/"POLICY_ISSUE_AUDIT.json",
  "exact_ac_observability_sha256":d/"exact_grid/A_B10_FRESH_EXACT_AC_OBSERVABILITY.json",
  "model_observability_sha256":d/"A_B10_COMMITTED_MODEL_OBSERVABILITY.json"}
 if m.get("schema_version")!="mobileess.post_stage15.atomic_commit_marker.v2" or m.get("status")!="COMMITTED":
  raise RuntimeError(f"OBSERVABILITY_REQUIRES_V2_COMMIT_MARKER issue={i}")
 for key,p in required.items():
  if not p.is_file() or digest(p)!=m.get(key):raise RuntimeError(f"OBSERVABILITY_SHA_MISMATCH issue={i} file={p.name}")
 return m
def physical_mess_rows(i:int,d:Path)->list[dict]:
 pre=load(d/"BUILD7C_PRECOMMIT_STATE.json").get("state",{});post=load(d/"BUILD7C_POSTCOMMIT_STATE.json").get("state",{})
 plan={str(r["mess_id"]):r for r in csvrows(d/"BUILD7B_FULL54_MESS_PLAN.csv") if int(float(r["horizon_step"]))==0}
 move={str(r["mess_id"]):r for r in csvrows(d/"BUILD7B_FULL54_MOVE_ARCS_SELECTED.csv") if int(float(r["horizon_step"]))==0}
 rows=[]
 for mid in sorted(pre.get("mess_E_kWh",{})):
  r=plan.get(mid,{});mv=move.get(mid);ps=(pre.get("mess_state",{}) or {}).get(mid,{});qs=(post.get("mess_state",{}) or {}).get(mid,{})
  pchg=f(r.get("P_charge_kW"),0.0);pdis=f(r.get("P_discharge_kW"),0.0);e0=f(pre["mess_E_kWh"][mid],0.0);e1=f(post["mess_E_kWh"][mid],0.0)
  realized=e0+0.95*(5/60)*pchg-(5/60)*pdis/0.95-e1
  rows.append({"issue_step":i,"mess_id":mid,"pre_phase":ps.get("phase"),"post_phase":qs.get("phase"),
   "source_service_id":ps.get("service_id",ps.get("source_service_id")),"destination_service_id":qs.get("dest_service_id"),
   "post_service_id":qs.get("service_id"),"route_slot":None if mv is None else mv.get("slot"),
   "route_template_id":None if mv is None else mv.get("template_id"),"departure":mv is not None,
   "arrival":ps.get("phase") in {"TRANSIT","CONNECTION_DELAY"} and qs.get("phase")=="STAY",
   "remaining_total_steps":qs.get("remaining_total_steps"),"remaining_profile_kWh":json.dumps(qs.get("remaining_profile_kWh",[])),
   "grid_connected":str(r.get("state",qs.get("phase","")))=="STAY","P_charge_kW":pchg,"P_discharge_kW":pdis,
   "P_net_kW":pdis-pchg,"Q_kvar":f(r.get("Q_kvar"),0.0),"SOC_pre_kWh":e0,"SOC_post_kWh":e1,
   "mobility_energy_realized_signed_kWh":realized,"mobility_energy_safe_plan_kWh":None if mv is None else f(mv.get("safe_energy_kWh")),
   "travel_time_safe_min":None if mv is None else 5*f(mv.get("safe_total_duration_steps"),0.0),
   "support_debt_post_kWh":f((post.get("mess_support_debt_kWh",{}) or {}).get(mid),0.0)})
 return rows
def main():
 a=argparse.ArgumentParser();a.add_argument("policy_root",type=Path);a.add_argument("--chunk-issues",type=int,default=64)
 a.add_argument("--output",type=Path,help="Separate offline materialization directory (default: POLICY_ROOT/K9H7_OBSERVABILITY_V1).")
 a.add_argument("--issue-first",type=int);a.add_argument("--issue-last",type=int)
 a.add_argument("--v2-only",action="store_true",help="Bounded forensic mode: ignore superseded v1 markers.");x=a.parse_args()
 if x.chunk_issues<1:raise RuntimeError("--chunk-issues must be positive")
 if x.issue_first is not None and x.issue_last is not None and x.issue_first>x.issue_last:raise RuntimeError("--issue-first exceeds --issue-last")
 started=time.monotonic();out=x.output or (x.policy_root/"K9H7_OBSERVABILITY_V1");out.mkdir(parents=True,exist_ok=True);chunks=[];issues=[]
 for d in sorted((x.policy_root/"engine").glob("issue_*")):
  if not (d/"A_B10_COMMIT_MARKER.json").is_file():continue
  if x.v2_only and load(d/"A_B10_COMMIT_MARKER.json").get("schema_version")!="mobileess.post_stage15.atomic_commit_marker.v2":continue
  m=valid_marker(d);issue=int(m["issue"])
  if x.issue_first is not None and issue<x.issue_first:continue
  if x.issue_last is not None and issue>x.issue_last:continue
  issues.append((issue,d))
 finite_chunks=[]
 for pos in range(0,len(issues),x.chunk_issues):
  block=issues[pos:pos+x.chunk_issues];lo,hi=block[0][0],block[-1][0]
  tables={k:[] for k in ("grid_bus_phase","grid_line_terminal_phase","grid_transformer_terminal_phase","mess_physical_step",
   "rack_pool_step","wan_event","forecast_issued","debt_rebound_step","controller_decision","objective_breakdown","recovery_attempt")}
  for i,d in block:
   o=load(d/"exact_grid/A_B10_FRESH_EXACT_AC_OBSERVABILITY.json");mo=load(d/"A_B10_COMMITTED_MODEL_OBSERVABILITY.json")
   pre=load(d/"BUILD7C_PRECOMMIT_STATE.json").get("state",{});post=load(d/"BUILD7C_POSTCOMMIT_STATE.json").get("state",{});audit=load(d/"POLICY_ISSUE_AUDIT.json")
   tables["grid_bus_phase"].extend({"issue_step":i,**r} for r in o["bus_phase_voltage"])
   tables["grid_line_terminal_phase"].extend({"issue_step":i,**r} for r in o["line_terminal_phase"])
   tables["grid_transformer_terminal_phase"].extend({"issue_step":i,**r} for r in o["transformer_terminal_current"])
   tables["mess_physical_step"].extend(physical_mess_rows(i,d))
   tables["rack_pool_step"].extend({"issue_step":i,**r} for r in mo["rack_pool_h0"])
   tables["wan_event"].extend({"issue_step":i,**r} for r in mo["wan_send_h0"])
   tables["forecast_issued"].extend({"issue_step":i,**r} for r in mo["forecast_issued"])
   tables["debt_rebound_step"].append({"issue_step":i,"workload_debt_pre_GPUh":sum(map(float,(pre.get("workload_debt_GPUh",{}) or {}).values())),
    "workload_debt_post_GPUh":sum(map(float,(post.get("workload_debt_GPUh",{}) or {}).values())),
    "support_debt_pre_kWh":sum(map(float,(pre.get("mess_support_debt_kWh",{}) or {}).values())),
    "support_debt_post_kWh":sum(map(float,(post.get("mess_support_debt_kWh",{}) or {}).values())),"repayment":json.dumps(mo.get("debt_repayment_h0",{}),sort_keys=True)})
   tables["controller_decision"].append({"issue_step":i,"planner_mode":audit.get("planner_mode"),"event_reasons":json.dumps(audit.get("event_reasons",[])),
    "replan_executed":audit.get("replan_executed"),"ac_recovery_status":(audit.get("ac_safety_recovery") or {}).get("status","OBSERVED_ZERO_EVENTS"),
    "causal_exogenous_identity":audit.get("causal_exogenous_identity"),"comparison_method_id":audit.get("comparison_method_id")})
   tables["objective_breakdown"].append({"issue_step":i,**mo.get("objective",{})})
   for attempt in (audit.get("ac_safety_recovery") or {}).get("attempts",[]):tables["recovery_attempt"].append({"issue_step":i,**attempt})
  files={};chunk_finite={name:finite_audit(name,rows) for name,rows in tables.items()}
  finite_chunks.append({"issue_first":lo,"issue_last":hi,"tables":chunk_finite})
  for name,rows in tables.items():
   p=out/f"{name}_{lo}_{hi}.parquet";pd.DataFrame(rows).to_parquet(p,index=False,compression="zstd")
   files[name]={"path":p.name,"sha256":digest(p),"bytes":p.stat().st_size,"rows":len(rows),"semantics":"OBSERVED_VALUE" if rows else "OBSERVED_ZERO_EVENTS"}
  chunks.append({"issue_first":lo,"issue_last":hi,"files":files})
 counts={name:sum(c["files"][name]["rows"] for c in chunks) for name in chunks[0]["files"]} if chunks else {}
 n=len(issues);expected={"grid_bus_phase":">0_PER_ISSUE","grid_line_terminal_phase":">0_PER_ISSUE","grid_transformer_terminal_phase":">0_PER_ISSUE",
  "mess_physical_step":4*n,"rack_pool_step":48*n,"forecast_issued":54*n,"debt_rebound_step":n,"controller_decision":n,"objective_breakdown":n,
  "wan_event":"TRUE_ZERO_ALLOWED","recovery_attempt":"TRUE_ZERO_ALLOWED"}
 gates={"committed_issue_count_positive":n>0,"mess_4_per_issue":counts.get("mess_physical_step")==4*n,"rack_48_per_issue":counts.get("rack_pool_step")==48*n,
  "forecast_54_per_issue":counts.get("forecast_issued")==54*n,"controller_1_per_issue":counts.get("controller_decision")==n,
  "grid_spatial_nonempty":all(counts.get(k,0)>0 for k in ("grid_bus_phase","grid_line_terminal_phase","grid_transformer_terminal_phase")),
  "required_numeric_values_finite":bool(finite_chunks) and all(a["pass"] for c in finite_chunks for a in c["tables"].values())}
 total_bytes=sum(p.stat().st_size for p in out.glob("*.parquet"));raw_files=sum(sum(1 for p in d.rglob("*") if p.is_file()) for _,d in issues)
 manifest={"schema_version":"K9H7_OBSERVABILITY_V1.materialization.v2","status":"PASS" if all(gates.values()) else "FAIL_CLOSED",
  "policy_root":str(x.policy_root),"committed_issues":n,"expected_cardinality":expected,"actual_row_counts":counts,"gates":gates,"chunks":chunks,
  "missingness_semantics":{"wan_event":"OBSERVED_ZERO_EVENTS" if counts.get("wan_event",0)==0 else "OBSERVED_VALUE",
  "recovery_attempt":"OBSERVED_ZERO_EVENTS" if counts.get("recovery_attempt",0)==0 else "OBSERVED_VALUE"},
  "finite_value_audit":finite_chunks,"units":UNITS,
  "resource_projection":{"parquet_bytes":total_bytes,"bytes_per_issue":total_bytes/max(1,n),"raw_files_per_issue":raw_files/max(1,n),
   "projected_parquet_bytes_48_episodes":total_bytes/max(1,n)*2016*48},"materialization_wall_s":time.monotonic()-started,
  "production_critical_path":False,"gurobi_solve_count":0,"opendss_solve_count":0,"simulation_rerun_count":0}
 manifest["bounded_v2_only_forensic_mode"]=bool(x.v2_only)
 manifest["issue_filter"]={"first":x.issue_first,"last":x.issue_last}
 atomic_json(out/"MANIFEST.json",manifest);print(out/"MANIFEST.json")
 return 0 if manifest["status"]=="PASS" else 2
if __name__=="__main__":raise SystemExit(main())

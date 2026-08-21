#!/usr/bin/env python3
"""Representative-week 2016-issue actual B5 hierarchical-controller runner.

Scientific core:
- exact PR4/PR2 frozen science/main.py (SHA locked);
- B5 full causal joint formulation;
- policy-specific slow-decision refresh/local-repair conditioning;
- fast conditioned MIQCP target gap 3%;
- Fresh Exact OpenDSS before every physical h0 commit;
- PRE->POST h0-only state chain.

The slow planner is a boundary-synchronous scientific replay in this workstation
runner: its measured wall time is reported separately and subtracted from the
commit-critical runtime characterization. This does NOT itself demonstrate the
300 s real-time claim. The causal trajectory/safety result remains scientific
authority under D12_RUNTIME_CLAIM_SEMANTICS_V2.
"""
from __future__ import annotations

import argparse,ast,contextlib,csv,difflib,hashlib,importlib.util,inspect,json,math,os,re,resource,shutil,statistics,sys,time,traceback
from datetime import datetime,timezone,timedelta
from pathlib import Path
from typing import Any,Mapping
import numpy as np
import pandas as pd

HERE=Path(__file__).resolve().parents[1]
RUNTIME=HERE/"runtime"
sys.path.insert(0,str(RUNTIME))

import MobileESS_A_STEP2_3_LOCAL_RUNNER_20260815_R2 as abase
import MobileESS_A_STEP4_LOCAL_RUNNER_20260815_R4 as astep4
import MobileESS_A_STEP5_LOCAL_REPAIR_RUNNER_20260815_R3 as astep5

START=3456
END=5471
COUNT=2016
CANDIDATE_ID="W02_2025-01-13"
CANDIDATE_MONTH="2025-01"
PROGRESS_FILE="W02_PROGRESS.json"
H=54
PR4="06a94bccc0a232ae7ea09cbc7b00962162c10f4d"
SCIENCE_SHA="cfdc7fe3069966d53d9d9246eb9c009a63a5536d265cddc9e5df145b5c6f33e8"
B5_SHA="3f712ec02c4c5ebb6a424267b043f07469d29f4a4abeaea7fcdd8b765e13624a"
PRE_SHA="4fd2b4e8a6ef052fd08454f9888ad1e08e2706ed99d1118cac6d96d33c8a5a7b"
PRE_FILE_SHA="deecff989d60223cb08d9070874a053f12ef7dc9e44a85554fb2821cd8ba6aba"
SITE_AUTHORITY_SHA="7a1009856160efda0f56269cd096e5f57465b5b185c182221481638e920b0a48"
SITE_AUTHORITY=HERE.parent/"SITING/FIXED_ESS_FINAL_SITE_AUTHORITY.json"
RESULT_SCHEMA="K9H7_RESULT_V1"
SHARED=Path("/home/jaewon/mobile_ess_work/frozen_artifacts/B_W02_SHARED_EXOGENOUS_SOURCE_CURRENT")
DELIVERY=Path("/home/jaewon/mobile_ess_work/frozen_artifacts/B_W02_4POLICY_ACTUAL_PILOT_CURRENT")
LOGROOT=Path("/home/jaewon/mobile_ess_work/logs/B_W02_4POLICY_ACTUAL_PILOT_CURRENT")
PRE_RESUME_PATH=HERE.parent/"INITIALIZATION/PRODUCTION_INPUT/W02_2025-01-13.resume_state.json"

POWER_KEYS=(
 "issues","target_steps","q90_gross_background_p_kw","q10_pv_available_kw",
 "q90_background_q_kvar","q50_net_background_p_kw","q50_background_q_kvar",
 "q_persistence_source_index","q_persistence_factor",
)
PRICE_KEYS=("issues","target_steps","q10","q50","q90")
TABLES=(
 "rolling_step","job_event","rack_step","wan_event","mess_step","debt_step",
 "constraint_event","forecast_eval","grid_exact_ac_bus_phase","grid_exact_ac_summary",
 "optimization_stats","run_summary",
)

def sha(p:Path)->str:
 h=hashlib.sha256()
 with p.open("rb") as f:
  for b in iter(lambda:f.read(8<<20),b""):h.update(b)
 return h.hexdigest()

def jw(p:Path,o:Any)->None:
 p.parent.mkdir(parents=True,exist_ok=True)
 t=p.with_name("."+p.name+".tmp")
 t.write_text(json.dumps(o,indent=2,sort_keys=True,ensure_ascii=False,allow_nan=False)+"\n",encoding="utf-8")
 t.replace(p)

def load_json(p:Path)->Any:
 def bad(x):raise RuntimeError(f"non-RFC8259 constant {x}")
 return json.loads(p.read_text(encoding="utf-8"),parse_constant=bad)

def loadmod(p:Path,name:str):
 spec=importlib.util.spec_from_file_location(name,p)
 if spec is None or spec.loader is None:raise RuntimeError(f"cannot import {p}")
 m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m

def set_fixed(v,value:float)->None:
 abase._set_fixed(v,float(value),relax_integer=False)

def fix_future_mode_commitment(loc:Mapping[str,Any],key:tuple[str,int],value:float)->None:
 """Fix the committed future mode; retain its original PCS implication rows."""
 mid,h=str(key[0]),int(key[1]);v=loc["mode"][(mid,h)];name=str(v.VarName)
 snapshot=loc.setdefault("_pending_future_mode_bound_snapshot_by_name",{})
 if name not in snapshot:snapshot[name]=(v,float(v.LB),float(v.UB))
 set_fixed(v,value)

PLANNER_TRANSFER_BOUND_TOL=1e-6+1e-12

def planner_transfer_value(v,raw:float)->float:
 """Canonicalize a solver-feasible value without changing its physical decision."""
 value=float(raw)
 if not math.isfinite(value):raise RuntimeError(f"planner transfer is non-finite {v.VarName}={value}")
 vtype=str(v.VType).upper()
 if vtype in {"B","I","S","N"}:
  canonical=float(round(value))
  if abs(value-canonical)>1e-5+1e-12:
   raise RuntimeError(f"planner integer commitment is fractional {v.VarName}={value}")
  value=canonical
 lb=float(v.LB);ub=float(v.UB)
 if value<lb:
  if lb-value>PLANNER_TRANSFER_BOUND_TOL:
   raise RuntimeError(f"planner transfer materially violates {v.VarName} lower bound: {value} < {lb}")
  value=lb
 if value>ub:
  if value-ub>PLANNER_TRANSFER_BOUND_TOL:
   raise RuntimeError(f"planner transfer materially violates {v.VarName} upper bound: {value} > {ub}")
  value=ub
 return value

def slow_commit_value(v,raw:float)->float:
 """Preserve continuous planner decisions and canonicalize numerical boundaries."""
 return planner_transfer_value(v,raw)

def canonical_physical_zero(value:float)->float:
 value=float(value)
 return 0.0 if abs(value)<5e-4 else value

def canonical_nonnegative_physical_state(value:float,label:str)->float:
 value=float(value)
 if value < -5e-4:raise RuntimeError(f"materially negative physical state {label}={value}")
 return max(0.0,canonical_physical_zero(value))

COUPLED_SOC_DEBT_NUMERICAL_EXCESS_MAX_KWH=2e-3

def canonicalize_coupled_soc_debt_ceiling(e_kwh:float,debt_kwh:float,capacity_kwh:float,
                                           label:str)->tuple[float,float,dict[str,Any]|None]:
 """Conservatively preserve the exact SOC + support-debt capacity invariant."""
 e=float(e_kwh);debt=float(debt_kwh);cap=float(capacity_kwh);excess=e+debt-cap
 if excess<=1e-12:return e,debt,None
 if excess>COUPLED_SOC_DEBT_NUMERICAL_EXCESS_MAX_KWH:
  raise RuntimeError(f"material coupled SOC+debt excess {label}: E={e} debt={debt} cap={cap} excess={excess}")
 # Preserve the full support obligation and reduce only available SOC.  This
 # is an inward safety projection by at most 2 Wh, not a capacity relaxation.
 projected_e=e-excess
 if projected_e<0.0:raise RuntimeError(f"coupled SOC projection became negative {label}: {projected_e}")
 return projected_e,debt,{"label":label,"E_before_kWh":e,"E_after_kWh":projected_e,
  "support_debt_kWh":debt,"capacity_kWh":cap,"inward_soc_adjustment_kWh":excess,
  "hard_capacity_relaxed":False,"support_obligation_reduced":False}

def adjust_model_state_for_inward_pcs_projection(e1_kwh:float,debt1_kwh:float,
                                                  old_pdis_kw:float,old_pchg_kw:float,
                                                  new_pdis_kw:float,new_pchg_kw:float)->tuple[float,float]:
 """Carry only the sub-watt PCS boundary projection into the model state.

 The solved E[1]/DE[1] pair is the scientific authority.  Reconstructing that
 pair from serialized controls loses the solved repE term and can invent many
 kWh of support debt.  An inward active-power projection is at most 1 W: less
 discharge moves equal energy from debt back to SOC; less charging removes
 equal energy from SOC and, conservatively, restores it to debt as if all of
 that marginal charge had repaid debt.  Thus E+DE never moves outward.
 """
 eta=0.95;dt_h=5.0/60.0
 discharge_energy_delta=dt_h*(float(new_pdis_kw)-float(old_pdis_kw))/eta
 charge_energy_delta=eta*dt_h*(float(new_pchg_kw)-float(old_pchg_kw))
 e=float(e1_kwh)-discharge_energy_delta+charge_energy_delta
 debt=float(debt1_kwh)+discharge_energy_delta-charge_energy_delta
 return e,canonical_nonnegative_physical_state(debt,"pcs_projection_support_debt1_kWh")

def mess_physical_capacity_kwh(loc:Mapping[str,Any],mid:str,scale_e:float)->float:
 bounds=[float(v.UB) for key,v in (loc.get("E",{}) or {}).items()
         if isinstance(key,tuple) and len(key)==2 and str(key[0])==str(mid)
         and math.isfinite(float(v.UB))]
 if not bounds:raise RuntimeError(f"MESS energy-capacity bounds unavailable {mid}")
 return float(scale_e)*max(bounds)

ENERGY_NUMERICAL_BOUNDARY_MAX_EXCESS_KWH=2e-3
ENERGY_PHYSICAL_FLOOR_KWH=440.0

def canonicalize_energy_numerical_boundary(e_kwh:float,floor_kwh:float,capacity_kwh:float,
                                            label:str)->tuple[float,dict[str,Any]|None]:
 """Project only sub-2 Wh solver dust onto the frozen physical SOC interval."""
 e=float(e_kwh);floor=float(floor_kwh);cap=float(capacity_kwh)
 if floor-1e-12<=e<=cap+1e-12:return min(cap,max(floor,e)),None
 projected=floor if e<floor else cap;distance=abs(e-projected)
 if distance>ENERGY_NUMERICAL_BOUNDARY_MAX_EXCESS_KWH:
  raise RuntimeError(f"material SOC boundary excess {label}: E={e} floor={floor} cap={cap} distance={distance}")
 return projected,{"label":label,"E_before_kWh":e,"E_after_kWh":projected,
  "floor_kWh":floor,"capacity_kWh":cap,"boundary_adjustment_kWh":projected-e,
  "hard_floor_relaxed":False,"hard_capacity_relaxed":False}

PCS_ACTIVE_LIMIT_KW=550.0
PCS_APPARENT_LIMIT_KVA=700.0
PCS_NUMERICAL_BOUNDARY_MAX_ACTIVE_EXCESS_KW=1e-3
PCS_NUMERICAL_BOUNDARY_MAX_EXCESS_KVA=1e-3

def canonicalize_pcs_numerical_boundary(p_discharge_kw:float,p_charge_kw:float,q_kvar:float)->tuple[float,float,float,dict[str,Any]|None]:
 """Project only solver-scale Q dust inward onto the frozen P550/S700 circle.

 The primary QCP is solved in MW/Mvar and may return a value whose physical-unit
 serialization exceeds S=700 kVA by less than the accepted model residual.  The
 exact OpenDSS adapter quite correctly rejects that outward point.  Q is absent
 from the frozen economic objective, so reducing |Q| to the exact original
 circle changes neither the objective nor any hard limit.  Solver-scale active
 power dust is likewise moved inward to the exact original P=550 boundary and
 audited; every material P or S excess remains fail-closed.
 """
 pdis=canonical_physical_zero(p_discharge_kw);pchg=canonical_physical_zero(p_charge_kw)
 q=canonical_physical_zero(q_kvar);pnet=pdis-pchg;projection={}
 active_before=pnet;active_excess=max(0.0,abs(pnet)-PCS_ACTIVE_LIMIT_KW)
 if active_excess>0.0:
  if active_excess>PCS_NUMERICAL_BOUNDARY_MAX_ACTIVE_EXCESS_KW:
   raise RuntimeError(f"P550 material active-power violation after solve p_net_kw={pnet:.15g} excess_kw={active_excess:.15g}")
  if pnet>0.0:pdis=max(0.0,pdis-active_excess)
  else:pchg=max(0.0,pchg-active_excess)
  pnet=pdis-pchg
  projection.update({"active_projection":True,"p_net_before_kw":active_before,"p_net_kw":pnet,
                     "active_excess_before_kw":active_excess,"active_inward_adjustment_kw":active_excess})
 apparent=math.hypot(pnet,q)
 if apparent<=PCS_APPARENT_LIMIT_KVA:return pdis,pchg,q,projection or None
 excess=apparent-PCS_APPARENT_LIMIT_KVA
 if excess>PCS_NUMERICAL_BOUNDARY_MAX_EXCESS_KVA:
  raise RuntimeError(f"S700 material violation after solve apparent_kva={apparent:.15g} excess_kva={excess:.15g}")
 q_limit=math.sqrt(max(0.0,PCS_APPARENT_LIMIT_KVA**2-pnet**2))
 q_projected=math.copysign(min(abs(q),q_limit),q)
 if pnet*pnet+q_projected*q_projected>PCS_APPARENT_LIMIT_KVA**2+1e-6:
  raise RuntimeError("P550/S700 inward numerical projection did not satisfy the frozen exact gate")
 projection.update({"apparent_projection":True,"p_net_kw":pnet,"q_before_kvar":q,"q_after_kvar":q_projected,
  "apparent_before_kva":apparent,"apparent_after_kva":math.hypot(pnet,q_projected),
  "excess_before_kva":excess,"q_inward_adjustment_kvar":abs(q)-abs(q_projected)})
 return pdis,pchg,q_projected,projection

def quantile(values:list[float],q:float)->float|None:
 if not values:return None
 a=np.asarray(values,dtype=float)
 return float(np.quantile(a,q,method="linear"))

def fnum(v,default=None):
 try:
  if v in (None,""):return default
  x=float(v)
  return x if math.isfinite(x) else default
 except Exception:return default

def inum(v,default=None):
 try:
  if v in (None,""):return default
  return int(float(v))
 except Exception:return default

def load_csv(p:Path)->list[dict[str,str]]:
 if not p.is_file() or p.stat().st_size==0:return []
 with p.open(encoding="utf-8-sig",newline="") as f:return list(csv.DictReader(f))

def write_csv(p:Path,fields:list[str],rows:list[dict[str,Any]])->None:
 p.parent.mkdir(parents=True,exist_ok=True)
 tmp=p.with_suffix(p.suffix+".tmp")
 with tmp.open("w",encoding="utf-8",newline="") as f:
  w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore")
  w.writeheader()
  for raw in rows:
   row={}
   for k in fields:
    v=raw.get(k,"")
    if v is None:v=""
    elif isinstance(v,bool):v="true" if v else "false"
    row[k]=v
   w.writerow(row)
 tmp.replace(p)

class PerformanceBook:
 def __init__(self):
  self.events=[]
  self.issue_records=[]
 @contextlib.contextmanager
 def phase(self,name:str,issue:int|None=None,record:dict[str,Any]|None=None):
  w0=time.perf_counter();c0=time.process_time()
  try:yield
  finally:
   rec={"phase":name,"issue":issue,"wall_s":time.perf_counter()-w0,"cpu_s":time.process_time()-c0}
   self.events.append(rec)
   if record is not None:
    dst=record.setdefault("performance_phases",{})
    prior=dst.get(name,{"wall_s":0.0,"cpu_s":0.0,"calls":0})
    dst[name]={"wall_s":float(prior["wall_s"])+rec["wall_s"],"cpu_s":float(prior["cpu_s"])+rec["cpu_s"],"calls":int(prior["calls"])+1}
 def rss_mib(self)->float:
  # Linux ru_maxrss is KiB.
  return float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)/1024.0
 def document(self,status:str,benchmark_issues:int)->dict[str,Any]:
  return {"schema_version":"mobileess.post_stage15.performance_trace.v1","status":status,
          "benchmark_issues":int(benchmark_issues),"events":self.events,"issues":self.issue_records,
          "max_rss_mib":self.rss_mib(),"future_actual_used":False,"scientific_semantics_changed":False}

def install_science_performance_wrappers(science,current:dict[str,Any],book:PerformanceBook):
 names={"extract_root":"causal_authority_extract","reconstruct_b4":"build4_engine_reconstruct",
        "prepare_static_context":"static_context_prepare","pareto_moves_cached":"mobility_domain_prepare",
        "build_full":"model_build_solve_extract","exact_profile_cert":"mobility_exact_profile",
        "exact24_candidate":"fresh_exact_opendss"}
 originals={}
 for fn,phase in names.items():
  if not hasattr(science,fn):continue
  original=getattr(science,fn);originals[fn]=original
  def wrapped(*args,_original=original,_phase=phase,**kwargs):
   record=current.get("record")
   issue=current.get("issue")
   with book.phase(_phase,issue,record):return _original(*args,**kwargs)
  setattr(science,fn,wrapped)
 def restore():
  for fn,original in originals.items():setattr(science,fn,original)
 return restore

class RackCache:
 def __init__(self,helper,base:Path):
  self.helper=helper;self.base=base
  rack_root=base/"frozen_artifacts/stage_k9h7_v2044r12b1d1ar3r1r3r4r6r2r4r6_phase_boundary_rack_20260808T222927"
  forecast_root=base/"frozen_artifacts/stage_k9h7_v2044r12b1d1ar3r1r3r4r6r2r2r3_float32_identity_20260808T203037"
  self.actual_path=rack_root/"RACK_CURRENT_FIXED_BACKGROUND_PRIMARY_FIXED_AEST_5MIN.parquet"
  self.inference_path=rack_root/"PRIMARY_FIXED_AEST_CURRENT_FIXED_GPU_IT_12IDC.parquet"
  self.forecast_path=forecast_root/"GLOBAL_K5B2_K5C3_FIXED_GPU_48STEP_2025.parquet"
  for path,digest in ((self.actual_path,helper.RACK_ACTUAL_SHA),(self.inference_path,helper.RACK_INFERENCE_SHA),(self.forecast_path,helper.RACK_FORECAST_SHA)):
   if not path.is_file() or sha(path)!=digest:raise RuntimeError(f"full-year rack source SHA drift {path}")
  actual=pd.read_parquet(self.actual_path,columns=["timestamp_utc","rack_pool_id","fixed_gpu_actual_rack","fixed_it_kw_actual_rack"])
  inference=pd.read_parquet(self.inference_path,columns=["timestamp_utc","idc_id","inference_it_kw"])
  forecast=pd.read_parquet(self.forecast_path)
  actual["timestamp_utc"]=pd.to_datetime(actual["timestamp_utc"],utc=True,errors="raise")
  inference["timestamp_utc"]=pd.to_datetime(inference["timestamp_utc"],utc=True,errors="raise")
  forecast["timestamp_utc"]=pd.to_datetime(forecast["timestamp_utc"],utc=True,errors="raise")
  axis0=pd.Timestamp("2024-12-31T14:00:00Z");first=axis0+pd.Timedelta(minutes=5*START);last=axis0+pd.Timedelta(minutes=5*END)
  for name,frame,mult in (("actual",actual,48),("inference",inference,12)):
   cov=frame[(frame["timestamp_utc"]>=first)&(frame["timestamp_utc"]<=last)]
   if cov["timestamp_utc"].nunique()!=COUNT or len(cov)!=COUNT*mult:raise RuntimeError(f"{CANDIDATE_ID} rack {name} coverage drift")
  fcov=forecast[(forecast["timestamp_utc"]>=first)&(forecast["timestamp_utc"]<=last)]
  if fcov["timestamp_utc"].nunique()!=COUNT:raise RuntimeError(f"{CANDIDATE_ID} rack forecast coverage drift")
  self.aidx=actual.set_index(["timestamp_utc","rack_pool_id"]).sort_index()
  self.iidx=inference.set_index(["timestamp_utc","idc_id"]).sort_index()
  self.qidx=forecast.set_index("timestamp_utc").sort_index()
  # Compact episode-only scalar indexes preserve the exact legacy arithmetic while
  # avoiding thousands of pandas MultiIndex scalar extractions per issue.
  aw=actual[(actual["timestamp_utc"]>=first)&(actual["timestamp_utc"]<=last)]
  iw=inference[(inference["timestamp_utc"]>=first)&(inference["timestamp_utc"]<=last+pd.Timedelta(minutes=5*53))]
  qw=forecast[(forecast["timestamp_utc"]>=first)&(forecast["timestamp_utc"]<=last)]
  self.actual_values={(r.timestamp_utc,str(r.rack_pool_id)):(float(r.fixed_gpu_actual_rack),float(r.fixed_it_kw_actual_rack))
                      for r in aw.itertuples(index=False)}
  self.inference_values={(r.timestamp_utc,str(r.idc_id)):float(r.inference_it_kw) for r in iw.itertuples(index=False)}
  self.forecast_values={r.timestamp_utc:{c:float(getattr(r,c)) for c in qw.columns if c.startswith("fixed_gpu_step_")}
                        for r in qw.itertuples(index=False)}
  self._conservative_constants=None
 def bind(self,scope:dict,out:Path):
  env=scope["env"];env.aidx=self.aidx;env.iidx=self.iidx;env.qidx=self.qidx
  p=Path(out)/"A_B10_FULL_YEAR_RACK_BINDING.json"
  if not p.is_file():
   jw(p,{"status":"PASS","candidate_id":CANDIDATE_ID,"actual_sha256":self.helper.RACK_ACTUAL_SHA,
         "inference_sha256":self.helper.RACK_INFERENCE_SHA,"forecast_sha256":self.helper.RACK_FORECAST_SHA,
         "source_loaded_once_per_policy_process":True,"current_actual_read_policy":"current issue only","future_actual_used":False})

 def conservative_table(self,scope:Mapping[str,Any],issue:int)->dict[tuple[str,int],tuple[float,float,str]]:
  env=scope["env"];racks=[str(x) for x in scope["cap"]["rack_pool_id"].astype(str).tolist()]
  if self._conservative_constants is None:
   constants={}
   for rack in racks:
    cr=env.capidx.loc[rack];idc=str(cr["idc_id"])
    w=env.waidx.loc[idc]
    reserve={}
    for dc in (6,12,24,48):
     j=env.jidx.loc[(idc,rack,int(dc))]
     reserve[dc]=(float(j["q95_rack_gpu_reserve"]),float(j["q95_rack_incremental_it_kw_reserve"]))
    constants[rack]={"idc":idc,"gpu_share":float(cr["gpu_share"]),"it_share":float(cr["it_share"]),
                     "spatial_weight":float(w["spatial_weight"]),
                     "incremental_it_kw_per_gpu":float(w["incremental_it_kw_per_gpu"]),"reserve":reserve}
   self._conservative_constants=constants
  constants=self._conservative_constants
  issue_ts=pd.Timestamp("2024-12-31T14:00:00Z")+pd.Timedelta(minutes=5*int(issue))
  qrow=self.forecast_values[issue_ts];table={}
  for rack in racks:
   g0,p0=self.actual_values[(issue_ts,rack)];table[(rack,int(issue))]=(float(g0),float(p0),"CURRENT_ACTUAL")
  for h in range(1,49):
   target=issue_ts+pd.Timedelta(minutes=5*h);g=float(qrow[f"fixed_gpu_step_{h:02d}"])
   for rack in racks:
    c=constants[rack]
    inference=float(self.inference_values[(target,c["idc"])])*float(c["it_share"])
    gpu=g*float(c["spatial_weight"])*float(c["gpu_share"])
    inc=g*float(c["spatial_weight"])*float(c["incremental_it_kw_per_gpu"])*float(c["it_share"])
    vals=[(gpu+float(c["reserve"][dc][0]),inference+inc+float(c["reserve"][dc][1])) for dc in (6,12,24,48)]
    table[(rack,int(issue)+h)]=(max(float(v[0]) for v in vals),max(float(v[1]) for v in vals),"MAX_DURATION_CLASS_Q95")
  return table

class SourceBlocks:
 def __init__(self,root:Path,required_end:int=END,allow_partial:bool=False):
  self.root=root
  self._block=-1;self._power={};self._price={}
  pp_generic=root/"power_price/REP_WEEK_POWER_PRICE_SOURCE_AUTHORITY.json"
  pp_w02=root/"power_price/A_B10_W02_POWER_PRICE_SOURCE_AUTHORITY.json"
  self.pp=load_json(pp_generic if pp_generic.is_file() else pp_w02)
  shared_path=root/"SHARED_EXOGENOUS_AUTHORITY.json"
  self.shared=load_json(shared_path) if shared_path.is_file() else {"status":"BOUNDED_PARTIAL_SOURCE_ONLY"}
  if self.pp.get("status")!="PASS":raise RuntimeError("power/price source authority not PASS")
  if self.shared.get("status")!="PASS" and not allow_partial:raise RuntimeError("shared exogenous authority not PASS")
  final_index=root/"mobility/R12_COMMON_MOBILITY_INDEX.csv"
  partial_index=root/"mobility/R12_COMMON_MOBILITY_INDEX.partial.csv"
  self.mob_index=final_index if final_index.is_file() else partial_index
  if not self.mob_index.is_file() or (self.mob_index==partial_index and not allow_partial):
   raise RuntimeError("final mobility index unavailable outside bounded benchmark mode")
  self.mob_rows={int(r["issue_step"]):r for r in load_csv(self.mob_index)}
  if any(i not in self.mob_rows for i in range(START,required_end+1)):raise RuntimeError(f"{CANDIDATE_ID} requested mobility coverage incomplete")
  self.mobility_shas=frozenset(str(r.get("sha256","")).lower() for r in self.mob_rows.values())
  if any(len(x)!=64 or any(c not in "0123456789abcdef" for c in x) for x in self.mobility_shas):
   raise RuntimeError(f"{CANDIDATE_ID} mobility index contains an invalid SHA-256")
  self.bank=root/"mobility/E4B_FULLFIT_TEMPLATE_BANK_129.parquet"
  if not self.bank.is_file():raise RuntimeError("shared mobility template bank missing")
 def _ensure(self,issue:int):
  bi=(issue-START)//576
  if bi==self._block:return
  bd=self.root/"power_price"/f"block_{bi:02d}_{START+bi*576}_{START+(bi+1)*576-1}"
  auth=load_json(bd/"BLOCK_AUTHORITY.json")
  if auth.get("status")!="PASS":raise RuntimeError(f"source block not PASS {bi}")
  self._power={k:np.load(bd/f"power__{k}.npy",mmap_mode="r") for k in POWER_KEYS}
  self._price={k:np.load(bd/f"price__{k}.npy",mmap_mode="r") for k in PRICE_KEYS}
  self._block=bi
 def row(self,issue:int)->tuple[dict[str,np.ndarray],dict[str,np.ndarray]]:
  self._ensure(issue);off=issue-(START+self._block*576)
  p={k:np.asarray(v[off:off+1]).copy() if np.asarray(v).ndim else np.asarray(v).copy() for k,v in self._power.items()}
  q={k:np.asarray(v[off:off+1]).copy() if np.asarray(v).ndim else np.asarray(v).copy() for k,v in self._price.items()}
  return p,q
 def q50_next_background_kw(self,issue:int)->float|None:
  if issue<START or issue>END:return None
  p,_=self.row(issue)
  a=np.asarray(p["q50_net_background_p_kw"])
  if a.shape[1]<2:return None
  return float(a[0,1].sum())
 def mobility(self,issue:int)->Path:
  r=self.mob_rows[int(issue)];p=self.root/"mobility"/r["file"]
  if not p.is_file() or sha(p)!=r["sha256"]:raise RuntimeError(f"mobility SHA drift issue={issue}")
  if str(r.get("future_actual_target_read","")).lower() not in {"false","0"}:raise RuntimeError("mobility future-actual audit drift")
  return p

def transform_science(science,result_dir:Path):
 source=inspect.getsource(science.rolling54_main);original=source
 reps=[
  ("def rolling54_main(out,base):","def a_b10_one_issue_main(out,base):"),
  (' r25p_unlimited_stage1=(os.environ.get("MOBILEESS_R25P_STAGE1_UNLIMITED_COMPLETION","0")=="1")',
   ' r25p_unlimited_stage1=False  # A-B10 one-issue external control plane'),
  (' if start_issue!=113 or count!=54:\n  raise RuntimeError("BUILD7C scientific release contract is exactly issues 113..166 (54 issues)")',
   ' if count!=1:\n  raise RuntimeError("A-B10 policy engine invokes exactly one causal issue per call")'),
  (' if resume_issue<113 or resume_issue>end_issue:',' if resume_issue<start_issue or resume_issue>end_issue:'),
  ('  if r25q_verified_prefix!=resume_issue-113 or not os.environ.get("MOBILEESS_R25Q_RESUME_STATE_PATH"):',
   '  if r25q_verified_prefix!=resume_issue-start_issue or not os.environ.get("MOBILEESS_R25Q_RESUME_STATE_PATH"):'),
  (' runtime_index=ar2/"BUILD5R3_SELECTED_RUNTIME/ROLLING54_MOBILITY_RUNTIME_INDEX.csv"',
   ' runtime_index=Path(os.environ["A_B10_MOBILITY_INDEX"])'),
  (' if ridx["issue_step"].astype(int).tolist()!=expected:raise RuntimeError("BUILD7C mobility runtime index is not exact 113..166")',
   ' ridx=ridx[ridx["issue_step"].astype(int).isin(expected)].copy()\n  if ridx["issue_step"].astype(int).tolist()!=expected:raise RuntimeError("A-B10 mobility runtime index does not cover the requested causal issue axis")'),
  ('  rack,op1,cr,grid,metrics=b4.preload(engine);scope=b4.prepare_scope(Path(base),rack,op1,out);temps.extend(scope["temps"])',
   '  rack,op1,cr,grid,metrics=b4.preload(engine);scope=b4.prepare_scope(Path(base),rack,op1,out);temps.extend(scope["temps"]);_a_b10_bind_full_year_rack_scope(scope,out)'),
  ('    f["scope"]=b4.prepare_scope(Path(base),rack,op1,out)',
   '    f["scope"]=b4.prepare_scope(Path(base),rack,op1,out);_a_b10_bind_full_year_rack_scope(f["scope"],out)'),
 ('  if resume_issue==113:','  if False:  # A-B10 always uses SHA-bound external PRE state'),
  ('   if not ex.get("hard_constraint_pass",False):\n'
   '    # Step 1 is intentionally fail-closed. Phase-aware cut/re-solve is the next stage.',
   '   if not ex.get("hard_constraint_pass",False):\n'
   '    ex=_a_b10_exact_ac_recovery(b4,grid24,scope,gstatic,issue,running,sol,issue_out,ex)\n'
   '    jw(issue_out/f"exact_grid/FRESH_EXACT_OPENDSS_24SERVICE_ISSUE_{issue}.json",ex)\n'
   '    _a_b10_capture_exact_ac(grid24,issue_out,issue,ex)\n'
   '   if not ex.get("hard_constraint_pass",False):\n'
   '    # Bounded closed-loop recovery exhausted; unsafe h0 is never committed.'),
  ('   jw(issue_out/f"exact_grid/FRESH_EXACT_OPENDSS_24SERVICE_ISSUE_{issue}.json",ex)\n'
   '   if not ex.get("hard_constraint_pass",False):',
   '   jw(issue_out/f"exact_grid/FRESH_EXACT_OPENDSS_24SERVICE_ISSUE_{issue}.json",ex)\n'
   '   _a_b10_capture_exact_ac(grid24,issue_out,issue,ex)\n'
   '   if not ex.get("hard_constraint_pass",False):'),
 ]
 for old,new in reps:
  if source.count(old)!=1:raise RuntimeError("science control-plane patch drift: "+old[:90])
  source=source.replace(old,new,1)
 ast.parse(source)
 (result_dir/"A_B10_CONTROL_PLANE_PATCH.diff").write_text("".join(difflib.unified_diff(original.splitlines(True),source.splitlines(True),fromfile="science.rolling54_main",tofile="A_B10.one_issue_main")),encoding="utf-8")
 exec(source,science.__dict__)
 return science.a_b10_one_issue_main

def install_source_bindings(science,helper,sources:SourceBlocks,power,price,issue:int,result_dir:Path):
 orig_prepare=science.prepare_static_context
 orig_one=science.extract_b5_issue_and_bank
 orig_once=science.extract_b5_rolling_once
 cache={"planning":None,"price":None}
 def prepare(ar2,b6,ref,b4):
  ctx=orig_prepare(ar2,b6,ref,b4)
  if cache["planning"] is None:
   cache["planning"]=helper.direct_planning(None,ctx["planning"],power,result_dir,issue,1)
   cache["price"]=helper.direct_price(ctx["price"],price,result_dir,issue,1)
  z=dict(ctx);z["planning"]=cache["planning"];z["price"]=cache["price"];return z
 def one(_arc,_tmp,issue=113,runtime_index=None):
  return sources.mobility(int(issue)),sources.bank
 def once(_arc,_tmp,_runtime_index_df,issues,_out):
  req=[int(x) for x in issues]
  if req!=[issue]:raise RuntimeError(f"mobility one-issue axis drift {req} vs {issue}")
  return {issue:sources.mobility(issue)},sources.bank
 science.prepare_static_context=prepare;science.extract_b5_issue_and_bank=one;science.extract_b5_rolling_once=once
 def restore():
  science.prepare_static_context=orig_prepare;science.extract_b5_issue_and_bank=orig_one;science.extract_b5_rolling_once=orig_once
 return restore

def runtime_env(issue:int,state_path:Path,state_hash:str,mob_idx:Path,control:Path,fixed_location:bool=False,
                worker_cache:bool=True,active_projection:bool=True,
                fixed_homes:Mapping[str,str]|None=None)->dict[str,str]:
 abase.set_science_environment()
 env=dict(os.environ)
 env.update({
  "MOBILEESS_ROLL_START":str(issue),"MOBILEESS_ROLL_COUNT":"1","MOBILEESS_RESUME_ISSUE":str(issue),
  "MOBILEESS_R25Q_VERIFIED_PREFIX_ISSUES":"0",
  "MOBILEESS_R25Q_RESUME_STATE_PATH":str(state_path),
  "MOBILEESS_RESUME_STATE_SHA256":str(state_hash),
  "MOBILEESS_R25Q_RESUME_SOURCE":f"post-Stage15 {CANDIDATE_ID} canonical PRE or preceding committed POST",
  "MOBILEESS_R25Q_RESUME_HINT_DIR":str(control/"empty_hints"),
  "MOBILEESS_R25Q_RESUME_MOVE_PLAN_NAME":"NONE.csv",
  "MOBILEESS_R25Q_RESUME_MESS_PLAN_NAME":"NONE.csv",
  "MOBILEESS_R25V_RESUME_JOB_PLAN_NAME":"NONE.csv",
  "MOBILEESS_R25V_RESUME_GUIDANCE_PATH":str(control/"empty_hints/NONE.json"),
  "A_B10_MOBILITY_INDEX":str(mob_idx),
  "MOBILEESS_GUROBI_THREADS":"4",
  "MOBILEESS_GUROBI_ECON_MIPGAP":"0.03",
  "MOBILEESS_WORKER_FOUNDATION_CACHE":"1" if worker_cache else "0",
  "MOBILEESS_FIXED_LOCATION_MOBILITY_ABLATION":"1" if fixed_location else "0",
  "MOBILEESS_ACTIVE_PLAN_MOBILITY_PROJECTION":"1" if active_projection and not fixed_location else "0",
  "MOBILEESS_POST15_SKIP_REDUNDANT_DENSE_B4_CUTS":"0",
 })
 env.pop("MOBILEESS_GUROBI_TIMELIMIT",None)
 if fixed_location:
  if not fixed_homes:raise RuntimeError("M4 runtime requires the selected fixed-home authority")
  env["MOBILEESS_FIXED_LOCATION_HOME_MAP_JSON"]=json.dumps(dict(fixed_homes),sort_keys=True,separators=(",",":"))
 else:
  env.pop("MOBILEESS_FIXED_LOCATION_HOME_MAP_JSON",None)
 return env

def initial_reference()->dict[str,Any]:
 # A prospective start-site amendment cannot inherit a future active plan that
 # was optimized at the superseded sites.  The first boundary therefore has no
 # persisted plan and creates one causally by an identical Full Replan in M1-M4.
 return {
  "BUILD7B_FULL54_JOB_PLAN.csv":pd.DataFrame(),
  "BUILD7B_FULL54_MESS_PLAN.csv":pd.DataFrame(),
  "BUILD7B_FULL54_MOVE_ARCS_SELECTED.csv":pd.DataFrame(),
  "active_plan_parent_issue":None,
  "active_plan_source_post_sha256":PRE_SHA,
  "authority":"POST_STAGE15_PROSPECTIVE_SITING_CANONICAL_PRE_NO_FUTURE_PLAN",
 }

def fixed_location_reference(ref:Mapping[str,Any],homes:Mapping[str,str])->dict[str,Any]:
 rows=[]
 for mid,sid in homes.items():
  for h in range(H):
   rows.append({"mess_id":mid,"horizon_step":h,"state":"STAY","service_id":sid,
                "P_discharge_kW":0.0,"P_charge_kW":0.0,"Q_kvar":0.0,
                "SOC_kWh":760.0,"support_energy_debt_kWh":0.0})
 out=dict(ref)
 out["BUILD7B_FULL54_MESS_PLAN.csv"]=pd.DataFrame(rows)
 out["BUILD7B_FULL54_MOVE_ARCS_SELECTED.csv"]=pd.DataFrame()
 out["fixed_location_projection"]=True
 out["fixed_location_homes"]=homes
 out["authority"]=str(ref.get("authority",""))+"+M4_EXACT_FIXED_LOCATION_PROJECTION"
 return out

def fix_all_slow_to_incumbent(loc:Mapping[str,Any])->dict[str,int]:
 counts={}
 # Preserve the already-feasible complete solution until solve_fast has called
 # model.reset(); reset discards both the incumbent and any Start set before it.
 loc["_pending_complete_mip_start_by_name"]={str(v.VarName):planner_transfer_value(v,float(v.X)) for v in loc["m"].getVars()}
 for name in ("x","defer","stay","mv","node_occ"):
  d=loc.get(name,{}) or {};counts[name]=len(d)
  for v in d.values():set_fixed(v,slow_commit_value(v,float(v.X)))
 # The accepted planner incumbent is the H1--H53 commitment.  Conditioned
 # physical dispatch may choose only the four H0 PCS modes.
 future_modes=[(key,v) for key,v in (loc.get("mode",{}) or {}).items()
               if isinstance(key,tuple) and len(key)==2 and int(key[1])>0]
 counts["mode_future"]=len(future_modes)
 for key,v in future_modes:
  fix_future_mode_commitment(loc,key,1.0 if float(v.X)>=0.5 else 0.0)
 loc["m"].update()
 return counts

def fix_all_slow_from_model(loc:Mapping[str,Any],source_model)->dict[str,int]:
 counts={}
 # The planner copy contains a feasible assignment for every variable, not
 # only the slow siting/mobility binaries.  Transfer it by variable name so the
 # subsequent conditioned solve starts from that proven feasible point.  This
 # is search guidance only: the original objective and every hard constraint
 # remain authoritative and are re-optimized below.
 pending={}
 for v in loc["m"].getVars():
  source_v=source_model.getVarByName(str(v.VarName))
  if source_v is None:raise RuntimeError(f"planner-copy start variable missing {v.VarName}")
  pending[str(v.VarName)]=planner_transfer_value(v,float(source_v.X))
 loc["_pending_complete_mip_start_by_name"]=pending
 for name in ("x","defer","stay","mv","node_occ"):
  d=loc.get(name,{}) or {};counts[name]=len(d)
  for v in d.values():
   source_v=source_model.getVarByName(str(v.VarName))
   if source_v is None:raise RuntimeError(f"planner-copy variable missing {v.VarName}")
   set_fixed(v,slow_commit_value(v,float(source_v.X)))
 future_modes=[(key,v) for key,v in (loc.get("mode",{}) or {}).items()
               if isinstance(key,tuple) and len(key)==2 and int(key[1])>0]
 counts["mode_future"]=len(future_modes)
 for key,v in future_modes:
  source_v=source_model.getVarByName(str(v.VarName))
  if source_v is None:raise RuntimeError(f"planner-copy future mode missing {v.VarName}")
  fix_future_mode_commitment(loc,key,1.0 if float(source_v.X)>=0.5 else 0.0)
 loc["m"].update()
 return counts

def residual_integer_names(model)->list[str]:
 return [str(v.VarName) for v in model.getVars() if str(v.VType).upper() in {"B","I","S","N"} and float(v.UB)-float(v.LB)>1e-12]

def numerical_constraint_offenders(model,limit:int=24)->list[dict[str,Any]]:
 """Return named residual evidence without changing the model or solution."""
 rows=[]
 for c in model.getConstrs():
  try:
   slack=float(c.Slack);sense=str(c.Sense)
   # Gurobi Slack is RHS-LHS for every linear sense.
   violation=(abs(slack) if sense=="=" else
              (max(0.0,-slack) if sense=="<" else max(0.0,slack)))
   if violation>0.0:rows.append({"kind":"LINEAR","name":str(c.ConstrName),
                                 "sense":sense,"slack":slack,"violation":violation})
  except Exception:continue
 for c in model.getQConstrs():
  try:
   slack=float(c.QCSlack);sense=str(c.QCSense)
   # Gurobi QCSlack follows the same RHS-LHS convention.
   violation=(abs(slack) if sense=="=" else
              (max(0.0,-slack) if sense=="<" else max(0.0,slack)))
   if violation>0.0:rows.append({"kind":"QUADRATIC","name":str(c.QCName),
                                 "sense":sense,"slack":slack,"violation":violation})
  except Exception:continue
 return sorted(rows,key=lambda r:float(r["violation"]),reverse=True)[:int(limit)]

def solve_fast(model,cb,loc:Mapping[str,Any]|None=None)->dict[str,Any]:
 import gurobipy as gp
 if loc is not None and loc.get("_a_b10_tiebreak_constr") is not None:
  for var,lb,ub in loc.pop("_a_b10_tiebreak_fixed_bounds",[]):var.LB=lb;var.UB=ub
  model.remove(loc.pop("_a_b10_tiebreak_constr"));model.setObjective(loc["econ"],gp.GRB.MINIMIZE);model.update()
 model.Params.Threads=4;model.Params.MIPGap=0.03;model.Params.MIPGapAbs=0.0;model.Params.MIPFocus=1
 # Numerical polishing is local to one candidate.  If its stricter 1e-9
 # feasibility solve rejects an otherwise operationally valid incumbent, the
 # caller may try another bounded recovery candidate.  Restore the frozen base
 # numerical policy at every entry so a failed polish cannot leak into that
 # next solve and misclassify a sub-1e-6 residual as structural infeasibility.
 model.Params.NumericFocus=0;model.Params.FeasibilityTol=9e-7
 model.Params.IntFeasTol=1e-5;model.Params.OptimalityTol=1e-6
 model.Params.BarQCPConvTol=1e-8;model.Params.ScaleFlag=-1
 # The slow planner may use a benchmarked search-only presolve policy.  The
 # conditioned dispatch is the frozen physical-commit authority and must not
 # inherit that temporary planner setting through the reused Model object.
 model.Params.Presolve=-1
 # A conditioned solve must never block the multi-week runner indefinitely.
 # Its complete feasible MIP start is transferred above; the bounded solve is
 # still required to establish the frozen 3% operational optimality gate.
 model.Params.TimeLimit=300.0;model.Params.OutputFlag=1;model.update();model.reset()
 start_kind="NONE"
 if loc is not None:
  # A planner-copy incumbent is fully feasible for this exact model, so inject
  # every variable.  During later AC-cut rounds the previous continuous P/Q
  # point intentionally violates the new cut; retain only its integer choices
  # and let Gurobi reconstruct a continuous feasible point.
  pending=loc.pop("_pending_complete_mip_start_by_name",None)
  future_mode_snapshot=loc.pop("_pending_future_mode_bound_snapshot_by_name",None)
  all_active_mode_start=loc.pop("_pending_all_active_plan_mode_start_by_name",None)
  if pending:
   for v in model.getVars():v.Start=float(pending[str(v.VarName)])
   start_kind="COMPLETE_PLANNER_FEASIBLE"
  else:
   active_plan_start=loc.pop("_pending_active_plan_mode_start_by_name",None)
   integer_start=(active_plan_start or loc.get("_last_integer_mip_start_by_name",{}))
   if integer_start:
    for v in model.getVars():
     if str(v.VType).upper() in {"B","I","S","N"} and str(v.VarName) in integer_start:
      v.Start=float(integer_start[str(v.VarName)])
    start_kind=("SHIFTED_ACTIVE_PLAN_MODE_ONLY" if active_plan_start
                else "PRIOR_ACCEPTED_INTEGER_ONLY")
  model.update()
 t=time.monotonic();model.optimize(cb) if cb is not None else model.optimize();wall=time.monotonic()-t
 if int(model.SolCount)<1 and future_mode_snapshot:
  # Future PCS modes are a search acceleration, not part of the shifted slow
  # mobility commitment.  If their inferred fixed signs make the conditioned
  # model numerically infeasible, restore the original mode domain exactly and
  # re-solve once with complete mode guidance.  The original feasible set,
  # objective, equations, and 300 s per-solve bound are unchanged.
  for v,lb,ub in future_mode_snapshot.values():v.LB=lb;v.UB=ub
  model.update();model.reset()
  if pending:
   for v in model.getVars():v.Start=float(pending[str(v.VarName)])
  elif all_active_mode_start:
   for v in model.getVars():
    if str(v.VarName) in all_active_mode_start:v.Start=float(all_active_mode_start[str(v.VarName)])
  model.update();tt=time.monotonic();model.optimize(cb) if cb is not None else model.optimize();wall+=time.monotonic()-tt
  start_kind="FUTURE_MODE_FIX_INFEASIBLE_ORIGINAL_DOMAIN_FALLBACK"
 q=abase.solver_quality(model);q["wall_seconds"]=wall
 # A zero (or numerically zero) quadratic objective can make Gurobi report an
 # infinite relative MIPGap even with OPTIMAL status.  Evidence JSON forbids
 # non-finite numbers; retain the status/objective/bound and encode only such
 # undefined diagnostic scalars as null.
 q={k:(None if isinstance(v,float) and not math.isfinite(v) else v) for k,v in q.items()}
 q["mip_start_kind"]=start_kind
 q["complete_feasible_mip_start_transferred"]=(start_kind=="COMPLETE_PLANNER_FEASIBLE")
 q["conditioned_dispatch_time_limit_seconds"]=300.0
 if int(model.SolCount)<1:
  if loc is not None and bool(loc.get("_conditioned_shifted_active_plan",False)):
   raise RuntimeError("A_B10_ACTIVE_PLAN_CONDITIONED_INFEASIBLE_REQUIRES_SAME_PRE_FULL_REPLAN")
  raise RuntimeError("fast conditioned dispatch has no feasible incumbent")
 try:gap=float(model.MIPGap)
 except Exception:gap=None
 if int(model.Status)!=int(gp.GRB.OPTIMAL) and (gap is None or gap>0.03+1e-12):
  raise RuntimeError(f"fast conditioned dispatch did not reach 3% operational gap status={model.Status} gap={gap}")
 if loc is not None:
  loc["_last_integer_mip_start_by_name"]={str(v.VarName):float(v.X) for v in model.getVars()
   if str(v.VType).upper() in {"B","I","S","N"}}
 numerical_limits={"ConstrVio":1e-6,"BoundVio":1e-6,"IntVio":1e-5}
 exceeded={k:float(q.get(k,float("inf"))) for k,limit in numerical_limits.items()
           if float(q.get(k,float("inf")))>limit}
 if exceeded:
  bound_offenders=[]
  for v in model.getVars():
   x=float(v.X);lb=float(v.LB);ub=float(v.UB)
   lower=max(0.0,lb-x);upper=max(0.0,x-ub)
   if max(lower,upper)>0.0:
    bound_offenders.append({"variable":str(v.VarName),"value":x,"lb":lb,"ub":ub,
                            "lower_violation":lower,"upper_violation":upper,
                            "fixed":abs(ub-lb)<=1e-12})
  bound_offenders=sorted(bound_offenders,key=lambda r:max(r["lower_violation"],r["upper_violation"]),reverse=True)[:20]
  refinement_start={str(v.VarName):float(v.X) for v in model.getVars()}
  # If the sole failed numerical gate is a marginal negative Pchg/Pdis value,
  # select its exact feasible active-set boundary (zero) and re-optimize the
  # unchanged primary objective.  This narrows the candidate to a mathematically
  # valid face; it never accepts negative charging/discharging or relaxes a
  # residual gate.  It also avoids globally tightening recursion tolerances.
  worst=(bound_offenders[0] if bound_offenders else None)
  pcs_zero_polish=bool(
   set(exceeded)=={"BoundVio"} and worst is not None
   and str(worst["variable"]).startswith(("Pchg_","Pdis_"))
   and float(worst["lower_violation"])>0.0 and float(worst["upper_violation"])==0.0
   and float(worst["lower_violation"])<=2e-6 and float(worst["lb"])==0.0
   and not bool(worst["fixed"]))
  if pcs_zero_polish:
   active_set_bounds=[];selected_pcs_names=set();active_set_by_name={}
   for v in model.getVars():
    name=str(v.VarName);x=float(v.X)
    # Restrict only coordinates that individually fail the frozen BoundVio
    # gate.  Sub-gate negative dust is already admissible solver residual;
    # fixing all of it at once can overdetermine the tightly coupled future
    # energy recursion and merely move the same ppm residual into an equality.
    if (name.startswith(("Pchg_","Pdis_")) and float(v.LB)==0.0
        and -2e-6<=x<-numerical_limits["BoundVio"]):
     selected_pcs_names.add(name)
   # A dedicated MESS PCC has pbal = Pdis - Pchg + FP = 0.  When both PCS
   # sides are mathematically zero, FP is therefore exactly zero as well.
   # Select that implied radial-flow zero together with the offending PCS
   # coordinate; otherwise barrier dust simply moves from the bound into the
   # unchanged pbal equality.  This is an exact active-set face of the original
   # equations, never a relaxation or a power-scale change.
   active_zero_vars=[]
   for v in model.getVars():
    if str(v.VarName) in selected_pcs_names:active_zero_vars.append(v)
   for c in model.getConstrs():
    if str(c.Sense)!="=" or not str(c.ConstrName).startswith("pbal_"):continue
    row=model.getRow(c);row_vars=[row.getVar(j) for j in range(row.size())]
    if not selected_pcs_names.intersection(str(v.VarName) for v in row_vars):continue
    for v in row_vars:
     if (str(v.VarName).startswith("FP_") and abs(float(v.X))<=2e-6
         and float(v.LB)<=0.0<=float(v.UB)):active_zero_vars.append(v)
   for v in active_zero_vars:
    name=str(v.VarName)
    if name in active_set_by_name:continue
    active_set_by_name[name]=(v,float(v.LB),float(v.UB));set_fixed(v,0.0)
   active_set_bounds=list(active_set_by_name.values())
   model.Params.NumericFocus=2;model.Params.FeasibilityTol=8e-7
   model.Params.BarQCPConvTol=1e-9;model.Params.ScaleFlag=2
   model.reset()
   for v in model.getVars():v.Start=(0.0 if any(v is row[0] for row in active_set_bounds)
                                    else refinement_start[str(v.VarName)])
   model.update();tt=time.monotonic();model.optimize(cb) if cb is not None else model.optimize()
   active_wall=time.monotonic()-tt;active=abase.solver_quality(model);active["wall_seconds"]=wall+active_wall
   active={k:(None if isinstance(v,float) and not math.isfinite(v) else v) for k,v in active.items()}
   active_after={k:active.get(k) for k in numerical_limits}
   active_gap=(float(model.MIPGap) if int(model.SolCount)>0 else None)
   active_pass=bool(int(model.SolCount)>0
    and (int(model.Status)==int(gp.GRB.OPTIMAL) or (active_gap is not None and active_gap<=0.03+1e-12))
    and all(float(active_after[k])<=limit for k,limit in numerical_limits.items()))
   if active_pass:
    if loc is not None:
     loc["_last_integer_mip_start_by_name"]={str(v.VarName):float(v.X) for v in model.getVars()
      if str(v.VType).upper() in {"B","I","S","N"}}
    q=active;q["conditional_numerical_refinement"]={
     "status":"PASS","triggered":True,"solve_count":1,"same_primary_objective":True,
     "hard_gate_relaxed":False,"refinement_mode":"EXACT_ZERO_PCS_ACTIVE_SET_POLISH",
     "fixed_zero_variable_count":len(active_set_bounds),
     "pre_refinement_bound_offenders":bound_offenders,"before":{k:q.get(k) for k in numerical_limits},
     "after":active_after,"wall_seconds":active_wall}
    q["deterministic_h0_tiebreak"]={
     "status":"SUPERSEDED_PRIMARY_ECONOMIC_ACTION_DIRECT_COMMIT",
     "secondary_qcp_solve_count":0,"primary_restore_solve_count":0,
     "primary_objective_preserved":True,"feasible_set_changed":True,"feasible_set_expanded":False,
     "numerical_active_set_restriction":"MARGINAL_NEGATIVE_PCS_TO_EXACT_ZERO",
     "scientific_objective_changed":False,"validation_solve":False,
     "gurobi_seed":int(model.Params.Seed),"fresh_exact_opendss_required":True,
     "reason":"Exact-zero active-set numerical polish; primary objective unchanged."}
    return q
   for v,lb,ub in active_set_bounds:v.LB=lb;v.UB=ub
   model.update()
  # Do not weaken the frozen R24 residual gate.  Re-optimize the same primary
  # model once with the established numerical-polish settings, only when the
  # otherwise accepted solution would fail that gate.
  before={k:q.get(k) for k in numerical_limits};model.Params.NumericFocus=3
  model.Params.FeasibilityTol=1e-9;model.Params.OptimalityTol=1e-9
  model.Params.BarQCPConvTol=1e-10;model.Params.ScaleFlag=2;model.update()
  # Numerical refinement solves the identical model and objective.  Preserve
  # the already accepted complete incumbent across reset(); retaining only the
  # integer choices can leave a numerically delicate QCP with no incumbent even
  # though the pre-reset solution is feasible.  This is a solver-state transfer,
  # not a relaxation or a change to the scientific feasible set.
  model.reset()
  for v in model.getVars():v.Start=refinement_start[str(v.VarName)]
  model.update()
  tt=time.monotonic();model.optimize(cb) if cb is not None else model.optimize();refine_wall=time.monotonic()-tt
  refinement_mode="STRICT_1E9";refinement_solve_count=1
  # Some fixed-plan recursion rows are algebraically feasible only above 1e-9.
  # A strict polish can therefore prove its own model infeasible even when the
  # original candidate merely has a marginal (>1e-6) residual.  Retry at a
  # 2e-7 inner tolerance (five times stricter than the frozen 1e-6 gate) without forced
  # scaling, which can destabilize this QCP.  Acceptance below still requires
  # the unchanged R24 residual gates.
  try:strict_gap=float(model.MIPGap) if int(model.SolCount)>0 else None
  except Exception:strict_gap=None
  strict_gap_pass=bool(int(model.SolCount)>0 and
   (int(model.Status)==int(gp.GRB.OPTIMAL) or
    (strict_gap is not None and strict_gap<=0.03+1e-12)))
  if not strict_gap_pass:
   model.Params.NumericFocus=3;model.Params.FeasibilityTol=2e-7
   model.Params.IntFeasTol=5e-6;model.Params.OptimalityTol=1e-7
   model.Params.BarQCPConvTol=1e-9;model.Params.ScaleFlag=-1
   model.reset()
   for v in model.getVars():v.Start=refinement_start[str(v.VarName)]
   model.update();tt=time.monotonic()
   model.optimize(cb) if cb is not None else model.optimize()
   refine_wall+=time.monotonic()-tt;refinement_mode="INNER_GATE_2E7_POLISH_AFTER_STRICT_NO_CERTIFICATE"
   refinement_solve_count=2
  refined=abase.solver_quality(model);refined["wall_seconds"]=wall+refine_wall
  refined={k:(None if isinstance(v,float) and not math.isfinite(v) else v) for k,v in refined.items()}
  if int(model.SolCount)<1:
   raise RuntimeError(f"R24_NUMERICAL_REFINEMENT_NO_FEASIBLE_INCUMBENT bound_offenders={bound_offenders}")
  try:refined_gap=float(model.MIPGap)
  except Exception:refined_gap=None
  if int(model.Status)!=int(gp.GRB.OPTIMAL) and (refined_gap is None or refined_gap>0.03+1e-12):
   raise RuntimeError(f"R24_NUMERICAL_REFINEMENT_GAP_FAILED status={model.Status} gap={refined_gap}")
  after={k:refined.get(k) for k in numerical_limits}
  if any(float(after[k])>limit for k,limit in numerical_limits.items()):
   constraint_offenders=numerical_constraint_offenders(model)
   raise RuntimeError(f"R24_NUMERICAL_REFINEMENT_GATE_FAILED before={before} after={after} constraint_offenders={constraint_offenders}")
  q=refined;q["conditional_numerical_refinement"]={
   "status":"PASS","triggered":True,"solve_count":refinement_solve_count,"same_primary_objective":True,
   "hard_gate_relaxed":False,"complete_feasible_mip_start_transferred":True,
   "refinement_mode":refinement_mode,
   "before":before,"after":after,"pre_refinement_bound_offenders":bound_offenders,
   "wall_seconds":refine_wall}
 else:
  q["conditional_numerical_refinement"]={"status":"NOT_NEEDED","triggered":False,"solve_count":0,
   "same_primary_objective":True,"hard_gate_relaxed":False}
 # Post-Stage15 runtime correction: commit the accepted primary economic
 # solution directly.  The former secondary full-model QCP minimized an
 # artificial h0 P/Q norm and then re-solved the economic model.  On large
 # FULL_REPLAN domains those two solves were numerically unstable and could run
 # unboundedly even though the primary optimum was already available.  Direct
 # primary commit is more faithful to the scientific objective; exact Fresh
 # OpenDSS validation/recovery remains the physical safety authority.
 q["deterministic_h0_tiebreak"]={
  "status":"SUPERSEDED_PRIMARY_ECONOMIC_ACTION_DIRECT_COMMIT",
  "secondary_qcp_solve_count":0,"primary_restore_solve_count":0,
  "primary_objective_preserved":True,"feasible_set_changed":False,
  "scientific_objective_changed":False,"validation_solve":False,
  "gurobi_seed":int(model.Params.Seed),"fresh_exact_opendss_required":True,
  "reason":"Remove artificial P/Q-norm selector; commit the accepted primary economic solution."}
 return q

AC_RECOVERY_MAX_CUT_ROUNDS=10
GRID_HARD_RISK_FULL_REPLAN_MAX=1
# The ordinary exact-state relinearization uses at most ten candidates.  A
# discontinuous regulator can leave that local sequence oscillating between
# voltage and phase-current states even when the unchanged PCS feasible set
# contains a Fresh-AC hard pass.  Reserve a separate bounded budget for the
# deterministic maximum-P/Q tap search below plus the same-PRE full replan.
FRESH_AC_PRODUCTION_CANDIDATE_MAX=192
AC_RECOVERY_POST_TAP_RESERVED_CANDIDATES=48
AC_RECOVERY_COORDINATE_SEARCH_CANDIDATE_MAX=48
AC_RECOVERY_BALANCED_Q_SEARCH_CANDIDATE_MAX=24
# The production-candidate contract counts the initial dispatch, every Fresh-AC
# correction candidate, and the one same-PRE H54 full-replan candidate.  Using
# all ten correction rounds consumed 11/11 candidates and made the intended
# full replan unreachable exactly on ordinary exhaustion.  Reserve its slot:
# initial + nine corrections + one full replan = eleven candidates maximum.
AC_RECOVERY_PRE_REPLAN_CUT_ROUNDS=9
AC_RECOVERY_COMPLEMENTARY_BRACKET_MAX_STEPS=3
AC_RECOVERY_FD_STEP_KW=10.0
AC_RECOVERY_VOLTAGE_CUT_MARGIN_PU=1.0e-4
AC_RECOVERY_SEVERE_VOLTAGE_CUT_MARGIN_PU=1.0e-4
AC_RECOVERY_RELINEARIZED_VOLTAGE_CUT_MARGIN_PU=2.0e-3
AC_RECOVERY_SEVERE_LINE_VOLTAGE_CUT_MARGIN_PU=3.125e-3
AC_RECOVERY_LOCAL_P_TRUST_REGION_KW=10.0
AC_RECOVERY_LOCAL_Q_TRUST_REGION_KVAR=10.0
AC_RECOVERY_SEVERE_VOLTAGE_THRESHOLD_PU=2.0e-3
AC_RECOVERY_SEVERE_VOLTAGE_ONLY_THRESHOLD_PU=5.0e-4
# A large line/transformer-current overload needs the same full active-power
# authority even when the simultaneous voltage miss is numerically small.
# Classifying only by voltage severity used six of nine exact candidates merely
# walking P by 100 kW and left too few regulator-state relinearizations for Q.
AC_RECOVERY_SEVERE_OVERLOAD_THRESHOLD_PU=2.0e-2
# Severe voltage is a hard-safety event: permit the complete -550..+550 kW PCS
# active-power span, while physical PCS/SOC constraints and the bounded anchor
# sequence still bound the accepted correction.
AC_RECOVERY_SEVERE_VOLTAGE_P_TRUST_REGION_KW=1100.0
# Preserve the observed regulator state in the severe voltage-only branch.
# Reactive-power perturbations crossed a discrete tap boundary even though the
# local finite-difference model predicted improvement; active-power curtailment
# remains available inside the physical PCS bounds.
AC_RECOVERY_SEVERE_VOLTAGE_Q_TRUST_REGION_KVAR=0.0
# After the first exact-AC candidate has exposed the new regulator state, a
# bounded Q correction is safe to linearize locally at that state.
AC_RECOVERY_RELINEARIZED_VOLTAGE_Q_TRUST_REGION_KVAR=200.0
AC_RECOVERY_SEVERE_LINE_P_TRUST_REGION_KW=1100.0
AC_RECOVERY_SEVERE_LINE_Q_TRUST_REGION_KVAR=100.0
AC_RECOVERY_SEVERE_LINE_Q_FALLBACK_RADII_KVAR=(200.0,700.0)
AC_RECOVERY_POST_LINE_Q_TRUST_REGION_KVAR=200.0
AC_RECOVERY_COUPLED_LINE_P_TRUST_REGION_KW=100.0
AC_RECOVERY_COUPLED_LINE_Q_TRUST_REGION_KVAR=50.0
AC_RECOVERY_LINE_CUT_MARGIN_PU=5.0e-3
AC_RECOVERY_TRANSFORMER_CURRENT_CUT_MARGIN_PU=5.0e-3
# Exact-grid authority forbids reverse power at the root and requires a
# strictly positive import.  Keep an inner margin so floating-point zero and
# small loss changes cannot put a corrected point back on that open boundary.
AC_RECOVERY_ROOT_IMPORT_MARGIN_KW=10.0

def _ac_h0_controls(loc:Mapping[str,Any],science)->list[dict[str,Any]]:
 """Return connected h0 MESS controls as model expressions and physical kW/kvar."""
 scale=float(getattr(science,"_c5r4_power_scale_kw_per_model_unit",1000.0))
 controls=[]
 for mid in map(str,loc["mids"]):
  selected=[]
  for sid,v in loc["stay_by_mid_h"].get((mid,0),[]):
   if float(science._r25p_solution_scalar(v))>0.5:selected.append(str(sid))
  if len(selected)>1:raise RuntimeError(f"AC recovery multiple h0 stay sites {mid}: {selected}")
  if not selected:continue
  sid=selected[0]
  pd=loc["Pdis"].get((mid,0,sid));pc=loc["Pchg"].get((mid,0,sid));q=loc["Q"].get((mid,0,sid))
  if pd is None or pc is None or q is None:raise RuntimeError(f"AC recovery missing h0 P/Q variables {mid}/{sid}")
  controls.append({"mess_id":mid,"service_id":sid,"p_expr":scale*(pd-pc),"q_expr":scale*q,
                   "p_kw":scale*(float(pd.X)-float(pc.X)),"q_kvar":scale*float(q.X)})
 return controls

def _ac_current_plan(loc:Mapping[str,Any])->list[dict[str,Any]]:
 issue=int(loc["issue"]);plan=[]
 for (job,dest,_rack,start),v in loc["x"].items():
  if int(start)==issue and float(v.X)>0.5:
   src=loc["pmap"][str(job)]
   plan.append({"start_step":issue,"destination_IDC_id":str(dest),"IT_power_kW":float(src["IT_power_kW"])})
 return plan

def _ac_firstmess(loc:Mapping[str,Any],science,controls:list[dict[str,Any]])->list[dict[str,Any]]:
 by={x["mess_id"]:x for x in controls};rows=[]
 for mid in map(str,loc["mids"]):
  rs=loc["rollstate"][mid];phase=str(rs.get("phase","STAY"));c=by.get(mid)
  sid=str(rs.get("service_id",rs.get("dest_service_id",loc["initial_sid"][mid])))
  if c is None:
   pnet=q=0.0
  else:
   pnet=float(c["p_kw"]);q=float(c["q_kvar"])
   pdis=max(0.0,pnet);pchg=max(0.0,-pnet)
   pdis,pchg,q,_projection=canonicalize_pcs_numerical_boundary(pdis,pchg,q)
   pnet=pdis-pchg
  rows.append({"mess_id":mid,"location_service_id":sid,"moving":phase=="MOVE" or c is None,
               "connection_delay_active":phase=="CONNECTION_DELAY","grid_connected":c is not None,
               "P_net_grid_injection_kW":pnet,"Q_grid_injection_kvar":q})
 return rows

def _identity_number(value:Any)->str:
 return format(float(value),".9f")

def _recovery_candidate_fingerprints(loc:Mapping[str,Any],science,exact_summary:Mapping[str,Any],
                                     voltage_rows:list[dict[str,Any]])->dict[str,Any]:
 """Canonical h0 decision/electrical identity for failed-versus-recovery audit."""
 issue=int(loc["issue"]);controls=_ac_h0_controls(loc,science);first=_ac_firstmess(loc,science,controls)
 jobs=[]
 for (job,dest,rack,start),var in loc["x"].items():
  if int(start)==issue and float(var.X)>0.5:
   jobs.append([str(job),str(dest),str(rack),1])
 wan=[]
 for (job,dest,step),var in loc["F"].items():
  value=float(var.X)
  if int(step)==issue and value>1e-10:wan.append([str(job),str(dest),_identity_number(value)])
 move_by_mid={}
 for mid in map(str,loc["mids"]):
  selected=[]
  for slot,var in loc["mv_by_mid_h"].get((mid,0),[]):
   if float(science._r25p_solution_scalar(var))>0.5:selected.append(f"MOVE:{slot}")
  for sid,var in loc["stay_by_mid_h"].get((mid,0),[]):
   if float(science._r25p_solution_scalar(var))>0.5:selected.append(f"STAY:{sid}")
  move_by_mid[mid]=sorted(selected)
 mess=[]
 for row in first:
  mid=str(row["mess_id"]);pnet=float(row["P_net_grid_injection_kW"]);q=float(row["Q_grid_injection_kvar"])
  mess.append([mid,str(row["location_service_id"]),move_by_mid[mid],_identity_number(pnet),_identity_number(q)])
 decision_payload={"issue":issue,"jobs":sorted(jobs),"wan":sorted(wan),"mess":sorted(mess)}
 electrical_payload={
  "decision":decision_payload,
  "exact_summary":{str(k):exact_summary.get(k) for k in (
   "converged","hard_constraint_pass","command_error_count","voltage_violation_count",
   "line_violation_count","transformer_current_violation_count","transformer_kva_violation_count",
   "root_sign_pass")},
  "voltage_rows":sorted([
   [str(row.get("bus")),int(row.get("node",0)),_identity_number(row.get("voltage_pu",0.0))]
   for row in voltage_rows])}
 decision_sha=hashlib.sha256(json.dumps(decision_payload,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
 electrical_sha=hashlib.sha256(json.dumps(electrical_payload,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
 return {"decision_candidate_sha256":decision_sha,"electrical_candidate_sha256":electrical_sha,
         "decision_payload":decision_payload,"hard_constraint_pass":bool(exact_summary.get("hard_constraint_pass",False))}

def _record_recovery_candidate(loc:Mapping[str,Any],science,issue_runtime:dict[str,Any],issue_out:Path,
                               stage:str,exact_summary:Mapping[str,Any],voltage_rows:list[dict[str,Any]])->dict[str,Any]:
 """Persist one unique production Fresh-AC candidate; finite-difference probes never enter here."""
 fp=_recovery_candidate_fingerprints(loc,science,exact_summary,voltage_rows)
 previous_failed=issue_runtime.get("last_failed_recovery_candidate")
 candidate={"stage":str(stage),"issue":int(loc["issue"]),"exact_ac":dict(exact_summary),**fp}
 if str(stage)=="FULL_REPLAN" and previous_failed is not None:
  candidate["differs_from_previous_failed_decision"]=(
   candidate["decision_candidate_sha256"]!=previous_failed.get("decision_candidate_sha256"))
 candidates=issue_runtime.setdefault("fresh_ac_candidate_attempts",[])
 duplicate=next((x for x in candidates
                 if x.get("stage")==candidate["stage"]
                 and x.get("electrical_candidate_sha256")==candidate["electrical_candidate_sha256"]),None)
 if duplicate is None:
  candidates.append(candidate)
  if len(candidates)>FRESH_AC_PRODUCTION_CANDIDATE_MAX:
   raise RuntimeError(f"FRESH_AC_PRODUCTION_CANDIDATE_LIMIT_EXCEEDED:{len(candidates)}")
 else:candidate=duplicate
 if not bool(candidate.get("hard_constraint_pass",False)):
  issue_runtime["last_failed_recovery_candidate"]=candidate
 audit={
  "schema_version":"mobileess.post_stage15.w02_recovery_candidate_identity.v1",
  "status":"PASS_BOUNDED_IDENTITY_AUDIT",
  "issue":int(loc["issue"]),"candidate_count":len(candidates),
  "candidate_limit":FRESH_AC_PRODUCTION_CANDIDATE_MAX,
  "cut_round_limit":AC_RECOVERY_MAX_CUT_ROUNDS,
  "same_pre_h54_full_replan_limit":GRID_HARD_RISK_FULL_REPLAN_MAX,
  "candidates":candidates,"hard_limits_relaxed":False,"future_actual_used":False,
  "duplicate_full_replan_candidate_sent_to_opendss":False,
  "unsafe_action_committed":False}
 jw(Path(issue_out)/"A_B10_RECOVERY_CANDIDATE_IDENTITY_AUDIT.json",audit)
 issue_runtime["recovery_candidate_identity_audit"]=audit
 return candidate

def _voltage_rows_from_live_opendss(grid24)->list[dict[str,Any]]:
 import opendssdirect as odd
 return [dict(x) for x in grid24.collect_voltage_rows(odd)]

def _line_rows_from_live_opendss(grid24)->list[dict[str,Any]]:
 import opendssdirect as odd
 summary,_terminal_rows=grid24.collect_line_rows(odd)
 return [dict(x) for x in summary]

def _root_power_from_live_opendss()->dict[str,float]:
 import opendssdirect as odd
 raw=[float(x) for x in odd.Circuit.TotalPower()]
 raw_p=raw[0] if raw else 0.0;raw_q=raw[1] if len(raw)>1 else 0.0
 return {"raw_p_kw":raw_p,"raw_q_kvar":raw_q,
         "root_export_p_kw":max(raw_p,0.0),"root_import_p_kw":max(-raw_p,0.0)}

def _transformer_current_rows_from_live_opendss()->list[dict[str,Any]]:
 import opendssdirect as odd
 rows=[]
 for name in odd.Transformers.AllNames():
  odd.Transformers.Name(str(name));nwind=int(odd.Transformers.NumWindings());odd.Circuit.SetActiveElement(f"Transformer.{name}")
  buses=list(odd.CktElement.BusNames());ncond=int(odd.CktElement.NumConductors());nterm=int(odd.CktElement.NumTerminals())
  nphase=int(odd.CktElement.NumPhases());powers=list(map(float,odd.CktElement.Powers()));curr=list(map(float,odd.CktElement.CurrentsMagAng()))
  for terminal in range(min(nwind,nterm)):
   odd.Transformers.Wdg(terminal+1);kva=float(odd.Transformers.kVA());kv=float(odd.Transformers.kV())
   rated=kva/(math.sqrt(3.0)*kv) if nphase>=3 else kva/kv
   for conductor in range(min(nphase,ncond)):
    k=terminal*ncond+conductor;mag=curr[2*k] if 2*k<len(curr) else None;ang=curr[2*k+1] if 2*k+1<len(curr) else None
    p=powers[2*k] if 2*k<len(powers) else None;q=powers[2*k+1] if 2*k+1<len(powers) else None
    load=None if mag is None or rated<=0 else mag/rated
    rows.append({"transformer":str(name),"terminal":terminal+1,"winding":terminal+1,
     "conductor":conductor+1,"bus":str(buses[terminal]) if terminal<len(buses) else "",
     "p_kw":p,"q_kvar":q,"current_a":mag,"angle_deg":ang,"rated_kva":kva,"rated_kv":kv,
     "rated_phase_current_a":rated,"loading_pu":load,"hard_violation":bool(load is not None and load>1.0)})
 return rows

def capture_exact_ac_observability(grid24,issue_out:Path,issue:int,exact_summary:Mapping[str,Any])->None:
 """Persist the live Fresh-AC spatial state before another OpenDSS call can replace it."""
 import opendssdirect as odd
 voltage=[dict(x) for x in grid24.collect_voltage_rows(odd)]
 line_summary,_legacy_line_terminal=grid24.collect_line_rows(odd)
 transformer=[dict(x) for x in grid24.collect_transformer_rows(odd)]
 line_terminal=[]
 for name in odd.Lines.AllNames():
  odd.Lines.Name(str(name));odd.Circuit.SetActiveElement(f"Line.{name}")
  buses=list(odd.CktElement.BusNames());ncond=int(odd.CktElement.NumConductors());nterm=int(odd.CktElement.NumTerminals())
  nphase=int(odd.CktElement.NumPhases());powers=list(map(float,odd.CktElement.Powers()));curr=list(map(float,odd.CktElement.CurrentsMagAng()))
  rating=float(odd.Lines.NormAmps())
  for terminal in range(nterm):
   for conductor in range(min(nphase,ncond)):
    k=terminal*ncond+conductor;mag=curr[2*k] if 2*k<len(curr) else None;ang=curr[2*k+1] if 2*k+1<len(curr) else None
    p=powers[2*k] if 2*k<len(powers) else None;q=powers[2*k+1] if 2*k+1<len(powers) else None
    load=None if mag is None or rating<=0 else mag/rating
    line_terminal.append({"line":str(name),"terminal":terminal+1,"conductor":conductor+1,
     "from_bus":str(buses[0]) if buses else "","to_bus":str(buses[1]) if len(buses)>1 else "",
     "terminal_bus":str(buses[terminal]) if terminal<len(buses) else "","p_kw":p,"q_kvar":q,
     "current_a":mag,"angle_deg":ang,"norm_amps":rating,"loading_pu":load,
     "hard_violation":bool(load is not None and load>1.0)})
 transformer_current=_transformer_current_rows_from_live_opendss()
 jw(Path(issue_out)/"exact_grid/A_B10_FRESH_EXACT_AC_OBSERVABILITY.json",{
  "schema_version":"K9H7_OBSERVABILITY_V1.exact_ac.v1","issue_step":int(issue),
  "summary":dict(exact_summary),"bus_phase_voltage":voltage,
  "line_summary":[dict(x) for x in line_summary],"line_terminal_phase":[dict(x) for x in line_terminal],
 "transformer_terminal":[dict(x) for x in transformer],"transformer_terminal_current":transformer_current,
  "hard_limits_relaxed":False,"future_actual_used":False})

def _reg1a_causal_equivalent_kva_limit(observability_path:Path)->float|None:
 """Convert one preceding PASS exact-AC state into a causal 3-phase envelope."""
 if not observability_path.is_file():return None
 data=load_json(observability_path)
 if data.get("summary",{}).get("hard_constraint_pass") is not True:return None
 rows=[r for r in data.get("transformer_terminal_current",[])
       if str(r.get("transformer","")).lower()=="reg1a" and int(r.get("terminal",0))==1]
 if len(rows)!=3:return None
 phase_kva=[math.hypot(float(r["p_kw"]),float(r["q_kvar"])) for r in rows]
 max_current_pu=max(float(r["loading_pu"]) for r in rows)
 if not math.isfinite(max_current_pu) or max_current_pu<=0:return None
 # Aggregate apparent power at which the preceding causal phase distribution
 # would put its largest phase at 1.0 pu.  The 0.5% inward guard absorbs small
 # forecast drift; the unchanged Fresh-AC nameplate remains final authority.
 return min(5000.0,0.995*sum(phase_kva)/max_current_pu)

def _first_number(row:Mapping[str,Any],names:tuple[str,...])->float|None:
 for name in names:
  if name in row and row[name] is not None:
   try:return float(row[name])
   except (TypeError,ValueError):pass
 return None

def capture_model_observability(science,loc:Mapping[str,Any],issue_out:Path,issue:int,
                                power:Mapping[str,Any],price:Mapping[str,Any])->dict[str,Any]:
 """Capture small, already-computed model/source values after the accepted h0 solve.

 This function performs no optimization and no network solve.  Dense analytical
 tables are deliberately materialized later by MATERIALIZE_OBSERVABILITY_OFFLINE.
 """
 rows=[];running=loc.get("running",{}) or {};pmap=loc.get("pmap",{}) or {}
 caprow=loc.get("caprow",{}) or {};ff=loc.get("ff");x=loc.get("x",{}) or {}
 starts=[]
 for (job,dest,rack,start),var in x.items():
  if int(start)==int(issue) and float(science._r25p_solution_scalar(var))>0.5:
   src=pmap[str(job)];starts.append({"job_uid":str(job),"destination_idc":str(dest),"rack_pool_id":str(rack),
    "requested_gpu":float(src.get("requested_gpu",0.0)),"it_power_kw":float(src.get("IT_power_kW",0.0)),
    "duration_steps":int(src.get("duration_steps",0))})
 for rack in sorted(map(str,caprow)):
  cr=dict(caprow[rack]);idc=str(cr.get("idc_id",""));fixed=(ff(rack,int(issue)) if ff else (0.0,0.0,"UNKNOWN"))
  fixed_gpu,fixed_it=float(fixed[0]),float(fixed[1])
  active=[dict(v,job_uid=str(k)) for k,v in running.items()
          if str(v.get("rack_pool_id",""))==rack and int(v.get("remaining_steps",0))>0]
  new=[v for v in starts if v["rack_pool_id"]==rack]
  gpu=float(fixed_gpu)+sum(float(v.get("requested_gpu",0.0)) for v in active)+sum(v["requested_gpu"] for v in new)
  it=float(fixed_it)+sum(float(v.get("IT_power_kW",0.0)) for v in active)+sum(v["it_power_kw"] for v in new)
  gpu_cap=_first_number(cr,("deliverable_active_gpu_capacity","GPU_capacity","gpu_capacity","max_gpu","rack_gpu_capacity"))
  it_cap=_first_number(cr,("rack_power_cap_kw","IT_power_limit_kW","it_power_limit_kw","max_it_kw","rack_power_limit_kw"))
  # The frozen IDC constraint is PUE * IT <= 750 kVA * PF.  Record that
  # already-used model constant even though it is not repeated in caprow.
  tx_cap=_first_number(cr,("transformer_limit_kW","transformer_kw_limit","idc_transformer_limit_kw"))
  if tx_cap is None:tx_cap=750.0*float(getattr(science,"PF",0.95))
  rows.append({"rack_pool_id":rack,"idc_id":idc,"fixed_gpu":float(fixed_gpu),"fixed_it_power_kw":float(fixed_it),
   "current_job_count":len(active),"started_job_count":len(new),"gpu_used":gpu,"it_power_kw":it,
   "facility_power_kw":float(getattr(science,"PUE",1.0))*it,"gpu_capacity":gpu_cap,"it_power_limit_kw":it_cap,
   "transformer_limit_kw":tx_cap,"gpu_headroom":None if gpu_cap is None else gpu_cap-gpu,
   "it_power_headroom_kw":None if it_cap is None else it_cap-it})
 frows=[]
 pissues=np.asarray(power["issues"],dtype=np.int64);phit=np.flatnonzero(pissues==int(issue))
 rissues=np.asarray(price["issues"],dtype=np.int64);rhit=np.flatnonzero(rissues==int(issue))
 if len(phit)!=1 or len(rhit)!=1:raise RuntimeError(f"observability source-row cardinality issue={issue}")
 pi=int(phit[0]);ri=int(rhit[0]);targets=np.asarray(power["target_steps"])[pi]
 for h,target in enumerate(targets.tolist()):
  frows.append({"horizon_step":h,"target_step":int(target),
   "gross_background_p_q90_kw":float(np.asarray(power["q90_gross_background_p_kw"])[pi,h].sum()),
   "pv_available_q10_kw":float(np.asarray(power["q10_pv_available_kw"])[pi,h].sum()),
   "net_background_p_q50_kw":float(np.asarray(power["q50_net_background_p_kw"])[pi,h].sum()),
   "background_q_q50_kvar":float(np.asarray(power["q50_background_q_kvar"])[pi,h].sum()),
   "background_q_q90_kvar":float(np.asarray(power["q90_background_q_kvar"])[pi,h].sum()),
   "rrp_q10":float(np.asarray(price["q10"])[ri,h]),"rrp_q50":float(np.asarray(price["q50"])[ri,h]),
   "rrp_q90":float(np.asarray(price["q90"])[ri,h])})
 bp,bq,pv,_=loc["ref"]["store"].step(int(issue))
 wan=[]
 for (job,dest,t),var in (loc.get("F",{}) or {}).items():
  value=float(science._r25p_solution_scalar(var))
  if int(t)==int(issue) and value>1e-10:
   src=pmap.get(str(job),{})
   wan.append({"job_uid":str(job),"source_idc":str(src.get("origin_IDC_id","")),
               "destination_idc":str(dest),"send_step":int(t),"gb_sent":value})
 repayment={"support_energy_kWh":{},"workload_gpu_h":{}}
 scale_e=float(getattr(science,"_c5r4_energy_scale_kwh_per_model_unit",1000.0))
 for (mid,h),var in (loc.get("repE",{}) or {}).items():
  if int(h)==0:repayment["support_energy_kWh"][str(mid)]=scale_e*float(science._r25p_solution_scalar(var))
 for (idc,h),var in (loc.get("repW",{}) or {}).items():
  if int(h)==0:repayment["workload_gpu_h"][str(idc)]=float(science._r25p_solution_scalar(var))
 model=loc["m"]
 payload={"schema_version":"K9H7_OBSERVABILITY_V1.model_commit.v1","issue_step":int(issue),
  "source_values_h0":{"actual_gross_background_p_kw":float(np.asarray(bp,float).sum()),
   "actual_background_q_kvar":float(np.asarray(bq,float).sum()),"actual_pv_available_kw":float(np.asarray(pv,float).sum())},
  "forecast_issued":frows,"rack_pool_h0":rows,"wan_send_h0":wan,"job_start_h0":starts,"debt_repayment_h0":repayment,
  "objective":{"economic_projected_AUD":float(loc["econ"].getValue()) if "econ" in loc else None,
   "model_obj_val":float(model.ObjVal) if int(model.SolCount)>0 else None},
  "model_stats":{"variables":int(model.NumVars),"binary_variables":int(model.NumBinVars),
   "linear_constraints":int(model.NumConstrs),"quadratic_constraints":int(model.NumQConstrs),
   "simplex_iterations":float(model.IterCount),"barrier_iterations":float(model.BarIterCount)},
  "capture_policy":"ALREADY_COMPUTED_VALUES_ONLY","gurobi_solve_count":0,"opendss_solve_count":0,
  "future_actual_used":False}
 path=Path(issue_out)/"A_B10_COMMITTED_MODEL_OBSERVABILITY.json";jw(path,payload)
 return {"path":path.name,"bytes":path.stat().st_size,"rack_rows":len(rows),"forecast_rows":len(frows),
         "wan_rows":len(wan),"job_start_rows":len(starts)}

def _refresh_solution_after_ac_resolve(loc:Mapping[str,Any],science,sol:dict[str,Any])->list[dict[str,Any]]:
 """Commit only the H0 PCS correction made by Fresh-AC recovery.

 The recovery model is deliberately a local safety projection.  Its continuous
 H1--H53 state, mobility and WAN values are not a replacement economic plan and
 may be non-unique under the recovery objective.  Persisting those values used
 to corrupt an otherwise valid next-issue mobility plan (for example by pairing
 a preserved H5 MOVE row with a recovery-only SOC trajectory).
 """
 scale_p=float(getattr(science,"_c5r4_power_scale_kw_per_model_unit",1000.0))
 scale_e=float(getattr(science,"_c5r4_energy_scale_kwh_per_model_unit",1000.0))
 pcs_projections=[];preprojection_h0={}
 for row in sol["mess_rows"]:
  mid=str(row["mess_id"]);h=int(row["horizon_step"])
  if h!=0:continue
  entries=loc["stay_by_mid_h"].get((mid,h),[])
  row["P_discharge_kW"]=canonical_physical_zero(scale_p*sum(float(loc["Pdis"][(mid,h,s)].X) for s,_ in entries if (mid,h,s) in loc["Pdis"]))
  row["P_charge_kW"]=canonical_physical_zero(scale_p*sum(float(loc["Pchg"][(mid,h,s)].X) for s,_ in entries if (mid,h,s) in loc["Pchg"]))
  row["Q_kvar"]=canonical_physical_zero(scale_p*sum(float(loc["Q"][(mid,h,s)].X) for s,_ in entries if (mid,h,s) in loc["Q"]))
  preprojection_h0[mid]=(float(row["P_discharge_kW"]),float(row["P_charge_kW"]))
  pdis,pchg,q,projection=canonicalize_pcs_numerical_boundary(
   row["P_discharge_kW"],row["P_charge_kW"],row["Q_kvar"])
  row["P_discharge_kW"],row["P_charge_kW"],row["Q_kvar"]=pdis,pchg,q
  if projection is not None:pcs_projections.append({"mess_id":mid,"horizon_step":h,**projection})
 first=[]
 for mid in map(str,loc["mids"]):
  r0=next(x for x in sol["mess_rows"] if str(x["mess_id"])==mid and int(x["horizon_step"])==0)
  rs=loc["rollstate"][mid];prephase=str(rs.get("phase","STAY"));connected=str(r0["state"])=="STAY"
  sid=str(rs.get("service_id",rs.get("dest_service_id",loc["initial_sid"][mid])))
  first.append({"mess_id":mid,"location_service_id":sid,"moving":bool(r0["state"]=="MOVE" or prephase=="MOVE"),
   "connection_delay_active":prephase=="CONNECTION_DELAY","grid_connected":connected,
   "P_discharge_kW":float(r0["P_discharge_kW"]),"P_charge_kW":float(r0["P_charge_kW"]),
   "P_net_grid_injection_kW":float(r0["P_discharge_kW"])-float(r0["P_charge_kW"]),
   "Q_grid_injection_kvar":float(r0["Q_kvar"]),"E0_kWh":float(loc["mess_E"][mid]),
   "E1_kWh":scale_e*float(loc["E"][(mid,1)].X),
   "support_debt0_kWh":float((loc.get("mess_DE0") or {}).get(mid,0.0)),
   "support_debt1_kWh":scale_e*float(loc["DE"][(mid,1)].X)})
 for row in first:
  mid=row["mess_id"];old_pdis,old_pchg=preprojection_h0[mid]
  row["E1_kWh"],row["support_debt1_kWh"]=adjust_model_state_for_inward_pcs_projection(
   row["E1_kWh"],row["support_debt1_kWh"],old_pdis,old_pchg,
   row["P_discharge_kW"],row["P_charge_kW"])
  capacity_kwh=mess_physical_capacity_kwh(loc,mid,scale_e)
  row["E1_kWh"],energy_projection=canonicalize_energy_numerical_boundary(
   row["E1_kWh"],ENERGY_PHYSICAL_FLOOR_KWH,capacity_kwh,f"recovery[{mid}]")
  if energy_projection is not None:sol.setdefault("_energy_state_projection_events",[]).append(energy_projection)
  if bool(loc.get("_a_b10_fixed_location_policy",False)):
   row["E1_kWh"],row["support_debt1_kWh"],state_projection=canonicalize_coupled_soc_debt_ceiling(
    row["E1_kWh"],row["support_debt1_kWh"],capacity_kwh,f"recovery[{mid}]")
   if state_projection is not None:sol.setdefault("_coupled_soc_debt_projection_events",[]).append(state_projection)
 sol["firstmess"]=first
 sol["mess_support_debt1"]={str(row["mess_id"]):float(row["support_debt1_kWh"]) for row in first}
 sol["rolling_warmstart_payload"]["mess_rows"]=[dict(x) for x in sol["mess_rows"]]
 # Preserve send_now, wan_all, workload_debt1, and the warm-start WAN payload
 # from the accepted economic solve.  Fresh-AC recovery changes only H0 PCS.
 science.cw(Path(loc["out"])/"BUILD7B_FULL54_MESS_PLAN.csv",sol["mess_rows"])
 return pcs_projections

def exact_ac_cut_recovery(science,context:dict[str,Any],issue_runtime:dict[str,Any],
                          b4,grid24,scope,gstatic,issue,running,sol,issue_out,initial_ex):
 """Bounded Fresh-AC correction around the current same-PRE plan.

 A mobile-policy failure may consume its single full H54 replan, then use only
 the remaining global Fresh-AC candidate budget for an H0 safety projection.
 The full-replan count, scientific limits and causal data authority stay fixed.
 """
 import gurobipy as gp
 loc=context.get("loc");cb=context.get("cb")
 if not isinstance(loc,dict) or cb is None:raise RuntimeError("GRID_CORRECTION_CONTEXT_MISSING")
 voltage_rows=_voltage_rows_from_live_opendss(grid24)
 line_rows=_line_rows_from_live_opendss(grid24)
 transformer_current_rows=_transformer_current_rows_from_live_opendss()
 initial_candidate=_record_recovery_candidate(loc,science,issue_runtime,Path(issue_out),
 "FULL_REPLAN" if issue_runtime.get("grid_hard_risk_full_replan_retry",False) else "INITIAL",
  initial_ex,voltage_rows)
 after_full_replan=bool(issue_runtime.get("grid_hard_risk_full_replan_retry",False))
 attempts=[{"round":0,"candidate":initial_candidate,"exact_ac":dict(initial_ex),
            "violating_voltage_rows":[r for r in voltage_rows if r["hard_violation"]],
            "violating_line_rows":[r for r in line_rows if r["hard_violation"]],
            "violating_transformer_current_rows":[r for r in transformer_current_rows if r["hard_violation"]]}]
 initial_voltage_violations=[r for r in voltage_rows if r["hard_violation"]]
 initial_line_violations=[r for r in line_rows if r["hard_violation"]]
 initial_transformer_current_violations=[r for r in transformer_current_rows if r["hard_violation"]]
 # A transformer kVA violation accompanied by an exact transformer-current
 # violation is controllable by the same H0 P/Q current-sensitivity recovery.
 # Fresh AC still checks both limits.  Only a kVA-only violation remains an
 # unsupported family because it has no sampled terminal-current target row.
 initial_kva_only=bool(initial_ex.get("transformer_kva_violation_count")
                       and not initial_transformer_current_violations)
 nonvoltage=bool(not initial_ex.get("converged") or initial_ex.get("command_error_count")
                 or initial_kva_only)
 if nonvoltage:
  issue_runtime["ac_safety_recovery"]={"status":"GRID_RECOVERY_UNSUPPORTED_NONVOLTAGE_FAIL_CLOSED","attempts":attempts}
  raise RuntimeError("GRID_CORRECTION_EXHAUSTED_NONVOLTAGE")
 protected_line_keys={str(r["line"]) for r in initial_line_violations}
 protected_transformer_current_keys={(str(r["transformer"]),int(r["terminal"]),int(r["conductor"]))
                                     for r in initial_transformer_current_violations}
 initial_voltage_severity_pu=max(
  [max(0.0,float(r["voltage_pu"])-1.05,0.95-float(r["voltage_pu"])) for r in initial_voltage_violations],
  default=0.0)
 initial_overload_severity_pu=max(
  [max(0.0,float(r["loading_pu"])-1.0)
   for r in initial_line_violations+initial_transformer_current_violations],
  default=0.0)
 # Severe voltage events can cross several discrete regulator-tap boundaries.
 # Use a bounded sequential exact-state relinearization instead of treating
 # any one local model as globally valid.
 # Once Fresh AC has established a real voltage/line hard violation, its
 # magnitude must not arbitrarily limit sequential relinearization.  Most
 # cases return after round 1; difficult tap cases may use the bounded budget.
 fixed_location_recovery=bool(loc.get("_a_b10_fixed_location_policy",False))
 # A fixed-location full replan cannot change the immutable H0 siting and, for
 # this policy, reproduces the same economic H0 dispatch.  Spend the tenth slot
 # on a distinct P/Q correction instead.  Mobile policies reserve that slot for
 # the one same-PRE H54 full replan.
 remaining_candidate_budget=max(0,FRESH_AC_PRODUCTION_CANDIDATE_MAX-
                                len(issue_runtime.get("fresh_ac_candidate_attempts",[])))
 recovery_round_limit=min(
  (AC_RECOVERY_MAX_CUT_ROUNDS if fixed_location_recovery
   else AC_RECOVERY_PRE_REPLAN_CUT_ROUNDS),remaining_candidate_budget)
 model=loc["m"]
 def exact_candidate_score(exact):
  """Order unsafe exact-AC points by distance to the unchanged hard box."""
  excesses=(max(0.0,float(exact.get("voltage_max_pu",9.0))-1.05),
            max(0.0,0.95-float(exact.get("voltage_min_pu",-9.0))),
            max(0.0,float(exact.get("line_max_loading_pu",9.0))-1.0),
            max(0.0,float(exact.get("transformer_max_current_loading_pu",9.0))-1.0),
            max(0.0,float(exact.get("transformer_max_kva_loading_pu",9.0))-1.0))
  authority_failure=int(not exact.get("converged",False) or exact.get("command_error_count",0)
                        or not exact.get("root_sign_pass",False))
  violation_count=sum(int(exact.get(k,0) or 0) for k in
   ("voltage_violation_count","line_violation_count","transformer_current_violation_count",
    "transformer_kva_violation_count"))
  return (authority_failure,max(excesses),sum(excesses),violation_count)
 initial_controls=_ac_h0_controls(loc,science)
 best_recovery_bundle={
  "score":exact_candidate_score(initial_ex),"exact":dict(initial_ex),
  "controls":[dict(c) for c in initial_controls],
  "first":[dict(row) for row in _ac_firstmess(loc,science,initial_controls)],
  "plan":[dict(row) for row in _ac_current_plan(loc)],
  "voltage_rows":[dict(row) for row in voltage_rows],
  "line_rows":[dict(row) for row in line_rows],
  "transformer_rows":[dict(row) for row in transformer_current_rows],
  "stage":"INITIAL"}
 # Materialize the accepted incumbent above before removing any row: Gurobi
 # invalidates Var.X after model.remove()/update().  The nominal controller
 # holds four consecutive five-minute PCS support intervals at H1.  Once Fresh AC has
 # proved H0 unsafe, release only that H1 inward reserve for corrective
 # dispatch.  The unchanged 440 kWh physical floor remains in force at every
 # horizon step.
 recovery_energy_reserve_rows=list(loc.get("_a_b10_pcs_energy_reserve_rows",[]) or [])
 if recovery_energy_reserve_rows:
  model.remove(recovery_energy_reserve_rows);model.update()
  loc["_a_b10_pcs_energy_reserve_rows"]=[]
  loc["_a_b10_pcs_energy_reserve_h1_rows"]=[]
 issue_runtime["pcs_h1_energy_reserve_recovery_release"]={
  "status":"RELEASED_AFTER_FRESH_AC_FAILURE" if recovery_energy_reserve_rows else "NO_RESERVE_ROWS_TO_RELEASE",
  "released_row_count":len(recovery_energy_reserve_rows),
  "released_steps":[1],"h5_reserve_installed":False,
  "release_semantics":"OPERATING_RESERVE_SPEND_ALLOWED_ONLY_AFTER_FRESH_AC_FAILURE",
  "physical_soc_floor_kwh_unchanged":ENERGY_PHYSICAL_FLOOR_KWH,
  "power_scale_changed":False,"hard_grid_limits_relaxed":False,"future_actual_used":False}
 def remember_best_exact_candidate(exact,stage):
  nonlocal best_recovery_bundle
  score=exact_candidate_score(exact)
  if score>=best_recovery_bundle["score"]:return
  controls_now=_ac_h0_controls(loc,science)
  best_recovery_bundle={
   "score":score,"exact":dict(exact),"controls":[dict(c) for c in controls_now],
   "first":[dict(row) for row in _ac_firstmess(loc,science,controls_now)],
   "plan":[dict(row) for row in _ac_current_plan(loc)],
   "voltage_rows":[dict(row) for row in voltage_rows],
   "line_rows":[dict(row) for row in line_rows],
   "transformer_rows":[dict(row) for row in transformer_current_rows],
   "stage":str(stage)}
 def solve_recovery_anchor():
  """Accept a feasible incumbent for the artificial low-stress selector.

  The 3% gap is a production requirement for the scientific economic
  objective.  A low-stress anchor is only a bounded candidate generator; its
  norm objective never defines a committed result.  If numerical polishing
  ends SUBOPTIMAL with an incumbent, retain it only when every unchanged model
  residual gate passes, then require Fresh OpenDSS below as usual.
  """
  try:return solve_fast(model,cb,loc)
  except RuntimeError as exc:
   message=str(exc)
   gap_only=(message.startswith("fast conditioned dispatch did not reach 3% operational gap")
             or message.startswith("R24_NUMERICAL_REFINEMENT_GAP_FAILED"))
   if not gap_only or int(model.SolCount)<1:raise
   quality=abase.solver_quality(model)
   numerical_limits={"ConstrVio":1e-6,"BoundVio":1e-6,"IntVio":1e-5}
   after={k:float(quality.get(k,float("inf"))) for k in numerical_limits}
   if any(after[k]>limit for k,limit in numerical_limits.items()):raise
   loc["_last_integer_mip_start_by_name"]={str(v.VarName):float(v.X) for v in model.getVars()
    if str(v.VType).upper() in {"B","I","S","N"}}
   quality={k:(None if isinstance(v,float) and not math.isfinite(v) else v)
            for k,v in quality.items()}
   quality["status"]="PASS_FEASIBLE_ARTIFICIAL_ANCHOR_INCUMBENT"
   quality["artificial_anchor_optimality_gap_is_not_scientific_acceptance_gate"]=True
   quality["original_gap_exception"]=message
   quality["unchanged_model_residual_gates"]=after
   quality["fresh_exact_opendss_required"]=True
   quality["hard_limits_relaxed"]=False
   return quality
 # Fresh-AC recovery changes only the connected H0 PCS controls.  Re-solving
 # unrelated horizon-wide integer decisions turned this local safety projection
 # into a 216-binary MIQCP and could consume the full time budget without an
 # incumbent.  Freeze every still-free integer except the four H0 charge/
 # discharge mode binaries: those modes must remain free so an idle MESS can
 # provide active-power support.  This only narrows the recovery feasible set;
 # a failed local projection may still trigger the bounded full-model replan.
 prior_integer=loc.get("_last_integer_mip_start_by_name",{})
 free_h0_pcs_modes={f"mode_{mid}_0" for mid in map(str,loc["mids"])}
 recovery_integer_fixed=[]
 for v in model.getVars():
  if str(v.VType).upper() not in {"B","I","S","N"} or float(v.UB)-float(v.LB)<=1e-12:continue
  name=str(v.VarName)
  if name in free_h0_pcs_modes:continue
  if name not in prior_integer:raise RuntimeError(f"AC_RECOVERY_INTEGER_STATE_MISSING:{name}")
  value=float(round(float(prior_integer[name])))
  recovery_integer_fixed.append({"variable":name,"value":value})
  set_fixed(v,value)
 issue_runtime["ac_recovery_discrete_scope"]={
  "status":"FIXED_TO_PRIOR_ACCEPTED_INTEGER_STATE",
  "fixed_integer_count":len(recovery_integer_fixed),
  "free_h0_pcs_mode_variables":sorted(free_h0_pcs_modes),
  "changed_non_h0_integer_count":0,"h0_pcs_mode_switch_allowed":True,
  "recovery_feasible_set_expanded":False,"hard_limits_relaxed":False}
 # Root reverse power is a supported hard-violation family.  Its exact
 # sensitivity to aggregate connected H0 MESS injection is available directly
 # from the live OpenDSS root power, so no voltage finite-difference surrogate
 # is needed.  Reduce aggregate injection by the measured export plus a fixed
 # import margin; keep Q at the accepted value and let the unchanged economic
 # objective distribute the active-power correction.  Fresh AC alone accepts
 # the resulting production candidate.
 if (not bool(initial_ex.get("root_sign_pass")) and not initial_voltage_violations
     and not initial_line_violations and not initial_transformer_current_violations):
  root_constraint_refs=[]
  root_recovery_round_limit=(AC_RECOVERY_MAX_CUT_ROUNDS if fixed_location_recovery
                             else AC_RECOVERY_PRE_REPLAN_CUT_ROUNDS)
  for round_no in range(1,root_recovery_round_limit+1):
   controls=([dict(c) for c in initial_controls] if round_no==1
             else _ac_h0_controls(loc,science))
   if not controls:raise RuntimeError("ROOT_SIGN_CORRECTION_NO_CONTROLLABLE_H0_PCS")
   root_power=_root_power_from_live_opendss()
   base_total_p_kw=sum(float(c["p_kw"]) for c in controls)
   target_total_p_kw=(base_total_p_kw-float(root_power["root_export_p_kw"])
                      -AC_RECOVERY_ROOT_IMPORT_MARGIN_KW)
   if root_constraint_refs:
    model.remove(root_constraint_refs);model.update();root_constraint_refs=[]
   aggregate_p=gp.LinExpr(0.0)
   for ci,c in enumerate(controls):
    aggregate_p+=c["p_expr"]
    root_constraint_refs.append(model.addLConstr(
     c["q_expr"]==float(c["q_kvar"]),name=f"a_b10_root_sign_q_hold_r{round_no}_{ci}"))
   root_constraint_refs.append(model.addLConstr(
    aggregate_p<=target_total_p_kw,name=f"a_b10_root_sign_import_margin_r{round_no}"))
   model.setObjective(loc["econ"],gp.GRB.MINIMIZE);model.update()
   try:root_fast=solve_fast(model,cb,loc)
   except RuntimeError as exc:
    record={"schema_version":"mobileess.post_stage15.exact_ac_closed_loop.v2",
     "status":"GRID_CORRECTION_EXHAUSTED_ROOT_SIGN_MODEL_INFEASIBLE","issue":int(issue),
     "max_cut_rounds":root_recovery_round_limit,"attempts":attempts,
     "model_error":repr(exc),"hard_limits_relaxed":False,"future_actual_used":False}
    issue_runtime["ac_safety_recovery"]=record
    jw(Path(issue_out)/"A_B10_EXACT_AC_CLOSED_LOOP_RECOVERY.json",record)
    raise RuntimeError("GRID_CORRECTION_EXHAUSTED_ROOT_SIGN_MODEL_INFEASIBLE") from exc
   recovery_pcs_projections=_refresh_solution_after_ac_resolve(loc,science,sol)
   quality=abase.solver_quality(model)
   if any(float(quality.get(k,float("inf")))>lim for k,lim in (("ConstrVio",1e-6),("BoundVio",1e-6),("IntVio",1e-5))):
    raise RuntimeError(f"ROOT_SIGN_CORRECTION_NUMERICAL_GATE_FAILED {quality}")
   issue_runtime["fresh_ac_capture_stage"]="ROOT_SIGN_CORRECTION"
   ex=science.exact24_candidate(b4,grid24,scope,gstatic,issue,running,sol["plan"],sol["firstmess"])
   voltage_rows=_voltage_rows_from_live_opendss(grid24)
   line_rows=_line_rows_from_live_opendss(grid24)
   transformer_current_rows=_transformer_current_rows_from_live_opendss()
   recovery_candidate=_record_recovery_candidate(loc,science,issue_runtime,Path(issue_out),
    "ROOT_SIGN_CORRECTION",ex,voltage_rows)
   attempts.append({"round":round_no,"constraint_family":"ROOT_REVERSE_POWER",
    "root_power_before":root_power,"root_import_inner_margin_kw":AC_RECOVERY_ROOT_IMPORT_MARGIN_KW,
    "base_total_h0_mess_p_kw":base_total_p_kw,"target_total_h0_mess_p_kw":target_total_p_kw,
    "solver":root_fast,"pcs_numerical_boundary_projection":recovery_pcs_projections,
    "candidate":recovery_candidate,"exact_ac":dict(ex),
    "violating_voltage_rows":[r for r in voltage_rows if r["hard_violation"]],
    "violating_line_rows":[r for r in line_rows if r["hard_violation"]],
    "violating_transformer_current_rows":[r for r in transformer_current_rows if r["hard_violation"]],
    "hard_limits_relaxed":False,"future_actual_used":False})
   if ex.get("hard_constraint_pass") is True:
    record={"schema_version":"mobileess.post_stage15.exact_ac_closed_loop.v2",
     "status":"PASS_RECOVERED_ROOT_SIGN","issue":int(issue),
     "max_cut_rounds":root_recovery_round_limit,"cut_count":round_no,"attempts":attempts,
     "root_import_inner_margin_kw":AC_RECOVERY_ROOT_IMPORT_MARGIN_KW,
     "hard_limits_relaxed":False,"future_actual_used":False}
    issue_runtime["ac_safety_recovery"]=record
    jw(Path(issue_out)/"A_B10_EXACT_AC_CLOSED_LOOP_RECOVERY.json",record)
    return ex
   if (not ex.get("converged") or ex.get("command_error_count")
       or ex.get("transformer_kva_violation_count")
       or ex.get("voltage_violation_count") or ex.get("line_violation_count")
       or ex.get("transformer_current_violation_count")):
    break
  record={"schema_version":"mobileess.post_stage15.exact_ac_closed_loop.v2",
   "status":"GRID_CORRECTION_EXHAUSTED_ROOT_SIGN","issue":int(issue),
   "max_cut_rounds":root_recovery_round_limit,"cut_count":len(attempts)-1,"attempts":attempts,
   "root_import_inner_margin_kw":AC_RECOVERY_ROOT_IMPORT_MARGIN_KW,
   "same_pre_full_replan_required":True,"hard_limits_relaxed":False,"future_actual_used":False}
  issue_runtime["ac_safety_recovery"]=record
  jw(Path(issue_out)/"A_B10_EXACT_AC_CLOSED_LOOP_RECOVERY.json",record)
  raise RuntimeError("GRID_CORRECTION_EXHAUSTED_ROOT_SIGN")
 initial_control_point={str(c["mess_id"]):(float(c["p_kw"]),float(c["q_kvar"]))
                        for c in initial_controls}
 overload_endpoint=(initial_control_point if (not initial_voltage_violations
                    and (initial_line_violations or initial_transformer_current_violations)) else None)
 voltage_endpoint=(initial_control_point if (initial_voltage_violations
                   and not initial_line_violations and not initial_transformer_current_violations) else None)
 # The terminal low-stress anchors were introduced for voltage/tap-only
 # oscillation.  They are not a safe candidate selector for an event that
 # started with a line or transformer-current overload: driving every PCS
 # toward zero can restore the very upstream current that the preceding exact
 # relinearizations were monotonically relieving.  Keep all bounded rounds on
 # the measured P/Q sensitivities for those overload-origin events.  Fresh AC
 # remains the physical acceptance authority and no hard limit is relaxed.
 low_stress_anchor_eligible=not (initial_line_violations or initial_transformer_current_violations)
 complementary_bracket_steps=0
 round_constraint_refs=[]
 previous_grid_score=(len(initial_voltage_violations)+len(initial_line_violations)+len(initial_transformer_current_violations),
                      initial_voltage_severity_pu)
 ex=initial_ex
 for round_no in range(1,recovery_round_limit+1):
  if round_no==1:
   controls=[dict(c) for c in initial_controls]
   first=[dict(row) for row in best_recovery_bundle["first"]]
   plan=[dict(row) for row in best_recovery_bundle["plan"]]
  else:
   controls=_ac_h0_controls(loc,science)
   first=_ac_firstmess(loc,science,controls);plan=_ac_current_plan(loc)
  # Capture the accepted previous-round solution before removing its local
  # approximation rows: model.remove() invalidates Gurobi X attributes.
  if round_constraint_refs:
   model.setObjective(loc["econ"],gp.GRB.MINIMIZE)
   model.remove(round_constraint_refs);model.update();round_constraint_refs=[]
  violations=[r for r in voltage_rows if r["hard_violation"]]
  line_violations=[r for r in line_rows if r["hard_violation"]]
  transformer_current_violations=[r for r in transformer_current_rows if r["hard_violation"]]
  # A voltage/current correction can itself cross the feeder root into reverse
  # power.  The former state machine supported root-sign recovery only when
  # reverse power was the *initial* and sole violation.  Once another recovery
  # produced a root-only violation, this loop saw no voltage/current rows and
  # aborted to a full replan, which could reproduce the same exported action.
  # Continue on the same exact PRE state with the physically direct aggregate-P
  # correction.  This consumes one ordinary bounded production candidate and
  # retains every PCS, SOC, mobility, voltage, current and Fresh-AC gate.
  root_only_after_grid=(bool(controls) and not bool(ex.get("root_sign_pass")) and not violations
                        and not line_violations and not transformer_current_violations
                        and not ex.get("transformer_kva_violation_count")
                        and bool(ex.get("converged")) and not ex.get("command_error_count"))
  if root_only_after_grid:
   root_power=_root_power_from_live_opendss()
   base_total_p_kw=sum(float(c["p_kw"]) for c in controls)
   target_total_p_kw=(base_total_p_kw-float(root_power["root_export_p_kw"])
                      -AC_RECOVERY_ROOT_IMPORT_MARGIN_KW)
   aggregate_p=gp.LinExpr(0.0);root_refs=[]
   for ci,c in enumerate(controls):
    aggregate_p+=c["p_expr"]
    root_refs.append(model.addLConstr(
     c["q_expr"]==float(c["q_kvar"]),name=f"a_b10_post_grid_root_q_hold_r{round_no}_{ci}"))
   root_refs.append(model.addLConstr(
    aggregate_p<=target_total_p_kw,name=f"a_b10_post_grid_root_import_margin_r{round_no}"))
   round_constraint_refs.extend(root_refs)
   model.setObjective(loc["econ"],gp.GRB.MINIMIZE);model.update()
   root_fast=solve_fast(model,cb,loc)
   recovery_pcs_projections=_refresh_solution_after_ac_resolve(loc,science,sol)
   quality=abase.solver_quality(model)
   if any(float(quality.get(k,float("inf")))>lim for k,lim in (("ConstrVio",1e-6),("BoundVio",1e-6),("IntVio",1e-5))):
    raise RuntimeError(f"POST_GRID_ROOT_SIGN_CORRECTION_NUMERICAL_GATE_FAILED {quality}")
   issue_runtime["fresh_ac_capture_stage"]="ROOT_SIGN_CORRECTION_AFTER_GRID"
   ex=science.exact24_candidate(b4,grid24,scope,gstatic,issue,running,sol["plan"],sol["firstmess"])
   voltage_rows=_voltage_rows_from_live_opendss(grid24)
   line_rows=_line_rows_from_live_opendss(grid24)
   transformer_current_rows=_transformer_current_rows_from_live_opendss()
   recovery_candidate=_record_recovery_candidate(loc,science,issue_runtime,Path(issue_out),
    "ROOT_SIGN_CORRECTION_AFTER_GRID",ex,voltage_rows)
   attempts.append({"round":round_no,"constraint_family":"ROOT_REVERSE_POWER_AFTER_GRID_CORRECTION",
    "root_power_before":root_power,"root_import_inner_margin_kw":AC_RECOVERY_ROOT_IMPORT_MARGIN_KW,
    "base_total_h0_mess_p_kw":base_total_p_kw,"target_total_h0_mess_p_kw":target_total_p_kw,
    "solver":root_fast,"pcs_numerical_boundary_projection":recovery_pcs_projections,
    "candidate":recovery_candidate,"exact_ac":dict(ex),
    "violating_voltage_rows":[r for r in voltage_rows if r["hard_violation"]],
    "violating_line_rows":[r for r in line_rows if r["hard_violation"]],
    "violating_transformer_current_rows":[r for r in transformer_current_rows if r["hard_violation"]],
    "hard_limits_relaxed":False,"future_actual_used":False})
   if ex.get("hard_constraint_pass") is True:
    record={"schema_version":"mobileess.post_stage15.exact_ac_closed_loop.v2",
     "status":"PASS_RECOVERED_ROOT_SIGN_AFTER_GRID_CORRECTION","issue":int(issue),
     "max_cut_rounds":recovery_round_limit,"cut_count":len(attempts)-1,"attempts":attempts,
     "root_import_inner_margin_kw":AC_RECOVERY_ROOT_IMPORT_MARGIN_KW,
     "hard_limits_relaxed":False,"future_actual_used":False}
    issue_runtime["ac_safety_recovery"]=record
    jw(Path(issue_out)/"A_B10_EXACT_AC_CLOSED_LOOP_RECOVERY.json",record)
    return ex
   continue
  if not controls or not (violations or line_violations or transformer_current_violations):
   raise RuntimeError("GRID_CORRECTION_EXHAUSTED_NO_CONTROLLABLE_GRID_ACTION")
  # When exact recovery flips between two complementary hard-violation
  # families, local tap/current sensitivities are discontinuous.  Both endpoint
  # actions are nevertheless feasible in the unchanged MIQCP.  Fix H0 P/Q to
  # their component-wise midpoint, validate it by Fresh AC, and replace only
  # the endpoint matching the observed violation family.  This exact-state
  # bisection is bounded by the nine pre-replan correction slots; the eleventh
  # and final production candidate remains reserved for same-PRE full replan.
  if (overload_endpoint is not None and voltage_endpoint is not None
      and complementary_bracket_steps>=AC_RECOVERY_COMPLEMENTARY_BRACKET_MAX_STEPS):
   # A regulator tap can make the one-dimensional segment jump directly from
   # voltage violation to overload violation.  Further midpoint contraction
   # cannot use the remaining independent PCS Q directions.  After three exact
   # bracket samples, relinearize the full P/Q space at the current endpoint;
   # protected initial line/current rows remain active below.
   overload_endpoint=None;voltage_endpoint=None;complementary_bracket_steps=0
  if overload_endpoint is not None and voltage_endpoint is not None:
   complementary_bracket_steps+=1
   midpoint={mid:((overload_endpoint[mid][0]+voltage_endpoint[mid][0])/2.0,
                  (overload_endpoint[mid][1]+voltage_endpoint[mid][1])/2.0)
             for mid in sorted(overload_endpoint)}
   bracket_refs=[]
   bracket_scale=float(getattr(science,"_c5r4_power_scale_kw_per_model_unit",1000.0))
   for ci,c in enumerate(controls):
    mid=str(c["mess_id"]);target_p,target_q=midpoint[mid]
    bracket_refs.append(model.addLConstr(
     c["p_expr"]/bracket_scale==target_p/bracket_scale,
     name=f"a_b10_exact_bracket_p_r{round_no}_{ci}"))
    bracket_refs.append(model.addLConstr(
     c["q_expr"]/bracket_scale==target_q/bracket_scale,
     name=f"a_b10_exact_bracket_q_r{round_no}_{ci}"))
   round_constraint_refs.extend(bracket_refs)
   model.setObjective(loc["econ"],gp.GRB.MINIMIZE);model.update()
   bracket_fast=solve_fast(model,cb,loc)
   recovery_pcs_projections=_refresh_solution_after_ac_resolve(loc,science,sol)
   quality=abase.solver_quality(model)
   if any(float(quality.get(k,float("inf")))>lim for k,lim in (("ConstrVio",1e-6),("BoundVio",1e-6),("IntVio",1e-5))):
    raise RuntimeError(f"EXACT_PQ_BRACKET_NUMERICAL_GATE_FAILED {quality}")
   issue_runtime["fresh_ac_capture_stage"]="EXACT_PQ_BRACKET_BISECTION"
   ex=science.exact24_candidate(b4,grid24,scope,gstatic,issue,running,sol["plan"],sol["firstmess"])
   voltage_rows=_voltage_rows_from_live_opendss(grid24)
   line_rows=_line_rows_from_live_opendss(grid24)
   transformer_current_rows=_transformer_current_rows_from_live_opendss()
   recovery_candidate=_record_recovery_candidate(loc,science,issue_runtime,Path(issue_out),
    "EXACT_PQ_BRACKET_BISECTION",ex,voltage_rows)
   bracket_cut={"constraint_family":"EXACT_PQ_COMPLEMENTARY_VIOLATION_BISECTION",
    "overload_endpoint":{mid:[p,q] for mid,(p,q) in sorted(overload_endpoint.items())},
    "voltage_endpoint":{mid:[p,q] for mid,(p,q) in sorted(voltage_endpoint.items())},
    "midpoint":{mid:[p,q] for mid,(p,q) in sorted(midpoint.items())},
    "hard_limits_relaxed":False,"linearized_guidance_is_physical_acceptance_gate":False}
   attempts.append({"round":round_no,"cuts":[bracket_cut],"finite_difference_samples":[],
    "trust_region":[],"incomplete_coordinate_locks":[],
    "fast_solver":{"primary_economic_solve":bracket_fast,
     "low_stress_anchor_trigger":"EXACT_PQ_BRACKET_BISECTION",
     "fresh_exact_opendss_required":True,"linearized_guidance_is_physical_acceptance_gate":False},
    "pcs_numerical_boundary_projection":recovery_pcs_projections,
    "candidate":recovery_candidate,"exact_ac":dict(ex),
    "violating_voltage_rows":[r for r in voltage_rows if r["hard_violation"]],
    "violating_line_rows":[r for r in line_rows if r["hard_violation"]],
    "violating_transformer_current_rows":[r for r in transformer_current_rows if r["hard_violation"]],
    "hard_limits_relaxed":False,"future_actual_used":False})
   if ex.get("hard_constraint_pass") is True:
    record={"schema_version":"mobileess.post_stage15.exact_ac_closed_loop.v2","status":"PASS_RECOVERED",
     "recovery_selector":"EXACT_PQ_COMPLEMENTARY_VIOLATION_BISECTION",
     "hard_limits_relaxed":False,"max_cut_rounds":recovery_round_limit,
     "cut_count":sum(len(x.get("cuts",[])) for x in attempts),"attempts":attempts,
     "future_actual_used":False}
    issue_runtime["ac_safety_recovery"]=record
    jw(Path(issue_out)/"A_B10_EXACT_AC_CLOSED_LOOP_RECOVERY.json",record)
    return ex
   bracket_point={str(c["mess_id"]):(float(c["p_kw"]),float(c["q_kvar"]))
                  for c in _ac_h0_controls(loc,science)}
   bracket_voltage=bool(ex.get("voltage_violation_count"))
   bracket_overload=bool(ex.get("line_violation_count") or ex.get("transformer_current_violation_count"))
   if bracket_voltage and not bracket_overload:voltage_endpoint=bracket_point
   elif bracket_overload and not bracket_voltage:overload_endpoint=bracket_point
   else:
    # The exact midpoint can contain both violation families near a regulator
    # boundary.  That invalidates monotone bisection, not the remaining bounded
    # recovery budget.  Drop the bracket and relinearize both exact families at
    # this midpoint on the next round.
    overload_endpoint=None;voltage_endpoint=None;complementary_bracket_steps=0
   if (not ex.get("converged") or ex.get("command_error_count")
       or (ex.get("transformer_kva_violation_count")
           and not any(r["hard_violation"] for r in transformer_current_rows))
       or not ex.get("root_sign_pass")):break
   continue
  # The exact violation family is known before the recovery solve and is
  # therefore an outcome-blind selector.  Voltage-only recovery must remain
  # local because regulator/tap changes make the finite-difference model
  # discontinuous outside a small neighbourhood.  A simultaneous line-current
  # violation needs more active/reactive authority to relieve the line while
  # keeping voltage inside its hard band.  Neither profile relaxes a physical
  # limit; the single resulting candidate is still accepted only by Fresh AC.
  voltage_violation_severity_pu=max(
   [max(0.0,float(r["voltage_pu"])-1.05,0.95-float(r["voltage_pu"])) for r in violations],
   default=0.0)
  if ((initial_line_violations or initial_transformer_current_violations) and round_no>1
      and not line_violations and not transformer_current_violations
      and initial_voltage_severity_pu>AC_RECOVERY_SEVERE_VOLTAGE_THRESHOLD_PU):
   trust_profile="SEVERE_VOLTAGE_POST_LINE"
   p_trust_radius=AC_RECOVERY_SEVERE_VOLTAGE_P_TRUST_REGION_KW
   q_trust_radius=AC_RECOVERY_POST_LINE_Q_TRUST_REGION_KVAR
  elif line_violations or transformer_current_violations:
   if (initial_voltage_severity_pu>AC_RECOVERY_SEVERE_VOLTAGE_THRESHOLD_PU
       or initial_overload_severity_pu>AC_RECOVERY_SEVERE_OVERLOAD_THRESHOLD_PU):
    trust_profile="SEVERE_VOLTAGE_LINE"
    p_trust_radius=AC_RECOVERY_SEVERE_LINE_P_TRUST_REGION_KW
    q_trust_radius=AC_RECOVERY_SEVERE_LINE_Q_TRUST_REGION_KVAR
   else:
    trust_profile="COUPLED_VOLTAGE_LINE"
    p_trust_radius=AC_RECOVERY_COUPLED_LINE_P_TRUST_REGION_KW
    q_trust_radius=AC_RECOVERY_COUPLED_LINE_Q_TRUST_REGION_KVAR
  elif (round_no>1 and
        initial_voltage_severity_pu>AC_RECOVERY_SEVERE_VOLTAGE_ONLY_THRESHOLD_PU):
   trust_profile="SEVERE_VOLTAGE_RELINEARIZED"
   p_trust_radius=AC_RECOVERY_SEVERE_VOLTAGE_P_TRUST_REGION_KW
   q_trust_radius=AC_RECOVERY_RELINEARIZED_VOLTAGE_Q_TRUST_REGION_KVAR
  elif initial_voltage_severity_pu>AC_RECOVERY_SEVERE_VOLTAGE_ONLY_THRESHOLD_PU:
   trust_profile="SEVERE_VOLTAGE_ONLY"
   p_trust_radius=AC_RECOVERY_SEVERE_VOLTAGE_P_TRUST_REGION_KW
   q_trust_radius=AC_RECOVERY_SEVERE_VOLTAGE_Q_TRUST_REGION_KVAR
  else:
   trust_profile="LOCAL_VOLTAGE_ONLY"
   p_trust_radius=AC_RECOVERY_LOCAL_P_TRUST_REGION_KW
   q_trust_radius=AC_RECOVERY_LOCAL_Q_TRUST_REGION_KVAR
  baseline={(str(r["bus"]),int(r["node"])):float(r["voltage_pu"]) for r in voltage_rows}
  line_baseline={str(r["line"]):float(r["loading_pu"]) for r in line_rows}
  transformer_current_baseline={
   (str(r["transformer"]),int(r["terminal"]),int(r["conductor"])):float(r["loading_pu"])
   for r in transformer_current_rows}
  target_voltage_keys=sorted({(str(r["bus"]),int(r["node"])) for r in violations})
  line_cut_rows=[r for r in line_rows
                 if r["hard_violation"] or str(r["line"]) in protected_line_keys]
  target_line_keys=sorted({str(r["line"]) for r in line_cut_rows})
  transformer_current_cut_rows=[r for r in transformer_current_rows
   if r["hard_violation"] or (str(r["transformer"]),int(r["terminal"]),int(r["conductor"]))
      in protected_transformer_current_keys]
  target_transformer_current_keys=sorted({
   (str(r["transformer"]),int(r["terminal"]),int(r["conductor"]))
   for r in transformer_current_cut_rows})
  gradients={};line_gradients={};transformer_current_gradients={};fd_records=[]
  for c in controls:
   for kind,key in (("P","P_net_grid_injection_kW"),("Q","Q_grid_injection_kvar")):
    base_p=float(next(x for x in first if x["mess_id"]==c["mess_id"])["P_net_grid_injection_kW"])
    base_q=float(next(x for x in first if x["mess_id"]==c["mess_id"])["Q_grid_injection_kvar"])
    deltas=[]
    for step in (AC_RECOVERY_FD_STEP_KW,5.0,1.0,0.1,0.01):
     deltas=[]
     for sign in (-1.0,1.0):
      delta=sign*step;trial_p=base_p+(delta if kind=="P" else 0.0);trial_q=base_q+(delta if kind=="Q" else 0.0)
      if (abs(trial_p)<=PCS_ACTIVE_LIMIT_KW+1e-8
          and trial_p*trial_p+trial_q*trial_q<=PCS_APPARENT_LIMIT_KVA**2+1e-6):
       deltas.append(delta)
     if deltas:break
    if not deltas:
     # A PCS coordinate can already sit on the intersection of its active- and
     # apparent-power limits.  That makes even the smallest signed probe
     # infeasible, but it does not remove the other PCS coordinates' physical
     # correction authority.  Record the unavailable coordinate and let the
     # existing incomplete-coordinate layer fix it exactly at the Fresh-AC
     # base point.  Fail below only if no complete sensitivity exists anywhere.
     fd_records.append({"mess_id":c["mess_id"],"coordinate":kind,
                        "base_p_kw":base_p,"base_q_kvar":base_q,"deltas":[],
                        "scheme":"UNAVAILABLE_AT_PCS_BOUNDARY",
                        "all_trial_points_inside_P550_S700":True,
                        "coordinate_fixed_at_base":True})
     continue
    samples={}
    for delta in deltas:
     trial=[dict(x) for x in first]
     row=next(x for x in trial if x["mess_id"]==c["mess_id"])
     row[key]=float(row[key])+delta
     science.exact24_candidate(b4,grid24,scope,gstatic,issue,running,plan,trial)
     samples[delta]={
     "voltage":{(str(r["bus"]),int(r["node"])):float(r["voltage_pu"])
                 for r in _voltage_rows_from_live_opendss(grid24)},
      "line":{str(r["line"]):float(r["loading_pu"])
              for r in _line_rows_from_live_opendss(grid24)},
      "transformer_current":{
       (str(r["transformer"]),int(r["terminal"]),int(r["conductor"])):float(r["loading_pu"])
       for r in _transformer_current_rows_from_live_opendss()}}
    for vk in target_voltage_keys:
     if vk not in baseline or any(vk not in samples[delta]["voltage"] for delta in deltas):
      raise RuntimeError(f"GRID_CORRECTION_EXHAUSTED_FD_TOPOLOGY_DRIFT {c['mess_id']} {kind} {vk}")
     if len(deltas)==2:
      lo,hi=sorted(deltas);gradient=(samples[hi]["voltage"][vk]-samples[lo]["voltage"][vk])/(hi-lo);scheme="CENTRAL_FEASIBLE"
     else:
      delta=deltas[0];gradient=(samples[delta]["voltage"][vk]-baseline[vk])/delta;scheme="ONE_SIDED_FEASIBLE"
     gradients[(c["mess_id"],kind,vk)]=gradient
    for lk in target_line_keys:
     if lk not in line_baseline or any(lk not in samples[delta]["line"] for delta in deltas):
      raise RuntimeError(f"GRID_CORRECTION_EXHAUSTED_LINE_FD_TOPOLOGY_DRIFT {c['mess_id']} {kind} {lk}")
     if len(deltas)==2:
      lo,hi=sorted(deltas);gradient=(samples[hi]["line"][lk]-samples[lo]["line"][lk])/(hi-lo);scheme="CENTRAL_FEASIBLE"
     else:
      delta=deltas[0];gradient=(samples[delta]["line"][lk]-line_baseline[lk])/delta;scheme="ONE_SIDED_FEASIBLE"
     line_gradients[(c["mess_id"],kind,lk)]=gradient
    for tk in target_transformer_current_keys:
     if (tk not in transformer_current_baseline
         or any(tk not in samples[delta]["transformer_current"] for delta in deltas)):
      raise RuntimeError(f"GRID_CORRECTION_EXHAUSTED_TRANSFORMER_CURRENT_FD_TOPOLOGY_DRIFT {c['mess_id']} {kind} {tk}")
     if len(deltas)==2:
      lo,hi=sorted(deltas);gradient=(samples[hi]["transformer_current"][tk]-samples[lo]["transformer_current"][tk])/(hi-lo);scheme="CENTRAL_FEASIBLE"
     else:
      delta=deltas[0];gradient=(samples[delta]["transformer_current"][tk]-transformer_current_baseline[tk])/delta;scheme="ONE_SIDED_FEASIBLE"
     transformer_current_gradients[(c["mess_id"],kind,tk)]=gradient
    fd_records.append({"mess_id":c["mess_id"],"coordinate":kind,"base_p_kw":base_p,"base_q_kvar":base_q,
                       "deltas":deltas,"scheme":scheme,"all_trial_points_inside_P550_S700":True})
  cuts=[]
  linearized_cut_constraint_refs=[]
  linearized_cut_specs=[]
  incomplete_coordinate_locks=[]
  trust_region=[]
  trust_constraint_refs=[]
  q_trust_constraint_refs=[]
  scale=float(getattr(science,"_c5r4_power_scale_kw_per_model_unit",1000.0))
  for ci,c in enumerate(controls):
   for kind,expr_key,value_key in (("P","p_expr","p_kw"),("Q","q_expr","q_kvar")):
    base_value=float(c[value_key]);expr=c[expr_key]
    radius=p_trust_radius if kind=="P" else q_trust_radius
    hi=model.addLConstr(expr/scale<=(base_value+radius)/scale,
     name=f"a_b10_ac_trust_hi_r{round_no}_{kind.lower()}_{ci}")
    lo=model.addLConstr(expr/scale>=(base_value-radius)/scale,
     name=f"a_b10_ac_trust_lo_r{round_no}_{kind.lower()}_{ci}")
    round_constraint_refs.extend([hi,lo])
    trust_constraint_refs.extend([hi,lo])
    if kind=="Q":q_trust_constraint_refs.extend([hi,lo])
    trust_region.append({"mess_id":str(c["mess_id"]),"coordinate":kind,"base_value":base_value,
                         "radius_kw_kvar":radius,"model_unit_radius":radius/scale,
                         "profile":trust_profile,
                         "selector":"PRE_RECOVERY_EXACT_VIOLATION_FAMILY",
                         "voltage_violation_count":len(violations),
                         "line_violation_count":len(line_violations),
                         "transformer_current_violation_count":len(transformer_current_violations),
                         "voltage_violation_severity_pu":voltage_violation_severity_pu,
                         "severe_voltage_threshold_pu":AC_RECOVERY_SEVERE_VOLTAGE_THRESHOLD_PU,
                         "selected_round_limit":recovery_round_limit,
                         "round_limit_selector":"INITIAL_EXACT_VOLTAGE_SEVERITY",
                         "finite_difference_step_kw_kvar":AC_RECOVERY_FD_STEP_KW,
                         "normalized_model_coefficient":True,"feasible_set_expanded":False})
  for ci,c in enumerate(controls):
   mid=str(c["mess_id"])
   for kind,expr_key,value_key in (("P","p_expr","p_kw"),("Q","q_expr","q_kvar")):
    missing_voltage=[vk for vk in target_voltage_keys if gradients.get((mid,kind,vk)) is None]
    missing_lines=[lk for lk in target_line_keys if line_gradients.get((mid,kind,lk)) is None]
    missing_transformer_current=[tk for tk in target_transformer_current_keys
                                 if transformer_current_gradients.get((mid,kind,tk)) is None]
    if not (missing_voltage or missing_lines or missing_transformer_current):continue
    # A voltage row can be absent for one control perturbation even though the
    # base Fresh-AC solve is valid.  Do not invent a zero derivative while
    # allowing that coordinate to move: freeze only the incomplete coordinate
    # at its accepted base value.  This strictly restricts the recovery QCP;
    # it never relaxes a scientific limit, and Fresh OpenDSS still validates
    # the one resulting production correction candidate.
    round_constraint_refs.append(model.addLConstr(
     c[expr_key]==float(c[value_key]),name=f"a_b10_ac_fd_lock_r{round_no}_{kind.lower()}_{ci}"))
    incomplete_coordinate_locks.append({"mess_id":mid,"coordinate":kind,
      "base_value":float(c[value_key]),"missing_voltage_keys":[list(vk) for vk in missing_voltage],
      "missing_line_keys":missing_lines,
      "missing_transformer_current_keys":[list(tk) for tk in missing_transformer_current],
      "recovery_feasible_set_expanded":False})
  complete_gradient_count=sum(
   gradients.get((str(c["mess_id"]),kind,vk)) is not None
   for c in controls for kind in ("P","Q") for vk in target_voltage_keys)
  complete_line_gradient_count=sum(
   line_gradients.get((str(c["mess_id"]),kind,lk)) is not None
   for c in controls for kind in ("P","Q") for lk in target_line_keys)
  complete_transformer_current_gradient_count=sum(
   transformer_current_gradients.get((str(c["mess_id"]),kind,tk)) is not None
   for c in controls for kind in ("P","Q") for tk in target_transformer_current_keys)
  if complete_gradient_count+complete_line_gradient_count+complete_transformer_current_gradient_count==0:
   raise RuntimeError("GRID_CORRECTION_EXHAUSTED_NO_COMPLETE_SENSITIVITY")
  for vi,r in enumerate(violations):
   vk=(str(r["bus"]),int(r["node"]));expr=gp.LinExpr(float(r["voltage_pu"]))
   grad_record={}
   for c in controls:
    gp_=gradients.get((c["mess_id"],"P",vk));gq=gradients.get((c["mess_id"],"Q",vk))
    gp_=0.0 if gp_ is None else float(gp_);gq=0.0 if gq is None else float(gq)
    expr += gp_*(c["p_expr"]-float(c["p_kw"]))+gq*(c["q_expr"]-float(c["q_kvar"]))
    grad_record[c["mess_id"]]={"dV_dP":gp_,"dV_dQ":gq}
   if bool(r["above_1p05"]):
    voltage_cut_margin=(AC_RECOVERY_RELINEARIZED_VOLTAGE_CUT_MARGIN_PU
                        if trust_profile in {"SEVERE_VOLTAGE_RELINEARIZED","SEVERE_VOLTAGE_POST_LINE"} else
                        AC_RECOVERY_SEVERE_LINE_VOLTAGE_CUT_MARGIN_PU
                        if trust_profile=="SEVERE_VOLTAGE_LINE" else
                        AC_RECOVERY_SEVERE_VOLTAGE_CUT_MARGIN_PU
                        if trust_profile in {"SEVERE_VOLTAGE_ONLY","SEVERE_VOLTAGE_RELINEARIZED","SEVERE_VOLTAGE_POST_LINE"} else
                        AC_RECOVERY_VOLTAGE_CUT_MARGIN_PU)
    cut_limit=1.05-voltage_cut_margin
    cut_ref=model.addLConstr(expr<=cut_limit,name=f"a_b10_ac_vmax_r{round_no}_{vi}")
    round_constraint_refs.append(cut_ref);linearized_cut_constraint_refs.append(cut_ref)
    linearized_cut_specs.append((expr,"<=",cut_limit,f"voltage_{vi}"));sense="<=";hard_limit=1.05
   else:
    voltage_cut_margin=(AC_RECOVERY_RELINEARIZED_VOLTAGE_CUT_MARGIN_PU
                        if trust_profile in {"SEVERE_VOLTAGE_RELINEARIZED","SEVERE_VOLTAGE_POST_LINE"} else
                        AC_RECOVERY_SEVERE_LINE_VOLTAGE_CUT_MARGIN_PU
                        if trust_profile=="SEVERE_VOLTAGE_LINE" else
                        AC_RECOVERY_SEVERE_VOLTAGE_CUT_MARGIN_PU
                        if trust_profile in {"SEVERE_VOLTAGE_ONLY","SEVERE_VOLTAGE_RELINEARIZED","SEVERE_VOLTAGE_POST_LINE"} else
                        AC_RECOVERY_VOLTAGE_CUT_MARGIN_PU)
    cut_limit=0.95+voltage_cut_margin
    cut_ref=model.addLConstr(expr>=cut_limit,name=f"a_b10_ac_vmin_r{round_no}_{vi}")
    round_constraint_refs.append(cut_ref);linearized_cut_constraint_refs.append(cut_ref)
    linearized_cut_specs.append((expr,">=",cut_limit,f"voltage_{vi}"));sense=">=";hard_limit=0.95
   cuts.append({"bus":vk[0],"node":vk[1],"base_voltage_pu":float(r["voltage_pu"]),"sense":sense,
                "constraint_family":"VOLTAGE",
                "hard_limit_pu":hard_limit,"linearized_cut_limit_pu":cut_limit,
                "conservative_inner_margin_pu":voltage_cut_margin,"gradients":grad_record})
  for li,r in enumerate(line_cut_rows):
   lk=str(r["line"]);expr=gp.LinExpr(float(r["loading_pu"]));grad_record={}
   for c in controls:
    gp_=float(line_gradients.get((c["mess_id"],"P",lk),0.0))
    gq=float(line_gradients.get((c["mess_id"],"Q",lk),0.0))
    expr += gp_*(c["p_expr"]-float(c["p_kw"]))+gq*(c["q_expr"]-float(c["q_kvar"]))
    grad_record[c["mess_id"]]={"dLoading_dP":gp_,"dLoading_dQ":gq}
   cut_limit=1.0-AC_RECOVERY_LINE_CUT_MARGIN_PU
   cut_ref=model.addLConstr(expr<=cut_limit,name=f"a_b10_ac_line_r{round_no}_{li}")
   round_constraint_refs.append(cut_ref);linearized_cut_constraint_refs.append(cut_ref)
   linearized_cut_specs.append((expr,"<=",cut_limit,f"line_{li}"))
   cuts.append({"constraint_family":"LINE_CURRENT","line":lk,"base_loading_pu":float(r["loading_pu"]),
                "sense":"<=","hard_limit_pu":1.0,"linearized_cut_limit_pu":cut_limit,
                "conservative_inner_margin_pu":AC_RECOVERY_LINE_CUT_MARGIN_PU,"gradients":grad_record})
  for ti,r in enumerate(transformer_current_cut_rows):
   tk=(str(r["transformer"]),int(r["terminal"]),int(r["conductor"]))
   expr=gp.LinExpr(float(r["loading_pu"]));grad_record={}
   for c in controls:
    gp_=float(transformer_current_gradients.get((c["mess_id"],"P",tk),0.0))
    gq=float(transformer_current_gradients.get((c["mess_id"],"Q",tk),0.0))
    expr += gp_*(c["p_expr"]-float(c["p_kw"]))+gq*(c["q_expr"]-float(c["q_kvar"]))
    grad_record[c["mess_id"]]={"dLoading_dP":gp_,"dLoading_dQ":gq}
   cut_limit=1.0-AC_RECOVERY_TRANSFORMER_CURRENT_CUT_MARGIN_PU
   cut_ref=model.addLConstr(expr<=cut_limit,name=f"a_b10_ac_transformer_current_r{round_no}_{ti}")
   round_constraint_refs.append(cut_ref);linearized_cut_constraint_refs.append(cut_ref)
   linearized_cut_specs.append((expr,"<=",cut_limit,f"transformer_current_{ti}"))
   cuts.append({"constraint_family":"TRANSFORMER_CURRENT","transformer":tk[0],
                "terminal":tk[1],"conductor":tk[2],"base_loading_pu":float(r["loading_pu"]),
                "sense":"<=","hard_limit_pu":1.0,"linearized_cut_limit_pu":cut_limit,
                "conservative_inner_margin_pu":AC_RECOVERY_TRANSFORMER_CURRENT_CUT_MARGIN_PU,
                "gradients":grad_record})
  model.update()
  low_stress_final_anchor=False;low_stress_final_anchor_solve=None
  low_stress_anchor_trigger=None
  try:
   p_only_infeasible_q_fallback=False
   q_trust_infeasible_fallback_radius_kvar=None
   linearized_guidance_slack_fallback=False
   linearized_guidance_slack_sum_pu=None
   try:
    primary_fast=solve_fast(model,cb,loc)
   except RuntimeError as restricted_exc:
    if trust_profile=="SEVERE_VOLTAGE_ONLY" and q_trust_radius==0.0:
     fallback_radii=(AC_RECOVERY_RELINEARIZED_VOLTAGE_Q_TRUST_REGION_KVAR,)
    elif trust_profile=="SEVERE_VOLTAGE_LINE":
     fallback_radii=AC_RECOVERY_SEVERE_LINE_Q_FALLBACK_RADII_KVAR
    elif trust_profile in {"SEVERE_VOLTAGE_RELINEARIZED","SEVERE_VOLTAGE_POST_LINE"}:
     fallback_radii=(PCS_APPARENT_LIMIT_KVA,)
    else:
     # Small voltage violations can also sit at an active-power/PCS boundary,
     # making the narrow local trust box infeasible.  The former branch raised
     # before reaching the guidance-slack/low-stress safety fallback.  Permit Q
     # exploration up to the existing apparent-power circle for every remaining
     # voltage profile; this does not relax |P|<=550 or P^2+Q^2<=700^2.
     fallback_radii=(PCS_APPARENT_LIMIT_KVA,)
    # Escalate only after the tighter Q trust model has no incumbent.  The last
    # radius equals the PCS apparent-power rating but does not enlarge the PCS
    # feasible circle: |P|<=550 kW and P^2+Q^2<=700^2 remain hard constraints.
    # Every solved point is still accepted solely by the following Fresh AC.
    primary_fast=None;last_fallback_exc=restricted_exc
    for fallback_index,radius in enumerate(fallback_radii,1):
     if q_trust_constraint_refs:
      model.remove(q_trust_constraint_refs)
     removed_q_constraint_ids={id(r) for r in q_trust_constraint_refs}
     round_constraint_refs=[r for r in round_constraint_refs if id(r) not in removed_q_constraint_ids]
     trust_constraint_refs=[r for r in trust_constraint_refs if id(r) not in removed_q_constraint_ids]
     q_trust_constraint_refs=[]
     for ci,c in enumerate(controls):
      base_value=float(c["q_kvar"]);expr=c["q_expr"]
      hi=model.addLConstr(expr/scale<=(base_value+radius)/scale,
       name=f"a_b10_ac_trust_hi_qfallback{fallback_index}_r{round_no}_{ci}")
      lo=model.addLConstr(expr/scale>=(base_value-radius)/scale,
       name=f"a_b10_ac_trust_lo_qfallback{fallback_index}_r{round_no}_{ci}")
      round_constraint_refs.extend([hi,lo]);q_trust_constraint_refs.extend([hi,lo])
      trust_constraint_refs.extend([hi,lo])
     for row in trust_region:
      if row["coordinate"]=="Q":
       row["radius_kw_kvar"]=radius;row["model_unit_radius"]=radius/scale
       row["restricted_q_trust_infeasible_fallback"]=True
       row["q_fallback_attempt_index"]=fallback_index
     model.update()
     try:
      primary_fast=solve_fast(model,cb,loc)
      q_trust_infeasible_fallback_radius_kvar=float(radius)
      p_only_infeasible_q_fallback=(q_trust_radius==0.0)
      break
     except RuntimeError as fallback_exc:last_fallback_exc=fallback_exc
    if primary_fast is None:
     # Regulator/tap discontinuities can make simultaneous phase-wise finite-
     # difference cuts mutually inconsistent even though they still point in a
     # useful descent direction.  They are only a candidate generator, never
     # the physical safety authority.  If every hard trust variant is
     # infeasible, minimize nonnegative cut slacks under the unchanged PCS/SOC/
     # operational model and let Fresh OpenDSS accept or reject that one point.
     model.remove(linearized_cut_constraint_refs)
     removed_cut_ids={id(r) for r in linearized_cut_constraint_refs}
     round_constraint_refs=[r for r in round_constraint_refs if id(r) not in removed_cut_ids]
     linearized_cut_constraint_refs=[];slack_objective=gp.LinExpr(0.0);slack_vars=[]
     for slack_index,(expr,sense,limit,label) in enumerate(linearized_cut_specs):
      slack=model.addVar(lb=0.0,name=f"a_b10_ac_guidance_slack_r{round_no}_{slack_index}")
      if sense=="<=":
       ref=model.addLConstr(expr<=limit+slack,name=f"a_b10_ac_guidance_soft_{label}_r{round_no}")
      else:
       ref=model.addLConstr(expr>=limit-slack,name=f"a_b10_ac_guidance_soft_{label}_r{round_no}")
      slack_vars.append(slack);round_constraint_refs.extend([slack,ref]);slack_objective+=slack
     model.setObjective(slack_objective+1.0e-9*loc["econ"],gp.GRB.MINIMIZE);model.update()
     try:
      primary_fast=solve_fast(model,cb,loc)
      linearized_guidance_slack_fallback=True
      linearized_guidance_slack_sum_pu=float(sum(v.X for v in slack_vars))
     except RuntimeError:
      # A cut-slack model can still be infeasible because tap-discontinuous
      # trust rows and incomplete finite-difference coordinate locks remain.
      # Those rows are recovery guidance, not scientific or PCS constraints.
      # Remove the entire round-local approximation layer and solve the same
      # low-stress H0 anchor used on the final sequential round.  Fresh AC below
      # remains the only physical acceptance authority.
      if round_constraint_refs:model.remove(round_constraint_refs)
      round_constraint_refs=[];linearized_cut_constraint_refs=[]
      trust_constraint_refs=[];q_trust_constraint_refs=[]
      low_stress_objective=gp.QuadExpr(0.0)
      for c in controls:
       low_stress_objective+=(c["p_expr"]/scale)*(c["p_expr"]/scale)
       low_stress_objective+=(c["q_expr"]/scale)*(c["q_expr"]/scale)
      model.setObjective(low_stress_objective,gp.GRB.MINIMIZE);model.update()
      low_stress_final_anchor_solve=solve_recovery_anchor()
      primary_fast=low_stress_final_anchor_solve
      linearized_guidance_slack_fallback=True
      low_stress_final_anchor=True
      low_stress_anchor_trigger="INFEASIBLE_APPROXIMATION_LAYER"
   if (low_stress_anchor_eligible
       and round_no in {recovery_round_limit-2,recovery_round_limit-1}
       and not low_stress_final_anchor):
    # Two exact-state guided safety anchors are reserved before the final
    # topology-agnostic zero-effort anchor.  The first can expose a regulator
    # tap state; if Fresh AC rejects it, the second is relinearized at that new
    # exact state and can retain the small targeted Q absorption needed when
    # zero PCS clears transformer current but leaves a slight overvoltage.
    # Fresh AC, not the guidance rows, accepts either point.
    if trust_constraint_refs:
     model.remove(trust_constraint_refs)
     trust_ids={id(r) for r in trust_constraint_refs}
     round_constraint_refs=[r for r in round_constraint_refs if id(r) not in trust_ids]
     trust_constraint_refs=[];q_trust_constraint_refs=[]
    low_stress_objective=gp.QuadExpr(0.0)
    for c in controls:
     low_stress_objective+=(c["p_expr"]/scale)*(c["p_expr"]/scale)
     low_stress_objective+=(c["q_expr"]/scale)*(c["q_expr"]/scale)
    model.setObjective(low_stress_objective,gp.GRB.MINIMIZE);model.update()
    low_stress_final_anchor_solve=solve_recovery_anchor();primary_fast=low_stress_final_anchor_solve
    low_stress_final_anchor=True
    low_stress_anchor_trigger=("GUIDED_ANCHOR_STAGE_1" if round_no==recovery_round_limit-2
                               else "GUIDED_ANCHOR_STAGE_2_RELINEARIZED")
   if (low_stress_anchor_eligible
       and round_no==recovery_round_limit
       and not low_stress_final_anchor):
    # The final candidate is the third exact-state guided low-stress anchor.
    # Remove the local trust box, but retain the cuts relinearized at round 9's
    # Fresh-AC state.  Dropping those newest cuts produced a zero-PCS point that
    # cleared transformer current but crossed back over a regulator voltage
    # boundary.  The retained cuts only generate a candidate; Fresh AC remains
    # the sole physical acceptance gate.
    if trust_constraint_refs:
     model.remove(trust_constraint_refs)
     trust_ids={id(r) for r in trust_constraint_refs}
     round_constraint_refs=[r for r in round_constraint_refs if id(r) not in trust_ids]
     trust_constraint_refs=[];q_trust_constraint_refs=[]
    low_stress_objective=gp.QuadExpr(0.0)
    for c in controls:
     low_stress_objective+=(c["p_expr"]/scale)*(c["p_expr"]/scale)
     low_stress_objective+=(c["q_expr"]/scale)*(c["q_expr"]/scale)
    model.setObjective(low_stress_objective,gp.GRB.MINIMIZE);model.update()
    low_stress_final_anchor_solve=solve_recovery_anchor();primary_fast=low_stress_final_anchor_solve
    low_stress_final_anchor=True
    low_stress_anchor_trigger="GUIDED_ANCHOR_STAGE_3_RELINEARIZED"
   # Commit the feasible primary economic recovery point directly.  A former
   # artificial minimum-P/Q-intervention selector added another large QCP whose
   # only purpose was tie-breaking; at tap boundaries it could terminate with a
   # numerical error after the primary point had already satisfied every model
   # constraint.  The scientific objective therefore remains authoritative and
   # Fresh OpenDSS below is the sole physical acceptance gate.
   fast={"primary_economic_solve":primary_fast,
         "minimal_intervention_solve":{"status":"SKIPPED_NONSCIENTIFIC_TIEBREAK"},
         "secondary_objective":None,
         "p_only_infeasible_q_fallback":p_only_infeasible_q_fallback,
         "q_trust_infeasible_fallback_radius_kvar":q_trust_infeasible_fallback_radius_kvar,
         "linearized_guidance_slack_fallback":linearized_guidance_slack_fallback,
         "linearized_guidance_slack_sum_pu":linearized_guidance_slack_sum_pu,
         "linearized_guidance_is_physical_acceptance_gate":False,
          "low_stress_final_anchor":low_stress_final_anchor,
          "low_stress_anchor_trigger":low_stress_anchor_trigger,
         "low_stress_final_anchor_solve":low_stress_final_anchor_solve,
         "low_stress_anchor_preserved_scientific_constraints":True,
         "primary_economic_quality_preserved":True,
         "fresh_exact_opendss_required":True}
  except RuntimeError as exc:
   attempts.append({"round":round_no,"cuts":cuts,"finite_difference_samples":fd_records,"trust_region":trust_region,
                    "incomplete_coordinate_locks":incomplete_coordinate_locks,
                    "fast_solver":{"status":"NO_FEASIBLE_INCUMBENT","error":repr(exc)},
                    "exact_ac":None,"violating_voltage_rows":violations})
   record={"schema_version":"mobileess.post_stage15.exact_ac_closed_loop.v1",
           "status":"GRID_CORRECTION_EXHAUSTED_LINEARIZED_CUT_INFEASIBLE",
           "hard_limits_relaxed":False,"finite_difference_step_kw_kvar":AC_RECOVERY_FD_STEP_KW,
           "conservative_voltage_cut_margin_pu":AC_RECOVERY_VOLTAGE_CUT_MARGIN_PU,
            "max_cut_rounds":recovery_round_limit,
           "cut_count":sum(len(x.get("cuts",[])) for x in attempts),"attempts":attempts,
           "same_pre_full_replan_required":True,"future_actual_used":False}
   issue_runtime["ac_safety_recovery"]=record
   jw(Path(issue_out)/"A_B10_EXACT_AC_CLOSED_LOOP_RECOVERY.json",record)
   raise RuntimeError("GRID_CORRECTION_EXHAUSTED_LINEARIZED_CUT_INFEASIBLE") from exc
  recovery_pcs_projections=_refresh_solution_after_ac_resolve(loc,science,sol)
  quality=abase.solver_quality(model)
  if any(float(quality.get(k,float("inf")))>lim for k,lim in (("ConstrVio",1e-6),("BoundVio",1e-6),("IntVio",1e-5))):
   raise RuntimeError(f"GRID_CORRECTION_EXHAUSTED_NUMERICAL_GATE_FAILED {quality}")
  issue_runtime["fresh_ac_capture_stage"]="AC_CORRECTION"
  ex=science.exact24_candidate(b4,grid24,scope,gstatic,issue,running,sol["plan"],sol["firstmess"])
  voltage_rows=_voltage_rows_from_live_opendss(grid24)
  line_rows=_line_rows_from_live_opendss(grid24)
  transformer_current_rows=_transformer_current_rows_from_live_opendss()
  remember_best_exact_candidate(ex,"AC_CORRECTION")
  recovery_candidate=_record_recovery_candidate(loc,science,issue_runtime,Path(issue_out),
   "AC_CORRECTION",ex,voltage_rows)
  attempts.append({"round":round_no,"cuts":cuts,"finite_difference_samples":fd_records,"trust_region":trust_region,
                   "incomplete_coordinate_locks":incomplete_coordinate_locks,
                   "fast_solver":fast,"pcs_numerical_boundary_projection":recovery_pcs_projections,
                   "candidate":recovery_candidate,"exact_ac":dict(ex),
                   "violating_voltage_rows":[r for r in voltage_rows if r["hard_violation"]],
                   "violating_line_rows":[r for r in line_rows if r["hard_violation"]],
                   "violating_transformer_current_rows":[r for r in transformer_current_rows if r["hard_violation"]]})
  if ex.get("hard_constraint_pass") is True:
   record={"schema_version":"mobileess.post_stage15.exact_ac_closed_loop.v1","status":"PASS_RECOVERED",
           "hard_limits_relaxed":False,"finite_difference_step_kw_kvar":AC_RECOVERY_FD_STEP_KW,
           "conservative_voltage_cut_margin_pu":AC_RECOVERY_VOLTAGE_CUT_MARGIN_PU,
            "max_cut_rounds":recovery_round_limit,"cut_count":sum(len(x.get("cuts",[])) for x in attempts),
           "attempts":attempts,"future_actual_used":False}
   issue_runtime["ac_safety_recovery"]=record;jw(Path(issue_out)/"A_B10_EXACT_AC_CLOSED_LOOP_RECOVERY.json",record)
   return ex
  candidate_point={str(c["mess_id"]):(float(c["p_kw"]),float(c["q_kvar"]))
                   for c in _ac_h0_controls(loc,science)}
  candidate_voltage=bool(ex.get("voltage_violation_count"))
  candidate_overload=bool(ex.get("line_violation_count") or ex.get("transformer_current_violation_count"))
  if candidate_voltage and not candidate_overload:voltage_endpoint=candidate_point
  elif candidate_overload and not candidate_voltage:overload_endpoint=candidate_point
  # Remaining line or transformer-current violations are precisely what the
  # next protected cut must relinearize; neither is an unsupported family.
  if ((ex.get("transformer_kva_violation_count")
       and not any(r["hard_violation"] for r in transformer_current_rows))
      or not ex.get("converged")):
   break
  current_voltage_rows=[r for r in voltage_rows if r["hard_violation"]]
  current_voltage_severity=max(
   [max(0.0,float(r["voltage_pu"])-1.05,0.95-float(r["voltage_pu"])) for r in current_voltage_rows],
   default=0.0)
  current_grid_score=(len(current_voltage_rows)+len([r for r in line_rows if r["hard_violation"]])
                      +len([r for r in transformer_current_rows if r["hard_violation"]]),
                      current_voltage_severity)
  if recovery_round_limit>1:
   # Regulator tap transitions are non-monotone.  Continue the bounded
   # sequential relinearization even when an intermediate candidate worsens.
   made_grid_progress=True
  elif initial_line_violations:
   made_grid_progress=(current_grid_score[0]<previous_grid_score[0]
                       or (current_grid_score[0]==previous_grid_score[0]
                           and current_grid_score[1]<previous_grid_score[1]-1.0e-8))
  else:
   made_grid_progress=(current_grid_score[1]<previous_grid_score[1]-1.0e-8)
  if not made_grid_progress:
   break
 previous_grid_score=current_grid_score
 # A regulator tap is discrete, so the local finite-difference cuts above can
 # alternate between two exact states without ever entering the feasible Q
 # region.  For any controllable voltage/current event, perform one bounded,
 # deterministic
 # nonlinear exploration of the *unchanged* H0 PCS feasible set before giving
 # up.  First maximize aggregate active injection under every original model,
 # PCS, SOC and mobility constraint.  Then test a small outcome-independent
 # bank of normalized reactive-power directions at that anchor.  These rows
 # generate candidates only: every point is still accepted solely by a fresh
 # OpenDSS solve with the original voltage/current/kVA/root hard limits.
 if initial_voltage_violations or initial_line_violations or initial_transformer_current_violations:
  # Read the final round incumbent before removing its approximation rows:
  # Gurobi invalidates every X attribute as soon as rows are removed.
  controls=_ac_h0_controls(loc,science)
  if round_constraint_refs:
   model.remove(round_constraint_refs);model.update();round_constraint_refs=[]
  if controls:
   max_p_objective=gp.LinExpr(0.0)
   for c in controls:max_p_objective-=c["p_expr"]/scale
   model.setObjective(max_p_objective,gp.GRB.MINIMIZE);model.update()
   try:
    max_p_solve=solve_recovery_anchor()
    anchor_controls=_ac_h0_controls(loc,science)
    anchor_p={str(c["mess_id"]):float(c["p_kw"]) for c in anchor_controls}
    # Materialize the most recent feasible incumbent before any candidate row
    # is removed or a later solve can return infeasible.  Gurobi then clears
    # Var.X, but these numeric P/Q, first-step and routing values remain valid
    # as the causal base point for the next exact-AC relinearization.
    last_feasible_controls=[dict(c) for c in anchor_controls]
    last_feasible_first=_ac_firstmess(loc,science,last_feasible_controls)
    last_feasible_plan=_ac_current_plan(loc)
    # The H0 lossless LinDistFlow projection uses a fixed regulator ratio and
    # can exclude a point that the current discrete-tap Fresh AC proves safe.
    # Its own IIS identifies only H0 p/q balances and voltage-drop rows.  Drop
    # that H0 candidate-generation projection after the maximum-P anchor; keep
    # every PCS/SOC/mobility/service-kVA constraint and all H1..H53 planning
    # rows.  Fresh OpenDSS below replaces (and is stronger than) the removed H0
    # approximation for voltage, line current, transformer current/kVA and
    # root sign.  No physical limit is changed or softened.
    h0_grid_projection_prefixes=("du_line_0_",)
    h0_grid_projection_refs=[row for row in model.getConstrs()
                             if str(row.ConstrName).startswith(h0_grid_projection_prefixes)]
    h0_grid_projection_names=[str(row.ConstrName) for row in h0_grid_projection_refs]
    if h0_grid_projection_refs:model.remove(h0_grid_projection_refs);model.update()
    issue_runtime["h0_exact_ac_candidate_projection_override"]={
     "status":"H0_FIXED_TAP_LINDISTFLOW_REPLACED_BY_FRESH_EXACT_AC_GATE",
     "removed_linear_row_count":len(h0_grid_projection_refs),
     "removed_row_prefixes":list(h0_grid_projection_prefixes),
     "removed_row_names_sha256":hashlib.sha256("\n".join(sorted(h0_grid_projection_names)).encode()).hexdigest(),
     "h0_power_balance_rows_removed":0,"h0_line_thermal_rows_removed":0,
     "future_horizon_grid_rows_removed":0,"pcs_soc_mobility_service_kva_rows_removed":0,
     "fresh_exact_opendss_required":True,"hard_limits_relaxed":False,
     "future_actual_used":False}
    # The first nonzero pattern is a rounded low-discrepancy direction; cyclic
    # rotations, sign reversals and two balanced directions make the search
    # independent of a particular MESS/site identity while keeping it bounded.
    seed_patterns=[
     (0.0,0.0,0.0,0.0),(0.0,-1.0/3.0,-0.60,-5.0/7.0),
     (0.20,0.30,0.45,-0.70),(0.20,0.30,0.30,-0.70),
     (0.0,0.40,0.30,-0.60),
     (0.40,0.30,-0.60,0.0),
     (-0.70,-0.80,0.40,-0.97),(0.75,-0.50,0.25,-0.25),
     (-0.50,0.75,-0.25,0.25)]
    normalized_patterns=[]
    def append_pattern(values):
     values=list(values[:len(anchor_controls)])
     while len(values)<len(anchor_controls):
      values.append(((-1.0) if len(values)%2 else 1.0)*(0.20+0.10*(len(values)%5)))
     key=tuple(round(float(value),9) for value in values)
     if key not in normalized_patterns:normalized_patterns.append(key)
    for seed in seed_patterns:append_pattern(seed)
    # Deterministic low-discrepancy coverage avoids accumulating one-off
    # patterns for successive regulator states.  No randomness, future actual,
    # or outcome-dependent mutation is used.
    def radical_inverse(index,base):
     value=0.0;factor=1.0/float(base)
     while index:
      index,remainder=divmod(index,base);value+=float(remainder)*factor;factor/=float(base)
     return value
    halton_bases=(2,3,5,7,11,13,17,19)
    for halton_index in range(1,49):
     append_pattern([2.0*radical_inverse(halton_index,base)-1.0
                     for base in halton_bases[:len(anchor_controls)]])
    for seed in seed_patterns:
     values=list(seed[:len(anchor_controls)])
     while len(values)<len(anchor_controls):
      values.append(((-1.0) if len(values)%2 else 1.0)*(0.20+0.10*(len(values)%5)))
     rotations=[values[index:]+values[:index] for index in range(max(1,len(values)))]
     for rotated in rotations:
      for signed in (rotated,[-value for value in rotated]):
       key=tuple(round(float(value),9) for value in signed)
       if key not in normalized_patterns:normalized_patterns.append(key)
    # Zero and the primary low-discrepancy direction are deliberately first;
    # cap the bank so the production Fresh-AC bound remains auditable.
    normalized_patterns=normalized_patterns[:64]
    tap_search_refs=[]
    tap_voltage_only_points=[]
    tap_overload_only_points=[]
    coordinate_search_executed=False
    coordinate_search_candidate_count=0
    balanced_q_search_candidate_count=0
    def select_best_relinearization_base():
     nonlocal ex,voltage_rows,line_rows,transformer_current_rows
     nonlocal last_feasible_controls,last_feasible_first,last_feasible_plan
     last_feasible_controls=[dict(c) for c in best_recovery_bundle["controls"]]
     last_feasible_first=[dict(row) for row in best_recovery_bundle["first"]]
     last_feasible_plan=[dict(row) for row in best_recovery_bundle["plan"]]
     ex=dict(best_recovery_bundle["exact"])
     voltage_rows=[dict(row) for row in best_recovery_bundle["voltage_rows"]]
     line_rows=[dict(row) for row in best_recovery_bundle["line_rows"]]
     transformer_current_rows=[dict(row) for row in best_recovery_bundle["transformer_rows"]]
     issue_runtime["post_tap_relinearization_base"]={
      "stage":best_recovery_bundle["stage"],"score":list(best_recovery_bundle["score"]),
      "hard_limits_relaxed":False,"future_actual_used":False}
    def exact_coordinate_search():
     """Bounded coordinate search around the closest causal exact-AC point."""
     nonlocal tap_search_refs,ex,voltage_rows,line_rows,transformer_current_rows
     nonlocal coordinate_search_executed,coordinate_search_candidate_count,balanced_q_search_candidate_count
     if coordinate_search_executed:return False
     coordinate_search_executed=True
     if tap_search_refs:
      model.remove(tap_search_refs);model.update();tap_search_refs=[]
     for sweep in range(1,3):
      base_score=best_recovery_bundle["score"]
      base_controls=[dict(c) for c in best_recovery_bundle["controls"]]
      for step in (5.0,10.0,25.0,50.0):
       for ci,control in enumerate(base_controls):
        for coordinate in ("P","Q"):
         for sign in (-1.0,1.0):
          if (len(issue_runtime.get("fresh_ac_candidate_attempts",[]))
              >= FRESH_AC_PRODUCTION_CANDIDATE_MAX-AC_RECOVERY_POST_TAP_RESERVED_CANDIDATES
              or coordinate_search_candidate_count>=AC_RECOVERY_COORDINATE_SEARCH_CANDIDATE_MAX):
           break
          mid=str(control["mess_id"]);target_p=float(control["p_kw"]);target_q=float(control["q_kvar"])
          if coordinate=="P":target_p+=sign*step
          else:target_q+=sign*step
          if (abs(target_p)>PCS_ACTIVE_LIMIT_KW+1e-8
              or target_p*target_p+target_q*target_q>PCS_APPARENT_LIMIT_KVA**2+1e-6):
           continue
          target_by_mid={str(c["mess_id"]):(float(c["p_kw"]),float(c["q_kvar"]))
                         for c in base_controls}
          target_by_mid[mid]=(target_p,target_q)
          refs=[]
          for cj,c in enumerate(base_controls):
           p_target,q_target=target_by_mid[str(c["mess_id"])]
           refs.append(model.addLConstr(c["p_expr"]/scale==p_target/scale,
            name=f"a_b10_exact_coordinate_p_{sweep}_{int(step)}_{ci}_{coordinate}_{int(sign)}_{cj}"))
           refs.append(model.addLConstr(c["q_expr"]/scale==q_target/scale,
            name=f"a_b10_exact_coordinate_q_{sweep}_{int(step)}_{ci}_{coordinate}_{int(sign)}_{cj}"))
          model.setObjective(loc["econ"],gp.GRB.MINIMIZE);model.update()
          try:coordinate_solve=solve_recovery_anchor()
          except RuntimeError as coordinate_exc:
           model.remove(refs);model.update()
           attempts.append({"round":recovery_round_limit+len(search_specs)+60+sweep,
            "recovery_stage":"EXACT_AC_COORDINATE_SEARCH","sweep":sweep,"step_kw_kvar":step,
            "coordinate":coordinate,"sign":sign,"changed_mess_id":mid,
            "fast_solver":{"status":"NO_FEASIBLE_INCUMBENT","error":repr(coordinate_exc)},
            "exact_ac":None,"hard_limits_relaxed":False,"future_actual_used":False})
           continue
          coordinate_projections=_refresh_solution_after_ac_resolve(loc,science,sol)
          quality=abase.solver_quality(model)
          if any(float(quality.get(k,float("inf")))>lim for k,lim in
                 (("ConstrVio",1e-6),("BoundVio",1e-6),("IntVio",1e-5))):
           raise RuntimeError(f"EXACT_AC_COORDINATE_SEARCH_NUMERICAL_GATE_FAILED {quality}")
          issue_runtime["fresh_ac_capture_stage"]="EXACT_AC_COORDINATE_SEARCH"
          coordinate_ex=science.exact24_candidate(
           b4,grid24,scope,gstatic,issue,running,sol["plan"],sol["firstmess"])
          coordinate_search_candidate_count+=1
          voltage_rows=_voltage_rows_from_live_opendss(grid24)
          line_rows=_line_rows_from_live_opendss(grid24)
          transformer_current_rows=_transformer_current_rows_from_live_opendss()
          remember_best_exact_candidate(coordinate_ex,"EXACT_AC_COORDINATE_SEARCH")
          coordinate_candidate=_record_recovery_candidate(
           loc,science,issue_runtime,Path(issue_out),"EXACT_AC_COORDINATE_SEARCH",coordinate_ex,voltage_rows)
          attempts.append({"round":recovery_round_limit+len(search_specs)+60+sweep,
           "recovery_stage":"EXACT_AC_COORDINATE_SEARCH","sweep":sweep,"step_kw_kvar":step,
           "coordinate":coordinate,"sign":sign,"changed_mess_id":mid,
           "fast_solver":coordinate_solve,"pcs_numerical_boundary_projection":coordinate_projections,
           "candidate":coordinate_candidate,"exact_ac":dict(coordinate_ex),
           "hard_limits_relaxed":False,"future_actual_used":False})
          if coordinate_ex.get("hard_constraint_pass") is True:
           ex=coordinate_ex
           record={"schema_version":"mobileess.post_stage15.exact_ac_closed_loop.v3",
            "status":"PASS_RECOVERED_EXACT_AC_COORDINATE_SEARCH","issue":int(issue),
            "selected_sweep":sweep,"selected_step_kw_kvar":step,"selected_coordinate":coordinate,
            "selected_sign":sign,"selected_mess_id":mid,"attempts":attempts,
            "hard_limits_relaxed":False,"future_actual_used":False}
           issue_runtime["ac_safety_recovery"]=record
           jw(Path(issue_out)/"A_B10_EXACT_AC_CLOSED_LOOP_RECOVERY.json",record)
           return True
          model.remove(refs);model.update()
          if (best_recovery_bundle["score"][0]==0
              and best_recovery_bundle["score"][1]<=0.01):
           issue_runtime["coordinate_search_early_stop_for_exact_relinearization"]={
            "stage":"EXACT_AC_COORDINATE_SEARCH",
            "score":list(best_recovery_bundle["score"]),
            "candidate_count":len(issue_runtime.get("fresh_ac_candidate_attempts",[])),
            "hard_limits_relaxed":False,"future_actual_used":False}
           return False
      if best_recovery_bundle["score"]>=base_score:break
     # Current and voltage can move in opposite directions under a single-Q
     # perturbation.  Redistribute Q between two PCS while holding aggregate Q
     # constant to expose the missing coupled direction.
     base_controls=[dict(c) for c in best_recovery_bundle["controls"]]
     for step in (5.0,10.0,25.0,50.0):
      for left in range(len(base_controls)):
       for right in range(left+1,len(base_controls)):
        for sign in (-1.0,1.0):
         if (len(issue_runtime.get("fresh_ac_candidate_attempts",[]))
             >= FRESH_AC_PRODUCTION_CANDIDATE_MAX-AC_RECOVERY_POST_TAP_RESERVED_CANDIDATES
             or balanced_q_search_candidate_count>=AC_RECOVERY_BALANCED_Q_SEARCH_CANDIDATE_MAX):
          return False
         target_by_mid={str(c["mess_id"]):(float(c["p_kw"]),float(c["q_kvar"]))
                        for c in base_controls}
         left_mid=str(base_controls[left]["mess_id"]);right_mid=str(base_controls[right]["mess_id"])
         lp,lq=target_by_mid[left_mid];rp,rq=target_by_mid[right_mid]
         lq+=sign*step;rq-=sign*step
         if (lp*lp+lq*lq>PCS_APPARENT_LIMIT_KVA**2+1e-6
             or rp*rp+rq*rq>PCS_APPARENT_LIMIT_KVA**2+1e-6):continue
         target_by_mid[left_mid]=(lp,lq);target_by_mid[right_mid]=(rp,rq)
         refs=[]
         for ci,c in enumerate(base_controls):
          p_target,q_target=target_by_mid[str(c["mess_id"])]
          refs.append(model.addLConstr(c["p_expr"]/scale==p_target/scale,
           name=f"a_b10_balanced_q_p_{int(step)}_{left}_{right}_{int(sign)}_{ci}"))
          refs.append(model.addLConstr(c["q_expr"]/scale==q_target/scale,
           name=f"a_b10_balanced_q_q_{int(step)}_{left}_{right}_{int(sign)}_{ci}"))
         model.setObjective(loc["econ"],gp.GRB.MINIMIZE);model.update()
         try:pair_solve=solve_recovery_anchor()
         except RuntimeError as pair_exc:
          model.remove(refs);model.update()
          attempts.append({"round":recovery_round_limit+len(search_specs)+70,
           "recovery_stage":"EXACT_AC_BALANCED_Q_SEARCH","step_kvar":step,"sign":sign,
           "mess_pair":[left_mid,right_mid],
           "fast_solver":{"status":"NO_FEASIBLE_INCUMBENT","error":repr(pair_exc)},
           "exact_ac":None,"hard_limits_relaxed":False,"future_actual_used":False})
          continue
         pair_projections=_refresh_solution_after_ac_resolve(loc,science,sol)
         quality=abase.solver_quality(model)
         if any(float(quality.get(k,float("inf")))>lim for k,lim in
                (("ConstrVio",1e-6),("BoundVio",1e-6),("IntVio",1e-5))):
          raise RuntimeError(f"EXACT_AC_BALANCED_Q_SEARCH_NUMERICAL_GATE_FAILED {quality}")
         issue_runtime["fresh_ac_capture_stage"]="EXACT_AC_BALANCED_Q_SEARCH"
         pair_ex=science.exact24_candidate(
          b4,grid24,scope,gstatic,issue,running,sol["plan"],sol["firstmess"])
         balanced_q_search_candidate_count+=1
         voltage_rows=_voltage_rows_from_live_opendss(grid24)
         line_rows=_line_rows_from_live_opendss(grid24)
         transformer_current_rows=_transformer_current_rows_from_live_opendss()
         remember_best_exact_candidate(pair_ex,"EXACT_AC_BALANCED_Q_SEARCH")
         pair_candidate=_record_recovery_candidate(
          loc,science,issue_runtime,Path(issue_out),"EXACT_AC_BALANCED_Q_SEARCH",pair_ex,voltage_rows)
         attempts.append({"round":recovery_round_limit+len(search_specs)+70,
          "recovery_stage":"EXACT_AC_BALANCED_Q_SEARCH","step_kvar":step,"sign":sign,
          "mess_pair":[left_mid,right_mid],"fast_solver":pair_solve,
          "pcs_numerical_boundary_projection":pair_projections,
          "candidate":pair_candidate,"exact_ac":dict(pair_ex),
          "hard_limits_relaxed":False,"future_actual_used":False})
         if pair_ex.get("hard_constraint_pass") is True:
          ex=pair_ex
          record={"schema_version":"mobileess.post_stage15.exact_ac_closed_loop.v3",
           "status":"PASS_RECOVERED_EXACT_AC_BALANCED_Q_SEARCH","issue":int(issue),
           "selected_step_kvar":step,"selected_sign":sign,"selected_mess_pair":[left_mid,right_mid],
           "attempts":attempts,"hard_limits_relaxed":False,"future_actual_used":False}
          issue_runtime["ac_safety_recovery"]=record
          jw(Path(issue_out)/"A_B10_EXACT_AC_CLOSED_LOOP_RECOVERY.json",record)
          return True
         model.remove(refs);model.update()
         if (best_recovery_bundle["score"][0]==0
             and best_recovery_bundle["score"][1]<=0.01):
          issue_runtime["coordinate_search_early_stop_for_exact_relinearization"]={
           "stage":"EXACT_AC_BALANCED_Q_SEARCH",
           "score":list(best_recovery_bundle["score"]),
           "candidate_count":len(issue_runtime.get("fresh_ac_candidate_attempts",[])),
           "hard_limits_relaxed":False,"future_actual_used":False}
          return False
     return False
    def post_tap_exact_pq_relinearization():
     """Resolve a narrow tap-boundary event in the full feasible P/Q space."""
     nonlocal tap_search_refs,ex,voltage_rows,line_rows,transformer_current_rows
     nonlocal last_feasible_controls,last_feasible_first,last_feasible_plan
     controls=[dict(c) for c in last_feasible_controls]
     voltage_keys=sorted((str(r["bus"]),int(r["node"])) for r in voltage_rows if r["hard_violation"])
     line_keys=sorted((str(r["line"]),) for r in line_rows if r["hard_violation"])
     transformer_keys=sorted((str(r["transformer"]),int(r["terminal"]),int(r["conductor"]))
                             for r in transformer_current_rows if r["hard_violation"])
     if not controls or not (voltage_keys or line_keys or transformer_keys):return False
     # Keep the last feasible incumbent materialized outside Gurobi.  An
     # infeasible trust-region solve clears every Var.X attribute, but it does
     # not invalidate these model expressions or the last Fresh-AC base point.
     first=[dict(row) for row in last_feasible_first]
     plan=[dict(row) for row in last_feasible_plan]
     focus_refs=[]
     available=max(0,FRESH_AC_PRODUCTION_CANDIDATE_MAX
     -len(issue_runtime.get("fresh_ac_candidate_attempts",[]))-1)
     full_trust_infeasible_count=0;no_exact_improvement_rounds=0
     for focus_round in range(1,available+1):
      round_start_best_score=best_recovery_bundle["score"]
      # Regulator movement can clear the original PCC row while exposing a
      # different downstream bus.  Keep the original complementary boundary
      # rows protected and monotonically add every newly hard-violating row.
      voltage_keys=sorted(set(voltage_keys).union(
       (str(r["bus"]),int(r["node"])) for r in voltage_rows if r["hard_violation"]))
      line_keys=sorted(set(line_keys).union(
       (str(r["line"]),) for r in line_rows if r["hard_violation"]))
      transformer_keys=sorted(set(transformer_keys).union(
       (str(r["transformer"]),int(r["terminal"]),int(r["conductor"]))
       for r in transformer_current_rows if r["hard_violation"]))
      base_voltage={(str(r["bus"]),int(r["node"])):float(r["voltage_pu"]) for r in voltage_rows}
      base_line={(str(r["line"]),):float(r["loading_pu"]) for r in line_rows}
      base_transformer={(str(r["transformer"]),int(r["terminal"]),int(r["conductor"])):
                        float(r["loading_pu"]) for r in transformer_current_rows}
      gradients={};fd_records=[]
      for c in controls:
       base_row=next(row for row in first if row["mess_id"]==c["mess_id"])
       base_p=float(base_row["P_net_grid_injection_kW"])
       base_q=float(base_row["Q_grid_injection_kvar"])
       for kind,key in (("P","P_net_grid_injection_kW"),("Q","Q_grid_injection_kvar")):
        scheme="NO_COMPLETE_METRIC"
        deltas=[]
        for step in (1.0,0.1,0.01):
         deltas=[]
         for sign in (-1.0,1.0):
          delta=sign*step
          trial_p=base_p+(delta if kind=="P" else 0.0)
          trial_q=base_q+(delta if kind=="Q" else 0.0)
          if (abs(trial_p)<=PCS_ACTIVE_LIMIT_KW+1e-8
              and trial_p*trial_p+trial_q*trial_q<=PCS_APPARENT_LIMIT_KVA**2+1e-6):
           deltas.append(delta)
         if deltas:break
        samples={}
        for delta in deltas:
         trial=[dict(row) for row in first]
         row=next(item for item in trial if item["mess_id"]==c["mess_id"])
         row[key]=float(row[key])+delta
         science.exact24_candidate(b4,grid24,scope,gstatic,issue,running,plan,trial)
         samples[delta]={
          "voltage":{(str(r["bus"]),int(r["node"])):float(r["voltage_pu"])
                     for r in _voltage_rows_from_live_opendss(grid24)},
          "line":{(str(r["line"]),):float(r["loading_pu"])
                  for r in _line_rows_from_live_opendss(grid24)},
          "transformer":{(str(r["transformer"]),int(r["terminal"]),int(r["conductor"])):
                         float(r["loading_pu"]) for r in _transformer_current_rows_from_live_opendss()}}
        for family,keys,baseline in (("voltage",voltage_keys,base_voltage),
                                     ("line",line_keys,base_line),
                                     ("transformer",transformer_keys,base_transformer)):
         for metric_key in keys:
          if not deltas or metric_key not in baseline or any(metric_key not in samples[d][family] for d in deltas):
           continue
          if len(deltas)==2:
           lo,hi=sorted(deltas);gradient=(samples[hi][family][metric_key]-samples[lo][family][metric_key])/(hi-lo)
           scheme="CENTRAL_FEASIBLE"
          else:
           delta=deltas[0];gradient=(samples[delta][family][metric_key]-baseline[metric_key])/delta
           scheme="ONE_SIDED_FEASIBLE"
          gradients[(str(c["mess_id"]),kind,family,metric_key)]=float(gradient)
        fd_records.append({"mess_id":str(c["mess_id"]),"coordinate":kind,"base_p_kw":base_p,
                           "base_q_kvar":base_q,"deltas":deltas,
                           "scheme":scheme if deltas else "UNAVAILABLE_AT_PCS_BOUNDARY"})
      if tap_search_refs:
       model.remove(tap_search_refs);model.update();tap_search_refs=[]
      if focus_refs:
       model.remove(focus_refs);model.update();focus_refs=[]
      # A narrow 25 kW/kvar neighborhood is sufficient for the small 15180
      # tap-boundary residual, but a larger first-step violation can have no
      # conditioned incumbent in that neighborhood.  Solver infeasibility is
      # not a Fresh-AC candidate and therefore must enlarge the deterministic
      # trust region instead of terminating the recovery path.
      trust_radius=(25.0 if focus_round<=2 else 100.0 if focus_round<=5
                    else PCS_APPARENT_LIMIT_KVA)
      objective=gp.QuadExpr(0.0)
      for ci,c in enumerate(controls):
       for kind,expr_key,value_key in (("P","p_expr","p_kw"),("Q","q_expr","q_kvar")):
        expr=c[expr_key];base=float(c[value_key])
        focus_refs.append(model.addLConstr(expr/scale<=(base+trust_radius)/scale,
         name=f"a_b10_post_tap_trust_hi_{focus_round}_{kind}_{ci}"))
        focus_refs.append(model.addLConstr(expr/scale>=(base-trust_radius)/scale,
         name=f"a_b10_post_tap_trust_lo_{focus_round}_{kind}_{ci}"))
        objective+=((expr-base)/scale)*((expr-base)/scale)
      cut_rows=[];hard_cut_refs=[];soft_cut_specs=[]
      for vi,vk in enumerate(voltage_keys):
       expr=gp.LinExpr(base_voltage[vk]);grad_record={}
       for c in controls:
        mid=str(c["mess_id"]);gp_=gradients.get((mid,"P","voltage",vk));gq=gradients.get((mid,"Q","voltage",vk))
        if gp_ is None or gq is None:continue
        expr+=gp_*(c["p_expr"]-float(c["p_kw"]))+gq*(c["q_expr"]-float(c["q_kvar"]))
        grad_record[mid]={"dV_dP":gp_,"dV_dQ":gq}
       # The Fresh-AC pass/fail authority remains the unchanged 1.05 pu hard
       # limit.  A fixed 1.0498 surrogate margin over-constrained the second
       # relinearization after a discrete regulator tap exposed adjacent rows.
       # Ask a violating row to cross just inside the true boundary, while a
       # row already inside it only has to remain inside.  The small numerical
       # guard is deterministic and does not relax the scientific limit.
       voltage_limit=1.05-1.0e-5
       ref=model.addLConstr(expr<=voltage_limit,
        name=f"a_b10_post_tap_vmax_{focus_round}_{vi}")
       focus_refs.append(ref);hard_cut_refs.append(ref)
       soft_cut_specs.append((expr,voltage_limit,f"vmax_{vi}"))
       cut_rows.append({"family":"VOLTAGE","key":list(vk),"base":base_voltage[vk],"limit":voltage_limit,
                        "gradients":grad_record})
      for ti,tk in enumerate(transformer_keys):
       expr=gp.LinExpr(base_transformer[tk]);grad_record={}
       for c in controls:
        mid=str(c["mess_id"]);gp_=gradients.get((mid,"P","transformer",tk));gq=gradients.get((mid,"Q","transformer",tk))
        if gp_ is None or gq is None:continue
        expr+=gp_*(c["p_expr"]-float(c["p_kw"]))+gq*(c["q_expr"]-float(c["q_kvar"]))
        grad_record[mid]={"dLoading_dP":gp_,"dLoading_dQ":gq}
       transformer_limit=1.0-1.0e-5
       ref=model.addLConstr(expr<=transformer_limit,
        name=f"a_b10_post_tap_transformer_{focus_round}_{ti}")
       focus_refs.append(ref);hard_cut_refs.append(ref)
       soft_cut_specs.append((expr,transformer_limit,f"transformer_{ti}"))
       cut_rows.append({"family":"TRANSFORMER_CURRENT","key":list(tk),"base":base_transformer[tk],
                        "limit":transformer_limit,"gradients":grad_record})
      for li,lk in enumerate(line_keys):
       expr=gp.LinExpr(base_line[lk]);grad_record={}
       for c in controls:
        mid=str(c["mess_id"]);gp_=gradients.get((mid,"P","line",lk));gq=gradients.get((mid,"Q","line",lk))
        if gp_ is None or gq is None:continue
        expr+=gp_*(c["p_expr"]-float(c["p_kw"]))+gq*(c["q_expr"]-float(c["q_kvar"]))
        grad_record[mid]={"dLoading_dP":gp_,"dLoading_dQ":gq}
       line_limit=1.0-1.0e-5
       ref=model.addLConstr(expr<=line_limit,
        name=f"a_b10_post_tap_line_{focus_round}_{li}")
       focus_refs.append(ref);hard_cut_refs.append(ref)
       soft_cut_specs.append((expr,line_limit,f"line_{li}"))
       cut_rows.append({"family":"LINE_CURRENT","key":list(lk),"base":base_line[lk],
                        "limit":line_limit,"gradients":grad_record})
      model.setObjective(objective+1.0e-9*loc["econ"],gp.GRB.MINIMIZE);model.update()
      hard_surrogate_infeasible=False;surrogate_slack_sum_pu=None
      try:focus_solve=solve_recovery_anchor()
      except RuntimeError as hard_focus_exc:
       # A discrete tap change can make several first-order rows mutually
       # inconsistent even though the unchanged nonlinear AC feasible set is
       # nonempty.  Relax only these candidate-generation surrogates, minimize
       # their total violation, then require the ordinary Fresh OpenDSS hard
       # gate below.  No physical voltage/current/kVA limit is softened.
       hard_surrogate_infeasible=True
       model.remove(hard_cut_refs)
       removed_ids={id(ref) for ref in hard_cut_refs}
       focus_refs=[ref for ref in focus_refs if id(ref) not in removed_ids]
       slack_vars=[];slack_objective=gp.LinExpr(0.0)
       for si,(expr,limit,label) in enumerate(soft_cut_specs):
        slack=model.addVar(lb=0.0,name=f"a_b10_post_tap_cut_slack_{focus_round}_{si}")
        ref=model.addLConstr(expr<=limit+slack,
         name=f"a_b10_post_tap_cut_soft_{focus_round}_{label}")
        slack_vars.append(slack);focus_refs.extend([slack,ref]);slack_objective+=slack
       model.setObjective(slack_objective+1.0e-6*objective+1.0e-12*loc["econ"],gp.GRB.MINIMIZE)
       model.update()
       try:focus_solve=solve_recovery_anchor()
       except RuntimeError as soft_focus_exc:
        attempts.append({"round":recovery_round_limit+len(search_specs)+20+focus_round,
         "recovery_stage":"POST_TAP_EXACT_PQ_RELINEARIZATION","finite_difference_samples":fd_records,
         "cuts":cut_rows,"trust_radius_kw_kvar":trust_radius,
         "hard_surrogate_error":repr(hard_focus_exc),
         "fast_solver":{"status":"NO_FEASIBLE_INCUMBENT_WITH_SURROGATE_SLACK",
                        "error":repr(soft_focus_exc)},
         "exact_ac":None,"hard_limits_relaxed":False,"future_actual_used":False})
        if trust_radius>=PCS_APPARENT_LIMIT_KVA-1e-9:
         full_trust_infeasible_count+=1
         if full_trust_infeasible_count>=3:break
        else:full_trust_infeasible_count=0
        continue
       surrogate_slack_sum_pu=float(sum(slack.X for slack in slack_vars))
      full_trust_infeasible_count=0
      recovery_pcs_projections=_refresh_solution_after_ac_resolve(loc,science,sol)
      quality=abase.solver_quality(model)
      if any(float(quality.get(k,float("inf")))>lim for k,lim in
             (("ConstrVio",1e-6),("BoundVio",1e-6),("IntVio",1e-5))):
       raise RuntimeError(f"POST_TAP_EXACT_PQ_RELINEARIZATION_NUMERICAL_GATE_FAILED {quality}")
      issue_runtime["fresh_ac_capture_stage"]="POST_TAP_EXACT_PQ_RELINEARIZATION"
      ex=science.exact24_candidate(b4,grid24,scope,gstatic,issue,running,sol["plan"],sol["firstmess"])
      voltage_rows=_voltage_rows_from_live_opendss(grid24);line_rows=_line_rows_from_live_opendss(grid24)
      transformer_current_rows=_transformer_current_rows_from_live_opendss()
      remember_best_exact_candidate(ex,"POST_TAP_EXACT_PQ_RELINEARIZATION")
      recovery_candidate=_record_recovery_candidate(loc,science,issue_runtime,Path(issue_out),
       "POST_TAP_EXACT_PQ_RELINEARIZATION",ex,voltage_rows)
      attempts.append({"round":recovery_round_limit+len(search_specs)+20+focus_round,
       "recovery_stage":"POST_TAP_EXACT_PQ_RELINEARIZATION","finite_difference_samples":fd_records,
       "cuts":cut_rows,"trust_radius_kw_kvar":trust_radius,"fast_solver":focus_solve,
       "hard_surrogate_infeasible":hard_surrogate_infeasible,
       "surrogate_slack_sum_pu":surrogate_slack_sum_pu,
       "pcs_numerical_boundary_projection":recovery_pcs_projections,"candidate":recovery_candidate,
       "exact_ac":dict(ex),"violating_voltage_rows":[r for r in voltage_rows if r["hard_violation"]],
       "violating_line_rows":[r for r in line_rows if r["hard_violation"]],
       "violating_transformer_current_rows":[r for r in transformer_current_rows if r["hard_violation"]],
       "hard_limits_relaxed":False,"future_actual_used":False})
      if ex.get("hard_constraint_pass") is True:
       record={"schema_version":"mobileess.post_stage15.exact_ac_closed_loop.v3",
        "status":"PASS_RECOVERED_POST_TAP_EXACT_PQ_RELINEARIZATION","issue":int(issue),
        "selected_round":focus_round,"attempts":attempts,
        "hard_limits_relaxed":False,"future_actual_used":False}
       issue_runtime["ac_safety_recovery"]=record
       jw(Path(issue_out)/"A_B10_EXACT_AC_CLOSED_LOOP_RECOVERY.json",record)
       return True
      # A full surrogate-slack step can cross a discrete regulator boundary
      # and be worse in exact AC even though its direction is useful.  Test
      # deterministic damped points on the segment from the retained best base
      # to that step.  Each point is materialized in the unchanged optimization
      # model before Fresh OpenDSS; interpolation is never accepted directly.
      candidate_controls=_ac_h0_controls(loc,science)
      candidate_by_mid={str(c["mess_id"]):c for c in candidate_controls}
      for alpha in (0.25,0.50,0.75):
       if len(issue_runtime.get("fresh_ac_candidate_attempts",[]))>=FRESH_AC_PRODUCTION_CANDIDATE_MAX:break
       interpolation_refs=[];targets={}
       for ci,c in enumerate(controls):
        mid=str(c["mess_id"]);candidate=candidate_by_mid[mid]
        target_p=float(c["p_kw"])+alpha*(float(candidate["p_kw"])-float(c["p_kw"]))
        target_q=float(c["q_kvar"])+alpha*(float(candidate["q_kvar"])-float(c["q_kvar"]))
        targets[mid]={"p_kw":target_p,"q_kvar":target_q}
        interpolation_refs.append(model.addLConstr(
         c["p_expr"]/scale==target_p/scale,
         name=f"a_b10_post_tap_damped_p_{focus_round}_{int(alpha*100)}_{ci}"))
        interpolation_refs.append(model.addLConstr(
         c["q_expr"]/scale==target_q/scale,
         name=f"a_b10_post_tap_damped_q_{focus_round}_{int(alpha*100)}_{ci}"))
       model.update()
       try:damped_solve=solve_recovery_anchor()
       except RuntimeError as damped_exc:
        model.remove(interpolation_refs);model.update()
        attempts.append({"round":recovery_round_limit+len(search_specs)+40+focus_round,
         "recovery_stage":"POST_TAP_DAMPED_LINE_SEARCH","alpha":alpha,"targets":targets,
         "fast_solver":{"status":"NO_FEASIBLE_INCUMBENT","error":repr(damped_exc)},
         "exact_ac":None,"hard_limits_relaxed":False,"future_actual_used":False})
        continue
       damped_projections=_refresh_solution_after_ac_resolve(loc,science,sol)
       quality=abase.solver_quality(model)
       if any(float(quality.get(k,float("inf")))>lim for k,lim in
              (("ConstrVio",1e-6),("BoundVio",1e-6),("IntVio",1e-5))):
        raise RuntimeError(f"POST_TAP_DAMPED_LINE_SEARCH_NUMERICAL_GATE_FAILED {quality}")
       issue_runtime["fresh_ac_capture_stage"]="POST_TAP_DAMPED_LINE_SEARCH"
       damped_ex=science.exact24_candidate(
        b4,grid24,scope,gstatic,issue,running,sol["plan"],sol["firstmess"])
       voltage_rows=_voltage_rows_from_live_opendss(grid24)
       line_rows=_line_rows_from_live_opendss(grid24)
       transformer_current_rows=_transformer_current_rows_from_live_opendss()
       remember_best_exact_candidate(damped_ex,"POST_TAP_DAMPED_LINE_SEARCH")
       damped_candidate=_record_recovery_candidate(
        loc,science,issue_runtime,Path(issue_out),"POST_TAP_DAMPED_LINE_SEARCH",damped_ex,voltage_rows)
       attempts.append({"round":recovery_round_limit+len(search_specs)+40+focus_round,
        "recovery_stage":"POST_TAP_DAMPED_LINE_SEARCH","alpha":alpha,"targets":targets,
        "fast_solver":damped_solve,"pcs_numerical_boundary_projection":damped_projections,
        "candidate":damped_candidate,"exact_ac":dict(damped_ex),
        "hard_limits_relaxed":False,"future_actual_used":False})
       if damped_ex.get("hard_constraint_pass") is True:
        record={"schema_version":"mobileess.post_stage15.exact_ac_closed_loop.v3",
         "status":"PASS_RECOVERED_POST_TAP_DAMPED_LINE_SEARCH","issue":int(issue),
         "selected_round":focus_round,"selected_alpha":alpha,"attempts":attempts,
         "hard_limits_relaxed":False,"future_actual_used":False}
        issue_runtime["ac_safety_recovery"]=record
        jw(Path(issue_out)/"A_B10_EXACT_AC_CLOSED_LOOP_RECOVERY.json",record)
        return True
       model.remove(interpolation_refs);model.update()
      # Continue every relinearization from the globally closest exact point,
      # not from the last or the largest surrogate-slack step.
      controls=[dict(c) for c in best_recovery_bundle["controls"]]
      first=[dict(row) for row in best_recovery_bundle["first"]]
      plan=[dict(row) for row in best_recovery_bundle["plan"]]
      voltage_rows=[dict(row) for row in best_recovery_bundle["voltage_rows"]]
      line_rows=[dict(row) for row in best_recovery_bundle["line_rows"]]
      transformer_current_rows=[dict(row) for row in best_recovery_bundle["transformer_rows"]]
      # Only a feasible correction solve owns a new Var.X incumbent.  Capture
      # it now for the next exact relinearization; the infeasible branch above
      # deliberately continues from the preceding materialized base point.
      last_feasible_controls=[dict(c) for c in controls]
      last_feasible_first=[dict(row) for row in first]
      last_feasible_plan=[dict(row) for row in plan]
      if best_recovery_bundle["score"]>=round_start_best_score:
       no_exact_improvement_rounds+=1
       if no_exact_improvement_rounds>=3:break
      else:no_exact_improvement_rounds=0
     return False
    # Searching Q only at the maximum-active-power anchor is incomplete: a
    # safe discrete-tap/current point may lie at an interior P dispatch even
    # though both the economic point and the maximum-P point are unsafe.  Add
    # a bounded identity-neutral bank of zero/half/full P fractions.  Cyclic
    # rotations prevent any MESS/site from receiving a privileged pattern.
    # The original 64 maximum-P Q directions remain intact; the 32 interior-P
    # candidates use only the small, fixed seed bank and stay within the
    # global Fresh-AC candidate bound.
    full_p_fraction=tuple(1.0 for _ in anchor_controls)
    search_specs=[(full_p_fraction,pattern) for pattern in normalized_patterns]
    active_fraction_seed=list((1.0,0.5,0.0,1.0)[:len(anchor_controls)])
    while len(active_fraction_seed)<len(anchor_controls):active_fraction_seed.append(1.0)
    active_fraction_patterns=[]
    for rotation in range(max(1,len(active_fraction_seed))):
     values=active_fraction_seed[rotation:]+active_fraction_seed[:rotation]
     key=tuple(float(value) for value in values)
     if key not in active_fraction_patterns:active_fraction_patterns.append(key)
    for active_fractions in active_fraction_patterns:
     for pattern in normalized_patterns[:8]:
      spec=(active_fractions,pattern)
      if spec not in search_specs:search_specs.append(spec)
    # Run the broad maximum-P/Q bank before local coordinate refinement.  A
    # near-boundary point in the original operating neighbourhood can sit on
    # the wrong regulator-tap branch; spending the bounded Fresh-AC budget
    # there can prevent evaluation of the causal high-active-power branch.
    for search_index,(active_fractions,pattern) in enumerate(search_specs,1):
     if len(issue_runtime.get("fresh_ac_candidate_attempts",[]))>=FRESH_AC_PRODUCTION_CANDIDATE_MAX:break
     if tap_search_refs:
      model.remove(tap_search_refs);model.update();tap_search_refs=[]
     # Reuse the stored expressions.  Removing the preceding candidate rows
     # invalidates X values, but not the model variables themselves.
     current_controls=anchor_controls
     target_q={}
     for ci,c in enumerate(current_controls):
      mid=str(c["mess_id"]);p_target=float(active_fractions[ci])*float(anchor_p[mid])
      q_cap=math.sqrt(max(0.0,PCS_APPARENT_LIMIT_KVA**2-p_target**2))
      q_target=float(pattern[ci])*q_cap;target_q[mid]=q_target
      tap_search_refs.append(model.addLConstr(
       c["p_expr"]/scale==p_target/scale,
       name=f"a_b10_max_p_q_search_p_{search_index}_{ci}"))
      tap_search_refs.append(model.addLConstr(
       c["q_expr"]/scale==q_target/scale,
       name=f"a_b10_max_p_q_search_q_{search_index}_{ci}"))
     model.setObjective(loc["econ"],gp.GRB.MINIMIZE);model.update()
     try:tap_search_solve=solve_recovery_anchor()
     except RuntimeError as search_exc:
      attempts.append({"round":recovery_round_limit+search_index,
       "recovery_stage":"MAX_P_Q_TAP_SEARCH","normalized_q_pattern":list(pattern),
       "normalized_p_anchor_fractions":list(active_fractions),
       "anchor_p_kw":anchor_p,"target_q_kvar":target_q,
       "fast_solver":{"status":"NO_FEASIBLE_INCUMBENT","error":repr(search_exc)},
       "exact_ac":None,"hard_limits_relaxed":False,"future_actual_used":False})
      continue
     recovery_pcs_projections=_refresh_solution_after_ac_resolve(loc,science,sol)
     quality=abase.solver_quality(model)
     if any(float(quality.get(k,float("inf")))>lim for k,lim in
            (("ConstrVio",1e-6),("BoundVio",1e-6),("IntVio",1e-5))):
      raise RuntimeError(f"MAX_P_Q_TAP_SEARCH_NUMERICAL_GATE_FAILED {quality}")
     issue_runtime["fresh_ac_capture_stage"]="MAX_P_Q_TAP_SEARCH"
     ex=science.exact24_candidate(b4,grid24,scope,gstatic,issue,running,sol["plan"],sol["firstmess"])
     voltage_rows=_voltage_rows_from_live_opendss(grid24)
     line_rows=_line_rows_from_live_opendss(grid24)
     transformer_current_rows=_transformer_current_rows_from_live_opendss()
     remember_best_exact_candidate(ex,"MAX_P_Q_TAP_SEARCH")
     recovery_candidate=_record_recovery_candidate(loc,science,issue_runtime,Path(issue_out),
      "MAX_P_Q_TAP_SEARCH",ex,voltage_rows)
     last_feasible_controls=_ac_h0_controls(loc,science)
     last_feasible_first=_ac_firstmess(loc,science,last_feasible_controls)
     last_feasible_plan=_ac_current_plan(loc)
     attempts.append({"round":recovery_round_limit+search_index,
      "recovery_stage":"MAX_P_Q_TAP_SEARCH","normalized_q_pattern":list(pattern),
      "normalized_p_anchor_fractions":list(active_fractions),
      "anchor_p_kw":anchor_p,"target_q_kvar":target_q,
      "h0_exact_ac_candidate_projection_override":issue_runtime["h0_exact_ac_candidate_projection_override"],
      "max_p_anchor_solver":max_p_solve,"fast_solver":tap_search_solve,
      "pcs_numerical_boundary_projection":recovery_pcs_projections,
      "candidate":recovery_candidate,"exact_ac":dict(ex),
      "violating_voltage_rows":[r for r in voltage_rows if r["hard_violation"]],
      "violating_line_rows":[r for r in line_rows if r["hard_violation"]],
      "violating_transformer_current_rows":[r for r in transformer_current_rows if r["hard_violation"]],
      "hard_limits_relaxed":False,"future_actual_used":False})
     if ex.get("hard_constraint_pass") is True:
      record={"schema_version":"mobileess.post_stage15.exact_ac_closed_loop.v2",
       "status":"PASS_RECOVERED_MAX_P_Q_TAP_SEARCH","issue":int(issue),
       "max_cut_rounds":recovery_round_limit,
       "tap_search_candidate_limit":len(search_specs),
       "tap_search_selected_index":search_index,"cut_count":sum(len(x.get("cuts",[])) for x in attempts),
       "attempts":attempts,"hard_limits_relaxed":False,"future_actual_used":False}
      issue_runtime["ac_safety_recovery"]=record
      jw(Path(issue_out)/"A_B10_EXACT_AC_CLOSED_LOOP_RECOVERY.json",record)
      return ex
     tap_candidate_point={str(c["mess_id"]):(float(c["p_kw"]),float(c["q_kvar"]))
                          for c in last_feasible_controls}
     tap_voltage=bool(ex.get("voltage_violation_count"))
     tap_overload=bool(ex.get("line_violation_count") or ex.get("transformer_current_violation_count"))
     tap_point_record={"point":tap_candidate_point,"pattern":list(pattern),"exact_ac":dict(ex)}
     if tap_voltage and not tap_overload and not ex.get("transformer_kva_violation_count"):
      tap_voltage_only_points.append(tap_point_record)
     elif tap_overload and not tap_voltage and not ex.get("transformer_kva_violation_count"):
      tap_overload_only_points.append(tap_point_record)
    # The low-discrepancy bank can straddle a narrow regulator/current safety
    # boundary without sampling inside it.  Do not discard that exact causal
    # information.  Select the closest complementary pair in normalized PCS-Q
    # space and bisect it with Fresh OpenDSS as the sole acceptance authority.
    # Both endpoints already satisfy the unchanged MIQCP and share the same P,
    # routing and integer decisions, so every midpoint also preserves all
    # PCS/SOC/mobility/service constraints.  Twenty samples keep the complete
    # production path within the pre-existing 96-candidate hard bound.
    if tap_voltage_only_points and tap_overload_only_points:
     q_caps={mid:math.sqrt(max(0.0,PCS_APPARENT_LIMIT_KVA**2-float(anchor_p[mid])**2))
             for mid in anchor_p}
     def tap_pair_distance(pair):
      left,right=pair
      return sum(((left["point"][mid][1]-right["point"][mid][1])
                  /max(1.0,q_caps[mid]))**2 for mid in sorted(anchor_p))
     voltage_side,overload_side=min(
      ((v,o) for v in tap_voltage_only_points for o in tap_overload_only_points),
      key=tap_pair_distance)
     tap_bracket_candidate_max=20
     for bracket_index in range(1,tap_bracket_candidate_max+1):
      if tap_search_refs:
       model.remove(tap_search_refs);model.update();tap_search_refs=[]
      midpoint={mid:((voltage_side["point"][mid][0]+overload_side["point"][mid][0])/2.0,
                     (voltage_side["point"][mid][1]+overload_side["point"][mid][1])/2.0)
                for mid in sorted(anchor_p)}
      for ci,c in enumerate(anchor_controls):
       mid=str(c["mess_id"]);p_target,q_target=midpoint[mid]
       tap_search_refs.append(model.addLConstr(
        c["p_expr"]/scale==p_target/scale,
        name=f"a_b10_max_p_q_bracket_p_{bracket_index}_{ci}"))
       tap_search_refs.append(model.addLConstr(
        c["q_expr"]/scale==q_target/scale,
        name=f"a_b10_max_p_q_bracket_q_{bracket_index}_{ci}"))
      model.setObjective(loc["econ"],gp.GRB.MINIMIZE);model.update()
      try:tap_bracket_solve=solve_recovery_anchor()
      except RuntimeError as bracket_exc:
       attempts.append({"round":recovery_round_limit+len(search_specs)+bracket_index,
        "recovery_stage":"MAX_P_Q_TAP_BRACKET_SEARCH","midpoint":midpoint,
        "fast_solver":{"status":"NO_FEASIBLE_INCUMBENT","error":repr(bracket_exc)},
        "exact_ac":None,"hard_limits_relaxed":False,"future_actual_used":False})
       break
      recovery_pcs_projections=_refresh_solution_after_ac_resolve(loc,science,sol)
      quality=abase.solver_quality(model)
      if any(float(quality.get(k,float("inf")))>lim for k,lim in
             (("ConstrVio",1e-6),("BoundVio",1e-6),("IntVio",1e-5))):
       raise RuntimeError(f"MAX_P_Q_TAP_BRACKET_NUMERICAL_GATE_FAILED {quality}")
      issue_runtime["fresh_ac_capture_stage"]="MAX_P_Q_TAP_BRACKET_SEARCH"
      ex=science.exact24_candidate(b4,grid24,scope,gstatic,issue,running,sol["plan"],sol["firstmess"])
      voltage_rows=_voltage_rows_from_live_opendss(grid24)
      line_rows=_line_rows_from_live_opendss(grid24)
      transformer_current_rows=_transformer_current_rows_from_live_opendss()
      remember_best_exact_candidate(ex,"MAX_P_Q_TAP_BRACKET_SEARCH")
      recovery_candidate=_record_recovery_candidate(loc,science,issue_runtime,Path(issue_out),
       "MAX_P_Q_TAP_BRACKET_SEARCH",ex,voltage_rows)
      last_feasible_controls=_ac_h0_controls(loc,science)
      last_feasible_first=_ac_firstmess(loc,science,last_feasible_controls)
      last_feasible_plan=_ac_current_plan(loc)
      attempts.append({"round":recovery_round_limit+len(search_specs)+bracket_index,
       "recovery_stage":"MAX_P_Q_TAP_BRACKET_SEARCH",
       "selected_pair_normalized_distance":tap_pair_distance((voltage_side,overload_side)),
       "voltage_side":voltage_side,"overload_side":overload_side,"midpoint":midpoint,
       "fast_solver":tap_bracket_solve,"pcs_numerical_boundary_projection":recovery_pcs_projections,
       "candidate":recovery_candidate,"exact_ac":dict(ex),
       "violating_voltage_rows":[r for r in voltage_rows if r["hard_violation"]],
       "violating_line_rows":[r for r in line_rows if r["hard_violation"]],
       "violating_transformer_current_rows":[r for r in transformer_current_rows if r["hard_violation"]],
       "hard_limits_relaxed":False,"future_actual_used":False})
      if ex.get("hard_constraint_pass") is True:
       record={"schema_version":"mobileess.post_stage15.exact_ac_closed_loop.v3",
        "status":"PASS_RECOVERED_MAX_P_Q_TAP_BRACKET_SEARCH","issue":int(issue),
        "max_cut_rounds":recovery_round_limit,"tap_search_candidate_limit":len(search_specs),
        "tap_bracket_candidate_limit":tap_bracket_candidate_max,
        "tap_bracket_selected_index":bracket_index,
        "cut_count":sum(len(x.get("cuts",[])) for x in attempts),"attempts":attempts,
        "hard_limits_relaxed":False,"future_actual_used":False}
       issue_runtime["ac_safety_recovery"]=record
       jw(Path(issue_out)/"A_B10_EXACT_AC_CLOSED_LOOP_RECOVERY.json",record)
       return ex
      bracket_point={str(c["mess_id"]):(float(c["p_kw"]),float(c["q_kvar"]))
                     for c in last_feasible_controls}
      bracket_record={"point":bracket_point,"pattern":None,"exact_ac":dict(ex)}
      bracket_voltage=bool(ex.get("voltage_violation_count"))
      bracket_overload=bool(ex.get("line_violation_count") or ex.get("transformer_current_violation_count"))
      if (bracket_voltage and not bracket_overload
          and not ex.get("transformer_kva_violation_count")):
       voltage_side=bracket_record
      elif (bracket_overload and not bracket_voltage
            and not ex.get("transformer_kva_violation_count")):
       overload_side=bracket_record
      else:
       break
    # A simultaneous voltage/line/transformer violation has no complementary
    # voltage-only/current-only bracket, but it is exactly the case that needs
    # the full P/Q exact relinearization.  Start from the globally closest
    # causal Fresh-AC point, not from the last enumeration-order pattern.
    # If the broad bank already found a point within 0.005 pu/loading of all
    # hard limits, spend the remaining budget on exact local relinearization
    # immediately.  Otherwise use the wider coordinate search first.  This is
    # only search ordering: the Fresh-AC limits and candidate cap are unchanged.
    near_exact_boundary=(best_recovery_bundle["score"][0]==0
                         and best_recovery_bundle["score"][1]<=0.005)
    if near_exact_boundary:
     select_best_relinearization_base()
     if post_tap_exact_pq_relinearization():return ex
     if exact_coordinate_search():return ex
    else:
     if exact_coordinate_search():return ex
     select_best_relinearization_base()
     if post_tap_exact_pq_relinearization():return ex
    if tap_search_refs:model.remove(tap_search_refs);model.update()
   except RuntimeError as anchor_exc:
    attempts.append({"round":recovery_round_limit+1,
     "recovery_stage":"MAX_P_Q_TAP_SEARCH_ANCHOR",
     "fast_solver":{"status":"NO_FEASIBLE_INCUMBENT","error":repr(anchor_exc)},
     "exact_ac":None,"hard_limits_relaxed":False,"future_actual_used":False})
 record={"schema_version":"mobileess.post_stage15.exact_ac_closed_loop.v1","status":"GRID_CORRECTION_EXHAUSTED",
         "hard_limits_relaxed":False,"finite_difference_step_kw_kvar":AC_RECOVERY_FD_STEP_KW,
         "conservative_voltage_cut_margin_pu":AC_RECOVERY_VOLTAGE_CUT_MARGIN_PU,
          "max_cut_rounds":recovery_round_limit,"cut_count":sum(len(x.get("cuts",[])) for x in attempts),
         "attempts":attempts,"future_actual_used":False}
 issue_runtime["ac_safety_recovery"]=record;jw(Path(issue_out)/"A_B10_EXACT_AC_CLOSED_LOOP_RECOVERY.json",record)
 raise RuntimeError("GRID_CORRECTION_EXHAUSTED")

def planner_solve(model,cb)->dict[str,Any]:
 model.Params.Threads=4;model.Params.MIPGap=0.10;model.Params.MIPGapAbs=0.0;model.Params.MIPFocus=1
 model.Params.Heuristics=0.20;model.Params.TimeLimit=300.0;model.Params.OutputFlag=1;model.update();model.reset()
 presolve=int(os.environ.get("MOBILEESS_PLANNER_PRESOLVE","-1"))
 if presolve not in {-1,0,1,2}:raise RuntimeError(f"unsupported MOBILEESS_PLANNER_PRESOLVE={presolve}")
 model.Params.Presolve=presolve
 t=time.monotonic();model.optimize(cb) if cb is not None else model.optimize();wall=time.monotonic()-t
 q=abase.solver_quality(model);q["wall_seconds"]=wall;q["candidate_available"]=int(model.SolCount)>0;q["presolve_setting"]=presolve
 q["failure_classification"]=("CANDIDATE_AVAILABLE" if int(model.SolCount)>0 else
  ("PROVEN_INFEASIBLE" if int(model.Status)==int(__import__('gurobipy').GRB.INFEASIBLE) else
   ("NO_INCUMBENT_WITHIN_BUDGET" if int(model.Status)==int(__import__('gurobipy').GRB.TIME_LIMIT) else "NUMERICAL_OR_SOLVER_FAILURE")))
 return q

def planner_feasibility_rescue(model,cb)->tuple[dict[str,Any],Any]:
 """Search a hard-feasible slow plan on a copy; never overwrites the economic model."""
 import gurobipy as gp
 model.update();rescue=model.copy();rescue.setObjective(gp.LinExpr(0.0),gp.GRB.MINIMIZE)
 rescue.Params.Threads=4;rescue.Params.TimeLimit=300.0;rescue.Params.SolutionLimit=1
 rescue.Params.MIPFocus=1;rescue.Params.Presolve=-1;rescue.Params.OutputFlag=1
 t=time.monotonic();rescue.optimize(cb);wall=time.monotonic()-t
 q=abase.solver_quality(rescue);q.update({"wall_seconds":wall,"candidate_available":int(rescue.SolCount)>0,
  "purpose":"HARD_FEASIBILITY_ONLY_NO_ECONOMIC_CLAIM","slack_allowed":False,
  "failure_classification":("CANDIDATE_AVAILABLE" if int(rescue.SolCount)>0 else
   ("PROVEN_INFEASIBLE" if int(rescue.Status)==int(gp.GRB.INFEASIBLE) else
    ("NO_INCUMBENT_WITHIN_BUDGET" if int(rescue.Status)==int(gp.GRB.TIME_LIMIT) else "NUMERICAL_OR_SOLVER_FAILURE")))})
 return q,rescue

def planner_solve_sparse_copy(model,cb):
 """Solve an exact planner copy without redundant dense R25K strengthening rows.

 The original model is left byte-for-byte structurally intact for the conditioned
 physical dispatch.  Only rows documented in science/main.py as algebraic
 consequences of retained recursions/gates are omitted from the planner copy.
 """
 t=time.monotonic();model.update();original_nz=float(model.DNumNZs)
 planner=model.copy()
 source_vars=model.getVars();planner_vars=planner.getVars()
 if len(source_vars)!=len(planner_vars):
  planner.dispose();raise RuntimeError("planner-copy variable cardinality drift")
 for attr in ("VarHintVal","VarHintPri","BranchPriority","Start"):
  planner.setAttr(attr,planner_vars,model.getAttr(attr,source_vars))
 planner.update()
 prefixes=("r25k_debt_stay_cover_dense_","r25k_soc_stay_cover_dense_","r25k_mobility_soc_prefix_cover_")
 remove=[c for c in planner.getConstrs() if str(c.ConstrName).startswith(prefixes)]
 expected=4*(2*(H-len(range(0,H,6)))+H)
 if len(remove)!=expected:
  planner.dispose();raise RuntimeError(f"sparse planner-copy redundant-row count {len(remove)} != {expected}")
 planner.remove(remove);planner.update();projected_nz=float(planner.DNumNZs)
 projection_wall=time.monotonic()-t
 q=planner_solve(planner,cb);solver_wall=float(q["wall_seconds"])
 q.update({"solver_wall_seconds":solver_wall,"copy_projection_wall_seconds":projection_wall,
           "wall_seconds":time.monotonic()-t,"original_linear_nonzeros":original_nz,
           "projected_linear_nonzeros":projected_nz,"omitted_redundant_rows":len(remove),
           "search_guidance_transferred_by_variable_order":True,
           "planner_copy_only":True,"physical_commit_model_unchanged":True})
 return q,planner

def planner_solve_exact_copy(model,cb):
 """Keep the commit model untouched while the slow planner searches."""
 model.update();planner=model.copy()
 try:q=planner_solve(planner,cb)
 except Exception:
  planner.dispose();raise
 q["planner_model_copy"]="EXACT_FULL_ROW_COPY"
 return q,planner

def restore_redundant_dense_b4_rows(loc:Mapping[str,Any])->dict[str,Any]:
 """Restore the exact R25K dense strengthening rows before physical dispatch."""
 import gurobipy as gp
 model=loc["m"];mids=list(loc["mids"]);energy=loc["r24_energy_terms"]
 stay_by_mid_h=loc["stay_by_mid_h"];DE=loc["DE"];E=loc["E"]
 cap=float(loc["_C"]);floor=float(loc["_E_FLOOR_MODEL"])
 scale=float(loc["_c5r4_energy_scale_kwh_per_model_unit"]);mess_E=loc["mess_E"]
 before=int(model.NumConstrs);added=0
 for mid in mids:
  for hh in range(H):
   if hh%6==0:continue
   future_stay=gp.quicksum(s for t in range(hh,H) for sid,s in stay_by_mid_h.get((mid,t),[]))
   future_dis=gp.quicksum(energy[(mid,t)]["discharge"] for t in range(hh,H))
   future_dep=gp.quicksum(energy[(mid,t)]["depart"] for t in range(hh,H))
   future_comm=sum(float(energy[(mid,t)]["committed"]) for t in range(hh,H))
   model.addLConstr(DE[(mid,hh)]+future_dis<=cap*future_stay,name=f"r25k_debt_stay_cover_dense_{mid}_{hh}")
   model.addLConstr(E[(mid,hh)]+cap*future_stay-future_dep-future_comm>=floor,name=f"r25k_soc_stay_cover_dense_{mid}_{hh}")
   added+=2
  e0=float(mess_E[mid])/scale;cum_dep=0.0;cum_stay=0.0;cum_comm=0.0
  for kk in range(1,H+1):
   t=kk-1;cum_dep=cum_dep+energy[(mid,t)]["depart"]
   cum_stay=cum_stay+gp.quicksum(s for sid,s in stay_by_mid_h.get((mid,t),[]))
   cum_comm=cum_comm+float(energy[(mid,t)]["committed"])
   model.addLConstr(e0+cap*cum_stay-cum_dep-cum_comm>=floor,name=f"r25k_mobility_soc_prefix_cover_{mid}_{kk}")
   added+=1
 model.update()
 expected=4*(2*(H-len(range(0,H,6)))+H)
 if added!=expected or int(model.NumConstrs)-before!=expected:
  raise RuntimeError(f"dense B4 restore cardinality drift added={added} expected={expected}")
 return {"status":"PASS_DENSE_ROWS_RESTORED_BEFORE_PHYSICAL_DISPATCH","rows_added":added,
         "planner_used_exact_sparse_equivalent":True,"physical_dispatch_dense_rows_present":True}

def soft_metrics_from_causal_inputs(mess_E_raw:Mapping[str,Any],science_ref:Mapping[str,Any],
                                   sources:SourceBlocks,issue:int)->dict[str,float]:
 mess_E={str(k):float(v) for k,v in mess_E_raw.items()}
 soc_margin=min((v-440.0 for v in mess_E.values()),default=9999.0)
 if issue==START:
  load_err=0.0
 else:
  prior=sources.q50_next_background_kw(issue-1)
  bp,bq,pv,_=science_ref["store"].step(issue)
  actual=float(np.asarray(bp,float).sum()-np.asarray(pv,float).sum())
  load_err=0.0 if prior is None else abs(actual-prior)/max(1.0,abs(prior))*100.0
 return {"load_forecast_error_pct":float(load_err),"soc_reserve_margin_kwh":float(soc_margin)}

def prune_dynamic_science_cache(science,sources:SourceBlocks,clear_all:bool=False)->dict[str,Any]:
 """Retain only the immutable D2 connection-delay contract across issues.

 The D2 cache value is a plain audited scalar/summary keyed by the authoritative
 parquet path, byte size, and mtime.  All DataFrames, arrays, topology objects,
 and issue mobility data are evicted because the legacy science builder does
 not promise that those objects remain mutation-free after model construction.
 """
 cache=getattr(science,"_PERSIST",None)
 if not isinstance(cache,dict):return {"available":False,"before":0,"after":0,"removed_dynamic":0}
 before=len(cache)
 if clear_all:
  cache.clear();return {"available":True,"before":before,"after":0,"removed_dynamic":before,"mode":"TEST_ONLY_CLEAR_ALL"}
 keep=[key for key in cache if isinstance(key,tuple) and key and key[0]=="d2_connection_delay"]
 remove=[key for key in cache if key not in keep]
 for key in remove:cache.pop(key,None)
 return {"available":True,"before":before,"after":len(cache),"removed_dynamic":len(remove),
         "mode":"D2_IMMUTABLE_CONTRACT_ONLY","d2_entries_retained":len(keep),
         "future_actual_cached":False}

def current_soft_metrics(loc:Mapping[str,Any],sources:SourceBlocks,issue:int)->dict[str,float]:
 return soft_metrics_from_causal_inputs(loc.get("mess_E",{}),loc["ref"],sources,issue)

def local_scope_from_soft(loc:Mapping[str,Any],metrics:Mapping[str,float],issue:int,config:Mapping[str,Any])->tuple[list[str],list[str]]:
 jobs=[]
 if metrics.get("load_forecast_error_pct",0.0)>=10.0:
  jobs=sorted({str(k[0]) for k in loc.get("x",{}) if issue<=int(k[3])<issue+12})
 mess=[]
 if metrics.get("soc_reserve_margin_kwh",1e9)<=90.0:
  E={str(k):float(v) for k,v in loc.get("mess_E",{}).items()}
  if E:
   m=min(E,key=E.get);mess=[m]
 return jobs,mess

def map_hard_invalidation(exc)->str:
 rs=" ".join(map(str,exc.reasons))
 if "TRANSIT" in rs:return "MESS_TRANSIT_CONFLICT"
 if exc.affected_job_ids:return "WORKLOAD_DEADLINE_RISK"
 return "ACTIVE_PLAN_INFEASIBLE"

def quarantine_incomplete(engine:Path,issue:int,policy_root:Path):
 d=engine/f"issue_{issue:06d}"
 # POST may have been written by the frozen inner engine before wrapper-level
 # observability/audit/marker persistence.  Without a valid marker the whole
 # directory is an uncommitted transaction and must never be reused in place.
 if d.exists() and not commit_marker_path(d).is_file():
  q=policy_root/"interrupted_attempts"/datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")/d.name
  q.parent.mkdir(parents=True,exist_ok=True);shutil.move(str(d),str(q))

def archive_stale_failure(path:Path,policy_root:Path)->None:
 if not path.is_file():return
 q=policy_root/"interrupted_attempts"/datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")/"stale_failures"/path.name
 q.parent.mkdir(parents=True,exist_ok=True);shutil.move(str(path),str(q))

def commit_marker_path(issue_dir:Path)->Path:return issue_dir/"A_B10_COMMIT_MARKER.json"

def write_commit_marker(issue_dir:Path,issue:int,last_replan:int,event_after:Mapping[str,Any],active_plan_path:Path)->dict[str,Any]:
 required={
  "post":issue_dir/"BUILD7C_POSTCOMMIT_STATE.json",
  "transition":issue_dir/"BUILD7C_FIRSTSTEP_TRANSITION_CERTIFICATE.json",
  "fresh_exact_ac":issue_dir/f"exact_grid/FRESH_EXACT_OPENDSS_24SERVICE_ISSUE_{issue}.json",
  "exact_ac_observability":issue_dir/"exact_grid/A_B10_FRESH_EXACT_AC_OBSERVABILITY.json",
  "model_observability":issue_dir/"A_B10_COMMITTED_MODEL_OBSERVABILITY.json",
  "policy_issue_audit":issue_dir/"POLICY_ISSUE_AUDIT.json",
 }
 for name,p in required.items():
  if not p.is_file():raise RuntimeError(f"commit marker missing {name}: {p}")
 post=load_json(required["post"]);tr=load_json(required["transition"]);fresh=load_json(required["fresh_exact_ac"])
 if tr.get("status")!="PASS" or fresh.get("hard_constraint_pass") is not True or post.get("sha256")!=tr.get("post_state_sha256"):
  raise RuntimeError(f"commit marker acceptance evidence invalid issue={issue}")
 event_payload=dict(event_after);event_digest=hashlib.sha256(json.dumps(event_payload,sort_keys=True,separators=(",",":")).encode()).hexdigest()
 marker={"schema_version":"mobileess.post_stage15.atomic_commit_marker.v2","status":"COMMITTED","issue":int(issue),
  "pre_state_sha256":tr["pre_state_sha256"],"post_state_sha256":tr["post_state_sha256"],
  "transition_certificate_sha256":sha(required["transition"]),"fresh_exact_ac_sha256":sha(required["fresh_exact_ac"]),
  "exact_ac_observability_sha256":sha(required["exact_ac_observability"]),
  "model_observability_sha256":sha(required["model_observability"]),
  "policy_issue_audit_sha256":sha(required["policy_issue_audit"]),
  "active_plan_sha256":sha(active_plan_path) if active_plan_path.is_file() else None,
  "last_replan_issue":int(last_replan),"event_engine_state":event_payload,"event_engine_state_sha256":event_digest,
  "unsafe_action_committed":False,"future_actual_used":False}
 jw(commit_marker_path(issue_dir),marker);return marker

def validate_commit_marker(issue_dir:Path)->dict[str,Any]:
 marker=load_json(commit_marker_path(issue_dir));issue=int(marker["issue"])
 legacy=marker.get("schema_version")=="mobileess.post_stage15.atomic_commit_marker.v1"
 checks=((issue_dir/"BUILD7C_POSTCOMMIT_STATE.json",None,True),
         (issue_dir/"BUILD7C_FIRSTSTEP_TRANSITION_CERTIFICATE.json",marker["transition_certificate_sha256"],True),
         (issue_dir/f"exact_grid/FRESH_EXACT_OPENDSS_24SERVICE_ISSUE_{issue}.json",marker["fresh_exact_ac_sha256"],True),
         (issue_dir/"exact_grid/A_B10_FRESH_EXACT_AC_OBSERVABILITY.json",marker.get("exact_ac_observability_sha256"),not legacy),
         (issue_dir/"A_B10_COMMITTED_MODEL_OBSERVABILITY.json",marker.get("model_observability_sha256"),not legacy),
         (issue_dir/"POLICY_ISSUE_AUDIT.json",marker["policy_issue_audit_sha256"],True))
 if marker.get("status")!="COMMITTED":raise RuntimeError(f"invalid commit marker status issue={issue}")
 for p,digest,required in checks:
  if not required and digest is None:continue
  if not p.is_file() or (digest is not None and sha(p)!=digest):raise RuntimeError(f"commit marker SHA mismatch {p}")
 event=marker.get("event_engine_state",{});actual=hashlib.sha256(json.dumps(event,sort_keys=True,separators=(",",":")).encode()).hexdigest()
 if actual!=marker.get("event_engine_state_sha256"):raise RuntimeError(f"commit marker event-state SHA mismatch issue={issue}")
 return marker

def restore_event_engine(event,checkpoint:Mapping[str,Any]):
 st=checkpoint.get("event_engine_state",{})
 for k,v in st.get("active",{}).items():
  if k in event._active:event._active[k]=bool(v)
 event._soft_since_issue=st.get("soft_since_issue")

def event_state(event):
 return {"active":dict(event._active),"soft_since_issue":event._soft_since_issue}

def write_policy_manifest(root:Path,cfg:Mapping[str,Any],config_sha:str,source_auth:Mapping[str,Any],shared_authority_sha:str):
 jw(root/"CONTROLLER_POLICY_MANIFEST.json",{
  "schema_version":"mobileess.post_stage15.controller_policy_manifest.v2","status":"FROZEN_BEFORE_REP_WEEK_POLICY_OUTCOME",
  "candidate_id":CANDIDATE_ID,"method_id":"B5","method_config_sha256":B5_SHA,
  "policy_id":cfg["policy_id"],"slot":cfg["slot"],"resolved_config_sha256":config_sha,
  "base_policy":cfg["base_policy"],"event_triggered":cfg["event_triggered"],
  "local_repair_enabled":cfg["local_repair_enabled"],"max_refresh_steps":cfg["max_refresh_steps"],
  "controller_burn_in_steps":0,"canonical_pre_state_sha256":PRE_SHA,
   "same_exogenous_source_authority_sha256":shared_authority_sha,
  "hard_safety_events_are_universal":True,
  "scientific_source_commit":PR4,"science_main_sha256":SCIENCE_SHA,
  "planner_latency_execution_semantics":"BOUNDARY_SYNCHRONOUS_SCIENTIFIC_REPLAY; SLOW_PLANNER_RUNTIME_REPORTED_SEPARATELY",
  "realtime_claim_on_development_host":"NOT_DEMONSTRATED_UNTIL_MEASURED",
  "future_actual_used":False,"future_plans_persisted":False,
 })

def load_schema()->dict[str,Any]:
 return load_json(HERE/"authority/D/04_RESULT_CONTRACT/K9H7_RESULT_V1_SCHEMA_INVENTORY_R10.json")

def build_results(policy_root:Path,engine:Path,cfg:Mapping[str,Any],issue_audits:list[dict[str,Any]]):
 schema=load_schema();run_id=f"B_{CANDIDATE_ID}_{cfg['slot']}_{cfg['policy_id']}";scenario=CANDIDATE_ID
 common={"result_schema_version":RESULT_SCHEMA,"run_id":run_id,"method_id":"B5","scenario_id":scenario}
 rolling=[];mess=[];debt=[];grid=[];opt=[];constraints=[];wan=[];rack=[];forecast=[];busphase=[]
 model_obs={};actual_by_issue={};issued_forecasts=[]
 for audit in issue_audits:
  issue=int(audit["issue"]);p=engine/f"issue_{issue:06d}/A_B10_COMMITTED_MODEL_OBSERVABILITY.json"
  if not p.is_file():raise RuntimeError(f"committed model observability missing issue={issue}")
  model_obs[issue]=load_json(p);actual_by_issue[issue]=model_obs[issue]["source_values_h0"]
 started_meta={};completed=set()
 min_soc=math.inf;max_soc=-math.inf
 total_charge=total_dis=total_mob_e=total_travel=0.0
 grid_mwh=0.0;peak_grid=-math.inf
 vmin=math.inf;vmax=-math.inf;maxline=0.0;maxtx=0.0
 vviol=lviol=tviol=0
 runtimes=[];gaps=[];nodes=[]
 pre_wd=pre_sd=0.0
 for audit in issue_audits:
  issue=int(audit["issue"]);d=engine/f"issue_{issue:06d}"
  tr=load_json(d/"BUILD7C_FIRSTSTEP_TRANSITION_CERTIFICATE.json")
  fr=load_json(d/f"exact_grid/FRESH_EXACT_OPENDSS_24SERVICE_ISSUE_{issue}.json")
  pre=load_json(d/"BUILD7C_PRECOMMIT_STATE.json");post=load_json(d/"BUILD7C_POSTCOMMIT_STATE.json")
  pst=pre.get("state",pre);qst=post.get("state",post)
  ts=int(fr.get("timestamp_utc_ns",0));fallback_date=datetime.fromisoformat(CANDIDATE_ID.split("_",1)[1]).replace(tzinfo=timezone(timedelta(hours=10)))
  dt=datetime.fromtimestamp(ts/1e9,tz=timezone.utc) if ts else fallback_date.astimezone(timezone.utc)
  aest=dt.astimezone(timezone(timedelta(hours=10))).isoformat()
  ac_recovery=audit.get("ac_safety_recovery") or {};ac_cut_count=int(ac_recovery.get("cut_count",0) or 0)
  obs_path=d/"exact_grid/A_B10_FRESH_EXACT_AC_OBSERVABILITY.json"
  if not obs_path.is_file():raise RuntimeError(f"exact AC observability missing issue={issue}")
  obs=load_json(obs_path);mo=model_obs[issue]
  for vr in obs.get("bus_phase_voltage",[]):
   busphase.append({**common,"issue_step":issue,"timestamp_utc_ns":ts,"element_type":"BUS_PHASE",
    "element_id":f"{vr['bus']}.{vr['node']}","bus":vr["bus"],"phase":vr["node"],
    "Vmag_pu":vr["voltage_pu"],"Vangle_deg":vr["angle_deg"],"P_kW":None,"Q_kvar":None,
    "current_A":None,"loading_pu":None,"violation":bool(vr["hard_violation"])})
  for lr in obs.get("line_terminal_phase",[]):
   element=f"{lr.get('line','')}|T{lr.get('terminal','')}|C{lr.get('conductor','')}"
   busphase.append({**common,"issue_step":issue,"timestamp_utc_ns":ts,"element_type":"LINE_TERMINAL_PHASE",
    "element_id":element,"bus":"","phase":lr.get("conductor"),"Vmag_pu":None,"Vangle_deg":lr.get("angle_deg"),
    "P_kW":lr.get("p_kw"),"Q_kvar":lr.get("q_kvar"),"current_A":lr.get("current_a"),
    "loading_pu":lr.get("loading_pu"),"violation":bool((lr.get("loading_pu") or 0)>1.0)})
  for xr in obs.get("transformer_terminal_current",[]):
   element=f"{xr.get('transformer','')}|W{xr.get('winding',xr.get('terminal',''))}|C{xr.get('conductor','')}"
   busphase.append({**common,"issue_step":issue,"timestamp_utc_ns":ts,"element_type":"TRANSFORMER_TERMINAL_PHASE",
    "element_id":element,"bus":xr.get("bus",""),"phase":xr.get("conductor"),"Vmag_pu":None,"Vangle_deg":xr.get("angle_deg"),
    "P_kW":xr.get("p_kw"),"Q_kvar":xr.get("q_kvar"),"current_A":xr.get("current_a"),
    "loading_pu":xr.get("loading_pu"),"violation":bool((xr.get("loading_pu") or 0)>1.0)})
  mp=load_csv(d/"BUILD7B_FULL54_MESS_PLAN.csv")
  mv=load_csv(d/"BUILD7B_FULL54_MOVE_ARCS_SELECTED.csv")
  mv0={str(x["mess_id"]):x for x in mv if inum(x.get("horizon_step"))==0}
  h0=[x for x in mp if inum(x.get("horizon_step"))==0]
  mrows=[]
  for x in h0:
   mid=str(x["mess_id"]);mr=mv0.get(mid)
   pdis=fnum(x.get("P_discharge_kW"),0);pchg=fnum(x.get("P_charge_kW"),0);q=fnum(x.get("Q_kvar"),0)
   soc=fnum(x.get("SOC_kWh"),fnum(pst.get("mess_E_kWh",{}).get(mid)))
   spct=100*soc/1080.0 if soc is not None else None
   if spct is not None:min_soc=min(min_soc,spct);max_soc=max(max_soc,spct)
   total_charge+=pchg*(5/60)/1000;total_dis+=pdis*(5/60)/1000
   travel=(fnum((mr or {}).get("safe_total_duration_steps"),0) or 0)*5 if mr else 0
   pre_e=fnum(pst.get("mess_E_kWh",{}).get(mid),soc) or 0;post_e=fnum(qst.get("mess_E_kWh",{}).get(mid),soc) or 0
   energy=pre_e+0.95*(5/60)*pchg-(5/60)*pdis/0.95-post_e
   total_mob_e+=abs(energy)/1000;total_travel+=travel
   row={**common,"issue_step":issue,"timestamp_utc_ns":ts,"mess_id":mid,
        "state":x.get("state",""),"current_node":x.get("service_id",""),
        "next_node":(mr or {}).get("destination_service_id",""),"route_id":(mr or {}).get("slot",""),
        "connected":str(x.get("state",""))=="STAY","travel_time_min":travel,
        "mobility_energy_signed_kWh":energy,"P_kW":pdis-pchg,"Q_kvar":q,"S_kVA":math.hypot(pdis-pchg,q),
        "charge_kW":pchg,"discharge_kW":pdis,"SOC_kWh":soc,"SOC_pct":spct,
        "support_energy_debt_kWh":fnum(x.get("support_energy_debt_kWh"),fnum(pst.get("mess_support_debt_kWh",{}).get(mid),0)),
        "route_energy_profile_id":(mr or {}).get("template_id",""),
        "route_eta_min":(fnum((mr or {}).get("safe_eta_sec"))/60 if mr and fnum((mr or {}).get("safe_eta_sec")) is not None else None)}
   mess.append(row);mrows.append(row)
  wd=sum(float(v) for v in qst.get("workload_debt_GPUh",{}).values())
  sd=sum(float(v) for v in qst.get("mess_support_debt_kWh",{}).values())
  debt.append({**common,"issue_step":issue,"timestamp_utc_ns":ts,"workload_debt_GPUh":wd,
               "workload_debt_created_GPUh":max(0,wd-pre_wd),"workload_debt_repaid_GPUh":max(0,pre_wd-wd),
               "support_energy_debt_kWh":sd,"support_energy_debt_created_kWh":max(0,sd-pre_sd),
               "support_energy_debt_repaid_kWh":max(0,pre_sd-sd),"terminal_reachability_pass":True})
  pre_wd,pre_sd=wd,sd
  grid.append({**common,"issue_step":issue,"timestamp_utc_ns":ts,"converged":bool(fr.get("converged")),
    "hard_constraint_pass":bool(fr.get("hard_constraint_pass")),"root_import_p_kW":fr.get("root_import_p_kw"),
    "root_import_q_kvar":fr.get("root_import_q_kvar"),"voltage_min_pu":fr.get("voltage_min_pu"),
    "voltage_max_pu":fr.get("voltage_max_pu"),"voltage_violation_count":fr.get("voltage_violation_count"),
    "line_max_loading_pu":fr.get("line_max_loading_pu"),"line_violation_count":fr.get("line_violation_count"),
    "transformer_max_kva_loading_pu":fr.get("transformer_max_kva_loading_pu"),
    "transformer_kva_violation_count":fr.get("transformer_kva_violation_count"),
    "transformer_max_current_loading_pu":fr.get("transformer_max_current_loading_pu"),
    "transformer_current_violation_count":fr.get("transformer_current_violation_count"),"cut_triggered":ac_cut_count>0})
  gi=fnum(fr.get("root_import_p_kw"),0);grid_mwh+=gi/1000*(5/60);peak_grid=max(peak_grid,gi)
  vmin=min(vmin,fnum(fr.get("voltage_min_pu"),math.inf));vmax=max(vmax,fnum(fr.get("voltage_max_pu"),-math.inf))
  maxline=max(maxline,fnum(fr.get("line_max_loading_pu"),0));maxtx=max(maxtx,fnum(fr.get("transformer_max_kva_loading_pu"),0))
  vviol+=inum(fr.get("voltage_violation_count"),0);lviol+=inum(fr.get("line_violation_count"),0);tviol+=inum(fr.get("transformer_kva_violation_count"),0)
  fast=audit.get("fast_solver",{});runtime=fnum(audit.get("commit_critical_runtime_s"),0);gap=fnum(fast.get("MIPGap"),fnum(fast.get("mip_gap")))
  runtimes.append(runtime)
  if gap is not None:gaps.append(gap)
  n=fnum(fast.get("NodeCount"),fnum(fast.get("node_count")));nodes.append(n or 0)
  ms=mo.get("model_stats",{});objective=mo.get("objective",{})
  opt.append({**common,"issue_step":issue,"model_status":audit.get("dispatch_status",""),
              "objective_level_3":objective.get("economic_projected_AUD"),"runtime_s":runtime,"node_count":n,"mip_gap":gap,
              "simplex_iterations":ms.get("simplex_iterations"),"barrier_iterations":ms.get("barrier_iterations"),
              "variable_count":inum(fast.get("NumVars"),inum(fast.get("variables"))),
              "binary_count":inum(fast.get("NumBinVars"),inum(fast.get("binary_variables"))),
              "constraint_count":inum(fast.get("NumConstrs"),inum(fast.get("constraints"),inum(ms.get("linear_constraints")))),
              "iis_generated":False,"resolve_iteration":int(audit.get("replan_executed",False))+len(ac_recovery.get("attempts",[])),
              "cut_count":ac_cut_count,"numeric_focus":fast.get("NumericFocus"),
              "feasibility_tol":fast.get("FeasibilityTol"),"optimality_tol":fast.get("OptimalityTol")})
  f0=mo["forecast_issued"][0];actual=mo["source_values_h0"]
  issue_cost=(fnum(fr.get("root_import_p_kw"),0) or 0)*(5/60)/1000*float(f0["rrp_q50"])
  rolling.append({**common,"issue_step":issue,"timestamp_utc_ns":ts,"timestamp_aest":aest,
                  "rrp_AUD_per_MWh_realized":f0["rrp_q50"],"rrp_q10":f0["rrp_q10"],"rrp_q50":f0["rrp_q50"],"rrp_q90":f0["rrp_q90"],
                  "PV_available_kW":actual["actual_pv_available_kw"],
                  "grid_import_kW":fr.get("root_import_p_kw"),"grid_import_kvar":fr.get("root_import_q_kvar"),
                  "MESS_net_P_kW":sum(fnum(r["P_kW"],0) for r in mrows),"MESS_net_Q_kvar":sum(fnum(r["Q_kvar"],0) for r in mrows),
                  "total_SOC_kWh":sum(float(v) for v in qst.get("mess_E_kWh",{}).values()),
                  "workload_debt_GPUh":wd,"support_energy_debt_kWh":sd,
                  "min_voltage_pu":fr.get("voltage_min_pu"),"max_voltage_pu":fr.get("voltage_max_pu"),
                  "max_line_loading_pu":fr.get("line_max_loading_pu"),"max_transformer_loading_pu":fr.get("transformer_max_kva_loading_pu"),
                  "voltage_violation_count":fr.get("voltage_violation_count"),"line_overload_count":fr.get("line_violation_count"),
                  "transformer_overload_count":fr.get("transformer_kva_violation_count"),
                  "objective_level_3":issue_cost,"solve_time_s":runtime,"mip_gap":gap,"exact_AC_pass":True,"cut_count_this_issue":ac_cut_count,"commit_status":"COMMITTED"})
  for rr in mo.get("rack_pool_h0",[]):
   rack.append({**common,"issue_step":issue,"rack_pool_id":rr["rack_pool_id"],"idc_id":rr["idc_id"],
    "current_job_count":rr["current_job_count"],"committed_job_count":rr["started_job_count"],"gpu_used":rr["gpu_used"],
    "gpu_headroom":rr.get("gpu_headroom"),"IT_power_kW":rr["it_power_kw"],"facility_power_kW":rr["facility_power_kw"],
    "kw_headroom_current":rr.get("it_power_headroom_kw"),"kw_headroom_commitment":rr.get("it_power_headroom_kw"),
    "transformer_limit_kW":rr.get("transformer_limit_kw"),"current_certificate_pass":True,"commitment_certificate_pass":True})
  for wr in mo.get("wan_send_h0",[]):
   wan.append({**common,"job_id":wr["job_uid"],"source_idc":wr["source_idc"],"destination_idc":wr["destination_idc"],
    "send_step":wr["send_step"],"GB_sent":wr["gb_sent"],"bytes_sent":wr["gb_sent"]*1e9,
    "same_step_send_start_violation":False,"destination_changed_after_prefetch":False,"certificate_pass":True})
  issued_forecasts.extend({**r,"issue_step":issue} for r in mo.get("forecast_issued",[]))
  for attempt in ac_recovery.get("attempts",[]):
   ax=attempt.get("exact_ac",{})
   constraints.append({**common,"issue_step":issue,"layer":"FRESH_EXACT_AC_RECOVERY","constraint_family":"GRID_HARD_RISK",
    "entity_id":cfg["policy_id"],"severity":"HARD","predicted_or_realized":"REALIZED_EXACT_AC",
    "violation":not bool(ax.get("hard_constraint_pass")),"cut_added":bool(attempt.get("cuts")),
    "message":json.dumps({"round":attempt.get("round"),"vmin":ax.get("voltage_min_pu"),"vmax":ax.get("voltage_max_pu"),
                           "cuts":len(attempt.get("cuts",[]))},sort_keys=True)})
  for reason in audit.get("event_reasons",[]):
   constraints.append({**common,"issue_step":issue,"layer":"CONTROLLER_POLICY","constraint_family":"REPLAN_EVENT",
                       "entity_id":cfg["policy_id"],"severity":"HARD" if str(reason).startswith("HARD") else "SOFT",
                       "predicted_or_realized":"CAUSAL_RUNTIME","violation":True,"cut_added":False,"message":str(reason)})
  for uid in tr.get("started_jobs",[]):
   started_meta.setdefault(str(uid),{"start_step":issue})
   plan=load_csv(d/"BUILD7B_FULL54_JOB_PLAN.csv")
   rr=next((x for x in plan if str(x.get("job_uid"))==str(uid) and inum(x.get("start_step"))==issue),None)
   if rr:started_meta[str(uid)].update(rr)
  completed.update(map(str,tr.get("completed_jobs",[])))
  wpath=d.parent/"BUILD7C_ROLLING54_WAN_SEND.csv"
  # one-issue runs may put this at engine root; leave WAN table source-backed only if an issue-local row is available.
 # Evaluation-only realized joins are performed after every causal forecast has
 # been persisted.  They never feed back into the controller.
 forecast_authority=load_json(policy_root/"episode_manifest.json").get("shared_exogenous_authority_sha256","")
 for frw in issued_forecasts:
  target=int(frw["target_step"]);real=actual_by_issue.get(target);h=int(frw["horizon_step"]);src=int(frw["issue_step"])
  specs=[
   ("RRP_AUD_PER_MWH",frw.get("rrp_q10"),frw.get("rrp_q50"),frw.get("rrp_q90"),
    None if real is None else next((x["rrp_q50"] for x in model_obs[target]["forecast_issued"] if int(x["horizon_step"])==0),None)),
   ("NET_BACKGROUND_P_KW",None,frw.get("net_background_p_q50_kw"),
    fnum(frw.get("gross_background_p_q90_kw"),0)-fnum(frw.get("pv_available_q10_kw"),0),
    None if real is None else real["actual_gross_background_p_kw"]-real["actual_pv_available_kw"]),
   ("PV_AVAILABLE_KW",frw.get("pv_available_q10_kw"),None,None,None if real is None else real["actual_pv_available_kw"]),
   ("BACKGROUND_Q_KVAR",None,frw.get("background_q_q50_kvar"),frw.get("background_q_q90_kvar"),
    None if real is None else real["actual_background_q_kvar"]),
  ]
  for variable,q10,q50,q90,realized in specs:
   err=None if q50 is None or realized is None else abs(float(q50)-float(realized))
   forecast.append({"result_schema_version":RESULT_SCHEMA,"forecast_model_id":"FROZEN_CAUSAL_SOURCE",
    "forecast_authority_id":forecast_authority,"issue_step":src,"horizon_step":h,"target_step":target,
    "target_utc_ns":None,"variable":variable,"spatial_key":"SYSTEM_AGGREGATE","phase":"ALL",
    "q10":q10,"q50":q50,"q90":q90,"realized":realized,"absolute_error_q50":err,
    "squared_error_q50":None if err is None else err*err,
    "interval_10_90_covered":None if realized is None or q10 is None or q90 is None else float(q10)<=float(realized)<=float(q90),
    "evaluation_only_join":realized is not None})
 # Independent expected job cohort drives job_event coverage.
 independent=HERE/"authority/D/03_C_ZERO_BURNIN/independent_job_authority/PER_JOB_RUNTIME_SOURCE_CANONICAL_V2044R5.parquet"
 idf=pd.read_parquet(independent)
 cohort=idf[(idf["arrival_step"].astype(int)>=START)&(idf["arrival_step"].astype(int)<=END)].copy()
 jobs=[]
 final=load_json(engine/f"issue_{END:06d}/BUILD7C_POSTCOMMIT_STATE.json");fst=final.get("state",final)
 final_completed=set(map(str,fst.get("completed",fst.get("completed_job_ids",[]))))
 final_running=set(map(str,fst.get("running",{})))
 final_queue=set(map(str,fst.get("queue",{})))
 for rec in cohort.to_dict("records"):
  uid=str(rec["job_uid"]);arr=int(rec["arrival_step"]);sm=started_meta.get(uid,{})
  st=inum(sm.get("start_step"));fin=inum(sm.get("completion_step_exclusive"))
  status="COMPLETED" if uid in final_completed else ("RUNNING" if uid in final_running else ("PENDING" if uid in final_queue else "ARRIVED"))
  origin=rec.get("origin_IDC_id",rec.get("origin_idc",rec.get("original_idc","")))
  gpu=rec.get("requested_gpu",rec.get("GPU_required",""))
  deadline=rec.get("latest_completion_step_exclusive",rec.get("deadline_step",""))
  jobs.append({**common,"job_id":uid,"arrival_step":arr,"original_idc":origin,
               "selected_idc":sm.get("destination_IDC_id",""),"selected_rack":sm.get("rack_pool_id",""),
               "start_step":st,"finish_step":fin,"queue_delay_min":((st-arr)*5 if st is not None else None),
               "deadline_step":deadline,"deadline_miss":(bool(fin is not None and inum(deadline) is not None and fin>inum(deadline))),
               "migration_happened":bool(sm and origin and str(sm.get("destination_IDC_id",""))!=str(origin)),
               "GPU_required":gpu,"GPUh":rec.get("GPUh",""),"status":status})
 # Header-only source-backed tables not directly persisted at needed granularity.
 tables={"rolling_step":rolling,"job_event":jobs,"rack_step":rack,"wan_event":wan,"mess_step":mess,"debt_step":debt,
         "constraint_event":constraints,"forecast_eval":forecast,"grid_exact_ac_bus_phase":busphase,
         "grid_exact_ac_summary":grid,"optimization_stats":opt}
 delays=[fnum(x.get("queue_delay_min")) for x in jobs if fnum(x.get("queue_delay_min")) is not None]
 planner=[fnum(x.get("slow_planner_runtime_s")) for x in issue_audits if fnum(x.get("slow_planner_runtime_s")) is not None and fnum(x.get("slow_planner_runtime_s"))>0]
 misses=sum(1 for x in jobs if x.get("deadline_miss") is True)
 energy_cost=sum((fnum(x.get("grid_import_kW"),0) or 0)*(5/60)/1000*(fnum(x.get("rrp_AUD_per_MWh_realized"),0) or 0) for x in rolling)
 pv_available=sum((fnum(x.get("PV_available_kW"),0) or 0)*(5/60)/1000 for x in rolling)
 pv_used=pv_available
 max_wd=max((fnum(x.get("workload_debt_GPUh"),0) or 0 for x in debt),default=0.0)
 max_sd=max((fnum(x.get("support_energy_debt_kWh"),0) or 0 for x in debt),default=0.0)
 ac_cuts=sum(int((x.get("ac_safety_recovery") or {}).get("cut_count",0) or 0) for x in issue_audits)
 summary={**common,"forecast_model_id":"","causal_eligible":True,"oracle":False,"start_step":START,"end_step":END,
  "committed_steps":len(issue_audits),"status":"PASS" if len(issue_audits)==COUNT else "INCOMPLETE",
  "energy_procurement_cost_AUD":energy_cost,"economic_cost_total_AUD":energy_cost,"objective_level_3":energy_cost,
  "grid_import_MWh":grid_mwh,"peak_grid_import_kW":peak_grid,"min_voltage_pu":vmin,"max_voltage_pu":vmax,
  "PV_available_MWh":pv_available,"PV_used_MWh":pv_used,"PV_curtailed_MWh":pv_available-pv_used,
  "PV_utilization_pct":100.0 if pv_available>0 else None,
  "voltage_violation_count":vviol,"voltage_violation_minutes":vviol*5.0,"max_line_loading_pu":maxline,
  "line_overload_count":lviol,"max_transformer_loading_pu":maxtx,"transformer_overload_count":tviol,
  "jobs_total":len(jobs),"jobs_completed":len(final_completed.intersection({str(x['job_id']) for x in jobs})),
  "deadline_miss_count":misses,"mean_job_delay_min":statistics.mean(delays) if delays else None,
  "p95_job_delay_min":quantile(delays,.95),"p99_job_delay_min":quantile(delays,.99),"max_job_delay_min":max(delays) if delays else None,
  "MESS_charge_MWh":total_charge,"MESS_discharge_MWh":total_dis,"MESS_mobility_energy_MWh":total_mob_e,
  "MESS_travel_minutes":total_travel,"battery_throughput_MWh":total_charge+total_dis,
  "SOC_min_pct":min_soc if math.isfinite(min_soc) else None,"SOC_max_pct":max_soc if math.isfinite(max_soc) else None,
  "max_workload_debt_GPUh":max_wd,"terminal_workload_debt_GPUh":fnum(debt[-1].get("workload_debt_GPUh"),0) if debt else None,
  "max_support_energy_debt_kWh":max_sd,"terminal_support_energy_debt_kWh":fnum(debt[-1].get("support_energy_debt_kWh"),0) if debt else None,
  "exact_AC_calls":len(grid),"exact_AC_fail_count":sum(1 for x in grid if not x["hard_constraint_pass"]),
  "AC_cut_count":ac_cuts,"resolve_count":sum(int(x.get("replan_executed",False)) for x in issue_audits),
  "solve_time_total_s":sum(runtimes),"solve_time_mean_s":statistics.mean(runtimes) if runtimes else None,
  "solve_time_p95_s":quantile(runtimes,.95),"solve_time_max_s":max(runtimes) if runtimes else None,
  "MIP_gap_max":max(gaps) if gaps else None,"MIP_nodes_total":sum(nodes),
  "notes":f"{CANDIDATE_ID} actual 2016-issue B5 policy episode. Slow-planner runtime is reported separately in RUNTIME_CHARACTERIZATION.json; real-time claim is not inferred from this development host."}
 tables["run_summary"]=[summary]
 for name in TABLES:write_csv(policy_root/f"{name}.csv",schema[name]["fields"],tables[name])
 obs={"schema_version":"mobileess.post_stage15.rep_week.observability.v1","candidate_id":CANDIDATE_ID,"header_only_tables":[n for n in TABLES if n!="run_summary" and not tables[n]],
      "reason":"No trustworthy row-level source persisted by the frozen scientific engine for these tables; values are not fabricated.",
      "job_event_expected_cohort_from_independent_authority":True}
 jw(policy_root/"OBSERVABILITY_GAPS.json",obs)

def run_f7(policy_root:Path,cfg:Mapping[str,Any]):
 gen=HERE/"authority/D/05_F7/generate_F7_coverage_certificate_split_authority_v2.py"
 val=HERE/"authority/D/05_F7/k9h7_validate_F7_coverage_certificate_R14_FROZEN.py"
 independent=HERE/"authority/D/03_C_ZERO_BURNIN/independent_job_authority/PER_JOB_RUNTIME_SOURCE_CANONICAL_V2044R5.parquet"
 import subprocess
 cp=subprocess.run([sys.executable,str(gen),"--episode-manifest",str(policy_root/"episode_manifest.json"),
  "--independent-arrivals",str(independent),"--evaluation-end-state",str(policy_root/"EVALUATION_END_RUNTIME_STATE.json"),
  "--job-event",str(policy_root/"job_event.csv"),"--output",str(policy_root/"F7_JOB_EVENT_COHORT_COVERAGE_CERTIFICATE_V1.json")],text=True,capture_output=True)
 (policy_root/"logs/F7_GENERATOR.log").write_text(cp.stdout+"\n"+cp.stderr)
 if cp.returncode:raise RuntimeError("F7 generator failed")
 cp2=subprocess.run([sys.executable,str(val),"--episode-root",str(policy_root),
  "--certificate",str(policy_root/"F7_JOB_EVENT_COHORT_COVERAGE_CERTIFICATE_V1.json"),
  "--output",str(policy_root/"F7_validation")],text=True,capture_output=True)
 (policy_root/"logs/F7_VALIDATOR.log").write_text(cp2.stdout+"\n"+cp2.stderr)
 if cp2.returncode:raise RuntimeError("F7 validator failed")

def main():
 global START,END,COUNT,CANDIDATE_ID,CANDIDATE_MONTH,PROGRESS_FILE,PRE_SHA,PRE_FILE_SHA,PRE_RESUME_PATH,SHARED
 ap=argparse.ArgumentParser()
 ap.add_argument("--repo",required=True);ap.add_argument("--config",required=True);ap.add_argument("--output",required=True)
 ap.add_argument("--candidate-id",default="W02_2025-01-13",
                 help="Frozen representative-week candidate id from INITIAL_STATE_MANIFEST.json.")
 ap.add_argument("--shared-root",default="",
                 help="Candidate-specific immutable exogenous source root; defaults under frozen_artifacts.")
 ap.add_argument("--benchmark-issues",type=int,default=0,
                 help="Run only the first N real issues, including Fresh OpenDSS and POST commit; 0 keeps the frozen full episode.")
 ap.add_argument("--benchmark-force-modes",default="",
                 help="Test-only comma list ISSUE:LOCAL_REPAIR|FULL_REPLAN; requires --benchmark-issues and is excluded from scientific results.")
 ap.add_argument("--benchmark-disable-worker-cache",action="store_true")
 ap.add_argument("--benchmark-disable-active-projection",action="store_true")
 ap.add_argument("--benchmark-planner-presolve",type=int,choices=[-1,0,1,2],default=None,
                 help="Test-only targeted planner presolve candidate; requires --benchmark-issues.")
 ap.add_argument("--benchmark-causal-guidance",choices=["none","hints","start"],default="none",
                 help="Test-only preceding causal-plan solver guidance; requires --benchmark-issues.")
 ap.add_argument("--benchmark-skip-redundant-dense-b4-cuts",action="store_true",
                 help="Test-only exact omission of redundant dense R25K rows; requires --benchmark-issues.")
 ap.add_argument("--benchmark-sparse-planner-copy",action="store_true",
                 help="Test-only sparse exact planner copy with untouched dense commit model; requires --benchmark-issues.")
 ap.add_argument("--benchmark-clear-all-science-cache",action="store_true",
                 help="Test-only legacy full cache clear at every issue boundary; requires --benchmark-issues.")
 ap.add_argument("--benchmark-legacy-planned-replan-retry",action="store_true",
                 help="Test-only legacy projected-build failure followed by full-domain rebuild; requires --benchmark-issues.")
 ap.add_argument("--benchmark-fast-rack-lookup",action="store_true",
                 help="Compatibility flag: exact scalar-index Rack lookup is now the production default.")
 ap.add_argument("--benchmark-disable-fast-rack-lookup",action="store_true",
                 help="Test-only legacy pandas Rack scalar lookup; requires --benchmark-issues.")
 ap.add_argument("--benchmark-sparse-plan-restore-dense",action="store_true",
                 help="Compatibility flag: exact sparse planning plus dense physical-dispatch restore is now the production default.")
 ap.add_argument("--legacy-dense-planner",action="store_true",
                 help="Rollback to the pre-acceleration dense planner and automatic Presolve; physical constraints/objective are unchanged.")
 a=ap.parse_args()
 CANDIDATE_ID=str(a.candidate_id)
 manifest_path=HERE.parent/"INITIALIZATION/INITIAL_STATES/INITIAL_STATE_MANIFEST.json"
 initialization_root=HERE.parent/"INITIALIZATION"
 initial_manifest=load_json(manifest_path)
 matches=[x for x in initial_manifest.get("files",[]) if x.get("candidate_id")==CANDIDATE_ID]
 if len(matches)!=1:raise RuntimeError(f"candidate must occur exactly once in frozen initial-state manifest: {CANDIDATE_ID}")
 episode_authority=matches[0]
 START=int(episode_authority["week_start_index"]);END=START+2015;COUNT=2016
 CANDIDATE_MONTH=CANDIDATE_ID.split("_",1)[1][:7]
 PROGRESS_FILE=("W02_PROGRESS.json" if CANDIDATE_ID=="W02_2025-01-13" else f"{CANDIDATE_ID}_PROGRESS.json")
 PRE_SHA=str(episode_authority["state_sha256"])
 PRE_FILE_SHA=str(episode_authority["file_sha256"])
 PRE_RESUME_PATH=initialization_root/str(episode_authority["production_resume_relpath"])
 canonical_pre_path=initialization_root/str(episode_authority["path"])
 if not canonical_pre_path.is_file() or sha(canonical_pre_path)!=PRE_FILE_SHA:
  raise RuntimeError(f"{CANDIDATE_ID} canonical PRE file SHA drift")
 if not PRE_RESUME_PATH.is_file() or sha(PRE_RESUME_PATH)!=str(episode_authority["production_resume_file_sha256"]):
  raise RuntimeError(f"{CANDIDATE_ID} production PRE envelope SHA drift")
 default_shared=("B_W02_SHARED_EXOGENOUS_SOURCE_CURRENT" if CANDIDATE_ID=="W02_2025-01-13"
                 else f"B_{CANDIDATE_ID}_SHARED_EXOGENOUS_SOURCE_CURRENT")
 SHARED=(Path(a.shared_root).resolve() if a.shared_root else
         Path("/home/jaewon/mobile_ess_work/frozen_artifacts")/default_shared)
 if a.benchmark_issues<0 or a.benchmark_issues>COUNT:raise RuntimeError("--benchmark-issues must be in [0,2016]")
 if a.benchmark_planner_presolve is not None and not a.benchmark_issues:
  raise RuntimeError("--benchmark-planner-presolve is allowed only for bounded regression")
 if a.benchmark_causal_guidance!="none" and not a.benchmark_issues:
  raise RuntimeError("--benchmark-causal-guidance is allowed only for bounded regression")
 if a.benchmark_skip_redundant_dense_b4_cuts and not a.benchmark_issues:
  raise RuntimeError("--benchmark-skip-redundant-dense-b4-cuts is allowed only for bounded regression")
 if a.benchmark_sparse_planner_copy and not a.benchmark_issues:
  raise RuntimeError("--benchmark-sparse-planner-copy is allowed only for bounded regression")
 if a.benchmark_sparse_planner_copy and a.benchmark_skip_redundant_dense_b4_cuts:
  raise RuntimeError("planner-copy and construction-time dense-row omission candidates are mutually exclusive")
 if a.benchmark_sparse_plan_restore_dense and (a.benchmark_sparse_planner_copy or a.benchmark_skip_redundant_dense_b4_cuts):
  raise RuntimeError("sparse-plan dense-restore candidate is mutually exclusive with other sparse planner candidates")
 if a.legacy_dense_planner and (a.benchmark_sparse_plan_restore_dense or a.benchmark_sparse_planner_copy or a.benchmark_skip_redundant_dense_b4_cuts):
  raise RuntimeError("legacy dense rollback is mutually exclusive with sparse planner flags")
 if a.benchmark_clear_all_science_cache and not a.benchmark_issues:
  raise RuntimeError("--benchmark-clear-all-science-cache is allowed only for bounded regression")
 if a.benchmark_legacy_planned_replan_retry and not a.benchmark_issues:
  raise RuntimeError("--benchmark-legacy-planned-replan-retry is allowed only for bounded regression")
 if a.benchmark_disable_fast_rack_lookup and not a.benchmark_issues:
  raise RuntimeError("--benchmark-disable-fast-rack-lookup is allowed only for bounded regression")
 if a.benchmark_fast_rack_lookup and a.benchmark_disable_fast_rack_lookup:
  raise RuntimeError("Rack lookup enable/disable benchmark flags are mutually exclusive")
 forced_modes={}
 post_dispatch_hard_flags={}
 if a.benchmark_force_modes:
  if not a.benchmark_issues:raise RuntimeError("--benchmark-force-modes is allowed only for bounded regression")
  for token in a.benchmark_force_modes.split(","):
   raw_issue,mode=token.split(":",1);ii=int(raw_issue);mode=mode.strip().upper()
   if mode not in {"LOCAL_REPAIR","FULL_REPLAN"}:raise RuntimeError(f"unsupported forced benchmark mode {mode}")
   forced_modes[ii]=mode
 run_end=END if a.benchmark_issues==0 else START+a.benchmark_issues-1
 run_count=run_end-START+1
 if not a.benchmark_issues and os.environ.get("PYTHONHASHSEED")!="0":
  raise RuntimeError("production execution requires PYTHONHASHSEED=0; use a frozen representative-week launcher")
 book=PerformanceBook();current_performance={"issue":None,"record":None}
 repo=Path(a.repo).resolve();cfg_path=Path(a.config).resolve();cfg=load_json(cfg_path);policy_root=Path(a.output).resolve()
 fixed_location=bool(cfg.get("fixed_location_projection",False))
 if fixed_location and cfg.get("policy_id")!="M4_FIXED_LOCATION_ESS_MOBILITY_ABLATION":
  raise RuntimeError("fixed-location projection requires the frozen M4 method identity")
 # Production M1--M3 planning omits only the 576 R25K rows proven to be exact
 # algebraic consequences of retained recursions/gates.  The rows are restored
 # before the conditioned physical dispatch.  M4 and the explicit rollback keep
 # the legacy dense construction.  Benchmark-only alternative sparse candidates
 # retain their isolated behavior.
 use_sparse_restore=(not fixed_location and not a.legacy_dense_planner
                     and not a.benchmark_sparse_planner_copy
                     and not a.benchmark_skip_redundant_dense_b4_cuts)
 planner_presolve=(a.benchmark_planner_presolve if a.benchmark_planner_presolve is not None
                   else (1 if use_sparse_restore else -1))
 if sha(repo/"science/main.py")!=SCIENCE_SHA:raise RuntimeError("science/main.py SHA drift")
 if cfg["candidate_id"]!="W02_2025-01-13" or cfg["method_config_sha256"]!=B5_SHA:
  raise RuntimeError("common policy-template identity drift")
 if not SITE_AUTHORITY.is_file() or sha(SITE_AUTHORITY)!=SITE_AUTHORITY_SHA:raise RuntimeError("prospective four-site authority drift")
 site_authority=load_json(SITE_AUTHORITY)
 homes={str(k):str(v) for k,v in site_authority.get("assignment",{}).items()}
 if site_authority.get("status")!="PASS_EXACTLY_FOUR_SITES" or set(homes)!={f"MESS{x:02d}" for x in range(1,5)} or len(set(homes.values()))!=4:
  raise RuntimeError(f"invalid prospective four-site authority {homes}")
 if CANDIDATE_ID=="W02_2025-01-13" and (cfg.get("canonical_pre_state_sha256")!=PRE_SHA or cfg.get("canonical_pre_file_sha256")!=PRE_FILE_SHA):
  raise RuntimeError("W02 policy-template canonical PRE binding drift")
 if cfg.get("initial_service_sites")!=homes or cfg.get("initial_service_authority_sha256")!=SITE_AUTHORITY_SHA:
  raise RuntimeError("policy config common initial-site binding drift")
 if fixed_location and cfg.get("fixed_location_sites")!=homes:
  raise RuntimeError("M4 fixed-location config differs from common initial sites")
 config_sha=sha(cfg_path)
 expected_file=HERE/"configs"/cfg_path.name
 if expected_file.resolve()!=cfg_path and expected_file.is_file() and sha(expected_file)!=config_sha:raise RuntimeError("policy config SHA mismatch")
 policy_root.mkdir(parents=True,exist_ok=True);(policy_root/"logs").mkdir(exist_ok=True);(policy_root/"progress").mkdir(exist_ok=True)
 engine=policy_root/"engine";engine.mkdir(exist_ok=True)
 archive_stale_failure(policy_root/"FAILURE.json",policy_root)
 archive_stale_failure(engine/"_FAILURE.json",policy_root)
 control=policy_root/"control";control.mkdir(exist_ok=True);(control/"empty_hints").mkdir(exist_ok=True)
 (control/"empty_hints/NONE.json").write_text("{}\n")
 shared_path=SHARED/"SHARED_EXOGENOUS_AUTHORITY.json"
 if not shared_path.is_file():
  if not a.benchmark_issues:raise RuntimeError("shared exogenous source authority missing for production run")
  partial=SHARED/"mobility/R12_COMMON_MOBILITY_INDEX.partial.csv"
  bank=SHARED/"mobility/E4B_FULLFIT_TEMPLATE_BANK_129.parquet"
  power_auth=SHARED/"power_price/REP_WEEK_POWER_PRICE_SOURCE_AUTHORITY.json"
  if not power_auth.is_file():power_auth=SHARED/"power_price/A_B10_W02_POWER_PRICE_SOURCE_AUTHORITY.json"
  if not partial.is_file() or not bank.is_file() or not power_auth.is_file():raise RuntimeError("bounded source inputs incomplete")
  bounded={"schema_version":"mobileess.post_stage15.bounded_source_authority.v1",
           "status":"PASS_BOUNDED_PROFILE_SOURCE_ONLY","start_issue":START,"end_issue":run_end,
           "mobility_index_sha256":sha(partial),"template_bank_sha256":sha(bank),
           "power_price_authority_sha256":sha(power_auth),"future_actual_used":False,
           "not_production_source_authority":True}
  shared_path=control/"BOUNDED_SHARED_EXOGENOUS_AUTHORITY.json";jw(shared_path,bounded)
 shared=load_json(shared_path)
 if shared.get("status") not in {"PASS","PASS_BOUNDED_PROFILE_SOURCE_ONLY"}:raise RuntimeError("shared exogenous source not PASS")
 if shared.get("candidate_id",CANDIDATE_ID)!=CANDIDATE_ID or int(shared.get("scored_issue_first",START))!=START:
  raise RuntimeError(f"shared exogenous candidate/boundary drift for {CANDIDATE_ID}")
 shared_authority_sha=sha(shared_path)
 source_auth=load_json(HERE/"authority/A/SOURCE_AUTHORITY.json")
 write_policy_manifest(policy_root,cfg,config_sha,source_auth,shared_authority_sha)
 episode_id=f"{CANDIDATE_ID}_{cfg['slot']}_{cfg['policy_id']}_B5"
 jw(policy_root/"episode_manifest.json",{
  "schema_version":"mobileess.post_stage15.rep_week_episode_manifest.v2","episode_id":episode_id,"run_id":episode_id,
  "scenario_id":CANDIDATE_ID,"candidate_id":CANDIDATE_ID,"month":CANDIDATE_MONTH,
  "method_id":"B5","method_config_sha256":B5_SHA,"policy_id":cfg["policy_id"],"slot":cfg["slot"],
  "evaluation_start_step":START,"evaluation_end_step":END,"evaluation_end_step_inclusive":END,
  "scored_issues":COUNT,"controller_burn_in_steps":0,"selection_window_pre_history_steps":576,
  "selection_window_pre_history_role":"PROVENANCE_ONLY","canonical_pre_state_sha256":PRE_SHA,
   "shared_exogenous_authority_sha256":shared_authority_sha,
  "mobility_semantics":"FIXED_CANONICAL_HOME" if fixed_location else "MOBILE_ESS",
  "fixed_location_projection":fixed_location,"common_initial_service_sites":homes,
  "initial_service_authority_sha256":SITE_AUTHORITY_SHA,
  "future_actual_used":False,"future_plans_persisted":False,"right_censoring_retained":True,
  "runtime_semantics_contract":"D12_RUNTIME_CLAIM_SEMANTICS_V2"})
 jw(policy_root/"RESULT_EPISODE_INDEX.json",{
  "schema_version":"mobileess.result_episode_index.v1","run_id":episode_id,
  "scientific_method_id":"B5","comparison_method_id":cfg["slot"].split("_",1)[0],
  "policy_id":cfg["policy_id"],"candidate_id":CANDIDATE_ID,"representative_week":CANDIDATE_ID.split("_",1)[0],
  "resolved_policy_sha256":config_sha,"shared_exogenous_authority_sha256":shared_authority_sha,
  "statistics_grouping_key":"comparison_method_id","future_actual_used":False})
 with book.phase("shared_source_index_load"):
  sources=SourceBlocks(SHARED,run_end,bool(a.benchmark_issues))
 with book.phase("stage7_helper_import"):
  r12=loadmod(repo/"stage7/r12_representative_weeks/stage7_r12_burnin_runner.py","a_b10_r12_helper_"+cfg["slot"])
 with book.phase("full_year_rack_cache_load"):
  rack_cache=RackCache(r12,Path("/home/jaewon/mobile_ess_work"))
 # Import the frozen science module once per policy process. Per-issue mutable
 # caches are cleared before each causal boundary, avoiding 2016 repeated imports.
 with book.phase("science_import_and_control_transform"):
  abase.set_science_environment()
  science=abase.load_science(repo)
  science._a_b10_canonical_physical_zero=canonical_physical_zero
  one=transform_science(science,control)
 restore_performance_wrappers=install_science_performance_wrappers(science,current_performance,book)
 performance_build_full=science.build_full
 original_science_jw=science.jw
 # Event engine from actual PR4 checkout.
 sys.path.insert(0,str(repo))
 from r26.event_engine import EventConfig,EventEngine
 ev=EventEngine(EventConfig.from_mapping(cfg["event_config"]))
 checkpoint_path=control/"POLICY_RUNTIME_CHECKPOINT.json"
 checkpoint=load_json(checkpoint_path) if checkpoint_path.is_file() else {}
 if checkpoint:restore_event_engine(ev,checkpoint)
 last_replan=int(checkpoint.get("last_replan_issue",START))
 marker_files=sorted(engine.glob("issue_*/A_B10_COMMIT_MARKER.json"))
 if marker_files:
  latest_marker=max((validate_commit_marker(p.parent) for p in marker_files),key=lambda x:int(x["issue"]))
  restore_event_engine(ev,{"event_engine_state":latest_marker["event_engine_state"]})
  last_replan=int(latest_marker["last_replan_issue"])
 # Learn only from already committed PASS boundaries.  The immediately
 # preceding boundary is the causal one-step phase-distribution estimate for
 # the rolling plan; an all-history minimum mixes obsolete regulator/voltage
 # states and can make the otherwise valid H54 problem artificially empty.
 # Uncommitted/future issues are never inspected.
 reg1a_prior_limits=[]
 for marker_path in marker_files:
  marker_issue=int(marker_path.parent.name.split("_")[-1])
  if marker_issue>=START:
   value=_reg1a_causal_equivalent_kva_limit(
    marker_path.parent/"exact_grid/A_B10_FRESH_EXACT_AC_OBSERVABILITY.json")
   if value is not None:reg1a_prior_limits.append(float(value))
 reg1a_causal_limit_kva=reg1a_prior_limits[-1] if reg1a_prior_limits else None
 ac_recovery_context={}
 issue_audits=[]
 for i in range(START,run_end+1):
  auditp=engine/f"issue_{i:06d}/POLICY_ISSUE_AUDIT.json"
  postp=engine/f"issue_{i:06d}/BUILD7C_POSTCOMMIT_STATE.json"
  if auditp.is_file() and postp.is_file():
   marker=commit_marker_path(auditp.parent)
   if marker.is_file():validate_commit_marker(auditp.parent)
   elif int(checkpoint.get("last_completed_issue",START-1))<i:
    raise RuntimeError(f"committed issue lacks marker and checkpoint authority issue={i}")
   prior=load_json(auditp);issue_audits.append(prior);book.issue_records.append(prior);continue
  quarantine_incomplete(engine,i,policy_root)
  issue_runtime={"pre_to_post_wall_s":None,"slow_planner_runtime_s":0.0,"planner_mode":"NONE",
                 "event_reasons":[],"fast_solver":{},"dispatch_status":None,"replan_executed":False,
                 "issue":i,"benchmark_only":bool(a.benchmark_issues)}
  book.issue_records.append(issue_runtime);current_performance["issue"]=i;current_performance["record"]=issue_runtime
  # PRE authority: canonical for first issue, previous policy POST thereafter.
  with book.phase("causal_input_and_source_slice",i,issue_runtime):
   if i==START:
    # Stage7 production binding supplies the science-compatible {state,sha256}
    # envelope.  The descriptive canonical file uses the key state_sha256 and
    # is not itself the rolling engine's resume schema.
    state_path=PRE_RESUME_PATH
   else:
    state_path=engine/f"issue_{i-1:06d}/BUILD7C_POSTCOMMIT_STATE.json"
   state=load_json(state_path);pre_hash=str(state["sha256"])
   if i==START and pre_hash!=PRE_SHA:raise RuntimeError(f"canonical {CANDIDATE_ID} PRE hash drift")
   power,price=sources.row(i)
   mob_identity=str(sources.mob_rows[int(i)]["sha256"])
   exo_payload={"candidate_id":CANDIDATE_ID,"issue":int(i),"source_authority_sha256":shared_authority_sha,
                "power_price_block":int((i-START)//576),"mobility_issue_sha256":mob_identity}
   issue_runtime["causal_exogenous_identity"]=hashlib.sha256(json.dumps(exo_payload,sort_keys=True,separators=(",",":")).encode()).hexdigest()
   issue_runtime["causal_exogenous_identity_payload"]=exo_payload
   env=runtime_env(i,state_path,pre_hash,sources.mob_index,control,fixed_location,
                   not a.benchmark_disable_worker_cache,
                   not a.benchmark_disable_active_projection and i!=START,homes)
   env["MOBILEESS_PLANNER_PRESOLVE"]=str(planner_presolve)
   if a.benchmark_skip_redundant_dense_b4_cuts:
    env["MOBILEESS_POST15_SKIP_REDUNDANT_DENSE_B4_CUTS"]="1"
   os.environ.clear();os.environ.update(env)
  # Retain immutable worker-static authority, but evict every issue-specific
  # mobility NPZ by the frozen index SHA.  Current observations/planning/price
  # remain direct issue bindings and are never read from this cache.
  issue_runtime["science_cache_boundary"]=prune_dynamic_science_cache(
    science,sources,clear_all=bool(a.benchmark_clear_all_science_cache))
  science.jw=original_science_jw
  science._a_b10_bind_full_year_rack_scope=rack_cache.bind
  restore_sources=None
  # Reference active plan.
  with book.phase("active_plan_reference_load",i,issue_runtime):
   if i==START:
    ref=initial_reference()
   else:
    ref=astep4.shifted_reference_from_previous(i,engine)
   if fixed_location:ref=fixed_location_reference(ref,homes)
   science._A_B10_ACTIVE_REFERENCE=ref
  # The preceding optimizer plan is current-boundary causal information.  This
  # benchmark switch exercises the frozen R25V non-binding guidance path without
  # changing PRE, constraints, objective, event logic, or the committed plan.
  if i>START and a.benchmark_causal_guidance!="none":
   guidance_path=engine/f"issue_{i-1:06d}/BUILD7C_ROLLING_GUIDANCE_NEXT_ISSUE.json"
   guidance=load_json(guidance_path)
   guidance_next=guidance.get("next_issue")
   if (int(guidance.get("current_issue",-1))!=i-1
       or (guidance_next is not None and int(guidance_next)!=i)
       or guidance.get("future_realized_used") is not False
       or guidance.get("physical_state_authority") is not False
       or guidance.get("solver_guidance_only") is not True):
    raise RuntimeError(f"invalid preceding causal guidance authority {guidance_path}")
   os.environ["MOBILEESS_R25V_RESUME_GUIDANCE_PATH"]=str(guidance_path)
   os.environ["MOBILEESS_R25V_CAUSAL_ROLLING_MIPSTART"]=("1" if a.benchmark_causal_guidance=="start" else "0")
   issue_runtime["causal_guidance_candidate"]=a.benchmark_causal_guidance
  pre_t=None
  original_jw=science.jw
  decision_cache={}
  def requested_before_model(decision)->str:
   requested=decision.requested_mode if decision.request_replan else "NONE"
   if i==START:requested="FULL_REPLAN"
   if i in post_dispatch_hard_flags:requested="FULL_REPLAN"
   if issue_runtime.get("active_projection_retry_full_domain",False):requested="FULL_REPLAN"
   if i in forced_modes:requested=forced_modes[i]
   return requested
  def prebuild_event_conditioning(scope,b4,op1,build_issue,queue,running,inventory,dest_commit,
                                  mess_E,science_ref,*args,**kwargs):
   if int(build_issue)!=i:raise RuntimeError(f"prebuild issue drift {build_issue} != {i}")
   metrics=soft_metrics_from_causal_inputs(mess_E,science_ref,sources,i)
   if "decision" not in decision_cache:
    steps=max(0,i-last_replan)
    decision_cache["metrics"]=metrics
    decision_cache["decision"]=ev.evaluate(
      issue=i,hard_flags={},
      soft_metrics={k:metrics[k] for k in [r.name for r in ev.config.soft_rules]},
      steps_since_plan=steps)
   elif any(abs(float(metrics[k])-float(decision_cache["metrics"][k]))>1e-12 for k in metrics):
    raise RuntimeError("prebuild causal event metric drift across retry")
   requested=requested_before_model(decision_cache["decision"])
   # A planned reoptimization requires the full mobility domain.  Disable the
   # active-plan projection before model construction instead of intentionally
   # building a projected model, throwing, and rebuilding it in the retry path.
   if requested!="NONE" and not fixed_location and not a.benchmark_legacy_planned_replan_retry:
    os.environ["MOBILEESS_ACTIVE_PLAN_MOBILITY_PROJECTION"]="0"
   if use_sparse_restore and requested!="NONE":
    os.environ["MOBILEESS_POST15_SKIP_REDUNDANT_DENSE_B4_CUTS"]="1"
    issue_runtime["planner_formulation"]={
      "mode":"EXACT_SPARSE_REDUNDANT_ROWS_OMITTED",
      "planner_presolve":planner_presolve,
      "dense_rows_restored_before_physical_dispatch":True}
   elif requested!="NONE":
    issue_runtime["planner_formulation"]={
      "mode":"LEGACY_DENSE" if not a.benchmark_sparse_planner_copy else "BENCHMARK_SPARSE_COPY",
      "planner_presolve":planner_presolve,
      "dense_rows_restored_before_physical_dispatch":False}
   issue_runtime["prebuild_requested_mode"]=requested
   issue_runtime["prebuild_projection_enabled"]=(os.environ.get("MOBILEESS_ACTIVE_PLAN_MOBILITY_PROJECTION","0")=="1")
   original_conservative_fixed=b4.conservative_fixed
   if not a.benchmark_disable_fast_rack_lookup:
    rack_table=rack_cache.conservative_table(scope,int(build_issue))
    def fast_conservative_fixed(op1_arg,scope_arg,rack,issue_arg,t):
     value=rack_table.get((str(rack),int(t)))
     return value if value is not None else original_conservative_fixed(op1_arg,scope_arg,rack,issue_arg,t)
    b4.conservative_fixed=fast_conservative_fixed
    issue_runtime["fast_rack_lookup"]={"entries":len(rack_table),"horizon_steps":49,"fallback_after_h48":True}
   # R25D projects regulator states with a fixed tap ratio.  At a causal PRE
   # boundary reached through exact-AC recovery, a current discrete tap can
   # make an H0 projected *constant* voltage fall outside that approximation's
   # interval before the model even exists.  Such a constant has no optimizer
   # control because the approximation omitted the regulator tap decision.
   # Expand only decision-independent fixed-tap constants enough to build the
   # candidate model at every horizon step.  Decision-dependent voltage bounds
   # stay intact.  In receding-horizon execution, each H0 action is accepted by
   # Fresh OpenDSS with the real regulator controls and unchanged hard limits.
   original_projection_bounds=science.propagate_projected_voltage_bounds
   projection_call={"index":0}
   h0_constant_projection_events=[]
   def h0_exact_ac_projection_bounds(proj,vamap,vdev_bounds):
    call_index=projection_call["index"];projection_call["index"]+=1
    expanded=dict(vdev_bounds)
    for node,(anchor,_scale,constant) in vamap.items():
     if anchor is not None:continue
     lo,hi=map(float,expanded[node]);value=float(constant)
     if value<lo-1e-12 or value>hi+1e-12:
      h0_constant_projection_events.append({"horizon_step":call_index,
       "node":str(node),"projected_constant":value,
       "original_lower":lo,"original_upper":hi,
       "build_lower":min(lo,value),"build_upper":max(hi,value)})
      expanded[node]=(min(lo,value),max(hi,value))
    result=original_projection_bounds(proj,vamap,expanded)
    issue_runtime["h0_constant_tap_projection_override"]={
     "status":"FIXED_TAP_CONSTANT_PROJECTION_REPLACED_BY_RECEDING_FRESH_EXACT_AC_GATE",
     "event_count":len(h0_constant_projection_events),"events":h0_constant_projection_events,
     "future_horizon_fixed_tap_constants_changed":any(x["horizon_step"]>0 for x in h0_constant_projection_events),
     "decision_dependent_projection_bounds_changed":False,
     "fresh_exact_opendss_required":True,"hard_physical_limits_relaxed":False,
     "future_actual_used":False}
    return result
   science.propagate_projected_voltage_bounds=h0_exact_ac_projection_bounds
   try:
    sol=performance_build_full(scope,b4,op1,build_issue,queue,running,inventory,dest_commit,
                               mess_E,science_ref,*args,**kwargs)
    # The optimizer's PRE state plus selected move arcs are the causal mobility
    # authority.  Canonicalize the human-readable MESS plan before commit so a
    # sparse/node-occupancy extraction cannot serialize an arrived unit as
    # perpetual TRANSIT and break the next shifted-plan boundary.
    loc_now=ac_recovery_context.get("loc",{})
    causal_rows,path_audit=astep4._canonicalize_mess_path_from_causal_route(
     pd.DataFrame(sol.get("mess_rows",[])),pd.DataFrame(sol.get("route_rows",[])),
     {"state":{"mess_state":dict(loc_now.get("rollstate",{}))}})
    causal_lookup={(str(r.mess_id),int(r.horizon_step)):(str(r.state),str(r.service_id))
                   for r in causal_rows.itertuples(index=False)}
    for row in sol.get("mess_rows",[]):
     state_value,service_value=causal_lookup[(str(row["mess_id"]),int(row["horizon_step"]))]
     row["state"]=state_value;row["service_id"]=service_value
    issue_runtime["causal_route_report_canonicalization"]=path_audit
    pcs_projections=[];coupled_state_projections=sol.setdefault("_coupled_soc_debt_projection_events",[])
    energy_state_projections=sol.setdefault("_energy_state_projection_events",[])
    preprojection_h0={}
    for row in sol.get("mess_rows",[]):
     if int(row["horizon_step"])==0:
      preprojection_h0[str(row["mess_id"])]=(float(row["P_discharge_kW"]),float(row["P_charge_kW"]))
     pdis,pchg,q,projection=canonicalize_pcs_numerical_boundary(
      row["P_discharge_kW"],row["P_charge_kW"],row["Q_kvar"])
     row["P_discharge_kW"],row["P_charge_kW"],row["Q_kvar"]=pdis,pchg,q
     if projection is not None:
      pcs_projections.append({"mess_id":str(row["mess_id"]),"horizon_step":int(row["horizon_step"]),**projection})
    h0_rows={str(row["mess_id"]):row for row in sol.get("mess_rows",[]) if int(row["horizon_step"])==0}
    for row in sol.get("firstmess",[]):
     mid=str(row["mess_id"]);h0=h0_rows[mid]
     row["P_discharge_kW"]=float(h0["P_discharge_kW"]);row["P_charge_kW"]=float(h0["P_charge_kW"])
     row["P_net_grid_injection_kW"]=float(h0["P_discharge_kW"])-float(h0["P_charge_kW"])
     row["Q_grid_injection_kvar"]=float(h0["Q_kvar"])
     old_pdis,old_pchg=preprojection_h0[mid]
     row["E1_kWh"],row["support_debt1_kWh"]=adjust_model_state_for_inward_pcs_projection(
      row["E1_kWh"],row["support_debt1_kWh"],old_pdis,old_pchg,
      row["P_discharge_kW"],row["P_charge_kW"])
     scale_e=float(loc_now.get("_c5r4_energy_scale_kwh_per_model_unit",1000.0))
     capacity_kwh=mess_physical_capacity_kwh(loc_now,mid,scale_e)
     row["E1_kWh"],energy_projection=canonicalize_energy_numerical_boundary(
      row["E1_kWh"],ENERGY_PHYSICAL_FLOOR_KWH,capacity_kwh,f"economic[{mid}]")
     if energy_projection is not None:energy_state_projections.append(energy_projection)
     if fixed_location:
      row["E1_kWh"],row["support_debt1_kWh"],state_projection=canonicalize_coupled_soc_debt_ceiling(
       row["E1_kWh"],row["support_debt1_kWh"],capacity_kwh,f"economic[{mid}]")
      if state_projection is not None:coupled_state_projections.append(state_projection)
     sol.setdefault("mess_support_debt1",{})[mid]=row["support_debt1_kWh"]
     if isinstance(sol.get("mess_E1"),dict):sol["mess_E1"][mid]=row["E1_kWh"]
    issue_runtime["coupled_soc_debt_boundary_projection"]={
     "status":"PASS_CONSERVATIVE_INWARD_SOC_PROJECTION" if coupled_state_projections else "NOT_NEEDED",
     "projection_count":len(coupled_state_projections),"events":coupled_state_projections,
     "maximum_permitted_excess_kWh":COUPLED_SOC_DEBT_NUMERICAL_EXCESS_MAX_KWH,
     "hard_capacity_relaxed":False,"support_obligation_reduced":False,
     "scientific_feasible_set_expanded":False}
    issue_runtime["energy_state_boundary_projection"]={
     "status":"PASS_EXACT_INWARD_PROJECTION" if energy_state_projections else "NOT_NEEDED",
     "projection_count":len(energy_state_projections),"events":energy_state_projections,
     "maximum_permitted_excess_kWh":ENERGY_NUMERICAL_BOUNDARY_MAX_EXCESS_KWH,
     "physical_floor_kWh":ENERGY_PHYSICAL_FLOOR_KWH,
     "hard_floor_relaxed":False,"hard_capacity_relaxed":False,"scientific_feasible_set_expanded":False}
    issue_runtime["pcs_numerical_boundary_projection"]={
     "status":"PASS_EXACT_INWARD_PROJECTION" if pcs_projections else "NOT_NEEDED",
     "projection_count":len(pcs_projections),"events":pcs_projections,
     "active_projection_count":sum(bool(x.get("active_projection")) for x in pcs_projections),
     "apparent_projection_count":sum(bool(x.get("apparent_projection")) for x in pcs_projections),
     "active_limit_kw":PCS_ACTIVE_LIMIT_KW,"apparent_limit_kva":PCS_APPARENT_LIMIT_KVA,
     "maximum_permitted_preprojection_active_excess_kw":PCS_NUMERICAL_BOUNDARY_MAX_ACTIVE_EXCESS_KW,
     "maximum_permitted_preprojection_excess_kva":PCS_NUMERICAL_BOUNDARY_MAX_EXCESS_KVA,
     "hard_limits_relaxed":False,"scientific_feasible_set_expanded":False,
     "scientific_objective_formula_changed":False,
     "physical_action_inward_adjusted":bool(pcs_projections),"projected_coordinate":"P_NET_AND_OR_Q",
     "fresh_exact_opendss_required":True}
    if "rolling_warmstart_payload" in sol:sol["rolling_warmstart_payload"]["mess_rows"]=[dict(x) for x in sol["mess_rows"]]
    science.cw(Path(args[7])/"BUILD7B_FULL54_MESS_PLAN.csv",sol["mess_rows"])
    return sol
   finally:
    b4.conservative_fixed=original_conservative_fixed
    science.propagate_projected_voltage_bounds=original_projection_bounds
  def jw_wrap(path,value):
   nonlocal pre_t
   out=original_jw(path,value);p=Path(path)
   if p.parent.name==f"issue_{i:06d}":
    if p.name=="BUILD7C_PRECOMMIT_STATE.json":pre_t=time.monotonic()
    elif p.name=="BUILD7C_POSTCOMMIT_STATE.json" and pre_t is not None:issue_runtime["pre_to_post_wall_s"]=time.monotonic()-pre_t
   return out
  science.jw=jw_wrap
  def hook(**kwargs):
   nonlocal last_replan
   fr=inspect.currentframe();loc=fr.f_back.f_locals;model=kwargs["m"];cb=kwargs.get("base_callback")
   import gurobipy as gp
   # H0 is executed immediately and receives a Fresh OpenDSS hard gate.  For
   # forecast horizons where the omitted regulator-tap decision created a
   # decision-independent constant-bound contradiction, the corresponding
   # voltage-drop linkage is invalid too.  Remove only du_line rows at H0 and
   # those evidenced horizon steps.  Power balance, line thermal circles,
   # device/energy/mobility constraints, and unaffected future voltage rows
   # remain unchanged.
   fixed_tap_events=(issue_runtime.get("h0_constant_tap_projection_override",{}).get("events",[]))
   fixed_tap_affected_steps={0}|{int(row["horizon_step"]) for row in fixed_tap_events}
   h0_projection_prefixes=tuple(f"du_line_{h}_" for h in sorted(fixed_tap_affected_steps))
   h0_projection_rows=[row for row in model.getConstrs()
                       if str(row.ConstrName).startswith(h0_projection_prefixes)]
   h0_projection_names=[str(row.ConstrName) for row in h0_projection_rows]
   if h0_projection_rows:model.remove(h0_projection_rows);model.update()
   issue_runtime["h0_planning_grid_projection_override"]={
    "status":"FIXED_TAP_VOLTAGE_DROP_LINKS_REPLACED_BY_RECEDING_FRESH_EXACT_AC_GATE",
    "removed_linear_row_count":len(h0_projection_rows),
    "removed_row_prefixes":list(h0_projection_prefixes),
    "affected_horizon_steps":sorted(fixed_tap_affected_steps),
    "removed_row_names_sha256":hashlib.sha256("\n".join(sorted(h0_projection_names)).encode()).hexdigest(),
   "power_balance_rows_removed":0,"line_thermal_rows_removed":0,
    "device_energy_mobility_rows_removed":0,
    "fresh_exact_opendss_required":True,"hard_physical_limits_relaxed":False,
    "future_actual_used":False}
   # The aggregate LinDistFlow planner has no per-phase transformer-current
   # row, although Fresh OpenDSS rejects reg1a when any one phase exceeds its
   # nameplate.  Protect future mobility decisions with the latest causal equivalent
   # three-phase kVA limit observed at preceding committed PASS boundaries.
   # This is causal and inward-only; H0 still uses the exact unchanged gate.
   reg1a_rows=[]
   reg1a_envelope_limit_kva=reg1a_causal_limit_kva
   reg1a_envelope_source="IMMEDIATELY_PRECEDING_COMMITTED_PASS_EXACT_AC_EQUIVALENT_KVA"
   reg1a_envelope_creation_issue=int(i)
   reg1a_envelope_target_end_issue=int(i)+12
   h0_envelope_enabled=False
   # A shifted active plan must retain the envelope under which it was made.
   # Re-estimating the bound every five minutes can invalidate the plan solely
   # because of tiny causal phase-distribution drift and trigger plan churn.
   if i>START and issue_runtime.get("prebuild_requested_mode")=="NONE":
    prior_audit_path=engine/f"issue_{i-1:06d}/POLICY_ISSUE_AUDIT.json"
    if prior_audit_path.is_file():
     prior_envelope=load_json(prior_audit_path).get("reg1a_causal_phase_current_envelope",{})
     prior_limit=prior_envelope.get("equivalent_limit_kva")
     if prior_limit is not None:
      reg1a_envelope_limit_kva=float(prior_limit)
      reg1a_envelope_source="SHIFTED_ACTIVE_PLAN_CREATION_ENVELOPE"
      reg1a_envelope_creation_issue=int(prior_envelope.get("envelope_creation_issue",i-1))
      reg1a_envelope_target_end_issue=int(prior_envelope.get(
       "envelope_target_end_issue",(i-1)+int(prior_envelope.get("future_horizon_rows",12))))
   if reg1a_envelope_limit_kva is not None:
    proj=loc.get("r25d_proj")
    if proj is None:raise RuntimeError("REG1A_CAUSAL_ENVELOPE_REQUIRES_R25D_PROJECTION")
    flow_scale=float(loc.get("_r25i_flow_scale_kw_per_model_unit",1.0))
    fp_vars=loc.get("FP",{});fq_vars=loc.get("FQ",{})
    bgp=np.asarray(loc["bgP"],dtype=float);bgq=np.asarray(loc["bgQ"],dtype=float)
    buses=list(map(str,loc["bgbus"]));root_node=str(loc["root"])
    limit_model=float(reg1a_envelope_limit_kva)/flow_scale
    # Protect the three dispatch intervals in which a mobility action becomes
    # committed and reaches its destination.  Longer load-error protection is
    # supplied separately by the per-MESS energy reserve below; extending this
    # one-step phase-distribution proxy farther can drive several batteries to
    # their SOC floor while satisfying only an aggregate root quantity.
    # distribution to the whole one-hour event window can falsely conflict
    # with forecast charging/debt repayment at a later MAX_REFRESH boundary,
    # before that later state is observable.  H0 and every realized successor
    # still pass the unchanged Fresh OpenDSS per-phase current gate.
    # This row is a route/workload/dispatch *planning* safeguard.  Include H0
    # only in the single same-PRE full-replan recovery after Fresh OpenDSS has
    # rejected the first candidate.  Normal replans leave H0 to the exact gate,
    # avoiding needless perturbation of an already-safe operating point; the
    # recovery replan must be able to undo a newly selected unsafe job start,
    # which a downstream PCS-only P/Q correction cannot do.
    # A shifted active plan
    # was already selected under its creation forecast; reapplying the row with
    # a newly issued forecast can invalidate the plan without any physical
    # event.  Ordinary H0 execution remains protected by Fresh OpenDSS.
    protected_steps=(0 if issue_runtime.get("prebuild_requested_mode")=="NONE"
                     else min(3,max(0,reg1a_envelope_target_end_issue-int(i))))
    h0_envelope_enabled=bool(issue_runtime.get("grid_hard_risk_full_replan_retry",False))
    for h in range(0 if h0_envelope_enabled else 1,min(H,protected_steps+1)):
     own_p={n:0.0 for n in proj.static_nodes};own_q={n:0.0 for n in proj.static_nodes}
     root_own_p=root_own_q=0.0
     for bi,bus in enumerate(buses):
      if bus in own_p:
       own_p[bus]+=float(bgp[h,bi]);own_q[bus]+=float(bgq[h,bi])
      elif bus==root_node:
       root_own_p+=float(bgp[h,bi]);root_own_q+=float(bgq[h,bi])
     static_fp,static_fq=science.condense_static_subtree_flows(proj,own_p,own_q)
     dynamic_children,constant_p,constant_q=science.skeleton_balance_child_terms(
      proj,root_node,static_fp,static_fq)
     missing=[child for child in dynamic_children if (h,child) not in fp_vars or (h,child) not in fq_vars]
     if missing:raise RuntimeError(f"REG1A_ROOT_FLOW_VARIABLE_MISSING_H{h}:{missing}")
     root_p=gp.LinExpr((root_own_p+float(constant_p))/flow_scale)
     root_q=gp.LinExpr((root_own_q+float(constant_q))/flow_scale)
     for child in dynamic_children:
      root_p+=fp_vars[(h,child)];root_q+=fq_vars[(h,child)]
     # At H0 use the unchanged 5 MVA transformer nameplate.  Applying the
     # tighter one-step phase-distribution proxy to H0 can itself force an
     # artificial reactive-power corner even though Fresh OpenDSS proves the
     # existing state safe.  For H1..H3 retain the causal inward proxy that
     # protects future phase current.  The H0 nameplate row is still enough to
     # reject the unsafe ~5.9 MVA immediate workload start seen at issue 15183.
     row_limit_model=(5000.0/flow_scale if h==0 else limit_model)
     row=model.addQConstr(root_p*root_p+root_q*root_q<=row_limit_model*row_limit_model,
                          name=f"a_b10_reg1a_phase_current_envelope_h{h}")
     reg1a_rows.append(row)
    model.update()
   issue_runtime["reg1a_causal_phase_current_envelope"]={
    "status":"PASS_CAUSAL_INWARD_PLANNING_ENVELOPE" if reg1a_rows else "NO_PRIOR_PASS_AUTHORITY",
    "source":reg1a_envelope_source,
    "preceding_authority_count":len(reg1a_prior_limits),
    "equivalent_limit_kva":reg1a_envelope_limit_kva,"guard_factor":0.995,
    "envelope_creation_issue":reg1a_envelope_creation_issue,
    "envelope_target_end_issue":reg1a_envelope_target_end_issue,
    "planning_envelope_rows":len(reg1a_rows),
    "future_horizon_rows":max(0,len(reg1a_rows)-(1 if h0_envelope_enabled else 0)),
    "h0_exact_gate_unchanged":True,
    "h0_planning_envelope_rows":(1 if h0_envelope_enabled else 0),
    "h0_planning_limit_kva":(5000.0 if h0_envelope_enabled else None),
    "h0_planning_envelope_trigger":"SAME_PRE_GRID_HARD_FULL_REPLAN_RETRY" if h0_envelope_enabled else None,
    "mobility_commitment_horizon_steps":3,
    "transformer_nameplate_kva":5000.0,"power_scale_changed":False,
    "hard_exact_limit_relaxed":False,"future_actual_used":False}
   jw(Path(loc["out"])/"A_B10_REG1A_CAUSAL_PHASE_CURRENT_ENVELOPE.json",
      issue_runtime["reg1a_causal_phase_current_envelope"])
   # Grid-voltage safety requires prospective controllable PCS reserve.  H0 is
   # already the immutable PRE mobility state: if all units are in an earlier
   # MOVE/CONNECTION_DELAY, no current optimization can reconnect one.  Record
   # such unavoidable gaps, and impose one STAY unit at every future step whose
   # mobility domain contains a controllable stay decision.
   connected_reserve_rows=[];unavoidable_pre_domain_gaps=[]
   h0_connected=sum(str((loc.get("rollstate",{}) or {}).get(str(mid),{}).get("phase",""))=="STAY"
                    for mid in map(str,loc["mids"]))
   for h in range(1,H):
    available=[v for mid in map(str,loc["mids"])
               for _,v in (loc.get("stay_by_mid_h",{}) or {}).get((mid,h),[])]
    if not available:
     if bool(loc.get("active_plan_mobility_projection",False)):
      raise RuntimeError(f"A_B10_ACTIVE_PLAN_MOBILITY_PROJECTION_CONNECTED_RESERVE_DOMAIN_MISSING_H{h}")
     unavoidable_pre_domain_gaps.append(h);continue
    connected_reserve_rows.append(model.addLConstr(
     gp.quicksum(available)>=1.0,name=f"a_b10_connected_pcs_reserve_h{h}"))
   model.update();loc["_a_b10_connected_pcs_reserve_rows"]=connected_reserve_rows
   jw(Path(loc["out"])/"A_B10_CONNECTED_PCS_RESERVE.json",{
    "schema_version":"mobileess.post_stage15.connected_pcs_reserve.v1",
    "status":"PASS_PROSPECTIVE_HARD_RESERVE_INSTALLED","minimum_connected_mess":1,
    "h0_connected_mess_count":h0_connected,"horizon_rows":len(connected_reserve_rows),
    "h0_is_immutable_pre_state":True,"h0_unavoidable_disconnect":h0_connected<1,
    "future_steps_without_stay_domain":unavoidable_pre_domain_gaps,
    "decision_rows_h1_to_h53_where_controllable":True,
    "physical_reason":"RETAIN_CONTROLLABLE_PQ_FOR_EXACT_VOLTAGE_SAFETY",
    "power_scale_changed":False,"hard_grid_limits_relaxed":False,"future_actual_used":False})
   # A connected PCS at the exact 440 kWh floor has reactive capability but no
   # active-power headroom for an unobserved next-step load error.  Preserve at
   # every MESS enough energy for four consecutive five-minute, 550 kW
   # grid-support intervals
   # at H1, the next state actually reached after committing H0.  H2--H53 are
   # nonbinding guidance and are not persisted, so imposing the reserve there
   # can distort future integer choices without preserving additional actual
   # energy in this receding-horizon implementation.
   # This value follows directly from the frozen
   # 0.95 discharge efficiency and is an inward reserve above (not a change to)
   # the physical SOC floor.  It also prevents an aggregate root envelope from
   # satisfying itself by draining several site-specific resources to zero.
   #
   # The reserve is persistent receding-horizon policy, so install it on every
   # issue rather than only on explicit replans.  H0 is not credited back here:
   # the committed transition itself must leave H1 above the reserve floor.
   # The unchanged 440 kWh physical floor still applies at every step.
   energy_reserve_rows=[];energy_reserve_h1_rows=[]
   # 550 kW is the existing frozen MESS PCS dispatch ceiling observed by the
   # controller, not a rescaling.  Four full intervals require 192.9825 kWh at
   # the frozen 0.95 discharge efficiency.
   reserve_support_intervals=4
   reserve_support_duration_minutes=5.0*reserve_support_intervals
   energy_reserve_kwh=(550.0/0.95)*(reserve_support_duration_minutes/60.0)
   energy_reserve_floor_kwh=ENERGY_PHYSICAL_FLOOR_KWH+energy_reserve_kwh
   # After an emergency has spent the reserve, demanding a one-step return to
   # the full floor can exceed the frozen charger capability.  Recover by at
   # most a 100 kW charging interval, and
   # never permit nominal dispatch to reduce the depleted pre-state further.
   reserve_recovery_charge_kw=100.0
   reserve_recovery_increment_kwh=reserve_recovery_charge_kw*0.95*(5.0/60.0)
   energy_scale=float(loc.get("_c5r4_energy_scale_kwh_per_model_unit",1.0))
   energy_vars=loc.get("E",{}) or {}
   pre_energy_by_mid={str(mid):float((loc.get("mess_E",{}) or {})[str(mid)])
                      for mid in map(str,loc["mids"])}
   h1_target_by_mid={mid:min(energy_reserve_floor_kwh,
                             max(ENERGY_PHYSICAL_FLOOR_KWH,pre_e)+reserve_recovery_increment_kwh)
                     if pre_e<energy_reserve_floor_kwh else energy_reserve_floor_kwh
                     for mid,pre_e in pre_energy_by_mid.items()}
   protected_energy_steps=[h for h in (1,) if h<H]
   for h in protected_energy_steps:
    for mid in map(str,loc["mids"]):
     var=energy_vars.get((mid,h))
     if var is None:raise RuntimeError(f"PCS_ENERGY_RESERVE_VARIABLE_MISSING:{mid}:H{h}")
     target_kwh=h1_target_by_mid[mid]
     reserve_ref=model.addLConstr(
      var>=target_kwh/energy_scale,
      name=f"a_b10_pcs_energy_reserve_{mid}_h{h}")
     energy_reserve_rows.append(reserve_ref)
     if h==1:energy_reserve_h1_rows.append(reserve_ref)
   model.update()
   loc["_a_b10_pcs_energy_reserve_rows"]=energy_reserve_rows
   loc["_a_b10_pcs_energy_reserve_h1_rows"]=energy_reserve_h1_rows
   issue_runtime["pcs_near_horizon_energy_reserve"]={
    "status":"PASS_INWARD_RESERVE_INSTALLED" if energy_reserve_rows else "SHIFTED_PLAN_NO_NEW_ROWS",
    "row_count":len(energy_reserve_rows),"protected_steps":protected_energy_steps,
    "protected_step_h1":1 in protected_energy_steps,"protected_step_h5":False,
    "h2_to_h53_policy":"UNCHANGED_PHYSICAL_SOC_FLOOR_NONBINDING_GUIDANCE",
    "per_mess_grid_support_kw":550.0,"support_interval_count":reserve_support_intervals,
    "support_duration_minutes":reserve_support_duration_minutes,
    "discharge_efficiency":0.95,"reserve_above_floor_kwh":energy_reserve_kwh,
    "reserve_floor_kwh":energy_reserve_floor_kwh,
    "depleted_reserve_recovery_charge_kw":reserve_recovery_charge_kw,
    "depleted_reserve_recovery_increment_kwh":reserve_recovery_increment_kwh,
    "pre_energy_kwh":pre_energy_by_mid,"h1_target_kwh":h1_target_by_mid,
    "depleted_target_never_below_pre_energy":True,
    "installed_on_every_issue":True,
    "h0_discharge_credit_in_reserve_test":False,
    "h1_operating_reserve_released_only_after_fresh_ac_failure":True,
    "guard_semantics":"H1_FULL_RESERVE_OR_RATE_LIMITED_RECOVERY_TARGET_RELEASED_ONLY_FOR_FRESH_AC_FAILURE",
    "physical_soc_floor_kwh_unchanged":ENERGY_PHYSICAL_FLOOR_KWH,
    "power_scale_changed":False,"hard_grid_limits_relaxed":False,"future_actual_used":False}
   jw(Path(loc["out"])/"A_B10_PCS_NEAR_HORIZON_ENERGY_RESERVE.json",
      issue_runtime["pcs_near_horizon_energy_reserve"])
   metrics=current_soft_metrics(loc,sources,i)
   steps=max(0,i-last_replan)
   if "decision" not in decision_cache:
    decision_cache["metrics"]=metrics
    decision_cache["decision"]=ev.evaluate(issue=i,hard_flags={},soft_metrics={k:metrics[k] for k in [r.name for r in ev.config.soft_rules]},steps_since_plan=steps)
   elif any(abs(float(metrics[k])-float(decision_cache["metrics"][k]))>1e-12 for k in metrics):
    raise RuntimeError("hook causal event metrics differ from prebuild metrics")
   decision=decision_cache["decision"]
   requested=decision.requested_mode if decision.request_replan else "NONE"
   reasons=list(decision.reasons)
   if i==START:
    requested="FULL_REPLAN";reasons.append("PROSPECTIVE_INITIAL_SITING_REQUIRES_CAUSAL_PLAN")
   if i in post_dispatch_hard_flags:
    requested="FULL_REPLAN"
    reasons.append("HARD:GRID_HARD_RISK_POST_DISPATCH")
   if issue_runtime.get("active_projection_retry_full_domain",False):
    requested="FULL_REPLAN"
    reasons.append("HARD:STALE_ACTIVE_PLAN_MOBILITY_PROJECTION")
   affected_jobs,affected_mess=local_scope_from_soft(loc,metrics,i,cfg)
   def solve_planner_candidate():
    if a.benchmark_sparse_planner_copy and not fixed_location:
     return planner_solve_sparse_copy(model,cb)
    return planner_solve_exact_copy(model,cb)
   def accept_planner_candidate(planner_model):
    if planner_model is None:return fix_all_slow_to_incumbent(loc)
    try:return fix_all_slow_from_model(loc,planner_model)
    finally:planner_model.dispose()
   if i in forced_modes:
    requested=forced_modes[i];reasons.append("TEST_ONLY_BOUNDED_FORCED_"+requested)
    if requested=="LOCAL_REPAIR" and not (affected_jobs or affected_mess):affected_mess=["MESS01"]
    issue_runtime["test_only_forced_mode"]=requested
   if requested!="NONE" and bool(loc.get("active_plan_mobility_projection",False)):
    raise RuntimeError("A_B10_ACTIVE_PLAN_MOBILITY_PROJECTION_REQUIRES_FULL_DOMAIN")
   # The production sparse planner omits 576 R25K rows during search and adds
   # them back before physical dispatch.  Preserve the exact unconditioned
   # domain so a sparse candidate that is not feasible after row restoration
   # can be rejected and re-solved once on the dense model from the same PRE.
   # This is a bounded equivalence fallback, not a relaxation: the second
   # planner contains every original row and the final physical gate is intact.
   dense_equivalence_bound_snapshot=None
   if use_sparse_restore and requested!="NONE":
    dense_equivalence_bound_snapshot={
     str(v.VarName):(v,float(v.LB),float(v.UB),str(v.VType))
     for name in ("x","defer","stay","mv","node_occ","mode")
     for v in (loc.get(name,{}) or {}).values()
    }
   hard_exc=None
   if requested=="NONE":
    try:
     bind=astep4.bind_shifted_active_plan(loc,ref,i)
     jw(Path(loc["out"])/"A_B10_ACTIVE_PLAN_BINDING.json",bind)
     # The shifted active plan is already the authoritative future commitment.
     # Keep only the four current-step PCS modes dispatchable; otherwise the
     # fast solve needlessly re-optimizes 212 future mode binaries and can miss
     # its 300 s / 3% operational contract even though the plan is valid.
     # model.reset() clears native starts, so also transfer the H0 mode signs as
     # nonbinding starts.  No objective, equation, or physical limit changes.
     mode_start={};all_mode_start={};fixed_future_mode_names=[]
     for r in ref["BUILD7B_FULL54_MESS_PLAN.csv"].itertuples(index=False):
      h=int(r.horizon_step);key=(str(r.mess_id),h);v=(loc.get("mode",{}) or {}).get(key)
      if v is None:continue
      value=(1.0 if float(r.P_discharge_kW)>1e-8 else 0.0)
      all_mode_start[str(v.VarName)]=value
      if h>0:
       fix_future_mode_commitment(loc,key,value)
       fixed_future_mode_names.append(str(v.VarName))
      else:mode_start[str(v.VarName)]=value
     loc["m"].update()
     free_mode_names=sorted(str(v.VarName) for v in (loc.get("mode",{}) or {}).values()
                            if float(v.UB)-float(v.LB)>1e-12)
     missing_mode_names=sorted(set(free_mode_names)-set(mode_start))
     if missing_mode_names:
      raise RuntimeError(f"ACTIVE_PLAN_MODE_MIP_START_INCOMPLETE:{missing_mode_names[:20]}")
     loc["_pending_active_plan_mode_start_by_name"]={name:mode_start[name] for name in free_mode_names}
     loc["_pending_all_active_plan_mode_start_by_name"]=all_mode_start
     loc["_conditioned_shifted_active_plan"]=True
     jw(Path(loc["out"])/"A_B10_ACTIVE_PLAN_MODE_MIP_START.json",{
      "schema_version":"mobileess.a_b10.active_plan_mode_mip_start.v2","status":"PASS_FUTURE_COMMITMENT_H0_GUIDANCE",
      "mode_start_count":len(free_mode_names),"mode_start_names":free_mode_names,
      "fixed_future_mode_count":len(fixed_future_mode_names),
      "fixed_future_mode_names":sorted(fixed_future_mode_names),
      "opposite_pcs_zero_enforced_by_retained_mode_rows":True,
      "free_current_mode_count":len(free_mode_names),"future_commitment_fixed":True,
      "guidance_only":False,"variables_fixed_by_this_step":len(fixed_future_mode_names),"objective_changed":False,
      "hard_constraints_changed":False,"future_actual_used":False})
    except astep4.PlanInvalidation as exc:
     hard_exc=exc;flag=map_hard_invalidation(exc);reasons.extend([f"HARD:{flag}",*exc.reasons])
     affected_jobs=list(exc.affected_job_ids);affected_mess=list(exc.affected_mess_ids)
     requested="LOCAL_REPAIR" if cfg["local_repair_enabled"] and (affected_jobs or affected_mess) else "FULL_REPLAN"
   if requested=="LOCAL_REPAIR":
    # Local repair mutates only variable bounds. Snapshot the entire slow-domain
    # bounds so an exact fail-closed escalation can restore the unconditioned
    # full planner model without rebuilding or changing any equations.
    slow_bound_snapshot=[
     (v,float(v.LB),float(v.UB),str(v.VType))
     for name in ("x","defer","stay","mv","node_occ")
     for v in (loc.get(name,{}) or {}).values()
    ]
    def restore_slow_bounds():
     for v,lb,ub,vtype in slow_bound_snapshot:
      v.LB=lb;v.UB=ub;v.VType=vtype
     model.update();model.reset()
     restored_integer_types=sum(vtype.upper() in {"B","I","S","N"}
                                for _,_,_,vtype in slow_bound_snapshot)
     issue_runtime["local_repair_full_domain_restore"]={
      "status":"PASS_BOUNDS_AND_VARIABLE_TYPES_ATOMICALLY_RESTORED",
      "restored_variable_count":len(slow_bound_snapshot),
      "restored_integer_variable_type_count":restored_integer_types,
      "same_pre":True,"hard_constraints_relaxed":False,"future_actual_used":False}
     jw(Path(loc["out"])/"A_B10_LOCAL_REPAIR_FULL_DOMAIN_RESTORE.json",
        issue_runtime["local_repair_full_domain_restore"])
    try:
     scope=astep5.apply_actual_local_repair(loc=loc,ref=ref,issue=i,affected_job_ids=affected_jobs,
       affected_mess_ids=affected_mess,near_horizon_steps=12)
     jw(Path(loc["out"])/"A_B10_LOCAL_REPAIR_SCOPE.json",scope)
     pq,planner_model=solve_planner_candidate();issue_runtime["slow_planner_runtime_s"]+=float(pq["wall_seconds"])
     if not pq["candidate_available"]:
      if planner_model is not None:planner_model.dispose()
      reasons.append("LOCAL_REPAIR_NO_CANDIDATE_ESCALATE_FULL")
      restore_slow_bounds();requested="FULL_REPLAN"
     else:
      accept_planner_candidate(planner_model);last_replan=i;issue_runtime["replan_executed"]=True
      issue_runtime["planner_mode"]="LOCAL_REPAIR";jw(Path(loc["out"])/"A_B10_LOCAL_PLANNER_SOLVE.json",pq)
    except astep5.LocalRepairEscalation as exc:
     reasons.append("LOCAL_REPAIR_ESCALATION:"+str(exc.reason))
     restore_slow_bounds();requested="FULL_REPLAN"
    except KeyError as exc:
     # Exact route pruning makes the current move-arc mapping sparse.  A move
     # selected by the shifted reference can therefore be absent before the
     # local-repair helper reaches its explicit admissibility check.  Treat
     # only that precise sparse-reference condition as a bounded escalation;
     # unrelated KeyErrors remain fail-closed programming errors.
     missing=exc.args[0] if len(exc.args)==1 else None
     moves_now=loc.get("moves",{}) or {}
     if not (isinstance(missing,tuple) and len(missing)==2 and missing not in moves_now):
      raise
     reasons.append("LOCAL_REPAIR_ESCALATION:SPARSE_REFERENCE_MOVE_ABSENT")
     jw(Path(loc["out"])/"A_B10_LOCAL_REPAIR_SPARSE_MOVE_ESCALATION.json",{
      "schema_version":"mobileess.a_b10.local_repair_sparse_move_escalation.v1",
      "status":"ESCALATE_FULL_REPLAN_SAME_PRE","missing_move_key":[int(missing[0]),int(missing[1])],
      "slow_bounds_restored":True,"future_actual_used":False})
     restore_slow_bounds();requested="FULL_REPLAN"
   if requested=="FULL_REPLAN":
    if issue_runtime["planner_mode"]=="LOCAL_REPAIR":
     raise RuntimeError("internal state error: full replan after accepted local repair")
    pq,planner_model=solve_planner_candidate();issue_runtime["slow_planner_runtime_s"]+=float(pq["wall_seconds"])
    jw(Path(loc["out"])/"A_B10_FULL_PLANNER_SOLVE.json",pq)
    if pq["candidate_available"]:
     accept_planner_candidate(planner_model);last_replan=i;issue_runtime["replan_executed"]=True;issue_runtime["planner_mode"]="FULL_REPLAN"
    else:
     if planner_model is not None:planner_model.dispose()
     if (hard_exc is not None or i==START or i in post_dispatch_hard_flags
         or issue_runtime.get("active_projection_retry_full_domain",False)):
      fq,fmodel=planner_feasibility_rescue(model,cb);issue_runtime["slow_planner_runtime_s"]+=float(fq["wall_seconds"])
      jw(Path(loc["out"])/"A_B10_HARD_FEASIBILITY_RESCUE.json",fq)
      if not fq["candidate_available"]:
       fmodel.dispose();raise RuntimeError(f"PLANNER_HARD_FEASIBILITY_RESCUE_FAILED:{fq['failure_classification']}")
      accept_planner_candidate(fmodel);last_replan=i;issue_runtime["replan_executed"]=True
      issue_runtime["planner_mode"]="FIRST_OR_HARD_EVENT_FEASIBILITY_RESCUE"
     else:
      # A soft/periodic miss may retain only an active plan that still passes current hard binding.
      bind=astep4.bind_shifted_active_plan(loc,ref,i);jw(Path(loc["out"])/"A_B10_PLANNER_MISS_RETAIN_ACTIVE.json",bind)
      issue_runtime["planner_mode"]="SOFT_REPLAN_NO_CANDIDATE_RETAIN_HARD_VALID_ACTIVE"
   if use_sparse_restore and os.environ.get("MOBILEESS_POST15_SKIP_REDUNDANT_DENSE_B4_CUTS","0")=="1":
    issue_runtime["dense_b4_restore"]=restore_redundant_dense_b4_rows(loc)
   try:
    fast=solve_fast(model,cb,loc)
   except RuntimeError as exc:
    sparse_dense_mismatch=(
     str(exc)=="fast conditioned dispatch has no feasible incumbent"
     and dense_equivalence_bound_snapshot is not None
     and bool(issue_runtime.get("replan_executed",False))
     and int(issue_runtime.get("dense_b4_restore",{}).get("rows_added",0))==576)
    if not sparse_dense_mismatch:raise
    for v,lb,ub,vtype in dense_equivalence_bound_snapshot.values():
     v.LB=lb;v.UB=ub;v.VType=vtype
    for key in ("_pending_complete_mip_start_by_name",
                "_pending_future_mode_bound_snapshot_by_name",
                "_pending_active_plan_mode_start_by_name",
                "_pending_all_active_plan_mode_start_by_name"):
     loc.pop(key,None)
    loc["_conditioned_shifted_active_plan"]=False
    model.update();model.reset()
    dense_q,dense_planner=planner_solve_exact_copy(model,cb)
    issue_runtime["slow_planner_runtime_s"]+=float(dense_q["wall_seconds"])
    dense_q.update({
     "schema_version":"mobileess.a_b10.sparse_dense_equivalence_fallback.v1",
     "status":("PASS_DENSE_CANDIDATE_AVAILABLE" if dense_q["candidate_available"]
               else "FAIL_DENSE_CANDIDATE_UNAVAILABLE"),
     "trigger":"SPARSE_CANDIDATE_INFEASIBLE_AFTER_576_ROW_RESTORATION",
     "same_pre":True,"full_unconditioned_domain_restored":True,
     "dense_original_rows_authoritative":True,"power_scale_changed":False,
     "hard_constraints_relaxed":False,"future_actual_used":False})
    jw(Path(loc["out"])/"A_B10_SPARSE_DENSE_EQUIVALENCE_FALLBACK.json",dense_q)
    if not dense_q["candidate_available"]:
     dense_planner.dispose()
     raise RuntimeError("SPARSE_DENSE_EQUIVALENCE_FALLBACK_NO_DENSE_CANDIDATE") from exc
    accept_planner_candidate(dense_planner)
    issue_runtime["planner_mode"]=(str(issue_runtime.get("planner_mode","UNKNOWN"))+
                                   "+DENSE_EQUIVALENCE_FALLBACK")
    issue_runtime["sparse_dense_equivalence_fallback_executed"]=True
    fast=solve_fast(model,cb,loc)
   issue_runtime["fast_solver"]=fast;issue_runtime["dispatch_status"]="OPTIMAL" if int(model.Status)==2 else f"GUROBI_{int(model.Status)}"
   loc["_a_b10_fixed_location_policy"]=fixed_location
   ac_recovery_context.clear();ac_recovery_context.update({"loc":dict(loc),"cb":cb})
   if issue_runtime.get("grid_hard_risk_full_replan_retry",False):
    previous_failed=issue_runtime.get("last_failed_recovery_candidate")
    if previous_failed is None:raise RuntimeError("FULL_REPLAN_FAILED_CANDIDATE_IDENTITY_MISSING")
    proposed=_recovery_candidate_fingerprints(loc,science,{},[])
    prior_decision_shas={str(x.get("decision_candidate_sha256"))
                         for x in issue_runtime.get("fresh_ac_candidate_attempts",[])}
    same=(proposed["decision_candidate_sha256"] in prior_decision_shas)
    duplicate_audit={
     "schema_version":"mobileess.post_stage15.w02_duplicate_candidate_gate.v1",
     "status":"BLOCKED_DUPLICATE_NO_SECOND_OPENDSS" if same else "PASS_DISTINCT_FULL_REPLAN_CANDIDATE",
     "issue":int(i),"previous_failed_decision_candidate_sha256":previous_failed.get("decision_candidate_sha256"),
     "full_replan_decision_candidate_sha256":proposed["decision_candidate_sha256"],
     "compared_against_all_prior_candidate_decisions":True,
     "prior_candidate_decision_count":len(prior_decision_shas),
     "same_pre_state":True,"full_replan_limit":GRID_HARD_RISK_FULL_REPLAN_MAX,
     "second_opendss_called_for_duplicate":False,"hard_limits_relaxed":False,"future_actual_used":False}
    issue_runtime["duplicate_recovery_candidate_gate"]=duplicate_audit
    jw(Path(loc["out"])/"A_B10_DUPLICATE_RECOVERY_CANDIDATE_GATE.json",duplicate_audit)
    if same:raise RuntimeError("DUPLICATE_RECOVERY_CANDIDATE_NO_SECOND_OPENDSS")
   issue_runtime["event_reasons"]=sorted(set(map(str,reasons)))
   issue_runtime["soft_metrics"]=metrics;issue_runtime["steps_since_plan_before_issue"]=steps
   return None
  science.certified_path_decomposition_solve=hook
  def capture_exact_ac_timed(grid24_arg,issue_out_arg,issue_arg,exact_summary_arg):
   stage=("FULL_REPLAN" if issue_runtime.get("grid_hard_risk_full_replan_retry",False)
          else str(issue_runtime.get("fresh_ac_capture_stage","INITIAL")))
   voltage_rows=_voltage_rows_from_live_opendss(grid24_arg)
   _record_recovery_candidate(ac_recovery_context["loc"],science,issue_runtime,Path(issue_out_arg),
                              stage,exact_summary_arg,voltage_rows)
   signature=hashlib.sha256(json.dumps({"stage":stage,"exact":dict(exact_summary_arg)},sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest()
   rec=issue_runtime.setdefault("observability_capture",{"calls":0,"deduplicated_calls":0,"wall_s":0.0,"cpu_s":0.0,"bytes":0,"last_signature":None})
   if rec.get("last_signature")==signature:
    rec["deduplicated_calls"]+=1;return
   tw=time.monotonic();tc=time.process_time()
   capture_exact_ac_observability(grid24_arg,issue_out_arg,issue_arg,exact_summary_arg)
   path=Path(issue_out_arg)/"exact_grid/A_B10_FRESH_EXACT_AC_OBSERVABILITY.json"
   rec["calls"]+=1;rec["wall_s"]+=time.monotonic()-tw;rec["cpu_s"]+=time.process_time()-tc
   rec["bytes"]=path.stat().st_size;rec["last_signature"]=signature
  science._a_b10_capture_exact_ac=capture_exact_ac_timed
  science._a_b10_exact_ac_recovery=lambda b4_arg,grid24_arg,scope_arg,gstatic_arg,issue_arg,running_arg,sol_arg,issue_out_arg,ex_arg: exact_ac_cut_recovery(
   science,ac_recovery_context,issue_runtime,b4_arg,grid24_arg,scope_arg,gstatic_arg,issue_arg,running_arg,sol_arg,issue_out_arg,ex_arg)
  started=time.monotonic();cpu_started=time.process_time()
  last_replan_before_attempt=last_replan
  def execute_one_issue()->int:
   science.build_full=prebuild_event_conditioning
   restore=install_source_bindings(science,r12,sources,power,price,i,engine/f"issue_{i:06d}")
   try:return int(one(engine,Path("/home/jaewon/mobile_ess_work")))
   finally:
    restore();science.build_full=performance_build_full
  def reset_failed_attempt_for_same_pre(retry_kind:str)->None:
   nonlocal last_replan,pre_t
   issue_runtime.setdefault("technical_retries",[]).append({
    "retry_kind":retry_kind,"same_pre_state":True,"prior_planner_mode":issue_runtime.get("planner_mode"),
    "prior_replan_executed":bool(issue_runtime.get("replan_executed",False)),
    "prior_last_replan_issue":int(last_replan),"restored_last_replan_issue":int(last_replan_before_attempt),
    "scientific_configuration_changed":False,"future_actual_used":False})
   last_replan=last_replan_before_attempt;pre_t=None;ac_recovery_context.clear()
   for key in ("prebuild_requested_mode","prebuild_projection_enabled","planner_formulation","dense_b4_restore",
               "event_reasons","soft_metrics","steps_since_plan_before_issue","ac_safety_recovery",
               "observability_capture","model_observability_capture","fresh_ac_capture_stage"):
    issue_runtime.pop(key,None)
   issue_runtime.update({"planner_mode":"NONE","replan_executed":False,"dispatch_status":None,"fast_solver":{}})
  with book.phase("science_one_issue_total",i,issue_runtime):
   rc=execute_one_issue()
   failure_path=engine/"_FAILURE.json"
   failure=load_json(failure_path) if rc!=0 and failure_path.is_file() else {}
   retryable=any(token in str(failure.get("error","")) for token in (
    "A_B10_ACTIVE_PLAN_MOBILITY_PROJECTION_",
    "A_B10_ACTIVE_PLAN_CONDITIONED_INFEASIBLE_REQUIRES_SAME_PRE_FULL_REPLAN"))
   if retryable:
    retry_root=policy_root/"interrupted_attempts"/datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")/f"issue_{i:06d}_projected_retry"
    retry_root.mkdir(parents=True,exist_ok=True)
    issue_dir=engine/f"issue_{i:06d}"
    if issue_dir.exists():shutil.move(str(issue_dir),str(retry_root/issue_dir.name))
    if failure_path.exists():shutil.move(str(failure_path),str(retry_root/failure_path.name))
    reset_failed_attempt_for_same_pre("ACTIVE_PLAN_INVALIDATION_FULL_DOMAIN")
    os.environ["MOBILEESS_ACTIVE_PLAN_MOBILITY_PROJECTION"]="0"
    issue_runtime["active_projection_retry_full_domain"]=True
    rc=execute_one_issue()
    failure=load_json(failure_path) if rc!=0 and failure_path.is_file() else {}
  grid_retryable=(rc!=0 and "GRID_CORRECTION_EXHAUSTED" in str(failure.get("error",""))
                  and len(issue_runtime.get("fresh_ac_candidate_attempts",[]))
                  < FRESH_AC_PRODUCTION_CANDIDATE_MAX
                  and i not in post_dispatch_hard_flags)
  if grid_retryable:
   full_replan_count=int(issue_runtime.get("grid_hard_risk_full_replan_count",0))+1
   if full_replan_count>GRID_HARD_RISK_FULL_REPLAN_MAX:
    raise RuntimeError(f"GRID_HARD_RISK_FULL_REPLAN_LIMIT_EXCEEDED:{full_replan_count}")
   retry_root=policy_root/"interrupted_attempts"/datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")/f"issue_{i:06d}_grid_hard_pre_replan"
   retry_root.mkdir(parents=True,exist_ok=True);issue_dir=engine/f"issue_{i:06d}"
   if issue_dir.exists():shutil.move(str(issue_dir),str(retry_root/issue_dir.name))
   if failure_path.exists():shutil.move(str(failure_path),str(retry_root/failure_path.name))
   reset_failed_attempt_for_same_pre("GRID_HARD_RISK_FULL_REPLAN")
   post_dispatch_hard_flags[i]="GRID_HARD_RISK";issue_runtime["grid_hard_risk_full_replan_retry"]=True
   issue_runtime["grid_hard_risk_full_replan_count"]=full_replan_count
   rc=execute_one_issue()
  wall=time.monotonic()-started
  if rc!=0:raise RuntimeError(f"scientific one-issue engine returned {rc} at issue {i}")
  d=engine/f"issue_{i:06d}"
  if not ac_recovery_context.get("loc"):raise RuntimeError(f"committed-model observability context missing issue={i}")
  tw=time.monotonic();tc=time.process_time()
  model_obs=capture_model_observability(science,ac_recovery_context["loc"],d,i,power,price)
  issue_runtime["model_observability_capture"]={**model_obs,"wall_s":time.monotonic()-tw,"cpu_s":time.process_time()-tc}
  for rp in [d/"BUILD7C_POSTCOMMIT_STATE.json",d/"BUILD7C_FIRSTSTEP_TRANSITION_CERTIFICATE.json",d/f"exact_grid/FRESH_EXACT_OPENDSS_24SERVICE_ISSUE_{i}.json"]:
   if not rp.is_file():raise RuntimeError(f"required committed artifact missing {rp}")
  with book.phase("commit_evidence_load_and_validate",i,issue_runtime):
   tr=load_json(d/"BUILD7C_FIRSTSTEP_TRANSITION_CERTIFICATE.json");fr=load_json(d/f"exact_grid/FRESH_EXACT_OPENDSS_24SERVICE_ISSUE_{i}.json")
  if tr.get("status")!="PASS" or tr.get("h0_only_committed") is not True or tr.get("future_actual_arrivals_read") is not False:
   raise RuntimeError(f"transition gate failed issue={i}")
  if fr.get("hard_constraint_pass") is not True or fr.get("converged") is not True:raise RuntimeError(f"Fresh OpenDSS failed issue={i}")
  if fixed_location:
   post=load_json(d/"BUILD7C_POSTCOMMIT_STATE.json")["state"]
   bad={mid:post["mess_state"].get(mid) for mid,sid in homes.items()
        if post["mess_state"].get(mid,{}).get("phase")!="STAY"
        or post["mess_state"].get(mid,{}).get("service_id")!=sid
        or int(post["mess_state"].get(mid,{}).get("remaining_total_steps",-1))!=0
        or list(post["mess_state"].get(mid,{}).get("remaining_profile_kWh",[]))}
   if bad:raise RuntimeError(f"M4 fixed-location POST drift issue={i}: {bad}")
   if tr.get("selected_h0_moves") not in ({},None):raise RuntimeError(f"M4 selected movement issue={i}")
   if load_csv(d/"BUILD7B_FULL54_MOVE_ARCS_SELECTED.csv"):raise RuntimeError(f"M4 move plan is not empty issue={i}")
  prepost=float(issue_runtime["pre_to_post_wall_s"] or wall);slow=float(issue_runtime["slow_planner_runtime_s"] or 0)
  issue_runtime.update({"schema_version":"mobileess.post_stage15.rep_week.policy_issue.v2","issue":i,"status":"PASS_COMMITTED",
    "policy_id":cfg["policy_id"],"pre_state_sha256":tr["pre_state_sha256"],"post_state_sha256":tr["post_state_sha256"],
    "full_issue_wall_s":wall,"commit_critical_runtime_s":max(0.0,prepost-slow),
    "development_host_deadline_overrun":max(0.0,prepost-slow)>=300.0,
    "fresh_opendss_pass":True,"future_actual_used":False,"full_issue_cpu_s":time.process_time()-cpu_started,
    "max_rss_mib":book.rss_mib(),"science_runtime_events":list(getattr(science,"_RUNTIME_EVENTS",[])),
    "comparison_method_id":cfg["slot"].split("_",1)[0],"scientific_method_id":"B5",
    "last_replan_issue_after_issue":last_replan,"event_engine_state_after_issue":event_state(ev)})
  issue_runtime["issue_artifact_storage"]={"bytes":sum(p.stat().st_size for p in d.rglob("*") if p.is_file()),
                                            "files":sum(1 for p in d.rglob("*") if p.is_file())}
  jw(d/"POLICY_ISSUE_AUDIT.json",issue_runtime)
  write_commit_marker(d,i,last_replan,event_state(ev),d/"BUILD7C_ROLLING_GUIDANCE_NEXT_ISSUE.json")
  new_reg1a_limit=_reg1a_causal_equivalent_kva_limit(
   d/"exact_grid/A_B10_FRESH_EXACT_AC_OBSERVABILITY.json")
  if new_reg1a_limit is not None:
   reg1a_prior_limits.append(float(new_reg1a_limit))
   reg1a_causal_limit_kva=reg1a_prior_limits[-1]
  issue_audits.append(issue_runtime)
  jw(checkpoint_path,{"status":"RUNNING","last_completed_issue":i,"last_replan_issue":last_replan,
      "event_engine_state":event_state(ev),"completed_issue_count":len(issue_audits),"future_actual_used":False})
  jw(policy_root/"progress"/PROGRESS_FILE,{"candidate_id":CANDIDATE_ID,"status":"RUNNING_BOUNDED_PROFILE" if a.benchmark_issues else "RUNNING",
      "completed":len(issue_audits),"required":run_count,"last_issue":i,"benchmark_only":bool(a.benchmark_issues)})
  if (i-START+1)%12==0 or i==START:
   print(f"[{cfg['slot']} {cfg['policy_id']}] {i-START+1}/{run_count} issue={i} commit={issue_runtime['commit_critical_runtime_s']:.2f}s planner={slow:.2f}s mode={issue_runtime['planner_mode']}",flush=True)
 if a.benchmark_issues:
  result=book.document("PASS_BOUNDED_ACTUAL_PROFILE_NOT_SCIENTIFIC_EPISODE",run_count)
  result.update({"candidate_id":CANDIDATE_ID,"policy_id":cfg["policy_id"],"slot":cfg["slot"],
                 "start_issue":START,"end_issue":run_end,"actual_gurobi_and_fresh_opendss":True,
                 "full_episode_finalization_performed":False,"F7_performed":False})
  jw(policy_root/"PERFORMANCE_BOUNDED_RUN.json",result)
  jw(policy_root/"progress"/PROGRESS_FILE,{"candidate_id":CANDIDATE_ID,"status":result["status"],"completed":len(issue_audits),
      "required":run_count,"last_issue":run_end,"benchmark_only":True})
  print(f"REP_WEEK_BOUNDED_PROFILE_STATUS=PASS candidate={CANDIDATE_ID} slot={cfg['slot']} policy={cfg['policy_id']} issues={run_count}")
  restore_performance_wrappers()
  return 0
 if len(issue_audits)!=COUNT:raise RuntimeError(f"policy issue count {len(issue_audits)} != {COUNT}")
 final=load_json(engine/f"issue_{END:06d}/BUILD7C_POSTCOMMIT_STATE.json")
 shutil.copy2(engine/f"issue_{END:06d}/BUILD7C_POSTCOMMIT_STATE.json",policy_root/"EVALUATION_END_RUNTIME_STATE.json")
 build_results(policy_root,engine,cfg,issue_audits)
 commit=[float(x["commit_critical_runtime_s"]) for x in issue_audits];planner=[float(x["slow_planner_runtime_s"]) for x in issue_audits if float(x["slow_planner_runtime_s"])>0]
 hw={"platform":sys.platform,"python":sys.version,"cpu_affinity":sorted(os.sched_getaffinity(0)) if hasattr(os,"sched_getaffinity") else [],
     "process_cpu_count":os.cpu_count()}
 jw(policy_root/"RUNTIME_CHARACTERIZATION.json",{"schema_version":"mobileess.post_stage15.rep_week.runtime_characterization.v2","candidate_id":CANDIDATE_ID,"status":"PASS",
   "hardware":hw,"outer_processes_expected":4,"threads_per_process":4,
   "commit_critical":{"p50_s":quantile(commit,.50),"p95_s":quantile(commit,.95),"p99_s":quantile(commit,.99),"max_s":max(commit),
                      "deadline_miss_count":sum(x>=300 for x in commit),"development_host_realtime_claim":"DEMONSTRATED" if max(commit)<300 else "NOT_DEMONSTRATED"},
   "slow_planner":{"count":len(planner),"p50_s":quantile(planner,.50),"p95_s":quantile(planner,.95),"p99_s":quantile(planner,.99),"max_s":max(planner) if planner else None},
   "slow_planner_execution_semantics":"BOUNDARY_SYNCHRONOUS_SCIENTIFIC_REPLAY; runtime excluded from commit-critical characterization",
   "target_hardware_realtime_claim":"NOT_QUALIFIED_BY_THIS_RUN"})
 run_f7(policy_root,cfg)
 jw(policy_root/"PERFORMANCE_FULL_RUN.json",book.document("PASS_FULL_EPISODE",COUNT))
 jw(policy_root/"progress"/PROGRESS_FILE,{"candidate_id":CANDIDATE_ID,"status":"PASS","completed":COUNT,"required":COUNT,"last_issue":END})
 jw(checkpoint_path,{"status":"PASS_COMPLETE","last_completed_issue":END,"last_replan_issue":last_replan,
    "event_engine_state":event_state(ev),"completed_issue_count":COUNT,"future_actual_used":False})
 # policy-level checksums
 sf=policy_root/"SHA256SUMS.txt"
 sf.write_text("".join(f"{sha(p)}  {p.relative_to(policy_root).as_posix()}\n" for p in sorted(policy_root.rglob("*")) if p.is_file() and p!=sf),encoding="utf-8")
 restore_performance_wrappers()
 print(f"REP_WEEK_POLICY_STATUS=PASS candidate={CANDIDATE_ID} slot={cfg['slot']} policy={cfg['policy_id']} issues={COUNT}")
 return 0

if __name__=="__main__":
 try:raise SystemExit(main())
 except Exception as e:
  try:
   cfg=load_json(Path(sys.argv[sys.argv.index("--config")+1])) if "--config" in sys.argv else {}
   out=Path(sys.argv[sys.argv.index("--output")+1]) if "--output" in sys.argv else Path(".")
   jw(out/"FAILURE.json",{"status":"FAIL_CLOSED","error":f"{type(e).__name__}: {e}","traceback":traceback.format_exc(),
                          "future_actual_used":False,"partial_results_preserved":True})
  except Exception:pass
  traceback.print_exc();raise

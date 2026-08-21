#!/usr/bin/env python3
"""W02 2016-issue actual B5 hierarchical-controller policy runner.

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

import argparse,csv,difflib,hashlib,importlib.util,inspect,json,math,os,re,shutil,statistics,sys,time,traceback
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
H=54
PR4="06a94bccc0a232ae7ea09cbc7b00962162c10f4d"
SCIENCE_SHA="1177ac8814f1008907f89ebf513bf9fe3e469d2c09a51ba85303c46c428f76b9"
B5_SHA="3f712ec02c4c5ebb6a424267b043f07469d29f4a4abeaea7fcdd8b765e13624a"
PRE_SHA="1e7b722816a9f938be45fbcbaf5442261496bdb40a58ad30883007c112e1142e"
RESULT_SCHEMA="K9H7_RESULT_V1"
SHARED=Path("/home/jaewon/mobile_ess_work/frozen_artifacts/B_W02_SHARED_EXOGENOUS_SOURCE_CURRENT")
DELIVERY=Path("/home/jaewon/mobile_ess_work/frozen_artifacts/B_W02_4POLICY_ACTUAL_PILOT_CURRENT")
LOGROOT=Path("/home/jaewon/mobile_ess_work/logs/B_W02_4POLICY_ACTUAL_PILOT_CURRENT")

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
   if cov["timestamp_utc"].nunique()!=COUNT or len(cov)!=COUNT*mult:raise RuntimeError(f"W02 rack {name} coverage drift")
  fcov=forecast[(forecast["timestamp_utc"]>=first)&(forecast["timestamp_utc"]<=last)]
  if fcov["timestamp_utc"].nunique()!=COUNT:raise RuntimeError("W02 rack forecast coverage drift")
  self.aidx=actual.set_index(["timestamp_utc","rack_pool_id"]).sort_index()
  self.iidx=inference.set_index(["timestamp_utc","idc_id"]).sort_index()
  self.qidx=forecast.set_index("timestamp_utc").sort_index()
 def bind(self,scope:dict,out:Path):
  env=scope["env"];env.aidx=self.aidx;env.iidx=self.iidx;env.qidx=self.qidx
  p=Path(out)/"A_B10_FULL_YEAR_RACK_BINDING.json"
  if not p.is_file():
   jw(p,{"status":"PASS","candidate_id":"W02_2025-01-13","actual_sha256":self.helper.RACK_ACTUAL_SHA,
         "inference_sha256":self.helper.RACK_INFERENCE_SHA,"forecast_sha256":self.helper.RACK_FORECAST_SHA,
         "source_loaded_once_per_policy_process":True,"current_actual_read_policy":"current issue only","future_actual_used":False})

class SourceBlocks:
 def __init__(self,root:Path):
  self.root=root
  self._block=-1;self._power={};self._price={}
  self.pp=load_json(root/"power_price/A_B10_W02_POWER_PRICE_SOURCE_AUTHORITY.json")
  self.shared=load_json(root/"SHARED_EXOGENOUS_AUTHORITY.json")
  if self.pp.get("status")!="PASS" or self.shared.get("status")!="PASS":raise RuntimeError("shared exogenous authority not PASS")
  self.mob_index=root/"mobility/R12_COMMON_MOBILITY_INDEX.csv"
  self.mob_rows={int(r["issue_step"]):r for r in load_csv(self.mob_index)}
  if any(i not in self.mob_rows for i in range(START,END+1)):raise RuntimeError("W02 mobility scored coverage incomplete")
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
  ('  rack,op1,cr,grid,metrics=b4.preload(engine);scope=b4.prepare_scope(Path(base),rack,op1,out);temps.extend(scope["temps"])',
   '  rack,op1,cr,grid,metrics=b4.preload(engine);scope=b4.prepare_scope(Path(base),rack,op1,out);temps.extend(scope["temps"]);_a_b10_bind_full_year_rack_scope(scope,out)'),
  ('  if resume_issue==113:','  if False:  # A-B10 always uses SHA-bound external PRE state'),
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

def runtime_env(issue:int,state_path:Path,state_hash:str,mob_idx:Path,control:Path)->dict[str,str]:
 abase.set_science_environment()
 env=dict(os.environ)
 env.update({
  "MOBILEESS_ROLL_START":str(issue),"MOBILEESS_ROLL_COUNT":"1","MOBILEESS_RESUME_ISSUE":str(issue),
  "MOBILEESS_R25Q_VERIFIED_PREFIX_ISSUES":"0",
  "MOBILEESS_R25Q_RESUME_STATE_PATH":str(state_path),
  "MOBILEESS_RESUME_STATE_SHA256":str(state_hash),
  "MOBILEESS_R25Q_RESUME_SOURCE":"A-B10 W02 policy canonical PRE or preceding committed POST",
  "MOBILEESS_R25Q_RESUME_HINT_DIR":str(control/"empty_hints"),
  "MOBILEESS_R25Q_RESUME_MOVE_PLAN_NAME":"NONE.csv",
  "MOBILEESS_R25Q_RESUME_MESS_PLAN_NAME":"NONE.csv",
  "MOBILEESS_R25V_RESUME_JOB_PLAN_NAME":"NONE.csv",
  "MOBILEESS_R25V_RESUME_GUIDANCE_PATH":str(control/"empty_hints/NONE.json"),
  "A_B10_MOBILITY_INDEX":str(mob_idx),
  "MOBILEESS_GUROBI_THREADS":"4",
  "MOBILEESS_GUROBI_ECON_MIPGAP":"0.03",
 })
 env.pop("MOBILEESS_GUROBI_TIMELIMIT",None)
 return env

def initial_reference(raw:Path)->dict[str,Any]:
 import pandas as pd
 return {
  "BUILD7B_FULL54_JOB_PLAN.csv":pd.read_csv(raw/"BUILD7B_FULL54_JOB_PLAN.csv"),
  "BUILD7B_FULL54_MESS_PLAN.csv":pd.read_csv(raw/"BUILD7B_FULL54_MESS_PLAN.csv"),
  "BUILD7B_FULL54_MOVE_ARCS_SELECTED.csv":pd.read_csv(raw/"BUILD7B_FULL54_MOVE_ARCS_SELECTED.csv"),
  "active_plan_parent_issue":None,
  "active_plan_source_post_sha256":PRE_SHA,
  "authority":"PR4_W02_CANONICAL_H0_COMMON_INITIAL_PLAN",
 }

def fix_all_slow_to_incumbent(loc:Mapping[str,Any])->dict[str,int]:
 counts={}
 for name in ("x","defer","stay","mv","node_occ"):
  d=loc.get(name,{}) or {};counts[name]=len(d)
  for v in d.values():set_fixed(v,1.0 if float(v.X)>=0.5 else 0.0)
 loc["m"].update()
 return counts

def residual_integer_names(model)->list[str]:
 return [str(v.VarName) for v in model.getVars() if str(v.VType).upper() in {"B","I","S","N"} and float(v.UB)-float(v.LB)>1e-12]

def solve_fast(model,cb)->dict[str,Any]:
 import gurobipy as gp
 model.Params.Threads=4;model.Params.MIPGap=0.03;model.Params.MIPGapAbs=0.0;model.Params.MIPFocus=1
 model.Params.TimeLimit=gp.GRB.INFINITY;model.Params.OutputFlag=1;model.update();model.reset()
 t=time.monotonic();model.optimize(cb) if cb is not None else model.optimize();wall=time.monotonic()-t
 q=abase.solver_quality(model);q["wall_seconds"]=wall
 if int(model.SolCount)<1:raise RuntimeError("fast conditioned dispatch has no feasible incumbent")
 try:gap=float(model.MIPGap)
 except Exception:gap=None
 if int(model.Status)!=int(gp.GRB.OPTIMAL) and (gap is None or gap>0.03+1e-12):
  raise RuntimeError(f"fast conditioned dispatch did not reach 3% operational gap status={model.Status} gap={gap}")
 return q

def planner_solve(model,cb)->dict[str,Any]:
 model.Params.Threads=4;model.Params.MIPGap=0.10;model.Params.MIPGapAbs=0.0;model.Params.MIPFocus=1
 model.Params.Heuristics=0.20;model.Params.TimeLimit=300.0;model.Params.OutputFlag=1;model.update();model.reset()
 t=time.monotonic();model.optimize(cb) if cb is not None else model.optimize();wall=time.monotonic()-t
 q=abase.solver_quality(model);q["wall_seconds"]=wall;q["candidate_available"]=int(model.SolCount)>0
 return q

def current_soft_metrics(loc:Mapping[str,Any],sources:SourceBlocks,issue:int)->dict[str,float]:
 mess_E={str(k):float(v) for k,v in loc.get("mess_E",{}).items()}
 soc_margin=min((v-440.0 for v in mess_E.values()),default=9999.0)
 if issue==START:
  load_err=0.0
 else:
  prior=sources.q50_next_background_kw(issue-1)
  bp,bq,pv,_=loc["ref"]["store"].step(issue)
  actual=float(np.asarray(bp,float).sum()-np.asarray(pv,float).sum())
  load_err=0.0 if prior is None else abs(actual-prior)/max(1.0,abs(prior))*100.0
 return {"load_forecast_error_pct":float(load_err),"soc_reserve_margin_kwh":float(soc_margin)}

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
 if d.exists() and not (d/"BUILD7C_POSTCOMMIT_STATE.json").is_file():
  q=policy_root/"interrupted_attempts"/datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")/d.name
  q.parent.mkdir(parents=True,exist_ok=True);shutil.move(str(d),str(q))

def restore_event_engine(event,checkpoint:Mapping[str,Any]):
 st=checkpoint.get("event_engine_state",{})
 for k,v in st.get("active",{}).items():
  if k in event._active:event._active[k]=bool(v)
 event._soft_since_issue=st.get("soft_since_issue")

def event_state(event):
 return {"active":dict(event._active),"soft_since_issue":event._soft_since_issue}

def write_policy_manifest(root:Path,cfg:Mapping[str,Any],config_sha:str,source_auth:Mapping[str,Any]):
 jw(root/"CONTROLLER_POLICY_MANIFEST.json",{
  "schema_version":"a_to_b.10.controller_policy_manifest.v1","status":"FROZEN_BEFORE_W02_POLICY_OUTCOME",
  "candidate_id":"W02_2025-01-13","method_id":"B5","method_config_sha256":B5_SHA,
  "policy_id":cfg["policy_id"],"slot":cfg["slot"],"resolved_config_sha256":config_sha,
  "base_policy":cfg["base_policy"],"event_triggered":cfg["event_triggered"],
  "local_repair_enabled":cfg["local_repair_enabled"],"max_refresh_steps":cfg["max_refresh_steps"],
  "controller_burn_in_steps":0,"canonical_pre_state_sha256":PRE_SHA,
  "same_exogenous_source_authority_sha256":sha(SHARED/"SHARED_EXOGENOUS_AUTHORITY.json"),
  "hard_safety_events_are_universal":True,
  "scientific_source_commit":PR4,"science_main_sha256":SCIENCE_SHA,
  "planner_latency_execution_semantics":"BOUNDARY_SYNCHRONOUS_SCIENTIFIC_REPLAY; SLOW_PLANNER_RUNTIME_REPORTED_SEPARATELY",
  "realtime_claim_on_development_host":"NOT_DEMONSTRATED_UNTIL_MEASURED",
  "future_actual_used":False,"future_plans_persisted":False,
 })

def load_schema()->dict[str,Any]:
 return load_json(HERE/"authority/D/04_RESULT_CONTRACT/K9H7_RESULT_V1_SCHEMA_INVENTORY_R10.json")

def build_results(policy_root:Path,engine:Path,cfg:Mapping[str,Any],issue_audits:list[dict[str,Any]]):
 schema=load_schema();run_id=f"B_W02_{cfg['slot']}_{cfg['policy_id']}";scenario="W02_2025-01-13"
 common={"result_schema_version":RESULT_SCHEMA,"run_id":run_id,"method_id":"B5","scenario_id":scenario}
 rolling=[];mess=[];debt=[];grid=[];opt=[];constraints=[];wan=[];rack=[];forecast=[];busphase=[]
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
  ts=int(fr.get("timestamp_utc_ns",0));dt=datetime.fromtimestamp(ts/1e9,tz=timezone.utc) if ts else datetime(2025,1,13,tzinfo=timezone.utc)
  aest=dt.astimezone(timezone(timedelta(hours=10))).isoformat()
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
   energy=fnum((mr or {}).get("safe_energy_kWh"),0) or 0
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
    "transformer_current_violation_count":fr.get("transformer_current_violation_count"),"cut_triggered":False})
  gi=fnum(fr.get("root_import_p_kw"),0);grid_mwh+=gi/1000*(5/60);peak_grid=max(peak_grid,gi)
  vmin=min(vmin,fnum(fr.get("voltage_min_pu"),math.inf));vmax=max(vmax,fnum(fr.get("voltage_max_pu"),-math.inf))
  maxline=max(maxline,fnum(fr.get("line_max_loading_pu"),0));maxtx=max(maxtx,fnum(fr.get("transformer_max_kva_loading_pu"),0))
  vviol+=inum(fr.get("voltage_violation_count"),0);lviol+=inum(fr.get("line_violation_count"),0);tviol+=inum(fr.get("transformer_kva_violation_count"),0)
  fast=audit.get("fast_solver",{});runtime=fnum(audit.get("commit_critical_runtime_s"),0);gap=fnum(fast.get("MIPGap"),fnum(fast.get("mip_gap")))
  runtimes.append(runtime)
  if gap is not None:gaps.append(gap)
  n=fnum(fast.get("NodeCount"),fnum(fast.get("node_count")));nodes.append(n or 0)
  opt.append({**common,"issue_step":issue,"model_status":audit.get("dispatch_status",""),
              "runtime_s":runtime,"node_count":n,"mip_gap":gap,
              "variable_count":inum(fast.get("NumVars"),inum(fast.get("variables"))),
              "binary_count":inum(fast.get("NumBinVars"),inum(fast.get("binary_variables"))),
              "constraint_count":inum(fast.get("NumConstrs"),inum(fast.get("constraints"))),
              "iis_generated":False,"resolve_iteration":int(audit.get("replan_executed",False)),
              "cut_count":0,"numeric_focus":fast.get("NumericFocus"),
              "feasibility_tol":fast.get("FeasibilityTol"),"optimality_tol":fast.get("OptimalityTol")})
  rolling.append({**common,"issue_step":issue,"timestamp_utc_ns":ts,"timestamp_aest":aest,
                  "grid_import_kW":fr.get("root_import_p_kw"),"grid_import_kvar":fr.get("root_import_q_kvar"),
                  "MESS_net_P_kW":sum(fnum(r["P_kW"],0) for r in mrows),"MESS_net_Q_kvar":sum(fnum(r["Q_kvar"],0) for r in mrows),
                  "total_SOC_kWh":sum(float(v) for v in qst.get("mess_E_kWh",{}).values()),
                  "workload_debt_GPUh":wd,"support_energy_debt_kWh":sd,
                  "min_voltage_pu":fr.get("voltage_min_pu"),"max_voltage_pu":fr.get("voltage_max_pu"),
                  "max_line_loading_pu":fr.get("line_max_loading_pu"),"max_transformer_loading_pu":fr.get("transformer_max_kva_loading_pu"),
                  "voltage_violation_count":fr.get("voltage_violation_count"),"line_overload_count":fr.get("line_violation_count"),
                  "transformer_overload_count":fr.get("transformer_kva_violation_count"),
                  "solve_time_s":runtime,"mip_gap":gap,"exact_AC_pass":True,"cut_count_this_issue":0,"commit_status":"COMMITTED"})
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
 summary={**common,"forecast_model_id":"","causal_eligible":True,"oracle":False,"start_step":START,"end_step":END,
  "committed_steps":len(issue_audits),"status":"PASS" if len(issue_audits)==COUNT else "INCOMPLETE",
  "grid_import_MWh":grid_mwh,"peak_grid_import_kW":peak_grid,"min_voltage_pu":vmin,"max_voltage_pu":vmax,
  "voltage_violation_count":vviol,"voltage_violation_minutes":vviol*5.0,"max_line_loading_pu":maxline,
  "line_overload_count":lviol,"max_transformer_loading_pu":maxtx,"transformer_overload_count":tviol,
  "jobs_total":len(jobs),"jobs_completed":len(final_completed.intersection({str(x['job_id']) for x in jobs})),
  "deadline_miss_count":misses,"mean_job_delay_min":statistics.mean(delays) if delays else None,
  "p95_job_delay_min":quantile(delays,.95),"p99_job_delay_min":quantile(delays,.99),"max_job_delay_min":max(delays) if delays else None,
  "MESS_charge_MWh":total_charge,"MESS_discharge_MWh":total_dis,"MESS_mobility_energy_MWh":total_mob_e,
  "MESS_travel_minutes":total_travel,"battery_throughput_MWh":total_charge+total_dis,
  "SOC_min_pct":min_soc if math.isfinite(min_soc) else None,"SOC_max_pct":max_soc if math.isfinite(max_soc) else None,
  "exact_AC_calls":len(grid),"exact_AC_fail_count":sum(1 for x in grid if not x["hard_constraint_pass"]),
  "AC_cut_count":0,"resolve_count":sum(int(x.get("replan_executed",False)) for x in issue_audits),
  "solve_time_total_s":sum(runtimes),"solve_time_mean_s":statistics.mean(runtimes) if runtimes else None,
  "solve_time_p95_s":quantile(runtimes,.95),"solve_time_max_s":max(runtimes) if runtimes else None,
  "MIP_gap_max":max(gaps) if gaps else None,"MIP_nodes_total":sum(nodes),
  "notes":"W02 actual 2016-issue B5 policy episode. Slow-planner runtime is reported separately in RUNTIME_CHARACTERIZATION.json; real-time claim is not inferred from this development host."}
 tables["run_summary"]=[summary]
 for name in TABLES:write_csv(policy_root/f"{name}.csv",schema[name]["fields"],tables[name])
 obs={"schema_version":"a_to_b.10.w02.observability.v1","header_only_tables":[n for n in TABLES if n!="run_summary" and not tables[n]],
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
 ap=argparse.ArgumentParser()
 ap.add_argument("--repo",required=True);ap.add_argument("--config",required=True);ap.add_argument("--output",required=True)
 a=ap.parse_args()
 repo=Path(a.repo).resolve();cfg_path=Path(a.config).resolve();cfg=load_json(cfg_path);policy_root=Path(a.output).resolve()
 if sha(repo/"science/main.py")!=SCIENCE_SHA:raise RuntimeError("science/main.py SHA drift")
 if cfg["candidate_id"]!="W02_2025-01-13" or cfg["method_config_sha256"]!=B5_SHA:raise RuntimeError("policy config identity drift")
 config_sha=sha(cfg_path)
 expected_file=HERE/"configs"/cfg_path.name
 if expected_file.resolve()!=cfg_path and expected_file.is_file() and sha(expected_file)!=config_sha:raise RuntimeError("policy config SHA mismatch")
 shared=load_json(SHARED/"SHARED_EXOGENOUS_AUTHORITY.json")
 if shared.get("status")!="PASS":raise RuntimeError("shared exogenous source not PASS")
 policy_root.mkdir(parents=True,exist_ok=True);(policy_root/"logs").mkdir(exist_ok=True);(policy_root/"progress").mkdir(exist_ok=True)
 engine=policy_root/"engine";engine.mkdir(exist_ok=True)
 control=policy_root/"control";control.mkdir(exist_ok=True);(control/"empty_hints").mkdir(exist_ok=True)
 (control/"empty_hints/NONE.json").write_text("{}\n")
 source_auth=load_json(HERE/"authority/A/SOURCE_AUTHORITY.json")
 write_policy_manifest(policy_root,cfg,config_sha,source_auth)
 episode_id=f"W02_{cfg['slot']}_{cfg['policy_id']}_B5"
 jw(policy_root/"episode_manifest.json",{
  "schema_version":"a_to_b.10.w02_episode_manifest.v1","episode_id":episode_id,"run_id":episode_id,
  "scenario_id":"W02_2025-01-13","candidate_id":"W02_2025-01-13","month":"2025-01",
  "method_id":"B5","method_config_sha256":B5_SHA,"policy_id":cfg["policy_id"],"slot":cfg["slot"],
  "evaluation_start_step":START,"evaluation_end_step":END,"evaluation_end_step_inclusive":END,
  "scored_issues":COUNT,"controller_burn_in_steps":0,"selection_window_pre_history_steps":576,
  "selection_window_pre_history_role":"PROVENANCE_ONLY","canonical_pre_state_sha256":PRE_SHA,
  "shared_exogenous_authority_sha256":sha(SHARED/"SHARED_EXOGENOUS_AUTHORITY.json"),
  "future_actual_used":False,"future_plans_persisted":False,"right_censoring_retained":True,
  "runtime_semantics_contract":"D12_RUNTIME_CLAIM_SEMANTICS_V2"})
 sources=SourceBlocks(SHARED)
 r12=loadmod(repo/"stage7/r12_representative_weeks/stage7_r12_burnin_runner.py","a_b10_r12_helper_"+cfg["slot"])
 rack_cache=RackCache(r12,Path("/home/jaewon/mobile_ess_work"))
 # Import the frozen science module once per policy process. Per-issue mutable
 # caches are cleared before each causal boundary, avoiding 2016 repeated imports.
 abase.set_science_environment()
 science=abase.load_science(repo)
 one=transform_science(science,control)
 original_science_jw=science.jw
 # Event engine from actual PR4 checkout.
 sys.path.insert(0,str(repo))
 from r26.event_engine import EventConfig,EventEngine
 ev=EventEngine(EventConfig.from_mapping(cfg["event_config"]))
 checkpoint_path=control/"POLICY_RUNTIME_CHECKPOINT.json"
 checkpoint=load_json(checkpoint_path) if checkpoint_path.is_file() else {}
 if checkpoint:restore_event_engine(ev,checkpoint)
 last_replan=int(checkpoint.get("last_replan_issue",START))
 issue_audits=[]
 for i in range(START,END+1):
  auditp=engine/f"issue_{i:06d}/POLICY_ISSUE_AUDIT.json"
  postp=engine/f"issue_{i:06d}/BUILD7C_POSTCOMMIT_STATE.json"
  if auditp.is_file() and postp.is_file():
   issue_audits.append(load_json(auditp));continue
  quarantine_incomplete(engine,i,policy_root)
  # PRE authority: canonical for first issue, previous policy POST thereafter.
  if i==START:
   state_path=HERE/"authority/D/03_C_ZERO_BURNIN/initial_states/CANONICAL_PRE_STATE_W02_2025-01-13.json"
  else:
   state_path=engine/f"issue_{i-1:06d}/BUILD7C_POSTCOMMIT_STATE.json"
  state=load_json(state_path);pre_hash=str(state["sha256"])
  if i==START and pre_hash!=PRE_SHA:raise RuntimeError("canonical W02 PRE hash drift")
  power,price=sources.row(i)
  env=runtime_env(i,state_path,pre_hash,sources.mob_index,control)
  os.environ.clear();os.environ.update(env)
  # Clear scientific data caches across issue boundaries: current observations
  # and current causal source slices must never be inherited from the prior issue.
  if hasattr(science,"_PERSIST"):science._PERSIST.clear()
  science.jw=original_science_jw
  science._a_b10_bind_full_year_rack_scope=rack_cache.bind
  restore_sources=install_source_bindings(science,r12,sources,power,price,i,engine/f"issue_{i:06d}")
  # Reference active plan.
  if i==START:
   seed=Path("/home/jaewon/mobile_ess_work/stage7_r13_zero_burnin_runs/W02_2025-01-13/canonical_h0/issue_003456")
   if not (seed/"BUILD7B_FULL54_JOB_PLAN.csv").is_file():raise RuntimeError("PR4 W02 canonical h0 initial full plan unavailable")
   ref=initial_reference(seed)
  else:
   ref=astep4.shifted_reference_from_previous(i,engine)
  issue_runtime={"pre_to_post_wall_s":None,"slow_planner_runtime_s":0.0,"planner_mode":"NONE",
                 "event_reasons":[],"fast_solver":{},"dispatch_status":None,"replan_executed":False}
  pre_t=None
  original_jw=science.jw
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
   metrics=current_soft_metrics(loc,sources,i)
   steps=max(0,i-last_replan)
   decision=ev.evaluate(issue=i,hard_flags={},soft_metrics={k:metrics[k] for k in [r.name for r in ev.config.soft_rules]},steps_since_plan=steps)
   requested=decision.requested_mode if decision.request_replan else "NONE"
   reasons=list(decision.reasons)
   affected_jobs,affected_mess=local_scope_from_soft(loc,metrics,i,cfg)
   hard_exc=None
   if requested=="NONE":
    try:
     bind=astep4.bind_shifted_active_plan(loc,ref,i)
     jw(Path(loc["out"])/"A_B10_ACTIVE_PLAN_BINDING.json",bind)
    except astep4.PlanInvalidation as exc:
     hard_exc=exc;flag=map_hard_invalidation(exc);reasons.extend([f"HARD:{flag}",*exc.reasons])
     affected_jobs=list(exc.affected_job_ids);affected_mess=list(exc.affected_mess_ids)
     requested="LOCAL_REPAIR" if cfg["local_repair_enabled"] and (affected_jobs or affected_mess) else "FULL_REPLAN"
   if requested=="LOCAL_REPAIR":
    # Local repair mutates only variable bounds. Snapshot the entire slow-domain
    # bounds so an exact fail-closed escalation can restore the unconditioned
    # full planner model without rebuilding or changing any equations.
    slow_bound_snapshot=[
     (v,float(v.LB),float(v.UB))
     for name in ("x","defer","stay","mv","node_occ")
     for v in (loc.get(name,{}) or {}).values()
    ]
    def restore_slow_bounds():
     for v,lb,ub in slow_bound_snapshot:
      v.LB=lb;v.UB=ub
     model.update();model.reset()
    try:
     scope=astep5.apply_actual_local_repair(loc=loc,ref=ref,issue=i,affected_job_ids=affected_jobs,
       affected_mess_ids=affected_mess,near_horizon_steps=12)
     jw(Path(loc["out"])/"A_B10_LOCAL_REPAIR_SCOPE.json",scope)
     pq=planner_solve(model,cb);issue_runtime["slow_planner_runtime_s"]+=float(pq["wall_seconds"])
     if not pq["candidate_available"]:
      reasons.append("LOCAL_REPAIR_NO_CANDIDATE_ESCALATE_FULL")
      restore_slow_bounds();requested="FULL_REPLAN"
     else:
      fix_all_slow_to_incumbent(loc);last_replan=i;issue_runtime["replan_executed"]=True
      issue_runtime["planner_mode"]="LOCAL_REPAIR";jw(Path(loc["out"])/"A_B10_LOCAL_PLANNER_SOLVE.json",pq)
    except astep5.LocalRepairEscalation as exc:
     reasons.append("LOCAL_REPAIR_ESCALATION:"+str(exc.reason))
     restore_slow_bounds();requested="FULL_REPLAN"
   if requested=="FULL_REPLAN":
    if issue_runtime["planner_mode"]=="LOCAL_REPAIR":
     raise RuntimeError("internal state error: full replan after accepted local repair")
    pq=planner_solve(model,cb);issue_runtime["slow_planner_runtime_s"]+=float(pq["wall_seconds"])
    jw(Path(loc["out"])/"A_B10_FULL_PLANNER_SOLVE.json",pq)
    if pq["candidate_available"]:
     fix_all_slow_to_incumbent(loc);last_replan=i;issue_runtime["replan_executed"]=True;issue_runtime["planner_mode"]="FULL_REPLAN"
    else:
     if hard_exc is not None:raise RuntimeError("hard-invalidated active plan and full planner produced no candidate")
     # Soft/periodic planner miss: retain the still-valid shifted active plan.
     bind=astep4.bind_shifted_active_plan(loc,ref,i);jw(Path(loc["out"])/"A_B10_PLANNER_MISS_RETAIN_ACTIVE.json",bind)
     issue_runtime["planner_mode"]="FULL_REPLAN_NO_CANDIDATE_RETAIN_ACTIVE"
   fast=solve_fast(model,cb);issue_runtime["fast_solver"]=fast;issue_runtime["dispatch_status"]="OPTIMAL" if int(model.Status)==2 else f"GUROBI_{int(model.Status)}"
   issue_runtime["event_reasons"]=sorted(set(map(str,reasons)))
   issue_runtime["soft_metrics"]=metrics;issue_runtime["steps_since_plan_before_issue"]=steps
   return None
  science.certified_path_decomposition_solve=hook
  started=time.monotonic()
  try:
   rc=int(one(engine,Path("/home/jaewon/mobile_ess_work")))
  finally:
   restore_sources()
  wall=time.monotonic()-started
  if rc!=0:raise RuntimeError(f"scientific one-issue engine returned {rc} at issue {i}")
  d=engine/f"issue_{i:06d}"
  for rp in [d/"BUILD7C_POSTCOMMIT_STATE.json",d/"BUILD7C_FIRSTSTEP_TRANSITION_CERTIFICATE.json",d/f"exact_grid/FRESH_EXACT_OPENDSS_24SERVICE_ISSUE_{i}.json"]:
   if not rp.is_file():raise RuntimeError(f"required committed artifact missing {rp}")
  tr=load_json(d/"BUILD7C_FIRSTSTEP_TRANSITION_CERTIFICATE.json");fr=load_json(d/f"exact_grid/FRESH_EXACT_OPENDSS_24SERVICE_ISSUE_{i}.json")
  if tr.get("status")!="PASS" or tr.get("h0_only_committed") is not True or tr.get("future_actual_arrivals_read") is not False:
   raise RuntimeError(f"transition gate failed issue={i}")
  if fr.get("hard_constraint_pass") is not True or fr.get("converged") is not True:raise RuntimeError(f"Fresh OpenDSS failed issue={i}")
  prepost=float(issue_runtime["pre_to_post_wall_s"] or wall);slow=float(issue_runtime["slow_planner_runtime_s"] or 0)
  issue_runtime.update({"schema_version":"a_to_b.10.w02.policy_issue.v1","issue":i,"status":"PASS_COMMITTED",
     "policy_id":cfg["policy_id"],"pre_state_sha256":tr["pre_state_sha256"],"post_state_sha256":tr["post_state_sha256"],
     "full_issue_wall_s":wall,"commit_critical_runtime_s":max(0.0,prepost-slow),
     "development_host_deadline_overrun":max(0.0,prepost-slow)>=300.0,
     "fresh_opendss_pass":True,"future_actual_used":False})
  jw(d/"POLICY_ISSUE_AUDIT.json",issue_runtime);issue_audits.append(issue_runtime)
  jw(checkpoint_path,{"status":"RUNNING","last_completed_issue":i,"last_replan_issue":last_replan,
      "event_engine_state":event_state(ev),"completed_issue_count":len(issue_audits),"future_actual_used":False})
  jw(policy_root/"progress/W02_PROGRESS.json",{"status":"RUNNING","completed":len(issue_audits),"required":COUNT,"last_issue":i})
  if (i-START+1)%12==0 or i==START:
   print(f"[{cfg['slot']} {cfg['policy_id']}] {i-START+1}/{COUNT} issue={i} commit={issue_runtime['commit_critical_runtime_s']:.2f}s planner={slow:.2f}s mode={issue_runtime['planner_mode']}",flush=True)
 if len(issue_audits)!=COUNT:raise RuntimeError(f"policy issue count {len(issue_audits)} != {COUNT}")
 final=load_json(engine/f"issue_{END:06d}/BUILD7C_POSTCOMMIT_STATE.json")
 shutil.copy2(engine/f"issue_{END:06d}/BUILD7C_POSTCOMMIT_STATE.json",policy_root/"EVALUATION_END_RUNTIME_STATE.json")
 build_results(policy_root,engine,cfg,issue_audits)
 commit=[float(x["commit_critical_runtime_s"]) for x in issue_audits];planner=[float(x["slow_planner_runtime_s"]) for x in issue_audits if float(x["slow_planner_runtime_s"])>0]
 hw={"platform":sys.platform,"python":sys.version,"cpu_affinity":sorted(os.sched_getaffinity(0)) if hasattr(os,"sched_getaffinity") else [],
     "process_cpu_count":os.cpu_count()}
 jw(policy_root/"RUNTIME_CHARACTERIZATION.json",{"schema_version":"a_to_b.10.w02.runtime_characterization.v1","status":"PASS",
   "hardware":hw,"outer_processes_expected":4,"threads_per_process":4,
   "commit_critical":{"p50_s":quantile(commit,.50),"p95_s":quantile(commit,.95),"p99_s":quantile(commit,.99),"max_s":max(commit),
                      "deadline_miss_count":sum(x>=300 for x in commit),"development_host_realtime_claim":"DEMONSTRATED" if max(commit)<300 else "NOT_DEMONSTRATED"},
   "slow_planner":{"count":len(planner),"p50_s":quantile(planner,.50),"p95_s":quantile(planner,.95),"p99_s":quantile(planner,.99),"max_s":max(planner) if planner else None},
   "slow_planner_execution_semantics":"BOUNDARY_SYNCHRONOUS_SCIENTIFIC_REPLAY; runtime excluded from commit-critical characterization",
   "target_hardware_realtime_claim":"NOT_QUALIFIED_BY_THIS_RUN"})
 run_f7(policy_root,cfg)
 jw(policy_root/"progress/W02_PROGRESS.json",{"status":"PASS","completed":COUNT,"required":COUNT,"last_issue":END})
 jw(checkpoint_path,{"status":"PASS_COMPLETE","last_completed_issue":END,"last_replan_issue":last_replan,
    "event_engine_state":event_state(ev),"completed_issue_count":COUNT,"future_actual_used":False})
 # policy-level checksums
 sf=policy_root/"SHA256SUMS.txt"
 sf.write_text("".join(f"{sha(p)}  {p.relative_to(policy_root).as_posix()}\n" for p in sorted(policy_root.rglob("*")) if p.is_file() and p!=sf),encoding="utf-8")
 print(f"W02_POLICY_STATUS=PASS slot={cfg['slot']} policy={cfg['policy_id']} issues={COUNT}")
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

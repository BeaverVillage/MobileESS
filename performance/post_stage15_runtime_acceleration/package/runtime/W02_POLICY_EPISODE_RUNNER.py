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
 for name in ("x","defer","stay","mv","node_occ"):
  d=loc.get(name,{}) or {};counts[name]=len(d)
  for v in d.values():set_fixed(v,1.0 if float(v.X)>=0.5 else 0.0)
 loc["m"].update()
 return counts

def fix_all_slow_from_model(loc:Mapping[str,Any],source_model)->dict[str,int]:
 counts={}
 for name in ("x","defer","stay","mv","node_occ"):
  d=loc.get(name,{}) or {};counts[name]=len(d)
  for v in d.values():
   source_v=source_model.getVarByName(str(v.VarName))
   if source_v is None:raise RuntimeError(f"planner-copy variable missing {v.VarName}")
   set_fixed(v,1.0 if float(source_v.X)>=0.5 else 0.0)
 loc["m"].update()
 return counts

def residual_integer_names(model)->list[str]:
 return [str(v.VarName) for v in model.getVars() if str(v.VType).upper() in {"B","I","S","N"} and float(v.UB)-float(v.LB)>1e-12]

def solve_fast(model,cb)->dict[str,Any]:
 import gurobipy as gp
 model.Params.Threads=4;model.Params.MIPGap=0.03;model.Params.MIPGapAbs=0.0;model.Params.MIPFocus=1
 # The slow planner may use a benchmarked search-only presolve policy.  The
 # conditioned dispatch is the frozen physical-commit authority and must not
 # inherit that temporary planner setting through the reused Model object.
 model.Params.Presolve=-1
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
 presolve=int(os.environ.get("MOBILEESS_PLANNER_PRESOLVE","-1"))
 if presolve not in {-1,0,1,2}:raise RuntimeError(f"unsupported MOBILEESS_PLANNER_PRESOLVE={presolve}")
 model.Params.Presolve=presolve
 t=time.monotonic();model.optimize(cb) if cb is not None else model.optimize();wall=time.monotonic()-t
 q=abase.solver_quality(model);q["wall_seconds"]=wall;q["candidate_available"]=int(model.SolCount)>0;q["presolve_setting"]=presolve
 return q

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
 issue_audits=[]
 for i in range(START,run_end+1):
  auditp=engine/f"issue_{i:06d}/POLICY_ISSUE_AUDIT.json"
  postp=engine/f"issue_{i:06d}/BUILD7C_POSTCOMMIT_STATE.json"
  if auditp.is_file() and postp.is_file():
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
   try:
    return performance_build_full(scope,b4,op1,build_issue,queue,running,inventory,dest_commit,
                                  mess_E,science_ref,*args,**kwargs)
   finally:
    b4.conservative_fixed=original_conservative_fixed
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
   affected_jobs,affected_mess=local_scope_from_soft(loc,metrics,i,cfg)
   def solve_planner_candidate():
    if a.benchmark_sparse_planner_copy and not fixed_location:
     return planner_solve_sparse_copy(model,cb)
    return planner_solve(model,cb),None
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
   if requested=="FULL_REPLAN":
    if issue_runtime["planner_mode"]=="LOCAL_REPAIR":
     raise RuntimeError("internal state error: full replan after accepted local repair")
    pq,planner_model=solve_planner_candidate();issue_runtime["slow_planner_runtime_s"]+=float(pq["wall_seconds"])
    jw(Path(loc["out"])/"A_B10_FULL_PLANNER_SOLVE.json",pq)
    if pq["candidate_available"]:
     accept_planner_candidate(planner_model);last_replan=i;issue_runtime["replan_executed"]=True;issue_runtime["planner_mode"]="FULL_REPLAN"
    else:
     if planner_model is not None:planner_model.dispose()
     if hard_exc is not None:raise RuntimeError("hard-invalidated active plan and full planner produced no candidate")
     # Soft/periodic planner miss: retain the still-valid shifted active plan.
     bind=astep4.bind_shifted_active_plan(loc,ref,i);jw(Path(loc["out"])/"A_B10_PLANNER_MISS_RETAIN_ACTIVE.json",bind)
     issue_runtime["planner_mode"]="FULL_REPLAN_NO_CANDIDATE_RETAIN_ACTIVE"
   if use_sparse_restore and os.environ.get("MOBILEESS_POST15_SKIP_REDUNDANT_DENSE_B4_CUTS","0")=="1":
    issue_runtime["dense_b4_restore"]=restore_redundant_dense_b4_rows(loc)
   fast=solve_fast(model,cb);issue_runtime["fast_solver"]=fast;issue_runtime["dispatch_status"]="OPTIMAL" if int(model.Status)==2 else f"GUROBI_{int(model.Status)}"
   issue_runtime["event_reasons"]=sorted(set(map(str,reasons)))
   issue_runtime["soft_metrics"]=metrics;issue_runtime["steps_since_plan_before_issue"]=steps
   return None
  science.certified_path_decomposition_solve=hook
  started=time.monotonic();cpu_started=time.process_time()
  def execute_one_issue()->int:
   science.build_full=prebuild_event_conditioning
   restore=install_source_bindings(science,r12,sources,power,price,i,engine/f"issue_{i:06d}")
   try:return int(one(engine,Path("/home/jaewon/mobile_ess_work")))
   finally:
    restore();science.build_full=performance_build_full
  with book.phase("science_one_issue_total",i,issue_runtime):
   rc=execute_one_issue()
   failure_path=engine/"_FAILURE.json"
   failure=load_json(failure_path) if rc!=0 and failure_path.is_file() else {}
   retryable=("A_B10_ACTIVE_PLAN_MOBILITY_PROJECTION_" in str(failure.get("error","")))
   if retryable:
    retry_root=policy_root/"interrupted_attempts"/datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")/f"issue_{i:06d}_projected_retry"
    retry_root.mkdir(parents=True,exist_ok=True)
    issue_dir=engine/f"issue_{i:06d}"
    if issue_dir.exists():shutil.move(str(issue_dir),str(retry_root/issue_dir.name))
    if failure_path.exists():shutil.move(str(failure_path),str(retry_root/failure_path.name))
    os.environ["MOBILEESS_ACTIVE_PLAN_MOBILITY_PROJECTION"]="0"
    issue_runtime["active_projection_retry_full_domain"]=True
    rc=execute_one_issue()
  wall=time.monotonic()-started
  if rc!=0:raise RuntimeError(f"scientific one-issue engine returned {rc} at issue {i}")
  d=engine/f"issue_{i:06d}"
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
    "max_rss_mib":book.rss_mib(),"science_runtime_events":list(getattr(science,"_RUNTIME_EVENTS",[]))})
  jw(d/"POLICY_ISSUE_AUDIT.json",issue_runtime);issue_audits.append(issue_runtime)
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

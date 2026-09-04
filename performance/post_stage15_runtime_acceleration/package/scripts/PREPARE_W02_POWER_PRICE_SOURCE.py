#!/usr/bin/env python3
"""Materialize one frozen P/Q/PV and price source chunk."""
from __future__ import annotations
import argparse,hashlib,importlib.util,json,shutil,sys,tempfile
from pathlib import Path
import numpy as np

START=3456
BLOCK=576
BLOCKS=4
SCORED_END=5471
PADDED_END=5759
FORECAST_SHA="d0e10553851cd9cbaf08cd01009915454d2c81eb0366e36fdd916a54b039fb65"
R7_SOURCE_SHA="f712d096e9b8ae5efc12ad01aef6ca28ce5d5cb313a2b22f8db1a5765ffeb735"
KEEP_POWER=(
 "issues","target_steps","q90_gross_background_p_kw","q10_pv_available_kw",
 "q90_background_q_kvar","q50_net_background_p_kw","q50_background_q_kvar",
 "q_persistence_source_index","q_persistence_factor",
)
KEEP_PRICE=("issues","target_steps","q10","q50","q90")

def sha(p:Path)->str:
 h=hashlib.sha256()
 with p.open("rb") as f:
  for b in iter(lambda:f.read(8<<20),b""):h.update(b)
 return h.hexdigest()
def load(path:Path,name:str):
 spec=importlib.util.spec_from_file_location(name,path)
 if spec is None or spec.loader is None:raise RuntimeError(path)
 m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m
def jw(p:Path,o):
 p.write_text(json.dumps(o,indent=2,sort_keys=True,allow_nan=False)+"\n",encoding="utf-8")
def main():
 ap=argparse.ArgumentParser();ap.add_argument("--repo",required=True);ap.add_argument("--output-root",required=True)
 ap.add_argument("--candidate-id",default="W02_2025-01-13");ap.add_argument("--start-index",type=int,default=START)
 ap.add_argument("--scored-count",type=int,default=2016)
 ap.add_argument("--base-work",default="/home/jaewon/mobile_ess_work");a=ap.parse_args()
 repo=Path(a.repo).resolve();out=Path(a.output_root).resolve();base=Path(a.base_work).resolve()
 start=int(a.start_index)
 if not 1<=a.scored_count<=BLOCK*BLOCKS:raise RuntimeError("scored-count must be in [1,2304]")
 scored_end=start+a.scored_count-1;padded_end=start+BLOCK*BLOCKS-1
 out.mkdir(parents=True,exist_ok=True)
 helper=load(repo/"stage7/r12_representative_weeks/materialize_r12_episode_power_price.py","a_b10_pp_helper")
 forecast=base/"execution_packages/Mobile_ESS_stage_p6a4h1b_p7a3f1b_conditional_dag_parallel_v3_0_1/assets/forecast/P6A3_FULL_YEAR_CAUSAL_FORECAST.npz"
 r7_path=base/"stage7_t2_power_price_r7/A_TO_C_T2_R7_20260815T052954Z/power/source_tree/main.py"
 if sha(forecast)!=FORECAST_SHA or sha(r7_path)!=R7_SOURCE_SHA:raise RuntimeError("frozen power/price source SHA drift")
 r7=load(r7_path,"a_b10_r7_power")
 resolved,kernel,work,temps=helper.build_r7_context(r7)
 if sha(resolved)!=FORECAST_SHA:raise RuntimeError("resolved forecast SHA drift")
 records=[]
 try:
  for bi in range(BLOCKS):
   lo=start+bi*BLOCK;hi=lo+BLOCK;issues=np.arange(lo,hi,dtype=np.int32)
   bd=out/f"block_{bi:02d}_{lo}_{hi-1}";bd.mkdir(exist_ok=True)
   auth=bd/"BLOCK_AUTHORITY.json"
   if auth.is_file():
    old=json.loads(auth.read_text())
    if old.get("status")!="PASS" or old.get("candidate_id",a.candidate_id)!=a.candidate_id or old.get("issue_first")!=lo or old.get("issue_last")!=hi-1 or old.get("scored_overlap_first")!=max(lo,start) or old.get("scored_overlap_last")!=min(hi-1,scored_end):raise RuntimeError("existing source block authority drift")
    records.append(old);continue
   pdir=bd/"power_tmp";pdir.mkdir()
   prec=helper.materialize_power(r7,resolved,kernel,work,issues,pdir)
   pnpz=Path(prec["path"])
   with np.load(pnpz,allow_pickle=False) as z:
    for key in KEEP_POWER:
     if key not in z.files:raise RuntimeError(f"power key missing {key}")
     np.save(bd/f"power__{key}.npy",np.asarray(z[key]),allow_pickle=False)
   price_npz=bd/"price_tmp.npz";pr=helper.materialize_price(forecast,issues,price_npz)
   with np.load(price_npz,allow_pickle=False) as z:
    for key in KEEP_PRICE:np.save(bd/f"price__{key}.npy",np.asarray(z[key]),allow_pickle=False)
   psha={key:sha(bd/f"power__{key}.npy") for key in KEEP_POWER}
   qsha={key:sha(bd/f"price__{key}.npy") for key in KEEP_PRICE}
   pnpz.unlink(missing_ok=True);price_npz.unlink(missing_ok=True);shutil.rmtree(pdir,ignore_errors=True)
   rec={"status":"PASS","candidate_id":a.candidate_id,"block":bi,"issue_first":lo,"issue_last":hi-1,"issue_count":BLOCK,
        "power_fields":psha,"price_fields":qsha,"forecast_sha256":FORECAST_SHA,
        "r7_source_sha256":R7_SOURCE_SHA,"future_actual_used":False,
        "scored_overlap_first":max(lo,start),"scored_overlap_last":min(hi-1,scored_end)}
   jw(auth,rec);records.append(rec)
 finally:
  for t in temps:shutil.rmtree(t,ignore_errors=True)
 top={"schema_version":"mobileess.post_stage15.rep_week.power_price_blocks.v2","status":"PASS","candidate_id":a.candidate_id,
      "scored_issue_first":start,"scored_issue_last":scored_end,"scored_issue_count":a.scored_count,
      "source_issue_last":padded_end,"source_block_steps":BLOCK,"block_count":BLOCKS,
      "extra_source_cache_steps":BLOCK*BLOCKS-a.scored_count,
      "extra_source_cache_role":("NONE_ALL_SOURCE_ISSUES_SCORED" if a.scored_count==BLOCK*BLOCKS else "UNSCORED_CAUSAL_SOURCE_PADDING"),
      "future_actual_used":False,"blocks":records}
 jw(out/"REP_WEEK_POWER_PRICE_SOURCE_AUTHORITY.json",top)
 if a.candidate_id=="W02_2025-01-13":jw(out/"A_B10_W02_POWER_PRICE_SOURCE_AUTHORITY.json",top)
 print(json.dumps(top,indent=2))
if __name__=="__main__":raise SystemExit(main())

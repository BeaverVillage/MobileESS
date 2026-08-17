#!/usr/bin/env python3
"""Outcome-blind dry-run of the frozen postprocessing plan on synthetic data only."""
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

METHODS=("M1","M2","M3","M4")
CONTRASTS=("M3-M2","M1-M3","M1-M4","M1-M2")
FIGURES=("cost","grid_voltage_loading","mess_soc_pq","mess_mobility","job_sla","rack","wan","debt_rebound","controller_events","runtime_ac_recovery")
def sha(p:Path)->str:return hashlib.sha256(p.read_bytes()).hexdigest()
def km_table(duration,event):
 at=len(duration);survival=1.0;rows=[]
 for t in sorted(set(duration)):
  d=sum(1 for x,e in zip(duration,event) if x==t and e);c=sum(1 for x,e in zip(duration,event) if x==t and not e)
  if at and d:survival*=1-d/at
  rows.append({"time_min":t,"at_risk":at,"events":d,"censored":c,"survival":survival});at-=d+c
 return rows
def main():
 a=argparse.ArgumentParser();a.add_argument("--output",type=Path,required=True);x=a.parse_args();x.output.mkdir(parents=True,exist_ok=True)
 rng=np.random.default_rng(20260816);rows=[]
 weights=np.asarray([.07,.08,.08,.08,.08,.08,.08,.08,.08,.08,.09,.10]);weights/=weights.sum()
 effect={"M1":-2.0,"M2":0.0,"M3":-0.8,"M4":1.5}
 for w in range(12):
  shared=rng.normal(100,5,7)
  for m in METHODS:
   for day in range(7):
    rows.append({"week_id":f"W{w+1:02d}","week_index":w,"day":day,"method":m,"weight":weights[w],
     "economic_cost_AUD":shared[day]+effect[m]+rng.normal(0,.4),"vmax_pu":1.03+rng.normal(0,.002),
     "line_loading_pu":.65+rng.normal(0,.03),"soc_pct":65+rng.normal(0,4),"mess_p_kw":rng.normal(0,80),
     "rack_utilization":.55+rng.normal(0,.04),"wan_GB":max(0,rng.normal(8,2)),"deadline_miss":int(rng.random()<.03),
     "debt_GPUh":max(0,rng.normal(.2,.1)),"replan_count":int(rng.random()<.15),"runtime_s":max(.1,rng.normal(35,4)),
     "ac_recovery_count":int(rng.random()<.02)})
 df=pd.DataFrame(rows);df.to_parquet(x.output/"SYNTHETIC_DAILY_INPUT.parquet",index=False)
 contrasts=[]
 for label in CONTRASTS:
  a1,b1=label.split("-");p=df.pivot_table(index=["week_index","day","weight"],columns="method",values="economic_cost_AUD").reset_index()
  p["delta"]=p[a1]-p[b1];week=p.groupby(["week_index","weight"],as_index=False)["delta"].mean()
  estimate=float(np.sum(week["weight"]*week["delta"])/np.sum(week["weight"]))
  boots=[]
  for _ in range(1000):
   idx=rng.integers(0,len(week),len(week));s=week.iloc[idx];boots.append(float(np.sum(s["weight"]*s["delta"])/np.sum(s["weight"])))
  contrasts.append({"contrast":label,"role":"PRIMARY" if label!="M1-M2" else "SECONDARY","estimate":estimate,
   "ci_low":float(np.quantile(boots,.025)),"ci_high":float(np.quantile(boots,.975)),"resampling_unit":"REPRESENTATIVE_WEEK"})
 pd.DataFrame(contrasts).to_csv(x.output/"PAIRED_CONTRASTS.csv",index=False)
 durations=rng.integers(5,241,200).tolist();events=(rng.random(200)>.12).tolist();pd.DataFrame(km_table(durations,events)).to_csv(x.output/"F7_KAPLAN_MEIER.csv",index=False)
 numeric=[c for c in df.columns if c not in {"week_id","method"}]
 for name in FIGURES:
  metric={"cost":"economic_cost_AUD","grid_voltage_loading":"vmax_pu","mess_soc_pq":"soc_pct","mess_mobility":"mess_p_kw",
   "job_sla":"deadline_miss","rack":"rack_utilization","wan":"wan_GB","debt_rebound":"debt_GPUh","controller_events":"replan_count",
   "runtime_ac_recovery":"runtime_s"}[name]
  fig,ax=plt.subplots(figsize=(5,3));df.groupby("method")[metric].mean().reindex(METHODS).plot.bar(ax=ax);ax.set_title(f"SYNTHETIC DRY RUN — {name}");fig.tight_layout()
  fig.savefig(x.output/f"FIG_{name}.png",dpi=100);plt.close(fig)
 files=sorted(p for p in x.output.iterdir() if p.is_file())
 manifest={"schema_version":"mobileess.pre_w02.analysis_dryrun.v1","status":"PASS","scientific_result":False,
  "input_semantics":"DETERMINISTIC_SYNTHETIC_NON_EVALUATION_DATA","production_runner_imported":False,"gurobi_solve_count":0,"opendss_solve_count":0,
  "primary_contrasts":["M3-M2","M1-M3","M1-M4"],"secondary_contrasts":["M1-M2"],"day_level_aggregation":True,
  "representative_week_weighting":True,"week_cluster_bootstrap":True,"F7_right_censoring":True,"kaplan_meier":True,
  "figure_families":list(FIGURES),"files":{p.name:sha(p) for p in files}}
 (x.output/"MANIFEST.json").write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\n",encoding="utf-8");print(x.output/"MANIFEST.json")
if __name__=="__main__":main()

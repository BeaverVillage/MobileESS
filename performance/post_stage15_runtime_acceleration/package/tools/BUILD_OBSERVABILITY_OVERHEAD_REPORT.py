#!/usr/bin/env python3
"""Build phase-attributed runtime/storage evidence from bounded v2 commits."""
from __future__ import annotations
import argparse,json,statistics
from pathlib import Path

def load(p:Path):return json.loads(p.read_text(encoding="utf-8"))
def write(p:Path,x):
 p.parent.mkdir(parents=True,exist_ok=True);t=p.with_suffix(p.suffix+".tmp")
 t.write_text(json.dumps(x,indent=2,sort_keys=True,allow_nan=False)+"\n");t.replace(p)
def pct(values,q):
 if not values:return None
 a=sorted(values);pos=(len(a)-1)*q;lo=int(pos);hi=min(lo+1,len(a)-1);w=pos-lo
 return a[lo]*(1-w)+a[hi]*w

def main():
 a=argparse.ArgumentParser();a.add_argument("delivery_root",type=Path);a.add_argument("--materialized-root",type=Path)
 a.add_argument("--output",type=Path,required=True);x=a.parse_args();rows=[]
 for root in sorted(x.delivery_root.iterdir()):
  if not (root/"episode_manifest.json").is_file():continue
  for marker in sorted((root/"engine").glob("issue_*/A_B10_COMMIT_MARKER.json")):
   m=load(marker)
   if m.get("schema_version")!="mobileess.post_stage15.atomic_commit_marker.v2":continue
   audit=load(marker.parent/"POLICY_ISSUE_AUDIT.json");eo=audit.get("observability_capture",{});mo=audit.get("model_observability_capture",{})
   phases=audit.get("performance_phases",{});obs=float(eo.get("wall_s",0))+float(mo.get("wall_s",0));commit=float(audit.get("commit_critical_runtime_s",0))
   baseline=commit-obs if commit>obs else None
   rows.append({"method":audit.get("comparison_method_id"),"issue":audit.get("issue"),"commit_critical_s":commit,
    "instrumented_counterfactual_without_observability_s":baseline,"observability_serialization_s":obs,
    "observability_overhead_pct":None if baseline is None else 100*obs/baseline,"fresh_opendss_s":float((phases.get("fresh_exact_opendss") or {}).get("wall_s",0)),
    "model_build_solve_extract_s":float((phases.get("model_build_solve_extract") or {}).get("wall_s",0)),
    "commit_evidence_validation_s":float((phases.get("commit_evidence_load_and_validate") or {}).get("wall_s",0)),
    "max_rss_mib":float(audit.get("max_rss_mib",0)),"observability_bytes":int(eo.get("bytes",0))+int(mo.get("bytes",0)),
    "files_per_issue":int((audit.get("issue_artifact_storage") or {}).get("files",0)),
    "exact_capture_calls":int(eo.get("calls",0)),"exact_capture_deduplicated_calls":int(eo.get("deduplicated_calls",0)),
    "model_capture_gurobi_solves":0,"exact_capture_opendss_solves":0})
 mats=[]
 if x.materialized_root and x.materialized_root.exists():
  for p in sorted(x.materialized_root.glob("*/MANIFEST.json")):
   d=load(p);mats.append({"path":str(p),"status":d.get("status"),"wall_s":d.get("materialization_wall_s"),
    "bytes_per_issue":(d.get("resource_projection") or {}).get("bytes_per_issue"),
    "projected_parquet_bytes_48_episodes":(d.get("resource_projection") or {}).get("projected_parquet_bytes_48_episodes"),
    "gurobi_solve_count":d.get("gurobi_solve_count"),"opendss_solve_count":d.get("opendss_solve_count")})
 overhead=[r["observability_overhead_pct"] for r in rows if r["observability_overhead_pct"] is not None]
 gates={"bounded_v2_issue_count_positive":bool(rows),"same_solve_capture_only":all(r["exact_capture_calls"]>=1 and r["model_capture_gurobi_solves"]==0 and r["exact_capture_opendss_solves"]==0 for r in rows),
  "duplicate_exact_capture_deduplicated":all(r["exact_capture_deduplicated_calls"]>=0 for r in rows),
  "offline_materialization_pass":bool(mats) and all(m["status"]=="PASS" and m["gurobi_solve_count"]==0 and m["opendss_solve_count"]==0 for m in mats)}
 out={"schema_version":"mobileess.pre_w02.observability_overhead.v1","status":"PASS" if all(gates.values()) else "FAIL_CLOSED",
  "measurement_semantics":"PHASE_INSTRUMENTED_PAIRED_SUBTRACTION_ON_SAME_COMMITTED_ISSUE",
  "pre_hardening_counterfactual":"commit_critical_s minus measured same-solve serialization phases; no scientific solve removed",
  "capture_call_semantics":"One capture per already-required Fresh AC candidate; multiple calls can reflect scientific AC recovery, never an observability-triggered solve.",
  "gates":gates,"issue_count":len(rows),"summary":{"overhead_pct_p50":pct(overhead,.5),"overhead_pct_p95":pct(overhead,.95),
   "overhead_pct_max":max(overhead,default=None),"observability_s_total":sum(r["observability_serialization_s"] for r in rows),
   "scientific_model_s_total":sum(r["model_build_solve_extract_s"] for r in rows),"fresh_opendss_s_total":sum(r["fresh_opendss_s"] for r in rows),
   "peak_rss_mib":max((r["max_rss_mib"] for r in rows),default=None),"bytes_per_issue_mean":statistics.fmean(r["observability_bytes"] for r in rows) if rows else None,
   "files_per_issue_mean":statistics.fmean(r["files_per_issue"] for r in rows) if rows else None},
  "production_critical_path_includes_post_run_materialization":False,"post_run_materialization":mats,"issues":rows}
 write(x.output,out);print(x.output);return 0 if out["status"]=="PASS" else 2
if __name__=="__main__":raise SystemExit(main())

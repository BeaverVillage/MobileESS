#!/usr/bin/env python3
from __future__ import annotations
import argparse,csv,json,hashlib
from pathlib import Path

POLICIES={
"M1_PROPOSED_EVENT30_LOCAL_REPAIR_MOBILE":"PROPOSED_EVENT30_LOCAL_REPAIR",
"M2_FIXED30_MOBILE":"FIXED30",
"M3_EVENT30_NO_LOCAL_REPAIR_MOBILE":"EVENT30_NO_LOCAL_REPAIR",
"M4_FIXED_LOCATION_ESS_MOBILITY_ABLATION":"M4_FIXED_LOCATION_ESS_MOBILITY_ABLATION",
}
TABLES=[
"rolling_step","job_event","rack_step","wan_event","mess_step","debt_step",
"constraint_event","forecast_eval","grid_exact_ac_bus_phase","grid_exact_ac_summary",
"optimization_stats","run_summary",
]
def load(p): return json.loads(Path(p).read_text(encoding="utf-8"))
def main():
 ap=argparse.ArgumentParser(); ap.add_argument("--delivery-root",required=True)
 ap.add_argument("--candidate-id",default="W02_2025-01-13");ap.add_argument("--start-index",type=int,default=3456);a=ap.parse_args()
 root=Path(a.delivery_root)
 expected_end=a.start_index+2015
 failures=[]; details=[]
 for pd,expected_policy_id in POLICIES.items():
  p=root/pd
  if not p.is_dir(): failures.append(f"missing policy dir {pd}"); continue
  for req in ["episode_manifest.json","CONTROLLER_POLICY_MANIFEST.json","EVALUATION_END_RUNTIME_STATE.json","F7_JOB_EVENT_COHORT_COVERAGE_CERTIFICATE_V1.json"]:
   if not (p/req).is_file(): failures.append(f"{pd}: missing {req}")
  missing=[]
  for t in TABLES:
   candidates=[p/f"{t}.csv",p/f"{t}.parquet",p/f"{t}.jsonl"]
   if not any(x.is_file() for x in candidates): missing.append(t)
  if missing: failures.append(f"{pd}: missing result tables {missing}")
  if (p/"episode_manifest.json").is_file():
   m=load(p/"episode_manifest.json")
   if m.get("scenario_id",m.get("candidate_id"))!=a.candidate_id: failures.append(f"{pd}: wrong representative-week scenario")
   if int(m.get("evaluation_start_step",-1))!=a.start_index or int(m.get("evaluation_end_step_inclusive",-1))!=expected_end:
    failures.append(f"{pd}: wrong evaluation boundaries")
   if int(m.get("controller_burn_in_steps",-1))!=0: failures.append(f"{pd}: burn-in must be 0")
   if m.get("method_id")!="B5": failures.append(f"{pd}: method_id must be B5")
  if (p/"CONTROLLER_POLICY_MANIFEST.json").is_file():
   cpm=load(p/"CONTROLLER_POLICY_MANIFEST.json")
   if cpm.get("policy_id")!=expected_policy_id:
    failures.append(f"{pd}: wrong policy_id {cpm.get('policy_id')!r}, expected {expected_policy_id!r}")
  if (p/"F7_JOB_EVENT_COHORT_COVERAGE_CERTIFICATE_V1.json").is_file():
   c=load(p/"F7_JOB_EVENT_COHORT_COVERAGE_CERTIFICATE_V1.json")
   if c.get("coverage_pass") is not True: failures.append(f"{pd}: F7 coverage not PASS")
  details.append({"policy":pd,"tables_required":12,"structure_checked":True})
 status="PASS_W02_M1_M4_DELIVERY_STRUCTURE" if not failures else "FAIL_CLOSED"
 print(json.dumps({"status":status,"failures":failures,"details":details},indent=2))
 raise SystemExit(0 if not failures else 2)
if __name__=="__main__": main()

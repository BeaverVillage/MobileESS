#!/usr/bin/env python3
from __future__ import annotations
import argparse,json
from pathlib import Path

def main():
 ap=argparse.ArgumentParser()
 ap.add_argument("--episode-root",required=True)
 ap.add_argument("--certificate",required=True)
 ap.add_argument("--output",required=True)
 a=ap.parse_args();ep=Path(a.episode_root);cp=Path(a.certificate);out=Path(a.output);out.mkdir(parents=True,exist_ok=True)
 m=json.loads((ep/"episode_manifest.json").read_text())
 c=json.loads(cp.read_text())
 req=["certificate_version","episode_id","method_id","month","evaluation_start_step","evaluation_end_step",
      "expected_evaluation_arrival_job_count","logged_job_event_evaluation_arrival_job_count",
      "pending_evaluation_arrival_jobs_at_evaluation_end","coverage_pass","independent_source_kind","independent_source_sha256"]
 miss=[k for k in req if k not in c]
 if miss:raise RuntimeError(f"coverage certificate missing {miss}")
 if c["certificate_version"]!="K9H7_F7_COVERAGE_V1":raise RuntimeError("coverage certificate version drift")
 for k in ["episode_id","method_id","month","evaluation_start_step","evaluation_end_step"]:
  if str(c[k])!=str(m[k]):raise RuntimeError(f"coverage/manifest mismatch: {k}")
 if bool(c["coverage_pass"]) is not True:raise RuntimeError("coverage_pass is not true")
 expected=int(c["expected_evaluation_arrival_job_count"]);logged=int(c["logged_job_event_evaluation_arrival_job_count"])
 pending=int(c["pending_evaluation_arrival_jobs_at_evaluation_end"])
 if expected<0 or logged<0 or pending<0:raise RuntimeError("negative coverage count")
 if expected!=logged:raise RuntimeError(f"expected arrivals {expected} != logged job_event arrivals {logged}")
 kind=str(c["independent_source_kind"]).strip().lower()
 if not kind or "job_event"==kind or "job_event_only" in kind or "derived solely from job_event" in kind:
  raise RuntimeError("coverage source is not independent of job_event")
 sha=str(c["independent_source_sha256"]).strip().lower()
 if len(sha)!=64 or any(ch not in "0123456789abcdef" for ch in sha):raise RuntimeError("independent source SHA malformed")
 res={"stage":"F7_JOB_EVENT_COHORT_COVERAGE_VALIDATION","status":"PASS",
      "episode_id":c["episode_id"],"method_id":c["method_id"],"month":c["month"],
      "expected_arrivals":expected,"logged_arrivals":logged,"pending_at_eval_end":pending,
      "independent_source_kind":c["independent_source_kind"]}
 (out/"F7_JOB_EVENT_COHORT_COVERAGE_VALIDATION_RESULT.json").write_text(json.dumps(res,indent=2)+"\n")
 print(json.dumps(res,indent=2))
if __name__=="__main__":main()

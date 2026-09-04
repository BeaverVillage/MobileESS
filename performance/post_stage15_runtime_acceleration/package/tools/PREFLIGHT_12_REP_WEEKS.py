#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,os
from pathlib import Path

HERE=Path(__file__).resolve().parents[1]
EXPECTED=[
 "W02_2025-01-13","W07_2025-02-17","W10_2025-03-10",
 "W17_2025-04-28","W18_2025-05-05","W25_2025-06-23",
 "W26_2025-06-30","W32_2025-08-11","W38_2025-09-22",
 "W41_2025-10-13","W44_2025-11-03","W51_2025-12-22",
]
EXPECTED_STARTS=[3456,13536,19584,33696,35712,49824,51840,63936,76032,82080,88128,102240]

def sha(path:Path)->str:
 h=hashlib.sha256()
 with path.open("rb") as f:
  for block in iter(lambda:f.read(1<<20),b""):h.update(block)
 return h.hexdigest()

def main()->int:
 ap=argparse.ArgumentParser();ap.add_argument("--repo",required=True);ap.parse_args()
 manifest=HERE.parent/"INITIALIZATION/INITIAL_STATES/INITIAL_STATE_MANIFEST.json"
 rows=json.loads(manifest.read_text(encoding="utf-8")).get("files",[])
 if len(rows)!=12:raise RuntimeError(f"12-week manifest cardinality drift: {len(rows)}")
 if [r.get("candidate_id") for r in rows]!=EXPECTED:raise RuntimeError("12 representative-week order drift")
 if [int(r.get("week_start_index",-1)) for r in rows]!=EXPECTED_STARTS:
  raise RuntimeError("12 representative-week start-index drift")
 checks=[]
 for r in rows:
  pre=HERE.parent/"INITIALIZATION"/r["path"]
  resume=HERE.parent/"INITIALIZATION"/r["production_resume_relpath"]
  ok=(sha(pre)==r["file_sha256"] and sha(resume)==r["production_resume_file_sha256"]
      and json.loads(resume.read_text(encoding="utf-8"))["sha256"]==r["state_sha256"])
  if not ok:raise RuntimeError(f"initial-state authority drift {r['candidate_id']}")
  checks.append({"candidate_id":r["candidate_id"],"start_index":int(r["week_start_index"]),
                 "end_index_inclusive":int(r["week_start_index"])+2015,
                 "state_sha256":r["state_sha256"],"pass":True})
 groups=json.loads(os.popen(f"{os.sys.executable} '{HERE/'tools/CPU_AFFINITY_4X4.py'}'").read())
 if len(groups.get("groups",[]))!=4 or any(len(g)!=4 for g in groups["groups"]):
  raise RuntimeError("initial 4x4 CPU topology drift")
 out={"schema_version":"mobileess.post_stage15.rep12_preflight.v1","status":"PASS","weeks":checks,
      "representative_week_count":12,"episodes":48,"issues_per_episode":2016,
      "worker_slots":4,"fixed_threads_per_episode":4,"maximum_concurrent_episodes":4,
      "global_week_policy_episode_queue":True,"completed_worker_starts_next_pending_episode":True,
      "w02_preacceptance_barrier":False,"cross_week_overlap_allowed":True,"full_campaign_executed":False}
 print(json.dumps(out,indent=2));return 0
if __name__=="__main__":raise SystemExit(main())

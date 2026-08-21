#!/usr/bin/env python3
from __future__ import annotations
import csv,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4]
PKG=Path(__file__).resolve().parents[1]
BASE=PKG.parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def load(p):return json.loads(p.read_text())
def main():
 selection=ROOT/"stage7/r13_zero_burnin/frozen_authority/REP_WEEK_SELECTION_2025_K12.csv"
 initial=load(BASE/"INITIALIZATION/UPDATED_INITIAL_STATE_MANIFEST.json");pre={x["candidate_id"]:x for x in initial["files"]}
 policies=[("M1",PKG/"configs/P1_PROPOSED_EVENT30_LOCAL_REPAIR.json"),("M2",PKG/"configs/P2_FIXED30.json"),("M3",PKG/"configs/P3_EVENT30_NO_LOCAL_REPAIR.json"),("M4",PKG/"configs/M4_FIXED_LOCATION_ESS_MOBILITY_ABLATION.json")]
 out=PKG/"episode_bindings";out.mkdir(exist_ok=True);index=[]
 with selection.open(newline="",encoding="utf-8-sig") as f:weeks=list(csv.DictReader(f))
 for w in weeks:
  p=pre[w["candidate_id"]]
  for comparison,cfg in policies:
   c=load(cfg);record={"schema_version":"mobileess.resolved_episode_binding.v1","status":"FROZEN_PRE_OUTCOME",
    "candidate_id":w["candidate_id"],"comparison_method_id":comparison,"scientific_method_id":"B5","policy_id":c["policy_id"],
    "policy_template_path":str(cfg.relative_to(PKG)),"policy_template_sha256":sha(cfg),"start_index":int(w["start_index"]),
    "end_index_exclusive":int(w["end_index_exclusive"]),"scored_issues":int(w["end_index_exclusive"])-int(w["start_index"]),
    "representative_weight":float(w["cluster_weight"]),"canonical_pre_state_sha256":p["state_sha256"],
    "canonical_pre_file_sha256":p["file_sha256"],"production_resume_file_sha256":p["production_resume_file_sha256"],
    "site_authority_sha256":"7a1009856160efda0f56269cd096e5f57465b5b185c182221481638e920b0a48",
    "output_namespace":f"{w['candidate_id']}/{comparison}_{c['policy_id']}","controller_burn_in_steps":0,
    "source_authority_role":"CANDIDATE_SPECIFIC_SHARED_SOURCE_SHA_BOUND_AT_PREFLIGHT","future_actual_used":False}
   path=out/f"{w['candidate_id']}_{comparison}.json";path.write_text(json.dumps(record,indent=2,sort_keys=True)+"\n");index.append({"path":path.name,"sha256":sha(path),**record})
 manifest={"schema_version":"mobileess.resolved_episode_binding_manifest.v1","status":"PASS","binding_count":len(index),"weeks":len(weeks),"methods":4,"bindings":index,"controller_outcomes_used":False}
 (out/"MANIFEST.json").write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\n");print(out/"MANIFEST.json")
if __name__=="__main__":main()

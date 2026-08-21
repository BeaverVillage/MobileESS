#!/usr/bin/env python3
"""Bind a W02 result root to one immutable scientific execution source."""
from __future__ import annotations

import argparse,hashlib,json
from datetime import datetime,timezone
from pathlib import Path

def sha(path:Path)->str:
 h=hashlib.sha256()
 with path.open("rb") as f:
  for block in iter(lambda:f.read(8<<20),b""):h.update(block)
 return h.hexdigest()

def load(path:Path):return json.loads(path.read_text(encoding="utf-8"))

def atomic_write(path:Path,payload:dict)->None:
 tmp=path.with_suffix(path.suffix+".tmp")
 tmp.write_text(json.dumps(payload,indent=2,sort_keys=True,allow_nan=False)+"\n",encoding="utf-8")
 tmp.replace(path)

def main()->int:
 ap=argparse.ArgumentParser()
 ap.add_argument("--package",type=Path,required=True)
 ap.add_argument("--repo",type=Path,required=True)
 ap.add_argument("--delivery-root",type=Path,required=True)
 ap.add_argument("--run-id",required=True)
 a=ap.parse_args();pkg=a.package.resolve();repo=a.repo.resolve();root=a.delivery_root.resolve()
 runner=pkg/"runtime/W02_POLICY_EPISODE_RUNNER.py"
 launcher=pkg/"RUN_W02_4POLICY_ACTUAL.sh"
 release_path=pkg/"authority/PRE_W02_FINAL_RELEASE_AUTHORIZATION.json"
 correction_path=pkg/"authority/POST_STAGE15_W02_ACTUAL_FAILURE_CORRECTION.json"
 recovery_path=pkg/"authority/POST_STAGE15_W02_SAFETY_RECOVERY_REFREEZE.json"
 sensitivity_path=pkg/"authority/POST_STAGE15_W02_SENSITIVITY_KEYERROR_CORRECTION.json"
 rootcause_path=pkg/"authority/POST_STAGE15_W02_R15_FINAL_RECOVERY_ATOMIC_ROOTCAUSE_CORRECTION.json"
 science=repo/"science/main.py"
 for path in (runner,launcher,release_path,correction_path,recovery_path,sensitivity_path,rootcause_path,science):
  if not path.is_file():raise RuntimeError(f"required source authority missing: {path}")
 release=load(release_path);correction=load(correction_path);recovery=load(recovery_path);sensitivity=load(sensitivity_path);rootcause=load(rootcause_path)
 if release.get("status")!="AUTHORIZED_FOR_W02":raise RuntimeError("W02 release is not authorized")
 if correction.get("status")!="PASS_FAILURE_CORRECTION_WITH_RECOVERY_SCOPE_SUPERSEDED":
  raise RuntimeError("W02 actual-failure correction is not PASS")
 if recovery.get("status")!="PASS_CODE_AND_BOUNDED_REGRESSION":
  raise RuntimeError("W02 safety-recovery refreeze is not PASS")
 if sensitivity.get("status")!="PASS_KEYERROR_CORRECTION_AND_BOUNDED_REGRESSION":
  raise RuntimeError("W02 sensitivity-key correction is not PASS")
 if rootcause.get("status")!="PASS_FINAL_RECOVERY_ATOMIC_EVIDENCE_CONTRACT":
  raise RuntimeError("W02 final recovery/atomic-evidence authority is not PASS")
 release_runner=next((x.get("sha256") for x in release.get("release_source_files",[])
                      if x.get("path")=="runtime/W02_POLICY_EPISODE_RUNNER.py"),None)
 identity={"run_id":a.run_id,"candidate_id":"W02_2025-01-13","delivery_root":str(root),
  "runner_sha256":sha(runner),"launcher_sha256":sha(launcher),"science_main_sha256":sha(science),
  "release_authorization_sha256":sha(release_path),
  "release_source_tree_sha256":release.get("release_source_tree_sha256"),
  "correction_authority_sha256":sha(correction_path),
  "safety_recovery_authority_sha256":sha(recovery_path),
  "sensitivity_keyerror_authority_sha256":sha(sensitivity_path),
  "final_recovery_atomic_authority_sha256":sha(rootcause_path)}
 # The original release authority is immutable lineage evidence and therefore
 # intentionally names the historical release runner.  The final correction
 # authority must preserve that lineage while binding the current runner.
 if rootcause.get("lineage",{}).get("historical_release_runner_sha256")!=release_runner:
  raise RuntimeError("historical release-runner lineage drift")
 if rootcause.get("correction",{}).get("runner",{}).get("sha256")!=identity["runner_sha256"]:
  raise RuntimeError("final recovery/atomic-evidence authority runner SHA drift")
 identity_sha=hashlib.sha256(json.dumps(identity,sort_keys=True,separators=(",",":")).encode()).hexdigest()
 binding_path=root/"W02_RUN_SOURCE_AUTHORITY.json"
 committed=list(root.glob("*/engine/issue_*/A_B10_COMMIT_MARKER.json")) if root.is_dir() else []
 if binding_path.is_file():
  existing=load(binding_path)
  if existing.get("source_identity_sha256")!=identity_sha or existing.get("source_identity")!=identity:
   raise RuntimeError("existing W02 result root is bound to a different execution source")
  print(json.dumps({"status":"PASS_SAME_SOURCE_RESUME","run_id":a.run_id,
                    "committed_issue_markers":len(committed),"source_identity_sha256":identity_sha},sort_keys=True))
  return 0
 if committed:raise RuntimeError("committed W02 result root lacks immutable source binding")
 root.mkdir(parents=True,exist_ok=True)
 payload={"schema_version":"mobileess.w02.run_source_authority.v1","status":"FROZEN_BEFORE_FIRST_ISSUE",
  "created_utc":datetime.now(timezone.utc).isoformat(),"source_identity":identity,
  "source_identity_sha256":identity_sha,"same_source_resume_only":True,
  "mixed_runner_episode_forbidden":True,"future_actual_used":False}
 atomic_write(binding_path,payload)
 print(json.dumps({"status":"PASS_NEW_SOURCE_BINDING","run_id":a.run_id,
                   "source_identity_sha256":identity_sha},sort_keys=True))
 return 0

if __name__=="__main__":raise SystemExit(main())

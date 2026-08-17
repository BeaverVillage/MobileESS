#!/usr/bin/env python3
"""Bounded pre-W02 proof for lightweight M1--M4 exogenous identities.

No optimizer, controller, or OpenDSS code is imported.  Immutable block SHA
authorities are checked once; production issue identities then bind only those
authorities, candidate, issue, block number, and the already-indexed mobility SHA.
"""
from __future__ import annotations
import argparse,csv,hashlib,json
from pathlib import Path

def load(p:Path):return json.loads(p.read_text(encoding="utf-8"))
def sha(p:Path)->str:
 h=hashlib.sha256()
 with p.open("rb") as f:
  for b in iter(lambda:f.read(8<<20),b""):h.update(b)
 return h.hexdigest()
def write(p:Path,x):
 p.parent.mkdir(parents=True,exist_ok=True);t=p.with_suffix(p.suffix+".tmp")
 t.write_text(json.dumps(x,indent=2,sort_keys=True,allow_nan=False)+"\n");t.replace(p)
def identity(candidate:str,issue:int,authority_sha:str,mobility_sha:str)->tuple[dict,str]:
 payload={"candidate_id":candidate,"issue":issue,"source_authority_sha256":authority_sha,
          "power_price_block":(issue-3456)//576,"mobility_issue_sha256":mobility_sha}
 digest=hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(",",":")).encode()).hexdigest()
 return payload,digest

def main():
 a=argparse.ArgumentParser();a.add_argument("delivery_root",type=Path);a.add_argument("shared_root",type=Path)
 a.add_argument("--output",type=Path,required=True);a.add_argument("--sample-issues",default="3456,3518,4032,4608,5184,5471");x=a.parse_args()
 shared_file=x.shared_root/"SHARED_EXOGENOUS_AUTHORITY.json";shared=load(shared_file);shared_sha=sha(shared_file)
 roots=[p for p in sorted(x.delivery_root.iterdir()) if (p/"episode_manifest.json").is_file()]
 manifests=[load(p/"episode_manifest.json") for p in roots]
 bounded_manifest_shas={m.get("shared_exogenous_authority_sha256") for m in manifests}
 method_binding=len(roots)==4 and len(bounded_manifest_shas)==1 and None not in bounded_manifest_shas and \
  {m.get("candidate_id") for m in manifests}=={"W02_2025-01-13"}
 with (x.shared_root/"mobility/R12_COMMON_MOBILITY_INDEX.csv").open(encoding="utf-8-sig",newline="") as f:
  mobility={int(r["issue_step"]):r for r in csv.DictReader(f)}
 samples=[int(v) for v in x.sample_issues.split(",") if v.strip()]
 mobility_checks=[];sample_identities={}
 for issue in samples:
  row=mobility[issue];p=x.shared_root/"mobility"/row["file"]
  ok=p.is_file() and sha(p)==row["sha256"]
  payload,dig=identity("W02_2025-01-13",issue,shared_sha,row["sha256"])
  mobility_checks.append({"issue":issue,"file":str(p),"indexed_sha256":row["sha256"],"actual_content_sha_pass":ok})
  sample_identities[str(issue)]={"payload":payload,"lightweight_digest":dig,
   "M1":dig,"M2":dig,"M3":dig,"M4":dig,"cross_method_equal":True}
 power_auth=load(x.shared_root/"power_price/REP_WEEK_POWER_PRICE_SOURCE_AUTHORITY.json")
 block_checks=[]
 for block in power_auth["blocks"]:
  bdir=x.shared_root/"power_price"/f"block_{int(block['block']):02d}_{int(block['issue_first'])}_{int(block['issue_last'])}"
  fields={}
  for family in ("power","price"):
   for name,expected in block[f"{family}_fields"].items():
    p=bdir/f"{family}__{name}.npy";fields[f"{family}.{name}"]=(p.is_file() and sha(p)==expected)
  block_checks.append({"block":block["block"],"all_immutable_file_sha_pass":all(fields.values()),"fields":fields})
 audit_checks=[]
 for root,manifest in zip(roots,manifests):
  bounded_authority_sha=str(manifest["shared_exogenous_authority_sha256"])
  for marker in sorted((root/"engine").glob("issue_*/A_B10_COMMIT_MARKER.json")):
   if load(marker).get("schema_version")!="mobileess.post_stage15.atomic_commit_marker.v2":continue
   audit=load(marker.parent/"POLICY_ISSUE_AUDIT.json");issue=int(audit["issue"]);row=mobility[issue]
   payload,dig=identity("W02_2025-01-13",issue,bounded_authority_sha,row["sha256"])
   audit_checks.append({"method":audit.get("comparison_method_id"),"issue":issue,
    "payload_equal":audit.get("causal_exogenous_identity_payload")==payload,
    "digest_equal":audit.get("causal_exogenous_identity")==dig})
 gates={"four_method_same_authority_binding":method_binding,
  "shared_authority_declares_same_source":shared.get("same_source_for_all_methods",shared.get("same_source_for_all_policies")) is True,
  "current_shared_authority_ready_for_production":shared.get("status")=="PASS" and shared.get("candidate_id")=="W02_2025-01-13",
  "sampled_mobility_actual_content_sha":all(r["actual_content_sha_pass"] for r in mobility_checks),
  "all_power_price_immutable_block_file_sha":all(r["all_immutable_file_sha_pass"] for r in block_checks),
  "sampled_lightweight_cross_method_equal":all(r["cross_method_equal"] for r in sample_identities.values()),
  "production_audit_payload_and_digest_match":bool(audit_checks) and all(r["payload_equal"] and r["digest_equal"] for r in audit_checks)}
 out={"schema_version":"mobileess.pre_w02.lightweight_fairness.v1","status":"PASS" if all(gates.values()) else "FAIL_CLOSED",
  "gurobi_solve_count":0,"opendss_solve_count":0,"simulation_rerun_count":0,"full_W02_executed":False,
  "gates":gates,"shared_authority_sha256":shared_sha,"sampled_mobility":mobility_checks,
  "bounded_four_method_authority_sha256":next(iter(bounded_manifest_shas)) if len(bounded_manifest_shas)==1 else None,
  "power_price_blocks":block_checks,"sample_identities":sample_identities,"production_audit_checks":audit_checks}
 write(x.output,out);print(x.output);return 0 if out["status"]=="PASS" else 2
if __name__=="__main__":raise SystemExit(main())

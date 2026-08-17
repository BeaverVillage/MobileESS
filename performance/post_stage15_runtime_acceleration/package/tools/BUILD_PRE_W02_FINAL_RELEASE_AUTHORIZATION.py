#!/usr/bin/env python3
"""Fail-closed assembler for the outcome-blind Pre-W02 release certificate."""
from __future__ import annotations
import argparse,hashlib,json,subprocess,sys
from pathlib import Path

def load(p:Path):return json.loads(p.read_text(encoding="utf-8"))
def sha(p:Path)->str:
 h=hashlib.sha256()
 with p.open("rb") as f:
  for b in iter(lambda:f.read(8<<20),b""):h.update(b)
 return h.hexdigest()
def write(p:Path,x):
 p.parent.mkdir(parents=True,exist_ok=True);t=p.with_suffix(p.suffix+".tmp")
 t.write_text(json.dumps(x,indent=2,sort_keys=True,allow_nan=False)+"\n",encoding="utf-8");t.replace(p)
def evidence(path:Path,accepted:tuple[str,...])->dict:
 d=load(path);return {"path":str(path),"sha256":sha(path),"status":d.get("status"),"pass":str(d.get("status")) in accepted}

def main():
 a=argparse.ArgumentParser();a.add_argument("--package",type=Path,default=Path(__file__).resolve().parents[1])
 a.add_argument("--artifact-root",type=Path,default=Path("/home/jaewon/mobile_ess_work/frozen_artifacts"));x=a.parse_args();pkg=x.package.resolve();art=x.artifact_root
 static_checks=[]
 for p in sorted(pkg.rglob("*.py")):
  if "__pycache__" in p.parts:continue
  try:compile(p.read_text(encoding="utf-8"),str(p),"exec");ok=True;detail=None
  except Exception as exc:ok=False;detail=repr(exc)
  static_checks.append({"kind":"PYTHON_COMPILE","path":str(p.relative_to(pkg)),"pass":ok,"detail":detail})
 for p in sorted(pkg.rglob("*.sh")):
  r=subprocess.run(["bash","-n",str(p)],capture_output=True,text=True)
  static_checks.append({"kind":"BASH_PARSE","path":str(p.relative_to(pkg)),"pass":r.returncode==0,"detail":r.stderr.strip() or None})
 critical_json=[pkg/"authority/RERUN_ELIGIBILITY_CONTRACT.json",pkg/"authority/TRANSFORMER_SCENARIO_AUTHORITY.json",
  pkg/"authority/K9H7_OBSERVABILITY_V1_MANIFEST.json",pkg/"episode_bindings/MANIFEST.json"]
 for p in critical_json:
  try:load(p);ok=True;detail=None
  except Exception as exc:ok=False;detail=repr(exc)
  static_checks.append({"kind":"JSON_PARSE","path":str(p.relative_to(pkg)),"pass":ok,"detail":detail})
 static={"schema_version":"mobileess.pre_w02.static_validation.v1","status":"PASS" if all(r["pass"] for r in static_checks) else "FAIL_CLOSED",
  "checks":static_checks,"scientific_solve_count":0,"full_W02_executed":False}
 write(pkg/"STATIC_VALIDATION.json",static)
 ev=[]
 ev.append(evidence(art/"B_W02_4POLICY_PREFLIGHT.json",("PASS",)))
 ev.append(evidence(art/"PRE_W02_FIRST6_PREFLIGHT_CURRENT.json",("PASS",)))
 ev.append(evidence(art/"PRE_W02_REPEATABILITY_M4_CURRENT/PRE_W02_REPEATABILITY_EVIDENCE.json",("PASS",)))
 ev.append(evidence(art/"PRE_W02_KILL_RESTART_4X4_CURRENT/PRE_W02_KILL_RESTART_4X4_EVIDENCE.json",("PASS",)))
 ev.append(evidence(art/"PRE_W02_LIGHTWEIGHT_FAIRNESS_CURRENT.json",("PASS",)))
 ev.append(evidence(art/"PRE_W02_POLICY_PATHS_CURRENT.json",("PASS",)))
 ev.append(evidence(art/"PRE_W02_OBSERVABILITY_OVERHEAD_CURRENT.json",("PASS",)))
 ev.append(evidence(art/"PRE_W02_ANALYSIS_DRYRUN_CURRENT/MANIFEST.json",("PASS",)))
 for method in ("M1","M2","M3","M4"):
  ev.append(evidence(art/f"PRE_W02_OBSERVABILITY_FINITE_CURRENT/{method}/MANIFEST.json",("PASS",)))
  ev.append(evidence(art/f"PRE_W02_OFFLINE_RECALCULATOR_CURRENT/{method}.json",("PASS_BOUNDED_INDIVIDUAL_EVIDENCE",)))
 binding=load(pkg/"episode_bindings/MANIFEST.json");bindings=binding.get("bindings",[])
 binding_gate=(binding.get("binding_count")==48 and len(bindings)==48 and len({r["candidate_id"] for r in bindings})==12
  and {r["comparison_method_id"] for r in bindings}=={"M1","M2","M3","M4"} and all(r.get("status")=="FROZEN_PRE_OUTCOME" for r in bindings))
 rerun=load(pkg/"authority/RERUN_ELIGIBILITY_CONTRACT.json");obs=load(pkg/"authority/K9H7_OBSERVABILITY_V1_MANIFEST.json")
 kill=load(art/"PRE_W02_KILL_RESTART_4X4_CURRENT/PRE_W02_KILL_RESTART_4X4_EVIDENCE.json")
 gates={"all_evidence_pass":all(r["pass"] for r in ev),"static_validation_pass":static["status"]=="PASS",
  "resolved_episode_bindings_12x4":binding_gate,"rerun_eligibility_frozen_pre_outcome":rerun.get("status")=="FROZEN_PRE_OUTCOME",
  "observability_contract_frozen_pre_outcome":obs.get("status")=="FROZEN_PRE_OUTCOME",
  "bounded_4process_x_4thread_pass":kill.get("status")=="PASS" and kill.get("processes")==4 and kill.get("gurobi_threads_per_process")==4,
  "full_W02_not_executed_by_hardening":all(load(Path(r["path"])).get("full_W02_executed",False) is False for r in ev if Path(r["path"]).suffix==".json"),
  "outcome_blind_acceptance":True}
 source_files=[]
 include=[pkg/"runtime/W02_POLICY_EPISODE_RUNNER.py",pkg/"RUN_W02_4POLICY_ACTUAL.sh",pkg/"RUN_FIRST6_REP_WEEKS_ACTUAL.sh",
  pkg/"STATIC_VALIDATION.json",pkg/"episode_bindings/MANIFEST.json"]
 include+=sorted((pkg/"configs").glob("*.json"))+sorted((pkg/"tools").glob("*.py"))+sorted((pkg/"tools").glob("*.sh"))
 include+=sorted((pkg/"authority").glob("*.json"))
 for p in include:
  if p.is_file() and p.name!="PRE_W02_FINAL_RELEASE_AUTHORIZATION.json":source_files.append({"path":str(p.relative_to(pkg)),"sha256":sha(p)})
 tree_sha=hashlib.sha256("\n".join(f"{r['sha256']}  {r['path']}" for r in source_files).encode()).hexdigest()
 ok=all(gates.values())
 out={"schema_version":"mobileess.pre_w02.final_release_authorization.v1","status":"AUTHORIZED_FOR_W02" if ok else "BLOCKED_FAIL_CLOSED",
  "authorization_scope":"W02_2025-01-13 four-policy scientific episode only; remaining weeks require the frozen W02 acceptance token",
  "full_w02_executed":False,"full_first6_executed":False,"full_12week_executed":False,
  "scientific_outcome_examined_for_authorization":False,"proposed_method_win_required":False,
  "gates":gates,"evidence":ev,"release_source_tree_sha256":tree_sha,"release_source_files":source_files,
  "production_topology":{"outer_processes":4,"gurobi_threads_per_process":4},
  "post_run_only_tools":["OFFLINE_RESULT_RECALCULATOR.py","MATERIALIZE_OBSERVABILITY_OFFLINE.py","PRE_W02_ANALYSIS_DRYRUN.py"],
  "forbidden_inside_issue_loop":["VALIDATION_GUROBI_SOLVE","VALIDATION_OPENDSS_SOLVE","PAPER_STATISTICS","FIGURE_GENERATION","FULL_SOURCE_REHASH"]}
 write(pkg/"authority/PRE_W02_FINAL_RELEASE_AUTHORIZATION.json",out);print(pkg/"authority/PRE_W02_FINAL_RELEASE_AUTHORIZATION.json")
 return 0 if ok else 2
if __name__=="__main__":raise SystemExit(main())

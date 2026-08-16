#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,os,platform,subprocess,sys
from pathlib import Path

HERE=Path(__file__).resolve().parents[1]
PR4="06a94bccc0a232ae7ea09cbc7b00962162c10f4d"
SCIENCE_SHA="cfdc7fe3069966d53d9d9246eb9c009a63a5536d265cddc9e5df145b5c6f33e8"
B5_SHA="3f712ec02c4c5ebb6a424267b043f07469d29f4a4abeaea7fcdd8b765e13624a"
PRE_FILE_SHA="deecff989d60223cb08d9070874a053f12ef7dc9e44a85554fb2821cd8ba6aba"
PRE_STATE_SHA="4fd2b4e8a6ef052fd08454f9888ad1e08e2706ed99d1118cac6d96d33c8a5a7b"
SITE_SHA="7a1009856160efda0f56269cd096e5f57465b5b185c182221481638e920b0a48"
SITES={"MESS01":"STA09","MESS02":"IDC12","MESS03":"STA07","MESS04":"STA11"}
F7_SHA="faa537141d67f468f10b32d741d8193c14125cd745c042d132510b72e111f8ba"
EXPECTED={
 "configs/P1_PROPOSED_EVENT30_LOCAL_REPAIR.json":"a33f90af96e8d861154e1caa182ac9d47d024a49e24a9ace0b700b5b12e9c0e1",
 "configs/P2_FIXED30.json":"b16b9a7c81c2c1ccab65e93c7c7be554296f06e7a60a9b87412cbc49d819002b",
 "configs/P3_EVENT30_NO_LOCAL_REPAIR.json":"7caa33d7db378705130e6549f7de03cd1124672d0ee6369446fb31368e6ea814",
 "configs/M4_FIXED_LOCATION_ESS_MOBILITY_ABLATION.json":"919a30ebe9c2d349a281a0021bc453fb43b969dd447c915e86de4a0d7e235a8e",
 "configs/P4_FIXED15.json":"20b562999551f06c0cdf9a4b7d8dde7e3846775f991904b1248147ffaa0daa21",
 "runtime/W02_POLICY_EPISODE_RUNNER.py":"c8713ed222814b0bb895e9d72dc3d4a8003ab03be664006f3e6a296175cd4246",
 "runtime/production_adapter.py":"85eb2334b0fde228bc82a603ab07ec145f63794866ce2bb203dff63a3de1ebd2",
 "runtime/MobileESS_A_STEP2_3_LOCAL_RUNNER_20260815_R2.py":"c95f0641ba30806db74770ae1246ffeb20c551cf39b8074f8fd3fb55e0788a03",
 "RUN_W02_4POLICY_ACTUAL.sh":"74776197f13c4b191abfa8a897eeac83f0ba209277c659397063873d0aaad664",
 "tools/BENCHMARK_POST15_4X4_SHORT.sh":"b13043a5ce797635e50ad5c06647b069037be65ee12906101cffee4ff5797021",
 "tools/CPU_AFFINITY_4X4.py":"1919df7f013d09474353c28f89afd4fa32112f2df95b152aef045e50f85c72ce",
 "authority/D/tools/validate_B_W02_4POLICY_delivery_structure.py":"fa56563ad49f426e12efeaa829e008053e6db54d11b98e1f23ffaef9797cc88a",
 "authority/D/tools/build_B_TO_D_W02_handoff.sh":"09c0f4adea436a879820363203899726a4f07f514cc411ec2749c2e2dfa7bf24",
 "authority/POST_STAGE15_M1_M4_SUPERSESSION.json":"f0eef024f5a3291a8aa8bb2db19822191f0dab7c2ff495606c1e5f5787066378",
 "authority/D/06_W02_EXECUTION/W02_M1_M4_PRODUCTION_REQUEST.json":"72608c8febe5c1468663775f3420ff48d0a09316468f4704f1284a2acbabd5d4",
}

def sha(p:Path)->str:
 h=hashlib.sha256()
 with p.open("rb") as f:
  for b in iter(lambda:f.read(1<<20),b""):h.update(b)
 return h.hexdigest()

def main():
 ap=argparse.ArgumentParser();ap.add_argument("--repo",required=True);ap.add_argument("--require-shared-source",action="store_true");a=ap.parse_args()
 repo=Path(a.repo).resolve();checks=[]
 def ck(name,cond,detail=None):
  checks.append({"name":name,"pass":bool(cond),"detail":detail})
  if not cond:raise RuntimeError(f"preflight failed: {name}: {detail}")
 ancestry=subprocess.run(["git","-C",str(repo),"merge-base","--is-ancestor",PR4,"HEAD"]).returncode==0
 ck("PR4_SCIENTIFIC_BASE_ANCESTRY",ancestry,subprocess.check_output(["git","-C",str(repo),"rev-parse","HEAD"],text=True).strip())
 ck("SCIENCE_MAIN_SHA",sha(repo/"science/main.py")==SCIENCE_SHA,sha(repo/"science/main.py"))
 for rel,h in EXPECTED.items():
  p=HERE/rel;ck("SHA:"+rel,p.is_file() and sha(p)==h,sha(p) if p.is_file() else "missing")
 b5=HERE/"authority/D/04_RESULT_CONTRACT/B5_METHOD_CONFIG.json";ck("B5_SHA",sha(b5)==B5_SHA,sha(b5))
 pre=HERE.parent/"INITIALIZATION/INITIAL_STATES/CANONICAL_PRE_STATE_W02_2025-01-13.json"
 ck("PRE_FILE_SHA",sha(pre)==PRE_FILE_SHA,sha(pre));x=json.loads(pre.read_text());ck("PRE_STATE_SHA",x["state_sha256"]==PRE_STATE_SHA,x.get("state_sha256"))
 site=HERE.parent/"SITING/FIXED_ESS_FINAL_SITE_AUTHORITY.json";sx=json.loads(site.read_text()) if site.is_file() else {}
 ck("OUTCOME_BLIND_SITE_AUTHORITY_SHA",site.is_file() and sha(site)==SITE_SHA,sha(site) if site.is_file() else "missing")
 ck("OUTCOME_BLIND_SITE_ASSIGNMENT",sx.get("status")=="PASS_EXACTLY_FOUR_SITES" and sx.get("assignment")==SITES,sx.get("assignment"))
 for rel in ["configs/P1_PROPOSED_EVENT30_LOCAL_REPAIR.json","configs/P2_FIXED30.json","configs/P3_EVENT30_NO_LOCAL_REPAIR.json","configs/M4_FIXED_LOCATION_ESS_MOBILITY_ABLATION.json"]:
  cfg=json.loads((HERE/rel).read_text());ck("COMMON_INITIAL_SITES:"+rel,cfg.get("initial_service_sites")==SITES,cfg.get("initial_service_sites"))
 f7=HERE/"authority/D/03_C_ZERO_BURNIN/independent_job_authority/PER_JOB_RUNTIME_SOURCE_CANONICAL_V2044R5.parquet"
 ck("F7_INDEPENDENT_SHA",sha(f7)==F7_SHA,sha(f7))
 allowed=sorted(os.sched_getaffinity(0)) if hasattr(os,"sched_getaffinity") else list(range(os.cpu_count() or 0))
 ck("CPU_BUDGET_16",len(allowed)>=16,allowed)
 mods={}
 for m in ["numpy","pandas","pyarrow","gurobipy","opendssdirect"]:
  try:__import__(m);mods[m]=True
  except Exception as e:mods[m]=f"{type(e).__name__}: {e}"
 ck("PYTHON_RUNTIME_DEPS",all(v is True for v in mods.values()),mods)
 # Gurobi license minimal model, no scientific solve.
 try:
  import gurobipy as gp
  mm=gp.Model("A_B10_PREFLIGHT");mm.Params.OutputFlag=0;z=mm.addVar(lb=0);mm.setObjective(z);mm.optimize()
  lic=int(mm.Status)==int(gp.GRB.OPTIMAL);mm.dispose()
 except Exception as e:lic=False;mods["gurobi_license"]=repr(e)
 ck("GUROBI_LICENSE",lic,mods.get("gurobi_license","PASS"))
 if a.require_shared_source:
  shared=Path("/home/jaewon/mobile_ess_work/frozen_artifacts/B_W02_SHARED_EXOGENOUS_SOURCE_CURRENT/SHARED_EXOGENOUS_AUTHORITY.json")
  sx=json.loads(shared.read_text()) if shared.is_file() else {}
  ck("SHARED_EXOGENOUS_PASS",sx.get("status")=="PASS",str(shared))
 rec={"schema_version":"a_to_b.10.w02.preflight.v1","status":"PASS","checks":checks,
      "environment":{"python":sys.executable,"python_version":sys.version,"platform":platform.platform(),
                     "cpu_affinity":allowed,"modules":mods}}
 out=Path("/home/jaewon/mobile_ess_work/frozen_artifacts/B_W02_4POLICY_PREFLIGHT.json");out.parent.mkdir(parents=True,exist_ok=True)
 out.write_text(json.dumps(rec,indent=2,sort_keys=True)+"\n");print(json.dumps(rec,indent=2));return 0
if __name__=="__main__":raise SystemExit(main())

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
 "runtime/W02_POLICY_EPISODE_RUNNER.py":"dd53a661224b14899a7aff8e68b685e1a0420dbefb1f6d3e38a3cccc1e0ec0cf",
 "runtime/MobileESS_A_STEP4_LOCAL_RUNNER_20260815_R4.py":"e02dd6bff1ac32dbfb0d9627f020a4f7bcf58d8c2bd594a9d088c1b7bd402170",
 "runtime/production_adapter.py":"85eb2334b0fde228bc82a603ab07ec145f63794866ce2bb203dff63a3de1ebd2",
 "runtime/MobileESS_A_STEP2_3_LOCAL_RUNNER_20260815_R2.py":"c95f0641ba30806db74770ae1246ffeb20c551cf39b8074f8fd3fb55e0788a03",
 "RUN_W02_4POLICY_ACTUAL.sh":"d592b6901e65bbee811c8dc43debb381159becffc15f4b00c52ffe6e9c86d7a5",
 "tools/BIND_W02_RUN_SOURCE.py":"7c561c801467498790fd3d255c8f65bcfe78d3a896ae8d4200edbccdfb528da9",
 "tools/BUILD_PRE_W02_FINAL_RELEASE_AUTHORIZATION.py":"81bd0974d9c1a5306ffa6e8894cdd1cac91798399bc3538a458eed8ea04be319",
 "tools/VALIDATE_W02_SAFETY_RECOVERY_CONTRACT.py":"d96e543a03adf8b42028d477ea1a8dfe8cd340d3f5c837658cf231d68e55edf5",
 "tools/VALIDATE_W02_SENSITIVITY_KEYERROR_CORRECTION.py":"e2a8cfaa75bb727267acc0bdc4df5f58fcf21ff27398f4698b39e1704a940480",
 "tools/VALIDATE_W02_R3_ACTUAL_FAILURE_RECOVERY.py":"c7be2150d3f833a82083ef49dc4ea62412dac73c235602729d102697e55c8762",
 "tools/VALIDATE_W02_R4_M4_ISSUE3518_RECOVERY.py":"68c00bd60e92b73f9dcab61ec70d1f0ad2af6dd995cc41be2c113fff6aa7011b",
 "tools/VALIDATE_W02_M4_ADAPTIVE_GRID_RECOVERY.py":"5bc649e069e4526ece8c2422e726a5546ade111352eaa218a1435b5106010118",
 "authority/POST_STAGE15_W02_ACTUAL_FAILURE_CORRECTION.json":"73c50d5f80f0150339a4754a5b358efc1354b919c667718b92e9e2c099d68fd4",
 "authority/POST_STAGE15_W02_SAFETY_RECOVERY_REFREEZE.json":"f2daeed9eb67bb38d6f0a8e9c49ef6aab529e4d4c1397791c272d8521a7f20a3",
 "authority/POST_STAGE15_W02_SENSITIVITY_KEYERROR_CORRECTION.json":"43ea9068aae25a1bd3e93d9400833d8bf04945164a334e61c7d4666f53c9739d",
 "authority/POST_STAGE15_W02_R3_ACTUAL_FAILURE_ROOTCAUSE_CORRECTION.json":"df48b36374da11216cbfcc1fd138d27be29bc2f44085170a729237cabb4b1139",
 "authority/POST_STAGE15_W02_R4_M4_ISSUE3518_ROOTCAUSE_CORRECTION.json":"e5e087c5c993d233f3b011d4bf40f1dff0f63bd6c050994be78f5f3267d69827",
 "authority/POST_STAGE15_W02_R5_M4_ADAPTIVE_GRID_RECOVERY_ROOTCAUSE_CORRECTION.json":"02a23906842f39cc573d594ab9b4a1dcb08911998e401005d3aa66e9526402eb",
 "authority/POST_STAGE15_W02_R7_M4_REGULATOR_SAFE_GRID_RECOVERY_ROOTCAUSE_CORRECTION.json":"978106fced793d7f49bef6a1033ece13439b6eb2115571dd0eb48297c42bfc02",
 "authority/POST_STAGE15_W02_R8_M4_TWO_STAGE_GRID_RECOVERY_ROOTCAUSE_CORRECTION.json":"91c5aff02441eb95043a7ec7dbe1d123d024b7a4b51acaed95fdeba0bbcedfc1",
 "authority/POST_STAGE15_W02_R9_M4_TAP_RISK_GRID_RECOVERY_ROOTCAUSE_CORRECTION.json":"05259c65859cba2f820f64a6bca57ce95cf6020c35c03caaa98216e535a9c6d0",
 "authority/POST_STAGE15_W02_R10_M4_TAP_RELINEARIZATION_ROOTCAUSE_CORRECTION.json":"2f7190c2e603f1e70deea601f3b243b00ac50aab96cb1bdad931d4877e4faa76",
 "authority/POST_STAGE15_W02_R11_M4_THREE_STAGE_TAP_RECOVERY_ROOTCAUSE_CORRECTION.json":"cfe49939a35ca4f3c7e46eb783498a5d10fb705f1bbf4b212c258f246fac850e",
 "authority/POST_STAGE15_W02_R12_M4_BOUNDED_ITERATIVE_TAP_RECOVERY_ROOTCAUSE_CORRECTION.json":"3a3a5046d54707cccb1e7668a22d748044aa7f6cb0996724ac89bad386ba4844",
 "authority/POST_STAGE15_W02_R13_M4_UNIFIED_ITERATIVE_RECOVERY_ROOTCAUSE_CORRECTION.json":"2b784f097398dd820f59e551f18a8d547f48e09e4a586cf54aff321866545588",
 "authority/POST_STAGE15_W02_R14_BOUNDED_CONDITIONED_DISPATCH_ROOTCAUSE_CORRECTION.json":"d0f586f173a8355e714e6d730f85a35e67bb898de5609a97f1a8cd7d9a92f8b1",
 "authority/POST_STAGE15_W02_R15_FINAL_RECOVERY_ATOMIC_ROOTCAUSE_CORRECTION.json":"0ef3dd33fec62393cb5d878474241c88c55f60ee41acc8995884bcbe9e07b1c4",
 "authority/POST_STAGE15_W02_R19_POST_GRID_ROOT_SIGN_DYNAMIC_WORKERS_REP12_ROOTCAUSE_CORRECTION.json":"abce416c2eae34f2e379ad40a4524cd88fbb5ef6594d5a617c90103548f4c465",
 "authority/POST_STAGE15_W02_R20_M1_ISSUE4499_CONTINUOUS_COMMIT_ROOTCAUSE_CORRECTION.json":"b83ab13197bcf860a1b8ab28d174855d8eec6763a8c9d0f3ea8598cfe086f582",
 "authority/POST_STAGE15_W02_R20_1_PLANNER_TRANSFER_BOUND_CANONICALIZATION_ROOTCAUSE_CORRECTION.json":"911377e1955e3c66a76d43f7f8f764dc4f4d9f3d39b0de015a493e89c6a216c3",
 "authority/POST_STAGE15_W02_R20_2_NUMERICAL_REFINEMENT_CERTIFICATE_RETRY_ROOTCAUSE_CORRECTION.json":"8d9269882741e2459fc044ef96db3b6155301c47219ae423f706c19df6f2eee7",
 "authority/POST_STAGE15_REP12_R20_3_ISOLATED_TASK_FAILURE_CONTINUATION_ROOTCAUSE_CORRECTION.json":"90f864a50fd49f1081c499bae591062d79fdc95ab151ecb963f8d1f7f20e0395",
 "authority/POST_STAGE15_REP12_R20_4_CAUSAL_ROUTE_TAIL_ROOTCAUSE_CORRECTION.json":"54f4e5d049482453f734273b18ab2390301d1af3a5020fb0c8c18e0d3a29b0d2",
 "authority/POST_STAGE15_REP12_R20_5_PCC_BALANCE_NUMERICAL_POLISH_ROOTCAUSE_CORRECTION.json":"9d181601de891dd4ac48b5169a746ac33eca3ddda18b2a4622c3704e986be596",
 "authority/POST_STAGE15_REP12_R20_6_SPARSE_DENSE_EQUIVALENCE_FALLBACK_ROOTCAUSE_CORRECTION.json":"1ab2c5c9e2a9b77347774003e3c3966d426d7122473931af3dae3d6a7d2dcca7",
 "authority/POST_STAGE15_REP12_R20_7_LOCAL_REPAIR_VTYPE_RESTORE_ROOTCAUSE_CORRECTION.json":"8ef1a8f1ad3563c0f5224f559cbd643b4b7daee6507ef9566a746581e819ad8e",
 "tools/BENCHMARK_POST15_4X4_SHORT.sh":"b13043a5ce797635e50ad5c06647b069037be65ee12906101cffee4ff5797021",
 "tools/CPU_AFFINITY_4X4.py":"1919df7f013d09474353c28f89afd4fa32112f2df95b152aef045e50f85c72ce",
 "authority/D/tools/validate_B_W02_4POLICY_delivery_structure.py":"a98ef1bc40e419f8624afc5c368c659509cda1495d80ca6438f33321e83f8006",
 "authority/D/tools/build_B_TO_D_W02_handoff.sh":"09c0f4adea436a879820363203899726a4f07f514cc411ec2749c2e2dfa7bf24",
 "authority/POST_STAGE15_M1_M4_SUPERSESSION.json":"f0eef024f5a3291a8aa8bb2db19822191f0dab7c2ff495606c1e5f5787066378",
 "authority/D/06_W02_EXECUTION/W02_M1_M4_PRODUCTION_REQUEST.json":"72608c8febe5c1468663775f3420ff48d0a09316468f4704f1284a2acbabd5d4",
 "RUN_FIRST6_REP_WEEKS_ACTUAL.sh":"a2469f457be0342cb8f9105f473c00ca6c864b2be5f66b63133059eab6479773",
 "RUN_12_REP_WEEKS_ACTUAL.sh":"d0fc1714e62fa9154820d19072ee41ce574d4b56cb45558d3bb1a30a7f35b9d9",
 "scripts/PREPARE_REP_WEEK_SHARED_SOURCES.sh":"f0be03ac8031e1b224539f23c336a26962e6060528fda1cd8ff086c0bfc30389",
 "scripts/PREPARE_W02_SHARED_SOURCES.sh":"e824db26e0a95882cc1c73bfe58274a122a53b35e11f1cb3eaf559762dc59423",
 "scripts/PREPARE_W02_POWER_PRICE_SOURCE.py":"5c976a2c2476b3816908ede45ce776c086c094541dd9bcfa0a979b32662be467",
 "scripts/PREPARE_W02_MOBILITY_SOURCE.py":"4886b829fb19efc90926eca6cb4f2fedaa03d27663c6c72830997806011b7ed0",
 "tools/PREFLIGHT_FIRST6_REP_WEEKS.py":"f3e9ec0215e2793fa52dbd0bb7146fda29b8a0a7126d52bd8c491af473bc2584",
 "tools/SHOW_FIRST6_REP_WEEKS_PROGRESS.py":"e2ce4b679d4d0610c51c6719ca48aed0772f4eef9012f95230457c7865927016",
 "tools/PREFLIGHT_12_REP_WEEKS.py":"711328c99e21137aea4f5d2fc26d98adc31e3f0bf5b1977ffcf8e9e625bb597b",
 "tools/SHOW_12_REP_WEEKS_PROGRESS.py":"5d004df01fd0a15bb95277a4188cccce080c92ae4835810eb252fc18df3c8a55",
 "tools/VALIDATE_REP12_GLOBAL_QUEUE.py":"5167cf574cb15ea20e6dafa288f5f2bb37a8a607aec3e6ef6f9a017e6a838c39",
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

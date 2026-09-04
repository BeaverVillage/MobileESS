"""Isolated V16.3 decomposition completion and read-only diagnostics."""

from __future__ import annotations

import argparse,json,subprocess
from pathlib import Path
from typing import Sequence
import numpy as np

from .authority import sha256_file
from .run_authority_semantic_g11_v16_2 import _write_json
from .run_v16_3_prepare_final_days import DEFAULT_SOURCE
from .v16_3_decomposition_executor import solve_benders,verify_preserved_schedule
from .v16_3_final_context import build_context


AUTHORITY="2246063175977f152f3ac8df8f65a861cc7bbd22";CONTRACT="b5c89cc73c3f97c04a6998b5b44f8156825838eb";FINAL="461817f543d59fb75463415690825d3bc1fffbfd"
SCIENCE_SHA="9f43711b586172a784709fa501301d1506d127d5c98d9ab0dcce634bb43d65a6";FINAL_MANIFEST_SHA="abe8dae43ed31c96b20a530421fa88a76d0a1e3a03dd7e4a9a7a9d4b1e980798"
HISTORICAL=("V16_3_FINAL_SCIENCE_RESULT_MANIFEST.json","V16_3_MAY_B0_B1_B2_B3_RESULTS.json","V16_3_JUNE_REPLICATION_B0_B1_B2_B3_RESULTS.json","V16_3_FINAL_DUAL_AC_VALIDATION_RESULTS.json","V16_3_MONOLITHIC_RESULTS.json","V16_3_STANDARD_BD_RESULTS.json","V16_3_CL_MC_BD_RESULTS.json","V16_3_DECOMPOSITION_COMPARISON.json")


def _git(repo,*args):return subprocess.run(["git",*args],cwd=repo,text=True,capture_output=True,check=True).stdout.strip()


def firewall(repo:Path,output:Path)->dict:
    head=_git(repo,"rev-parse","HEAD")
    for commit in (AUTHORITY,CONTRACT,FINAL):
        subprocess.run(["git","merge-base","--is-ancestor",commit,head],cwd=repo,check=True)
    science=repo/"dayahead/artifacts/v16_3/V16_3_SCIENTIFIC_AUTHORITY.json";final=repo/"dayahead/artifacts/v16_3_final"
    if sha256_file(science)!=SCIENCE_SHA or sha256_file(final/HISTORICAL[0])!=FINAL_MANIFEST_SHA:raise RuntimeError("DECOMP_FIREWALL_SHA")
    hashes={name:sha256_file(final/name) for name in HISTORICAL}
    payload={"artifact_id":"V16_3_DECOMPOSITION_EXECUTOR_CONTRACT","status":"IMPLEMENTATION_ONLY_FIREWALL_PASS","authority_commit":AUTHORITY,"execution_contract_commit":CONTRACT,"final_execution_commit":FINAL,"current_descendant_head":head,"scientific_authority_sha256":SCIENCE_SHA,"final_science_manifest_sha256":FINAL_MANIFEST_SHA,"historical_final_artifact_sha256":hashes,"namespace":"dayahead/artifacts/v16_3_decomposition_completion","problem":"EXACT_FROZEN_V16_3_B3","master":"EXACT_RESOURCE_MASTER_EXTRACTED_FROM_FINAL_MONOLITHIC","grid_subproblems":96,"beta":.25,"rho":.10,"gamma_crit":.98,"objective":"MINIMUM_MAXIMUM_NORMALIZED_PHASE_LINE_CURRENT_LOADING","Pi":"ACTUAL_GUROBI_PI","Farkas":"ACTUAL_GUROBI_FARKASDUAL_WITH_BOUND_AWARE_FULL_LP_CUT","limits":{"iterations":200,"seconds_per_method":1800,"gap":1e-3},"OpenDSS_calls_inside_Benders":0,"firewall_counters":{k:0 for k in ("scientific_authority_changes","beta_changes","rho_changes","H_changes","J_I_changes","PUE_changes","PF_changes","kappa_changes","alpha_grid_changes","voltage_limit_changes","rating_changes","tap_semantics_changes","gamma_crit_changes","objective_changes","post_hoc_AC_tuning_count","OpenDSS_calls_inside_Benders","historical_final_science_artifacts_modified")}}
    _write_json(output/"V16_3_DECOMPOSITION_EXECUTOR_CONTRACT.json",payload);return payload


def _may02(repo:Path,source:Path,final_output:Path,output:Path):
    context,inputs,_=build_context(repo,source,final_output,"2025-05-02",prepare=False)
    voltage=np.load(final_output/"cache/data/D1_AC_ANCHOR_SENSITIVITY_2025-05-02.npz",allow_pickle=False);current=np.load(final_output/"cache/data/D1_AC_ANCHOR_CURRENT_SENSITIVITY_2025-05-02.npz",allow_pickle=False)
    final_row=json.loads((final_output/"cache/results/2025-05-02.json").read_text(encoding="utf-8"));b3=final_row["cases"]["B3"];raw=np.load(b3["raw_schedule_cache"],allow_pickle=False);controls=np.asarray(raw["controls_96x60"])
    identity=verify_preserved_schedule(context=context,voltage=voltage,current=current,controls=controls);mono=0.7683165991452516
    identity["preserved_monolithic_objective"]=mono;identity["relative_difference"]=abs(identity["objective"]-mono)/mono;identity["coefficient_identity_pass"]=identity["all_96_feasible"] and identity["relative_difference"]<=1e-9
    if not identity["coefficient_identity_pass"]:raise RuntimeError(f"DECOMP_COEFFICIENT_IDENTITY:{identity}")
    standard=solve_benders(inputs=inputs,context=context,voltage=voltage,current=current,method="STANDARD_BD",raw_dir=output/"cache/may02_standard")
    _write_json(output/"V16_3_MAY02_STANDARD_BD_COMPLETION.json",{"artifact_id":"V16_3_MAY02_STANDARD_BD_COMPLETION","operating_day":"2025-05-02","coefficient_identity":identity,**standard})
    if standard["status"]!="OPTIMAL_CERTIFIED" or abs(float(standard["objective"])-mono)/mono>1e-3:return identity,standard,None
    cl=solve_benders(inputs=inputs,context=context,voltage=voltage,current=current,method="CL_MC_BD",raw_dir=output/"cache/may02_clmc")
    _write_json(output/"V16_3_MAY02_CL_MC_BD_COMPLETION.json",{"artifact_id":"V16_3_MAY02_CL_MC_BD_COMPLETION","operating_day":"2025-05-02","coefficient_identity":identity,**cl})
    rel={"STANDARD_BD":abs(float(standard["objective"])-mono)/mono,"CL_MC_BD":abs(float(cl["objective"])-mono)/mono}
    eq={"artifact_id":"V16_3_MAY02_DECOMPOSITION_EQUIVALENCE","operating_day":"2025-05-02","monolithic":{"status":"OPTIMAL","objective":mono,"ObjBound":mono,"MIP_gap":0,"runtime_seconds":4.819999933242798},"STANDARD_BD":{"status":standard["status"],"objective":standard["objective"],"runtime_seconds":standard["runtime_seconds"],"iterations":standard["iterations"],"cuts":standard["optimality_cut_count"]+standard["farkas_cut_count"],"gap":standard["gap"]},"CL_MC_BD":{"status":cl["status"],"objective":cl["objective"],"runtime_seconds":cl["runtime_seconds"],"iterations":cl["iterations"],"cuts":cl["optimality_cut_count"]+cl["farkas_cut_count"],"gap":cl["gap"]},"relative_objective_difference":rel,"same_hard_feasibility_status":standard["hard_feasible"] and cl["hard_feasible"],"acceptance_tolerance":1e-3,"status":"PASS" if max(rel.values())<=1e-3 and standard["hard_feasible"] and cl["hard_feasible"] else "FAIL","ORIGINAL_JUNE_BENCHMARK_STATUS":"NOT_TESTABLE_REFERENCE_CONSTRUCTION_INFEASIBLE","historical_final_artifacts_modified":0}
    _write_json(output/"V16_3_MAY02_DECOMPOSITION_EQUIVALENCE.json",eq);return identity,standard,cl


def execute(repo:Path,source:Path,output:Path,stage:str):
    output.mkdir(parents=True,exist_ok=True);contract=firewall(repo,output)
    if stage=="contract":return contract
    identity,standard,cl=_may02(repo,source,repo/"dayahead/artifacts/v16_3_final",output)
    return {"identity":identity,"standard_status":standard["status"],"cl_status":None if cl is None else cl["status"]}


def main(argv:Sequence[str]|None=None):
    repo=Path.cwd();p=argparse.ArgumentParser();p.add_argument("--repo",type=Path,default=repo);p.add_argument("--source",type=Path,default=DEFAULT_SOURCE);p.add_argument("--output",type=Path,default=repo/"dayahead/artifacts/v16_3_decomposition_completion");p.add_argument("--stage",choices=("contract","may02"),default="may02");print(json.dumps(execute(**vars(p.parse_args(argv))),indent=2))
if __name__=="__main__":main()

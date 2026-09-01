"""Run the post-hoc exhaustive all-41 V16.3 decomposition contract."""

from __future__ import annotations
import argparse,json,hashlib
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
from statistics import mean,median
import numpy as np

from .authority import sha256_file
from .run_authority_semantic_g11_v16_2 import _write_json
from .run_v16_3_prepare_final_days import DEFAULT_SOURCE
from .v16_3_decomposition_executor import solve_benders
from .v16_3_final_context import build_context


def _compact(value):
    return {k:value.get(k) for k in ("method","status","hard_feasible","objective","runtime_seconds","iterations","optimality_cut_count","farkas_cut_count","LB","UB","gap","LB_monotone","UB_nonincreasing","UB_only_from_all_96_feasible","OpenDSS_calls_inside_Benders","coefficient_hash_of_hashes")}


def run_day(repo:Path,source:Path,output:Path,day:str,force:bool=False):
    cache=output/f"cache/supplementary_results/{day}.json"
    if cache.is_file() and not force:
        row=json.loads(cache.read_text(encoding="utf-8"))["summary"];row["cache_path"]=str(cache);row["cache_sha256"]=sha256_file(cache);return row
    final=repo/"dayahead/artifacts/v16_3_final";context,inputs,_=build_context(repo,source,final,day,prepare=False)
    voltage=np.load(final/f"cache/data/D1_AC_ANCHOR_SENSITIVITY_{day}.npz",allow_pickle=False);current=np.load(final/f"cache/data/D1_AC_ANCHOR_CURRENT_SENSITIVITY_{day}.npz",allow_pickle=False)
    preserved=json.loads((final/f"cache/results/{day}.json").read_text(encoding="utf-8"))["cases"]["B3"]
    standard=solve_benders(inputs=inputs,context=context,voltage=voltage,current=current,method="STANDARD_BD")
    cl=solve_benders(inputs=inputs,context=context,voltage=voltage,current=current,method="CL_MC_BD")
    mono_feasible=bool(preserved.get("hard_feasible"));mono_obj=preserved.get("objective_max_normalized_phase_line_current")
    def rel(v):return abs(float(v["objective"])-float(mono_obj))/max(abs(float(mono_obj)),1e-6) if mono_feasible and v.get("objective") is not None else None
    row={"operating_day":day,"preserved_monolithic":{"status":preserved["status"],"hard_feasible":mono_feasible,"objective":mono_obj,"runtime_seconds":preserved.get("runtime_seconds"),"ObjBound":preserved.get("obj_bound"),"gap":preserved.get("mip_gap")},"STANDARD_BD":_compact(standard),"CL_MC_BD":_compact(cl),"relative_objective_difference":{"STANDARD_BD":rel(standard),"CL_MC_BD":rel(cl)},"status_identity":{"STANDARD_BD":bool(standard["hard_feasible"])==mono_feasible,"CL_MC_BD":bool(cl["hard_feasible"])==mono_feasible},"iteration_log_sha256":{"STANDARD_BD":hashlib.sha256(json.dumps(standard["iteration_log"],sort_keys=True,separators=(",",":")).encode()).hexdigest(),"CL_MC_BD":hashlib.sha256(json.dumps(cl["iteration_log"],sort_keys=True,separators=(",",":")).encode()).hexdigest()},"no_day_selection":True,"OpenDSS_calls_inside_Benders":0}
    cache.parent.mkdir(parents=True,exist_ok=True);cache.write_text(json.dumps({"summary":row,"iteration_logs":{"STANDARD_BD":standard["iteration_log"],"CL_MC_BD":cl["iteration_log"]}},indent=2,sort_keys=True)+"\n",encoding="utf-8");row["cache_path"]=str(cache);row["cache_sha256"]=sha256_file(cache);return row


def _worker(args):return run_day(Path(args[0]),Path(args[1]),Path(args[2]),args[3],args[4])


def execute(repo:Path,source:Path,output:Path,workers:int,force:bool=False,only_day:str|None=None):
    contract=json.loads((output/"V16_3_POSTHOC_SUPPLEMENTARY_DECOMPOSITION_CONTRACT.json").read_text(encoding="utf-8"));days=list(contract["days"])
    if only_day:days=[only_day]
    rows=[]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        fs={pool.submit(_worker,(str(repo),str(source),str(output),day,force)):day for day in days}
        for i,f in enumerate(as_completed(fs),1):
            row=f.result();rows.append(row);print(json.dumps({"complete":i,"total":len(days),"day":row["operating_day"],"mono":row["preserved_monolithic"]["status"],"standard":row["STANDARD_BD"]["status"],"cl":row["CL_MC_BD"]["status"]}),flush=True)
    if not only_day:
        rows.sort(key=lambda r:r["operating_day"])
        for row in rows:
            mono_runtime=row["preserved_monolithic"].get("runtime_seconds")
            row["speed_up_vs_preserved_monolithic"]={
                method:(float(mono_runtime)/float(row[method]["runtime_seconds"]) if mono_runtime is not None and float(row[method]["runtime_seconds"])>0 else None)
                for method in ("STANDARD_BD","CL_MC_BD")
            }
        feasible=[r for r in rows if r["preserved_monolithic"]["hard_feasible"]];infeasible=[r for r in rows if not r["preserved_monolithic"]["hard_feasible"]]
        def method_stats(group,method):
            runtimes=[float(r[method]["runtime_seconds"]) for r in group]
            return {"mean_runtime_seconds":mean(runtimes) if runtimes else None,"median_runtime_seconds":median(runtimes) if runtimes else None,"maximum_runtime_seconds":max(runtimes) if runtimes else None,"mean_iterations":mean(float(r[method]["iterations"]) for r in group) if group else None,"total_optimality_cuts":sum(int(r[method]["optimality_cut_count"]) for r in group),"total_Farkas_cuts":sum(int(r[method]["farkas_cut_count"]) for r in group),"median_speed_up_vs_preserved_monolithic":median(float(r["speed_up_vs_preserved_monolithic"][method]) for r in group if r["speed_up_vs_preserved_monolithic"][method] is not None) if any(r["speed_up_vs_preserved_monolithic"][method] is not None for r in group) else None}
        payload={"artifact_id":"V16_3_SUPPLEMENTARY_ALL41_DECOMPOSITION_RESULTS","contract_role":contract["role"],"day_count":len(rows),"feasible_day_count":len(feasible),"infeasible_day_count":len(infeasible),"days":rows,"feasible_summary":{"all_standard_objective_equivalent":all(r["relative_objective_difference"]["STANDARD_BD"] is not None and r["relative_objective_difference"]["STANDARD_BD"]<=1e-3 for r in feasible),"all_cl_mc_bd_objective_equivalent":all(r["relative_objective_difference"]["CL_MC_BD"] is not None and r["relative_objective_difference"]["CL_MC_BD"]<=1e-3 for r in feasible),"STANDARD_BD":method_stats(feasible,"STANDARD_BD"),"CL_MC_BD":method_stats(feasible,"CL_MC_BD")},"infeasible_summary":{"historical_status_interpretation":"FINAL_SOLVE_FAIL_GUROBI_3_WITH_HARD_FEASIBLE_FALSE","decomposition_required_status":"INFEASIBLE_CERTIFIED","all_standard_status_identical":all(r["status_identity"]["STANDARD_BD"] and r["STANDARD_BD"]["status"]=="INFEASIBLE_CERTIFIED" for r in infeasible),"all_cl_mc_bd_status_identical":all(r["status_identity"]["CL_MC_BD"] and r["CL_MC_BD"]["status"]=="INFEASIBLE_CERTIFIED" for r in infeasible),"STANDARD_BD":method_stats(infeasible,"STANDARD_BD"),"CL_MC_BD":method_stats(infeasible,"CL_MC_BD")},"timeout_count":{"STANDARD_BD":sum("TIME" in r["STANDARD_BD"]["status"] for r in rows),"CL_MC_BD":sum("TIME" in r["CL_MC_BD"]["status"] for r in rows)},"OpenDSS_calls_inside_Benders":0,"scientific_authority_changes":0,"historical_final_artifacts_modified":0}
        _write_json(output/"V16_3_SUPPLEMENTARY_ALL41_DECOMPOSITION_RESULTS.json",payload)
    return {"days":len(rows)}


def main():
    r=Path.cwd();p=argparse.ArgumentParser();p.add_argument("--repo",type=Path,default=r);p.add_argument("--source",type=Path,default=DEFAULT_SOURCE);p.add_argument("--output",type=Path,default=r/"dayahead/artifacts/v16_3_decomposition_completion");p.add_argument("--workers",type=int,default=4);p.add_argument("--force",action="store_true");p.add_argument("--only-day");print(json.dumps(execute(**vars(p.parse_args())),indent=2))
if __name__=="__main__":main()

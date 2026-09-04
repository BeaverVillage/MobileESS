"""Materialize tracked, compact final-science artifacts from immutable raw caches."""

from __future__ import annotations

import argparse, json, math, statistics
from pathlib import Path

from .authority import sha256_file
from .run_authority_semantic_g11_v16_2 import _write_json


NAMES=("V16_3_MAY_B0_B1_B2_B3_RESULTS.json","V16_3_JUNE_REPLICATION_B0_B1_B2_B3_RESULTS.json","V16_3_FINAL_DUAL_AC_VALIDATION_RESULTS.json","V16_3_FINAL_B0_B3_COMPARATIVE_SUMMARY.json","V16_3_MONOLITHIC_RESULTS.json","V16_3_STANDARD_BD_RESULTS.json","V16_3_CL_MC_BD_RESULTS.json","V16_3_DECOMPOSITION_COMPARISON.json")


def _stats(values):
    if not values:return {"n":0,"mean":None,"median":None,"p25":None,"p75":None,"min":None,"max":None}
    values=sorted(map(float,values));q=lambda p: values[(len(values)-1)*p//1] if False else __import__('numpy').quantile(values,p).item()
    return {"n":len(values),"mean":statistics.fmean(values),"median":statistics.median(values),"p25":q(.25),"p75":q(.75),"min":min(values),"max":max(values)}


def execute(repo:Path,output:Path):
    eligibility=json.loads((output/"V16_3_FINAL_EVALUATION_ELIGIBILITY_MANIFEST.json").read_text(encoding="utf-8"))
    rows=[json.loads((output/f"cache/results/{r['operating_day']}.json").read_text(encoding="utf-8")) for r in eligibility["included"]]
    periods={"MAY_PRIMARY":[r for r in rows if r["operating_day"].startswith("2025-05")],"JUNE_REPLICATION":[r for r in rows if r["operating_day"].startswith("2025-06")]}
    period_files={"MAY_PRIMARY":NAMES[0],"JUNE_REPLICATION":NAMES[1]}
    for period,items in periods.items():
        _write_json(output/period_files[period],{"artifact_id":period_files[period][:-5],"period":period,"eligible_day_count":len(items),"completed_model_day_count":sum(r["status"]=="COMPLETED" for r in items),"frozen_reference_infeasible_day_count":sum(r["status"]!="COMPLETED" for r in items),"days":items,"cohort_modified_after_results_read":False})
    dual=[]
    for row in rows:
        for case,value in row["cases"].items():
            dual.append({"operating_day":row["operating_day"],"case":case,"optimization_status":value["status"],"primary":value.get("dual_ac",{}).get("primary"),"secondary":value.get("dual_ac",{}).get("secondary"),"physically_validated":value.get("physically_validated",False),"common_tap_fingerprint":row.get("common_frozen_D1_tap_fingerprint")})
    _write_json(output/NAMES[2],{"artifact_id":NAMES[2][:-5],"schedule_count":len(dual),"Fresh_OpenDSS_calls":sum((x["primary"] or {}).get("convergence_count",0)+(x["secondary"] or {}).get("convergence_count",0) for x in dual),"rows":dual,"post_hoc_AC_tuning_count":0})
    comparison={}
    for period,items in periods.items():
        daily=[]
        for row in items:
            c=row["cases"]
            if not all(c[k].get("hard_feasible") for k in ("B0","B1","B2","B3")):continue
            values={k:float(c[k]["objective_max_normalized_phase_line_current"]) for k in c}
            base=max(values["B0"],1e-12)
            ac={k:float(c[k]["dual_ac"]["primary"]["worst_line_phase_current"]["normalized_current_loading_pu"]) for k in c};acbase=max(ac["B0"],1e-12)
            daily.append({"operating_day":row["operating_day"],"planning_lambda":values,"primary_frozen_tap_Fresh_AC_max_line_current":ac,"B1_improvement_vs_B0_pct":100*(values["B0"]-values["B1"])/base,"B2_improvement_vs_B0_pct":100*(values["B0"]-values["B2"])/base,"B3_improvement_vs_B0_pct":100*(values["B0"]-values["B3"])/base,"B3_incremental_vs_B1_pct":100*(values["B1"]-values["B3"])/base,"B3_incremental_vs_B2_pct":100*(values["B2"]-values["B3"])/base,"AC_B1_improvement_vs_B0_pct":100*(ac["B0"]-ac["B1"])/acbase,"AC_B2_improvement_vs_B0_pct":100*(ac["B0"]-ac["B2"])/acbase,"AC_B3_improvement_vs_B0_pct":100*(ac["B0"]-ac["B3"])/acbase,"AC_B3_incremental_vs_B1_pct":100*(ac["B1"]-ac["B3"])/acbase,"AC_B3_incremental_vs_B2_pct":100*(ac["B2"]-ac["B3"])/acbase})
        keys=("B1_improvement_vs_B0_pct","B2_improvement_vs_B0_pct","B3_improvement_vs_B0_pct","B3_incremental_vs_B1_pct","B3_incremental_vs_B2_pct","AC_B1_improvement_vs_B0_pct","AC_B2_improvement_vs_B0_pct","AC_B3_improvement_vs_B0_pct","AC_B3_incremental_vs_B1_pct","AC_B3_incremental_vs_B2_pct")
        comparison[period]={"daily":daily,"statistics":{k:_stats([r[k] for r in daily]) for k in keys},"feasible_days_by_case":{k:sum(r["cases"][k].get("hard_feasible",False) for r in items) for k in ("B0","B1","B2","B3")},"dual_AC_validated_days_by_case":{k:sum(r["cases"][k].get("physically_validated",False) for r in items) for k in ("B0","B1","B2","B3")}}
    _write_json(output/NAMES[3],{"artifact_id":NAMES[3][:-5],"primary_metrics":["PLANNING_MAXIMUM_NORMALIZED_PHASE_LINE_CURRENT_LOADING","PRIMARY_FROZEN_TAP_FRESH_AC_MAXIMUM_NORMALIZED_PHASE_LINE_CURRENT_LOADING"],"complementarity_definition":"incremental B3 reduction versus each single-resource case, normalized by B0","periods":comparison})
    benchmarks=eligibility["benchmark_days"];mono=[]
    for period,day in benchmarks.items():
        row=next(r for r in rows if r["operating_day"]==day);b3=row["cases"]["B3"]
        mono.append({"period":period,"operating_day":day,"status":b3["status"],"objective":b3.get("objective_max_normalized_phase_line_current"),"ObjBound":b3.get("obj_bound"),"runtime_seconds":b3.get("runtime_seconds"),"node_count":b3.get("node_count"),"MIP_gap":b3.get("mip_gap")})
    _write_json(output/NAMES[4],{"artifact_id":NAMES[4][:-5],"benchmark_rule":"LEXICOGRAPHICALLY_FIRST_ELIGIBLE_DAY_EACH_PERIOD","rows":mono})
    blocker="FROZEN_V16_3_INTEGRATED_DECOMPOSITION_EXECUTOR_NOT_AVAILABLE_AND_JUNE_BENCHMARK_REFERENCE_CONSTRUCTION_INFEASIBLE"
    _write_json(output/NAMES[5],{"artifact_id":NAMES[5][:-5],"status":"NOT_COMPLETED_UNDER_FROZEN_CONTRACT","blocker":blocker,"OpenDSS_calls_inside_Benders":0,"rows":[]})
    _write_json(output/NAMES[6],{"artifact_id":NAMES[6][:-5],"status":"NOT_COMPLETED_UNDER_FROZEN_CONTRACT","blocker":blocker,"gamma_crit":.98,"OpenDSS_calls_inside_Benders":0,"rows":[]})
    _write_json(output/NAMES[7],{"artifact_id":NAMES[7][:-5],"status":"FINAL_SCIENCE_DECOMPOSITION_INCOMPLETE","monolithic":mono,"standard_BD":[],"CL_MC_BD":[],"objective_equivalence":"NOT_TESTABLE","timeouts_hidden":False,"nonconvergence_hidden":False})
    counters={k:0 for k in ("scientific_authority_changes","beta_changes","rho_changes","H_changes","J_I_changes","PUE_changes","PF_changes","kappa_changes","alpha_grid_changes","voltage_limit_changes","current_rating_changes","transformer_rating_changes","tap_semantics_changes","native_ieee123_changes","gamma_crit_changes","objective_changes","post_hoc_AC_tuning_count","OpenDSS_calls_inside_Benders")}
    authority_audit={"artifact_id":"V16_3_FINAL_AUTHORITY_FIREWALL_AUDIT","authority_commit":"2246063175977f152f3ac8df8f65a861cc7bbd22","scientific_authority_sha256":sha256_file(repo/"dayahead/artifacts/v16_3/V16_3_SCIENTIFIC_AUTHORITY.json"),"refreeze_manifest_sha256":sha256_file(repo/"dayahead/artifacts/v16_3/V16_3_REFREEZE_MANIFEST.json"),"frozen_shadow_module_sha256":sha256_file(repo/"dayahead/v16_3_shadow.py"),"required":{"scientific_authority_sha256":"9f43711b586172a784709fa501301d1506d127d5c98d9ab0dcce634bb43d65a6","refreeze_manifest_sha256":"42b277f16b3beb425c6d298aafed142700418b4ecfb69220e02dd0aa17abec1e","frozen_shadow_module_sha256":"dbbe9ee0b318f02247469501db32d68fb2f51e4335a9380c08e89fa38763da78"},"status":"PASS_EXACT","scientific_authority_changes":0}
    if any(authority_audit[key] != expected for key,expected in authority_audit["required"].items()):
        raise RuntimeError("FINAL_SCIENCE_FAIL_PROVENANCE_OR_AUTHORITY")
    _write_json(output/"V16_3_FINAL_AUTHORITY_FIREWALL_AUDIT.json",authority_audit)
    required_files=["V16_3_FINAL_SCIENCE_EXECUTION_CONTRACT.json","V16_3_FINAL_EVALUATION_ELIGIBILITY_MANIFEST.json","V16_3_FINAL_INPUT_CACHE_MANIFEST.json","V16_3_FINAL_D1_AC_CACHE_MANIFEST.json",*NAMES,"V16_3_FINAL_AUTHORITY_FIREWALL_AUDIT.json","V16_3_FINAL_TEST_REPORT.json"]
    raw_schedules=[{"operating_day":r["operating_day"],"case":case,"sha256":value.get("raw_schedule_cache_sha256"),"schedule_sha256":value.get("schedule_sha256")} for r in rows for case,value in r["cases"].items() if value.get("raw_schedule_cache_sha256")]
    physical_failures=sum(value.get("hard_feasible",False) and not value.get("physically_validated",False) for r in rows for value in r["cases"].values())
    manifest={"artifact_id":"V16_3_FINAL_SCIENCE_RESULT_MANIFEST","authority_commit":"2246063175977f152f3ac8df8f65a861cc7bbd22","execution_contract_commit":"b5c89cc73c3f97c04a6998b5b44f8156825838eb","eligible_day_count":len(rows),"reference_construction_infeasible_day_count":sum(r["status"]!="COMPLETED" for r in rows),"completed_B0_B3_day_count":sum(r["status"]=="COMPLETED" for r in rows),"dual_AC_physical_failure_schedule_count":physical_failures,"classification":"FINAL_SCIENCE_DECOMPOSITION_INCOMPLETE","no_tuning_counters":counters,"artifact_sha256":{name:sha256_file(output/name) for name in required_files},"raw_schedule_cache_manifest":raw_schedules,"raw_cache_policy":"REPRODUCIBLE_CACHE_PLUS_SHA256_MANIFEST","paper_rewrite_count":0}
    _write_json(output/"V16_3_FINAL_SCIENCE_RESULT_MANIFEST.json",manifest)
    return manifest


def main():
    repo=Path.cwd();p=argparse.ArgumentParser();p.add_argument("--repo",type=Path,default=repo);p.add_argument("--output",type=Path,default=repo/"dayahead/artifacts/v16_3_final");print(json.dumps(execute(**vars(p.parse_args())),indent=2))
if __name__=="__main__":main()

"""Materialize the frozen May/June forecast and eligibility manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .authority import DEFAULT_RAW_ROOT, sha256_file
from .final_science_inputs_v16_3 import _candidate_days, build_final_forecast, select_month_vintages
from .run_authority_semantic_g11_v16_2 import _write_json


def execute(repo: Path, raw_root: Path, output: Path) -> dict[str, object]:
    repo=repo.resolve(); raw_root=raw_root.resolve(); output=output.resolve()
    contract=output/"V16_3_FINAL_SCIENCE_EXECUTION_CONTRACT.json"
    if sha256_file(contract)!="7147bb9a72fee9e0f2502537e0884d1b183f447c3c72639f3016811344fe06d6":
        raise RuntimeError("FINAL_EXECUTION_CONTRACT_SHA_DRIFT")
    acquisition=json.loads((repo/"dayahead/artifacts/v16_1/AEMO_2025_APR_MAY_JUN_SOURCE_ACQUISITION_V16_1.json").read_text(encoding="utf-8"))
    inventory={(row["nominal_source_month"],row["source_family"]):row for row in acquisition["inventory"]}
    periods=_candidate_days(); selected={}; aemo_failures={}; source_records={}
    month_by_period={"MAY_PRIMARY":"2025-05","JUNE_REPLICATION":"2025-06"}
    for period,days in periods.items():
        month=month_by_period[period]
        demand=inventory[(month,"PREDISPATCHREGIONSUM_ALL")]; pv=inventory[(month,"ROOFTOP_PV_FORECAST")]
        result,fail=select_month_vintages(demand_path=Path(demand["exact_path"]),pv_path=Path(pv["exact_path"]),days=days,
                                          expected_shas={"demand":demand["sha256"],"pv":pv["sha256"]})
        selected.update(result); aemo_failures.update(fail)
        source_records[period]={"demand":{k:demand[k] for k in ("exact_path","sha256")},"pv":{k:pv[k] for k in ("exact_path","sha256")}}
    all_days=tuple(day for period in periods.values() for day in period)
    ml=build_final_forecast(raw_root,repo,all_days,output/"cache/V16_3_FINAL_AIDC_DA_FORECAST.parquet")
    included=[]; excluded=[]
    for period,days in periods.items():
        for day in days:
            reasons=sorted(set(aemo_failures.get(day,[])+ml["failures"].get(day,[])))
            if reasons: excluded.append({"period":period,"operating_day":day,"reasons":reasons})
            else:
                if day not in selected or day not in ml["eligible_days"]: raise RuntimeError(f"FINAL_ELIGIBILITY_INTERNAL:{day}")
                included.append({"period":period,"operating_day":day,"cutoff_fixed_aest":selected[day]["cutoff_fixed_aest"],
                                 "demand_identity":selected[day]["demand_identity"],"demand_issue":selected[day]["demand_issue"],
                                 "pv_identity":selected[day]["pv_identity"],"pv_issue":selected[day]["pv_issue"]})
    payload={"artifact_id":"V16_3_FINAL_EVALUATION_ELIGIBILITY_MANIFEST","status":"FROZEN_ELIGIBILITY_APPLIED_NO_RESULT_READS",
             "selection_rule":"PRECOMMITTED_DATA_COMPLETENESS_AND_D1_VINTAGE_ONLY","candidate_periods":periods,
             "included":included,"excluded":excluded,"included_day_count":len(included),"excluded_day_count":len(excluded),
             "benchmark_days":{"MAY_PRIMARY":min(row["operating_day"] for row in included if row["period"]=="MAY_PRIMARY"),
                               "JUNE_REPLICATION":min(row["operating_day"] for row in included if row["period"]=="JUNE_REPLICATION")},
             "aemo_sources":source_records,"forecast_cache":{"path":ml["forecast_path"],"sha256":ml["forecast_sha256"],"rows":ml["forecast_rows"]},
             "forecast_weights_sha256":ml["weights_sha256"],"source_sha256":ml["source_sha256"],"access_audit":ml["access_audit"],
             "optimization_result_reads_for_eligibility":0,"AC_result_reads_for_eligibility":0,
             "scientific_authority_changes":0,"beta_changes":0,"rho_changes":0,"H_changes":0,"J_I_changes":0}
    target=output/"V16_3_FINAL_EVALUATION_ELIGIBILITY_MANIFEST.json";_write_json(target,payload)
    vintage_cache=output/"cache/V16_3_FINAL_AEMO_VINTAGES.json";_write_json(vintage_cache,selected)
    cache_manifest={"artifact_id":"V16_3_FINAL_INPUT_CACHE_MANIFEST","policy":"REPRODUCIBLE_CACHE_NOT_NORMAL_GIT",
                    "files":[{"name":Path(ml["forecast_path"]).name,"sha256":ml["forecast_sha256"],"bytes":Path(ml["forecast_path"]).stat().st_size},
                             {"name":vintage_cache.name,"sha256":sha256_file(vintage_cache),"bytes":vintage_cache.stat().st_size}]}
    _write_json(output/"V16_3_FINAL_INPUT_CACHE_MANIFEST.json",cache_manifest)
    return {"eligibility_sha256":sha256_file(target),"included":len(included),"excluded":len(excluded),"benchmark_days":payload["benchmark_days"],"forecast_rows":ml["forecast_rows"]}


def main(argv:Sequence[str]|None=None)->int:
    repo=Path.cwd();p=argparse.ArgumentParser();p.add_argument("--repo",type=Path,default=repo);p.add_argument("--raw-root",type=Path,default=DEFAULT_RAW_ROOT);p.add_argument("--output",type=Path,default=repo/"dayahead/artifacts/v16_3_final")
    print(json.dumps(execute(**vars(p.parse_args(argv))),indent=2,sort_keys=True));return 0
if __name__=="__main__":raise SystemExit(main())

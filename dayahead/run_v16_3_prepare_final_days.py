"""Generate frozen D-1 AC voltage/current caches for eligible final days."""

from __future__ import annotations

import argparse,json
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
from typing import Sequence

from .authority import sha256_file
from .v16_3_final_context import build_context,reference_delta_diagnostic


DEFAULT_SOURCE=Path(r"C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\tmp\c12_exact_sources_repo_cleanup\c12_exact_sources\v2038_parent\Conversation3_Exact_AC_Remediation_Sweep_From_Conversation1_V2038\reference")


def _worker(args):
    repo,source,output,day=Path(args[0]),Path(args[1]),Path(args[2]),args[3]
    voltage=output/f"cache/data/D1_AC_ANCHOR_SENSITIVITY_{day}.npz"
    current=output/f"cache/data/D1_AC_ANCHOR_CURRENT_SENSITIVITY_{day}.npz"
    if voltage.is_file() and current.is_file():
        return {"day":day,"status":"PREPARED","voltage_sha256":sha256_file(voltage),"current_sha256":sha256_file(current),"voltage_bytes":voltage.stat().st_size,"current_bytes":current.stat().st_size}
    try:
        _context,_inputs,records=build_context(repo,source,output,day,prepare=True)
    except RuntimeError as exc:
        if str(exc)!="PENETRATION_REFERENCE_RESIDUAL_NEGATIVE": raise
        return reference_delta_diagnostic(repo,output,day)
    return {"day":day,"status":"PREPARED","voltage_sha256":records["voltage"]["sha256"],"current_sha256":records["current"]["sha256"],"voltage_bytes":records["voltage"].get("bytes",Path(records["voltage"]["path"]).stat().st_size),"current_bytes":records["current"]["bytes"]}


def execute(repo:Path,source:Path,output:Path,workers:int,only_day:str|None=None):
    eligibility=json.loads((output/"V16_3_FINAL_EVALUATION_ELIGIBILITY_MANIFEST.json").read_text(encoding="utf-8"));days=sorted(row["operating_day"] for row in eligibility["included"])
    if only_day: days=[only_day]
    results=[]
    if workers<=1:
        for i,day in enumerate(days,1):
            row=_worker((str(repo),str(source),str(output),day));results.append(row);print(json.dumps({"stage":"PREPARE", "complete":i,"total":len(days),**row}),flush=True)
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures={pool.submit(_worker,(str(repo),str(source),str(output),day)):day for day in days}
            for i,future in enumerate(as_completed(futures),1):
                row=future.result();results.append(row);print(json.dumps({"stage":"PREPARE","complete":i,"total":len(days),**row}),flush=True)
    if not only_day:
        prepared=[row for row in results if row["status"]=="PREPARED"]
        failures=[row for row in results if row["status"]!="PREPARED"]
        manifest={"artifact_id":"V16_3_FINAL_D1_AC_CACHE_MANIFEST","policy":"REPRODUCIBLE_CACHE_NOT_NORMAL_GIT","file_count":2*len(prepared),"prepared_day_count":len(prepared),"frozen_reference_failure_day_count":len(failures),"days":sorted(prepared,key=lambda x:x["day"]),"frozen_reference_failures":sorted(failures,key=lambda x:x["day"]),"H_changes":0,"J_I_changes":0,"May_June_outcome_reads_for_generation":0}
        from .run_authority_semantic_g11_v16_2 import _write_json
        _write_json(output/"V16_3_FINAL_D1_AC_CACHE_MANIFEST.json",manifest)
    return {"days":len(results),"files":2*sum(row["status"]=="PREPARED" for row in results),"frozen_reference_failures":sum(row["status"]!="PREPARED" for row in results)}


def main(argv:Sequence[str]|None=None)->int:
    repo=Path.cwd();p=argparse.ArgumentParser();p.add_argument("--repo",type=Path,default=repo);p.add_argument("--source",type=Path,default=DEFAULT_SOURCE);p.add_argument("--output",type=Path,default=repo/"dayahead/artifacts/v16_3_final");p.add_argument("--workers",type=int,default=1);p.add_argument("--only-day")
    print(json.dumps(execute(**vars(p.parse_args(argv))),indent=2));return 0
if __name__=="__main__":raise SystemExit(main())

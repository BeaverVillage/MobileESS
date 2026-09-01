"""Execute frozen V16.3 B0-B3 and dual Fresh OpenDSS for every eligible day."""

from __future__ import annotations

import argparse, json, time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np

from .authority import sha256_file
from .run_planning_ac_voltage_forensic_v1 import _compile
from .run_v16_3_correction import _ac_summary
from .run_v16_3_nonzero_validity import _apply_vector, _fresh_capture
from .run_v16_3_prepare_final_days import DEFAULT_SOURCE
from .run_v16_3_voltage_candidate import (
    CAPACITORS, REGULATORS, _enable_native_controls, _fix_controls,
    _regulator_taps, _set_slot,
)
from .v16_3_final_context import build_context, reference_delta_diagnostic
from .final_science_solver_v16_3 import solve_shadow


def _dual_ac(repo: Path, source: Path, context, voltage, controls: np.ndarray) -> dict[str, object]:
    reference, _vintage, background, binding, _cache, _authority = context
    nodes=tuple(map(str,voltage["node_names"])); branches=tuple(binding.factories[0].data.branches)
    limits=np.asarray([float(binding.factories[0].data.line_limit_kva_u080[(b.branch_id,b.phase)]) for b in branches])
    odd,adapter=_compile(source,repo,"NATIVE")
    primary=[];secondary=[];tap_slots=0;tap_counts={name:0 for name in REGULATORS};max_tap=0.0
    for slot in range(96):
        taps={name:float(voltage["regulator_taps"][slot,i]) for i,name in enumerate(REGULATORS)}
        caps={name:[int(voltage["capacitor_states"][slot,i])] for i,name in enumerate(CAPACITORS)}
        values=np.asarray(controls[slot],dtype=float)
        _set_slot(odd,adapter,background,reference["plan_kw_96x12"],slot)
        _fix_controls(odd,taps,caps);_apply_vector(odd,tuple(map(str,voltage["control_names"])),values);odd.Solution.SolveSnap()
        if not odd.Solution.Converged(): return {"primary":{"convergence_count":len(primary),"status":f"NONCONVERGED_SLOT_{slot}"},"secondary":{"convergence_count":len(secondary),"status":"NOT_COMPLETED"}}
        primary.append(_fresh_capture(odd,nodes,branches,limits,range(len(branches))))
        _set_slot(odd,adapter,background,reference["plan_kw_96x12"],slot)
        _fix_controls(odd,taps,caps);_enable_native_controls(odd);_apply_vector(odd,tuple(map(str,voltage["control_names"])),values);odd.Solution.SolveSnap()
        if not odd.Solution.Converged(): return {"primary":_ac_summary(primary),"secondary":{"convergence_count":len(secondary),"status":f"NONCONVERGED_SLOT_{slot}"}}
        secondary.append(_fresh_capture(odd,nodes,branches,limits,range(len(branches))))
        actual=_regulator_taps(odd);changed=False
        for name in REGULATORS:
            delta=abs(float(actual[name])-taps[name])
            if delta>1e-12: changed=True;tap_counts[name]+=1;max_tap=max(max_tap,delta)
        tap_slots+=int(changed)
    return {"primary":_ac_summary(primary),"secondary":{**_ac_summary(secondary),"tap_change_slot_count":tap_slots,"tap_change_counts_by_regulator":tap_counts,"max_tap_deviation_from_D1":max_tap}}


def _case_summary(case: str, solved: dict, context, inputs, raw_path: Path) -> dict[str, object]:
    controls=np.asarray(solved.pop("controls_96x60"));workload=np.asarray(solved.pop("workload_payload"))
    mp=np.asarray(solved.pop("mess_p_96x4"));mq=np.asarray(solved.pop("mess_q_96x4"));me=np.asarray(solved.pop("mess_e_97x4"))
    reference=context[0]["reference"].allocation
    ref=np.asarray([reference[k] for k in sorted(reference)])
    shifted=float(np.maximum(workload-ref,0).sum())
    redistribution=float(np.abs(workload-ref).sum()/2)
    np.savez_compressed(raw_path,controls_96x60=controls,workload=workload,mess_p=mp,mess_q=mq,mess_e=me)
    return solved,controls,{"raw_schedule_cache":str(raw_path),"raw_schedule_cache_sha256":sha256_file(raw_path),"AIDC_flexible_workload_shifted_nodeh":shifted,"AIDC_location_time_redistribution_nodeh":redistribution,"MESS_charge_energy_kwh":float(np.maximum(-mp,0).sum()*.25),"MESS_discharge_energy_kwh":float(np.maximum(mp,0).sum()*.25),"MESS_reactive_abs_kvarh":float(np.abs(mq).sum()*.25),"MESS_initial_SOC_kwh":list(map(float,me[0])),"MESS_terminal_SOC_kwh":list(map(float,me[-1]))}


def run_day(repo: Path, source: Path, output: Path, day: str, *, force: bool=False) -> dict[str, object]:
    result_path=output/f"cache/results/{day}.json"
    if result_path.is_file() and not force: return json.loads(result_path.read_text(encoding="utf-8"))
    cache_manifest=json.loads((output/"V16_3_FINAL_D1_AC_CACHE_MANIFEST.json").read_text(encoding="utf-8"))
    failure=next((r for r in cache_manifest["frozen_reference_failures"] if r["day"]==day),None)
    if failure:
        row={"operating_day":day,"status":"FROZEN_REFERENCE_CONSTRUCTION_INFEASIBLE","cases":{case:{"case":case,"status":"NOT_BUILT_REFERENCE_INFEASIBLE","hard_feasible":False} for case in ("B0","B1","B2","B3")},"reference_failure":failure}
    else:
        context,inputs,_=build_context(repo,source,output,day,prepare=False)
        voltage=np.load(output/f"cache/data/D1_AC_ANCHOR_SENSITIVITY_{day}.npz",allow_pickle=False)
        current=np.load(output/f"cache/data/D1_AC_ANCHOR_CURRENT_SENSITIVITY_{day}.npz",allow_pickle=False)
        cases={};raw_dir=output/"cache/schedules";raw_dir.mkdir(parents=True,exist_ok=True)
        batch_started=time.perf_counter();batch=solve_shadow(inputs=inputs,context=context,voltage_data=voltage,current_data=current,rho=.1,case="ALL")
        for case in ("B0","B1","B2","B3"):
            started=time.perf_counter();solved=batch[case]
            if solved["hard_feasible"]:
                solved,controls,extra=_case_summary(case,solved,context,inputs,raw_dir/f"{day}_{case}.npz")
                ac=_dual_ac(repo,source,context,voltage,controls)
                cases[case]={**solved,**extra,"dual_ac":ac,"physically_validated":bool(ac["primary"].get("all_frozen_hard_constraints_pass") and ac["secondary"].get("all_frozen_hard_constraints_pass")),"end_to_end_wall_seconds":time.perf_counter()-started}
            else: cases[case]={**solved,"dual_ac":{"primary":{"convergence_count":0},"secondary":{"convergence_count":0}},"physically_validated":False,"end_to_end_wall_seconds":time.perf_counter()-started}
        row={"operating_day":day,"status":"COMPLETED","cases":cases,"common_frozen_D1_tap_fingerprint":sha256_file(output/f"cache/data/D1_AC_ANCHOR_SENSITIVITY_{day}.npz"),"post_hoc_tuning_count":0}
    result_path.parent.mkdir(parents=True,exist_ok=True);result_path.write_text(json.dumps(row,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    return row


def _worker(args): return run_day(Path(args[0]),Path(args[1]),Path(args[2]),args[3],force=args[4])


def execute(repo: Path, source: Path, output: Path, workers: int, only_day: str|None=None, force: bool=False):
    eligibility=json.loads((output/"V16_3_FINAL_EVALUATION_ELIGIBILITY_MANIFEST.json").read_text(encoding="utf-8"));days=sorted(r["operating_day"] for r in eligibility["included"])
    if only_day: days=[only_day]
    rows=[]
    if workers<=1:
        for i,d in enumerate(days,1): rows.append(run_day(repo,source,output,d,force=force));print(json.dumps({"complete":i,"total":len(days),"day":d,"status":rows[-1]["status"]}),flush=True)
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures={pool.submit(_worker,(str(repo),str(source),str(output),d,force)):d for d in days}
            for i,f in enumerate(as_completed(futures),1):
                row=f.result();rows.append(row);print(json.dumps({"complete":i,"total":len(days),"day":row["operating_day"],"status":row["status"]}),flush=True)
    return {"day_count":len(rows),"completed":sum(r["status"]=="COMPLETED" for r in rows),"reference_failures":sum(r["status"]!="COMPLETED" for r in rows)}


def main():
    repo=Path.cwd();p=argparse.ArgumentParser();p.add_argument("--repo",type=Path,default=repo);p.add_argument("--source",type=Path,default=DEFAULT_SOURCE);p.add_argument("--output",type=Path,default=repo/"dayahead/artifacts/v16_3_final");p.add_argument("--workers",type=int,default=1);p.add_argument("--only-day");p.add_argument("--force",action="store_true")
    print(json.dumps(execute(**vars(p.parse_args())),indent=2))
if __name__=="__main__":main()

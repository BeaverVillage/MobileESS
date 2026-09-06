"""May-01 diagnosis only: saved execution metrics and fixed-input AC crossovers.

Crossovers are diagnostic injections, never accepted decisions or campaign cases.
No optimizer, job admission, route search, command shift, or authority change.
"""
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

import numpy as np
import pandas as pd
from dayahead.paper_analysis.storage import read, reference, write_json, write_parquet, digest, sha
from dayahead.v40d_actual.preflight import verify_protected


def main():
    root = REPO / "dayahead/artifacts/v40d_actual_realized_replay"
    smoke = root / "smoke/2025-05-01"
    output = root / "objective_diagnosis/2025-05-01"
    output.mkdir(parents=True, exist_ok=True)
    before = {str(p): sha(p) for p in smoke.rglob("*") if p.is_file()}
    guard = verify_protected(REPO, root)
    if guard["status"] != "PASS":
        raise RuntimeError("PROTECTED_INPUT_DRIFT")
    metrics, jobs, powers, fleets, sources = [], {}, {}, {}, {}
    for case in ("B0", "B1", "B2", "B3"):
        folder = smoke / case
        j = pd.read_parquet(folder / "job_ledger.parquet").set_index("job_uid").sort_index()
        x = pd.read_parquet(folder / "aidc_site_timeseries.parquet")
        m = pd.read_parquet(folder / "MESS_executed_trajectory.parquet")
        jobs[case] = j
        powers[case] = {key: x.pivot(index="slot", columns="site_id", values=field).to_numpy()
                        for key, field in (("PCC_P", "P_PCC_kW"), ("PCC_Q", "Q_PCC_kvar"))}
        ids = sorted(m.mess_id.unique())
        def pivot(field):
            return m.pivot(index="slot", columns="mess_id", values=field).reindex(columns=ids).to_numpy()
        locations = pivot("actual_service_id").astype(object)
        locations[pd.isna(locations)] = "TRANSIT_UNAVAILABLE"
        fleets[case] = {"p": pivot("P_EXEC"), "q": pivot("Q_EXEC"),
                        "ids": ids, "locations": locations.astype(str)}
        with np.load(folder / "actual_grid/OPENDSS_PHASE_ARRAYS.npz") as z:
            mask = z["branch_kinds"] == "line"
            current = z["phase_current_loading_pu"][:, mask]
            t, b = np.unravel_index(current.argmax(), current.shape)
            rho = float(current[t, b])
            peak = {"peak_slot": int(t), "peak_time": f"{t // 4:02d}:{t % 4 * 15:02d}",
                    "branch": str(z["branch_names"][mask][b]), "phase": str(z["branch_phases"][mask][b])}
        active = (j.actual_residual_start < 120) & (j.actual_execution_end > 24) & j.AIDC_site.ne("UNASSIGNED")
        da_case = "B0" if case == "B2" else case
        da_path = REPO / f"dayahead/artifacts/v39e_full_may_2025/V39E_DAYAHEAD_DECISION_FREEZE_2025-05-01_{da_case}.json"
        decision = read(da_path)["decision"]
        planned_gpu = pd.DataFrame(decision["site_GPU_trajectory"])
        metrics.append({"case": case, "Actual_AC_rho": rho, **peak,
                        "D_day_GPU_slot_hours": float(x.occupied_GPU.sum() * .25),
                        "D_day_PCC_kWh": float(x.P_PCC_kW.sum() * .25),
                        "D_day_active_jobs": int(active.sum()),
                        "D_day_completed_jobs": int(((j.actual_execution_end > 24) & (j.actual_execution_end <= 120)).sum()),
                        "GPU_hours_remaining_at_H": float(j.remaining_GPU_hours_at_H.sum()),
                        "GPU_hours_waiting_at_H": float(j.backlog_GPU_hours.sum()),
                        "capacity_delay_jobs": int(j.delayed_by_GPU_capacity.sum()),
                        "unassigned_post_H_jobs": int(j.status.eq("UNASSIGNED_POST_H_BACKLOG").sum()),
                        "pre_day_complete_jobs": int(j.status.eq("PRE_DAY_COMPLETE").sum()),
                        "planned_GPU_slot_hours": float(planned_gpu.active_GPU.sum() * .25),
                        "planned_full_site_slots": int((planned_gpu.active_GPU == planned_gpu.AIDC_GPU_capacity).sum()),
                        "planned_site_slots": len(planned_gpu), "temporal_mode": decision["temporal_mode"]})
        sources[case] = {name: reference(folder / name) for name in
                         ("job_ledger.parquet", "aidc_site_timeseries.parquet", "MESS_executed_trajectory.parquet", "actual_grid/OPENDSS_PHASE_ARRAYS.npz")}
        sources[case]["frozen_DA"] = reference(da_path)
    pairs = []
    for a, b in (("B0", "B1"), ("B0", "B2"), ("B1", "B3")):
        if not jobs[a].index.equals(jobs[b].index):
            raise RuntimeError("JOB_POPULATION_MISMATCH")
        row = {"pair": a + "_" + b, "same_job_universe": True, "job_count": len(jobs[a])}
        # Excluded / post-H records carry original start_slot and AIDC_site too.
        for key in ("start_slot", "end_slot", "AIDC_site", "actual_runtime_seconds"):
            x, y = jobs[a][key], jobs[b][key]
            row[key + "_changed_count"] = int((~(x.eq(y) | (x.isna() & y.isna()))).sum())
        row["actual_PCC_exact_equal"] = all(np.array_equal(powers[a][k], powers[b][k]) for k in powers[a])
        pairs.append(row)
    stage_root = REPO / "dayahead/artifacts/v40b_v40a_may_launch/days/2025-05-01/B3"
    checkpoint = read(stage_root / "COOPT_PLANNING_CHECKPOINT.json")
    stages = read(stage_root / "COOPT_STAGE_OBJECTIVES.json")
    result = {"scope": "MAY01_DIAGNOSIS_ONLY", "full_campaign_authorized": False,
              "job_hour_definition": "sum integer slot occupancy * 0.25 h; not fractional job service hours",
              "cases": metrics, "pairs": pairs, "sources": sources,
              "A0_A1_jobs_exact_equal": checkpoint["a0"] == checkpoint["a1"],
              "B3_stage_objectives_pre_AC_restoration": stages,
              "stage_sources": [reference(stage_root / n) for n in ("COOPT_PLANNING_CHECKPOINT.json", "COOPT_STAGE_OBJECTIVES.json")],
              "crossovers_are_not_accepted_case_results": True}
    write_json(output / "SAVED_METRICS.json", result)
    write_parquet(output / "CASE_METRICS.parquet", pd.DataFrame(metrics))
    print("Saved execution metrics audited", flush=True)

    import gurobipy as gp
    from dayahead.v40a.context import load_planning_context
    from dayahead.v40d_actual.grid_replay import replay
    original = gp.Model.optimize
    optimizer_calls = 0
    def forbidden(*args, **kwargs):
        nonlocal optimizer_calls
        optimizer_calls += 1
        raise RuntimeError("DIAGNOSTIC_OPTIMIZATION_FORBIDDEN")
    gp.Model.optimize = forbidden
    context = None
    crossovers = []
    try:
        context = load_planning_context(REPO, "2025-05-01")
        with np.load(smoke / "actual_exogenous.npz") as z:
            exo = {"demand_mw": z["demand_mw"], "pv_mw": z["pv_mw"],
                   "timestamps": pd.date_range("2025-05-01", periods=96, freq="15min", tz="Etc/GMT-10").map(lambda t: t.isoformat()).tolist()}
        # Own-case repeats validate exact reconstruction before interpreting swaps.
        for aidc, mess_case in (("B0", "B2"), ("B1", "B3"), ("B1", "B2"), ("B0", "B3")):
            tag = "AIDC_" + aidc + "_MESS_" + mess_case
            print("Diagnostic fixed-injection AC " + tag, flush=True)
            identity = digest({"role": "DIAGNOSTIC_ONLY_NOT_ACCEPTED_DECISION", "AIDC": sources[aidc], "MESS": sources[mess_case]})
            physical, binding = replay(REPO, "2025-05-01", tag, context, powers[aidc], exo, fleets[mess_case], identity, output / tag)
            own_case = "B2" if (aidc, mess_case) == ("B0", "B2") else "B3" if (aidc, mess_case) == ("B1", "B3") else None
            exact = None
            if own_case:
                with np.load(smoke / own_case / "actual_grid/OPENDSS_PHASE_ARRAYS.npz") as old:
                    exact = all(np.array_equal(getattr(physical, k), old[k], equal_nan=True) for k in
                                ("voltage_pu", "phase_current_a", "phase_current_loading_pu", "losses_kw_kvar", "regulator_taps", "capacitor_states", "convergence"))
                if not exact:
                    raise RuntimeError("OWN_CASE_RECONSTRUCTION_NOT_EXACT")
            crossovers.append({"AIDC_source_case": aidc, "MESS_source_case": mess_case,
                               "diagnostic_AC_rho": physical.summary["rho_max_AC"],
                               "voltage_violation_count": physical.summary["voltage_violation_count"],
                               "own_case_exact_repeat": exact, "rho_audit": binding["Actual_rho_recalculation"]})
    finally:
        gp.Model.optimize = original
        if context is not None:
            context.electrical.voltage.close()
            context.electrical.current.close()
    result["crossovers"] = crossovers
    result["optimizer_calls"] = optimizer_calls
    result["protected_after"] = verify_protected(REPO, root)
    result["original_smoke_changed_files"] = [p for p, expected in before.items() if sha(p) != expected]
    if result["protected_after"]["status"] != "PASS" or result["original_smoke_changed_files"]:
        raise RuntimeError("PROTECTED_RESULT_MODIFIED")
    result["status"] = "DIAGNOSTIC_COMPLETE"
    write_json(output / "OBJECTIVE_DIAGNOSIS.json", result)
    print({"status": result["status"], "crossovers": [{k: v for k, v in c.items() if k != "rho_audit"} for c in crossovers],
           "protected_diff": result["protected_after"]["changed_count"], "optimizer_calls": optimizer_calls}, flush=True)


if __name__ == "__main__":
    main()

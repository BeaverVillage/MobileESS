"""Recover numerical Planning arrays from exact saved controls and sealed caches.

Only this offline adapter imports the production numerical functions. Solver
entrypoints are disabled. Monthly analysis uses the saved arrays alone.
"""
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pandas as pd
from .storage import read, sha, reference, write_json, write_npz, write_parquet, STAGES


def grid_arrays(coefficients, controls, nodes):
    from dayahead.v28r2.electrical_subproblem import anchored_polygon_loading, is_dominated_mess_current_row
    voltage, v2s, loading, p, q, linear, kva = [], [], [], [], [], [], []
    for c, x in zip(coefficients, controls, strict=True):
        v2 = c.voltage_constant + c.voltage_matrix.T @ x
        v2s.append(v2)
        voltage.append(np.sqrt(v2))
        loading.append(anchored_polygon_loading(c, x))
        p.append(c.flow_p_constant + c.flow_p_matrix @ x)
        q.append(c.flow_q_constant + c.flow_q_matrix @ x)
        linear.append(c.current_constant + c.current_matrix.T @ x)
        kva.append([np.nan if r is None else np.hypot(p[-1][k], q[-1][k]) / r
                    for k, r in enumerate(c.transformer_ratings)])
    names = np.asarray(coefficients[0].branch_names)
    return {"voltage_pu": np.asarray(voltage), "voltage_squared_pu": np.asarray(v2s),
        "node_names": np.asarray(nodes), "branch_phase_names": names,
        "line_objective_mask": np.asarray([not n.startswith("transformer.") and not is_dominated_mess_current_row(n) for n in names]),
        "phase_current_loading_pu": np.asarray(loading), "linear_current_loading_pu": np.asarray(linear),
        "flow_p_kw": np.asarray(p), "flow_q_kvar": np.asarray(q),
        "transformer_kva_loading_pu": np.asarray(kva),
        "branch_limit_kVA_surrogate": np.asarray([c.branch_limits for c in coefficients]),
        "transformer_rating_kVA": np.asarray([[np.nan if r is None else r for r in c.transformer_ratings] for c in coefficients]),
        "controls": np.asarray(controls), "control_names": np.asarray(coefficients[0].control_names),
        "coefficient_SHA": np.asarray([c.coefficient_sha256 for c in coefficients]),
        "voltage_lower_pu": np.asarray(.95), "voltage_upper_pu": np.asarray(1.05)}


def site_rows(jobs, context, internal_stage):
    from dayahead.v40a.feedback import pcc_from_jobs
    from dayahead.v39a.power import site_it_power_kw, validate_power_conservation, frozen_site_to_pcc
    from dayahead.v36.contracts import PF_TAN
    pcc, occ = pcc_from_jobs(jobs, context)
    counts = np.zeros_like(occ)
    sites = list(context.capacity.aidc_ids)
    for r in jobs:
        start, end = max(24, r["start_slot"]), min(120, r["end_slot"])
        if start < end:
            counts[start-24:end-24, sites.index(r["AIDC_site"])] += 1
    mapping = frozen_site_to_pcc(context.repo)
    injections = context.electrical.legacy_context[3].factories[0].data.master_p_injection
    rows, checks = [], []
    for t in range(96):
        checks.append(validate_power_conservation(context.capacity.site_capacity, dict(zip(sites, map(int, occ[t])))))
        for i, site in enumerate(sites):
            cap = context.capacity.site_capacity[site]
            control = f"aidc_load_kw[{site}]"
            buses = sorted({str(bus) for (bus, phase), values in injections.items() if control in values})
            rows.append({"date": context.day, "internal_stage": internal_stage, "paper_stage": STAGES[internal_stage],
                "site_id": site, "slot": t, "active_job_count": int(counts[t, i]),
                "occupied_GPU_slots": int(occ[t, i]), "GPU_capacity": cap,
                "GPU_occupancy_fraction": float(occ[t, i] / cap),
                "P_IT_kW": float(site_it_power_kw(cap, int(occ[t, i]))),
                "P_PCC_kW": float(pcc[t, i]), "Q_PCC_kvar": float(pcc[t, i] * PF_TAN),
                "PCC": mapping[site], "buses": buses,
                "conversion_identifier": "FROZEN_CENTER_GPU_POWER_PLUS_EXACT_C1_D1_WEATHER"})
    expected = sum(int(r["requested_GPU"]) * max(0, min(120, r["end_slot"]) - max(24, r["start_slot"])) for r in jobs)
    if expected != int(occ.sum()) or not all(r["status"] == "PASS" for r in checks):
        raise RuntimeError("PAPER_GPU_IT_CONSERVATION_FAIL")
    return pd.DataFrame(rows), {"status": "PASS", "GPU_slot_sum": expected,
        "duplicated_job_UIDs": len(jobs) - len({r["job_uid"] for r in jobs}), "IT_conservation_by_slot": checks}


def recover_day(repo, day, output):
    from dayahead.v40a.context import load_planning_context
    from dayahead.v40a.grid import controls_from_trajectory, evaluate_grid
    from dayahead.v40a.feedback import pcc_from_jobs
    repo, output = Path(repo), Path(output)
    source = repo / "dayahead/artifacts/v40b_v40a_may_launch/days" / day / "B3"
    context = load_planning_context(repo, day)
    context.repo = repo
    try:
        expected = read(source / "D1_INPUT_PROVENANCE.json")["source_shas"]
        # Comparison is SHA-based; path portability never substitutes different content.
        if set(expected.values()) != set(context.input_shas.values()):
            raise RuntimeError("PAPER_NUMERIC_SOURCE_SHA_MISMATCH:" + day)
        payload = read(source / "FINAL_JOINT_DECISION_PAYLOAD.json")
        jobs = payload["AIDC_decision"]
        slots = [SimpleNamespace(**r) for r in payload["MESS_trajectory"]]
        pcc, _ = pcc_from_jobs(jobs, context)
        controls = controls_from_trajectory(context.coefficients, pcc, slots)
        observed = evaluate_grid(context.coefficients, controls, context.nodes)
        original = read(source / "PLANNING_PHYSICAL_GATES.json")
        for key in ("rho_max", "Vmin", "Vmax", "maximum_transformer_phase_current", "maximum_transformer_kVA"):
            if observed[key] != original[key]:
                raise RuntimeError("PAPER_NUMERIC_RESULT_NOT_BIT_EQUAL:" + key)
        arrays = grid_arrays(context.coefficients, controls, context.nodes)
        write_npz(output / "planning/planning_voltage_arrays.npz", **{k: arrays[k] for k in ("voltage_pu", "voltage_squared_pu", "node_names", "voltage_lower_pu", "voltage_upper_pu")})
        write_npz(output / "planning/planning_line_arrays.npz", **{k: arrays[k] for k in ("branch_phase_names", "phase_current_loading_pu", "linear_current_loading_pu", "flow_p_kw", "flow_q_kvar", "line_objective_mask", "branch_limit_kVA_surrogate")})
        write_npz(output / "planning/planning_transformer_arrays.npz", **{k: arrays[k] for k in ("branch_phase_names", "transformer_kva_loading_pu", "transformer_rating_kVA", "linear_current_loading_pu", "flow_p_kw", "flow_q_kvar")})
        write_npz(output / "planning/controls.npz", controls=controls, control_names=arrays["control_names"], coefficient_SHA=arrays["coefficient_SHA"])
        for name, internal in (("AIDC_PASS0_DECISION.parquet", "A0"), ("AIDC_FEEDBACK_PASS1_DECISION.parquet", "A1")):
            frame = pd.read_parquet(source / name)
            rows, checks = site_rows(frame.to_dict("records"), context, internal)
            write_parquet(output / f"{STAGES[internal]}_site_timeseries.parquet", rows)
            write_json(output / f"{STAGES[internal]}_conservation.json", checks)
        data = context.electrical.legacy_context[3].factories[0].data
        topology = [{"branch_id": b.branch_id, "phase": b.phase, "sending_bus": b.parent_bus,
                     "receiving_bus": b.child_bus, "model_ampacity_a_u080": b.ampacity_a_u080} for b in data.branches]
        from dayahead.v28r2.opendss_mapping import FeederAssets, REGULATORS, CAPACITORS
        from dayahead.v36.contracts import SOURCE_DATA_REPOSITORY
        assets = FeederAssets.from_repo(SOURCE_DATA_REPOSITORY)
        write_json(output / "planning/numeric_recovery.json", {"status": "PASS", "method": "EXACT_FROZEN_CACHE_EVALUATION_NO_SOLVER",
            "objective_and_extrema_bit_equal": True, "coefficient_SHAs": list(arrays["coefficient_SHA"]),
            "input_references": [reference(p) for p in context.input_shas],
            "feeder_assets": {k: reference(p) for k, p in vars(assets).items()},
            "topology": topology, "regulator_ids": list(REGULATORS), "capacitor_ids": list(CAPACITORS),
            "grid_injection_map": [{"bus": bus, "phase": phase, "P_controls": weights,
                                    "Q_controls": data.master_q_injection.get((bus, phase), {})}
                                   for (bus, phase), weights in data.master_p_injection.items()],
            "source_result": reference(source / "PLANNING_PHYSICAL_GATES.json")})
        return observed
    finally:
        context.electrical.voltage.close()
        context.electrical.current.close()


def recover(repo, days, root):
    import gurobipy as gp
    original = gp.Model.optimize
    calls = 0
    def forbidden(*args, **kwargs):
        nonlocal calls
        calls += 1
        raise RuntimeError("PAPER_BACKFILL_OPTIMIZATION_FORBIDDEN")
    gp.Model.optimize = forbidden
    rows = []
    try:
        for day in days:
            output = Path(root) / "days" / day / "B3"
            if (output / "planning/numeric_recovery.json").exists():
                print(day + " cached exact recovery", flush=True)
                continue
            try:
                recover_day(repo, day, output)
                rows.append({"day": day, "status": "PASS"})
                print(day + " exact numerical recovery PASS", flush=True)
            except Exception as e:
                rows.append({"day": day, "status": "RESULT_PERSISTENCE_FAIL", "error": repr(e)})
                print(day + " FAIL " + repr(e), flush=True)
                raise
    finally:
        gp.Model.optimize = original
        write_json(Path(root) / "NUMERIC_RECOVERY_STATUS.json", {"rows": rows, "optimizer_calls": calls})

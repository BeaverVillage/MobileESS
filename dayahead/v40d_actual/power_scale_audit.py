"""Independent scale arithmetic and read-only OpenDSS component observation.

Only May-01 accepted decisions are replayed. No optimization or science changes.
"""
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace
import csv
import gzip
import math
import numpy as np
import pandas as pd
from dayahead.paper_analysis.storage import read, reference, sha, digest, write_json, write_npz, write_parquet

ALPHA = 0.7481417265421424
P95 = 7100.2615
PV_DENOMINATOR = 4021.226
CAPACITIES = np.array([64, 32, 64, 32, 80, 64, 32, 64, 32, 64, 32, 64])
SITES = [f"AIDC{i:02d}" for i in range(1, 13)]
NUMERICAL_KW_TOLERANCE = 1e-8


def independent_background(paths, timestamps, operational, rooftop, output):
    """Read raw weights/lookup tables, without production synthesis helpers."""
    adapter = read(paths.runtime_adapter)
    buses = np.load(paths.bus_ids).astype(str).tolist()
    clusters = np.load(paths.clusters).astype(int)
    capacity = np.load(paths.pv_capacity).astype(float)
    index = {b.lower(): i for i, b in enumerate(buses)}
    p = np.zeros((len(buses), 3)); q = np.zeros_like(p)
    for load in adapter["loads"]:
        for phase in load["phases"]:
            p[index[load["bus"].lower()], phase - 1] += float(load["base_p_kw"]) / len(load["phases"])
            q[index[load["bus"].lower()], phase - 1] += float(load["base_q_kvar"]) / len(load["phases"])
    with gzip.open(paths.residual_lookup, "rt", encoding="utf-8-sig") as f:
        residual = {(int(r["cluster_id"]), int(r["month"]), r["day_type"], int(r["slot_30min"])): float(r["residual"]) for r in csv.DictReader(f)}
    with gzip.open(paths.q_lookup, "rt", encoding="utf-8-sig") as f:
        qfactor = {(int(r["month"]), r["day_type"], int(r["slot_30min"])): float(r["q_variation_factor"]) for r in csv.DictReader(f)}
    qp = q.sum() / p.sum()
    native_qp = np.divide(q, p, out=np.zeros_like(q), where=p > 1e-9)
    relative_qp = np.where(p > 0, np.clip(native_qp / qp, .15, 3.), 0.)
    gross, reactive, pv, rows = [], [], [], []
    for t, (stamp, op, roof) in enumerate(zip(timestamps, operational, rooftop)):
        dt = datetime.fromisoformat(str(stamp)); typ = "weekday" if dt.weekday() < 5 else "weekend"
        halfhour = dt.hour * 2 + dt.minute // 30
        op_pre = float(op) * 3490.0 / P95
        pv_pre = float(roof) / PV_DENOMINATOR * float(capacity.sum())
        target = ALPHA * (op_pre + pv_pre)
        weights = np.empty_like(p)
        for i, cluster in enumerate(clusters):
            weights[i] = p[i] * residual[int(cluster), dt.month, typ, halfhour]
        grow = weights * (target / weights.sum())
        qraw = grow * relative_qp
        qrow = qraw * (target * qp * qfactor[dt.month, typ, halfhour] / qraw.sum())
        pvrow = capacity * (float(roof) / PV_DENOMINATOR) * ALPHA
        gross.append(grow); reactive.append(qrow); pv.append(pvrow)
        rows.append({"slot": t, "timestamp": stamp, "regional_operational_demand_MW": float(op),
                     "regional_rooftop_pv_MW": float(roof), "regional_gross_demand_MW": float(op + roof),
                     "normalized_demand_profile": float(op / P95), "demand_normalization_denominator_MW": P95,
                     "alpha_grid": ALPHA, "feeder_background_total_kw": target,
                     "sum_bus_phase_background_kw": float(grow.sum()),
                     "regional_pv_source_value_MW": float(roof), "pv_normalization_denominator_MW": PV_DENOMINATOR,
                     "normalized_pv_profile": float(roof / PV_DENOMINATOR),
                     "feeder_pv_available_pre_alpha_kw": pv_pre,
                     "feeder_pv_available_kw": ALPHA * pv_pre, "sum_phase_pv_kw": float(pvrow.sum()),
                     "expected_operational_net_kw": ALPHA * op_pre,
                     "net_identity_error_kw": float((grow - pvrow).sum() - ALPHA * op_pre)})
    frame = pd.DataFrame(rows)
    write_parquet(output / "BACKGROUND_PV_INTERMEDIATES_96.parquet", frame)
    frame.to_csv(output / "BACKGROUND_PV_INTERMEDIATES_96.csv", index=False, encoding="utf-8-sig", float_format="%.17g")
    arrays = {"background_P_kw": np.asarray(gross), "background_Q_kvar": np.asarray(reactive), "PV_P_kw": np.asarray(pv)}
    write_npz(output / "INDEPENDENT_BUS_PHASE_BACKGROUND_PV.npz", bus_ids=np.array(buses), phases=np.array(["A", "B", "C"]), **arrays)
    mapping = {"bus_ids": buses, "cluster_ids": clusters.tolist(), "native_P_kw": p.tolist(), "native_Q_kvar": q.tolist(), "PV_capacity_kw": capacity.tolist()}
    write_json(output / "FROZEN_SPATIAL_MAPPING.json", mapping)
    return {"arrays": arrays, "frame": frame, "buses": buses, "mapping": mapping, "capacity_sum": float(capacity.sum())}


def binding_errors(background, independent):
    errors = {}
    for field, name in (("background_P_kw", "gross_p_kw_96"), ("background_Q_kvar", "gross_q_kvar_96"), ("PV_P_kw", "pv_generation_kw_96")):
        expected = independent["arrays"][field]
        observed = np.array([[[getattr(background, name)[t].get((b.lower(), p), 0.) for p in "ABC"] for b in independent["buses"]] for t in range(96)])
        errors[field] = float(np.max(np.abs(observed - expected)))
    return errors


def independent_c1(it, weather, payload):
    c, o = payload["coefficients"], payload["other_model_coefficients"]
    # These constants are independently pinned to the frozen C1 authority.
    from dayahead.v28.thermal import GFS_NORMALIZATION_FACTOR
    scale = 3.4987194698200215
    result = np.zeros_like(it)
    for t in range(96):
        wb, rh = float(weather.iloc[t].t_wb_c), float(weather.iloc[t].rh_pct)
        excess = max(wb - payload["t_ref_c"], 0.)
        for s in range(12):
            mw = it[t, s] * scale / 1000
            latent = (c["intercept"] + c["it_mw"] * mw + c["it_mw_squared"] * mw**2 + c["wetbulb_c"] * wb
                      + c["wetbulb_excess_c"] * excess + c["it_mw_x_wetbulb_excess_c"] * mw * excess + c["rh_pct"] * rh)
            other = o["intercept"] + o["it_mw"] * mw
            result[t, s] = it[t, s] + GFS_NORMALIZATION_FACTOR / scale * (np.logaddexp(0., latent) + np.logaddexp(0., other))
    return result


def engine_inventory(odd):
    elements, ratings = [], []
    for name in sorted(odd.Circuit.AllElementNames()):
        odd.Circuit.SetActiveElement(name)
        elements.append({"name": name.lower(), "buses": list(odd.CktElement.BusNames()), "phases": odd.CktElement.NumPhases(), "node_order": list(odd.CktElement.NodeOrder())})
        if name.lower().startswith("line."):
            odd.Lines.Name(name.split(".", 1)[1])
            ratings.append({"name": name.lower(), "NormAmps": odd.Lines.NormAmps(), "EmergAmps": odd.Lines.EmergAmps()})
        elif name.lower().startswith("transformer."):
            odd.Transformers.Name(name.split(".", 1)[1])
            for winding in range(1, odd.Transformers.NumWindings() + 1):
                odd.Transformers.Wdg(winding)
                ratings.append({"name": name.lower(), "winding": winding, "kVA": odd.Transformers.kVA(), "kV": odd.Transformers.kV()})
    voltage = []
    for name in odd.Vsources.AllNames():
        odd.Vsources.Name(name)
        voltage.append({"name": name, "pu": odd.Vsources.PU(), "base_kV": odd.Vsources.BasekV(), "phases": odd.Vsources.Phases(), "frequency": odd.Vsources.Frequency(), "angle_deg": odd.Vsources.AngleDeg()})
    return {"elements": elements, "ratings": ratings, "source_voltage": voltage,
            "compiled_bus_phase_mask": sorted(str(n).lower() for n in odd.Circuit.AllNodeNames())}


@contextmanager
def observe_components(namespace, case, output):
    from dayahead.v28r2 import opendss_backend as backend
    original = backend.apply_trajectory_slot
    original_voltage = backend._voltage_vector
    element_rows, summaries = [], []
    result = {}
    def wrapper(odd, adapter, context, trajectory, slot):
        original(odd, adapter, context, trajectory, slot)
        active = str(odd.CktElement.Name())
        try:
            background = context.legacy_context[2]
            expected = {}
            for r in adapter["loads"]:
                phases = ["ABC"[int(p) - 1] for p in r["phases"]]; bus = r["bus"].lower()
                expected["load." + r["load_name"].lower()] = ("background", sum(background.gross_p_kw_96[slot].get((bus, p), 0.) for p in phases), sum(background.gross_q_kvar_96[slot].get((bus, p), 0.) for p in phases))
            for r in adapter["pv_generators"]:
                expected["generator." + r["generator_name"].lower()] = ("PV", background.pv_generation_kw_96[slot].get((r["bus"].lower(), "ABC"[int(r["phase"]) - 1]), 0.), 0.)
            for i in range(12):
                expected[f"load.idc_idc{i + 1:02d}"] = ("AIDC", trajectory.pcc_p_kw[slot, i], trajectory.pcc_q_kvar[slot, i])
            services = {}
            for i, location in enumerate(trajectory.mess_locations_96x4[slot]):
                if str(location).upper().startswith("TRANSIT_"):
                    if trajectory.mess_p_kw[slot, i] != 0 or trajectory.mess_q_kvar[slot, i] != 0:
                        raise RuntimeError("DISCONNECTED_MESS_POWER")
                    continue
                values = services.setdefault(str(location).lower(), [0., 0.])
                values[0] += float(trajectory.mess_p_kw[slot, i]); values[1] += float(trajectory.mess_q_kvar[slot, i])
            sums = {k: [Fraction(0), Fraction(0)] for k in ("background", "PV", "AIDC", "MESS")}
            net_p = net_q = Fraction(0); mismatches = 0
            for kind, api in (("load", odd.Loads), ("generator", odd.Generators)):
                for name in sorted(api.AllNames()):
                    api.Name(name); key = kind + "." + name.lower()
                    if name.lower().startswith("mess_"):
                        service = name.split("_", 2)[2].lower(); p, q = services.get(service, [0., 0.])
                        ep, eq = (max(-p, 0.), 0.) if kind == "load" else (max(p, 0.), q)
                        component = "MESS"
                    else:
                        if key not in expected:
                            raise RuntimeError("UNCLASSIFIED_OPENDSS_ELEMENT:" + key)
                        component, ep, eq = expected[key]
                    rp, rq = float(api.kW()), float(api.kvar())
                    mismatches += int(rp != ep or rq != eq)
                    sign = -1 if kind == "generator" else 1
                    dp, dq = Fraction.from_float(rp), Fraction.from_float(rq)
                    net_p += sign * dp; net_q += sign * dq
                    component_sign = sign if component == "MESS" else 1
                    sums[component][0] += component_sign * dp; sums[component][1] += component_sign * dq
                    element_rows.append({"namespace": namespace, "case": case, "slot": slot, "element": key, "component": component,
                                         "P_kw": rp, "Q_kvar": rq, "expected_P_kw": float(ep), "expected_Q_kvar": float(eq),
                                         "setpoint_exact_match": rp == ep and rq == eq, "net_consumption_sign": sign})
            if mismatches:
                write_json(output / "EXACT_READBACK_MISMATCH.json", {"slot": slot, "rows": [r for r in element_rows if r["slot"] == slot and not r["setpoint_exact_match"]]})
                # Keep the exact-match failure and finish all requested slots/cases.
                # Do not silently substitute a numerical tolerance for the user gate.
            component_net = sums["background"][0] - sums["PV"][0] + sums["AIDC"][0] + sums["MESS"][0]
            component_q = sums["background"][1] - sums["PV"][1] + sums["AIDC"][1] + sums["MESS"][1]
            if component_net != net_p or component_q != net_q:
                raise RuntimeError("COMPONENT_CONSERVATION")
            summaries.append({"namespace": namespace, "case": case, "slot": slot,
                              **{f"{k}_{field}": float(sums[k][i]) for k in sums for i, field in enumerate(("P_kw", "Q_kvar"))},
                              "P_net_kw": float(component_net), "Q_net_kvar": float(component_q),
                              "OpenDSS_setpoint_net_P_kw": float(net_p), "OpenDSS_setpoint_net_Q_kvar": float(net_q),
                              "component_conservation_P_error_kw": float(component_net - net_p),
                              "component_conservation_Q_error_kvar": float(component_q - net_q),
                              "component_setpoint_mismatch_count": mismatches})
        finally:
            odd.Circuit.SetActiveElement(active)
    def voltage_observer(odd, nodes):
        values = original_voltage(odd, nodes)
        # NodeOrder is available only after the first ordinary SolveSnap.
        if "inventory" not in result:
            active = str(odd.CktElement.Name())
            try:
                result["inventory"] = engine_inventory(odd)
                write_json(output / "ENGINE_MAPPING_RATINGS_SOURCE.json", result["inventory"])
            finally:
                odd.Circuit.SetActiveElement(active)
        return values
    backend.apply_trajectory_slot = wrapper
    backend._voltage_vector = voltage_observer
    try:
        yield result
        frame = pd.DataFrame(summaries)
        if len(frame) != 96:
            raise RuntimeError("COMPONENT_COVERAGE_NOT_96")
        elements = pd.DataFrame(element_rows)
        result.update(frame=frame, exact_setpoint_match=bool(elements.setpoint_exact_match.all()), zero_extra_Solve_calls=True,
                      exact_setpoint_mismatch_count=int((~elements.setpoint_exact_match).sum()),
                      setpoint_max_error_kw_kvar=float(max((elements.P_kw-elements.expected_P_kw).abs().max(), (elements.Q_kvar-elements.expected_Q_kvar).abs().max())))
        write_parquet(output / "OPENDSS_COMPONENT_ELEMENTS.parquet", elements)
        write_parquet(output / "OPENDSS_COMPONENTS_96.parquet", frame)
        frame.to_csv(output / "OPENDSS_COMPONENTS_96.csv", index=False, encoding="utf-8-sig", float_format="%.17g")
    finally:
        backend.apply_trajectory_slot = original
        backend._voltage_vector = original_voltage


def pivot(frame, value, column, order):
    return frame.pivot(index="slot", columns=column, values=value).reindex(index=range(96), columns=order).to_numpy()


def case_arrays(repo, smoke, case, context, binding):
    from dayahead.v36.contracts import PF_TAN
    ids = [f"MESS{i:02d}" for i in range(1, 5)]
    af = pd.read_parquet(smoke / case / "aidc_site_timeseries.parquet")
    actual = {key: pivot(af, column, "site_id", SITES) for key, column in (("IT", "P_IT_kW"), ("pcc", "P_PCC_kW"), ("qcc", "Q_PCC_kvar"), ("GPU", "occupied_GPU"))}
    mf = pd.read_parquet(smoke / case / "MESS_executed_trajectory.parquet")
    actual.update(p=pivot(mf, "P_EXEC", "mess_id", ids), q=pivot(mf, "Q_EXEC", "mess_id", ids), loc=pivot(mf, "actual_service_id", "mess_id", ids))
    da_case = "B0" if case == "B2" else case
    path = repo / f"dayahead/artifacts/v39e_full_may_2025/V39E_DAYAHEAD_DECISION_FREEZE_2025-05-01_{da_case}.json"
    d = read(path)["decision"]
    gpu = pd.DataFrame(d["site_GPU_trajectory"])
    if not np.array_equal(pivot(gpu, "AIDC_GPU_capacity", "AIDC", SITES), np.tile(CAPACITIES, (96, 1))):
        raise RuntimeError("PLANNING_GPU_CAPACITY_AUTHORITY_DRIFT")
    if not np.array_equal(pivot(af, "GPU_capacity", "site_id", SITES), np.tile(CAPACITIES, (96, 1))):
        raise RuntimeError("ACTUAL_GPU_CAPACITY_AUTHORITY_DRIFT")
    da = {"GPU": pivot(gpu, "active_GPU", "AIDC", SITES), "IT": pivot(pd.DataFrame(d["site_IT_power_trajectory"]), "IT_power_kW", "AIDC", SITES),
          "pcc": pivot(pd.DataFrame(d["site_PCC_power_trajectory"]), "PCC_P_kW", "AIDC", SITES),
          "qcc": pivot(pd.DataFrame(d["site_PCC_power_trajectory"]), "PCC_Q_kvar", "AIDC", SITES)}
    commands = pd.DataFrame(read(smoke / case / "MESS_FROZEN_COMMANDS.json"))
    da.update(p=pivot(commands, "p_kw", "mess_id", ids), q=pivot(commands, "q_kvar", "mess_id", ids), loc=pivot(commands, "service_id", "mess_id", ids))
    if case == "B3":
        from dayahead.v40a.feedback import pcc_from_jobs
        payload = read(binding["final_PQ_source"])
        da["pcc"], da["GPU"] = pcc_from_jobs(payload["AIDC_decision"], context)
        da["qcc"] = da["pcc"] * PF_TAN
        da["IT"] = np.array([[float((Decimal(int(cap)) * Decimal("104.1606964512843") + Decimal(int(n)) * Decimal("547.7239090195797")) / 1000) for cap, n in zip(CAPACITIES, row)] for row in da["GPU"]])
    for v in (da, actual):
        v["loc"] = v["loc"].astype(object)
        v["loc"][pd.isna(v["loc"])] = "TRANSIT_UNAVAILABLE"
        v["loc"] = v["loc"].astype(str)
        v["ids"] = tuple(ids)
    return da, actual


def run(repo):
    from dayahead.v40a.context import load_planning_context
    from dayahead.v28r2.electrical_context import portable_background_paths, source_root, with_realized_background
    from dayahead.v28r2.opendss_mapping import FeederAssets
    from dayahead.v28r2.opendss_backend import run_fresh_opendss
    from dayahead.v28r2.trajectory import FrozenTrajectory
    from dayahead.v28r2.source_cache import day_root
    from dayahead.v36.contracts import SOURCE_DATA_REPOSITORY, PF_TAN
    from dayahead.v40d_actual.exogenous import load as load_exogenous
    from dayahead.v40d_actual.preflight import verify_protected
    import gurobipy as gp
    repo = Path(repo); day = "2025-05-01"
    root = repo / "dayahead/artifacts/v40d_actual_realized_replay"
    smoke = root / "smoke" / day
    output = root / "power_scale_parity" / day
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "AUDIT_STATUS.json", {"status": "RUNNING", "scientific_performance_interpretation_authorized": False, "full_campaign_authorized": False})
    original_files = {str(p): sha(p) for p in smoke.rglob("*") if p.is_file()}
    protected = verify_protected(repo, root)
    if protected["status"] != "PASS":
        raise RuntimeError("PROTECTED_INPUT_DRIFT")
    original = gp.Model.optimize; calls = 0; context = None
    def forbidden(*args, **kwargs):
        nonlocal calls
        calls += 1
        raise RuntimeError("SCALE_AUDIT_OPTIMIZATION_FORBIDDEN")
    gp.Model.optimize = forbidden
    try:
        print("Power scale audit: binding frozen May-01 contexts", flush=True)
        context = load_planning_context(repo, day)
        context.repo = repo
        forecast = context.electrical.legacy_context[1]
        weather_path = day_root(SOURCE_DATA_REPOSITORY, day) / "gfs_d1_weather.parquet"
        forecast_weather = pd.read_parquet(weather_path)
        actual_exo = load_exogenous(repo, day)
        with np.load(smoke / "actual_exogenous.npz") as saved:
            if not all(np.array_equal(saved[k], actual_exo[k]) for k in ("demand_mw", "pv_mw")):
                raise RuntimeError("ACTUAL_EXOGENOUS_NOT_SAVED_SMOKE")
            if not np.array_equal(saved["t_wb_c"], actual_exo["weather"].t_wb_c) or not np.array_equal(saved["rh_pct"], actual_exo["weather"].rh_pct):
                raise RuntimeError("ACTUAL_WEATHER_NOT_SAVED_SMOKE")
        paths = portable_background_paths(SOURCE_DATA_REPOSITORY, source_root(SOURCE_DATA_REPOSITORY))
        source_refs = {k: reference(v) for k, v in vars(paths).items()}
        assets = FeederAssets.from_repo(SOURCE_DATA_REPOSITORY)
        asset_refs = {k: reference(v) for k, v in vars(assets).items()}
        da_ind = independent_background(paths, forecast["timestamps_96"], np.array(forecast["demand_mw_96"]), np.array(forecast["pv_mw_96"]), output / "Planning")
        act_ind = independent_background(paths, actual_exo["timestamps"], actual_exo["demand_mw"], actual_exo["pv_mw"], output / "Actual")
        bg_error = {"Planning": binding_errors(context.electrical.legacy_context[2], da_ind)}
        bindings = {b["case"]: b for b in read(root / "V40D_ACTUAL_DECISION_BINDING_AUDIT.json")["cases"] if b["day"] == day}
        bundles = {case: case_arrays(repo, smoke, case, context, bindings[case]) for case in ("B0", "B1", "B2", "B3")}
        legacy = list(context.electrical.legacy_context); legacy[0] = {} if legacy[0] is None else legacy[0]
        base = SimpleNamespace(legacy_context=tuple(legacy), source_root=source_root(SOURCE_DATA_REPOSITORY), voltage=context.electrical.voltage, current=context.electrical.current,
                               voltage_path=context.electrical.voltage_path, current_path=Path(context.electrical.voltage_path).with_name(f"D1_AC_ANCHOR_CURRENT_SENSITIVITY_{day}.npz"))
        act_context = with_realized_background(SOURCE_DATA_REPOSITORY, base, timestamps_96=actual_exo["timestamps"], demand_mw_96=actual_exo["demand_mw"], pv_mw_96=actual_exo["pv_mw"], aidc_plan_kw_96x12=bundles["B0"][1]["pcc"])
        bg_error["Actual"] = binding_errors(act_context.legacy_context[2], act_ind)
        write_json(output / "BACKGROUND_SYNTHESIS_AUDIT.json", {"errors": bg_error,
                   "Planning": context.electrical.legacy_context[2].evidence,
                   "Actual": act_context.legacy_context[2].evidence})
        print({"independent_synthesis_errors": bg_error}, flush=True)
        c1path = repo / "dayahead/artifacts/v24t_thermal_aware_aidc/V24T_C1_QUASISTATIC_MODEL.json"
        c1 = read(c1path)
        cases, inventories, captured = [], {}, {}
        mappings, power_rows = [], []
        comparison = {r["case"]: r for r in read(smoke / "V40D_ACTUAL_SMOKE_COMPARISON.json")["cases"]}
        for case in ("B0", "B1", "B2", "B3"):
            da, actual = bundles[case]
            for namespace, inputs, electrical, weather, ind in (("Fresh", da, context.electrical, forecast_weather, da_ind), ("Actual", actual, act_context, actual_exo["weather"], act_ind)):
                target = output / namespace / case
                print("Power scale audit: OpenDSS readback " + namespace + " " + case, flush=True)
                it_check = np.array([[float((Decimal(int(cap)) * Decimal("104.1606964512843") + Decimal(int(n)) * Decimal("547.7239090195797")) / 1000) for cap, n in zip(CAPACITIES, row)] for row in inputs["GPU"]])
                expected_pcc = independent_c1(it_check, weather, c1)
                it_error = float(np.max(np.abs(inputs["IT"] - it_check)))
                c1_error = float(np.max(np.abs(inputs["pcc"] - expected_pcc)))
                q_error = float(np.max(np.abs(inputs["qcc"] - expected_pcc * PF_TAN)))
                # V39E JSON serialization records 10 decimal places; it is a source precision bound.
                power_tolerance = 1e-10 if namespace == "Fresh" and case != "B3" else 2e-12
                if max(it_error, c1_error, q_error) > power_tolerance:
                    raise RuntimeError("AIDC_SCALE_OR_C1_COUNT:" + namespace + case + str((it_error, c1_error, q_error)))
                if np.max(np.abs(inputs["p"])) > 550 + 1e-8 or np.max(np.hypot(inputs["p"], inputs["q"])) > 700 + 1e-8:
                    raise RuntimeError("MESS_UNIT_OR_RATING")
                trajectory = FrozenTrajectory(day, "DAYAHEAD" if namespace == "Fresh" else "ACTUAL", case, inputs["pcc"], inputs["qcc"], inputs["p"], inputs["q"], inputs["ids"], inputs["loc"], digest({"audit": "POWER_SCALE_PARITY", "namespace": namespace, "case": case}))
                with observe_components(namespace, case, target) as observation:
                    result = run_fresh_opendss(repo=SOURCE_DATA_REPOSITORY, context=electrical, voltage=context.electrical.voltage, trajectory=trajectory, output=target / "grid")
                inventory = observation["inventory"]
                inventories[namespace, case] = inventory
                captured[namespace, case] = observation["frame"]
                component_frame = observation["frame"]
                background_sum_error = float(np.max(np.abs(component_frame.background_P_kw - ind["frame"].sum_bus_phase_background_kw)))
                pv_sum_error = float(np.max(np.abs(component_frame.PV_P_kw - ind["frame"].sum_phase_pv_kw)))
                # Preserve a discovered mapping defect and finish the requested audit.
                # This does not authorize the science result or any full campaign.
                original_path = Path(comparison[case]["Actual_source" if namespace == "Actual" else "Fresh_source"]["path"])
                if namespace == "Actual" or case != "B3":
                    original_arrays = original_path.parent / "OPENDSS_PHASE_ARRAYS.npz"
                else:
                    expected_schedule = read(original_path)["Fresh_schedule_sha256"]
                    matches = [p.parent / "OPENDSS_PHASE_ARRAYS.npz" for p in (repo / "dayahead/artifacts/v40b_v40a_may_launch/days/2025-05-01/B3/postfreeze").rglob("OPENDSS_SUMMARY.json") if read(p)["schedule_sha256"] == expected_schedule]
                    if len(matches) != 1:
                        raise RuntimeError("FRESH_ACCEPTED_TRAJECTORY_SOURCE_AMBIGUOUS")
                    original_arrays = matches[0]
                repeat_errors, repeat_exact = {}, {}
                with np.load(original_arrays) as z:
                    for name in ("voltage_pu", "phase_current_a", "phase_current_loading_pu", "losses_kw_kvar", "regulator_taps", "capacitor_states", "convergence"):
                        current = getattr(result, name)
                        repeat_exact[name] = np.array_equal(z[name], current)
                        repeat_errors[name] = 0. if z[name].dtype.kind == "b" else float(np.nanmax(np.abs(z[name] - current)))
                if namespace == "Actual" and not all(repeat_exact.values()):
                    raise RuntimeError("ACTUAL_COMPONENT_OBSERVER_CHANGED_RESULT")
                if namespace == "Fresh" and max(repeat_errors.values()) > 1e-7:
                    raise RuntimeError("FRESH_FROZEN_RECONSTRUCTION_DRIFT:" + str(repeat_errors))
                case_record = {"namespace": namespace, "case": case, "alpha_grid": electrical.legacy_context[2].evidence["alpha_grid"],
                               "alpha_grid_application_count": electrical.legacy_context[2].evidence["alpha_grid_application_count"],
                               "background_total_max_kw": float(component_frame.background_P_kw.max()), "PV_max_kw": float(component_frame.PV_P_kw.max()),
                               "AIDC_max_aggregate_IT_kw": float(inputs["IT"].sum(axis=1).max()),
                               "IT_formula_error_kw": it_error, "C1_exactly_once_error_kw": c1_error, "Q_mapping_error_kvar": q_error,
                               "AIDC_source_precision_tolerance_kw": power_tolerance,
                               "background_independent_sum_error_kw": background_sum_error, "PV_independent_sum_error_kw": pv_sum_error,
                               "background_component_construction_PASS": background_sum_error <= NUMERICAL_KW_TOLERANCE,
                               "component_setpoint_exact_match": observation["exact_setpoint_match"],
                               "component_exact_setpoint_mismatch_count": observation["exact_setpoint_mismatch_count"],
                               "component_setpoint_max_error_kw_kvar": observation["setpoint_max_error_kw_kvar"],
                               "saved_result_repeat_exact": repeat_exact, "saved_result_repeat_max_error": repeat_errors,
                               "saved_result_source": reference(original_arrays), "inventory_SHA": digest(inventory)}
                cases.append(case_record)
                elements = {r["name"]: r for r in inventory["elements"]}
                for i, site in enumerate(SITES):
                    element = elements["load.idc_idc" + f"{i + 1:02d}"]
                    expected_bus = f"idc_idc{i + 1:02d}_pcc"
                    key = f"aidc_load_kw[{site}]"
                    planning_nodes = [(bus, phase) for (bus, phase), weights in context.electrical.legacy_context[3].factories[0].data.master_p_injection.items() if key in weights]
                    if sorted(planning_nodes) != [(expected_bus, p) for p in "ABC"] or any(str(b).split(".")[0].lower() != expected_bus for b in element["buses"]) or element["phases"] != 3 or element["node_order"][:3] != [1, 2, 3]:
                        raise RuntimeError("AIDC_SPATIAL_BINDING_HARD_FAIL")
                    mappings.append({"namespace": namespace, "case": case, "AIDC_site_id": site, "PCC_bus": expected_bus,
                                     "phase_connection": "A,B,C", "load_object_name": element["name"], "OpenDSS_bus_name": ";".join(element["buses"]),
                                     "site_ordering_index": i, "mapping_source_SHA": asset_refs["pcc"]["sha256"], "service_mapping_source_SHA": asset_refs["service_mapping"]["sha256"]})
                    for t in range(96):
                        power_rows.append({"namespace": namespace, "case": case, "site": site, "slot": t, "P_IT_kw": float(inputs["IT"][t, i]),
                                           "P_PCC_kw": float(inputs["pcc"][t, i]), "Q_PCC_kvar": float(inputs["qcc"][t, i]), "load_object_name": element["name"]})
            # Planning is the coefficient model consuming the same accepted DA inputs as Fresh.
            for row in [r for r in mappings if r["namespace"] == "Fresh" and r["case"] == case]:
                mappings.append({**row, "namespace": "Planning"})
        all_inventory_equal = len({digest(v) for v in inventories.values()}) == 1
        if not all_inventory_equal or da_ind["mapping"] != act_ind["mapping"]:
            raise RuntimeError("NAMESPACE_MAPPING_OR_RATING_DRIFT")
        mapframe = pd.DataFrame(mappings)
        write_parquet(output / "AIDC_SPATIAL_BINDING.parquet", mapframe)
        mapframe.to_csv(output / "AIDC_SPATIAL_BINDING.csv", index=False, encoding="utf-8-sig")
        pframe = pd.DataFrame(power_rows)
        for namespace in ("Fresh", "Actual"):
            for case in ("B0", "B1", "B2", "B3"):
                elements = pd.read_parquet(output / namespace / case / "OPENDSS_COMPONENT_ELEMENTS.parquet")
                e = elements[elements.component.eq("AIDC")][["slot", "element", "P_kw", "Q_kvar"]]
                pf = pframe[pframe.namespace.eq(namespace) & pframe.case.eq(case)].merge(e, left_on=["slot", "load_object_name"], right_on=["slot", "element"], validate="one_to_one")
                if len(pf) != 1152 or not np.array_equal(pf.P_PCC_kw, pf.P_kw) or not np.array_equal(pf.Q_PCC_kvar, pf.Q_kvar):
                    raise RuntimeError("AIDC_SITE_PCC_READBACK_MISMATCH")
                write_parquet(output / namespace / case / "AIDC_SITE_PQ_READBACK_96.parquet", pf)
        # Compare all physical input objects, not only their aggregate totals.
        pair_audits = []
        for left, right in (("B0", "B1"), ("B2", "B3")):
            tables = [pd.read_parquet(output / "Actual" / c / "OPENDSS_COMPONENT_ELEMENTS.parquet").set_index(["slot", "element"]).sort_index() for c in (left, right)]
            a, b = tables
            if not a.index.equals(b.index):
                raise RuntimeError("CASE_ENGINE_OBJECT_AXIS")
            delta = pd.DataFrame({"component": a.component, "Delta_P_kw": b.P_kw - a.P_kw, "Delta_Q_kvar": b.Q_kvar - a.Q_kvar})
            allowed = ["AIDC"] if left == "B0" else ["AIDC", "MESS"]
            outside = delta[~delta.component.isin(allowed)]
            outside_nonzero = int(((outside.Delta_P_kw != 0) | (outside.Delta_Q_kvar != 0)).sum())
            if outside_nonzero:
                raise RuntimeError("CASE_SPECIFIC_EXOGENOUS_INPUT")
            for c in (left, right):
                f = pd.read_parquet(smoke / c / "aidc_site_timeseries.parquet")
                if not np.array_equal(f.observed_t_wb_c.to_numpy().reshape(96, 12)[:, 0], actual_exo["weather"].t_wb_c) or not np.array_equal(f.observed_rh_pct.to_numpy().reshape(96, 12)[:, 0], actual_exo["weather"].rh_pct):
                    raise RuntimeError("CASE_WEATHER_DIFFERENCE")
            with np.load(smoke / left / "actual_grid/OPENDSS_PHASE_ARRAYS.npz") as za, np.load(smoke / right / "actual_grid/OPENDSS_PHASE_ARRAYS.npz") as zb:
                native_equal = all(np.array_equal(za[k], zb[k]) for k in ("regulator_taps", "capacitor_states"))
            if not native_equal:
                raise RuntimeError("NATIVE_REGULATOR_CAPACITOR_STATE_DIFFERENCE")
            write_parquet(output / (left + "_" + right + "_ALL_OPENDSS_INPUT_DIFFERENCES.parquet"), delta.reset_index())
            pair_audits.append({"pair": left + "_" + right, "background_PQ_exact_equal": True, "PV_exact_equal": True,
                                "weather_exact_equal": True, "mapping_ratings_source_exact_equal": True, "regulator_capacitor_all96_exact_equal": native_equal,
                                "permitted_differences": allowed, "nonzero_input_differences_outside_permitted_components": outside_nonzero})
        pa = pframe[pframe.namespace.eq("Actual") & pframe.case.eq("B0")].set_index(["slot", "site"])
        pb = pframe[pframe.namespace.eq("Actual") & pframe.case.eq("B1")].set_index(["slot", "site"])
        write_parquet(output / "B0_B1_AIDC_SITE_DELTA_PQ.parquet", pd.DataFrame({"Delta_P_IT_kw": pb.P_IT_kw - pa.P_IT_kw, "Delta_P_AIDC_kw": pb.P_PCC_kw - pa.P_PCC_kw, "Delta_Q_AIDC_kvar": pb.Q_PCC_kvar - pa.Q_PCC_kvar}).reset_index())
        background_pass = max(c["background_independent_sum_error_kw"] for c in cases) <= NUMERICAL_KW_TOLERANCE
        result = {"POWER_SCALE_PARITY": "FAIL", "FROZEN_FRESH_ACTUAL_SCALE_PATH_IDENTITY": "PASS",
                  "BACKGROUND_SCALE_PARITY": "PASS" if background_pass else "FAIL", "PV_SCALE_PARITY": "FAIL", "FROZEN_PV_NAMESPACE_PARITY": "PASS",
                  "AIDC_SCALE_PARITY": "PASS", "MESS_SCALE_PARITY": "PASS", "PV_DOUBLE_COUNTING": "NO",
                  "failure_reason": "OpenDSS gross background readback does not conserve the independent bus-phase synthesis. Shared bus/phase load mapping duplicates background at buses 65 and 76. Further strict gates: applied PV unit-profile availability is 522.202927266866 kW from nominal 698.000002861023 times alpha; native generator setpoints have recorded non-bit-exact roundtrips. No result is approved for scientific performance interpretation.",
                  "PV_698_gate_interpretation": "Strict applied feeder boundary interpretation. If 698 denotes the pre-alpha nominal allocation, that nominal authority is identical in all three paths; no nominal-capacity mismatch exists. This ambiguity is not resolved by changing frozen science.",
                  "alpha_grid": {n: {"actual_value": ALPHA, "source": reference(repo / "dayahead/grid_background_v16_2.py"), "contract": reference(paths.scale_contract), "function": "build_authority_background_binding"} for n in ("Planning", "Fresh", "Actual")},
                  "PV_engineering_nominal_pre_alpha_kW": da_ind["capacity_sum"], "PV_available_at_unit_profile_after_alpha_kW": ALPHA * da_ind["capacity_sum"],
                  "requested_applied_PV_peak_kW": 698.,
                  "regional_gross_formula": "operational_MW + rooftop_PV_MW",
                  "frozen_feeder_gross_formula": "alpha_grid * (operational_MW * 3490/7100.2615 + rooftop_PV_MW/4021.226 * 698.000002861023)",
                  "ACTUAL_ROOFTOP_PV_DOUBLE_SUBTRACTION": "NO", "ACTUAL_GROSS_BACKGROUND_CONSTRUCTION": "PASS" if background_pass else "FAIL", "ACTUAL_BACKGROUND_ALPHA_GRID_COUNT": 1,
                  "REGIONAL_TO_BUS_PHASE_GROSS_SYNTHESIS": "PASS", "BUS_PHASE_TO_OPENDSS_LOAD_CONSERVATION": "PASS" if background_pass else "FAIL",
                  "AIDC": {"capacities": CAPACITIES.tolist(), "capacity_sum": 624, "CENTER_W_per_GPU": "547.7239090195797", "p_idle_eq_W_per_GPU": "104.1606964512843", "aggregate_active_anchor_kW": "406.775993813819", "C1_application_count": 1, "extra_1_30_PUE_count": 0, "V22SR1_202_750769230769_MW_operating_power_path_count": 0, "C1_source": reference(c1path)},
                  "MESS": {"P_unit": "kW", "P_rating": 550., "Q_unit": "kvar", "S_rating_kVA": 700., "battery_capacity_kWh": 1200., "E_initial_kWh": 760., "energy_bounds_kWh": [440., 1080.], "source": reference(repo / "dayahead/mess_physics.py")},
                  "component_sign_convention": "Stored MESS_P_kw is net consumption (charging - discharge), MESS_Q_kvar=-Q_EXEC. Thus P_net=background-PV+AIDC+MESS. Raw P_EXEC remains discharge-positive. Net here is setpoint conservation, not source terminal power including losses/capacitors/voltage-dependent load behavior.",
                  "independent_background_max_errors": bg_error, "cases": cases, "same_exogenous_pair_audits": pair_audits,
                  "all_namespace_engine_mapping_ratings_source_equal": all_inventory_equal,
                  "background_source_refs": source_refs, "feeder_asset_refs": asset_refs,
                  "forecast_source": reference(day_root(SOURCE_DATA_REPOSITORY, day) / "aemo_forecast.json"), "forecast_weather_source": reference(weather_path), "actual_sources": actual_exo["authority"],
                  "Planning_semantics": "Planning is the frozen coefficient model, not an OpenDSS namespace; its input scale and map are independently checked and compared to a readback replay of its accepted DA trajectory in Fresh.",
                  "historical_readback_semantics": "New audit replays observe component setpoints. Original historical Fresh component logs were not retroactively fabricated; numerical repeat errors are reported for every original physical array.",
                  "optimizer_calls": calls, "full_campaign_authorized": False, "scientific_performance_interpretation_authorized": False}
        if max(v for errors in bg_error.values() for v in errors.values()) > NUMERICAL_KW_TOLERANCE:
            raise RuntimeError("BACKGROUND_INDEPENDENT_RECALCULATION")
        if any(c["alpha_grid"] != ALPHA or c["alpha_grid_application_count"] != 1 for c in cases):
            raise RuntimeError("ALPHA_GRID_MISSING_OR_DOUBLE_APPLIED")
        result["protected_after"] = verify_protected(repo, root)
        result["original_smoke_changed_files"] = [p for p, v in original_files.items() if sha(p) != v]
        if result["protected_after"]["status"] != "PASS" or result["original_smoke_changed_files"]:
            raise RuntimeError("PROTECTED_ARTIFACT_MODIFIED")
        write_json(output / "V40D_POWER_SCALE_PARITY_AUDIT.json", result)
        write_json(root / "V40D_POWER_SCALE_PARITY_AUDIT.json", result)
        write_json(output / "AUDIT_STATUS.json", {"status": "COMPLETE_WITH_IMPLEMENTATION_DEFECT", "POWER_SCALE_PARITY": "FAIL", "BACKGROUND_SCALE_PARITY": result["BACKGROUND_SCALE_PARITY"], "full_campaign_authorized": False, "scientific_performance_interpretation_authorized": False})
        print({"POWER_SCALE_PARITY": result["POWER_SCALE_PARITY"], "BACKGROUND_SCALE_PARITY": result["BACKGROUND_SCALE_PARITY"], "case_readbacks": len(cases), "protected_diff": result["protected_after"]["changed_count"]}, flush=True)
        return result
    finally:
        gp.Model.optimize = original
        if context is not None:
            context.electrical.voltage.close(); context.electrical.current.close()

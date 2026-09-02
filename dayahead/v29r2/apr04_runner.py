"""Frozen V29R2 Apr-04 development checkpoint executor."""

from __future__ import annotations

import csv
import json
import subprocess
import time
from dataclasses import replace
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np
import pandas as pd

from dayahead.aidc_power_response import KAPPA_KW_PER_ACTIVE_H100_NODE
from dayahead.v28r2.actual_replay import build_natural_actual, exact_pcc_from_site_it, replay_actual_case
from dayahead.v28r2.backend_contract import canonical_sha256
from dayahead.v28r2.c1_affine import endpoint_secant, load_c1
from dayahead.v28r2.electrical_cache_prepare import prepare_electrical_context
from dayahead.v28r2.electrical_context import build_electrical_context, with_realized_background
from dayahead.v28r2.formulation import DT_HOURS, _mess_authority
from dayahead.v28r2.opendss_backend import run_fresh_opendss
from dayahead.v28r2.reference_compute import case_rack_capacity_nodeh_per_slot
from dayahead.v28r2.reference_delta import build_reference_delta
from dayahead.v28r2.schedule_freeze import _schedule
from dayahead.v28r2.solver_payload import payload_from_registry
from dayahead.v28r2.solver_runner import add_grid_rows
from dayahead.v28r2.source_cache import day_root
from dayahead.v28r2.trajectory import FrozenTrajectory
from dayahead.v28r2.variable_registry import build_resource_model, value
from dayahead.v28r2.workload_replay import materialize_actual_workload
from dayahead.v29.mess_availability import normalize_mess_record
from dayahead.v29.reference_compute_v3 import build_reference_schedule_v3
from dayahead.v29r1.authority import Q_SCENARIOS
from dayahead.v29r1.source_resume import write_csv, write_json
from tools.v29.run_stage3_carryin_authority import cohort, cohort_bins, read_candidate_events, source_zip

from .anchor_forensic import OUT_REL, _critical
from .bridge_v2 import predict_bridge_day
from .formulation import V29R2FormulationData, formulation_fingerprint, materialize_formulation_data_v29r2
from .mess_noregret import EPSILON_AC_NR, EPSILON_NR, RUNG_ORDER, select_first_safe_rung, solve_b3_rung
from .reference_v4 import ReferenceScheduleV4
from .service_model import build_job_day_instances


DAY = "2025-04-04"
CAMPAIGN_REPO = Path(r"C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\MobileESS_v28r2_heavy_backend")
CAMPAIGN = "v28r2_april_full_month_preflight"


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


def require_dev_freeze(repo: Path) -> dict[str, object]:
    path = repo / OUT_REL / "V29R2_DEV_FREEZE.json"
    if not path.is_file():
        raise RuntimeError("V29R2_APR04_WITHOUT_DEV_FREEZE")
    freeze = json.loads(path.read_text(encoding="utf-8"))
    frozen = str(freeze["V29R2_DEV_FREEZE_HEAD"])
    if subprocess.run(["git", "-C", str(repo), "merge-base", "--is-ancestor", frozen, "HEAD"], check=False).returncode:
        raise RuntimeError("V29R2_APR04_FREEZE_HEAD_NOT_ANCESTOR")
    changed_science = _git(repo, "diff", "--name-only", frozen, "--", "dayahead/v29r2", "dayahead/v28r2/variable_registry.py")
    if changed_science:
        raise RuntimeError(f"V29R2_APR04_POSTFREEZE_SCIENCE_CHANGE:{changed_science}")
    if _git(repo, "status", "--short"):
        raise RuntimeError("V29R2_APR04_DIRTY_START")
    return freeze


def solve_case(data: object, context: object, voltage: object, current: object, case: str) -> object:
    from gurobipy import GRB
    started = time.perf_counter()
    registry = build_resource_model(data, voltage, case, rho_aidc=1.0, rho_mess=.10)
    add_grid_rows(registry, context, voltage, current)
    registry.model.optimize()
    if registry.model.Status != GRB.OPTIMAL:
        raise RuntimeError(f"V29R2_APR04_SOLVER_STATUS:{case}:{int(registry.model.Status)}")
    objective = float(value(registry.eta))
    return payload_from_registry(
        registry, solver="MONOLITHIC", status="OPTIMAL", hard_feasible=True,
        objective=objective, lower_bound=objective, upper_bound=objective, gap=0.0,
        iterations=int(registry.model.IterCount), optimality_cuts=0, feasibility_cuts=0,
        termination_reason="V29R2_GUROBI_OPTIMAL", runtime_seconds=time.perf_counter() - started,
    )


def _trajectory(data: object, payload: object, namespace: str, case: str | None = None) -> FrozenTrajectory:
    records = tuple(sorted(data.mess_records.items()))
    locations = np.asarray([list(map(str, record[1]["location_96"])) for record in records], dtype=str).T
    result = FrozenTrajectory(
        data.day, namespace, case or payload.case,
        np.asarray(payload.planning_pcc_power_kw, dtype=float),
        np.asarray(payload.planning_pcc_reactive_kvar, dtype=float),
        np.asarray(payload.mess_p_kw, dtype=float), np.asarray(payload.mess_q_kvar, dtype=float),
        tuple(record[0] for record in records), locations, payload.schedule_sha256,
    )
    result.validate()
    return result


def _fresh_row(result: object, namespace: str, scenario: str) -> dict[str, object]:
    summary = {key: value for key, value in result.summary.items() if key != "opendss_version"}
    return {"namespace": namespace, "scenario": scenario, **summary, **_critical(result)}


def _fallback_b3(b2: object) -> object:
    return replace(
        b2, case="B3", termination_reason="V29R2_B2_FALLBACK_BYTE_EQUIVALENT_ARRAYS",
        runtime_seconds=0.0,
    )


def _freeze_schedules(out: Path, payloads: Mapping[str, object], reference_bytes: bytes) -> tuple[dict[str, object], dict[str, dict[str, object]]]:
    import hashlib
    schedules: dict[str, dict[str, object]] = {}
    reference_sha = hashlib.sha256(reference_bytes).hexdigest()
    for case in ("B0", "B1", "B2", "B3"):
        schedules[case] = _schedule(payloads[case], reference_sha)
        write_json(out / f"V29R2_APR04_DAYAHEAD_{case}_SCHEDULE.json", schedules[case])
    b0 = canonical_sha256(schedules["B0"]["workload_service_tensor"])
    b2 = canonical_sha256(schedules["B2"]["workload_service_tensor"])
    if b0 != b2:
        raise RuntimeError("V29R2_APR04_B0_B2_REFERENCE_WORKLOAD_MISMATCH")
    manifest = {
        "artifact_id": "V29R2_APR04_DAYAHEAD_SCHEDULE_MANIFEST_V1", "status": "FROZEN",
        "reference_schedule_sha256": reference_sha,
        "B0_B2_reference_schedule_bytes_identical": True,
        "B0_B2_workload_service_sha256": b0,
        "cases": {case: {"schedule_sha256": schedules[case]["schedule_sha256"], "solver": schedules[case]["solver"]} for case in schedules},
        "actual_namespace_open_before_freeze": 0, "future_actual_reads_before_freeze": 0,
    }
    write_json(out / "V29R2_APR04_DAYAHEAD_SCHEDULE_MANIFEST.json", manifest)
    return manifest, schedules


def _actual_carryin(repo: Path, cohort_ids: Sequence[str]) -> tuple[np.ndarray, list[dict[str, object]]]:
    events, _members, _schemas = read_candidate_events(source_zip())
    instances = build_job_day_instances(events, (DAY,))
    bins = cohort_bins(repo)
    instances["cohort_id"] = [cohort(int(n), float(h), bins) for n, h in zip(instances["nodes"], instances["request_hours"], strict=True)]
    values = np.zeros(len(cohort_ids)); index = {name: i for i, name in enumerate(cohort_ids)}
    rows = []
    for cohort_id, selected in instances.groupby("cohort_id", sort=True):
        values[index[cohort_id]] = float(selected["H_REALIZED"].sum())
        rows.append({
            "day": DAY, "cohort_id": cohort_id,
            "H_REQ": float(selected["H_REQ"].sum()),
            "H_NOM": None, "H_LOW": None,
            "H_REALIZED": float(selected["H_REALIZED"].sum()),
            "pre_D0_REALIZED": float(selected["H_PRE_D0_REALIZED"].sum()),
            "job_count": len(selected),
        })
    return values, rows


def _actual_context(repo: Path, base: object, trajectory: FrozenTrajectory) -> object:
    actual = pd.read_parquet(day_root(repo, DAY) / "aemo_actual.parquet")
    return with_realized_background(
        repo, base, timestamps_96=actual["ts_fixed_aest_end"],
        demand_mw_96=actual["demand_mw"], pv_mw_96=actual["rooftop_pv_mw"],
        aidc_plan_kw_96x12=trajectory.pcc_p_kw,
    )


def _pi_data(repo: Path, actual: object, initial: np.ndarray) -> V29R2FormulationData:
    mapping = json.loads((repo / "dayahead/artifacts/v16/AIDC_RACK_MAPPING_CONTRACT.json").read_text(encoding="utf-8"))
    racks = tuple(mapping["racks"]); rack_ids = tuple(str(row["rack_id"]) for row in racks)
    rack_aidc = tuple(str(row["aidc_id"]) for row in racks); aidc_ids = tuple(dict.fromkeys(rack_aidc))
    power_weights = np.asarray(mapping["power_weights"], dtype=float); gpu_weights = np.asarray(mapping["gpu_weights"], dtype=float)
    capacity = case_rack_capacity_nodeh_per_slot(rack_ids, dict(zip(rack_ids, map(float, gpu_weights), strict=True)))
    schedule = build_reference_schedule_v3(
        actual.arrivals_nodeh, initial, cohort_ids=actual.cohort_ids, rack_ids=rack_ids,
        rack_capacity_nodeh_per_slot=capacity,
        rack_power_envelope_kw=power_weights[:, None] * actual.total_it_kw[None, :],
        rack_gpu_envelope_gpu=gpu_weights[:, None] * actual.total_h100_gpu[None, :],
    )
    reference = ReferenceScheduleV4(schedule, initial.copy(), initial.copy(), initial.copy(), np.zeros_like(initial))
    delta = build_reference_delta(
        actual.total_it_kw, actual.total_h100_gpu, schedule.p_f_ref_kw, schedule.g_f_ref_gpu,
        rack_ids=rack_ids, power_weights=dict(zip(rack_ids, map(float, power_weights), strict=True)),
        gpu_weights=dict(zip(rack_ids, map(float, gpu_weights), strict=True)),
    )
    weather = pd.read_parquet(day_root(repo, DAY) / "noaa_actual_weather.parquet")
    parameters = load_c1(repo / "dayahead/artifacts/v24t_thermal_aware_aidc/V24T_C1_QUASISTATIC_MODEL.json")
    rack_index = {rack: index for index, rack in enumerate(rack_ids)}; max_kappa = max(KAPPA_KW_PER_ACTIVE_H100_NODE.values())
    coefficients = []
    for aidc in aidc_ids:
        indices = [rack_index[rack] for rack, owner in zip(rack_ids, rack_aidc, strict=True) if owner == aidc]
        for slot in range(96):
            p_min = float(delta.p_res_plan_kw[indices, slot].sum())
            p_max = p_min + float(capacity[indices].sum() / DT_HOURS * max_kappa)
            coefficients.append(endpoint_secant(aidc, slot, p_min, p_max, float(weather.iloc[slot]["t_wb_c"]), float(weather.iloc[slot]["rh_pct"]), parameters))
    aemo = pd.read_parquet(day_root(repo, DAY) / "aemo_actual.parquet")
    vintage = {"timestamps_96": [str(value) for value in aemo["ts_fixed_aest_end"]], "demand_mw_96": aemo["demand_mw"].astype(float).tolist(), "pv_mw_96": aemo["rooftop_pv_mw"].astype(float).tolist()}
    mobility = json.loads((day_root(repo, DAY) / "traffic_mobility.json").read_text(encoding="utf-8"))
    mobility["mess"] = [normalize_mess_record(record) for record in mobility["mess"]]
    data = V29R2FormulationData(
        DAY, "S_NOM", actual.cohort_ids, rack_ids, rack_aidc, aidc_ids,
        capacity / DT_HOURS * 4.0, initial, initial, actual.arrivals_nodeh,
        reference, delta, actual.total_it_kw, actual.total_h100_gpu,
        tuple(coefficients), vintage, _mess_authority(mobility), formulation_fingerprint(repo),
        canonical_sha256({"namespace": "PI", "day": DAY, "initial": initial.tolist(), "actual_source": actual.source_sha256}),
    )
    data.validate(); return data


def _read_v29_baseline(repo: Path) -> list[dict[str, object]]:
    root = repo / "dayahead/artifacts/v29_grid_responsive_aidc"
    rows = []
    for name, label in (("V29_4DAY_OBJECTIVE_RESULTS.csv", "DA"), ("V29_4DAY_OPENDSS_RESULTS.csv", "OPENDSS")):
        with (root / name).open(encoding="utf-8-sig", newline="") as stream:
            for row in csv.DictReader(stream):
                if row.get("day") == DAY:
                    rows.append({"source": label, **row})
    # ``write_csv`` deliberately freezes its schema from the first record.
    # The objective and OpenDSS baseline ledgers have different columns, so
    # materialize their union before serialization.
    leading = ("source", "day", "case")
    fields = (*leading, *sorted(set().union(*(row.keys() for row in rows)) - set(leading)))
    return [{field: row.get(field, "") for field in fields} for row in rows]


def run_apr04(repo: Path) -> dict[str, object]:
    freeze = require_dev_freeze(repo)
    out = repo / OUT_REL
    bridge_rows = predict_bridge_day(repo, DAY)
    campaign_cache = CAMPAIGN_REPO / "frozen_artifacts" / CAMPAIGN / DAY / "dayahead/electrical_cache"
    scenario_data: dict[str, object] = {}
    scenario_context: dict[str, object] = {}
    b2_payloads: dict[str, object] = {}
    rung_payloads: dict[str, dict[str, object]] = {rung: {} for rung in RUNG_ORDER[:-1]}
    evaluations: dict[str, dict[str, dict[str, object]]] = {rung: {} for rung in RUNG_ORDER[:-1]}
    gate_rows: list[dict[str, object]] = []
    opendss_rows: list[dict[str, object]] = []
    for scenario in Q_SCENARIOS:
        data = materialize_formulation_data_v29r2(repo, DAY, scenario, bridge_rows=bridge_rows)
        context = build_electrical_context(repo, data, campaign_cache)
        scenario_data[scenario] = data; scenario_context[scenario] = context
        b2 = solve_case(data, context.legacy_context, context.voltage, context.current, "B2")
        b2_payloads[scenario] = b2
        b2_result = run_fresh_opendss(repo=repo, context=context, voltage=context.voltage, trajectory=_trajectory(data, b2, "DAYAHEAD", "B2"))
        b2_rho = float(b2_result.summary["rho_max_AC"])
        for rung in RUNG_ORDER[:-1]:
            candidate = solve_b3_rung(data=data, context=context.legacy_context, voltage=context.voltage, current=context.current, b2_payload=b2, rung=rung, rho=1.0)
            rung_payloads[rung][scenario] = candidate
            result = run_fresh_opendss(repo=repo, context=context, voltage=context.voltage, trajectory=_trajectory(data, candidate, "DAYAHEAD", "B3"))
            evaluation = {
                "planning_delta_vs_B2": float(candidate.objective) - float(b2.objective),
                "rho_AC_delta_vs_B2": float(result.summary["rho_max_AC"]) - b2_rho,
                "all_converged": int(result.summary["convergence_count"]) == 96,
            }
            evaluations[rung][scenario] = evaluation
            gate_rows.append({"rung": rung, "scenario": scenario, **evaluation, "B2_rho_AC": b2_rho, "B3_rho_AC": result.summary["rho_max_AC"], "epsilon_NR": EPSILON_NR, "epsilon_AC_NR": EPSILON_AC_NR})
    selected, selection_audit = select_first_safe_rung(evaluations)
    nominal = scenario_data["S_NOM"]; context = scenario_context["S_NOM"]
    b2 = b2_payloads["S_NOM"]
    b3 = _fallback_b3(b2) if selected == "B2_FALLBACK" else rung_payloads[selected]["S_NOM"]
    operational = {
        "B0": solve_case(nominal, context.legacy_context, context.voltage, context.current, "B0"),
        "B1": solve_case(nominal, context.legacy_context, context.voltage, context.current, "B1"),
        "B2": b2, "B3": b3,
    }
    dominance = {
        "B1_le_B0": operational["B1"].objective <= operational["B0"].objective + EPSILON_NR,
        "B2_le_B0": operational["B2"].objective <= operational["B0"].objective + EPSILON_NR,
        "B3_le_B1": operational["B3"].objective <= operational["B1"].objective + EPSILON_NR,
        "B3_le_B2": operational["B3"].objective <= operational["B2"].objective + EPSILON_NR,
    }
    manifest, schedules = _freeze_schedules(out, operational, nominal.reference.canonical_bytes())
    da_rows = []
    for case, payload in operational.items():
        result = run_fresh_opendss(repo=repo, context=context, voltage=context.voltage, trajectory=_trajectory(nominal, payload, "DAYAHEAD", case))
        opendss_rows.append(_fresh_row(result, "DA", "S_NOM"))
        da_rows.append({"day": DAY, "case": case, "planning_objective": payload.objective, "schedule_sha256": schedules[case]["schedule_sha256"], "rho_AIDC": 1.0, "rho_MESS": .10})

    # Actual is opened only after schedules are frozen and verified in memory/on disk.
    actual = materialize_actual_workload(repo, DAY)
    actual_initial, actual_service_rows = _actual_carryin(repo, nominal.cohort_ids)
    mobility = json.loads((day_root(repo, DAY) / "traffic_mobility.json").read_text(encoding="utf-8"))["mess"]
    natural = build_natural_actual(repo, DAY, actual, mobility, canonical_sha256(manifest))
    actual_replays = {"R0": natural}
    for case in ("B0", "B1", "B2", "B3"):
        actual_replays[case] = replay_actual_case(repo, DAY, schedules[case], actual, mobility, initial_backlog_nodeh=actual_initial)
    actual_rows = []
    for case, replay in actual_replays.items():
        act_context = _actual_context(repo, context, replay.trajectory)
        result = run_fresh_opendss(repo=repo, context=act_context, voltage=act_context.voltage, trajectory=replay.trajectory)
        opendss_rows.append(_fresh_row(result, "ACT", "REALIZED"))
        actual_rows.append({"day": DAY, "case": case, **replay.summary, "rho_max_AC": result.summary["rho_max_AC"], "Vmin_pu": result.summary["Vmin_pu"], "Vmax_pu": result.summary["Vmax_pu"]})

    pi_data = _pi_data(repo, actual, actual_initial)
    pi_context = prepare_electrical_context(repo, pi_data, repo / "cache/v29r2_apr04_pi")
    pi_payload = solve_case(pi_data, pi_context.legacy_context, pi_context.voltage, pi_context.current, "B3")
    pcc_p, pcc_q = exact_pcc_from_site_it(repo, DAY, np.asarray(pi_payload.site_it_power_kw, dtype=float))
    pi_trajectory = _trajectory(pi_data, pi_payload, "PERFECT_INFORMATION", "B3")
    pi_trajectory = replace(pi_trajectory, pcc_p_kw=pcc_p, pcc_q_kvar=pcc_q)
    pi_result = run_fresh_opendss(repo=repo, context=pi_context, voltage=pi_context.voltage, trajectory=pi_trajectory)
    opendss_rows.append(_fresh_row(pi_result, "PI", "REALIZED_ORACLE"))
    pi_rows = [{"day": DAY, "case": "B3", "planning_objective": pi_payload.objective, "rho_max_AC": pi_result.summary["rho_max_AC"], "Vmin_pu": pi_result.summary["Vmin_pu"], "Vmax_pu": pi_result.summary["Vmax_pu"], "DA_namespace_reads": 0}]

    forecast_by = {row["cohort_id"]: row for row in bridge_rows}
    for row in actual_service_rows:
        predicted = forecast_by.get(row["cohort_id"], {})
        row["H_NOM"] = predicted.get("H0_NOM", 0.0); row["H_LOW"] = predicted.get("H0_LOW", 0.0)
    p2 = np.asarray(operational["B2"].mess_p_kw); p3 = np.asarray(operational["B3"].mess_p_kw)
    q2 = np.asarray(operational["B2"].mess_q_kvar); q3 = np.asarray(operational["B3"].mess_q_kvar)
    mess_rows = [{
        "day": DAY, "selected_rung": selected,
        "P_B3_minus_B2_max_abs_kw": float(np.max(np.abs(p3 - p2))),
        "P_B3_minus_B2_L1_kw": float(np.sum(np.abs(p3 - p2))),
        "Q_B3_minus_B2_max_abs_kvar": float(np.max(np.abs(q3 - q2))),
        "Q_B3_minus_B2_L1_kvar": float(np.sum(np.abs(q3 - q2))),
        "critical_slot": int(np.unravel_index(np.argmax(np.abs(q3 - q2)), q3.shape)[0]),
    }]
    actual_map = {row["case"]: row for row in actual_rows}
    classification = "V29R2_APR04_DEVELOPMENT_CHECKPOINT_PASS" if (
        all(dominance.values())
        and float(actual_map["B3"]["rho_max_AC"]) <= float(actual_map["B2"]["rho_max_AC"]) + EPSILON_AC_NR
        and all(int(row["convergence_count"]) == 96 for row in opendss_rows)
        and all(float(row.get("hidden_shedding_nodeh", 0.0)) == 0 for row in actual_rows)
        and all(abs(float(row.get("workload_mass_error_nodeh", 0.0))) <= 1e-8 for row in actual_rows)
    ) else "V29R2_APR04_DEV_FAIL_NEW_PROSPECTIVE_LINEAGE_REQUIRED"
    review = {
        "artifact_id": "V29R2_APR04_DEVELOPMENT_REVIEW_V1", "RESULT_CLASSIFICATION": classification,
        "day": DAY, "label": "V29R2_APR04_DEVELOPMENT_CHECKPOINT",
        "independent_validation": False, "final_validation": False,
        "DEV_FREEZE_HEAD": freeze["V29R2_DEV_FREEZE_HEAD"],
        "rho_CERT": 1.0, "selected_no_regret_rung": selected,
        "scenario_selection_audit": selection_audit, "dominance": dominance,
        "actual_optimizer_calls": 0, "PI_optimizer_calls": 1,
        "Fresh_OpenDSS_trajectory_count": len(opendss_rows),
        "Fresh_OpenDSS_sequential_slot_solves": 96 * len(opendss_rows),
        "Actual_B3_minus_B2_rho_AC": float(actual_map["B3"]["rho_max_AC"]) - float(actual_map["B2"]["rho_max_AC"]),
        "full_Apr1_4_regression_justified": classification == "V29R2_APR04_DEVELOPMENT_CHECKPOINT_PASS",
    }
    write_csv(out / "V29R2_MESS_NOREGRET_AC_GATE.csv", gate_rows)
    write_csv(out / "V29R2_MESS_FALLBACK_DECISION.csv", [{"day": DAY, "selected_rung": selected, **row} for row in selection_audit])
    write_csv(out / "V29R2_APR04_DA_RESULTS.csv", da_rows)
    write_csv(out / "V29R2_APR04_ACTUAL_RESULTS.csv", actual_rows)
    write_csv(out / "V29R2_APR04_PI_RESULTS.csv", pi_rows)
    write_csv(out / "V29R2_APR04_OPENDSS_RESULTS.csv", opendss_rows)
    write_csv(out / "V29R2_APR04_SERVICE_RESULTS.csv", actual_service_rows)
    write_csv(out / "V29R2_APR04_MESS_RESULTS.csv", mess_rows)
    write_csv(out / "V29R2_APR04_V29_COMPARISON.csv", _read_v29_baseline(repo))
    write_json(out / "V29R2_APR04_DEVELOPMENT_REVIEW.json", review)
    md = f"""# V29R2 Apr-04 Development Review

Result: **{classification}**

This is development/regression evidence, not independent or final validation. The selected no-regret rung was `{selected}`. Actual B3 minus B2 normalized-current maximum was {review['Actual_B3_minus_B2_rho_AC']:.9g}. Actual optimizer calls were zero. Fresh OpenDSS ran {len(opendss_rows)} trajectories / {96 * len(opendss_rows)} sequential slots.
"""
    (out / "V29R2_APR04_DEVELOPMENT_REVIEW.md").write_text(md, encoding="utf-8", newline="\n")
    for item in scenario_context.values():
        item.voltage.close(); item.current.close()
    pi_context.voltage.close(); pi_context.current.close()
    return review

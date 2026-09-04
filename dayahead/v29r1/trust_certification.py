"""Pre-April physics certification for the frozen V29R1 AIDC rho set."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np
import pandas as pd

from dayahead.aidc_power_response import KAPPA_KW_PER_ACTIVE_H100_NODE
from dayahead.full_ieee123_g11_v16_1 import build_full_grid_binding
from dayahead.grid_background_v16_2 import build_authority_background_binding
from dayahead.run_v16_3_voltage_candidate import _anchor_and_sensitivity_day
from dayahead.v28r2.backend_contract import canonical_sha256
from dayahead.v28r2.c1_affine import endpoint_secant, load_c1
from dayahead.v28r2.c1_certificate import summarize as summarize_c1
from dayahead.v28r2.electrical_context import (
    ElectricalContext,
    portable_background_paths,
    source_root,
)
from dayahead.v28r2.formulation import DT_HOURS, PF_TAN
from dayahead.v28r2.opendss_backend import run_fresh_opendss
from dayahead.v28r2.reference_compute import (
    case_rack_capacity_nodeh_per_slot,
)
from dayahead.v28r2.trajectory import FrozenTrajectory

from .authority import CANDIDATE_RHOS, CERTIFICATION_DAYS
from .source_resume import ARTIFACT_REL, CACHE_REL, sha256_file, write_csv, write_json


VOLTAGE_TOLERANCE = {"max": 0.01, "p95": 0.005, "mean": 0.003}
CURRENT_TOLERANCE = {"max": 0.03, "p95": 0.02, "mean": 0.01}
C1_SITE_RATING_KW = 1425.0
C1_AGGREGATE_RATING_KW = 528.8087919579648
PHYSICAL_TOLERANCE = 1e-8
DIRECTIONAL_PROBE_FRACTION = 0.01


@dataclass(frozen=True)
class TrustDayInputs:
    day: str
    aidc_ids: tuple[str, ...]
    reference_pcc_kw: np.ndarray
    pcc_min_kw: np.ndarray
    pcc_max_kw: np.ndarray
    coefficients: tuple[object, ...]
    vintage: Mapping[str, object]


def _inputs(repo: Path, day: str) -> TrustDayInputs:
    rack_payload = json.loads((repo / "dayahead/artifacts/v16/AIDC_RACK_MAPPING_CONTRACT.json").read_text(encoding="utf-8"))
    racks = tuple(rack_payload["racks"])
    rack_ids = tuple(str(row["rack_id"]) for row in racks)
    rack_aidc = tuple(str(row["aidc_id"]) for row in racks)
    aidc_ids = tuple(dict.fromkeys(rack_aidc))
    gpu_weights = dict(zip(rack_ids, map(float, rack_payload["gpu_weights"]), strict=True))
    capacities = case_rack_capacity_nodeh_per_slot(rack_ids, gpu_weights)
    weather = pd.read_parquet(repo / CACHE_REL / "days" / day / "gfs_d1_weather.parquet")
    parameters = load_c1(repo / "dayahead/artifacts/v24t_thermal_aware_aidc/V24T_C1_QUASISTATIC_MODEL.json")
    rack_index = {rack: index for index, rack in enumerate(rack_ids)}
    max_kappa = max(KAPPA_KW_PER_ACTIVE_H100_NODE.values())
    coefficients = []
    reference_pcc = np.zeros((96, 12), dtype=float)
    pcc_min = np.zeros_like(reference_pcc)
    pcc_max = np.zeros_like(reference_pcc)
    for aidc_index, aidc in enumerate(aidc_ids):
        indices = [rack_index[rack] for rack, owner in zip(rack_ids, rack_aidc, strict=True) if owner == aidc]
        for slot in range(96):
            p_min = 0.0
            p_max = float(capacities[indices].sum() / DT_HOURS * max_kappa)
            coefficient = endpoint_secant(
                aidc, slot, p_min, p_max,
                float(weather.iloc[slot]["t_wb_c"]), float(weather.iloc[slot]["rh_pct"]), parameters,
            )
            coefficients.append(coefficient)
            reference_it = 0.5 * (p_min + p_max)
            reference_pcc[slot, aidc_index] = coefficient.slope * reference_it + coefficient.intercept_kw
            pcc_min[slot, aidc_index] = coefficient.slope * p_min + coefficient.intercept_kw
            pcc_max[slot, aidc_index] = coefficient.slope * p_max + coefficient.intercept_kw
    vintage = json.loads((repo / CACHE_REL / "days" / day / "aemo_forecast.json").read_text(encoding="utf-8"))
    return TrustDayInputs(day, aidc_ids, reference_pcc, pcc_min, pcc_max, tuple(coefficients), vintage)


def _direction(inputs: TrustDayInputs) -> np.ndarray:
    ordinal = (pd.Timestamp(inputs.day) - pd.Timestamp(CERTIFICATION_DAYS[0])).days
    parity = (np.arange(96)[:, None] + np.arange(12)[None, :] + ordinal) % 2 == 0
    return np.where(
        parity,
        inputs.pcc_max_kw - inputs.reference_pcc_kw,
        inputs.pcc_min_kw - inputs.reference_pcc_kw,
    )


def _trajectory(day: str, case: str, pcc: np.ndarray) -> FrozenTrajectory:
    route = np.asarray([[f"STA{index:02d}" for index in range(1, 5)] for _ in range(96)], dtype=str)
    source_sha = canonical_sha256({"day": day, "case": case, "pcc_p_kw": pcc.tolist()})
    result = FrozenTrajectory(
        day=day, namespace="DAYAHEAD", case=case,
        pcc_p_kw=np.asarray(pcc, dtype=float), pcc_q_kvar=np.asarray(pcc, dtype=float) * PF_TAN,
        mess_p_kw=np.zeros((96, 4)), mess_q_kvar=np.zeros((96, 4)),
        mess_ids=("MESS01", "MESS02", "MESS03", "MESS04"),
        mess_locations_96x4=route, source_schedule_sha256=source_sha,
    )
    result.validate()
    return result


def _metrics(predicted: np.ndarray, actual: np.ndarray) -> dict[str, float]:
    error = np.abs(np.asarray(predicted, dtype=float) - np.asarray(actual, dtype=float))
    return {"max": float(error.max()), "p95": float(np.quantile(error, 0.95)), "mean": float(error.mean())}


def _physical_pass(summary: dict[str, object]) -> bool:
    return bool(
        float(summary["rho_max_AC"]) <= 1.0 + PHYSICAL_TOLERANCE
        and float(summary["transformer_phase_current_loading_max"]) <= 1.0 + PHYSICAL_TOLERANCE
        and float(summary["transformer_total_kva_loading_max"]) <= 1.0 + PHYSICAL_TOLERANCE
        and float(summary["Vmin_pu"]) >= 0.95 - PHYSICAL_TOLERANCE
        and float(summary["Vmax_pu"]) <= 1.05 + PHYSICAL_TOLERANCE
    )


def _day_certify(repo: Path, inputs: TrustDayInputs) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    source = source_root(repo)
    background = build_authority_background_binding(
        timestamps_fixed_aest=inputs.vintage["timestamps_96"],
        demand_mw_96=inputs.vintage["demand_mw_96"],
        rooftop_pv_mw_96=inputs.vintage["pv_mw_96"],
        paths=portable_background_paths(repo, source),
    )
    binding = build_full_grid_binding(
        assets=source / "opendss_assets", contract=source / "power_v70_p4f_contract",
        demand_mw_96=inputs.vintage["demand_mw_96"], rooftop_pv_mw_96=inputs.vintage["pv_mw_96"],
        aidc_plan_kw_96x12=inputs.reference_pcc_kw.tolist(),
        pcc_asset=repo / "dayahead/artifacts/v16_2/Generated_ThreePhase_PCC_v4.dss",
        background_binding=background,
    )
    anchor_path = repo / CACHE_REL / "electrical_anchor" / inputs.day / "D1_AC_ANCHOR.npz"
    _anchor_and_sensitivity_day(
        repo, source, background, inputs.reference_pcc_kw.tolist(), binding,
        inputs.day, anchor_path, build_sensitivity=False,
    )
    voltage = np.load(anchor_path, allow_pickle=False)
    reference = {"plan_kw_96x12": tuple(tuple(map(float, row)) for row in inputs.reference_pcc_kw)}
    legacy = (reference, inputs.vintage, background, binding, anchor_path, "V29R1_PREAPRIL_PHYSICS_CERT")
    context = ElectricalContext(legacy, voltage, None, source, anchor_path, anchor_path)
    direction = _direction(inputs)
    anchor = run_fresh_opendss(
        repo=repo, context=context, voltage=voltage,
        trajectory=_trajectory(inputs.day, "TRUST_ANCHOR", inputs.reference_pcc_kw),
    )
    plus = run_fresh_opendss(
        repo=repo, context=context, voltage=voltage,
        trajectory=_trajectory(inputs.day, "TRUST_PROBE_PLUS", inputs.reference_pcc_kw + DIRECTIONAL_PROBE_FRACTION * direction),
    )
    minus = run_fresh_opendss(
        repo=repo, context=context, voltage=voltage,
        trajectory=_trajectory(inputs.day, "TRUST_PROBE_MINUS", inputs.reference_pcc_kw - DIRECTIONAL_PROBE_FRACTION * direction),
    )
    voltage_derivative = (plus.voltage_pu - minus.voltage_pu) / (2.0 * DIRECTIONAL_PROBE_FRACTION)
    current_derivative = (plus.phase_current_loading_pu - minus.phase_current_loading_pu) / (2.0 * DIRECTIONAL_PROBE_FRACTION)
    line_mask = np.asarray([kind == "line" for kind in anchor.branch_kinds])
    anchor_summary = anchor.summary
    anchor_physical_pass = _physical_pass(anchor_summary)
    c1 = summarize_c1(inputs.coefficients, site_rating_kw=C1_SITE_RATING_KW, aggregate_rating_kw=C1_AGGREGATE_RATING_KW)
    opendss_rows: list[dict[str, object]] = []
    c1_rows: list[dict[str, object]] = []
    for rho in CANDIDATE_RHOS:
        candidate_pcc = inputs.reference_pcc_kw + float(rho) * direction
        result = run_fresh_opendss(
            repo=repo, context=context, voltage=voltage,
            trajectory=_trajectory(inputs.day, f"TRUST_RHO_{rho:.2f}", candidate_pcc),
        )
        predicted_voltage = anchor.voltage_pu + float(rho) * voltage_derivative
        predicted_current = anchor.phase_current_loading_pu + float(rho) * current_derivative
        v_error = _metrics(predicted_voltage, result.voltage_pu)
        i_error = _metrics(predicted_current[:, line_mask], result.phase_current_loading_pu[:, line_mask])
        summary = result.summary
        physical_pass = _physical_pass(summary)
        model_pass = all(v_error[key] <= VOLTAGE_TOLERANCE[key] for key in VOLTAGE_TOLERANCE) and all(i_error[key] <= CURRENT_TOLERANCE[key] for key in CURRENT_TOLERANCE)
        opendss_rows.append({
            "day": inputs.day, "rho_AIDC": rho, "status": "PASS" if physical_pass and model_pass else "FAIL",
            "OpenDSS_solve_count": summary["OpenDSS_solve_count"], "convergence_count": summary["convergence_count"],
            "rho_max_AC": summary["rho_max_AC"], "Vmin_pu": summary["Vmin_pu"], "Vmax_pu": summary["Vmax_pu"],
            "transformer_phase_current_loading_max": summary["transformer_phase_current_loading_max"],
            "transformer_total_kva_loading_max": summary["transformer_total_kva_loading_max"],
            "voltage_error_max_pu": v_error["max"], "voltage_error_p95_pu": v_error["p95"], "voltage_error_mean_pu": v_error["mean"],
            "current_error_max_pu": i_error["max"], "current_error_p95_pu": i_error["p95"], "current_error_mean_pu": i_error["mean"],
            "physical_pass": physical_pass, "planning_model_error_pass": model_pass,
            "anchor_physical_pass": anchor_physical_pass,
            "anchor_rho_max_AC": anchor_summary["rho_max_AC"],
            "anchor_Vmin_pu": anchor_summary["Vmin_pu"],
            "anchor_Vmax_pu": anchor_summary["Vmax_pu"],
            "anchor_transformer_phase_current_loading_max": anchor_summary["transformer_phase_current_loading_max"],
            "anchor_transformer_total_kva_loading_max": anchor_summary["transformer_total_kva_loading_max"],
            "candidate_delta_rho_max_AC": float(summary["rho_max_AC"]) - float(anchor_summary["rho_max_AC"]),
            "candidate_delta_Vmin_pu": float(summary["Vmin_pu"]) - float(anchor_summary["Vmin_pu"]),
            "candidate_delta_Vmax_pu": float(summary["Vmax_pu"]) - float(anchor_summary["Vmax_pu"]),
            "preexisting_anchor_violation": not anchor_physical_pass,
            "candidate_new_violation": anchor_physical_pass and not physical_pass,
            "candidate_resolves_anchor_violation": (not anchor_physical_pass) and physical_pass,
            "direction": "FROZEN_SIMULTANEOUS_ALTERNATING_LOW_HIGH_ENDPOINT",
            "April_performance_used": False,
        })
        c1_rows.append({
            "day": inputs.day, "rho_AIDC": rho, "status": c1["status"],
            "coefficient_count": c1["coefficient_count"],
            "minimum_conservatism_kw": c1["minimum_conservatism_kw"],
            "maximum_site_error_kw": c1["maximum_site_error_kw"],
            "maximum_aggregate_error_kw": c1["maximum_aggregate_error_kw"],
            "site_error_threshold_kw": c1["site_error_threshold_kw"],
            "aggregate_error_threshold_kw": c1["aggregate_error_threshold_kw"],
        })
    voltage.close()
    return opendss_rows, c1_rows


def _certify_worker(repo_text: str, day: str) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    repo = Path(repo_text)
    return _day_certify(repo, _inputs(repo, day))


def certify(repo: Path, *, workers: int = 4) -> dict[str, object]:
    opendss_rows: list[dict[str, object]] = []
    c1_rows: list[dict[str, object]] = []
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(_certify_worker, str(repo.resolve()), day): day
            for day in CERTIFICATION_DAYS
        }
        for index, future in enumerate(as_completed(futures), start=1):
            day = futures[future]
            day_open, day_c1 = future.result()
            opendss_rows.extend(day_open)
            c1_rows.extend(day_c1)
            print(json.dumps({"phase": "trust-cert", "day": day, "days_complete": index, "days_total": 90}), flush=True)
    opendss_rows.sort(key=lambda row: (str(row["day"]), float(row["rho_AIDC"])))
    c1_rows.sort(key=lambda row: (str(row["day"]), float(row["rho_AIDC"])))
    out = repo / "dayahead/artifacts/v29r1_reliability_calibrated_noregret"
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / "V29R1_TRUST_CERT_OPENDSS_RESULTS.csv", opendss_rows)
    write_csv(out / "V29R1_TRUST_CERT_C1_RESULTS.csv", c1_rows)
    candidates: list[dict[str, object]] = []
    for rho in CANDIDATE_RHOS:
        ac = [row for row in opendss_rows if float(row["rho_AIDC"]) == rho]
        c1 = [row for row in c1_rows if float(row["rho_AIDC"]) == rho]
        row = {
            "rho_AIDC": rho, "certification_day_count": len({row["day"] for row in ac}),
            "Fresh_OpenDSS_trajectory_count": len(ac),
            "Fresh_OpenDSS_solve_count": sum(int(row["OpenDSS_solve_count"]) for row in ac),
            "AC_all_days_pass": all(row["status"] == "PASS" for row in ac),
            "C1_all_days_pass": all(row["status"] == "PASS" for row in c1),
            "maximum_voltage_error_pu": max(float(row["voltage_error_max_pu"]) for row in ac),
            "maximum_current_error_pu": max(float(row["current_error_max_pu"]) for row in ac),
            "maximum_rho_AC": max(float(row["rho_max_AC"]) for row in ac),
            "preexisting_anchor_violation_day_count": len({row["day"] for row in ac if bool(row["preexisting_anchor_violation"])}),
            "candidate_new_violation_day_count": len({row["day"] for row in ac if bool(row["candidate_new_violation"])}),
            "candidate_resolves_anchor_violation_day_count": len({row["day"] for row in ac if bool(row["candidate_resolves_anchor_violation"])}),
            "April_rows_used": 0,
        }
        row["all_frozen_AC_C1_gates_pass"] = bool(row["AC_all_days_pass"] and row["C1_all_days_pass"] and row["certification_day_count"] == 90)
        row["status"] = "PASS" if row["all_frozen_AC_C1_gates_pass"] else "FAIL"
        candidates.append(row)
    write_csv(out / "V29R1_TRUST_CERT_CANDIDATES.csv", candidates)
    passing = [float(row["rho_AIDC"]) for row in candidates if row["status"] == "PASS"]
    selected = max(passing) if passing else None
    anchor_fail_days = sorted({
        str(row["day"]) for row in opendss_rows if bool(row["preexisting_anchor_violation"])
    })
    candidate_new_fail_days = sorted({
        str(row["day"]) for row in opendss_rows if bool(row["candidate_new_violation"])
    })
    decision = {
        "artifact_id": "V29R1_TRUST_CERT_DECISION_V2",
        "status": "PASS" if selected is not None else "V29R1_BLOCKED_TRUST_CERT_PHYSICS_GATES",
        "candidate_set": list(CANDIDATE_RHOS),
        "selection_rule": "largest prospectively frozen candidate passing all Jan-Mar AC/C1 gates",
        "selected_rho_AIDC": selected,
        "certification_population": {"start": CERTIFICATION_DAYS[0], "end": CERTIFICATION_DAYS[-1], "day_count": 90},
        "voltage_tolerance": VOLTAGE_TOLERANCE, "current_tolerance": CURRENT_TOLERANCE,
        "C1_error_threshold_rule": "existing one-percent site and aggregate rating authority",
        "directional_probe_fraction": DIRECTIONAL_PROBE_FRACTION,
        "probe_family": "FROZEN_SIMULTANEOUS_ALTERNATING_LOW_HIGH_ENDPOINT",
        "AIDC_interval_authority": "conservative full frozen rack-capacity/Dataset312-kappa IT interval with zero lower endpoint",
        "April_rows_used": 0, "April_performance_used_for_selection": False,
        "objective_improvement_used_for_selection": False,
        "production_rho_changed_before_freeze": False,
        "Fresh_OpenDSS_execution": {
            "anchor_trajectory_count": 90,
            "directional_probe_trajectory_count": 180,
            "candidate_trajectory_count": len(opendss_rows),
            "total_trajectory_count": 270 + len(opendss_rows),
            "sequential_slot_solves_per_trajectory": 96,
            "total_sequential_slot_solves": (270 + len(opendss_rows)) * 96,
        },
        "failure_causality": {
            "preexisting_D1_anchor_violation_day_count": len(anchor_fail_days),
            "preexisting_D1_anchor_violation_days": anchor_fail_days,
            "candidate_new_violation_day_count": len(candidate_new_fail_days),
            "candidate_new_violation_days": candidate_new_fail_days,
            "maximum_anchor_rho_AC": max(float(row["anchor_rho_max_AC"]) for row in opendss_rows),
            "maximum_anchor_Vmax_pu": max(float(row["anchor_Vmax_pu"]) for row in opendss_rows),
            "minimum_anchor_Vmin_pu": min(float(row["anchor_Vmin_pu"]) for row in opendss_rows),
        },
        "downstream_science_authorized": selected is not None,
        "blocked_reason": (
            None if selected is not None else
            "All frozen rho candidates fail absolute AC physical gates on pre-April days; "
            "the violations are already present in the D-1 anchor state and no candidate "
            "passes every certification day."
        ),
        "candidate_results": candidates,
        "required_statement": (
            f"rho_AIDC={selected:.2f} was selected from pre-April physics certification and not from April development performance."
            if selected is not None else
            "No rho_AIDC candidate passed every pre-April physics gate."
        ),
    }
    write_json(out / "V29R1_TRUST_CERT_DECISION.json", decision)
    if selected is None:
        raise RuntimeError("V29R1_NO_PHYSICS_CERTIFIED_RHO")
    return decision

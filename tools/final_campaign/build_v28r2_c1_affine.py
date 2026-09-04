#!/usr/bin/env python3
"""Certify April-day C1 endpoint-secant planning equalities."""

from __future__ import annotations

import csv
import dataclasses
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from dayahead.aidc_power_response import KAPPA_KW_PER_ACTIVE_H100_NODE
from dayahead.authority import sha256_file
from dayahead.v28.thermal import FROZEN_AGGREGATE_IT_PEAK_MW, GFS_NORMALIZATION_FACTOR
from dayahead.v28r2.c1_affine import (
    FROZEN_NLR_EQUIVALENT_SCALE, analytic_convexity_certificate, endpoint_secant,
    exact_c1_pcc_kw, load_c1,
)
from dayahead.v28r2.c1_certificate import summarize
from dayahead.v28r2.reference_compute import (
    FullNodeDistributionAdapter, build_reference_schedule, case_rack_capacity_nodeh_per_slot,
)
from dayahead.v28r2.reference_delta import build_reference_delta
from dayahead.v28r2.source_labels import load_optimizer_labels
from tools.final_campaign.build_v28r2_reference_delta import causal_predictions

OUT = REPO / "dayahead/artifacts/v28r2_heavy_backend"
DATE = "2025-04-02"


def write_json(name: str, payload: object) -> None:
    path = OUT / name
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def write_csv(name: str, rows: list[dict[str, object]]) -> None:
    path = OUT / name
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    os.replace(temporary, path)


def weather() -> tuple[np.ndarray, np.ndarray, str]:
    source = REPO / "dayahead/artifacts/v24t_thermal_aware_aidc/V24T_GFS_D1_FORECAST.parquet"
    frame = pd.read_parquet(source)
    initialization = pd.Timestamp("2025-04-01 06:00:00", tz="UTC")
    selected = frame[frame["initialization_utc"].eq(initialization)].copy()
    selected.index = pd.DatetimeIndex(selected["valid_time_utc"]).tz_convert("Etc/GMT-10")
    target = pd.date_range(DATE, periods=96, freq="15min", tz="Etc/GMT-10")
    expanded = selected[["t_wb_c", "rh_pct"]].reindex(selected.index.union(target)).sort_index().interpolate(method="time").reindex(target)
    if expanded.isna().any().any():
        raise RuntimeError("V28R2_C1_GFS_INTERPOLATION_GAP")
    return np.asarray(expanded["t_wb_c"], dtype=float), np.asarray(expanded["rh_pct"], dtype=float), sha256_file(source)


def planning_intervals():
    labels = load_optimizer_labels(REPO)
    p_quantiles, g_quantiles, w_quantiles = causal_predictions(labels, DATE)
    p_authority = json.loads((OUT / "V28R2_FINAL_P_REF_LIGHTGBM_AUTHORITY.json").read_text(encoding="utf-8"))
    p_q90 = p_quantiles[2] * float(p_authority["scale_binding"]["alpha_IT"])
    g_q90 = g_quantiles[2]
    adapter_payload = json.loads((OUT / "V28R2_FULLNODE_DISTRIBUTION_ADAPTER.json").read_text(encoding="utf-8"))
    adapter = FullNodeDistributionAdapter(np.asarray(adapter_payload["probabilities"]), labels.cohort_ids)
    arrivals = adapter.materialize(float(w_quantiles[1]), pd.Timestamp(DATE).dayofweek)
    rack_source = REPO / "dayahead/artifacts/v16/AIDC_RACK_MAPPING_CONTRACT.json"
    rack_payload = json.loads(rack_source.read_text(encoding="utf-8"))
    rack_ids = tuple(row["rack_id"] for row in rack_payload["racks"])
    aidc_ids = tuple(dict.fromkeys(row["aidc_id"] for row in rack_payload["racks"]))
    power_weights = dict(zip(rack_ids, map(float, rack_payload["power_weights"]), strict=True))
    gpu_weights = dict(zip(rack_ids, map(float, rack_payload["gpu_weights"]), strict=True))
    capacities = case_rack_capacity_nodeh_per_slot(rack_ids, gpu_weights)
    mapped_p = np.asarray(rack_payload["power_weights"], dtype=float)[:, None] * p_q90
    mapped_g = np.asarray(rack_payload["gpu_weights"], dtype=float)[:, None] * g_q90
    schedule = build_reference_schedule(
        arrivals, cohort_ids=labels.cohort_ids, rack_ids=rack_ids,
        rack_capacity_nodeh_per_slot=capacities,
        rack_power_envelope_kw=mapped_p, rack_gpu_envelope_gpu=mapped_g,
    )
    delta = build_reference_delta(
        p_q90, g_q90, schedule.p_f_ref_kw, schedule.g_f_ref_gpu,
        rack_ids=rack_ids, power_weights=power_weights, gpu_weights=gpu_weights,
    )
    rack_index = {rack: index for index, rack in enumerate(rack_ids)}
    p_min = np.zeros((len(aidc_ids), 96), dtype=float)
    p_max = np.zeros_like(p_min)
    max_kappa = max(KAPPA_KW_PER_ACTIVE_H100_NODE.values())
    for aidc_index, aidc in enumerate(aidc_ids):
        indices = [rack_index[row["rack_id"]] for row in rack_payload["racks"] if row["aidc_id"] == aidc]
        p_min[aidc_index] = delta.p_res_plan_kw[indices].sum(axis=0)
        maximum_flexible_kw = float(capacities[indices].sum() / 0.25 * max_kappa)
        p_max[aidc_index] = p_min[aidc_index] + maximum_flexible_kw
    return aidc_ids, p_min, p_max, rack_source, float(w_quantiles[1])


def main() -> None:
    c1_source = REPO / "dayahead/artifacts/v24t_thermal_aware_aidc/V24T_C1_QUASISTATIC_MODEL.json"
    parameters = load_c1(c1_source)
    aidc_ids, p_min, p_max, rack_source, w_q50 = planning_intervals()
    wetbulb, rh, weather_sha = weather()
    coefficients = []
    convexity_rows: list[dict[str, object]] = []
    coefficient_rows: list[dict[str, object]] = []
    dense_minimum = float("inf")
    for aidc_index, aidc in enumerate(aidc_ids):
        for slot in range(96):
            coefficient = endpoint_secant(
                aidc, slot, float(p_min[aidc_index, slot]), float(p_max[aidc_index, slot]),
                float(wetbulb[slot]), float(rh[slot]), parameters,
            )
            coefficients.append(coefficient)
            dense = np.linspace(coefficient.p_min_kw, coefficient.p_max_kw, 257)
            errors = coefficient.slope * dense + coefficient.intercept_kw - exact_c1_pcc_kw(
                dense, coefficient.wetbulb_c, coefficient.rh_pct, parameters,
            )
            dense_minimum = min(dense_minimum, float(errors.min()))
            convexity_rows.append({
                "aidc_id": aidc,
                "slot": slot,
                "p_min_kw": coefficient.p_min_kw,
                "p_max_kw": coefficient.p_max_kw,
                "wetbulb_c": coefficient.wetbulb_c,
                "rh_pct": coefficient.rh_pct,
                "analytic_convexity": analytic_convexity_certificate(parameters, coefficient.p_min_kw, coefficient.p_max_kw, coefficient.wetbulb_c),
                "certificate": "softplus_of_affine_plus_identity; second_derivative=sigmoid(z)*(1-sigmoid(z))*slope_squared>=0",
                "dense_diagnostic_min_second_difference_kw": float(np.diff(exact_c1_pcc_kw(dense, coefficient.wetbulb_c, coefficient.rh_pct, parameters), n=2).min()),
            })
            coefficient_rows.append(dataclasses.asdict(coefficient))
    write_csv("V28R2_C1_CONVEXITY_AUDIT.csv", convexity_rows)
    write_csv("V28R2_C1_AFFINE_COEFFICIENTS.csv", coefficient_rows)

    transformer_source = REPO / "dayahead/artifacts/v16_2/AIDC_PCC_TRANSFORMER_CONTRACT_V2.json"
    certificate = summarize(
        coefficients,
        site_rating_kw=1500.0 * 0.95,
        aggregate_rating_kw=528.8087919579648,
    )
    certificate.update({
        "artifact_id": "V28R2_C1_AFFINE_ERROR_CERTIFICATE_V1",
        "forecast_date": DATE,
        "mathematical_certificate": "analytic convexity plus endpoint secant; maximum error at unique f'(P)=secant slope located by 80-step bisection",
        "bisection_root_bracket_fraction": 2.0**-80,
        "dense_grid_role": "diagnostic only",
        "dense_grid_minimum_conservatism_kw": dense_minimum,
        "site_rating_basis": "1500_kVA_frozen_PCC_transformer_times_frozen_PF_0.95",
        "aggregate_rating_basis_kw": 528.8087919579648,
        "W_Q50_daily_nodeh_for_interval": w_q50,
        "C1_source_sha256": sha256_file(c1_source),
        "weather_source_sha256": weather_sha,
        "rack_source_sha256": sha256_file(rack_source),
        "transformer_source_sha256": sha256_file(transformer_source),
    })
    write_json("V28R2_C1_AFFINE_ERROR_CERTIFICATE.json", certificate)
    ready = certificate["status"] == "PASS"
    coefficient_sha = sha256_file(OUT / "V28R2_C1_AFFINE_COEFFICIENTS.csv")
    write_json("V28R2_C1_AFFINE_CONTRACT.json", {
        "artifact_id": "V28R2_C1_AFFINE_CONTRACT_V1",
        "status": "PASS" if ready else "FAIL_C1_AFFINE_SURROGATE_CERTIFICATION",
        "exact_model": "V24T_C1_QUASISTATIC_MODEL",
        "exact_model_sha256": sha256_file(c1_source),
        "C1_refit_calls": 0,
        "C1_retune_calls": 0,
        "planning_relation": "P_PCC_PLAN[i,t] = a[i,t] * P_IT[i,t] + b[i,t]",
        "representation": "single continuous affine equality per site and slot",
        "surrogate": "endpoint secant over source/capacity-derived feasible IT interval",
        "nlr_equivalent_scale": FROZEN_NLR_EQUIVALENT_SCALE,
        "normalization_factor": GFS_NORMALIZATION_FACTOR,
        "coefficient_sha256": coefficient_sha,
        "coefficient_count": len(coefficients),
        "binary_variable_count": 0,
        "SOS2_count": 0,
        "epigraph_inequality_count": 0,
        "PUE_PLAN_import_count": 0,
        "C2_import_count": 0,
        "beta_AIDC_count": 0,
        "reactive_power": {"power_factor": 0.95, "formula": "Q=P*tan(acos(0.95))", "Q_zero": False},
        "exact_physical_evaluation": {"dayahead": "C1+GFS", "actual": "C1+NOAA", "perfect_information": "C1+NOAA"},
        "C1_AFFINE_CONSERVATISM_READY": certificate["C1_AFFINE_CONSERVATISM_READY"],
        "C1_AFFINE_ERROR_READY": certificate["C1_AFFINE_ERROR_READY"],
        "C1_SURROGATE_LP_COMPATIBLE": ready,
    })
    write_json("V28R2_C1_LP_COMPATIBILITY_RESOLUTION.json", {
        "artifact_id": "V28R2_C1_LP_COMPATIBILITY_RESOLUTION_V1",
        "status": "PASS" if ready else "FAIL_C1_AFFINE_SURROGATE_CERTIFICATION",
        "rejected_binding": "24-segment PCC >= a_k*IT+b_k epigraph",
        "rejection_reason": "grid objective does not force epigraph tightness",
        "accepted_binding": "one endpoint-secant equality per site/slot/feasible interval",
        "LP_subproblem_retained": True,
        "integer_or_SOS2_added": False,
        "common_binding_function": "dayahead.v28r2.c1_affine.add_planning_equality",
        "coefficient_sha256_by_solver": {
            "Monolithic": coefficient_sha,
            "Standard_Single_Cut_BD": coefficient_sha,
            "CL_MC_BD": coefficient_sha,
        },
        "legacy_PUE_PLAN_reachable_from_v28r2_c1_module": False,
        "C1_SOLVER_BINDING_READY": False,
        "C1_solver_binding_note": "common certified binding ready; production solver consumers are connected in the heavy-backend commits",
    })
    if not ready:
        raise SystemExit(2)


if __name__ == "__main__":
    main()

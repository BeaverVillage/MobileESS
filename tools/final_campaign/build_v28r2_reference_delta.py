#!/usr/bin/env python3
"""Materialize April 1 forecasts and audit the map-first reference delta."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from dayahead.authority import sha256_file
from dayahead.v28r2.lightgbm_channels import daily_features, predict_serialized_quantiles, slot_features
from dayahead.v28r2.reference_compute import (
    FullNodeDistributionAdapter, build_reference_schedule, case_rack_capacity_nodeh_per_slot,
)
from dayahead.v28r2.reference_delta import LABEL, build_reference_delta
from dayahead.v28r2.source_labels import load_optimizer_labels

OUT = REPO / "dayahead/artifacts/v28r2_heavy_backend"
MODELS = OUT / "V28R2_OPTIMIZER_CHANNEL_MODELS"


def write_json(name: str, payload: object) -> None:
    path = OUT / name
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def causal_predictions(labels, target_date: str):
    target = pd.Timestamp(target_date, tz=labels.timestamps.tz)
    future_index = pd.date_range(labels.timestamps[-1] + pd.Timedelta(minutes=15), target + pd.Timedelta(days=1), freq="15min", inclusive="left")
    extended_index = labels.timestamps.append(future_index)
    variant = "APRIL_01_CAUSAL_FIT" if target_date == "2025-04-01" else "GENERAL_THROUGH_MARCH_31_FIT"
    p_values = np.concatenate([labels.p_it_kw, np.full(len(future_index), np.nan)])
    g_values = np.concatenate([labels.g_h100_gpu, np.full(len(future_index), np.nan)])
    target_index = pd.date_range(target, periods=96, freq="15min")
    p_x = slot_features(p_values, extended_index).loc[target_index]
    g_x = slot_features(g_values, extended_index).loc[target_index]
    if not np.isfinite(p_x).all().all() or not np.isfinite(g_x).all().all():
        raise RuntimeError("V28R2_APRIL1_CAUSAL_FEATURE_MISSING")
    p_quantiles = predict_serialized_quantiles(MODELS, "P_REF", variant, p_x)
    g_quantiles = predict_serialized_quantiles(MODELS, "G_REF", variant, g_x)

    daily_index = pd.date_range(labels.timestamps[0].normalize(), labels.timestamps[-1].normalize(), freq="D", tz=labels.timestamps.tz)
    daily_w = pd.Series(labels.w_nodeh.reshape(-1, 96, len(labels.cohort_ids)).sum(axis=(1, 2)), index=daily_index)
    future_days = pd.date_range(daily_index[-1] + pd.Timedelta(days=1), target, freq="D")
    extended_daily = pd.concat([daily_w, pd.Series(np.nan, index=future_days)])
    w_x = daily_features(extended_daily).iloc[[-1]]
    if not np.isfinite(w_x).all().all():
        raise RuntimeError("V28R2_APRIL1_W_CAUSAL_FEATURE_MISSING")
    w_quantiles = predict_serialized_quantiles(MODELS, "W_FULLNODE_DAILY", variant, w_x)[:, 0]
    return p_quantiles, g_quantiles, w_quantiles


def main() -> None:
    labels = load_optimizer_labels(REPO)
    p_quantiles, g_quantiles, w_quantiles = causal_predictions(labels, "2025-04-01")
    p_authority = json.loads((OUT / "V28R2_FINAL_P_REF_LIGHTGBM_AUTHORITY.json").read_text(encoding="utf-8"))
    alpha_it = float(p_authority["scale_binding"]["alpha_IT"])
    p_q90 = p_quantiles[2] * alpha_it
    g_q90 = g_quantiles[2]  # C_MODEL/C_K = 528/528 = 1.

    adapter_payload = json.loads((OUT / "V28R2_FULLNODE_DISTRIBUTION_ADAPTER.json").read_text(encoding="utf-8"))
    adapter = FullNodeDistributionAdapter(np.asarray(adapter_payload["probabilities"], dtype=float), labels.cohort_ids)
    arrivals = adapter.materialize(float(w_quantiles[1]), 1)  # 2025-04-01 Tuesday
    rack_source = REPO / "dayahead/artifacts/v16/AIDC_RACK_MAPPING_CONTRACT.json"
    rack_payload = json.loads(rack_source.read_text(encoding="utf-8"))
    rack_ids = tuple(row["rack_id"] for row in rack_payload["racks"])
    power_weights = dict(zip(rack_ids, map(float, rack_payload["power_weights"]), strict=True))
    gpu_weights = dict(zip(rack_ids, map(float, rack_payload["gpu_weights"]), strict=True))
    capacities = case_rack_capacity_nodeh_per_slot(rack_ids, gpu_weights)
    mapped_p_envelope = np.asarray(rack_payload["power_weights"], dtype=float)[:, None] * p_q90
    mapped_g_envelope = np.asarray(rack_payload["gpu_weights"], dtype=float)[:, None] * g_q90
    schedule = build_reference_schedule(
        arrivals, cohort_ids=labels.cohort_ids, rack_ids=rack_ids,
        rack_capacity_nodeh_per_slot=capacities,
        rack_power_envelope_kw=mapped_p_envelope,
        rack_gpu_envelope_gpu=mapped_g_envelope,
    )

    failure = None
    delta = None
    try:
        delta = build_reference_delta(
            p_q90, g_q90, schedule.p_f_ref_kw, schedule.g_f_ref_gpu,
            rack_ids=rack_ids, power_weights=power_weights, gpu_weights=gpu_weights,
        )
    except ValueError as error:
        failure = str(error)
    ready = delta is not None
    write_json("V28R2_REFERENCE_DELTA_CONTRACT.json", {
        "artifact_id": "V28R2_REFERENCE_DELTA_CONTRACT_V1",
        "status": "PASS" if ready else "FAIL_REFERENCE_DELTA_DECOMPOSITION",
        "label": LABEL,
        "formulas": {
            "P_RES_PLAN": "w_P[r] * P_IT_REF_Q90[t] - P_F_REF[r,t]",
            "G_RES_PLAN": "w_G[r] * G_REF_Q90[t] - G_F_REF[r,t]",
        },
        "mapping_order": "map-first then subtract",
        "numeric_tolerance": 1e-9,
        "substantive_clipping": False,
        "offset_injection": False,
        "W_reduction_on_failure": False,
        "semantic_denials": ["measured_nonflexible_power", "physical_background", "background_Q90", "probabilistic_quantile_subtraction_closure"],
        "rack_mapping_sha256": sha256_file(rack_source),
        "REFERENCE_DELTA_CLOSURE_READY": ready,
    })
    mapped_p = mapped_p_envelope
    mapped_g = mapped_g_envelope
    raw_p = mapped_p - schedule.p_f_ref_kw
    raw_g = mapped_g - schedule.g_f_ref_gpu
    write_json("V28R2_REFERENCE_DELTA_CLOSURE_AUDIT.json", {
        "artifact_id": "V28R2_REFERENCE_DELTA_CLOSURE_AUDIT_V1",
        "status": "PASS" if ready else "FAIL_REFERENCE_DELTA_DECOMPOSITION",
        "forecast_date": "2025-04-01",
        "shape": [len(rack_ids), 96],
        "P_Q90_case_kW_min_max": [float(p_q90.min()), float(p_q90.max())],
        "G_Q90_case_GPU_min_max": [float(g_q90.min()), float(g_q90.max())],
        "W_Q50_daily_nodeh": float(w_quantiles[1]),
        "W_materialization_mass_error_nodeh": float(abs(arrivals.sum() - w_quantiles[1])),
        "P_raw_residual_min_kW": float(raw_p.min()),
        "G_raw_residual_min_GPU": float(raw_g.min()),
        "P_substantive_negative_cell_count": int((raw_p < -1e-9).sum()),
        "G_substantive_negative_cell_count": int((raw_g < -1e-9).sum()),
        "P_tolerance_canonicalized_cell_count": 0 if delta is None else delta.p_tolerance_cells,
        "G_tolerance_canonicalized_cell_count": 0 if delta is None else delta.g_tolerance_cells,
        "terminal_backlog_nodeh": float(schedule.backlog_nodeh[-1].sum()),
        "failure": failure,
        "OPTIMIZER_CHANNEL_AUTHORITY_READY": ready,
    })
    if not ready:
        raise SystemExit(2)


if __name__ == "__main__":
    main()

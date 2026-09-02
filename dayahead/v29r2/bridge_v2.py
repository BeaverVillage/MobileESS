"""Causal PRE_DAY_QUEUE_BRIDGE_V2 at the frozen optimizer cohort level."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from dayahead.v29r1.authority import CERTIFICATION_DAYS, RELIABILITY_TARGET
from dayahead.v29r1.source_resume import sha256_file, write_csv, write_json
from tools.v29.run_stage3_carryin_authority import cohort, cohort_bins, read_candidate_events, source_zip

from .anchor_forensic import OUT_REL
from .service_model import (
    CLASSIFIER_PARAMS, EVALUATION_START, FEATURE_NAMES, MODEL_SEED, REGRESSOR_PARAMS,
    build_job_day_instances, cutoff, fit_hurdle, predict_hurdle_components, rolling_origin,
)


def _bridge_view(rows: pd.DataFrame, *, prediction: bool) -> pd.DataFrame:
    result = rows.copy()
    if prediction:
        result["H_REQ"] = result["H_REQ"].to_numpy(dtype=float) - result["H_NOM"].to_numpy(dtype=float)
    else:
        result["H_REQ"] = result["H_REQ"].to_numpy(dtype=float) - result["H_REALIZED"].to_numpy(dtype=float)
        result["H_REALIZED"] = result["H_PRE_D0_REALIZED"].to_numpy(dtype=float)
        result["positive_service"] = result["H_REALIZED"].gt(0).astype(int)
        result["realization_fraction"] = np.divide(
            result["H_REALIZED"].to_numpy(dtype=float), result["H_REQ"].to_numpy(dtype=float),
            out=np.zeros(len(result), dtype=float), where=result["H_REQ"].to_numpy(dtype=float) > 0,
        )
    result = result.loc[result["H_REQ"].gt(1e-12)].copy()
    valid = (result["H_REQ"] >= 0).all()
    if not prediction:
        valid = bool(
            valid
            and (result["H_REALIZED"] >= 0).all()
            and (result["H_REALIZED"] <= result["H_REQ"] + 1e-9).all()
        )
    if not valid:
        raise RuntimeError("V29R2_BRIDGE_V2_TARGET_BOUND_FAILURE")
    return result


def rolling_bridge(instances: pd.DataFrame) -> tuple[list[dict[str, object]], pd.DataFrame]:
    _service_rows, service_jobs = rolling_origin(instances)
    rows: list[dict[str, object]] = []
    job_rows: list[pd.DataFrame] = []
    for day in sorted(set(service_jobs["target_day"])):
        mark = cutoff(str(day))
        fit_source = instances.loc[instances["label_available_utc"].le(mark)]
        train = _bridge_view(fit_source, prediction=False)
        validation = service_jobs.loc[service_jobs["target_day"].eq(day)].copy()
        predict_view = _bridge_view(validation, prediction=True)
        if train.empty or predict_view.empty:
            continue
        model = fit_hurdle(train)
        probability, fraction = predict_hurdle_components(model, predict_view)
        pre_nom = predict_view["H_REQ"].to_numpy(dtype=float) * probability * fraction
        validation["pre_D0_service_probability"] = 0.0
        validation["H_PRE_D0_NOM"] = 0.0
        validation.loc[predict_view.index, "pre_D0_service_probability"] = probability
        validation.loc[predict_view.index, "H_PRE_D0_NOM"] = pre_nom
        validation["H0_REQ"] = validation["H_REQ"] - validation["H_PRE_D0_NOM"]
        validation["H0_NOM"] = validation["H_NOM"]
        validation["H0_LOW"] = validation["H_LOW"]
        validation["H0_REALIZED"] = validation["H_REALIZED"]
        if not (
            np.allclose(validation["H_REQ"], validation["H_PRE_D0_NOM"] + validation["H0_REQ"], atol=1e-9)
            and (validation["H0_LOW"] >= -1e-9).all()
            and (validation["H0_LOW"] <= validation["H0_NOM"] + 1e-9).all()
            and (validation["H0_NOM"] <= validation["H0_REQ"] + 1e-9).all()
        ):
            raise RuntimeError(f"V29R2_BRIDGE_V2_PREDICTED_MASS_FAILURE:{day}")
        job_rows.append(validation)
        for cohort_id, selected in validation.groupby("cohort_id", sort=True):
            requested = float(selected["H_REQ"].sum())
            pre_nominal = float(selected["H_PRE_D0_NOM"].sum())
            pre_realized = float(selected["H_PRE_D0_REALIZED"].sum())
            h0_req = float(selected["H0_REQ"].sum())
            h0_nom = float(selected["H0_NOM"].sum())
            h0_low = float(selected["H0_LOW"].sum())
            h0_realized = float(selected["H0_REALIZED"].sum())
            rows.append({
                "day": day, "cohort_id": cohort_id, "aggregation_level": "D_DAY_X_COHORT",
                "cutoff_utc": str(mark), "job_count": len(selected),
                "cutoff_H_REQ": requested,
                "pre_D0_service_probability_request_weighted": float(np.average(
                    selected["pre_D0_service_probability"], weights=selected["H_REQ"],
                )),
                "pre_D0_service_NOM": pre_nominal, "pre_D0_service_REALIZED": pre_realized,
                "H0_REQ": h0_req, "H0_NOM": h0_nom, "H0_LOW": h0_low, "H0_REALIZED": h0_realized,
                "bridge_nominal_error": h0_nom - h0_realized,
                "lower_bound_covered": h0_realized + 1e-9 >= h0_low,
                "predicted_mass_error": requested - pre_nominal - h0_req,
                "actual_no_double_count_margin": requested - pre_realized - h0_realized,
                "evaluation_row": bool(selected["evaluation_row"].iloc[0]),
                "fit_rows_with_label_available_after_cutoff": 0,
                "April_rows_used": 0,
            })
    return rows, pd.concat(job_rows, ignore_index=True) if job_rows else pd.DataFrame()


def _calibration(rows: list[dict[str, object]]) -> dict[str, object]:
    evaluation = [row for row in rows if bool(row["evaluation_row"])]
    if not evaluation:
        raise RuntimeError("V29R2_BRIDGE_V2_NO_EVALUATION_ROWS")
    realized = np.asarray([row["H0_REALIZED"] for row in evaluation], dtype=float)
    nominal = np.asarray([row["H0_NOM"] for row in evaluation], dtype=float)
    lower = np.asarray([row["H0_LOW"] for row in evaluation], dtype=float)
    pre_realized = np.asarray([row["pre_D0_service_REALIZED"] for row in evaluation], dtype=float)
    pre_nominal = np.asarray([row["pre_D0_service_NOM"] for row in evaluation], dtype=float)
    error = nominal - realized
    coverage = float(np.mean(realized + 1e-9 >= lower))
    return {
        "artifact_id": "V29R2_BRIDGE_V2_CALIBRATION_V1",
        "status": "PASS" if coverage >= RELIABILITY_TARGET else "FAIL",
        "aggregation_level": "D-day x frozen optimizer cohort",
        "evaluation_cohort_day_count": len(evaluation),
        "evaluation_day_count": len({str(row["day"]) for row in evaluation}),
        "lower_bound_coverage": coverage, "coverage_target": RELIABILITY_TARGET,
        "nominal_bias_nodeh": float(error.mean()),
        "nominal_MAE_nodeh": float(np.abs(error).mean()),
        "nominal_WAPE": float(np.abs(error).sum() / max(realized.sum(), 1e-15)),
        "zero_state_accuracy": float(np.mean((nominal <= 1e-9) == (realized <= 1e-9))),
        "overforecast_cohort_day_count": int(np.sum(error > 1e-9)),
        "underforecast_cohort_day_count": int(np.sum(error < -1e-9)),
        "pre_D0_nominal_bias_nodeh": float((pre_nominal - pre_realized).mean()),
        "pre_D0_nominal_MAE_nodeh": float(np.abs(pre_nominal - pre_realized).mean()),
        "predicted_mass_identity_max_error": max(abs(float(row["predicted_mass_error"])) for row in rows),
        "actual_no_double_count_min_margin": min(float(row["actual_no_double_count_margin"]) for row in rows),
        "April_fit_rows": 0,
    }


def build_bridge_v2(repo: Path) -> dict[str, object]:
    out = repo / OUT_REL
    service = json.loads((out / "V29R2_EXEC_SERVICE_MODEL_AUTHORITY.json").read_text(encoding="utf-8"))
    if service["status"] != "PASS" or not service["downstream_bridge_authorized"]:
        raise RuntimeError("V29R2_BRIDGE_V2_WITHOUT_SERVICE_AUTHORITY")
    raw_path = source_zip()
    events, _members, _schemas = read_candidate_events(raw_path)
    instances = build_job_day_instances(events, CERTIFICATION_DAYS)
    bins = cohort_bins(repo)
    instances["cohort_id"] = [
        cohort(int(nodes), float(hours), bins)
        for nodes, hours in zip(instances["nodes"], instances["request_hours"], strict=True)
    ]
    rows, jobs = rolling_bridge(instances)
    calibration = _calibration(rows)
    contract = {
        "artifact_id": "V29R2_BRIDGE_V2_CONTRACT_V1",
        "status": "PASS" if calibration["status"] == "PASS" else "V29R2_BRIDGE_V2_CALIBRATION_FAIL",
        "authority": "PRE_DAY_QUEUE_BRIDGE_V2",
        "cutoff": "D-1 18:00 fixed AEST", "bridge_end": "D0 00:00 fixed AEST",
        "optimization_boundary": "D0 00:00-24:00; 24 hours; 96 15-minute slots",
        "pre_day_interval": "six-hour state propagation only; not optimization horizon",
        "model_family": "deterministic LightGBM hurdle for pre-D0 execution on the residual request envelope",
        "model_seed": MODEL_SEED, "feature_names": list(FEATURE_NAMES),
        "classifier_parameters": CLASSIFIER_PARAMS, "regressor_parameters": REGRESSOR_PARAMS,
        "outputs": ["H0_REQ", "H0_NOM", "H0_LOW"],
        "identities": {
            "predicted": "cutoff_H_REQ = pre_D0_service_NOM + H0_REQ",
            "bounds": "0 <= H0_LOW <= H0_NOM <= H0_REQ",
            "actual": "pre_D0_service_REALIZED + H0_REALIZED <= cutoff_H_REQ",
        },
        "future_actual_feature_count": 0, "April_fit_rows": 0,
        "running_job_preemption": False, "post_cutoff_arrival_bridge_count": 0,
        "grid_signal_reads": 0, "optimization_horizon_extended": False,
        "rolling_origin": True, "calibration": calibration,
        "service_authority_sha256": sha256_file(out / "V29R2_EXEC_SERVICE_MODEL_AUTHORITY.json"),
        "reference_v4_authorized": calibration["status"] == "PASS",
    }
    write_json(out / "V29R2_BRIDGE_V2_CONTRACT.json", contract)
    write_csv(out / "V29R2_BRIDGE_V2_ROLLING_ORIGIN.csv", rows)
    write_json(out / "V29R2_BRIDGE_V2_CALIBRATION.json", calibration)
    if contract["status"] != "PASS":
        raise RuntimeError(str(contract["status"]))
    if jobs.empty:
        raise RuntimeError("V29R2_BRIDGE_V2_NO_JOB_ROWS")
    return contract

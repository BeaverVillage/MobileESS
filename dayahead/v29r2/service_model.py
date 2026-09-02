"""Causal executable-service hurdle model and aggregate conformal authority."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

import lightgbm as lgb
import numpy as np
import pandas as pd

from dayahead.v28r2.authority import CONTROLLABLE_NODE_CLASSES
from dayahead.v29r1.authority import CERTIFICATION_DAYS, RELIABILITY_TARGET
from dayahead.v29r1.source_resume import sha256_file, write_csv, write_json
from tools.v29.run_stage3_carryin_authority import (
    AEST, cohort, cohort_bins, read_candidate_events, source_zip,
)

from .anchor_forensic import OUT_REL


MODEL_SEED = 29
ROLLING_START = "2025-01-15"
EVALUATION_START = "2025-02-01"
MIN_CONFORMAL_POSITIVE_GROUPS = 30
EPSILON_FRACTION = 1e-4
FEATURE_NAMES = (
    "partition_hash", "nodes_req", "gpus_requested", "wallclock_req_hours",
    "qos_hash", "submit_epoch_days", "queue_age_hours", "submit_hour",
    "submit_day_of_week", "submit_month",
)
CLASSIFIER_PARAMS = {
    "objective": "binary", "n_estimators": 80, "learning_rate": .05,
    "num_leaves": 15, "max_depth": 4, "min_child_samples": 10,
    "reg_lambda": 1.0, "subsample": 1.0, "colsample_bytree": 1.0,
    "random_state": MODEL_SEED, "n_jobs": 1, "deterministic": True,
    "force_col_wise": True, "verbosity": -1,
}
REGRESSOR_PARAMS = {
    "objective": "regression_l1", "n_estimators": 80, "learning_rate": .05,
    "num_leaves": 15, "max_depth": 4, "min_child_samples": 10,
    "reg_lambda": 1.0, "subsample": 1.0, "colsample_bytree": 1.0,
    "random_state": MODEL_SEED, "n_jobs": 1, "deterministic": True,
    "force_col_wise": True, "verbosity": -1,
}


@dataclass
class HurdleFit:
    classifier: object
    regressor: object
    constant_probability: float | None
    constant_logit_fraction: float | None


def cutoff(day: str) -> pd.Timestamp:
    return (pd.Timestamp(day, tz=AEST) - pd.Timedelta(hours=6)).tz_convert("UTC")


def day_bounds(day: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    start = pd.Timestamp(day, tz=AEST).tz_convert("UTC")
    return start, start + pd.Timedelta(days=1)


def _stable_hash(value: object) -> float:
    digest = hashlib.sha256(str(value).casefold().encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") / float(2**64 - 1)


def _request_hours(values: pd.Series) -> pd.Series:
    return pd.to_timedelta(values, errors="coerce").dt.total_seconds() / 3600.0


def prepare_events(events: pd.DataFrame) -> pd.DataFrame:
    frame = events.copy()
    frame["submit_utc"] = pd.to_datetime(frame["submit_time"], utc=True, errors="coerce")
    frame["start_utc"] = pd.to_datetime(frame["start_time"], utc=True, errors="coerce")
    frame["end_utc"] = pd.to_datetime(frame["end_time"], utc=True, errors="coerce")
    frame["nodes"] = pd.to_numeric(frame["nodes_req"], errors="coerce")
    frame["gpus"] = pd.to_numeric(frame["gpus_requested"], errors="coerce")
    frame["request_hours"] = _request_hours(frame["wallclock_req"])
    strict = (
        frame["partition"].astype(str).str.casefold().str.contains("gpu-h100", regex=False)
        & frame["nodes"].isin(CONTROLLABLE_NODE_CLASSES)
        & np.isclose(frame["gpus"], 4.0 * frame["nodes"], equal_nan=False)
        & frame["request_hours"].gt(0)
        & frame["submit_utc"].notna()
    )
    return frame.loc[strict].reset_index(drop=True)


def _feature_frame(rows: pd.DataFrame) -> pd.DataFrame:
    submit = pd.to_datetime(rows["submit_utc"], utc=True)
    result = pd.DataFrame(index=rows.index)
    result["partition_hash"] = rows["partition"].fillna("MISSING").map(_stable_hash)
    result["nodes_req"] = rows["nodes"].astype(float)
    result["gpus_requested"] = rows["gpus"].astype(float)
    result["wallclock_req_hours"] = rows["request_hours"].astype(float)
    result["qos_hash"] = rows["qos"].fillna("MISSING").map(_stable_hash)
    result["submit_epoch_days"] = submit.map(lambda value: value.timestamp() / 86400.0)
    result["queue_age_hours"] = rows["queue_age_hours"].astype(float)
    result["submit_hour"] = submit.dt.hour.astype(float)
    result["submit_day_of_week"] = submit.dt.dayofweek.astype(float)
    result["submit_month"] = submit.dt.month.astype(float)
    if tuple(result.columns) != FEATURE_NAMES or not np.isfinite(result.to_numpy(dtype=float)).all():
        raise RuntimeError("V29R2_EXEC_SERVICE_FEATURE_MATRIX_INVALID")
    return result


def build_job_day_instances(events: pd.DataFrame, days: Sequence[str]) -> pd.DataFrame:
    prepared = prepare_events(events)
    instances: list[pd.DataFrame] = []
    for day in days:
        mark = cutoff(day)
        start_day, end_day = day_bounds(day)
        not_started = prepared["start_utc"].isna() | prepared["start_utc"].gt(mark)
        not_cancelled = prepared["start_utc"].notna() | prepared["end_utc"].isna() | prepared["end_utc"].gt(mark)
        queued = prepared["submit_utc"].le(mark) & not_started & not_cancelled
        selected = prepared.loc[queued].copy()
        if selected.empty:
            continue
        selected["target_day"] = day
        selected["cutoff_utc"] = mark
        selected["label_available_utc"] = end_day
        selected["queue_age_hours"] = (mark - selected["submit_utc"]).dt.total_seconds() / 3600.0
        selected["H_REQ"] = selected["nodes"] * selected["request_hours"]
        overlap_start = selected["start_utc"].where(selected["start_utc"].gt(start_day), start_day)
        overlap_end = selected["end_utc"].where(selected["end_utc"].lt(end_day), end_day)
        overlap_hours = (overlap_end - overlap_start).dt.total_seconds().div(3600.0)
        valid_execution = selected["start_utc"].notna() & selected["end_utc"].notna()
        overlap_hours = overlap_hours.where(valid_execution, 0.0).clip(lower=0.0)
        # Executed requested service is definitionally bounded by the request.
        selected["realized_requested_hours"] = np.minimum(overlap_hours, selected["request_hours"])
        selected["H_REALIZED"] = selected["nodes"] * selected["realized_requested_hours"]
        selected["positive_service"] = selected["H_REALIZED"].gt(0).astype(int)
        selected["realization_fraction"] = selected["H_REALIZED"] / selected["H_REQ"]
        if not (
            (selected["H_REQ"] > 0).all()
            and (selected["H_REALIZED"] >= 0).all()
            and (selected["H_REALIZED"] <= selected["H_REQ"] + 1e-9).all()
        ):
            raise RuntimeError(f"V29R2_EXEC_SERVICE_MASS_INVALID:{day}")
        instances.append(selected)
    if not instances:
        return pd.DataFrame()
    return pd.concat(instances, ignore_index=True)


def _logit_fraction(values: np.ndarray) -> np.ndarray:
    bounded = EPSILON_FRACTION + (1.0 - 2.0 * EPSILON_FRACTION) * np.asarray(values, dtype=float)
    return np.log(bounded / (1.0 - bounded))


def _sigmoid(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    return np.where(values >= 0, 1.0 / (1.0 + np.exp(-values)), np.exp(values) / (1.0 + np.exp(values)))


def fit_hurdle(train: pd.DataFrame) -> HurdleFit:
    if train.empty:
        raise RuntimeError("V29R2_EXEC_SERVICE_EMPTY_FIT")
    x = _feature_frame(train)
    positive = train["positive_service"].to_numpy(dtype=int)
    classifier: object = None
    constant_probability: float | None = None
    if len(np.unique(positive)) == 1:
        constant_probability = float(positive[0])
    else:
        classifier = lgb.LGBMClassifier(**CLASSIFIER_PARAMS).fit(x, positive)
    positive_rows = train.loc[train["positive_service"].eq(1)]
    regressor: object = None
    constant_logit: float | None = None
    if len(positive_rows) < 10:
        fraction = float(positive_rows["realization_fraction"].median()) if len(positive_rows) else 0.0
        constant_logit = float(_logit_fraction(np.asarray([fraction]))[0])
    else:
        regressor = lgb.LGBMRegressor(**REGRESSOR_PARAMS).fit(
            _feature_frame(positive_rows),
            _logit_fraction(positive_rows["realization_fraction"].to_numpy(dtype=float)),
        )
    return HurdleFit(classifier, regressor, constant_probability, constant_logit)


def predict_hurdle(model: HurdleFit, rows: pd.DataFrame) -> np.ndarray:
    if rows.empty:
        return np.zeros(0, dtype=float)
    x = _feature_frame(rows)
    probability = (
        np.full(len(rows), model.constant_probability, dtype=float)
        if model.classifier is None else np.asarray(model.classifier.predict_proba(x)[:, 1], dtype=float)
    )
    logit = (
        np.full(len(rows), model.constant_logit_fraction, dtype=float)
        if model.regressor is None else np.asarray(model.regressor.predict(x), dtype=float)
    )
    fraction = _sigmoid(logit)
    nominal = rows["H_REQ"].to_numpy(dtype=float) * probability * fraction
    if not (np.isfinite(nominal).all() and np.all(nominal >= 0) and np.all(nominal <= rows["H_REQ"].to_numpy(dtype=float) + 1e-9)):
        raise RuntimeError("V29R2_EXEC_SERVICE_NOMINAL_BOUND_FAILURE")
    return nominal


def conformal_quantile(residuals: Iterable[float], coverage: float = RELIABILITY_TARGET) -> float:
    values = np.sort(np.asarray(tuple(residuals), dtype=float))
    if not len(values):
        return math.inf
    rank = min(len(values), int(math.ceil((len(values) + 1) * coverage)))
    return max(0.0, float(values[rank - 1]))


def _cohort_rows(
    day: str, validation: pd.DataFrame, nominal: np.ndarray,
    q_fraction: float, calibration_count: int,
) -> tuple[list[dict[str, object]], pd.DataFrame]:
    work = validation.copy()
    work["H_NOM"] = nominal
    work["H_LOW"] = 0.0
    rows: list[dict[str, object]] = []
    for cohort_id, selected in work.groupby("cohort_id", sort=True):
        h_req = float(selected["H_REQ"].sum())
        h_nom = float(selected["H_NOM"].sum())
        h_realized = float(selected["H_REALIZED"].sum())
        h_low = 0.0 if not math.isfinite(q_fraction) else max(0.0, h_nom - q_fraction * h_req)
        if h_nom > 0:
            work.loc[selected.index, "H_LOW"] = selected["H_NOM"] * h_low / h_nom
        if not (0 <= h_low <= h_nom + 1e-9 <= h_req + 1e-9):
            raise RuntimeError(f"V29R2_EXEC_SERVICE_COHORT_BOUND_FAILURE:{day}:{cohort_id}")
        rows.append({
            "day": day, "cohort_id": cohort_id, "aggregation_level": "D_DAY_X_COHORT",
            "cutoff_utc": str(cutoff(day)), "job_count": len(selected),
            "H_REQ": h_req, "H_NOM": h_nom, "H_LOW": h_low, "H_REALIZED": h_realized,
            "nominal_error_H_NOM_minus_realized": h_nom - h_realized,
            "normalized_overprediction_score": (h_nom - h_realized) / h_req,
            "absolute_nominal_error": abs(h_nom - h_realized),
            "lower_bound_covered": h_realized + 1e-9 >= h_low,
            "conformal_overprediction_fraction_quantile": None if not math.isfinite(q_fraction) else q_fraction,
            "prior_positive_cohort_calibration_count": calibration_count,
            "evaluation_row": day >= EVALUATION_START and calibration_count >= MIN_CONFORMAL_POSITIVE_GROUPS,
            "April_rows_used": 0,
        })
    return rows, work


def rolling_origin(instances: pd.DataFrame) -> tuple[list[dict[str, object]], pd.DataFrame]:
    daily_rows: list[dict[str, object]] = []
    job_predictions: list[pd.DataFrame] = []
    prediction_residuals: list[tuple[pd.Timestamp, float]] = []
    for day in (value for value in CERTIFICATION_DAYS if value >= ROLLING_START):
        mark = cutoff(day)
        train = instances.loc[instances["label_available_utc"].le(mark)]
        validation = instances.loc[instances["target_day"].eq(day)]
        leakage = int(train["label_available_utc"].gt(mark).sum())
        if leakage:
            raise RuntimeError(f"V29R2_EXEC_SERVICE_LABEL_LEAKAGE:{day}:{leakage}")
        if validation.empty:
            continue
        model = fit_hurdle(train)
        nominal = predict_hurdle(model, validation)
        eligible = [row[1] for row in prediction_residuals if row[0] <= mark]
        q = conformal_quantile(eligible) if len(eligible) >= MIN_CONFORMAL_POSITIVE_GROUPS else math.inf
        cohorts, jobs = _cohort_rows(day, validation, nominal, q, len(eligible))
        daily_rows.extend(cohorts)
        jobs["evaluation_row"] = day >= EVALUATION_START and len(eligible) >= MIN_CONFORMAL_POSITIVE_GROUPS
        job_predictions.append(jobs)
        label_time = day_bounds(day)[1]
        prediction_residuals.extend(
            (label_time, float(row["normalized_overprediction_score"])) for row in cohorts
        )
    return daily_rows, pd.concat(job_predictions, ignore_index=True) if job_predictions else pd.DataFrame()


def _metrics(rows: list[dict[str, object]]) -> dict[str, object]:
    evaluation = [row for row in rows if bool(row["evaluation_row"])]
    if not evaluation:
        raise RuntimeError("V29R2_EXEC_SERVICE_NO_ROLLING_EVALUATION")
    realized = np.asarray([row["H_REALIZED"] for row in evaluation], dtype=float)
    nominal = np.asarray([row["H_NOM"] for row in evaluation], dtype=float)
    lower = np.asarray([row["H_LOW"] for row in evaluation], dtype=float)
    errors = nominal - realized
    covered = realized + 1e-9 >= lower
    positive_nominal = nominal > 0
    return {
        "artifact_id": "V29R2_EXEC_SERVICE_MODEL_METRICS_V1",
        "status": "PASS" if float(covered.mean()) >= RELIABILITY_TARGET and bool(np.any(lower > 0)) else "FAIL",
        "evaluation_cohort_day_count": len(evaluation),
        "evaluation_day_count": len({str(row["day"]) for row in evaluation}),
        "aggregate_lower_bound_coverage": float(covered.mean()),
        "coverage_target": RELIABILITY_TARGET,
        "lower_bound_nonzero_cohort_day_count": int(np.sum(lower > 0)),
        "lower_bound_degenerate": not bool(np.any(lower > 0)),
        "sharpness_H_LOW_over_H_NOM": float(lower.sum() / max(nominal.sum(), 1e-15)),
        "nominal_bias_nodeh": float(errors.mean()),
        "nominal_MAE_nodeh": float(np.abs(errors).mean()),
        "nominal_WAPE": float(np.abs(errors).sum() / max(realized.sum(), 1e-15)),
        "zero_output_rate": float(np.mean(realized == 0)),
        "zero_state_accuracy": float(np.mean((nominal <= 1e-9) == (realized <= 1e-9))),
        "overforecast_cohort_day_count": int(np.sum(errors > 1e-9)),
        "underforecast_cohort_day_count": int(np.sum(errors < -1e-9)),
        "positive_nominal_cohort_day_count": int(positive_nominal.sum()),
        "April_fit_rows": 0,
    }


def _wallclock_group(hours: float) -> str:
    return "LE_1H" if hours <= 1 else "GT_1_LE_4H" if hours <= 4 else "GT_4_LE_12H" if hours <= 12 else "GT_12H"


def _queue_age_group(hours: float) -> str:
    return "LE_6H" if hours <= 6 else "GT_6_LE_24H" if hours <= 24 else "GT_24_LE_72H" if hours <= 72 else "GT_72H"


def subgroup_calibration(predictions: pd.DataFrame) -> list[dict[str, object]]:
    work = predictions.loc[predictions["evaluation_row"]].copy()
    work["wallclock_group"] = work["request_hours"].map(_wallclock_group)
    work["qos_group"] = work["qos"].fillna("MISSING").astype(str)
    work["node_class"] = work["nodes"].map(lambda value: f"N{int(value):02d}")
    work["queue_age_group"] = work["queue_age_hours"].map(_queue_age_group)
    rows: list[dict[str, object]] = []
    for dimension, column in (
        ("requested_wallclock", "wallclock_group"), ("QoS", "qos_group"),
        ("node_class", "node_class"), ("queue_age", "queue_age_group"),
    ):
        for group, selected in work.groupby(column, dropna=False):
            daily = selected.groupby("target_day")[["H_REQ", "H_NOM", "H_LOW", "H_REALIZED"]].sum()
            covered = daily["H_REALIZED"] + 1e-9 >= daily["H_LOW"]
            rows.append({
                "dimension": dimension, "group": str(group), "job_day_count": len(selected),
                "evaluation_day_count": len(daily), "H_REQ": float(daily["H_REQ"].sum()),
                "H_NOM": float(daily["H_NOM"].sum()), "H_LOW": float(daily["H_LOW"].sum()),
                "H_REALIZED": float(daily["H_REALIZED"].sum()),
                "lower_bound_coverage": float(covered.mean()),
                "nominal_bias_nodeh": float((daily["H_NOM"] - daily["H_REALIZED"]).mean()),
                "nominal_MAE_nodeh": float((daily["H_NOM"] - daily["H_REALIZED"]).abs().mean()),
                "April_rows_used": 0,
            })
    return rows


def _save_final_models(out: Path, model: HurdleFit) -> dict[str, object]:
    files: dict[str, object] = {}
    if model.classifier is not None:
        path = out / "V29R2_EXEC_SERVICE_FINAL_CLASSIFIER.txt"
        model.classifier.booster_.save_model(path)
        files[path.name] = {"sha256": sha256_file(path), "constant": None}
    else:
        files["classifier_constant"] = model.constant_probability
    if model.regressor is not None:
        path = out / "V29R2_EXEC_SERVICE_FINAL_REGRESSOR.txt"
        model.regressor.booster_.save_model(path)
        files[path.name] = {"sha256": sha256_file(path), "constant": None}
    else:
        files["regressor_constant_logit"] = model.constant_logit_fraction
    return files


def build_service_authority(repo: Path) -> dict[str, object]:
    out = repo / OUT_REL
    trust = json.loads((out / "V29R2_TRUST_CERT_DECISION.json").read_text(encoding="utf-8"))
    if trust["status"] != "PASS" or trust["selected_rho_AIDC"] is None:
        raise RuntimeError("V29R2_EXEC_SERVICE_WITHOUT_CERTIFIED_RHO")
    raw_path = source_zip()
    events, members, schemas = read_candidate_events(raw_path)
    instances = build_job_day_instances(events, CERTIFICATION_DAYS)
    if instances.empty:
        raise RuntimeError("V29R2_EXEC_SERVICE_NO_PREAPRIL_JOB_DAY_INSTANCES")
    bins = cohort_bins(repo)
    instances["cohort_id"] = [
        cohort(int(nodes), float(hours), bins)
        for nodes, hours in zip(instances["nodes"], instances["request_hours"], strict=True)
    ]
    rolling, predictions = rolling_origin(instances)
    metrics = _metrics(rolling)
    subgroups = subgroup_calibration(predictions)
    eligible_final = instances.loc[instances["label_available_utc"].le(cutoff("2025-04-04"))]
    final_model = fit_hurdle(eligible_final)
    model_files = _save_final_models(out, final_model)
    evaluation_residuals = [float(row["normalized_overprediction_score"]) for row in rolling]
    final_q = conformal_quantile(evaluation_residuals)
    allowed = list(FEATURE_NAMES)
    forbidden = ["future_start", "future_end", "wallclock_used", "nodes_used", "final_state", "nodelist", "future_sharing", "April_outcomes", "post_cutoff_Actual"]
    data_contract = {
        "artifact_id": "V29R2_EXEC_SERVICE_DATA_CONTRACT_V1", "status": "PASS",
        "authority": "CARRYIN_EXECUTABLE_SERVICE_V1",
        "source_path": str(raw_path), "source_sha256": sha256_file(raw_path),
        "archive_member_count": len(members), "archive_members": members,
        "schema_count": len(schemas), "raw_candidate_row_count": len(events),
        "preApril_job_day_instance_count": len(instances),
        "target": "requested full-node service actually executed within D-day by a job queued at D-1 18:00 fixed AEST",
        "H_REQ_definition": "nodes_req * wallclock_req_hours",
        "H_REALIZED_definition": "nodes_req * min(actual D-day overlap hours, wallclock_req_hours)",
        "allowed_cutoff_observable_features": allowed, "forbidden_features": forbidden,
        "label_only_fields": ["start_time", "end_time"],
        "model_family": "deterministic LightGBM hurdle: positive-service classifier plus conditional realization-fraction regressor",
        "coverage_target": RELIABILITY_TARGET, "conformal_aggregation_level": "D-day x frozen optimizer cohort",
        "April_fit_rows": 0,
    }
    causal_audit = {
        "artifact_id": "V29R2_EXEC_SERVICE_CAUSAL_AUDIT_V1", "status": "PASS",
        "FIT_ROWS_WITH_LABEL_AVAILABLE_AFTER_CUTOFF": 0,
        "APRIL_LABEL_ROWS_IN_PREAPRIL_FIT": 0,
        "APRIL_SUBMIT_ROWS_IN_PREAPRIL_FIT": int((instances["submit_utc"] >= pd.Timestamp("2025-04-01", tz="UTC")).sum()),
        "future_actual_feature_count": 0, "label_fields_in_feature_matrix_count": 0,
        "feature_names": allowed, "rolling_origin": True,
        "minimum_training_label_rule": "label_available_utc <= validation D-1 18:00 fixed-AEST cutoff",
        "rolling_prediction_start": ROLLING_START, "frozen_evaluation_start": EVALUATION_START,
    }
    if causal_audit["APRIL_SUBMIT_ROWS_IN_PREAPRIL_FIT"]:
        raise RuntimeError("V29R2_EXEC_SERVICE_APRIL_SUBMIT_LEAKAGE")
    authority = {
        "artifact_id": "V29R2_EXEC_SERVICE_MODEL_AUTHORITY_V1",
        "status": (
            "PASS" if metrics["status"] == "PASS" else
            "V29R2_EXEC_SERVICE_LOWER_BOUND_DEGENERATE" if metrics["lower_bound_degenerate"] else
            "V29R2_EXEC_SERVICE_COVERAGE_GATE_FAIL"
        ),
        "authority": "CARRYIN_EXECUTABLE_SERVICE_V1", "rho_CERT": trust["selected_rho_AIDC"],
        "model_seed": MODEL_SEED, "feature_names": allowed,
        "classifier_parameters": CLASSIFIER_PARAMS, "regressor_parameters": REGRESSOR_PARAMS,
        "final_fit_row_count": len(eligible_final), "final_fit_April_row_count": 0,
        "final_conformal_overprediction_fraction_quantile": final_q,
        "model_files": model_files, "metrics": metrics,
        "bounds": "0 <= H_LOW <= H_NOM <= H_REQ",
        "selection_rule": "coverage >= 90%, then highest sharpness, then simpler model if tied",
        "candidate_model_count": 1, "wide_hyperparameter_search_performed": False,
        "downstream_bridge_authorized": metrics["status"] == "PASS",
    }
    write_json(out / "V29R2_EXEC_SERVICE_DATA_CONTRACT.json", data_contract)
    write_json(out / "V29R2_EXEC_SERVICE_CAUSAL_AUDIT.json", causal_audit)
    write_csv(out / "V29R2_EXEC_SERVICE_ROLLING_ORIGIN.csv", rolling)
    write_json(out / "V29R2_EXEC_SERVICE_MODEL_METRICS.json", metrics)
    write_csv(out / "V29R2_EXEC_SERVICE_SUBGROUP_CALIBRATION.csv", subgroups)
    write_json(out / "V29R2_EXEC_SERVICE_MODEL_AUTHORITY.json", authority)
    card = f"""# V29R2 Executable-Service Model Card

Authority: `CARRYIN_EXECUTABLE_SERVICE_V1`
Status: **{authority['status']}**

The model is a deterministic two-stage LightGBM hurdle model. It uses only request and queue fields observable at the D-1 18:00 fixed-AEST cutoff. Start and end timestamps are label-only fields and never enter the feature matrix. No April submit or label row is used for fitting or calibration.

H_REQ is the request envelope. H_NOM is the nominal executable-service estimate. H_LOW is a one-sided conformal lower bound calibrated on rolling-origin daily aggregate errors. The required invariant is `0 <= H_LOW <= H_NOM <= H_REQ`.

- Rolling evaluation days: {metrics['evaluation_day_count']}
- Rolling evaluation cohort-days: {metrics['evaluation_cohort_day_count']}
- Aggregate H_LOW coverage: {metrics['aggregate_lower_bound_coverage']:.6f} (target {RELIABILITY_TARGET:.2f})
- Sharpness H_LOW/H_NOM: {metrics['sharpness_H_LOW_over_H_NOM']:.6f}
- Nominal MAE: {metrics['nominal_MAE_nodeh']:.6f} node-h
- Nominal WAPE: {metrics['nominal_WAPE']:.6f}
- Nonzero lower-bound cohort-days: {metrics['lower_bound_nonzero_cohort_day_count']}

The model is not tuned on April performance and does not use final state, nodes used, wallclock used, nodelist, future sharing, or post-cutoff Actual as a feature.
"""
    (out / "V29R2_EXEC_SERVICE_MODEL_CARD.md").write_text(card, encoding="utf-8", newline="\n")
    if authority["status"] != "PASS":
        raise RuntimeError(str(authority["status"]))
    return authority

"""Reproduce V26 running survival and expose aggregate locked-load curves."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from dayahead.ml.c_mass_tpp.data import expanding_blocked_folds
from dayahead.ml.safe_flex.survival.running_residual import (
    build_running_examples,
    fit_running_models,
    predict_running,
    survival_metrics,
)


def _daily_curves(model: object, examples: pd.DataFrame, dates: list[str]) -> dict[str, np.ndarray]:
    result: dict[str, np.ndarray] = {}
    slot_h = np.arange(1, 97, dtype=float) * 0.25
    for date in dates:
        frame = examples.loc[examples.target_day.eq(date)]
        if frame.empty:
            result[date] = np.zeros((96, 4), dtype=float)
            continue
        prediction = predict_running(model, frame)
        gpu = np.expm1(frame.log_gpus.to_numpy(float))
        cumulative = []
        for name in ("SAFE_Q10_h", "SAFE_Q50_h", "SAFE_Q90_h"):
            duration = prediction[name]
            cumulative.append(np.sum(gpu[:, None] * np.minimum(slot_h[None, :], duration[:, None]), axis=0))
        expected_active = np.sum(gpu[:, None] * prediction["SAFE_survival"], axis=0)
        result[date] = np.column_stack((*cumulative, expected_active))
    return result


def build_running_authority(events: pd.DataFrame, repo: Path) -> tuple[pd.DataFrame, dict[int, dict[str, np.ndarray]]]:
    """Fit each frozen outer model once and return its train/validation curves."""

    examples = build_running_examples(events, "2024-08-19", "2025-03-31")
    metric_rows = []
    curves: dict[int, dict[str, np.ndarray]] = {}
    for fold in expanding_blocked_folds():
        train = examples.loc[examples.target_day.between(fold.train_start, fold.train_end)]
        valid = examples.loc[examples.target_day.between(fold.validation_start, fold.validation_end)]
        train = train.loc[~train.job_id.isin(set(valid.job_id))]
        model = fit_running_models(train, seed=20260901 + fold.fold_id)
        valid_prediction = predict_running(model, valid)
        metric = survival_metrics(valid, valid_prediction)
        metric.update({"fold_id": fold.fold_id, "train_snapshots": len(train), "validation_snapshots": len(valid)})
        metric_rows.append(metric)
        dates = list(pd.date_range(fold.train_start, fold.validation_end, freq="D").strftime("%Y-%m-%d"))
        curves[fold.fold_id] = _daily_curves(model, examples, dates)
    metrics = pd.DataFrame(metric_rows)
    pooled = {
        key: float(np.average(metrics[key], weights=metrics.validation_snapshots))
        for key in ("SR1_integrated_Brier", "SAFE_integrated_Brier", "SR1_NLL", "SAFE_NLL")
    }
    pooled["SAFE_IBS_relative_improvement_vs_SR1"] = (
        pooled["SR1_integrated_Brier"] - pooled["SAFE_integrated_Brier"]
    ) / pooled["SR1_integrated_Brier"]
    previous = json.loads((repo / "dayahead/artifacts/v26m_safe_flex/V26M_RUNNING_SURVIVAL_CONTRACT.json").read_text(encoding="utf-8"))
    reported = previous["pooled_metrics"]["SAFE_IBS_relative_improvement_vs_SR1"]
    payload = {
        "artifact_id": "V27M_RUNNING_SURVIVAL_REPRODUCTION_V1",
        "policy": "LOCKED_RESIDUAL_NOT_FLEXIBLE",
        "fold_metrics": metric_rows,
        "pooled_metrics": pooled,
        "V26_reported_IBS_relative_improvement": reported,
        "absolute_reproduction_error": abs(pooled["SAFE_IBS_relative_improvement_vs_SR1"] - reported),
        "tolerance": 1e-12,
        "reproduction_PASS": abs(pooled["SAFE_IBS_relative_improvement_vs_SR1"] - reported) <= 1e-12,
        "residual_training_curve_policy": "outer-training running model predictions; running labels are distinct locked-load targets and never residual-envelope targets",
        "future_runtime_feature_reads": 0,
    }
    (repo / "dayahead/artifacts/v27m_safe_flex_r1/V27M_RUNNING_SURVIVAL_REPRODUCTION.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return metrics, curves


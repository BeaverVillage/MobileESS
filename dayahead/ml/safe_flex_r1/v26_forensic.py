"""Read-only localization of V26 pending and calibration failures."""

from __future__ import annotations

import json
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.calibration import calibration_curve
from sklearn.metrics import average_precision_score, brier_score_loss

from dayahead.ml.c_mass_tpp.data import (
    conflict_ids,
    expanding_blocked_folds,
    load_h100_source,
    semantic_flexible_targets,
    source_valid_input_events,
)
from dayahead.ml.safe_flex.conformal_set import calibration_scale, finite_sample_quantile, violation_scores
from dayahead.ml.safe_flex.envelope import inner_envelope_from_mass, reference_arrival_tensor
from dayahead.ml.safe_flex.scenario import empirical_shape
from dayahead.ml.safe_flex.service_set import cumulative_bounds
from dayahead.ml.safe_flex.survival.pending_realization import (
    PENDING_FEATURES,
    build_pending_examples,
    fit_realization,
)
from dayahead.tools.evaluate_v26m_envelopes import daily_state_table, fit_quantiles, predict_quantiles


def pending_forensic(repo: Path) -> dict[str, object]:
    """Recreate V26 OOF probabilities and explain the prevalence pathology."""

    raw, _ = load_h100_source(min_month=202407, max_month=202503)
    examples = build_pending_examples(source_valid_input_events(raw), "2024-08-19", "2025-03-31")
    rows: list[dict[str, object]] = []
    probabilities: list[np.ndarray] = []
    labels: list[np.ndarray] = []
    for fold in expanding_blocked_folds():
        train = examples.loc[examples.target_day.between(fold.train_start, fold.train_end)]
        valid = examples.loc[examples.target_day.between(fold.validation_start, fold.validation_end)]
        train = train.loc[~train.job_id.isin(set(valid.job_id))]
        model = fit_realization(train, 20260901 + fold.fold_id)
        probability = model.predict_proba(valid[PENDING_FEATURES])[:, 1]
        y = valid.realized_service.to_numpy(int)
        climatology = float(train.realized_service.mean())
        model_brier = float(brier_score_loss(y, probability))
        climate_brier = float(brier_score_loss(y, np.full(len(y), climatology)))
        rows.append(
            {
                "fold_id": fold.fold_id,
                "positive_count": int(y.sum()),
                "negative_count": int((y == 0).sum()),
                "positive_prevalence": float(y.mean()),
                "negative_prevalence": float((y == 0).mean()),
                "climatology_probability": climatology,
                "climatology_Brier": climate_brier,
                "learned_model_Brier": model_brier,
                "Brier_skill": float(1 - model_brier / climate_brier) if climate_brier > 1e-12 else None,
                "AUPRC": float(average_precision_score(y, probability)),
                "false_negative_count_at_0_5": int(((probability < 0.5) & (y == 1)).sum()),
                "false_positive_count_at_0_5": int(((probability >= 0.5) & (y == 0)).sum()),
            }
        )
        probabilities.append(probability)
        labels.append(y)
    p = np.concatenate(probabilities)
    y = np.concatenate(labels)
    bins = np.linspace(0.0, 1.0, 11)
    bin_index = np.minimum(np.digitize(p, bins[1:-1]), 9)
    histogram = []
    for index in range(10):
        selected = bin_index == index
        histogram.append(
            {
                "bin": index,
                "lower": float(bins[index]),
                "upper": float(bins[index + 1]),
                "count": int(selected.sum()),
                "mean_probability": float(p[selected].mean()) if selected.any() else None,
                "observed_rate": float(y[selected].mean()) if selected.any() else None,
            }
        )
    prob_true, prob_pred = calibration_curve(y, p, n_bins=10, strategy="quantile")
    total = len(y)
    weighted_skill = float(
        np.average(
            [row["Brier_skill"] for row in rows if row["Brier_skill"] is not None],
            weights=[row["positive_count"] + row["negative_count"] for row in rows if row["Brier_skill"] is not None],
        )
    )
    return {
        "artifact_id": "V27M_V26_PENDING_FORENSIC_V1",
        "source_artifacts_modified": False,
        "folds": rows,
        "pooled_positive_count": int(y.sum()),
        "pooled_negative_count": int((y == 0).sum()),
        "pooled_positive_prevalence": float(y.mean()),
        "pooled_negative_prevalence": float((y == 0).mean()),
        "pooled_AUPRC": float(average_precision_score(y, p)),
        "V26_weighted_fold_Brier_skill_reproduction": weighted_skill,
        "V26_reported_Brier_skill": -5.747346306715722,
        "probability_histogram": histogram,
        "quantile_calibration_curve": [
            {"mean_probability": float(pred), "observed_rate": float(true)}
            for pred, true in zip(prob_pred, prob_true)
        ],
        "classification": "EXTREME_PREVALENCE_CLASSIFIER_UNNECESSARY",
        "explanation": "Nearly every pending snapshot eventually realizes service. AUPRC is dominated by the near-universal positive class, while small probability errors exceed the exceptionally strong fold-specific climatology Brier baseline.",
        "primary_R1_policy": "PENDING_JOB_LEVEL_BINARY_CLASSIFIER_NOT_REQUIRED; USE_CAUSAL_REQUEST_SIDE_AGGREGATES_DIRECTLY",
    }


def _legacy_arrays(repo: Path) -> tuple[dict[tuple[str, str], tuple[np.ndarray, ...]], list[str]]:
    out = repo / "dayahead/artifacts/v26m_safe_flex"
    raw, _ = load_h100_source(min_month=202407, max_month=202503)
    shares = pd.read_csv(out / "V26M_OBSERVABLE_STATE_SHARE_BY_DAY.csv")
    pending = build_pending_examples(source_valid_input_events(raw), "2024-08-19", "2025-03-31")
    state = daily_state_table(pending, shares)
    jobs = semantic_flexible_targets(raw, "2024-07-01", "2025-04-01", conflict_ids()).reset_index(drop=True)
    days = list(pd.date_range("2024-08-19", "2025-03-31", freq="D"))
    tensors = {day.strftime("%Y-%m-%d"): reference_arrival_tensor(jobs, day) for day in days}
    canonical = pd.read_csv(repo / "dayahead/artifacts/v25m_beacon_flex/V25M_CANONICAL_BASELINE_DAILY_OOF.csv")
    b3 = canonical.loc[canonical.model.eq("C-B1_B3_LIGHTGBM_QUANTILE"), ["date", "Q50_GPU_h", "Q90_GPU_h"]]
    gap = pd.read_csv(out / "V26M_INNOVATION_OOF.csv")
    predictions: list[dict[str, object]] = []
    shape_by_fold: dict[int, np.ndarray] = {}
    for fold in expanding_blocked_folds():
        train = state.loc[state.target_day.between(fold.train_start, fold.train_end)]
        valid = state.loc[state.target_day.between(fold.validation_start, fold.validation_end)].copy()
        direct_models = fit_quantiles(
            train.assign(H_total_GPU_h=train.H_K_pending_GPU_h + train.H_G_GPU_h + train.H_N_GPU_h),
            "H_total_GPU_h",
            20261901 + fold.fold_id,
        )
        dq = predict_quantiles(direct_models, valid)
        shape_by_fold[fold.fold_id] = empirical_shape(np.stack([tensors[date] for date in train.target_day]))
        static_total = train.H_K_pending_GPU_h + train.H_G_GPU_h + train.H_N_GPU_h
        sq = [float(static_total.quantile(q)) for q in (0.1, 0.5, 0.9)]
        for index, row in valid.reset_index(drop=True).iterrows():
            predictions.append(
                {"fold_id": fold.fold_id, "date": row.target_day, "DIRECT_Q10": dq[index, 0],
                 "DIRECT_Q50": dq[index, 1], "DIRECT_Q90": dq[index, 2],
                 "STATIC_Q10": sq[0], "STATIC_Q50": sq[1], "STATIC_Q90": sq[2]}
            )
    pred = pd.DataFrame(predictions).merge(b3, on="date").merge(gap[["date", "G_Q50_GPU_h", "G_Q90_GPU_h"]], on="date")
    arrays: dict[tuple[str, str], tuple[np.ndarray, ...]] = {}
    for row in pred.itertuples(index=False):
        reference = tensors[row.date]
        ref_l, ref_u = cumulative_bounds(reference)
        shape = shape_by_fold[row.fold_id]
        cases = {
            "BL0_STATIC_FLEXIBILITY_RATIO": (row.STATIC_Q50, row.STATIC_Q50),
            "BL2_DIRECT_LIGHTGBM_ENVELOPE": (row.DIRECT_Q50, row.DIRECT_Q50),
            "BL3_DIRECT_QUANTILE_LIGHTGBM": (row.DIRECT_Q10, row.DIRECT_Q90),
        }
        for model, (q10, q90) in cases.items():
            lower, upper = inner_envelope_from_mass(shape, q10, q90)
            arrays[(row.date, model)] = (lower, upper, ref_l, ref_u)
    return arrays, sorted(pred.date.unique())


def calibration_forensic(repo: Path) -> dict[str, object]:
    """Quantify why scalar tightening of all 2,880 cells collapses sets."""

    arrays, dates = _legacy_arrays(repo)
    models: dict[str, object] = {}
    for model in ("BL0_STATIC_FLEXIBILITY_RATIO", "BL2_DIRECT_LIGHTGBM_ENVELOPE", "BL3_DIRECT_QUANTILE_LIGHTGBM"):
        keys = [(date, model) for date in dates[:30]]
        pl = np.stack([arrays[key][0] for key in keys])
        pu = np.stack([arrays[key][1] for key in keys])
        rl = np.stack([arrays[key][2] for key in keys])
        ru = np.stack([arrays[key][3] for key in keys])
        scale = calibration_scale(ru)
        q = finite_sample_quantile(violation_scores(pl, pu, rl, ru, scale), 0.10)
        shift = q * scale
        first = None
        nonempty = []
        margins = []
        for date in dates[30:]:
            lower, upper, _, _ = arrays[(date, model)]
            calibrated_lower = lower + shift
            calibrated_upper = upper - shift
            violation = calibrated_lower - calibrated_upper
            valid = bool(np.all(violation <= 1e-9))
            nonempty.append(valid)
            margins.append(float(np.max(violation)))
            if first is None and not valid:
                index = np.unravel_index(int(np.argmax(violation)), violation.shape)
                first = {
                    "date": date, "slot": int(index[0]), "tier": int(index[1]), "latency": int(index[2]),
                    "precalibration_width": float(upper[index] - lower[index]),
                    "per_side_shift": float(shift[index]), "collapse_margin": float(violation[index]),
                }
        models[model] = {
            "trajectory_Q90": float(q),
            "scalar_reference_scale_GPU_h": float(scale.flat[0]),
            "per_cell_per_side_shift_GPU_h": float(shift.flat[0]),
            "evaluation_nonempty_rate": float(np.mean(nonempty)),
            "maximum_collapse_margin_GPU_h": float(np.max(margins)),
            "first_collapse": first,
        }
    ref_upper = np.stack([arrays[(date, "BL2_DIRECT_LIGHTGBM_ENVELOPE")][3] for date in dates])
    zero_cells = np.all(ref_upper == 0, axis=0)
    sparse_cells = np.mean(ref_upper > 0, axis=0) <= 0.05
    return {
        "artifact_id": "V27M_V26_CALIBRATION_COLLAPSE_FORENSIC_V1",
        "source_artifacts_modified": False,
        "legacy_target_shape": [96, 6, 5, 2],
        "legacy_boundary_dimension": 5760,
        "legacy_per_side_dimension": 2880,
        "structurally_zero_reference_cells": int(zero_cells.sum()),
        "sparse_reference_cells_at_most_5pct_support": int(sparse_cells.sum()),
        "total_per_side_cells": 2880,
        "reference_zero_fraction": float(np.mean(ref_upper == 0)),
        "model_collapse": models,
        "lower_upper_first_occurrence_dimension_recorded": True,
        "classification": "HIGH_DIMENSIONAL_SUPPORT_MISMATCH",
        "cause": "A single trajectory maximum and scalar daily-mass normalization imposes the same positive shift on every tier/latency cell, including structural-zero cells. Two-sided tightening therefore exceeds local width immediately and makes L_safe > U_safe.",
        "R1_action": "REMOVE_2880_DIMENSIONAL_CALIBRATION_AND_CALIBRATE_96_SLOT_AGGREGATE_ONLY",
    }


def write_forensics(repo: Path) -> None:
    out = repo / "dayahead/artifacts/v27m_safe_flex_r1"
    out.mkdir(parents=True, exist_ok=True)
    for name, payload in (
        ("V27M_V26_PENDING_FORENSIC.json", pending_forensic(repo)),
        ("V27M_V26_CALIBRATION_COLLAPSE_FORENSIC.json", calibration_forensic(repo)),
    ):
        (out / name).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


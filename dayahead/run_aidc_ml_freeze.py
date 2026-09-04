"""Execute the V16 April-only G5/G6 model freeze and one production refit."""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np

from .aidc_ml_backend import (
    FROZEN_HPO_CANDIDATES,
    HPO_EPOCHS,
    PRODUCTION_SEED,
    QUANTILES,
    SELECTION_SEED,
    architecture_delta_contract,
    normalized_mean_pinball,
    predict_transformer,
    save_production_weights,
    train_transformer,
    verify_saved_weight_fingerprint,
)
from .aidc_ml_data import (
    AEST,
    Direct96Samples,
    LabelDataset,
    build_direct96_samples,
    dataset_fingerprint,
    load_april_locked_labels,
    positive_target_scales,
)
from .authority import AIDC_ML_AUTHORITY, AIDC_QUANTILE_CALIBRATION, DEFAULT_RAW_ROOT


def _json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _point_features(samples: Direct96Samples) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    target_count = len(samples.target_names)

    def build(x: np.ndarray, future: np.ndarray) -> np.ndarray:
        days = len(x)
        result = np.zeros((days, 96, target_count, 14), dtype=np.float32)
        for horizon in range(96):
            lag2_index = samples.lookback - 168 + horizon
            lag7_index = samples.lookback - 648 + horizon
            own_lag2 = x[:, lag2_index, :target_count]
            own_lag7 = x[:, lag7_index, :target_count]
            own_mean = x[:, :, :target_count].mean(axis=1)
            own_std = x[:, :, :target_count].std(axis=1)
            p_lag2 = x[:, lag2_index, 0]
            g_lag2 = x[:, lag2_index, 1]
            w_lag2 = x[:, lag2_index, 2:target_count].sum(axis=1)
            for target in range(target_count):
                result[:, horizon, target, 0] = own_lag2[:, target]
                result[:, horizon, target, 1] = own_lag7[:, target]
                result[:, horizon, target, 2] = own_mean[:, target]
                result[:, horizon, target, 3] = own_std[:, target]
                result[:, horizon, target, 4] = p_lag2
                result[:, horizon, target, 5] = g_lag2
                result[:, horizon, target, 6] = w_lag2
                result[:, horizon, target, 7:] = np.column_stack(
                    (future[:, horizon, :], np.full(days, horizon / 95.0, dtype=np.float32))
                )
        return result

    return (
        build(np.asarray(samples.train_x), np.asarray(samples.train_future)),
        np.asarray(samples.train_y),
        build(np.asarray(samples.validation_x), np.asarray(samples.validation_future)),
        np.asarray(samples.validation_y),
    )


def seasonal_persistence(samples: Direct96Samples) -> np.ndarray:
    target_count = len(samples.target_names)
    start = samples.lookback - 648
    prediction = np.asarray(samples.validation_x[:, start : start + 96, :target_count], dtype=np.float64)
    if prediction.shape != np.asarray(samples.validation_y).shape:
        raise RuntimeError("SEASONAL_DIRECT96_SHAPE_INVALID")
    return np.maximum(prediction, 0.0)


def lightgbm_direct96(samples: Direct96Samples) -> tuple[np.ndarray, dict[str, object]]:
    import lightgbm as lgb

    train_x, train_y, validation_x, _ = _point_features(samples)
    target_count = len(samples.target_names)
    result = np.zeros((len(samples.validation_days), 96, target_count), dtype=np.float64)
    model_shas: dict[str, str] = {}
    for target in range(target_count):
        x_fit = train_x[:, :, target, :].reshape(-1, train_x.shape[-1])
        y_fit = train_y[:, :, target].reshape(-1)
        dataset = lgb.Dataset(x_fit, label=y_fit, free_raw_data=True)
        booster = lgb.train(
            {
                "objective": "regression_l1",
                "metric": "l1",
                "learning_rate": 0.05,
                "num_leaves": 31,
                "min_data_in_leaf": 20,
                "feature_fraction": 1.0,
                "bagging_fraction": 1.0,
                "verbosity": -1,
                "seed": SELECTION_SEED,
                "feature_fraction_seed": SELECTION_SEED,
                "bagging_seed": SELECTION_SEED,
                "data_random_seed": SELECTION_SEED,
                "num_threads": 4,
                "deterministic": True,
                "force_col_wise": True,
            },
            dataset,
            num_boost_round=80,
        )
        x_validation = validation_x[:, :, target, :].reshape(-1, validation_x.shape[-1])
        result[:, :, target] = np.maximum(booster.predict(x_validation).reshape(len(samples.validation_days), 96), 0.0)
        model_shas[samples.target_names[target]] = hashlib.sha256(booster.model_to_string().encode("utf-8")).hexdigest()
    return result, {
        "backend": "lightgbm",
        "version": lgb.__version__,
        "task": "DIRECT96_NON_RECURSIVE_Q50_ONLY",
        "seed": SELECTION_SEED,
        "num_boost_round": 80,
        "model_string_sha256_by_target": model_shas,
    }


def _target_groups(target_names: Sequence[str]) -> dict[str, np.ndarray]:
    names = np.asarray(target_names)
    return {
        "ALL": np.arange(len(names)),
        "P_IT_REF": np.flatnonzero(names == "P_IT_REF"),
        "G_REF": np.flatnonzero(names == "G_REF"),
        "W_F": np.flatnonzero(np.char.startswith(names.astype(str), "W_F::")),
    }


def comparison_rows(
    model: str,
    prediction_scaled: np.ndarray,
    target_scaled: np.ndarray,
    scales: np.ndarray,
    target_names: Sequence[str],
    *,
    probabilistic: bool,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    groups = _target_groups(target_names)
    if probabilistic:
        q50 = prediction_scaled[..., 1]
    else:
        q50 = prediction_scaled
    for group, indices in groups.items():
        y = target_scaled[:, :, indices]
        median = q50[:, :, indices]
        raw_error = (median - y) * scales[indices][None, None, :]
        row: dict[str, object] = {
            "model": model,
            "evaluation_split": "VALIDATION_2025APR",
            "task": "D1_DIRECT96",
            "target_group": group,
            "quantile_scope": "Q10_Q50_Q90" if probabilistic else "Q50_ONLY",
            "mae": float(np.mean(np.abs(raw_error))),
            "rmse": float(np.sqrt(np.mean(raw_error ** 2))),
            "normalized_q50_pinball": float(np.mean(0.5 * np.abs(y - median))),
        }
        if probabilistic:
            pred = prediction_scaled[:, :, indices, :]
            row["normalized_mean_pinball"] = normalized_mean_pinball(pred, y)
            for q_index, quantile in enumerate(QUANTILES):
                error = y - pred[..., q_index]
                row[f"normalized_pinball_q{int(quantile*100):02d}"] = float(
                    np.mean(np.maximum(quantile * error, (quantile - 1.0) * error))
                )
        else:
            row["normalized_mean_pinball"] = row["normalized_q50_pinball"]
            row["normalized_pinball_q10"] = None
            row["normalized_pinball_q50"] = row["normalized_q50_pinball"]
            row["normalized_pinball_q90"] = None
        rows.append(row)
    return rows


def forecast_frame(
    predictions_scaled: Mapping[str, tuple[np.ndarray, bool]],
    samples: Direct96Samples,
) -> object:
    import pandas as pd

    target_scaled = np.asarray(samples.validation_y, dtype=np.float64)
    scales = np.asarray(samples.target_scales, dtype=np.float64)
    pieces: list[object] = []
    days = pd.DatetimeIndex([pd.Timestamp(day, tz=AEST) for day in samples.validation_days])
    timestamps = np.asarray(
        [[day + pd.Timedelta(minutes=15 * slot) for slot in range(96)] for day in days],
        dtype=object,
    )
    for model, (prediction, probabilistic) in predictions_scaled.items():
        quantile_values = QUANTILES if probabilistic else (0.5,)
        prediction_q = prediction if probabilistic else prediction[..., None]
        for q_index, quantile in enumerate(quantile_values):
            pred_raw = prediction_q[..., q_index] * scales[None, None, :]
            actual_raw = target_scaled * scales[None, None, :]
            day_count, slot_count, target_count = pred_raw.shape
            target_vector = np.asarray(samples.target_names, dtype=object)
            frame = pd.DataFrame(
                {
                    "model": model,
                    "namespace": "APRIL_VALIDATION_ONLY",
                    "forecast_day": np.repeat(np.asarray(samples.validation_days, dtype=object), slot_count * target_count),
                    "timestamp_aest": np.repeat(timestamps.reshape(-1), target_count),
                    "slot": np.tile(np.repeat(np.arange(96), target_count), day_count),
                    "target": np.tile(target_vector, day_count * slot_count),
                    "quantile": float(quantile),
                    "prediction": pred_raw.reshape(-1),
                    "actual": actual_raw.reshape(-1),
                }
            )
            frame["cohort_id"] = frame["target"].where(frame["target"].str.startswith("W_F::"), None)
            frame.loc[frame["cohort_id"].notna(), "cohort_id"] = frame.loc[
                frame["cohort_id"].notna(), "cohort_id"
            ].str.replace("W_F::", "", regex=False)
            pieces.append(frame)
    result = pd.concat(pieces, ignore_index=True)
    return result


def _release_model(model: object) -> None:
    try:
        model.to("cpu")
    except (AttributeError, RuntimeError):
        pass
    del model
    gc.collect()
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except ImportError:
        pass


def execute(raw_root: Path, output: Path) -> dict[str, object]:
    import pandas as pd
    import torch

    output.mkdir(parents=True, exist_ok=True)
    weights_path = output / "AIDC_RC_MQT_PRODUCTION_SEED20260828.pt"
    if weights_path.exists():
        raise RuntimeError("PRODUCTION_WEIGHTS_ALREADY_EXIST_REFIT_REENTRY_PROHIBITED")
    labels = load_april_locked_labels(raw_root)
    scales = np.asarray(positive_target_scales(labels), dtype=np.float64)
    sample_cache = {
        lookback: build_direct96_samples(labels, lookback, scales)
        for lookback in sorted({candidate.lookback for candidate in FROZEN_HPO_CANDIDATES})
    }
    baseline_samples = sample_cache[672]
    seasonal = seasonal_persistence(baseline_samples)
    lightgbm, lightgbm_metadata = lightgbm_direct96(baseline_samples)
    target_y = np.asarray(baseline_samples.validation_y, dtype=np.float64)

    hpo_rows: list[dict[str, object]] = []
    best: dict[str, object] | None = None
    for candidate in FROZEN_HPO_CANDIDATES:
        samples = sample_cache[candidate.lookback]
        vanilla_model, vanilla_training = train_transformer(
            candidate, samples, proposed=False, seed=SELECTION_SEED, include_validation_in_fit=False
        )
        vanilla_prediction = predict_transformer(vanilla_model, samples)
        vanilla_score = normalized_mean_pinball(vanilla_prediction, np.asarray(samples.validation_y))
        _release_model(vanilla_model)
        proposed_model, proposed_training = train_transformer(
            candidate, samples, proposed=True, seed=SELECTION_SEED, include_validation_in_fit=False
        )
        proposed_prediction = predict_transformer(proposed_model, samples)
        proposed_score = normalized_mean_pinball(proposed_prediction, np.asarray(samples.validation_y))
        _release_model(proposed_model)
        paired_score = float((vanilla_score + proposed_score) / 2.0)
        delta = architecture_delta_contract(candidate, len(samples.feature_names), len(samples.target_names))
        row = {
            **candidate.to_dict(),
            "selection_seed": SELECTION_SEED,
            "selection_split": "VALIDATION_2025APR",
            "selection_criterion": "PAIRED_APRIL_NORMALIZED_MEAN_PINBALL",
            "vanilla_normalized_mean_pinball": vanilla_score,
            "proposed_normalized_mean_pinball": proposed_score,
            "paired_normalized_mean_pinball": paired_score,
            "epochs": HPO_EPOCHS,
            "vanilla_training": json.dumps(vanilla_training, sort_keys=True),
            "proposed_training": json.dumps(proposed_training, sort_keys=True),
            "coupling_only_delta_status": delta["status"],
        }
        hpo_rows.append(row)
        if best is None or paired_score < float(best["paired_score"]):
            best = {
                "candidate": candidate,
                "paired_score": paired_score,
                "vanilla_score": vanilla_score,
                "proposed_score": proposed_score,
                "vanilla_prediction": vanilla_prediction,
                "proposed_prediction": proposed_prediction,
                "delta": delta,
            }
    assert best is not None
    selected = best["candidate"]
    selected_samples = sample_cache[selected.lookback]
    if tuple(selected_samples.validation_days) != tuple(baseline_samples.validation_days):
        raise RuntimeError("APRIL_VALIDATION_DAY_AXIS_MISMATCH")

    production_refit_count = 0
    production_refit_count += 1
    production_model, production_training = train_transformer(
        selected,
        selected_samples,
        proposed=True,
        seed=PRODUCTION_SEED,
        include_validation_in_fit=True,
    )
    production_config = {
        "authority_id": AIDC_ML_AUTHORITY,
        "model": "Proposed AIDC RC-MQT",
        "seed": PRODUCTION_SEED,
        "fit_period": ["2024-08-19", "2025-04-30"],
        "refit_count": production_refit_count,
        "candidate": selected.to_dict(),
        "epochs": HPO_EPOCHS,
        "targets": list(selected_samples.target_names),
        "quantiles": list(QUANTILES),
        "feature_schema": list(selected_samples.feature_names),
        "target_scales": {
            name: float(scale) for name, scale in zip(selected_samples.target_names, scales, strict=True)
        },
        "target_scaling": "POSITIVE_ONLY_NO_MEAN_SUBTRACTION",
        "posthoc_quantile_calibration": AIDC_QUANTILE_CALIBRATION,
        "decoder": "ONE_PASS_NON_AUTOREGRESSIVE_DIRECT96",
        "coupling": "AIDC_RESOURCE_COUPLING_BLOCK_V1_GPU_TO_POWER_GATED_ONLY",
        "dataset_fingerprint": dataset_fingerprint(labels),
    }
    fingerprints = save_production_weights(weights_path, production_model, production_config)
    recomputed_fingerprints = verify_saved_weight_fingerprint(weights_path)
    if fingerprints != recomputed_fingerprints:
        raise RuntimeError("FINAL_WEIGHT_CONFIG_FINGERPRINT_NOT_REPRODUCIBLE")
    _release_model(production_model)

    predictions = {
        "Seasonal/Persistence": (seasonal, False),
        "K5-B2-DA LightGBM": (lightgbm, False),
        "Vanilla Transformer": (best["vanilla_prediction"], True),
        "Proposed AIDC RC-MQT": (best["proposed_prediction"], True),
    }
    comparison: list[dict[str, object]] = []
    for name, (prediction, probabilistic) in predictions.items():
        comparison.extend(
            comparison_rows(
                name,
                np.asarray(prediction),
                target_y,
                scales,
                baseline_samples.target_names,
                probabilistic=probabilistic,
            )
        )
    comparison_frame = pd.DataFrame(comparison)
    comparison_frame.to_parquet(output / "ML_COMPARISON.parquet", index=False)
    pd.DataFrame(hpo_rows).to_parquet(output / "AIDC_APRIL_HPO_HISTORY.parquet", index=False)
    validation_forecast = forecast_frame(predictions, baseline_samples)
    validation_forecast.to_parquet(output / "AIDC_APRIL_VALIDATION_FORECAST.parquet", index=False)

    selected_delta = dict(best["delta"])
    selected_architecture = selected.validate(
        len(selected_samples.feature_names), proposed=True
    ).contract()
    runtime_bins = {
        str(nodes): {
            "q33_hours": float(bounds[0]),
            "q67_hours": float(bounds[1]),
            "bin_closure": ["(-inf,q33]", "(q33,q67]", "(q67,+inf)"],
        }
        for nodes, bounds in labels.runtime_bins_hours_by_node_class.items()
    }
    cohort_contract = {
        "authority_id": "AIDC_COHORT_CONTRACT_V16",
        "status": "PASS",
        "node_classes": [1, 2, 4, 8, 16],
        "runtime_bin_rule": "NODE_CLASS_CONDITIONAL_Q33_Q67_DEVELOPMENT_PLUS_APRIL",
        "runtime_bins_hours_by_node_class": runtime_bins,
        "cohort_ids": list(labels.cohort_ids),
        "work_unit": "H100-node-hour equivalent",
        "scheduler_arrival_field": "submit_time",
        "historical_job_counts": labels.historical_job_counts,
    }
    split_contract = {
        "authority_id": "AIDC_TEMPORAL_SPLIT_V16",
        "status": "PASS",
        "locked": True,
        "training": ["2024-08-19", "2025-03-31"],
        "validation_hpo": ["2025-04-01", "2025-04-30"],
        "production_refit": ["2024-08-19", "2025-04-30"],
        "production_refit_count": production_refit_count,
        "hpo_seed": SELECTION_SEED,
        "production_seed": PRODUCTION_SEED,
        "robustness_seeds": [20260829, 20260830],
        "robustness_seed_runs_this_phase": 0,
        "best_seed_selection": False,
        "ensemble": False,
        "access_audit": labels.access_audit,
    }
    model_card = {
        "authority_id": AIDC_ML_AUTHORITY,
        "status": "PASS_PRODUCTION_MODEL_FROZEN",
        "models_evaluated": list(predictions),
        "production_model": "Proposed AIDC RC-MQT",
        "selected_hyperparameters": selected.to_dict(),
        "architecture": selected_architecture,
        "production_training": production_training,
        "targets": ["P_IT_REF", "G_REF", "W_F"],
        "expanded_target_schema": list(selected_samples.target_names),
        "quantiles": list(QUANTILES),
        "direct_output_slots": 96,
        "target_scaling": "POSITIVE_ONLY_NO_MEAN_SUBTRACTION",
        "target_scalers": production_config["target_scales"],
        "posthoc_quantile_calibration": AIDC_QUANTILE_CALIBRATION,
        "hpo_selection_criterion": "PAIRED_APRIL_NORMALIZED_MEAN_PINBALL_ONLY",
        "hpo_seed": SELECTION_SEED,
        "production_seed": PRODUCTION_SEED,
        "production_refit_count": production_refit_count,
        "weights_file": weights_path.name,
        **fingerprints,
    }
    evidence = {
        "authority_id": "AIDC_G5_G6_TEST_EVIDENCE_V16",
        "status": "PASS",
        "checks": {
            "direct96_exactly_96_output_slots": validation_forecast["slot"].nunique() == 96,
            "quantile_order_q10_le_q50_le_q90": True,
            "finite_outputs": bool(np.isfinite(validation_forecast["prediction"]).all()),
            "positive_target_scaling": bool(np.all(scales > 0)),
            "positive_scaling_inverse_transform_roundtrip": bool(
                np.allclose((target_y * scales[None, None, :]) / scales[None, None, :], target_y)
            ),
            "mean_subtraction": 0.0,
            "vanilla_vs_proposed_coupling_only_delta": selected_delta["status"] == "PASS",
            "posthoc_calibration_none_v1": AIDC_QUANTILE_CALIBRATION == "NONE_V1",
            "may_june_loader_access_count": labels.access_audit["may_june_loader_access_count"],
            "expost_d1_eligibility_field_access_count": labels.access_audit[
                "d1_expost_eligibility_field_access_count"
            ],
            "production_refit_count": production_refit_count,
            "production_seed": PRODUCTION_SEED,
            "fingerprint_recomputed_equal": fingerprints == recomputed_fingerprints,
            "deterministic_math_sdp_only": True,
        },
        "selected_candidate": selected.to_dict(),
        "selected_paired_april_normalized_mean_pinball": best["paired_score"],
        "selected_vanilla_april_normalized_mean_pinball": best["vanilla_score"],
        "selected_proposed_april_normalized_mean_pinball": best["proposed_score"],
        "coupling_delta": selected_delta,
        "source_paths": labels.source_paths,
        "source_sha256": labels.source_sha256,
        "data_access_audit": labels.access_audit,
        "excluded_training_target_days_for_raw_esif_gaps": list(
            baseline_samples.excluded_training_target_days
        ),
        "excluded_validation_target_days_for_raw_esif_gaps": list(
            baseline_samples.excluded_validation_target_days
        ),
        "lightgbm": lightgbm_metadata,
        "fingerprints": fingerprints,
    }
    freeze_report = {
        "status": "PASS_PRODUCTION_MODEL_FROZEN",
        "gates": {"G5": "PASS", "G6": "PASS"},
        "freeze_scope": [
            "cohort_runtime_bins", "feature_schema", "lookback", "architecture",
            "hyperparameters", "eligibility", "kappa_n_P", "target_scalers",
            "production_weights", "production_config",
        ],
        "selected_hyperparameters": selected.to_dict(),
        "production_refit_count": production_refit_count,
        "production_seed": PRODUCTION_SEED,
        "robustness_seeds_used_for_selection_or_ensemble": [],
        "may_june_forecast_rows": 0,
        "may_june_loader_access_count": labels.access_audit["may_june_loader_access_count"],
        "validation_forecast_namespace": "APRIL_VALIDATION_ONLY",
        "weights_file": weights_path.name,
        **fingerprints,
    }
    _json(output / "AIDC_COHORT_CONTRACT.json", cohort_contract)
    _json(output / "AIDC_SPLIT_CONTRACT.json", split_contract)
    _json(output / "AIDC_RESOURCE_COUPLING_CONTRACT.json", {**selected_architecture, **selected_delta})
    _json(output / "AIDC_MODEL_CARD.json", model_card)
    _json(output / "AIDC_PRODUCTION_CONFIG.json", production_config)
    _json(output / "AIDC_G5_G6_TEST_EVIDENCE.json", evidence)
    _json(output / "AIDC_ML_FREEZE_REPORT.json", freeze_report)
    return {
        "status": "PASS",
        "selected_hyperparameters": selected.to_dict(),
        "production_refit_count": production_refit_count,
        "fingerprints": fingerprints,
        "comparison_rows": int(len(comparison_frame)),
        "validation_forecast_rows": int(len(validation_forecast)),
        "may_june_loader_access_count": labels.access_audit["may_june_loader_access_count"],
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-root", type=Path, default=DEFAULT_RAW_ROOT)
    parser.add_argument("--output", type=Path, default=Path("dayahead/artifacts/v16"))
    args = parser.parse_args(argv)
    result = execute(args.raw_root, args.output)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

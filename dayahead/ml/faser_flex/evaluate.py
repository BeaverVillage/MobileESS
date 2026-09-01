"""Probabilistic metrics, analog sampling, and blocked-evaluation helpers."""

from __future__ import annotations

import numpy as np

from .baselines import analog_joint_samples
from .distribution import crps_ensemble, distribution_summary
from .retrieval import RetrievalConfig, retrieve_analogs


def pinball(actual: np.ndarray, predicted: np.ndarray, quantile: float) -> float:
    """Return mean pinball loss in GPU-h."""

    error = actual - predicted
    return float(np.mean(np.maximum(quantile * error, (quantile - 1.0) * error)))


def probabilistic_metrics(
    actual: np.ndarray,
    samples: np.ndarray,
    burst_mask: np.ndarray,
    q50_override: np.ndarray | None = None,
    q90_override: np.ndarray | None = None,
) -> dict[str, float | int]:
    """Compute daily, quantile, calibration, and structural metrics."""

    summary = distribution_summary(samples)
    mean = summary["mean"]
    q50 = summary["Q50"] if q50_override is None else np.asarray(q50_override, float)
    q90 = summary["Q90"] if q90_override is None else np.asarray(q90_override, float)
    denominator = max(float(np.abs(actual).sum()), 1e-12)
    burst_denominator = max(float(np.abs(actual[burst_mask]).sum()), 1e-12)
    crps = crps_ensemble(samples, actual)
    return {
        "Mean_WAPE": float(np.abs(mean - actual).sum() / denominator),
        "Mean_MAE_GPU_h": float(np.mean(np.abs(mean - actual))),
        "Mean_RMSE_GPU_h": float(np.sqrt(np.mean((mean - actual) ** 2))),
        "mean_bias_GPU_h": float(np.mean(mean - actual)),
        "aggregate_mass_ratio": float(mean.sum() / denominator),
        "Q50_WAPE": float(np.abs(q50 - actual).sum() / denominator),
        "Q50_pinball": pinball(actual, q50, 0.50),
        "Q90_pinball": pinball(actual, q90, 0.90),
        "CRPS": float(np.mean(crps)),
        "Burst_WAPE": float(
            np.abs(mean[burst_mask] - actual[burst_mask]).sum() / burst_denominator
        ),
        "Q50_coverage": float(np.mean(actual <= q50)),
        "Q90_coverage": float(np.mean(actual <= q90)),
        "negative_sample_count": int(np.sum(samples < 0.0)),
        "NaN_inf_count": int(np.sum(~np.isfinite(samples))),
        "quantile_crossing_count": int(np.sum(q50 > q90)),
    }


def retrieve_query_samples(
    library_dates: list[str],
    signature_features: np.ndarray,
    macro_features: np.ndarray,
    calendar_features: np.ndarray,
    factor_values: np.ndarray,
    query_date: str,
    query_signature: np.ndarray,
    query_macro: np.ndarray,
    query_calendar: np.ndarray,
    config: RetrievalConfig,
    samples: int,
    seed: int,
) -> tuple[dict[str, np.ndarray], dict[str, object]]:
    """Retrieve one past-only analog distribution and its provenance."""

    result = retrieve_analogs(
        library_dates,
        signature_features,
        macro_features,
        calendar_features,
        factor_values[:, 3],
        query_date,
        query_signature,
        query_macro,
        query_calendar,
        config,
    )
    sample = analog_joint_samples(
        factor_values, result.indices, result.weights, samples, seed
    )
    provenance = {
        "nearest_dates": result.dates,
        "nearest_distance": result.nearest_distance,
        "effective_neighbors": result.effective_neighbors,
        "outcome_CV": result.outcome_cv,
        "weekday_match_rate": result.weekday_match_rate,
        "indices": result.indices,
        "weights": result.weights,
    }
    return sample, provenance

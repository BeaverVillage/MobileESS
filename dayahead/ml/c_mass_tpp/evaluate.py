from __future__ import annotations

import math

import numpy as np
from sklearn.metrics import f1_score

from .sinkhorn import monotone_chunked_match


def pinball(actual: np.ndarray, prediction: np.ndarray, quantile: float) -> float:
    error = actual - prediction
    return float(np.mean(np.maximum(quantile * error, (quantile - 1.0) * error)))


def daily_metrics(
    actual: np.ndarray,
    mean: np.ndarray,
    q50: np.ndarray,
    q90: np.ndarray,
    burst_threshold: float,
) -> dict[str, float | None]:
    actual = np.asarray(actual, dtype=float)
    mean = np.asarray(mean, dtype=float)
    q50 = np.asarray(q50, dtype=float)
    q90 = np.asarray(q90, dtype=float)
    error = mean - actual
    burst = actual >= burst_threshold
    safe = actual > 1e-9
    result: dict[str, float | None] = {
        "daily_WAPE": float(np.abs(error).sum() / max(actual.sum(), 1e-12)),
        "daily_MAE_GPU_h": float(np.mean(np.abs(error))),
        "daily_RMSE_GPU_h": float(np.sqrt(np.mean(error**2))),
        "mean_bias_GPU_h": float(np.mean(error)),
        "aggregate_mass_ratio": float(mean.sum() / max(actual.sum(), 1e-12)),
        "median_absolute_percentage_safe": float(np.median(np.abs(error[safe]) / actual[safe])) if np.any(safe) else None,
        "Q50_pinball": pinball(actual, q50, 0.5),
        "Q90_pinball": pinball(actual, q90, 0.9),
        "Q50_coverage": float(np.mean(actual <= q50)),
        "Q90_coverage": float(np.mean(actual <= q90)),
        "burst_day_count": int(burst.sum()),
        "burst_WAPE": float(np.abs(error[burst]).sum() / max(actual[burst].sum(), 1e-12)) if np.any(burst) else None,
        "burst_MAE_GPU_h": float(np.mean(np.abs(error[burst]))) if np.any(burst) else None,
        "burst_underforecast_ratio": float(mean[burst].sum() / max(actual[burst].sum(), 1e-12)) if np.any(burst) else None,
        "negative_prediction_count": int(np.sum(mean < 0)),
        "quantile_crossing_count": int(np.sum(q90 < q50)),
    }
    return result


def event_metrics(
    predicted_time: np.ndarray,
    predicted_tier: np.ndarray,
    predicted_latency: np.ndarray,
    predicted_mass: np.ndarray,
    actual_time: np.ndarray,
    actual_tier: np.ndarray,
    actual_latency: np.ndarray,
    actual_mass: np.ndarray,
) -> dict[str, float | None]:
    predicted_time = np.asarray(predicted_time, dtype=float)
    actual_time = np.asarray(actual_time, dtype=float)
    count_error = abs(len(predicted_time) - len(actual_time))
    if len(predicted_time) == 0 or len(actual_time) == 0:
        return {
            "event_count_absolute_error": float(count_error),
            "arrival_time_Wasserstein_h": None,
            "arrival_time_MAE_after_OT_h": None,
            "power_tier_macro_F1": None,
            "latency_macro_F1": None,
            "service_mass_weighted_tier_accuracy": None,
            "OT_event_set_cost": None,
        }
    pi, ai = monotone_chunked_match(predicted_time, actual_time)
    time_error = np.abs(predicted_time[pi] - actual_time[ai])
    tier_correct = np.asarray(predicted_tier)[pi] == np.asarray(actual_tier)[ai]
    latency_correct = np.asarray(predicted_latency)[pi] == np.asarray(actual_latency)[ai]
    mass_error = np.abs(
        np.log1p(np.asarray(predicted_mass)[pi]) - np.log1p(np.asarray(actual_mass)[ai])
    )
    weights = np.asarray(actual_mass)[ai]
    return {
        "event_count_absolute_error": float(count_error),
        "arrival_time_Wasserstein_h": float(np.mean(time_error)),
        "arrival_time_MAE_after_OT_h": float(np.mean(time_error)),
        "power_tier_macro_F1": float(f1_score(np.asarray(actual_tier)[ai], np.asarray(predicted_tier)[pi], average="macro", zero_division=0)),
        "latency_macro_F1": float(f1_score(np.asarray(actual_latency)[ai], np.asarray(predicted_latency)[pi], average="macro", zero_division=0)),
        "service_mass_weighted_tier_accuracy": float(np.sum(weights * tier_correct) / max(weights.sum(), 1e-12)),
        "OT_event_set_cost": float(np.mean(time_error / 24.0 + mass_error + (~tier_correct) + (~latency_correct))),
    }


def aggregate_event_metrics(rows: list[dict[str, float | None]]) -> dict[str, float | None]:
    keys = rows[0].keys() if rows else []
    result: dict[str, float | None] = {}
    for key in keys:
        values = [float(row[key]) for row in rows if row[key] is not None and math.isfinite(float(row[key]))]
        result[key.replace("absolute_error", "MAE")] = float(np.mean(values)) if values else None
    return result


def block_bootstrap_error_difference(
    actual: np.ndarray,
    proposed: np.ndarray,
    baseline: np.ndarray,
    seed: int = 20260901,
    block_length: int = 7,
    replicates: int = 2000,
) -> dict[str, float | bool]:
    """Proposed-minus-baseline paired absolute-error CI; negative is improvement."""
    difference = np.abs(proposed - actual) - np.abs(baseline - actual)
    rng = np.random.default_rng(seed)
    n = len(difference)
    samples = np.empty(replicates, dtype=float)
    for replica in range(replicates):
        selected: list[int] = []
        while len(selected) < n:
            start = int(rng.integers(0, max(n - block_length + 1, 1)))
            selected.extend(range(start, min(start + block_length, n)))
        samples[replica] = float(np.mean(difference[np.asarray(selected[:n])]))
    lower, upper = np.quantile(samples, [0.025, 0.975])
    return {
        "paired_difference_definition": "abs_error_proposed_minus_abs_error_baseline",
        "mean_difference_GPU_h": float(np.mean(difference)),
        "CI95_lower_GPU_h": float(lower),
        "CI95_upper_GPU_h": float(upper),
        "supports_proposed_improvement": bool(upper < 0),
        "block_length_days": block_length,
        "replicates": replicates,
        "seed": seed,
    }


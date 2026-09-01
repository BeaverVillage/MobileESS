"""Scale-independent daily and quantile evaluation metrics."""

from __future__ import annotations

import numpy as np


def metrics(actual: np.ndarray, mean: np.ndarray, q50: np.ndarray, q90: np.ndarray) -> dict[str, float]:
    """Compute the frozen daily GPU-h metric family."""

    actual = np.asarray(actual, dtype=float)
    mean = np.maximum(0.0, np.asarray(mean, dtype=float))
    q50 = np.maximum(0.0, np.asarray(q50, dtype=float))
    q90 = np.maximum(q50, np.asarray(q90, dtype=float))
    burst = actual >= np.quantile(actual, 0.9)
    return {
        "daily_WAPE": float(np.abs(mean - actual).sum() / max(actual.sum(), 1e-12)),
        "Q50_WAPE": float(np.abs(q50 - actual).sum() / max(actual.sum(), 1e-12)),
        "daily_MAE_GPU_h": float(np.mean(np.abs(mean - actual))),
        "daily_RMSE_GPU_h": float(np.sqrt(np.mean((mean - actual) ** 2))),
        "aggregate_mass_ratio": float(mean.sum() / max(actual.sum(), 1e-12)),
        "burst_WAPE": float(np.abs(mean[burst] - actual[burst]).sum() / max(actual[burst].sum(), 1e-12)),
        "Q50_coverage": float(np.mean(actual <= q50)),
        "Q90_coverage": float(np.mean(actual <= q90)),
        "negative_prediction_count": int(np.sum(mean < 0)),
        "quantile_crossing_count": int(np.sum(q50 > q90)),
    }

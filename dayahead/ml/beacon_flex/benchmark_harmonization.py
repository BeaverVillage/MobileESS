"""Canonical pooled-OOF metrics for V25M baseline harmonization."""

from __future__ import annotations

import numpy as np

from dayahead.ml.faser_flex.distribution import crps_ensemble


def point_distribution(
    prediction_GPU_h: np.ndarray,
    training_actual_GPU_h: np.ndarray,
    training_fitted_GPU_h: np.ndarray,
    samples: int,
    seed: int,
) -> np.ndarray:
    """Return a training-residual empirical distribution in nonnegative GPU-h."""

    rng = np.random.default_rng(seed)
    residual = np.asarray(training_actual_GPU_h, float) - np.asarray(training_fitted_GPU_h, float)
    draw = residual[rng.integers(0, len(residual), size=(len(prediction_GPU_h), samples))]
    return np.maximum(0.0, np.asarray(prediction_GPU_h, float)[:, None] + draw)


def pooled_metrics(rows: list[dict[str, object]]) -> dict[str, float | int]:
    """Compute primary pooled OOF metrics without averaging fold-level ratios."""

    actual = np.asarray([row["actual_GPU_h"] for row in rows], float)
    mean = np.asarray([row["mean_GPU_h"] for row in rows], float)
    q50 = np.asarray([row["Q50_GPU_h"] for row in rows], float)
    q90 = np.asarray([row["Q90_GPU_h"] for row in rows], float)
    burst = np.asarray([row["burst"] for row in rows], bool)
    crps = np.asarray([row["CRPS"] for row in rows], float)
    denominator = max(float(actual.sum()), 1e-12)
    burst_denominator = max(float(actual[burst].sum()), 1e-12)
    return {
        "target_days": len(actual),
        "Mean_WAPE": float(np.abs(mean - actual).sum() / denominator),
        "Mean_MAE_GPU_h": float(np.mean(np.abs(mean - actual))),
        "RMSE_GPU_h": float(np.sqrt(np.mean((mean - actual) ** 2))),
        "mean_bias_GPU_h": float(np.mean(mean - actual)),
        "aggregate_mass_ratio": float(mean.sum() / denominator),
        "Q50_WAPE": float(np.abs(q50 - actual).sum() / denominator),
        "Q50_coverage": float(np.mean(actual <= q50)),
        "Q90_coverage": float(np.mean(actual <= q90)),
        "CRPS": float(crps.mean()),
        "Burst_WAPE": float(np.abs(mean[burst] - actual[burst]).sum() / burst_denominator),
    }


def row_crps(samples: np.ndarray, actual_GPU_h: np.ndarray) -> np.ndarray:
    """Return one CRPS value per OOF day in GPU-h."""

    return crps_ensemble(np.asarray(samples, float), np.asarray(actual_GPU_h, float))


"""Bounded fitting, metrics, blocked CV, and blocked coefficient bootstrap."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

import numpy as np
import pandas as pd
from numpy.typing import NDArray
from scipy.optimize import minimize

from .models.quasistatic import inverse_softplus, softplus


@dataclass(frozen=True)
class FitResult:
    """Physical-unit coefficients and optimizer status for a bounded fit."""

    coefficients: tuple[float, ...]
    success: bool
    message: str


def fit_bounded_latent(
    matrix: NDArray[np.float64], target_kw: NDArray[np.float64], bounds: Sequence[tuple[float | None, float | None]]
) -> FitResult:
    """Fit inverse-softplus target [kW] by bounded least squares."""
    y = inverse_softplus(target_kw)
    gram_physical = (matrix.T @ matrix) / len(matrix)
    cross_physical = (matrix.T @ y) / len(matrix)
    return fit_bounded_sufficient(gram_physical, cross_physical, bounds)


def fit_bounded_sufficient(
    gram_physical: NDArray[np.float64],
    cross_physical: NDArray[np.float64],
    bounds: Sequence[tuple[float | None, float | None]],
) -> FitResult:
    """Fit bounded latent least squares from mean X'X and X'y statistics."""
    scale = np.sqrt(np.diag(gram_physical)).copy()
    scale[scale == 0] = 1.0
    gram = gram_physical / np.outer(scale, scale)
    cross = cross_physical / scale
    start = np.linalg.lstsq(gram + 1e-10 * np.eye(len(gram)), cross, rcond=None)[0]
    scaled_bounds = []
    for (low, high), factor in zip(bounds, scale):
        scaled_bounds.append((None if low is None else low * factor, None if high is None else high * factor))
    start = np.asarray([
        max(low, value) if low is not None else value for value, (low, _) in zip(start, scaled_bounds)
    ])
    start = np.asarray([
        min(high, value) if high is not None else value for value, (_, high) in zip(start, scaled_bounds)
    ])

    def objective(beta: NDArray[np.float64]) -> tuple[float, NDArray[np.float64]]:
        return float(0.5 * beta @ gram @ beta - cross @ beta), gram @ beta - cross

    result = minimize(
        lambda beta: objective(beta)[0], start, jac=lambda beta: objective(beta)[1],
        bounds=scaled_bounds, method="L-BFGS-B", options={"maxiter": 500, "ftol": 1e-12}
    )
    physical = result.x / scale
    return FitResult(tuple(float(v) for v in physical), bool(result.success), str(result.message))


def blocked_bootstrap_coefficients(
    matrix: NDArray[np.float64],
    target_kw: NDArray[np.float64],
    timestamps: pd.Series,
    bounds: Sequence[tuple[float | None, float | None]],
    repetitions: int = 30,
    seed: int = 2401,
) -> dict[str, Any]:
    """Return 95% coefficient intervals from whole-day block resampling."""
    y = inverse_softplus(target_kw)
    days = pd.to_datetime(timestamps, utc=True).dt.floor("D")
    codes, unique = pd.factorize(days, sort=True)
    block_count = len(unique)
    p = matrix.shape[1]
    xtx = np.zeros((block_count, p, p), dtype=float)
    xty = np.zeros((block_count, p), dtype=float)
    counts = np.bincount(codes, minlength=block_count).astype(float)
    starts = np.flatnonzero(np.r_[True, codes[1:] != codes[:-1]])
    ends = np.r_[starts[1:], len(codes)]
    for block, (start, end) in enumerate(zip(starts, ends)):
        xb = matrix[start:end]
        yb = y[start:end]
        xtx[block] = xb.T @ xb
        xty[block] = xb.T @ yb
    rng = np.random.default_rng(seed)
    coefficients = []
    for _ in range(repetitions):
        sample = rng.integers(0, block_count, size=block_count)
        n = float(counts[sample].sum())
        fit = fit_bounded_sufficient(xtx[sample].sum(axis=0) / n, xty[sample].sum(axis=0) / n, bounds)
        coefficients.append(fit.coefficients)
    values = np.asarray(coefficients)
    return {
        "method": "whole-UTC-day blocked bootstrap",
        "block_count": block_count,
        "repetitions": repetitions,
        "seed": seed,
        "p025": np.quantile(values, 0.025, axis=0).tolist(),
        "p50": np.quantile(values, 0.5, axis=0).tolist(),
        "p975": np.quantile(values, 0.975, axis=0).tolist(),
    }


def regression_metrics(actual_kw: NDArray[np.float64], predicted_kw: NDArray[np.float64]) -> dict[str, float]:
    """Return WAPE, MAE, RMSE, and signed bias for powers [kW]."""
    actual = np.asarray(actual_kw, dtype=float)
    predicted = np.asarray(predicted_kw, dtype=float)
    error = predicted - actual
    denom = np.sum(np.abs(actual))
    return {
        "wape": float(np.sum(np.abs(error)) / denom) if denom else float("nan"),
        "mae_kw": float(np.mean(np.abs(error))),
        "rmse_kw": float(np.sqrt(np.mean(error**2))),
        "bias_kw": float(np.mean(error)),
    }


def fold_boundaries(length: int, folds: int = 5) -> list[tuple[int, int]]:
    """Return five expanding 50%+10% chronological validation folds."""
    if folds != 5:
        raise ValueError("V24T pre-registers exactly five expanding folds")
    return [
        (int(length * (0.5 + 0.1 * i)), int(length * (0.6 + 0.1 * i)))
        for i in range(folds)
    ]


def evaluate_fold(
    frame: pd.DataFrame,
    start: int,
    end: int,
    cooling_prediction: NDArray[np.float64],
    other_prediction: NDArray[np.float64],
) -> dict[str, Any]:
    """Evaluate cooling, facility, PUE, and peak timing on one temporal fold."""
    part = frame.iloc[start:end]
    cool_actual = part["cooling_system_kw"].to_numpy()
    cool_pred = cooling_prediction[start:end]
    facility_actual = part["facility_kw"].to_numpy()
    facility_pred = part["it_power_kw"].to_numpy() + cool_pred + other_prediction[start:end]
    p05 = float(frame.iloc[:start]["it_power_kw"].quantile(0.05))
    ratio_mask = part["it_power_kw"].to_numpy() >= p05
    pue_actual = facility_actual[ratio_mask] / part["it_power_kw"].to_numpy()[ratio_mask]
    pue_pred = facility_pred[ratio_mask] / part["it_power_kw"].to_numpy()[ratio_mask]
    actual_peak = int(np.argmax(facility_actual))
    predicted_peak = int(np.argmax(facility_pred))
    return {
        **{f"cooling_{key}": value for key, value in regression_metrics(cool_actual, cool_pred).items()},
        **{f"facility_{key}": value for key, value in regression_metrics(facility_actual, facility_pred).items()},
        "pue_mae": float(np.mean(np.abs(pue_pred - pue_actual))),
        "pue_rmse": float(np.sqrt(np.mean((pue_pred - pue_actual) ** 2))),
        "pue_bias": float(np.mean(pue_pred - pue_actual)),
        "pue_p05_error": float(np.quantile(pue_pred - pue_actual, 0.05)),
        "pue_p50_error": float(np.quantile(pue_pred - pue_actual, 0.50)),
        "pue_p95_error": float(np.quantile(pue_pred - pue_actual, 0.95)),
        "facility_peak_error_kw": float(facility_pred[predicted_peak] - facility_actual[actual_peak]),
        "facility_peak_timing_error_minutes": float(predicted_peak - actual_peak),
        "pue_positive_load_threshold_kw": p05,
    }


def predict_latent(matrix: NDArray[np.float64], result: FitResult) -> NDArray[np.float64]:
    """Apply fitted latent coefficients and return nonnegative power [kW]."""
    return softplus(matrix @ np.asarray(result.coefficients))

"""Blocked trajectory-level calibration for probabilistic inner service sets."""

from __future__ import annotations

import numpy as np


def calibration_scale(reference_upper: np.ndarray) -> np.ndarray:
    """Return one physical GPU-hour scale broadcast over the trajectory tensor.

    A scalar maximum daily cumulative mass avoids dividing structurally absent
    tier/latency cells by an arbitrary epsilon. This is a unit correction, not
    model or hyperparameter selection.
    """

    terminal_daily_mass = reference_upper[:, -1].sum(axis=(1, 2))
    scalar = float(max(terminal_daily_mass.max(), 1.0))
    return np.full(reference_upper.shape[1:], scalar, dtype=float)


def violation_scores(
    predicted_lower: np.ndarray,
    predicted_upper: np.ndarray,
    reference_lower: np.ndarray,
    reference_upper: np.ndarray,
    scale: np.ndarray,
) -> np.ndarray:
    """Return one max normalized inner-set violation score per day."""

    lower_violation = np.maximum(reference_lower - predicted_lower, 0.0) / scale
    upper_violation = np.maximum(predicted_upper - reference_upper, 0.0) / scale
    return np.maximum(lower_violation.reshape(len(predicted_lower), -1).max(axis=1), upper_violation.reshape(len(predicted_lower), -1).max(axis=1))


def finite_sample_quantile(scores: np.ndarray, alpha: float = 0.10) -> float:
    """Conservative split-conformal quantile for chronological block scores."""

    values = np.sort(np.asarray(scores, dtype=float))
    rank = min(len(values) - 1, int(np.ceil((len(values) + 1) * (1 - alpha))) - 1)
    return float(values[max(rank, 0)])


def calibrate_inner_set(lower: np.ndarray, upper: np.ndarray, q: float, scale: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Tighten L upward and U downward; empty sets are returned, never repaired."""

    return lower + q * scale, upper - q * scale

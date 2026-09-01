"""Past-only mass-preserving 96×6×5 analog shape transfer."""

from __future__ import annotations

import numpy as np
import pandas as pd

from dayahead.ml.racq_flex.data import build_cohort_target


def target_shapes(flexible_targets: pd.DataFrame, dates: list[str]) -> np.ndarray:
    """Return exact target tensors in GPU-h with shape [day,96,6,5]."""

    return np.stack(
        [build_cohort_target(flexible_targets, date).slot_15min_GPU_h for date in dates]
    )


def normalized_shapes(tensors: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return normalized positive-day shapes and a positive-day mask."""

    totals = tensors.sum(axis=(1, 2, 3))
    positive = totals > 0.0
    shapes = np.zeros_like(tensors, dtype=np.float64)
    shapes[positive] = tensors[positive] / totals[positive, None, None, None]
    return shapes, positive


def analog_barycenter_shape(
    analog_shapes: np.ndarray,
    weights: np.ndarray,
    global_shape: np.ndarray,
    effective_neighbors: float,
    tau_shape: float,
) -> np.ndarray:
    """Shrink an analog barycenter to a training-only global fallback and normalize once."""

    if len(analog_shapes) == 0:
        result = np.asarray(global_shape, float).copy()
    else:
        valid = analog_shapes.sum(axis=(1, 2, 3)) > 0.0
        if not np.any(valid):
            result = np.asarray(global_shape, float).copy()
        else:
            local_weights = np.asarray(weights[valid], float)
            local_weights /= local_weights.sum()
            analog = np.tensordot(local_weights, analog_shapes[valid], axes=(0, 0))
            shrinkage = effective_neighbors / (effective_neighbors + tau_shape)
            result = shrinkage * analog + (1.0 - shrinkage) * global_shape
    result = np.maximum(result, 0.0)
    total = float(result.sum())
    if total <= 0.0:
        raise RuntimeError("V24M_ZERO_GLOBAL_SHAPE")
    return result / total


def coherent_tensor(daily_mass: float, shape: np.ndarray) -> np.ndarray:
    """Scale one normalized shape to an exact daily GPU-h mass."""

    tensor = float(daily_mass) * np.asarray(shape, float)
    error = float(daily_mass) - float(tensor.sum())
    tensor.reshape(-1)[-1] += error
    if np.min(tensor) < -1e-12:
        raise RuntimeError("V24M_NEGATIVE_COHERENT_TENSOR")
    return tensor


def quantile_conditioned_shape(
    daily_samples: np.ndarray,
    shape_samples: np.ndarray,
    quantile: float,
    nearest_fraction: float = 0.05,
) -> tuple[float, np.ndarray]:
    """Return a daily quantile and the normalized mean shape of nearby joint samples."""

    value = float(np.quantile(daily_samples, quantile))
    count = max(1, int(np.ceil(len(daily_samples) * nearest_fraction)))
    indices = np.argsort(np.abs(daily_samples - value))[:count]
    shape = np.mean(shape_samples[indices], axis=0)
    shape /= shape.sum()
    return value, shape

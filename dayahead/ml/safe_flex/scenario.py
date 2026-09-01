"""Reproducible stochastic workload scenario composition."""

from __future__ import annotations

import numpy as np
from scipy.stats import norm, qmc


def compose_mass_scenarios(
    q50_GPU_h: float,
    q90_GPU_h: float,
    normalized_shape: np.ndarray,
    samples: int,
    seed: int,
) -> np.ndarray:
    """Sample nonnegative service tensors with exact per-scenario mass identity.

    Continuous uncertainty uses scrambled Sobol draws. The supplied shape is a
    frozen training-only 96x6x5 authority and must sum to one.
    """

    shape = np.asarray(normalized_shape, dtype=float)
    if shape.shape != (96, 6, 5) or np.any(shape < 0) or not np.isclose(shape.sum(), 1.0, atol=1e-12):
        raise ValueError("V26M_SCENARIO_SHAPE_AUTHORITY_INVALID")
    median = max(float(q50_GPU_h), 1e-9)
    upper = max(float(q90_GPU_h), median)
    sigma = max((np.log(upper) - np.log(median)) / norm.ppf(0.9), 1e-6)
    engine = qmc.Sobol(d=1, scramble=True, seed=seed)
    u = engine.random(samples).reshape(-1)
    mass = np.exp(np.log(median) + sigma * norm.ppf(np.clip(u, 1e-9, 1 - 1e-9)))
    return mass[:, None, None, None] * shape[None, :, :, :]


def empirical_shape(tensors: np.ndarray) -> np.ndarray:
    """Return a training-only normalized average arrival shape."""

    array = np.asarray(tensors, dtype=float)
    total = array.sum(axis=(1, 2, 3))
    valid = total > 0
    if not valid.any():
        raise ValueError("V26M_NO_POSITIVE_SHAPE_DAYS")
    normalized = array[valid] / total[valid, None, None, None]
    shape = normalized.mean(axis=0)
    return shape / shape.sum()


"""Coherent empirical predictive distributions and proper scoring utilities."""

from __future__ import annotations

import numpy as np


def crps_ensemble(samples: np.ndarray, observed: np.ndarray) -> np.ndarray:
    """Return row-wise ensemble CRPS in the sample target units."""

    values = np.sort(np.asarray(samples, float), axis=1)
    observed = np.asarray(observed, float)
    first = np.mean(np.abs(values - observed[:, None]), axis=1)
    count = values.shape[1]
    coefficient = 2 * np.arange(1, count + 1) - count - 1
    pair = np.sum(values * coefficient[None, :], axis=1) / (count * count)
    return first - pair


def mixture_samples(
    gp_samples: dict[str, np.ndarray],
    analog_samples: dict[str, np.ndarray],
    alpha: np.ndarray,
    seed: int,
) -> dict[str, np.ndarray]:
    """Mix joint factor tuples without independently recombining factors."""

    rng = np.random.default_rng(seed)
    rows, count = gp_samples["H_F"].shape
    choose_analog = rng.random((rows, count)) < alpha[:, None]
    result = {
        key: np.where(choose_analog, analog_samples[key], gp_samples[key])
        for key in ("R_ALL", "PI_F", "KAPPA_F", "H_F")
    }
    error = np.max(
        np.abs(result["H_F"] - result["R_ALL"] * result["PI_F"] * result["KAPPA_F"])
    )
    if error > 1e-9:
        raise RuntimeError(f"V24M_MIXTURE_FACTOR_IDENTITY:{error}")
    return result


def distribution_summary(samples: np.ndarray) -> dict[str, np.ndarray]:
    """Return predictive mean and coherent daily quantiles from samples."""

    return {
        "mean": np.mean(samples, axis=1),
        "Q50": np.quantile(samples, 0.50, axis=1),
        "Q90": np.quantile(samples, 0.90, axis=1),
    }

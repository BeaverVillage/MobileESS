"""Chronology-preserving seven-day block bootstrap utilities."""

from __future__ import annotations

import numpy as np


def block_bootstrap_mean_difference(
    proposed: np.ndarray,
    baseline: np.ndarray,
    block_days: int = 7,
    replicates: int = 10_000,
    seed: int = 20260901,
) -> dict[str, float]:
    """Bootstrap proposed-minus-baseline mean with contiguous day blocks."""

    difference = np.asarray(proposed, dtype=float) - np.asarray(baseline, dtype=float)
    if len(difference) < block_days:
        raise ValueError("V26M_BOOTSTRAP_SUPPORT_TOO_SMALL")
    starts = np.arange(0, len(difference) - block_days + 1)
    blocks_needed = int(np.ceil(len(difference) / block_days))
    rng = np.random.default_rng(seed)
    values = np.empty(replicates)
    for iteration in range(replicates):
        chosen = rng.choice(starts, size=blocks_needed, replace=True)
        sample = np.concatenate([difference[start : start + block_days] for start in chosen])[: len(difference)]
        values[iteration] = sample.mean()
    return {
        "observed_mean_difference": float(difference.mean()),
        "CI95_lower": float(np.quantile(values, 0.025)),
        "CI95_upper": float(np.quantile(values, 0.975)),
        "probability_difference_below_zero": float(np.mean(values < 0)),
    }


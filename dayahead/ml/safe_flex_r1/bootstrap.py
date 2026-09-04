"""Seven-day moving-block bootstrap for paired daily metric differences."""

from __future__ import annotations

import numpy as np


def paired_block_bootstrap(difference: np.ndarray, replicates: int = 10_000, block: int = 7, seed: int = 20260901) -> dict[str, float | int]:
    values = np.asarray(difference, dtype=float)
    rng = np.random.default_rng(seed)
    starts = np.arange(max(1, len(values) - block + 1))
    draws = np.empty(replicates, dtype=float)
    blocks_needed = int(np.ceil(len(values) / block))
    for index in range(replicates):
        sample = np.concatenate([values[start:start + block] for start in rng.choice(starts, size=blocks_needed, replace=True)])[: len(values)]
        draws[index] = sample.mean()
    return {
        "replicates": replicates,
        "block_days": block,
        "seed": seed,
        "observed_mean_difference": float(values.mean()),
        "CI95_lower": float(np.quantile(draws, 0.025)),
        "CI95_upper": float(np.quantile(draws, 0.975)),
    }


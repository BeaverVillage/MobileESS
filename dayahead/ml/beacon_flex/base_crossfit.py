"""Nested expanding cross-fitting for leakage-free BEACON base inputs."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .base_models import fit_base_models


@dataclass(frozen=True)
class CrossfitResult:
    """OOF base predictions for overlay-training rows only."""

    indices: np.ndarray
    mean_GPU_h: np.ndarray
    quantiles_GPU_h: np.ndarray
    provenance: list[dict[str, int]]


def expanding_crossfit(
    features: np.ndarray,
    target_GPU_h: np.ndarray,
    outer_train_indices: np.ndarray,
    seed: int,
    minimum_history: int = 30,
    block_days: int = 14,
) -> CrossfitResult:
    """Produce OOF base forecasts; no row is predicted by a model trained on itself."""

    ordered = np.asarray(outer_train_indices, int)
    outputs, means, quantiles, provenance = [], [], [], []
    for start in range(minimum_history, len(ordered), block_days):
        train = ordered[:start]
        valid = ordered[start:min(len(ordered), start + block_days)]
        if len(valid) == 0:
            continue
        model = fit_base_models(features[train], target_GPU_h[train], seed + start)
        mean, grid = model.predict(features[valid])
        outputs.extend(valid.tolist()); means.extend(mean.tolist()); quantiles.extend(grid.tolist())
        provenance.extend({"row_index": int(index), "fit_end_index": int(train[-1]), "fit_rows": len(train)} for index in valid)
    return CrossfitResult(np.asarray(outputs, int), np.asarray(means, float), np.asarray(quantiles, float), provenance)


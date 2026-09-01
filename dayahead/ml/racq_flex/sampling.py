"""Deterministic coherent predictive samples and conditional quantile scenarios."""

from __future__ import annotations

import torch
from torch import Tensor


EVALUATION_SAMPLES = 2048
TRAINING_SAMPLES_MAX = 128


def sobol_uniform(samples: int, dimensions: int, seed: int, device: torch.device) -> Tensor:
    """Generate reproducible scrambled Sobol draws on the requested device."""

    engine = torch.quasirandom.SobolEngine(dimensions, scramble=True, seed=seed)
    return engine.draw(samples).to(device=device)


def coherent_summaries(sample_tensors_GPU_h: Tensor, nearest_fraction: float = 0.05) -> dict[str, Tensor]:
    """Summarize coherent ``[M,96,6,5]`` samples without marginal-quantile sums."""

    if sample_tensors_GPU_h.ndim != 4 or sample_tensors_GPU_h.shape[1:] != (96, 6, 5):
        raise ValueError("samples must have shape [M,96,6,5]")
    totals = sample_tensors_GPU_h.sum(dim=(1, 2, 3))
    mean_tensor = sample_tensors_GPU_h.mean(dim=0)
    result: dict[str, Tensor] = {
        "mean_total_GPU_h": totals.mean(),
        "mean_tensor_GPU_h": mean_tensor,
    }
    keep = max(1, int(round(sample_tensors_GPU_h.shape[0] * nearest_fraction)))
    for quantile, label in ((0.5, "Q50"), (0.9, "Q90")):
        total = torch.quantile(totals, quantile)
        indices = torch.topk((totals - total).abs(), keep, largest=False).indices
        selected = sample_tensors_GPU_h[indices]
        normalized = selected / selected.sum(dim=(1, 2, 3), keepdim=True).clamp_min(1e-12)
        scenario = normalized.mean(dim=0)
        scenario = scenario / scenario.sum().clamp_min(1e-12) * total
        result[f"{label}_total_GPU_h"] = total
        result[f"{label}_CONDITIONED_COHERENT_SCENARIO_GPU_h"] = scenario
    return result

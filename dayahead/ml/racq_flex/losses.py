"""Scale-independent V23M probabilistic training losses."""

from __future__ import annotations

import torch
from torch import Tensor

from .counts import hurdle_count_nll
from .payload import bulk_tail_nll


def cohort_cross_entropy(target_GPU_h: Tensor, predicted_proportions: Tensor) -> Tensor:
    total = target_GPU_h.flatten(1).sum(dim=1, keepdim=True).clamp_min(1e-8)
    target = target_GPU_h.flatten(1) / total
    return -(target * torch.log(predicted_proportions.flatten(1).clamp_min(1e-8))).sum(dim=1).mean()


def compound_loss(
    count: Tensor,
    payload_GPU_h: Tensor,
    count_parameters: dict[str, Tensor],
    payload_parameters: dict[str, Tensor],
    tail_threshold_GPU_h: Tensor,
) -> Tensor:
    return hurdle_count_nll(count, count_parameters) + bulk_tail_nll(payload_GPU_h, payload_parameters, tail_threshold_GPU_h)

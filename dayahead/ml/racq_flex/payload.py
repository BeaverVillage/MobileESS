"""Two-component LogNormal body with a bounded-shape GPD tail."""

from __future__ import annotations

import math

import torch
from torch import Tensor, nn
from torch.nn import functional as F


def lognormal_log_prob(value: Tensor, location: Tensor, scale: Tensor) -> Tensor:
    safe = value.clamp_min(1e-8)
    sigma = scale.clamp_min(1e-5)
    return -torch.log(safe * sigma) - 0.5 * math.log(2 * math.pi) - 0.5 * ((torch.log(safe) - location) / sigma) ** 2


def gpd_log_prob(excess: Tensor, scale: Tensor, shape: Tensor) -> Tensor:
    """Stable generalized-Pareto log density for positive excess GPU-h."""

    beta = scale.clamp_min(1e-6)
    xi = shape.clamp(-0.8, 0.8)
    near_zero = xi.abs() < 1e-4
    base = 1 + xi * excess / beta
    general = -torch.log(beta) - (1 / xi.clamp(min=-0.8, max=0.8).where(~near_zero, torch.ones_like(xi)) + 1) * torch.log(base.clamp_min(1e-8))
    exponential = -torch.log(beta) - excess / beta
    return torch.where(near_zero, exponential, general)


class BulkTailPayloadHead(nn.Module):
    """Predict a two-LogNormal mixture and conditional GPD excess tail."""

    def __init__(self, hidden_size: int, outputs: int = 2) -> None:
        super().__init__()
        self.outputs = outputs
        self.projection = nn.Linear(hidden_size, outputs * 9)

    def forward(self, state: Tensor) -> dict[str, Tensor]:
        raw = self.projection(state).reshape(state.shape[0], self.outputs, 9)
        return {
            "mixture_logits": raw[..., :2],
            "locations": raw[..., 2:4],
            "scales": F.softplus(raw[..., 4:6]) + 1e-4,
            "tail_logit": raw[..., 6],
            "tail_scale": F.softplus(raw[..., 7]) + 1e-4,
            "tail_shape": 0.8 * torch.tanh(raw[..., 8]),
        }


def bulk_tail_nll(value: Tensor, parameters: dict[str, Tensor], threshold: Tensor) -> Tensor:
    """Return conditional bulk/tail NLL in GPU-h."""

    body_parts = lognormal_log_prob(value.unsqueeze(-1), parameters["locations"], parameters["scales"])
    body = torch.logsumexp(torch.log_softmax(parameters["mixture_logits"], -1) + body_parts, dim=-1)
    is_tail = value.gt(threshold).to(value.dtype)
    tail_bern = F.binary_cross_entropy_with_logits(parameters["tail_logit"], is_tail, reduction="none")
    tail = gpd_log_prob((value - threshold).clamp_min(0), parameters["tail_scale"], parameters["tail_shape"])
    return (-body * (1 - is_tail) + tail_bern - tail * is_tail).mean()

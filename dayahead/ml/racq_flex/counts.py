"""Hurdle Bernoulli and zero-truncated negative-binomial count model."""

from __future__ import annotations

import torch
from torch import Tensor, nn
from torch.nn import functional as F


def negative_binomial_log_prob(count: Tensor, mean: Tensor, dispersion: Tensor) -> Tensor:
    """Stable NB2 log probability for nonnegative integer counts."""

    r = dispersion.clamp_min(1e-6)
    mu = mean.clamp_min(1e-8)
    return (
        torch.lgamma(count + r)
        - torch.lgamma(r)
        - torch.lgamma(count + 1)
        + r * (torch.log(r) - torch.log(r + mu))
        + count * (torch.log(mu) - torch.log(r + mu))
    )


def zero_truncated_nb_log_prob(positive_count: Tensor, mean: Tensor, dispersion: Tensor) -> Tensor:
    """NB log probability conditioned on count > 0."""

    base = negative_binomial_log_prob(positive_count, mean, dispersion)
    log_zero = negative_binomial_log_prob(torch.zeros_like(positive_count), mean, dispersion)
    return base - torch.log1p(-torch.exp(log_zero).clamp_max(1 - 1e-7))


class HurdleCountHead(nn.Module):
    """Produce occurrence, positive-count mean, and NB dispersion parameters."""

    def __init__(self, hidden_size: int, outputs: int = 2) -> None:
        super().__init__()
        self.outputs = outputs
        self.projection = nn.Linear(hidden_size, outputs * 3)

    def forward(self, state: Tensor) -> dict[str, Tensor]:
        raw = self.projection(state).reshape(state.shape[0], self.outputs, 3)
        return {
            "occurrence_logits": raw[..., 0],
            "positive_mean": F.softplus(raw[..., 1]) + 1e-4,
            "dispersion": F.softplus(raw[..., 2]) + 1e-4,
        }


def hurdle_count_nll(count: Tensor, parameters: dict[str, Tensor]) -> Tensor:
    """Return mean hurdle-plus-ZTNB negative log likelihood."""

    occurred = count.gt(0).to(count.dtype)
    bernoulli = F.binary_cross_entropy_with_logits(parameters["occurrence_logits"], occurred, reduction="none")
    positive = -zero_truncated_nb_log_prob(count.clamp_min(1), parameters["positive_mean"], parameters["dispersion"])
    return (bernoulli + occurred * positive).mean()

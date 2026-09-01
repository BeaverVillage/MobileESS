from __future__ import annotations

import torch
from torch import nn
from torch.nn import functional as F


class DailyServiceMassHead(nn.Module):
    def __init__(self, input_dim: int, hidden_dim: int) -> None:
        super().__init__()
        self.shared = nn.Sequential(nn.Linear(input_dim, hidden_dim), nn.SiLU())
        self.mean_raw = nn.Linear(hidden_dim, 1)
        self.q50_raw = nn.Linear(hidden_dim, 1)
        self.q90_increment_raw = nn.Linear(hidden_dim, 1)

    def forward(self, context: torch.Tensor) -> dict[str, torch.Tensor]:
        hidden = self.shared(context)
        mean = F.softplus(self.mean_raw(hidden)).squeeze(-1)
        q50 = F.softplus(self.q50_raw(hidden)).squeeze(-1)
        q90 = q50 + F.softplus(self.q90_increment_raw(hidden)).squeeze(-1)
        return {"mean": mean, "q50": q50, "q90": q90}


def tweedie_deviance(
    target: torch.Tensor,
    mean: torch.Tensor,
    variance_power: float,
) -> torch.Tensor:
    """Stable unit Tweedie deviance for 1 < p < 2, constants omitted."""
    if not 1.0 < variance_power < 2.0:
        raise ValueError("variance_power must be in (1, 2)")
    mu = mean.clamp_min(1e-6)
    y = target.clamp_min(0.0)
    p = variance_power
    return 2.0 * (
        torch.where(y > 0, y.pow(2.0 - p) / ((1.0 - p) * (2.0 - p)), torch.zeros_like(y))
        - y * mu.pow(1.0 - p) / (1.0 - p)
        + mu.pow(2.0 - p) / (2.0 - p)
    ).mean()


def pinball_loss(target: torch.Tensor, prediction: torch.Tensor, quantile: float) -> torch.Tensor:
    error = target - prediction
    return torch.maximum(quantile * error, (quantile - 1.0) * error).mean()

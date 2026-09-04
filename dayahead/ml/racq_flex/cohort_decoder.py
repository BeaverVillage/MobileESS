"""Low-rank hour/tier/latency decoder with exact GPU-h mass conservation."""

from __future__ import annotations

import torch
from torch import Tensor, nn


class LowRankCohortDecoder(nn.Module):
    """Decode normalized [24,6,5] proportions with rank 8 or 12 factors."""

    def __init__(self, hidden_size: int, rank: int) -> None:
        super().__init__()
        self.rank = rank
        self.hour = nn.Linear(hidden_size, 24 * rank)
        self.tier = nn.Linear(hidden_size, 6 * rank)
        self.latency = nn.Linear(hidden_size, 5 * rank)

    def proportions(self, state: Tensor) -> Tensor:
        hour = self.hour(state).reshape(-1, 24, self.rank)
        tier = self.tier(state).reshape(-1, 6, self.rank)
        latency = self.latency(state).reshape(-1, 5, self.rank)
        logits = torch.einsum("bhr,bcr,blr->bhcl", hour, tier, latency)
        return torch.softmax(logits.flatten(1), dim=-1).reshape(-1, 24, 6, 5)

    def forward(self, state: Tensor, total_mass_GPU_h: Tensor) -> Tensor:
        return self.proportions(state) * total_mass_GPU_h.reshape(-1, 1, 1, 1)

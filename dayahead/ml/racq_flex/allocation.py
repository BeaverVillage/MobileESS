"""Exactly coherent hourly-to-15-minute GPU-h allocation."""

from __future__ import annotations

import torch
from torch import Tensor, nn


class QuarterHourAllocator(nn.Module):
    """Allocate each hourly cohort across four slots without changing mass."""

    def __init__(self, hidden_size: int) -> None:
        super().__init__()
        self.slot_logits = nn.Linear(hidden_size, 24 * 4 * 6 * 5)

    def forward(self, state: Tensor, hourly_GPU_h: Tensor) -> Tensor:
        logits = self.slot_logits(state).reshape(-1, 24, 4, 6, 5)
        proportions = torch.softmax(logits, dim=2)
        slots = (hourly_GPU_h.unsqueeze(2) * proportions).reshape(-1, 96, 6, 5)
        return slots

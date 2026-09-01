"""Training-only self-supervised masked-hour pretraining utilities."""

from __future__ import annotations

import torch
from torch import Tensor, nn


class MaskedHourObjective(nn.Module):
    """Reconstruct masked hourly event-set statistics without future inputs."""

    def __init__(self, hidden_size: int, statistics: int) -> None:
        super().__init__()
        self.head = nn.Linear(hidden_size, statistics)

    def forward(self, encoded_hours: Tensor, target_statistics: Tensor, mask: Tensor) -> Tensor:
        errors = (self.head(encoded_hours) - target_statistics).square().mean(dim=-1)
        return (errors * mask.to(errors.dtype)).sum() / mask.sum().clamp_min(1)

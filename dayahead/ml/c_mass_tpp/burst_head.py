from __future__ import annotations

from torch import nn


class BurstRegimeHead(nn.Module):
    def __init__(self, input_dim: int, hidden_dim: int) -> None:
        super().__init__()
        self.network = nn.Sequential(
            nn.Linear(input_dim, hidden_dim), nn.SiLU(), nn.Linear(hidden_dim, 3)
        )

    def forward(self, context):
        return self.network(context)


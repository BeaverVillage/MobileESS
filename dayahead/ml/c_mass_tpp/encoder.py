from __future__ import annotations

import torch
from torch import nn
from torch.nn import functional as F


class CausalContinuousTimeEncoder(nn.Module):
    """Diagonal decay/jump SSM over irregular request events.

    Each event is embedded independently and its contribution decays from the
    submission instant to the D-1 cutoff.  This is the vectorized closed-form
    counterpart of a causal exponential-decay state recurrence.  It retains
    every event in the frozen seven-day window and never reads realized fields.
    """

    def __init__(self, input_dim: int, hidden_dim: int) -> None:
        super().__init__()
        self.hidden_dim = hidden_dim
        self.event_mlp = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.SiLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.Tanh(),
        )
        self.raw_decay_per_day = nn.Parameter(torch.zeros(hidden_dim))
        self.output_norm = nn.LayerNorm(hidden_dim)

    def event_embedding(self, event_features: torch.Tensor) -> torch.Tensor:
        return self.event_mlp(event_features)

    def forward(
        self,
        event_features: torch.Tensor,
        event_ages_h: torch.Tensor,
        event_mask: torch.Tensor | None = None,
    ) -> torch.Tensor:
        if event_features.ndim == 2:
            event_features = event_features.unsqueeze(0)
            event_ages_h = event_ages_h.unsqueeze(0)
            if event_mask is not None:
                event_mask = event_mask.unsqueeze(0)
        embedding = self.event_embedding(event_features)
        decay = F.softplus(self.raw_decay_per_day).view(1, 1, -1) + 1e-4
        weights = torch.exp(-decay * event_ages_h.unsqueeze(-1) / 24.0)
        if event_mask is None:
            event_mask = torch.ones_like(event_ages_h, dtype=torch.bool)
        weights = weights * event_mask.unsqueeze(-1)
        numerator = (embedding * weights).sum(dim=1)
        denominator = weights.sum(dim=1).clamp_min(1.0).sqrt()
        return self.output_norm(numerator / denominator)


class MacroContextEncoder(nn.Module):
    def __init__(self, input_dim: int, hidden_dim: int) -> None:
        super().__init__()
        self.network = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.SiLU(),
            nn.LayerNorm(hidden_dim),
            nn.Linear(hidden_dim, hidden_dim),
            nn.SiLU(),
        )

    def forward(self, features: torch.Tensor) -> torch.Tensor:
        return self.network(features)


class StandardTransformerWindowEncoder(nn.Module):
    """Ablation encoder over 15-minute pooled event tokens for the 7-day window."""

    def __init__(self, input_dim: int, hidden_dim: int, slots: int = 7 * 96) -> None:
        super().__init__()
        self.slots = slots
        self.embedding = nn.Linear(input_dim, hidden_dim)
        layer = nn.TransformerEncoderLayer(
            hidden_dim,
            nhead=2,
            dim_feedforward=hidden_dim * 2,
            dropout=0.0,
            batch_first=True,
        )
        self.encoder = nn.TransformerEncoder(layer, num_layers=1)
        self.position = nn.Parameter(torch.zeros(1, slots, hidden_dim))
        self.norm = nn.LayerNorm(hidden_dim)

    def forward(self, event_features: torch.Tensor, event_ages_h: torch.Tensor) -> torch.Tensor:
        if event_features.ndim == 3:
            if event_features.shape[0] != 1:
                raise ValueError("ablation encoder accepts one window at a time")
            event_features = event_features[0]
            event_ages_h = event_ages_h[0]
        slot = torch.clamp(
            ((7.0 * 24.0 - event_ages_h) * 4.0).long(), min=0, max=self.slots - 1
        )
        token = torch.zeros(self.slots, self.position.shape[-1], dtype=event_features.dtype)
        count = torch.zeros(self.slots, 1, dtype=event_features.dtype)
        embedded = self.embedding(event_features)
        token.index_add_(0, slot, embedded)
        count.index_add_(0, slot, torch.ones(len(slot), 1, dtype=event_features.dtype))
        token = token / count.clamp_min(1.0)
        encoded = self.encoder((token.unsqueeze(0) + self.position))
        return self.norm(encoded.mean(dim=1))

"""Compact DeepSets hourly encoder followed by elapsed-time decay GRU."""

from __future__ import annotations

import torch
from torch import Tensor, nn
from torch.nn import functional as F


class HourlyEventSetEncoder(nn.Module):
    """Encode event sets shaped ``[batch, 168, events, fields]``."""

    def __init__(self, event_fields: int, hidden_size: int) -> None:
        super().__init__()
        self.phi = nn.Sequential(nn.Linear(event_fields, hidden_size), nn.SiLU(), nn.Linear(hidden_size, hidden_size))
        self.rho = nn.Sequential(nn.LayerNorm(hidden_size), nn.Linear(hidden_size, hidden_size), nn.SiLU())

    def forward(self, events: Tensor, event_mask: Tensor) -> Tensor:
        """Return hourly states ``[batch, 168, hidden]`` without padded-event leakage."""

        encoded = self.phi(events) * event_mask.unsqueeze(-1).to(events.dtype)
        return self.rho(encoded.sum(dim=2))


class DecayGRU(nn.Module):
    """Causal GRU whose hidden state decays across empty elapsed hours."""

    def __init__(self, input_size: int, hidden_size: int) -> None:
        super().__init__()
        self.hidden_size = hidden_size
        self.decay_unconstrained = nn.Parameter(torch.zeros(hidden_size))
        self.cell = nn.GRUCell(input_size, hidden_size)

    def forward(self, hourly: Tensor, elapsed_hours: Tensor) -> tuple[Tensor, Tensor]:
        """Return every causal state and the final state."""

        batch, steps, _ = hourly.shape
        state = hourly.new_zeros((batch, self.hidden_size))
        states = []
        rate = F.softplus(self.decay_unconstrained).unsqueeze(0)
        for step in range(steps):
            state = state * torch.exp(-rate * elapsed_hours[:, step : step + 1])
            state = self.cell(hourly[:, step], state)
            states.append(state)
        stacked = torch.stack(states, dim=1)
        return stacked, state


class GlobalEventStateEncoder(nn.Module):
    """Full compact causal event encoder used by ACQ/RACQ-Flex."""

    def __init__(self, event_fields: int, hidden_size: int) -> None:
        super().__init__()
        self.set_encoder = HourlyEventSetEncoder(event_fields, hidden_size)
        self.temporal = DecayGRU(hidden_size, hidden_size)

    def forward(self, events: Tensor, event_mask: Tensor, elapsed_hours: Tensor) -> Tensor:
        hourly = self.set_encoder(events, event_mask)
        _, final = self.temporal(hourly, elapsed_hours)
        return final

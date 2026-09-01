"""RACQ-Flex architecture with an auditable ACQ fallback switch."""

from __future__ import annotations

from dataclasses import dataclass

import torch
from torch import Tensor, nn
from torch.nn import functional as F

from .allocation import QuarterHourAllocator
from .cohort_decoder import LowRankCohortDecoder
from .counts import HurdleCountHead
from .event_encoder import GlobalEventStateEncoder
from .motif_memory import MotifMemory
from .payload import BulkTailPayloadHead


@dataclass(frozen=True)
class ModelConfig:
    event_fields: int = 12
    motif_fields: int = 16
    query_fields: int = 12
    hidden_size: int = 64
    motif_hidden_size: int = 48
    rank: int = 8
    dropout: float = 0.0
    recurrence_enabled: bool = False
    mass_scale_GPU_h: float = 10000.0


class RACQFlex(nn.Module):
    """Compound forecaster; recurrence must remain off when its gate fails."""

    def __init__(self, config: ModelConfig) -> None:
        super().__init__()
        self.config = config
        self.encoder = GlobalEventStateEncoder(config.event_fields, config.hidden_size)
        self.motif_memory = MotifMemory(config.motif_fields, config.query_fields, config.motif_hidden_size)
        context_size = config.hidden_size + (config.motif_hidden_size if config.recurrence_enabled else 0)
        self.context = nn.Sequential(nn.Linear(context_size, config.hidden_size), nn.SiLU(), nn.Dropout(config.dropout))
        self.counts = HurdleCountHead(config.hidden_size, outputs=2)
        self.payload = BulkTailPayloadHead(config.hidden_size, outputs=2)
        self.total_mass = nn.Linear(config.hidden_size, 1)
        self.cohorts = LowRankCohortDecoder(config.hidden_size, config.rank)
        self.allocation = QuarterHourAllocator(config.hidden_size)

    def forward(
        self,
        events: Tensor,
        event_mask: Tensor,
        elapsed_hours: Tensor,
        motifs: Tensor | None = None,
        motif_mask: Tensor | None = None,
        queries: Tensor | None = None,
    ) -> dict[str, Tensor | dict[str, Tensor]]:
        state = self.encoder(events, event_mask, elapsed_hours)
        if self.config.recurrence_enabled:
            if motifs is None or motif_mask is None or queries is None:
                raise ValueError("RACQ recurrence inputs are required when recurrence_enabled=True")
            motif = self.motif_memory(motifs, motif_mask, queries).mean(dim=1)
            state = torch.cat([state, motif], dim=-1)
        state = self.context(state)
        total = F.softplus(self.total_mass(state)).squeeze(-1) * self.config.mass_scale_GPU_h
        hourly = self.cohorts(state, total)
        slots = self.allocation(state, hourly)
        return {
            "state": state,
            "count_parameters": self.counts(state),
            "payload_parameters": self.payload(state),
            "total_mass_GPU_h": total,
            "hourly_cohort_GPU_h": hourly,
            "slot_cohort_GPU_h": slots,
        }

"""Training-only multi-task self-supervision heads for the causal event encoder."""

from __future__ import annotations

import torch
from torch import nn

from .event_encoder import CausalTCNEncoder


SSL_TASKS = (
    "next_hour_requested_GPU_h", "next_6_hour_requested_GPU_h",
    "next_hour_large_job_occurrence", "next_hour_arrival_count",
    "masked_GPU_request_reconstruction", "masked_walltime_reconstruction",
)


class SSLPressureModel(nn.Module):
    """Attach six training-only auxiliary heads to a compact causal encoder."""

    def __init__(self, encoder: CausalTCNEncoder, latent: int) -> None:
        super().__init__()
        self.encoder = encoder
        self.regression_heads = nn.ModuleList([nn.Linear(latent, 1) for _ in range(5)])
        self.occurrence_head = nn.Linear(latent, 1)

    def forward(self, path: torch.Tensor, explicit: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        latent = self.encoder(path, explicit)
        regression = torch.cat([head(latent) for head in self.regression_heads], dim=1)
        occurrence_logit = self.occurrence_head(latent).squeeze(1)
        return regression, occurrence_logit


from __future__ import annotations

import math

import torch
from torch import nn
from torch.nn import functional as F


class ChunkedServiceSetDecoder(nn.Module):
    """All-at-once anonymous service queries without K_max truncation."""

    def __init__(
        self,
        context_dim: int,
        query_dim: int,
        k_max: int,
        tier_count: int,
        latency_count: int,
        chunk_size: int = 512,
    ) -> None:
        super().__init__()
        self.k_max = int(k_max)
        self.chunk_size = int(chunk_size)
        self.query = nn.Embedding(self.k_max, query_dim)
        self.network = nn.Sequential(
            nn.Linear(context_dim + query_dim + 2, query_dim),
            nn.SiLU(),
            nn.Linear(query_dim, query_dim),
            nn.SiLU(),
        )
        self.activity = nn.Linear(query_dim, 1)
        self.arrival = nn.Linear(query_dim, 1)
        self.tier = nn.Linear(query_dim, tier_count)
        self.latency = nn.Linear(query_dim, latency_count)
        self.mass_score = nn.Linear(query_dim, 1)

    def forward(self, context: torch.Tensor) -> dict[str, torch.Tensor]:
        if context.ndim == 1:
            context = context.unsqueeze(0)
        batch = context.shape[0]
        outputs: dict[str, list[torch.Tensor]] = {
            "activity_logit": [],
            "arrival_h": [],
            "tier_logits": [],
            "latency_logits": [],
            "mass_score_raw": [],
        }
        for start in range(0, self.k_max, self.chunk_size):
            end = min(self.k_max, start + self.chunk_size)
            indices = torch.arange(start, end, device=context.device)
            query = self.query(indices).unsqueeze(0).expand(batch, -1, -1)
            phase = 2.0 * math.pi * (indices.float() + 0.5) / self.k_max
            phase_features = torch.stack((torch.sin(phase), torch.cos(phase)), dim=-1)
            phase_features = phase_features.unsqueeze(0).expand(batch, -1, -1)
            expanded = context.unsqueeze(1).expand(-1, end - start, -1)
            hidden = self.network(torch.cat((expanded, query, phase_features), dim=-1))
            outputs["activity_logit"].append(self.activity(hidden).squeeze(-1))
            outputs["arrival_h"].append(24.0 * torch.sigmoid(self.arrival(hidden).squeeze(-1)))
            outputs["tier_logits"].append(self.tier(hidden))
            outputs["latency_logits"].append(self.latency(hidden))
            outputs["mass_score_raw"].append(self.mass_score(hidden).squeeze(-1))
        return {name: torch.cat(parts, dim=1) for name, parts in outputs.items()}


def hard_mass_reconciliation(
    aggregate_mass: torch.Tensor,
    activity_logit: torch.Tensor,
    mass_score_raw: torch.Tensor,
) -> tuple[torch.Tensor, torch.Tensor]:
    # Reconciliation is intentionally float64 even when the learned network is
    # float32.  This isolates round-off from the scientific mass identity.
    aggregate_mass = aggregate_mass.to(torch.float64)
    raw = (
        torch.sigmoid(activity_logit).to(torch.float64)
        * F.softplus(mass_score_raw).to(torch.float64)
    )
    denominator = raw.sum(dim=-1, keepdim=True)
    uniform = torch.full_like(raw, 1.0 / raw.shape[-1])
    alpha = torch.where(denominator > 0, raw / denominator.clamp_min(1e-30), uniform)
    event_mass = aggregate_mass.unsqueeze(-1) * alpha
    event_mass = torch.where(
        aggregate_mass.unsqueeze(-1) == 0,
        torch.zeros_like(event_mass),
        event_mass,
    )
    if event_mass.shape[-1]:
        residual = aggregate_mass - event_mass.sum(dim=-1)
        event_mass = torch.cat(
            (event_mass[..., :-1], event_mass[..., -1:] + residual.unsqueeze(-1)), dim=-1
        )
    return event_mass, alpha

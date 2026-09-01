"""All-motif chunked encoder and query-conditioned attention pooling."""

from __future__ import annotations

import torch
from torch import Tensor, nn


class MotifMemory(nn.Module):
    """Attend over every active motif; no top-K truncation is permitted."""

    def __init__(self, motif_fields: int, query_fields: int, hidden_size: int, chunk_size: int = 4096) -> None:
        super().__init__()
        self.chunk_size = chunk_size
        self.key = nn.Linear(motif_fields, hidden_size)
        self.value = nn.Linear(motif_fields, hidden_size)
        self.query = nn.Linear(query_fields, hidden_size)
        self.scale = hidden_size**-0.5

    def forward(self, motifs: Tensor, motif_mask: Tensor, queries: Tensor) -> Tensor:
        """Return exact softmax attention over all motifs using stable chunks."""

        query = self.query(queries)
        maximum = query.new_full(query.shape[:-1], -torch.inf)
        scores_chunks = []
        values_chunks = []
        masks = []
        for start in range(0, motifs.shape[1], self.chunk_size):
            chunk = motifs[:, start : start + self.chunk_size]
            mask = motif_mask[:, start : start + self.chunk_size]
            keys = self.key(chunk)
            scores = torch.einsum("bqh,bmh->bqm", query, keys) * self.scale
            scores = scores.masked_fill(~mask[:, None, :], -torch.inf)
            maximum = torch.maximum(maximum, scores.amax(dim=-1))
            scores_chunks.append(scores)
            values_chunks.append(self.value(chunk))
            masks.append(mask)
        numerator = query.new_zeros(query.shape)
        denominator = query.new_zeros(query.shape[:-1])
        for scores, values, mask in zip(scores_chunks, values_chunks, masks):
            weights = torch.exp(scores - maximum.unsqueeze(-1)).masked_fill(~mask[:, None, :], 0.0)
            numerator = numerator + torch.einsum("bqm,bmh->bqh", weights, values)
            denominator = denominator + weights.sum(dim=-1)
        return numerator / denominator.clamp_min(1e-12).unsqueeze(-1)

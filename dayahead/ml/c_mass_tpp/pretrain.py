from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import torch
from torch import nn
from torch.nn import functional as F

from .encoder import CausalContinuousTimeEncoder
from .device import DEVICE


@dataclass(frozen=True)
class PretrainingResult:
    masked_mark_loss: float
    interarrival_loss: float
    next_request_loss: float
    events_seen: int
    epochs: int


class EventPretrainingHeads(nn.Module):
    def __init__(self, hidden_dim: int, gpu_classes: int, node_classes: int, wall_classes: int) -> None:
        super().__init__()
        self.gpu = nn.Linear(hidden_dim, gpu_classes)
        self.node = nn.Linear(hidden_dim, node_classes)
        self.wall = nn.Linear(hidden_dim, wall_classes)
        self.next_delta = nn.Linear(hidden_dim, 1)
        self.next_request = nn.Linear(hidden_dim, gpu_classes)


def _classes(values: np.ndarray, bins: np.ndarray) -> np.ndarray:
    return np.clip(np.digitize(values, bins, right=True), 0, len(bins)).astype(np.int64)


def pretrain_event_encoder(
    encoder: CausalContinuousTimeEncoder,
    features: np.ndarray,
    submit_seconds: np.ndarray,
    seed: int,
    epochs: int = 2,
    batch_size: int = 4096,
) -> PretrainingResult:
    torch.manual_seed(seed)
    rng = np.random.default_rng(seed)
    gpu_class = _classes(features[:, 0], np.log1p(np.asarray([1, 2, 4, 8, 16, 32, 64])))
    node_class = _classes(features[:, 1], np.log1p(np.asarray([1, 2, 4, 8, 16])))
    wall_class = _classes(features[:, 2], np.log1p(np.asarray([0.25, 1, 4, 12, 24, 72])))
    next_delta = np.log1p(np.maximum(np.diff(submit_seconds, append=submit_seconds[-1]), 0.0) / 3600.0)
    next_request = np.roll(gpu_class, -1)
    heads = EventPretrainingHeads(
        encoder.hidden_dim,
        int(gpu_class.max()) + 1,
        int(node_class.max()) + 1,
        int(wall_class.max()) + 1,
    ).to(DEVICE)
    optimizer = torch.optim.Adam(list(encoder.parameters()) + list(heads.parameters()), lr=2e-3)
    totals = np.zeros(3, dtype=float)
    steps = 0
    tensor = torch.from_numpy(features.astype(np.float32)).to(DEVICE)
    for _ in range(epochs):
        order = rng.permutation(len(features))
        for start in range(0, len(order), batch_size):
            index = order[start : start + batch_size]
            index_tensor = torch.from_numpy(index).long().to(DEVICE)
            x = tensor[index_tensor].clone()
            mask = torch.from_numpy(rng.random((len(index), 3)) < 0.30).to(DEVICE)
            x[:, :3] = torch.where(mask, torch.zeros_like(x[:, :3]), x[:, :3])
            hidden = encoder.event_embedding(x)
            loss_mark = (
                F.cross_entropy(heads.gpu(hidden), torch.from_numpy(gpu_class[index]).to(DEVICE))
                + F.cross_entropy(heads.node(hidden), torch.from_numpy(node_class[index]).to(DEVICE))
                + F.cross_entropy(heads.wall(hidden), torch.from_numpy(wall_class[index]).to(DEVICE))
            ) / 3.0
            loss_delta = F.smooth_l1_loss(
                heads.next_delta(hidden).squeeze(-1),
                torch.from_numpy(next_delta[index].astype(np.float32)).to(DEVICE),
            )
            loss_next = F.cross_entropy(
                heads.next_request(hidden), torch.from_numpy(next_request[index]).to(DEVICE)
            )
            loss = loss_mark + loss_delta + loss_next
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            totals += [
                float(loss_mark.detach().cpu()),
                float(loss_delta.detach().cpu()),
                float(loss_next.detach().cpu()),
            ]
            steps += 1
    return PretrainingResult(
        masked_mark_loss=float(totals[0] / max(steps, 1)),
        interarrival_loss=float(totals[1] / max(steps, 1)),
        next_request_loss=float(totals[2] / max(steps, 1)),
        events_seen=int(len(features)),
        epochs=epochs,
    )

"""CUDA-consistent training helpers for the compact ACQ/RACQ model."""

from __future__ import annotations

import copy
import random
import time
from dataclasses import dataclass

import numpy as np
import torch
from torch import Tensor

from .cohort_decoder import LowRankCohortDecoder
from .model import ModelConfig, RACQFlex


@dataclass
class FitResult:
    """One frozen configuration/seed fit and runtime record."""

    model: RACQFlex
    best_loss: float
    epochs: int
    epoch_runtime_seconds: list[float]
    peak_VRAM_bytes: int


def seed_everything(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def fit_model(
    events: Tensor,
    event_mask: Tensor,
    elapsed_hours: Tensor,
    target_total_GPU_h: Tensor,
    target_hourly_GPU_h: Tensor,
    config: ModelConfig,
    seed: int,
    learning_rate: float,
    weight_decay: float,
    epochs: int = 15,
    pretrained_set_encoder_state: dict[str, Tensor] | None = None,
) -> FitResult:
    """Fit one full-batch neural model on a single device without fold mixing."""

    if events.device.type != "cuda":
        raise RuntimeError("V23M_NEURAL_TRAINING_REQUIRES_CUDA")
    seed_everything(seed)
    torch.cuda.reset_peak_memory_stats(events.device)
    model = RACQFlex(config).to(events.device)
    if pretrained_set_encoder_state is not None:
        model.encoder.set_encoder.load_state_dict(pretrained_set_encoder_state)
    optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate, weight_decay=weight_decay)
    best_state = copy.deepcopy(model.state_dict())
    best_loss = float("inf")
    runtimes: list[float] = []
    for _ in range(epochs):
        start = time.perf_counter()
        model.train()
        optimizer.zero_grad(set_to_none=True)
        output = model(events, event_mask, elapsed_hours)
        predicted = output["total_mass_GPU_h"]
        proportions = model.cohorts.proportions(output["state"])
        total_loss = torch.nn.functional.smooth_l1_loss(torch.log1p(predicted), torch.log1p(target_total_GPU_h))
        target_proportions = target_hourly_GPU_h.flatten(1) / target_total_GPU_h.clamp_min(1e-8).unsqueeze(-1)
        cohort_loss = -(target_proportions * torch.log(proportions.flatten(1).clamp_min(1e-8))).sum(dim=1).mean()
        loss = total_loss + 0.05 * cohort_loss
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        optimizer.step()
        if float(loss.detach()) < best_loss:
            best_loss = float(loss.detach())
            best_state = copy.deepcopy(model.state_dict())
        torch.cuda.synchronize(events.device)
        runtimes.append(time.perf_counter() - start)
    model.load_state_dict(best_state)
    return FitResult(model, best_loss, epochs, runtimes, int(torch.cuda.max_memory_allocated(events.device)))


@torch.no_grad()
def predict_model(model: RACQFlex, events: Tensor, event_mask: Tensor, elapsed_hours: Tensor) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return daily GPU-h and coherent hourly cohorts on the model device."""

    model.eval()
    output = model(events, event_mask, elapsed_hours)
    return (
        output["total_mass_GPU_h"].detach().cpu().numpy().astype(float),
        output["hourly_cohort_GPU_h"].detach().cpu().numpy().astype(float),
        output["slot_cohort_GPU_h"].detach().cpu().numpy().astype(float),
    )

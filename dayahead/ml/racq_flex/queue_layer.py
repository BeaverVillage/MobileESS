"""Differentiable fluid EDF and frozen exact-scheduler adapter."""

from __future__ import annotations

import numpy as np
import torch
from torch import Tensor, nn

from dayahead.ml.c_mass_tpp.scheduler import grid_blind_edf
from .contracts import SLOT_CAPACITY_GPU_H


DEADLINE_SLOTS = (2, 4, 8, 12, 24)


class FluidEDF(nn.Module):
    """Training-only fluid EDF; this approximation is not the exact scheduler."""

    def __init__(self, slot_capacity_GPU_h: float = SLOT_CAPACITY_GPU_H) -> None:
        super().__init__()
        self.slot_capacity_GPU_h = float(slot_capacity_GPU_h)

    def forward(self, arrivals_GPU_h: Tensor) -> dict[str, Tensor]:
        """Serve ``[batch,96,6,5]`` arrivals by latency-class EDF priority."""

        if arrivals_GPU_h.shape[1:] != (96, 6, 5):
            raise ValueError("arrivals must have shape [batch,96,6,5]")
        backlog = torch.zeros_like(arrivals_GPU_h[:, 0])
        service_slots = []
        backlog_slots = []
        for slot in range(96):
            available = backlog + arrivals_GPU_h[:, slot]
            remaining = available.new_full((available.shape[0],), self.slot_capacity_GPU_h)
            served_classes = []
            for latency in range(5):
                class_available = available[:, :, latency]
                class_total = class_available.sum(dim=1)
                class_served = torch.minimum(class_total, remaining)
                shares = class_available / class_total.clamp_min(1e-12).unsqueeze(-1)
                served = shares * class_served.unsqueeze(-1)
                served_classes.append(served)
                remaining = remaining - class_served
            served_slot = torch.stack(served_classes, dim=-1)
            backlog = available - served_slot
            service_slots.append(served_slot)
            backlog_slots.append(backlog)
        service = torch.stack(service_slots, dim=1)
        backlog_trace = torch.stack(backlog_slots, dim=1)
        return {
            "service_GPU_h": service,
            "backlog_GPU_h": backlog_trace,
            "terminal_backlog_GPU_h": backlog.sum(dim=(1, 2)),
            "work_conservation_error_GPU_h": (
                arrivals_GPU_h.sum(dim=(1, 2, 3))
                - service.sum(dim=(1, 2, 3))
                - backlog.sum(dim=(1, 2))
            ).abs(),
        }


def exact_scheduler(arrivals_GPU_h: np.ndarray) -> dict[str, object]:
    """Call the frozen V19 exact reference scheduler with one aggregate rack."""

    return grid_blind_edf(np.asarray(arrivals_GPU_h, dtype=float), np.asarray([1.0]))


def queue_huber_loss(predicted_arrivals: Tensor, target_arrivals: Tensor, delta: float = 1.0) -> Tensor:
    """Compare served work, backlog, and terminal backlog without shrinking arrival mass."""

    scheduler = FluidEDF()
    predicted = scheduler(predicted_arrivals)
    target = scheduler(target_arrivals)
    served = torch.nn.functional.huber_loss(predicted["service_GPU_h"], target["service_GPU_h"], delta=delta)
    backlog = torch.nn.functional.huber_loss(predicted["backlog_GPU_h"], target["backlog_GPU_h"], delta=delta)
    terminal = torch.nn.functional.huber_loss(predicted["terminal_backlog_GPU_h"], target["terminal_backlog_GPU_h"], delta=delta)
    return served + backlog + terminal

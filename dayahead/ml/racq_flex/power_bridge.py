"""Frozen tier-to-IT-power projection; PUE and facility scale are excluded."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import torch
from torch import Tensor

from .contracts import POWER_TIERS


ROOT = Path(__file__).resolve().parents[3]
V18_CONTRACT = ROOT / "dayahead" / "artifacts" / "v18_aidc_physical_refreeze" / "V18_AIDC_NODE_POWER_AUTHORITY_CONTRACT.json"
DT_H = 0.25


def tier_coefficients_kWh_per_GPU_h() -> dict[str, float]:
    """Read the frozen Dataset312 hybrid IT-side coefficient authority."""

    contract = json.loads(V18_CONTRACT.read_text(encoding="utf-8"))
    full = {int(key): float(value) for key, value in contract["fullnode"]["kappa_total_kW_per_active_node"].items()}
    partial = float(contract["partialnode"]["kappa_kW_per_GPU"])
    return {
        tier: full[int(tier.split("_")[1])] / 4.0 if tier.startswith("FULL_") else partial
        for tier in POWER_TIERS
    }


def service_to_IT_power_kW(service_GPU_h: Tensor) -> Tensor:
    """Project ``[batch,96,6,5]`` served GPU-h to IT-side flexible kW."""

    coefficients = torch.tensor(
        [tier_coefficients_kWh_per_GPU_h()[tier] for tier in POWER_TIERS],
        dtype=service_GPU_h.dtype,
        device=service_GPU_h.device,
    )
    tier_mass = service_GPU_h.sum(dim=-1)
    return (tier_mass * coefficients.reshape(1, 1, -1)).sum(dim=-1) / DT_H


def service_to_IT_power_numpy_kW(service_GPU_h: np.ndarray) -> np.ndarray:
    coefficients = np.asarray([tier_coefficients_kWh_per_GPU_h()[tier] for tier in POWER_TIERS])
    return (np.asarray(service_GPU_h, dtype=float).sum(axis=-1) * coefficients[None, :]).sum(axis=-1) / DT_H


def power_huber_loss(predicted_service: Tensor, target_service: Tensor, delta_kW: float = 100.0) -> Tensor:
    """Normalized IT-side power loss with no PUE, grid, or facility-scale term."""

    predicted = service_to_IT_power_kW(predicted_service)
    target = service_to_IT_power_kW(target_service)
    scale = target.detach().abs().mean().clamp_min(1.0)
    return torch.nn.functional.huber_loss(predicted / scale, target / scale, delta=delta_kW / float(scale))

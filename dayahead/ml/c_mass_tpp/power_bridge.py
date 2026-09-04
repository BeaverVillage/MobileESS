from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from .data import ROOT, TIERS


V18 = ROOT / "dayahead" / "artifacts" / "v18_aidc_physical_refreeze"
DT_H = 0.25
PUE = 1.30


def tier_coefficients_kWh_per_GPU_h() -> dict[str, float]:
    contract = json.loads(
        (V18 / "V18_AIDC_NODE_POWER_AUTHORITY_CONTRACT.json").read_text(encoding="utf-8")
    )
    full = {
        int(key): float(value)
        for key, value in contract["fullnode"]["kappa_total_kW_per_active_node"].items()
    }
    partial = float(contract["partialnode"]["kappa_kW_per_GPU"])
    return {
        tier: full[int(tier.split("_")[1])] / 4.0 if tier.startswith("FULL_") else partial
        for tier in TIERS
    }


def packets_to_power(
    arrival_h: np.ndarray,
    tier_probability: np.ndarray,
    event_mass_GPU_h: np.ndarray,
) -> dict[str, object]:
    arrival_h = np.asarray(arrival_h, dtype=float)
    tier_probability = np.asarray(tier_probability, dtype=float)
    event_mass = np.asarray(event_mass_GPU_h, dtype=float)
    coefficients = tier_coefficients_kWh_per_GPU_h()
    coefficient_array = np.asarray([coefficients[tier] for tier in TIERS])
    slot_tier_mass = np.zeros((96, len(TIERS)), dtype=float)
    slot = np.minimum((arrival_h * 4).astype(int), 95)
    for index in range(len(event_mass)):
        slot_tier_mass[slot[index]] += event_mass[index] * tier_probability[index]
    power_it = (slot_tier_mass * coefficient_array[None, :]).sum(axis=1) / DT_H
    return {
        "slot_tier_mass_GPU_h": slot_tier_mass,
        "power_IT_kW": power_it,
        "power_PCC_kW": PUE * power_it,
        "IT_energy_kWh": float(power_it.sum() * DT_H),
        "PCC_energy_kWh": float(PUE * power_it.sum() * DT_H),
        "tier_mass_GPU_h": slot_tier_mass.sum(axis=0),
        "mass_identity_error_GPU_h": float(abs(event_mass.sum() - slot_tier_mass.sum())),
        "PUE_application_count": 1,
        "partial_CPU_double_count": 0,
    }


def actual_target_power(
    arrival_h: np.ndarray,
    tier_index: np.ndarray,
    event_mass_GPU_h: np.ndarray,
) -> np.ndarray:
    probability = np.eye(len(TIERS), dtype=float)[np.asarray(tier_index, dtype=int)]
    return np.asarray(packets_to_power(arrival_h, probability, event_mass_GPU_h)["power_IT_kW"])


def power_metrics(actual_kw: np.ndarray, predicted_kw: np.ndarray) -> dict[str, float]:
    actual = np.asarray(actual_kw, dtype=float)
    predicted = np.asarray(predicted_kw, dtype=float)
    return {
        "flexible_IT_power_WAPE": float(np.abs(predicted - actual).sum() / max(actual.sum(), 1e-12)),
        "IT_energy_bias_kWh": float((predicted - actual).sum() * DT_H),
        "peak_flexible_IT_power_error_kW": float(predicted.max() - actual.max()),
        "peak_timing_error_slots": float(abs(int(np.argmax(predicted)) - int(np.argmax(actual)))),
    }


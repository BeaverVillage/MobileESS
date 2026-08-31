from __future__ import annotations

import numpy as np

from .data import LATENCIES, TIERS


C_MODEL = 528.0
DT_H = 0.25
DEADLINE_SLOTS = (2, 4, 8, 12, 24)


def packet_arrivals(
    arrival_h: np.ndarray,
    tier_probability: np.ndarray,
    latency_probability: np.ndarray,
    event_mass_GPU_h: np.ndarray,
) -> np.ndarray:
    arrivals = np.zeros((96, len(TIERS), len(LATENCIES)), dtype=float)
    slots = np.minimum((np.asarray(arrival_h) * 4).astype(int), 95)
    for index, mass in enumerate(np.asarray(event_mass_GPU_h, dtype=float)):
        arrivals[slots[index]] += (
            mass
            * np.asarray(tier_probability[index], dtype=float)[:, None]
            * np.asarray(latency_probability[index], dtype=float)[None, :]
        )
    return arrivals


def grid_blind_edf(
    arrivals: np.ndarray,
    rack_weights: np.ndarray,
) -> dict[str, object]:
    arrivals = np.asarray(arrivals, dtype=float)
    service = np.zeros_like(arrivals)
    pending: list[dict[str, float | int]] = []
    deadline_shortfall = 0.0
    max_backlog = 0.0
    max_capacity_violation = 0.0
    capacity = C_MODEL * DT_H
    for slot in range(96):
        for tier in range(len(TIERS)):
            for latency in range(len(LATENCIES)):
                amount = float(arrivals[slot, tier, latency])
                if amount > 0:
                    pending.append(
                        {
                            "arrival": slot,
                            "due": min(96, slot + DEADLINE_SLOTS[latency]),
                            "tier": tier,
                            "latency": latency,
                            "remaining": amount,
                        }
                    )
        expired = [item for item in pending if int(item["due"]) <= slot and float(item["remaining"]) > 1e-12]
        deadline_shortfall = max(deadline_shortfall, sum(float(item["remaining"]) for item in expired))
        pending.sort(key=lambda item: (item["due"], item["arrival"], item["latency"], item["tier"]))
        remaining_capacity = capacity
        for item in pending:
            if remaining_capacity <= 1e-12:
                break
            amount = min(float(item["remaining"]), remaining_capacity)
            service[slot, int(item["tier"]), int(item["latency"])] += amount
            item["remaining"] = float(item["remaining"]) - amount
            remaining_capacity -= amount
        pending = [item for item in pending if float(item["remaining"]) > 1e-12]
        max_backlog = max(max_backlog, sum(float(item["remaining"]) for item in pending))
        max_capacity_violation = max(max_capacity_violation, float(service[slot].sum() - capacity))
    for item in pending:
        if int(item["due"]) <= 96:
            deadline_shortfall = max(deadline_shortfall, float(item["remaining"]))
    terminal = sum(float(item["remaining"]) for item in pending)
    service_tier_slot = service.sum(axis=2)
    rack_service = service_tier_slot[:, :, None] * np.asarray(rack_weights)[None, None, :]
    rack_capacity = C_MODEL * np.asarray(rack_weights) * DT_H
    rack_violation = float(np.max(rack_service.sum(axis=1) - rack_capacity[None, :]))
    arrival_total = float(arrivals.sum())
    service_total = float(service.sum())
    return {
        "arrival_GPU_h": arrival_total,
        "served_GPU_h": service_total,
        "work_conservation_abs_error_GPU_h": abs(arrival_total - service_total - terminal),
        "max_backlog_GPU_h": max_backlog,
        "terminal_backlog_GPU_h": terminal,
        "max_deadline_shortfall_GPU_h": deadline_shortfall,
        "max_system_capacity_violation_GPU_h_per_slot": max(0.0, max_capacity_violation),
        "max_rack_capacity_violation_GPU_h_per_slot": max(0.0, rack_violation),
        "hidden_shedding_GPU_h": 0.0,
        "feasible": bool(
            terminal <= 1e-8
            and deadline_shortfall <= 1e-8
            and max_capacity_violation <= 1e-8
            and rack_violation <= 1e-8
        ),
        "service": service,
        "rack_service": rack_service,
    }


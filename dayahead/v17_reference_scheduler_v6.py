"""Permutation-invariant GPU-hour reference scheduler for V17 V4R1."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .v17_deferrability_semantics import DEFERRAL_SLOTS, LATENCY_CLASSES


GPU_COUNTS = (1, 2, 3, 4)


@dataclass(frozen=True)
class ReferenceScheduleV6:
    authority_id: str
    service_by_class_gpu_rack_slot: Mapping[tuple[str, int, str, int], float]
    evidence: Mapping[str, Any]


def _weighted_water_fill(amount: float, remaining: dict[str, float], weights: Mapping[str, float]) -> dict[str, float]:
    """Allocate fluid service proportionally to immutable capacity weights."""

    allocation = {rack: 0.0 for rack in remaining}
    left = float(amount)
    active = {rack for rack, capacity in remaining.items() if capacity > 1e-15 and float(weights[rack]) > 0}
    while left > 1e-12 and active:
        weight_sum = sum(float(weights[rack]) for rack in active)
        if weight_sum <= 0:
            break
        saturated: set[str] = set()
        proposal = {rack: left * float(weights[rack]) / weight_sum for rack in active}
        consumed = 0.0
        for rack in sorted(active):
            value = min(proposal[rack], remaining[rack])
            allocation[rack] += value
            remaining[rack] -= value
            consumed += value
            if remaining[rack] <= 1e-12 or proposal[rack] >= remaining[rack] + value - 1e-12:
                saturated.add(rack)
        if consumed <= 1e-15:
            break
        left -= consumed
        active -= saturated
    if left > 1e-9:
        raise RuntimeError(f"REFERENCE_V6_WEIGHTED_WATER_FILL_CAPACITY_SHORTFALL:{left}")
    return allocation


def build_reference_schedule_v6_gpu_hour(
    arrivals: Mapping[tuple[str, int], Sequence[float]],
    rack_capacity_gpu_hour_per_slot: Mapping[str, float],
) -> ReferenceScheduleV6:
    expected = {(latency, gpu_count) for latency in LATENCY_CLASSES for gpu_count in GPU_COUNTS}
    if set(arrivals) != expected:
        raise ValueError("REFERENCE_V6_CLASS_GPU_AXIS_MISMATCH")
    if not rack_capacity_gpu_hour_per_slot or any(float(value) < 0 for value in rack_capacity_gpu_hour_per_slot.values()):
        raise ValueError("REFERENCE_V6_INVALID_RACK_GPU_HOUR_CAPACITY")
    for values in arrivals.values():
        if len(values) != 96 or any(not math.isfinite(float(value)) or float(value) < 0 for value in values):
            raise ValueError("REFERENCE_V6_REQUIRES_96_FINITE_NONNEGATIVE_GPU_HOUR_ARRIVALS")
    racks = tuple(sorted(rack_capacity_gpu_hour_per_slot))
    total_capacity = sum(float(rack_capacity_gpu_hour_per_slot[rack]) for rack in racks)
    if total_capacity <= 0:
        raise ValueError("REFERENCE_V6_ZERO_TOTAL_CAPACITY")
    weights = {rack: float(rack_capacity_gpu_hour_per_slot[rack]) / total_capacity for rack in racks}
    service = {
        (latency, gpu_count, rack, slot): 0.0
        for latency in LATENCY_CLASSES for gpu_count in GPU_COUNTS for rack in racks for slot in range(96)
    }
    pending: list[dict[str, Any]] = []
    for slot in range(96):
        for latency in LATENCY_CLASSES:
            for gpu_count in GPU_COUNTS:
                value = float(arrivals[(latency, gpu_count)][slot])
                if value > 0:
                    pending.append({
                        "class": latency, "gpu_count": gpu_count, "arrival": slot,
                        "due": min(95, slot + DEFERRAL_SLOTS[latency]), "remaining": value,
                    })
        remaining = {rack: float(rack_capacity_gpu_hour_per_slot[rack]) for rack in racks}
        pending.sort(key=lambda row: (row["due"], row["arrival"], row["class"], row["gpu_count"]))
        for item in pending:
            amount = min(float(item["remaining"]), sum(remaining.values()))
            if amount <= 0:
                continue
            allocation = _weighted_water_fill(amount, remaining, weights)
            for rack, value in allocation.items():
                service[(item["class"], item["gpu_count"], rack, slot)] += value
            item["remaining"] -= amount
        overdue = [item for item in pending if item["due"] <= slot and item["remaining"] > 1e-9]
        if overdue:
            raise RuntimeError(f"REFERENCE_V6_DEADLINE_INFEASIBLE:{slot}:{max(item['remaining'] for item in overdue)}")
        pending = [item for item in pending if item["remaining"] > 1e-12]
    terminal = sum(float(item["remaining"]) for item in pending)
    if terminal > 1e-9:
        raise RuntimeError(f"REFERENCE_V6_TERMINAL_SERVICE_PARITY_FAILED:{terminal}")
    max_anticipation = 0.0; max_deadline_shortfall = 0.0; parity_error = 0.0
    for latency, gpu_count in sorted(expected):
        arrival = [float(value) for value in arrivals[(latency, gpu_count)]]
        served = [sum(service[(latency, gpu_count, rack, slot)] for rack in racks) for slot in range(96)]
        parity_error = max(parity_error, abs(sum(arrival) - sum(served)))
        cumulative_arrival = 0.0; cumulative_service = 0.0
        for slot in range(96):
            cumulative_arrival += arrival[slot]; cumulative_service += served[slot]
            max_anticipation = max(max_anticipation, cumulative_service - cumulative_arrival)
            due = min(95, slot + DEFERRAL_SLOTS[latency])
            max_deadline_shortfall = max(max_deadline_shortfall, sum(arrival[:slot + 1]) - sum(served[:due + 1]))
    evidence = {
        "policy": "GRID_BLIND_MESS_BLIND_EARLIEST_DEADLINE_WEIGHTED_WATER_FILL",
        "workload_unit": "GPU_HOUR",
        "rack_capacity_unit": "GPU_HOUR_PER_15MIN_SLOT",
        "capacity_weights": weights,
        "capacity_weight_sum": sum(weights.values()),
        "max_no_anticipation_violation_GPU_hour": max(0.0, max_anticipation),
        "max_deadline_shortfall_GPU_hour": max(0.0, max_deadline_shortfall),
        "terminal_backlog_GPU_hour": terminal,
        "service_parity_max_abs_error_GPU_hour": parity_error,
        "permutation_invariant_by_rack_identity": True,
        "grid_information_reads": 0,
        "MESS_information_reads": 0,
        "OpenDSS_calls": 0,
        "optimized_result_reads": 0,
    }
    return ReferenceScheduleV6("REFERENCE_COMPUTE_SCHEDULE_V6_GPU_HOUR", service, evidence)

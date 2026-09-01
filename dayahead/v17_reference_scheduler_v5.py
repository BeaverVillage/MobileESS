"""V17 V5 grid-blind capacity-weighted reference spatialization.

V4 remains the immutable historical lexicographic first-fit authority.  This
module changes only the spatial allocation of each temporally ordered fluid
work item.  Nominal rack compute capacity is the sole spatial weight.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping, MutableMapping, Sequence

from .aidc_ml_data import NODE_CLASSES
from .v17_deferrability_semantics import DEFERRAL_SLOTS, LATENCY_CLASSES


AUTHORITY_ID = "REFERENCE_COMPUTE_SCHEDULE_V5"
POLICY_ID = "CAPACITY_PROPORTIONAL_WEIGHTED_WATERFILL"
NUMERICAL_TOLERANCE = 1e-12


@dataclass(frozen=True)
class ReferenceScheduleV5:
    authority_id: str
    service_by_class_node_rack_slot: Mapping[tuple[str, int, str, int], float]
    evidence: Mapping[str, Any]


def weighted_waterfill(
    workload_nodeh: float,
    nominal_capacity_nodeh: Mapping[str, float],
    remaining_capacity_nodeh: MutableMapping[str, float],
    *,
    tolerance: float = NUMERICAL_TOLERANCE,
) -> dict[str, float]:
    """Allocate up to available capacity using nominal-capacity weights.

    Labels are used only as dictionary keys and for deterministic returned
    serialization.  The allocation equation contains no label/order term.
    """

    workload = float(workload_nodeh)
    if not math.isfinite(workload) or workload < -tolerance:
        raise ValueError("REFERENCE_V5_INVALID_WORKLOAD")
    if set(nominal_capacity_nodeh) != set(remaining_capacity_nodeh):
        raise ValueError("REFERENCE_V5_CAPACITY_AXIS_MISMATCH")
    for rack in nominal_capacity_nodeh:
        nominal = float(nominal_capacity_nodeh[rack])
        remaining = float(remaining_capacity_nodeh[rack])
        if not math.isfinite(nominal) or nominal < 0 or not math.isfinite(remaining) or remaining < -tolerance:
            raise ValueError("REFERENCE_V5_INVALID_RACK_CAPACITY")

    allocation = {rack: 0.0 for rack in nominal_capacity_nodeh}
    available = math.fsum(max(0.0, float(value)) for value in remaining_capacity_nodeh.values())
    residual = min(max(0.0, workload), available)
    active = {
        rack
        for rack in nominal_capacity_nodeh
        if float(nominal_capacity_nodeh[rack]) > tolerance
        and float(remaining_capacity_nodeh[rack]) > tolerance
    }
    rounds = 0
    while residual > tolerance:
        rounds += 1
        if not active or rounds > len(nominal_capacity_nodeh) + 1:
            raise RuntimeError("REFERENCE_V5_WATERFILL_NONTERMINATION")
        denominator = math.fsum(float(nominal_capacity_nodeh[rack]) for rack in active)
        if denominator <= tolerance:
            raise RuntimeError("REFERENCE_V5_NO_POSITIVE_WEIGHT_FOR_AVAILABLE_CAPACITY")
        proposed = {
            rack: residual * float(nominal_capacity_nodeh[rack]) / denominator
            for rack in active
        }
        amounts = {
            rack: min(float(remaining_capacity_nodeh[rack]), proposed[rack])
            for rack in active
        }
        allocated = math.fsum(amounts.values())
        if allocated <= tolerance:
            raise RuntimeError("REFERENCE_V5_WATERFILL_NO_PROGRESS")
        for rack, amount in amounts.items():
            allocation[rack] += amount
            remaining_capacity_nodeh[rack] = max(0.0, float(remaining_capacity_nodeh[rack]) - amount)
        residual = max(0.0, residual - allocated)
        saturated = {
            rack
            for rack in active
            if float(remaining_capacity_nodeh[rack]) <= tolerance
            or proposed[rack] >= float(remaining_capacity_nodeh[rack]) + amounts[rack] - tolerance
        }
        if not saturated:
            # An unsaturated proportional round analytically allocates the
            # entire residual; only sub-tolerance floating residue may remain.
            if residual <= 10.0 * tolerance:
                residual = 0.0
                break
            raise RuntimeError("REFERENCE_V5_WATERFILL_UNSATURATED_RESIDUAL")
        active.difference_update(saturated)
    return {rack: allocation[rack] for rack in sorted(allocation)}


def build_reference_schedule_v5(
    arrivals: Mapping[tuple[str, int], Sequence[float]],
    rack_capacity_nodeh_per_slot: Mapping[str, float],
) -> ReferenceScheduleV5:
    """Preserve V4 temporal EDF and replace only rack first-fit by water-fill."""

    expected = {(name, node) for name in LATENCY_CLASSES for node in NODE_CLASSES}
    if set(arrivals) != expected:
        raise ValueError("REFERENCE_V5_CLASS_NODE_AXIS_MISMATCH")
    if not rack_capacity_nodeh_per_slot or any(
        not math.isfinite(float(value)) or float(value) < 0
        for value in rack_capacity_nodeh_per_slot.values()
    ):
        raise ValueError("REFERENCE_V5_INVALID_RACK_CAPACITY")
    for values in arrivals.values():
        if len(values) != 96 or any(
            not math.isfinite(float(value)) or float(value) < 0 for value in values
        ):
            raise ValueError("REFERENCE_V5_REQUIRES_96_FINITE_NONNEGATIVE_ARRIVALS")

    racks = tuple(sorted(rack_capacity_nodeh_per_slot))
    nominal = {rack: float(rack_capacity_nodeh_per_slot[rack]) for rack in racks}
    service = {
        (name, node, rack, slot): 0.0
        for name in LATENCY_CLASSES
        for node in NODE_CLASSES
        for rack in racks
        for slot in range(96)
    }
    pending: list[dict[str, Any]] = []
    max_overdue = 0.0
    for slot in range(96):
        for name in LATENCY_CLASSES:
            for node in NODE_CLASSES:
                value = float(arrivals[(name, node)][slot])
                if value > 0:
                    pending.append(
                        {
                            "class": name,
                            "node": node,
                            "arrival": slot,
                            "due": min(95, slot + DEFERRAL_SLOTS[name]),
                            "remaining": value,
                        }
                    )
        remaining = dict(nominal)
        pending.sort(
            key=lambda item: (
                item["due"], item["arrival"], item["class"], item["node"]
            )
        )
        for item in pending:
            target = min(
                float(item["remaining"]),
                math.fsum(max(0.0, value) for value in remaining.values()),
            )
            if target <= NUMERICAL_TOLERANCE:
                continue
            allocated = weighted_waterfill(target, nominal, remaining)
            total = math.fsum(allocated.values())
            for rack, amount in allocated.items():
                if amount:
                    service[(item["class"], item["node"], rack, slot)] += amount
            item["remaining"] = max(0.0, float(item["remaining"]) - total)
        for item in pending:
            if item["due"] <= slot and item["remaining"] > 1e-10:
                max_overdue = max(max_overdue, float(item["remaining"]))
        if max_overdue > 0:
            raise RuntimeError(f"REFERENCE_V5_DEADLINE_INFEASIBLE:{slot}:{max_overdue}")
        pending = [item for item in pending if item["remaining"] > NUMERICAL_TOLERANCE]

    terminal = math.fsum(float(item["remaining"]) for item in pending)
    if terminal > 1e-10:
        raise RuntimeError(f"REFERENCE_V5_TERMINAL_SERVICE_PARITY_FAILED:{terminal}")

    max_anticipation = 0.0
    max_deadline_shortfall = 0.0
    max_capacity_violation = 0.0
    total_arrivals = math.fsum(float(value) for values in arrivals.values() for value in values)
    total_service = math.fsum(service.values())
    for slot in range(96):
        for rack in racks:
            used = math.fsum(
                service[(name, node, rack, slot)]
                for name in LATENCY_CLASSES
                for node in NODE_CLASSES
            )
            max_capacity_violation = max(max_capacity_violation, used - nominal[rack])
    for name, node in sorted(expected):
        arrival_values = [float(value) for value in arrivals[(name, node)]]
        served = [
            math.fsum(service[(name, node, rack, slot)] for rack in racks)
            for slot in range(96)
        ]
        cumulative_arrival = 0.0
        cumulative_service = 0.0
        for slot in range(96):
            cumulative_arrival += arrival_values[slot]
            cumulative_service += served[slot]
            max_anticipation = max(max_anticipation, cumulative_service - cumulative_arrival)
            due_slot = min(95, slot + DEFERRAL_SLOTS[name])
            max_deadline_shortfall = max(
                max_deadline_shortfall,
                math.fsum(arrival_values[: slot + 1]) - math.fsum(served[: due_slot + 1]),
            )
    evidence = {
        "policy": POLICY_ID,
        "terminology": "CAPACITY-WEIGHTED SYNTHETIC NEUTRAL SPATIALIZATION",
        "temporal_ordering": ["due_slot", "arrival_slot", "class_C1_to_C5", "node_class_1_2_4_8_16"],
        "capacity_authority": "rack_capacity_nodeh_per_slot",
        "historical_spatial_labels_available": False,
        "synthetic_spatialization": True,
        "grid_information_reads": 0,
        "MESS_information_reads": 0,
        "J_I_reads": 0,
        "H_reads": 0,
        "OpenDSS_calls": 0,
        "optimized_result_reads": 0,
        "AIDC_label_ordering_influence": 0,
        "Rack_label_ordering_influence": 0,
        "max_no_anticipation_violation_nodeh": max(0.0, max_anticipation),
        "max_deadline_shortfall_nodeh": max(0.0, max_deadline_shortfall),
        "terminal_backlog_nodeh": terminal,
        "service_parity_abs_error_nodeh": abs(total_service - total_arrivals),
        "max_rack_capacity_violation_nodeh": max(0.0, max_capacity_violation),
    }
    return ReferenceScheduleV5(AUTHORITY_ID, service, evidence)

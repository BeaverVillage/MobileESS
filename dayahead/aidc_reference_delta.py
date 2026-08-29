"""V16 Q90 reference-decomposition planning residual and REF-to-DA delta."""

from __future__ import annotations

from typing import Sequence

AUTHORITY_ID = "AIDC_REFERENCE_DELTA_V1"
PLANNING_PUE = 1.30
PLANNING_PF = 0.95


def map_system_reference(system_values: Sequence[float], weights: Sequence[float]) -> tuple[tuple[float, ...], ...]:
    if len(system_values) != 96 or not weights or abs(sum(weights) - 1.0) > 1e-9:
        raise ValueError("REFERENCE_MAPPING_REQUIRES_96_VALUES_AND_UNIT_WEIGHTS")
    if any(weight < 0 for weight in weights):
        raise ValueError("NEGATIVE_RACK_MAPPING_WEIGHT")
    return tuple(tuple(float(value) * float(weight) for weight in weights) for value in system_values)


def planning_residual(
    mapped_reference_q90: Sequence[Sequence[float]], flexible_reference: Sequence[Sequence[float]]
) -> tuple[tuple[float, ...], ...]:
    if len(mapped_reference_q90) != 96 or len(flexible_reference) != 96:
        raise ValueError("REFERENCE_DELTA_REQUIRES_96_SLOTS")
    result = []
    for mapped, flexible in zip(mapped_reference_q90, flexible_reference):
        if len(mapped) != len(flexible):
            raise ValueError("REFERENCE_DELTA_RACK_AXIS_MISMATCH")
        row = tuple(float(a) - float(b) for a, b in zip(mapped, flexible))
        if any(value < 0.0 for value in row):
            raise ValueError("FAIL_REFERENCE_DELTA_DECOMPOSITION")
        result.append(row)
    return tuple(result)


def reconstruct_da(residual: Sequence[Sequence[float]], flexible_da: Sequence[Sequence[float]]) -> tuple[tuple[float, ...], ...]:
    if len(residual) != len(flexible_da):
        raise ValueError("REFERENCE_DELTA_SLOT_AXIS_MISMATCH")
    return tuple(tuple(float(a) + float(b) for a, b in zip(row_a, row_b)) for row_a, row_b in zip(residual, flexible_da))


def facility_power_and_reactive(it_power_kw: float) -> tuple[float, float]:
    import math
    facility = PLANNING_PUE * float(it_power_kw)
    return facility, facility * math.tan(math.acos(PLANNING_PF))

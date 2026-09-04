"""Transparency-only reference baseline fidelity metrics with locked-data firewall."""

from __future__ import annotations

from math import sqrt
from typing import Sequence

AUTHORITY_ID = "REFERENCE_BASELINE_FIDELITY_DIAGNOSTIC_V1"


def validate_access(period: str, *, may_evaluation_complete: bool = False, june_replication_complete: bool = False) -> None:
    if period == "PRIMARY_2025MAY" and not may_evaluation_complete:
        raise PermissionError("MAY_FIDELITY_LOCKED_UNTIL_PRIMARY_EVALUATION_COMPLETE")
    if period == "REPLICATION_2025JUN01_25" and not june_replication_complete:
        raise PermissionError("JUNE_FIDELITY_LOCKED_UNTIL_REPLICATION_COMPLETE")
    if period not in {"TRAIN_2024AUG19_2025MAR31", "VALIDATION_2025APR", "PRIMARY_2025MAY", "REPLICATION_2025JUN01_25"}:
        raise ValueError("UNKNOWN_FIDELITY_PERIOD")


def fidelity_metrics(reference: Sequence[float], natural: Sequence[float]) -> dict[str, object]:
    if len(reference) != len(natural) or not reference:
        raise ValueError("FIDELITY_SERIES_SHAPE_MISMATCH")
    delta = [float(a) - float(b) for a, b in zip(reference, natural)]
    ref_peak = max(map(float, reference)); nat_peak = max(map(float, natural))
    return {
        "authority_id": AUTHORITY_ID,
        "acceptance_threshold": None,
        "tuning_authority": False,
        "profile_rmse": sqrt(sum(value * value for value in delta) / len(delta)),
        "total_energy_or_work_difference": sum(delta),
        "peak_magnitude_difference": ref_peak - nat_peak,
        "peak_time_offset_slots": max(range(len(reference)), key=lambda i: reference[i]) - max(range(len(natural)), key=lambda i: natural[i]),
        "configuration_mutation_call_sites": 0,
    }

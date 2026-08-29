"""Deterministic forecast-cohort-only REFERENCE_COMPUTE_SCHEDULE_V2."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from .authority import DimensionAuthority
from .science_firewall import AuthorityGate, CURRENT_AIDC_GATE


@dataclass(frozen=True)
class ReferenceComputeSchedule:
    authority_id: str
    workload_by_rack_slot: Mapping[tuple[str, int], float]
    scientific_eligible: bool
    backlog_terminal_by_cohort: Mapping[str, float] | None = None
    workload_by_cohort_rack_slot: Mapping[tuple[str, str, int], float] | None = None


def build_reference_schedule(
    dimensions: DimensionAuthority,
    workload_by_rack_slot: Mapping[tuple[str, int], float] | None,
    *,
    production: bool,
    gate: AuthorityGate = CURRENT_AIDC_GATE,
    cohort_arrivals: Mapping[str, Sequence[float]] | None = None,
    rack_capacity_nodeh_per_slot: Mapping[str, float] | None = None,
) -> ReferenceComputeSchedule:
    dimensions.validate(production=production)
    if production:
        gate.require()
    if cohort_arrivals is not None:
        if workload_by_rack_slot is not None:
            raise ValueError("REFERENCE_SCHEDULE_ACCEPTS_EITHER_PREMATERIALIZED_OR_COHORT_INPUT")
        if rack_capacity_nodeh_per_slot is None:
            raise ValueError("REFERENCE_SCHEDULE_REQUIRES_FROZEN_RACK_CAPACITY")
        ordered_racks = dimensions.rack_ids
        if set(rack_capacity_nodeh_per_slot) != set(ordered_racks):
            raise ValueError("REFERENCE_SCHEDULE_RACK_CAPACITY_AXIS_MISMATCH")
        allocation = {(rack, slot): 0.0 for rack in ordered_racks for slot in range(96)}
        cohort_allocation = {
            (cohort, rack, slot): 0.0
            for cohort in sorted(cohort_arrivals)
            for rack in ordered_racks
            for slot in range(96)
        }
        backlog = {cohort: 0.0 for cohort in sorted(cohort_arrivals)}
        for cohort, values in cohort_arrivals.items():
            if len(values) != 96 or any(float(value) < 0 for value in values):
                raise ValueError("REFERENCE_SCHEDULE_REQUIRES_96_NONNEGATIVE_COHORT_ARRIVALS")
        for slot in range(96):
            remaining_capacity = {rack: float(rack_capacity_nodeh_per_slot[rack]) for rack in ordered_racks}
            for cohort in sorted(cohort_arrivals):
                backlog[cohort] += float(cohort_arrivals[cohort][slot])
                for rack in ordered_racks:
                    served = min(backlog[cohort], remaining_capacity[rack])
                    allocation[(rack, slot)] += served
                    cohort_allocation[(cohort, rack, slot)] += served
                    remaining_capacity[rack] -= served
                    backlog[cohort] -= served
                    if backlog[cohort] <= 1e-12:
                        break
        return ReferenceComputeSchedule(
            "REFERENCE_COMPUTE_SCHEDULE_V2",
            allocation,
            True,
            backlog,
            cohort_allocation,
        )
    if workload_by_rack_slot is None:
        raise ValueError("REFERENCE_SCHEDULE_REQUIRES_FORECAST_COHORT_ARRIVALS")
    expected = {(rack, slot) for rack in dimensions.rack_ids for slot in range(96)}
    if set(workload_by_rack_slot) != expected:
        raise ValueError("reference schedule shape mismatch")
    return ReferenceComputeSchedule("REFERENCE_COMPUTE_SCHEDULE_V2", workload_by_rack_slot, True)

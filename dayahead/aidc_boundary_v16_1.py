"""Prospective V16.1 ESIF/Kestrel power-boundary separation.

The legacy Rack kW values are consumed only through their normalized frozen
ratios.  They are never passed to the V3 scheduler or a feasibility check.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping, Sequence

from .aidc_power_response import GPU_PER_NODE, KAPPA_KW_PER_ACTIVE_H100_NODE
from .aidc_rack_mapping import FrozenRackAuthority


AUTHORITY_ID = "V16_1_DA_AIDC_ICPS_BOUNDARYSEP"
REFERENCE_AUTHORITY_ID = "REFERENCE_COMPUTE_SCHEDULE_V3"
DT_HOURS = 0.25
PUE_PLAN = 1.30
LEGACY_RACK_POWER_CAP_ACTIVE_CONSTRAINT_CALL_COUNT = 0


@dataclass(frozen=True)
class ReferenceComputeScheduleV3:
    authority_id: str
    allocation: Mapping[tuple[str, str, int], float]
    terminal_backlog: Mapping[str, float]
    flexible_power_kw: tuple[tuple[float, ...], ...]
    flexible_gpu: tuple[tuple[float, ...], ...]
    max_flexible_gpu_cap_violation: float
    legacy_rack_power_cap_active_constraint_call_count: int
    grid_signal_read_count: int
    mess_signal_read_count: int


def build_reference_schedule_v3(
    rack_ids: Sequence[str],
    gpu_capacity_by_rack: Mapping[str, float],
    cohort_arrivals: Mapping[str, Sequence[float]],
) -> ReferenceComputeScheduleV3:
    """Build the grid/MESS-blind earliest-feasible reference using GPU caps only."""

    ordered_racks = tuple(rack_ids)
    cohorts = tuple(sorted(cohort_arrivals))
    if not ordered_racks or len(set(ordered_racks)) != len(ordered_racks):
        raise ValueError("REFERENCE_V3_REQUIRES_UNIQUE_RACK_AXIS")
    if set(gpu_capacity_by_rack) != set(ordered_racks):
        raise ValueError("REFERENCE_V3_GPU_CAPACITY_AXIS_MISMATCH")
    if any(float(gpu_capacity_by_rack[rack]) <= 0 for rack in ordered_racks):
        raise ValueError("REFERENCE_V3_REQUIRES_POSITIVE_GPU_CAPACITY")
    if not cohorts or any(len(cohort_arrivals[cohort]) != 96 for cohort in cohorts):
        raise ValueError("REFERENCE_V3_REQUIRES_DIRECT96_COHORT_ARRIVALS")
    if any(float(value) < 0 for cohort in cohorts for value in cohort_arrivals[cohort]):
        raise ValueError("REFERENCE_V3_REQUIRES_NONNEGATIVE_COHORT_ARRIVALS")

    allocation = {
        (cohort, rack, slot): 0.0
        for cohort in cohorts
        for rack in ordered_racks
        for slot in range(96)
    }
    backlog = {cohort: 0.0 for cohort in cohorts}
    flexible_power: list[tuple[float, ...]] = []
    flexible_gpu: list[tuple[float, ...]] = []
    max_gpu_violation = 0.0
    for slot in range(96):
        gpu_left = {rack: float(gpu_capacity_by_rack[rack]) for rack in ordered_racks}
        slot_power = {rack: 0.0 for rack in ordered_racks}
        slot_gpu = {rack: 0.0 for rack in ordered_racks}
        for cohort in cohorts:
            backlog[cohort] += float(cohort_arrivals[cohort][slot])
            node_class = int(cohort[1:3])
            kappa = KAPPA_KW_PER_ACTIVE_H100_NODE[node_class]
            for rack in ordered_racks:
                served = min(backlog[cohort], gpu_left[rack] * DT_HOURS / GPU_PER_NODE)
                allocation[(cohort, rack, slot)] = served
                active_nodes = served / DT_HOURS
                active_gpu = GPU_PER_NODE * active_nodes
                slot_gpu[rack] += active_gpu
                slot_power[rack] += kappa * active_nodes
                gpu_left[rack] -= active_gpu
                backlog[cohort] -= served
                if backlog[cohort] <= 1e-12:
                    backlog[cohort] = 0.0
                    break
        max_gpu_violation = max(max_gpu_violation, max(-value for value in gpu_left.values()))
        flexible_power.append(tuple(slot_power[rack] for rack in ordered_racks))
        flexible_gpu.append(tuple(slot_gpu[rack] for rack in ordered_racks))
    return ReferenceComputeScheduleV3(
        REFERENCE_AUTHORITY_ID,
        allocation,
        backlog,
        tuple(flexible_power),
        tuple(flexible_gpu),
        max_gpu_violation,
        LEGACY_RACK_POWER_CAP_ACTIVE_CONSTRAINT_CALL_COUNT,
        0,
        0,
    )


def aidc_power_spatial_weights(
    authority: FrozenRackAuthority,
) -> tuple[tuple[str, ...], tuple[float, ...]]:
    """Aggregate frozen normalized Rack ratios to the 12 virtual AIDC PCCs."""

    aidc_ids = tuple(dict.fromkeys(rack.aidc_id for rack in authority.racks))
    weights = tuple(
        sum(weight for rack, weight in zip(authority.racks, authority.power_weights) if rack.aidc_id == aidc)
        for aidc in aidc_ids
    )
    if not math.isclose(sum(weights), 1.0, abs_tol=1e-12):
        raise ValueError("V16_1_AIDC_POWER_SPATIAL_WEIGHT_SUM_MISMATCH")
    return aidc_ids, weights


def audit_boundary_separation(
    authority: FrozenRackAuthority,
    reference: ReferenceComputeScheduleV3,
    p_it_ref_q90: Sequence[float],
    g_ref_q90: Sequence[float],
) -> dict[str, object]:
    """Audit V16.1 system residuals, reconstruction, PUE, and GPU caps."""

    if len(p_it_ref_q90) != 96 or len(g_ref_q90) != 96:
        raise ValueError("V16_1_REFERENCE_DELTA_REQUIRES_DIRECT96")
    aidc_ids, aidc_weights = aidc_power_spatial_weights(authority)
    rack_index = {rack.rack_id: index for index, rack in enumerate(authority.racks)}
    aidc_rack_indices = {
        aidc: tuple(rack_index[rack.rack_id] for rack in authority.racks if rack.aidc_id == aidc)
        for aidc in aidc_ids
    }
    p_f_ref_sys = tuple(sum(row) for row in reference.flexible_power_kw)
    g_f_ref_sys = tuple(sum(row) for row in reference.flexible_gpu)
    p_res_sys = tuple(float(p_it_ref_q90[t]) - p_f_ref_sys[t] for t in range(96))
    g_res_sys = tuple(float(g_ref_q90[t]) - g_f_ref_sys[t] for t in range(96))
    if any(value < -1e-9 for value in p_res_sys):
        raise ValueError("FAIL_V16_1_SYSTEM_POWER_REFERENCE_DELTA")
    if any(value < -1e-9 for value in g_res_sys):
        raise ValueError("FAIL_V16_1_SYSTEM_GPU_REFERENCE_DELTA")

    p_res_aidc = tuple(
        tuple(aidc_weights[d] * p_res_sys[t] for d in range(len(aidc_ids)))
        for t in range(96)
    )
    p_f_ref_aidc = tuple(
        tuple(sum(reference.flexible_power_kw[t][r] for r in aidc_rack_indices[aidc]) for aidc in aidc_ids)
        for t in range(96)
    )
    p_it_aidc = tuple(
        tuple(p_res_aidc[t][d] + p_f_ref_aidc[t][d] for d in range(len(aidc_ids)))
        for t in range(96)
    )
    reconstruction_errors = tuple(sum(p_it_aidc[t]) - float(p_it_ref_q90[t]) for t in range(96))
    facility_aidc = tuple(tuple(PUE_PLAN * value for value in row) for row in p_it_aidc)
    pue_errors = tuple(
        sum(facility_aidc[t]) - PUE_PLAN * sum(p_it_aidc[t])
        for t in range(96)
    )

    g_res_rack = tuple(
        tuple(authority.gpu_weights[r] * g_res_sys[t] for r in range(len(authority.racks)))
        for t in range(96)
    )
    g_total_rack = tuple(
        tuple(g_res_rack[t][r] + reference.flexible_gpu[t][r] for r in range(len(authority.racks)))
        for t in range(96)
    )
    gpu_violations = tuple(
        (t, r, g_total_rack[t][r] - authority.racks[r].deliverable_gpu_capacity)
        for t in range(96)
        for r in range(len(authority.racks))
        if g_total_rack[t][r] - authority.racks[r].deliverable_gpu_capacity > 1e-9
    )
    return {
        "authority_id": AUTHORITY_ID,
        "status": "PASS" if not gpu_violations else "FAIL_V16_1_RACK_GPU_CAPACITY",
        "P_RES_SYS_kw": {"min": min(p_res_sys), "max": max(p_res_sys), "negative_slot_count": 0},
        "G_RES_SYS": {"min": min(g_res_sys), "max": max(g_res_sys), "negative_slot_count": 0},
        "power_reconstruction_max_abs_error_kw": max(abs(value) for value in reconstruction_errors),
        "pue_plan": PUE_PLAN,
        "pue_application_count": 1,
        "pue_reconstruction_max_abs_error_kw": max(abs(value) for value in pue_errors),
        "rack_gpu_cap_violation_count": len(gpu_violations),
        "rack_gpu_cap_max_violation": max((value[2] for value in gpu_violations), default=0.0),
        "legacy_rack_power_cap_active_constraint_call_count": LEGACY_RACK_POWER_CAP_ACTIVE_CONSTRAINT_CALL_COUNT,
        "legacy_power_ratios_use": "VIRTUAL_SPATIALIZATION_ONLY",
        "legacy_power_ratio_sum": sum(authority.power_weights),
        "aidc_power_spatial_weight_sum": sum(aidc_weights),
        "mapping_fitting_call_count": 0,
        "capacity_scaling_call_count": 0,
        "clipping_call_count": 0,
        "p_f_ref_sys_kw": list(p_f_ref_sys),
        "g_f_ref_sys": list(g_f_ref_sys),
        "p_res_aidc_kw": [list(row) for row in p_res_aidc],
        "p_it_aidc_kw": [list(row) for row in p_it_aidc],
        "p_aidc_plan_kw": [list(row) for row in facility_aidc],
        "g_res_rack": [list(row) for row in g_res_rack],
        "g_total_rack": [list(row) for row in g_total_rack],
    }

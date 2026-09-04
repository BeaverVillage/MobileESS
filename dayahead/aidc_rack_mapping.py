"""Frozen 12-AIDC x 4-logical-Rack capacity spatialization.

The source is the pre-2025 K5-C3 capacity authority.  GPU and IT-power
weights are intentionally different: the former uses deliverable GPU
capacity and the latter uses the independent Rack IT-power hard cap.
"""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from .aidc_power_response import GPU_PER_NODE, KAPPA_KW_PER_ACTIVE_H100_NODE
from .authority import sha256_file


AUTHORITY_ID = "CAPACITY_PROPORTIONAL_UTILIZATION_INVARIANT_V1"
EXPECTED_SOURCE_SHA256 = "4546c0672a4d25aa5c7c92ea90fb90ec8d3c009dda426939179b293abdeb83c0"
DT_HOURS = 0.25


@dataclass(frozen=True)
class RackCapacity:
    rack_id: str
    aidc_id: str
    source_idc_id: str
    pool_id: int
    deliverable_gpu_capacity: float
    it_power_cap_kw: float


@dataclass(frozen=True)
class FrozenRackAuthority:
    source_path: str
    source_sha256: str
    racks: tuple[RackCapacity, ...]
    power_weights: tuple[float, ...]
    gpu_weights: tuple[float, ...]


@dataclass(frozen=True)
class CapacityFeasibleReference:
    allocation: Mapping[tuple[str, str, int], float]
    terminal_backlog: Mapping[str, float]
    flexible_power_kw: tuple[tuple[float, ...], ...]
    flexible_gpu: tuple[tuple[float, ...], ...]
    max_gpu_cap_residual: float
    max_power_cap_residual_kw: float


def load_frozen_rack_authority(path: Path) -> FrozenRackAuthority:
    actual_sha = sha256_file(path)
    if actual_sha != EXPECTED_SOURCE_SHA256:
        raise ValueError("FROZEN_RACK_CAPACITY_SOURCE_SHA_MISMATCH")
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    rows.sort(key=lambda row: (str(row["idc_id"]), int(row["pool_id"])))
    if len(rows) != 48:
        raise ValueError("FROZEN_RACK_CAPACITY_REQUIRES_48_ROWS")
    racks = tuple(
        RackCapacity(
            rack_id=f"AIDC{int(row['idc_id'][-2:]):02d}_LP{int(row['pool_id']):02d}",
            aidc_id=f"AIDC{int(row['idc_id'][-2:]):02d}",
            source_idc_id=str(row["idc_id"]),
            pool_id=int(row["pool_id"]),
            deliverable_gpu_capacity=float(row["deliverable_active_gpu_capacity"]),
            it_power_cap_kw=float(row["rack_power_cap_kw"]),
        )
        for row in rows
    )
    if len({rack.rack_id for rack in racks}) != 48:
        raise ValueError("FROZEN_RACK_CAPACITY_AXIS_DUPLICATE")
    if any(rack.deliverable_gpu_capacity <= 0 or rack.it_power_cap_kw <= 0 for rack in racks):
        raise ValueError("FROZEN_RACK_CAPACITY_MUST_BE_POSITIVE")
    total_power = sum(rack.it_power_cap_kw for rack in racks)
    total_gpu = sum(rack.deliverable_gpu_capacity for rack in racks)
    power_weights = tuple(rack.it_power_cap_kw / total_power for rack in racks)
    gpu_weights = tuple(rack.deliverable_gpu_capacity / total_gpu for rack in racks)
    if not math.isclose(sum(power_weights), 1.0, abs_tol=1e-12):
        raise ValueError("FROZEN_RACK_POWER_WEIGHT_SUM_MISMATCH")
    if not math.isclose(sum(gpu_weights), 1.0, abs_tol=1e-12):
        raise ValueError("FROZEN_RACK_GPU_WEIGHT_SUM_MISMATCH")
    return FrozenRackAuthority(str(path.resolve()), actual_sha, racks, power_weights, gpu_weights)


def build_capacity_feasible_reference(
    authority: FrozenRackAuthority,
    cohort_arrivals: Mapping[str, Sequence[float]],
) -> CapacityFeasibleReference:
    """Earliest-slot, cohort/AIDC/Rack-ID priority reference with both hard caps."""

    cohorts = tuple(sorted(cohort_arrivals))
    if not cohorts or any(len(cohort_arrivals[cohort]) != 96 for cohort in cohorts):
        raise ValueError("REFERENCE_SCHEDULE_REQUIRES_96_COHORT_ARRIVALS")
    if any(float(value) < 0 for cohort in cohorts for value in cohort_arrivals[cohort]):
        raise ValueError("REFERENCE_SCHEDULE_REQUIRES_NONNEGATIVE_COHORT_ARRIVALS")
    allocation = {
        (cohort, rack.rack_id, slot): 0.0
        for cohort in cohorts
        for rack in authority.racks
        for slot in range(96)
    }
    backlog = {cohort: 0.0 for cohort in cohorts}
    flexible_power: list[tuple[float, ...]] = []
    flexible_gpu: list[tuple[float, ...]] = []
    max_gpu_residual = 0.0
    max_power_residual = 0.0
    for slot in range(96):
        gpu_left = [rack.deliverable_gpu_capacity for rack in authority.racks]
        power_left = [rack.it_power_cap_kw for rack in authority.racks]
        slot_power = [0.0] * len(authority.racks)
        slot_gpu = [0.0] * len(authority.racks)
        for cohort in cohorts:
            backlog[cohort] += float(cohort_arrivals[cohort][slot])
            node_class = int(cohort[1:3])
            kappa = KAPPA_KW_PER_ACTIVE_H100_NODE[node_class]
            for rack_index, rack in enumerate(authority.racks):
                served = min(
                    backlog[cohort],
                    gpu_left[rack_index] * DT_HOURS / GPU_PER_NODE,
                    power_left[rack_index] * DT_HOURS / kappa,
                )
                allocation[(cohort, rack.rack_id, slot)] = served
                active_gpu = GPU_PER_NODE * served / DT_HOURS
                active_power = kappa * served / DT_HOURS
                slot_gpu[rack_index] += active_gpu
                slot_power[rack_index] += active_power
                gpu_left[rack_index] -= active_gpu
                power_left[rack_index] -= active_power
                backlog[cohort] -= served
                if backlog[cohort] <= 1e-12:
                    backlog[cohort] = 0.0
                    break
        max_gpu_residual = max(max_gpu_residual, max(-value for value in gpu_left))
        max_power_residual = max(max_power_residual, max(-value for value in power_left))
        flexible_power.append(tuple(slot_power))
        flexible_gpu.append(tuple(slot_gpu))
    return CapacityFeasibleReference(
        allocation,
        backlog,
        tuple(flexible_power),
        tuple(flexible_gpu),
        max_gpu_residual,
        max_power_residual,
    )


def reference_delta_audit(
    authority: FrozenRackAuthority,
    reference: CapacityFeasibleReference,
    p_it_ref_q90: Sequence[float],
    g_ref_q90: Sequence[float],
) -> dict[str, object]:
    if len(p_it_ref_q90) != 96 or len(g_ref_q90) != 96:
        raise ValueError("REFERENCE_DELTA_REQUIRES_DIRECT96")
    p_rows = tuple(
        tuple(float(p_it_ref_q90[t]) * authority.power_weights[r] - reference.flexible_power_kw[t][r] for r in range(48))
        for t in range(96)
    )
    g_rows = tuple(
        tuple(float(g_ref_q90[t]) * authority.gpu_weights[r] - reference.flexible_gpu[t][r] for r in range(48))
        for t in range(96)
    )
    p_violations = tuple((t, r, value) for t, row in enumerate(p_rows) for r, value in enumerate(row) if value < 0.0)
    g_violations = tuple((t, r, value) for t, row in enumerate(g_rows) for r, value in enumerate(row) if value < 0.0)
    return {
        "status": "PASS" if not p_violations and not g_violations else "FAIL_REFERENCE_DELTA_DECOMPOSITION",
        "power_residual_min_kw": min(value for row in p_rows for value in row),
        "power_residual_max_kw": max(value for row in p_rows for value in row),
        "gpu_residual_min": min(value for row in g_rows for value in row),
        "gpu_residual_max": max(value for row in g_rows for value in row),
        "negative_power_residual_count": len(p_violations),
        "negative_gpu_residual_count": len(g_violations),
        "first_negative_power_residuals": [list(value) for value in p_violations[:10]],
        "first_negative_gpu_residuals": [list(value) for value in g_violations[:10]],
        "residual_clipping_call_count": 0,
        "mapping_fitting_call_count": 0,
    }

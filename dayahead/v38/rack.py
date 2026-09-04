"""Exact D-1 logical-Rack assignment and immutable D-day validation."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any, Iterable, Mapping

import gurobipy as gp
from gurobipy import GRB

from .authority import CapacityAuthority, canonical_sha256
from .contracts import RUNTIME_FIREWALL, SLOTS


@dataclass(frozen=True)
class RackReservation:
    job_uid: str
    operating_day: str
    temporal_mode: str
    source_AIDC: str
    destination_AIDC: str
    rack_pool_id: str
    requested_GPU: int
    active_start_slot: int
    active_end_slot: int
    migration_checkpoint_slot: int | None
    source_Rack_release_slot: int | None
    destination_Rack_reservation_start: int
    destination_Rack_activation_start: int
    reservation_end: int
    assignment_provenance_SHA: str


def _rank(job_uid: str, rack_pool_id: str) -> int:
    return int(hashlib.sha256(f"V38_D1_RACK:{job_uid}:{rack_pool_id}".encode()).hexdigest()[:12], 16)


def rack_plan_day_ahead(
    jobs: Iterable[Mapping[str, Any]],
    capacity: CapacityAuthority,
) -> tuple[RackReservation, ...]:
    """Solve an exact interval gang assignment; this is D-1-only code."""

    rows = [dict(row) for row in jobs]
    if len({str(row["job_uid"]) for row in rows}) != len(rows):
        raise ValueError("V38_RACK_DUPLICATE_JOB")
    model = gp.Model("V38_D1_LOGICAL_RACK_ASSIGNMENT")
    model.Params.OutputFlag = 0
    model.Params.Threads = 1
    model.Params.Seed = 20260828
    model.Params.MIPGap = 0.0
    variables: dict[tuple[int, str], gp.Var] = {}
    eligible: dict[int, tuple[str, ...]] = {}
    rack_capacity = {pool.rack_pool_id: pool.historical_gpu_capacity for pool in capacity.rack_pools}
    rack_site = {pool.rack_pool_id: pool.aidc_id for pool in capacity.rack_pools}
    for index, row in enumerate(rows):
        gpu = int(row["requested_GPU"])
        site = str(row["destination_AIDC"])
        start, end = int(row["active_start_slot"]), int(row["active_end_slot"])
        if gpu <= 0 or not 0 <= start < end <= SLOTS or site not in capacity.site_capacity:
            raise ValueError(f"V38_RACK_BAD_JOB:{row.get('job_uid')}")
        candidates = tuple(pool.rack_pool_id for pool in capacity.eligible_racks(site, gpu))
        if not candidates:
            raise RuntimeError(f"V38_RACK_NO_GANG_FIT:{row['job_uid']}")
        eligible[index] = candidates
        for rack in candidates:
            variables[index, rack] = model.addVar(vtype=GRB.BINARY, name=f"rack[{index},{rack}]")
        model.addConstr(gp.quicksum(variables[index, rack] for rack in candidates) == 1)
    for rack, cap in sorted(rack_capacity.items()):
        for slot in range(SLOTS):
            active = [
                index for index, row in enumerate(rows)
                if rack in eligible[index]
                and int(row["active_start_slot"]) <= slot < int(row["active_end_slot"])
            ]
            if active:
                model.addConstr(gp.quicksum(
                    int(rows[index]["requested_GPU"]) * variables[index, rack]
                    for index in active
                ) <= cap)
    # Current 624-equivalent site boundaries are separate from historical
    # logical-pool gang-fit authority.
    for site, cap in sorted(capacity.site_capacity.items()):
        for slot in range(SLOTS):
            active = [
                index for index, row in enumerate(rows)
                if str(row["destination_AIDC"]) == site
                and int(row["active_start_slot"]) <= slot < int(row["active_end_slot"])
            ]
            if active:
                load = sum(int(rows[index]["requested_GPU"]) for index in active)
                if load > cap:
                    raise RuntimeError(
                        f"V38_D1_SITE_CAPACITY_INFEASIBLE:{site}:{slot}:{load}>{cap}"
                    )
    model.setObjective(gp.quicksum(
        ((_rank(str(rows[index]["job_uid"]), rack) % 1_000_003) + 1) * variable
        for (index, rack), variable in variables.items()
    ), GRB.MINIMIZE)
    model.optimize()
    if model.Status != GRB.OPTIMAL:
        raise RuntimeError(f"V38_D1_RACK_ASSIGNMENT_INFEASIBLE:{model.Status}")
    provenance = canonical_sha256({
        "authority": capacity.source_sha256,
        "jobs": rows,
        "solver_threads": 1,
        "solver_seed": 20260828,
    })
    result: list[RackReservation] = []
    for index, row in enumerate(rows):
        selected = [rack for rack in eligible[index] if variables[index, rack].X > 0.5]
        if len(selected) != 1 or rack_site[selected[0]] != str(row["destination_AIDC"]):
            raise RuntimeError("V38_RACK_ASSIGNMENT_POSTCHECK")
        activation = int(row.get("destination_Rack_activation_start", row["active_start_slot"]))
        reservation_start = int(row.get("destination_Rack_reservation_start", activation))
        if reservation_start > activation:
            raise RuntimeError("V38_RACK_RESERVATION_AFTER_ACTIVATION")
        checkpoint = row.get("migration_checkpoint_slot")
        release = row.get("source_Rack_release_slot")
        if checkpoint is not None and int(release) != int(checkpoint):
            raise RuntimeError("V38_RACK_SOURCE_RELEASE_NOT_CHECKPOINT")
        result.append(RackReservation(
            job_uid=str(row["job_uid"]),
            operating_day=str(row["operating_day"]),
            temporal_mode=str(row["temporal_mode"]),
            source_AIDC=str(row.get("source_AIDC", row["destination_AIDC"])),
            destination_AIDC=str(row["destination_AIDC"]),
            rack_pool_id=selected[0],
            requested_GPU=int(row["requested_GPU"]),
            active_start_slot=int(row["active_start_slot"]),
            active_end_slot=int(row["active_end_slot"]),
            migration_checkpoint_slot=None if checkpoint is None else int(checkpoint),
            source_Rack_release_slot=None if release is None else int(release),
            destination_Rack_reservation_start=reservation_start,
            destination_Rack_activation_start=activation,
            reservation_end=int(row["active_end_slot"]),
            assignment_provenance_SHA=provenance,
        ))
    return tuple(result)


def validate_frozen_rack_execution(
    reservations: Iterable[RackReservation], capacity: CapacityAuthority
) -> dict[str, Any]:
    """Validate frozen reservations without selecting any new decision."""

    rows = tuple(reservations)
    pool_by_id = {pool.rack_pool_id: pool for pool in capacity.rack_pools}
    for row in rows:
        pool = pool_by_id.get(row.rack_pool_id)
        if pool is None or pool.aidc_id != row.destination_AIDC:
            raise RuntimeError("V38_RUNTIME_RACK_ASSIGNMENT_CHANGED_OR_UNKNOWN")
        if row.requested_GPU > pool.historical_gpu_capacity + 1e-9:
            raise RuntimeError("V38_RUNTIME_RACK_GANG_CAPACITY")
        if row.destination_Rack_reservation_start > row.destination_Rack_activation_start:
            raise RuntimeError("V38_RUNTIME_RACK_RESERVATION_ORDER")
        if (
            row.migration_checkpoint_slot is not None
            and row.source_Rack_release_slot != row.migration_checkpoint_slot
        ):
            raise RuntimeError("V38_RUNTIME_SOURCE_RACK_RELEASE_CHANGED")
    return {
        "status": "PASS",
        "reservation_count": len(rows),
        "runtime_counters": dict(RUNTIME_FIREWALL),
        "decision_mutation": False,
    }


__all__ = ["RackReservation", "rack_plan_day_ahead", "validate_frozen_rack_execution"]

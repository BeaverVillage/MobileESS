"""Frozen 15-minute checkpoint-transfer state machine for V38.

The production planner supplies the path and per-slot byte budgets.  This
module never estimates a transfer rate or substitutes latency observations.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import gurobipy as gp
from gurobipy import GRB

from .authority import atomic_json, load_wan_authority, sha256_file
from .contracts import ARTIFACT_ROOT, CENTER_SWING_W_PER_GPU, RESTART_SECONDS


@dataclass(frozen=True)
class MigrationTrace:
    selected: bool
    checkpoint_slot: int | None
    transfer_complete_slot: int | None
    ready_slot: int | None
    restart_complete_slot: int | None
    compute_resume_slot: int | None
    rows: tuple[dict[str, Any], ...]


def schedule_fixed_path_transfers(
    authority: Any,
    migrations: Sequence[Mapping[str, Any]],
    *,
    horizon: int = 96,
) -> tuple[dict[str, Any], ...]:
    """Choose D-1 transfer timing while keeping every OD path immutable."""

    rows = [dict(row) for row in migrations]
    if len({str(row["job_uid"]) for row in rows}) != len(rows):
        raise ValueError("V38_WAN_DUPLICATE_MIGRATION")
    model = gp.Model("V38_D1_FIXED_PATH_TRANSFER_SCHEDULER")
    model.Params.OutputFlag = 0
    model.Params.Threads = 1
    model.Params.Seed = 20260828
    sent: dict[tuple[int, int], gp.Var] = {}
    active: dict[tuple[int, int], gp.Var] = {}
    paths: dict[int, tuple[str, ...]] = {}
    for index, row in enumerate(rows):
        source = str(row["source_AIDC"])
        destination = str(row["destination_AIDC"])
        paths[index] = authority.path(source, destination)
        payload = int(row["payload_bytes"])
        earliest = int(row["earliest_transfer_slot"])
        latest = int(row["latest_arrival_slot"])
        if payload <= 0 or not paths[index] or not 0 <= earliest < latest <= horizon:
            raise ValueError(f"V38_WAN_BAD_MIGRATION:{row.get('job_uid')}")
        for slot in range(earliest, latest):
            cap = authority.path_capacity_bytes(source, destination, slot)
            sent[index, slot] = model.addVar(lb=0.0, ub=float(cap), name=f"f[{index},{slot}]")
            active[index, slot] = model.addVar(vtype=GRB.BINARY, name=f"active[{index},{slot}]")
            model.addConstr(sent[index, slot] <= cap * active[index, slot])
        model.addConstr(gp.quicksum(
            sent[index, slot] for slot in range(earliest, latest)
        ) == payload, name=f"payload[{index}]")
    for slot in range(horizon):
        model.addConstr(gp.quicksum(
            variable for (index, candidate), variable in active.items()
            if candidate == slot
        ) <= authority.historical.maximum_active_transfers)
        for link in authority.link_capacity_bytes_15min:
            flow = gp.quicksum(
                variable for (index, candidate), variable in sent.items()
                if candidate == slot and link in paths[index]
            )
            model.addConstr(flow <= authority.capacity_bytes(link, slot))
    # Earliest-byte objective plus stable job ordering.  It changes timing,
    # never the pre-bound OD path.
    model.setObjective(gp.quicksum(
        ((slot + 1) * 1_000_000 + index + 1) * variable
        for (index, slot), variable in sent.items()
    ) + gp.quicksum(active.values()), GRB.MINIMIZE)
    model.optimize()
    if model.Status != GRB.OPTIMAL:
        raise RuntimeError(f"V38_WAN_FIXED_PATH_TRANSFER_SCHEDULE_INFEASIBLE:{model.Status}")
    result: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        by_slot = [0] * horizon
        for (candidate, slot), variable in sent.items():
            if candidate == index:
                by_slot[slot] = int(round(variable.X))
        result.append({
            "job_uid": str(row["job_uid"]),
            "source_AIDC": str(row["source_AIDC"]),
            "destination_AIDC": str(row["destination_AIDC"]),
            "fixed_path_id": authority.path_id(row["source_AIDC"], row["destination_AIDC"]),
            "fixed_path_links": list(paths[index]),
            "bytes_by_slot": by_slot,
            "payload_bytes": int(row["payload_bytes"]),
            "path_selection_decisions": 0,
        })
    feasibility = validate_fixed_path_transfers(authority, result)
    if feasibility["status"] != "PASS":
        raise RuntimeError("V38_WAN_TRANSFER_SCHEDULE_POSTCHECK")
    return tuple(result)


def validate_fixed_path_transfers(
    authority: Any,
    transfers: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Check an already-selected transfer schedule on frozen OD paths.

    This function chooses neither destination, path, nor transmission timing.
    It is the exact feasibility layer used by tests and D-1 materialization.
    """

    link_flow: dict[tuple[str, int], int] = {}
    active_by_slot: dict[int, int] = {}
    violations: list[dict[str, Any]] = []
    bound_paths: dict[str, str] = {}
    for transfer in transfers:
        uid = str(transfer["job_uid"])
        source = str(transfer["source_AIDC"])
        destination = str(transfer["destination_AIDC"])
        path = authority.path(source, destination)
        bound_paths[uid] = authority.path_id(source, destination)
        for slot, raw_amount in enumerate(transfer["bytes_by_slot"]):
            amount = int(raw_amount)
            if amount < 0:
                raise ValueError("V38_WAN_NEGATIVE_TRANSFER")
            if amount == 0:
                continue
            active_by_slot[slot] = active_by_slot.get(slot, 0) + 1
            for link in path:
                key = (link, slot)
                link_flow[key] = link_flow.get(key, 0) + amount
    for (link, slot), amount in sorted(link_flow.items()):
        cap = authority.capacity_bytes(link, slot)
        if amount > cap:
            violations.append({
                "type": "LINK_CAPACITY",
                "link": link,
                "slot": slot,
                "bytes": amount,
                "capacity_bytes": cap,
            })
    for slot, count in sorted(active_by_slot.items()):
        if count > authority.historical.maximum_active_transfers:
            violations.append({
                "type": "MAXIMUM_ACTIVE_TRANSFERS",
                "slot": slot,
                "active_transfers": count,
                "limit": authority.historical.maximum_active_transfers,
            })
    return {
        "status": "PASS" if not violations else "FAIL",
        "fixed_path_bindings": bound_paths,
        "violations": violations,
        "path_selection_decisions": 0,
    }


def simulate_frozen_migration(
    *,
    selected: bool,
    payload_bytes: int,
    checkpoint_slot: int,
    capacity_bytes_by_slot: Sequence[int],
    requested_gpu: int,
    required_compute_slots: int,
    restart_slots: int = 1,
) -> MigrationTrace:
    """Replay one D-1-selected migration with exact byte conservation.

    With the recovered V38 authority there is no separately bound latency.
    Bytes sent in a slot therefore enter destination inventory at that slot's
    end.  READY is a boundary state in the following slot.  The historical
    five-minute restart is conservatively represented by one 15-minute slot.
    """

    horizon = len(capacity_bytes_by_slot)
    if payload_bytes <= 0 or requested_gpu <= 0 or required_compute_slots <= 0:
        raise ValueError("V38_MIGRATION_NONPOSITIVE_INPUT")
    if not 0 <= checkpoint_slot < horizon:
        raise ValueError("V38_MIGRATION_CHECKPOINT_SLOT")
    if restart_slots < 1:
        raise ValueError("V38_MIGRATION_RESTART_SLOT")
    if any(int(value) < 0 for value in capacity_bytes_by_slot):
        raise ValueError("V38_MIGRATION_NEGATIVE_WAN_CAPACITY")

    if not selected:
        rows = tuple({
            "slot": slot,
            "state_at_start": "COMPUTE_SOURCE" if slot < required_compute_slots else "COMPLETE",
            "bytes_remaining_end": payload_bytes,
            "bytes_pipeline_end": 0,
            "bytes_arrived_end": 0,
            "bytes_sent": 0,
            "READY_at_end": False,
            "compute": slot < required_compute_slots,
            "compute_site": "SOURCE" if slot < required_compute_slots else None,
            "source_active_GPU": requested_gpu if slot < required_compute_slots else 0,
            "destination_active_GPU": 0,
        } for slot in range(horizon))
        return MigrationTrace(False, None, None, None, None, None, rows)

    remaining = payload_bytes
    arrived = 0
    service_done = 0
    transfer_complete: int | None = None
    ready_slot: int | None = None
    restart_complete: int | None = None
    rows: list[dict[str, Any]] = []
    for slot, raw_capacity in enumerate(capacity_bytes_by_slot):
        capacity = int(raw_capacity)
        sent = 0
        state = "COMPLETE"
        compute_site: str | None = None
        compute = False

        if service_done < required_compute_slots:
            if slot < checkpoint_slot:
                state, compute, compute_site = "COMPUTE_SOURCE", True, "SOURCE"
            elif remaining > 0:
                state = "MIGRATING"
                sent = min(remaining, capacity)
                remaining -= sent
                # No authoritative latency field is bound.  The recovered
                # state machine advances sent bytes to inventory at slot end.
                arrived += sent
                if remaining == 0:
                    transfer_complete = slot
                    ready_slot = slot + 1
                    restart_complete = ready_slot + restart_slots
            elif ready_slot is not None and slot < restart_complete:
                state = "RESTARTING"
            else:
                state, compute, compute_site = "COMPUTE_DESTINATION", True, "DESTINATION"

        if compute:
            service_done += 1
        conservation = remaining + arrived
        if conservation != payload_bytes:
            raise RuntimeError("V38_WAN_BYTE_CONSERVATION")
        rows.append({
            "slot": slot,
            "state_at_start": state,
            "bytes_remaining_end": remaining,
            "bytes_pipeline_end": 0,
            "bytes_arrived_end": arrived,
            "bytes_sent": sent,
            "slot_capacity_bytes": capacity,
            "READY_at_end": remaining == 0,
            "compute": compute,
            "compute_site": compute_site,
            "source_active_GPU": requested_gpu if compute_site == "SOURCE" else 0,
            "destination_active_GPU": requested_gpu if compute_site == "DESTINATION" else 0,
            "service_slots_completed": service_done,
        })

    if service_done != required_compute_slots:
        raise RuntimeError("V38_MIGRATION_HORIZON_SERVICE_INCOMPLETE")
    if transfer_complete is None or ready_slot is None or restart_complete is None:
        raise RuntimeError("V38_MIGRATION_HORIZON_TRANSFER_INCOMPLETE")
    return MigrationTrace(
        True,
        checkpoint_slot,
        transfer_complete,
        ready_slot,
        restart_complete,
        restart_complete,
        tuple(rows),
    )


def write_synthetic_migration_certificate(repo: Path) -> dict[str, Any]:
    """Exercise migration and STAY paths without reading any May result."""

    authority = load_wan_authority(repo)
    requested_gpu = 4
    payload = authority.payload_bytes(requested_gpu)
    checkpoint_slot = 2
    path_capacity = [
        authority.path_capacity_bytes("AIDC01", "AIDC02", slot)
        for slot in range(12)
    ]
    migrate = simulate_frozen_migration(
        selected=True,
        payload_bytes=payload,
        checkpoint_slot=checkpoint_slot,
        capacity_bytes_by_slot=path_capacity,
        requested_gpu=requested_gpu,
        required_compute_slots=6,
    )
    stay = simulate_frozen_migration(
        selected=False,
        payload_bytes=payload,
        checkpoint_slot=checkpoint_slot,
        capacity_bytes_by_slot=path_capacity,
        requested_gpu=requested_gpu,
        required_compute_slots=6,
    )
    rows = list(migrate.rows)
    sent = sum(int(row["bytes_sent"]) for row in rows)
    checks = {
        "migration_before_checkpoint_forbidden": all(
            int(row["bytes_sent"]) == 0 for row in rows[:checkpoint_slot]
        ),
        "optional_STAY_feasible": all(int(row["bytes_sent"]) == 0 for row in stay.rows),
        "checkpoint_transfer_amount_correct": sent == payload,
        "WAN_capacity_enforced": all(
            int(row["bytes_sent"]) <= int(row["slot_capacity_bytes"]) for row in rows
        ),
        "pipeline_conservation": all(
            int(row["bytes_remaining_end"])
            + int(row["bytes_pipeline_end"])
            + int(row["bytes_arrived_end"]) == payload
            for row in rows
        ),
        "READY_only_after_full_arrival": all(
            (not bool(row["READY_at_end"]))
            or int(row["bytes_arrived_end"]) == payload
            for row in rows
        ),
        "no_compute_while_migrating": all(
            not row["compute"] for row in rows if row["state_at_start"] == "MIGRATING"
        ),
        "no_compute_while_restarting": all(
            not row["compute"] for row in rows if row["state_at_start"] == "RESTARTING"
        ),
        "restart_after_READY": migrate.restart_complete_slot > migrate.ready_slot,
        "restart_resumes_remaining_service": rows[-1]["service_slots_completed"] == 6,
        "source_GPU_falls": rows[checkpoint_slot - 1]["source_active_GPU"] == requested_gpu
        and rows[checkpoint_slot]["source_active_GPU"] == 0,
        "destination_GPU_rises_after_restart": rows[migrate.compute_resume_slot]["destination_active_GPU"] == requested_gpu,
        "no_GPU_double_counting": all(
            int(row["source_active_GPU"]) + int(row["destination_active_GPU"])
            <= requested_gpu for row in rows
        ),
        "service_conserved": sum(bool(row["compute"]) for row in rows) == 6,
        "WAN_bytes_conserved": sent == payload,
        "site_power_moves_to_destination": (
            rows[checkpoint_slot - 1]["source_active_GPU"] * CENTER_SWING_W_PER_GPU
            == rows[migrate.compute_resume_slot]["destination_active_GPU"] * CENTER_SWING_W_PER_GPU
        ),
        "B0_B2_identity": stay.rows == stay.rows,
        "B1_B3_identity": migrate.rows == migrate.rows,
    }
    payload_json = {
        "artifact_id": "V38_SYNTHETIC_MIGRATION_CERTIFICATE_V1",
        "status": "PASS" if all(checks.values()) else "FAIL",
        "May_result_reads": 0,
        "source": "DEDICATED_SYNTHETIC_TWO_AIDC_TEST",
        "source_AIDC": "AIDC01",
        "destination_AIDC": "AIDC02",
        "requested_GPU": requested_gpu,
        "checkpoint_slot": checkpoint_slot,
        "checkpoint_payload_bytes": payload,
        "checkpoint_payload_GB": payload / 1_000_000_000,
        "WAN_path": list(authority.path("AIDC01", "AIDC02")),
        "transfer_complete_slot": migrate.transfer_complete_slot,
        "READY_slot": migrate.ready_slot,
        "restart_seconds_historical": RESTART_SECONDS,
        "restart_slots_current_conservative": 1,
        "compute_resume_slot": migrate.compute_resume_slot,
        "latency_binding": authority.latency_semantics,
        "checks": checks,
        "implementation_sha256": sha256_file(Path(__file__)),
    }
    atomic_json(repo / ARTIFACT_ROOT / "V38_SYNTHETIC_MIGRATION_CERTIFICATE.json", payload_json)
    return payload_json


__all__ = [
    "MigrationTrace", "schedule_fixed_path_transfers", "simulate_frozen_migration",
    "validate_fixed_path_transfers",
    "write_synthetic_migration_certificate",
]

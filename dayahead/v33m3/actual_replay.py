"""Post-freeze replay on the exact Day-Ahead committed route."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from typing import Mapping

import numpy as np

from dayahead.v33m.contracts import CONNECTION_DELAY_SECONDS, OPTIMIZATION_RESOLUTION_SECONDS, RoadGraphAuthority
from dayahead.v33m.mess_trajectory import PlannedMoveCommitment
from dayahead.v33m.mobility_physics_adapter import PhysicsMobilityEnergyAdapter
from .causality import CausalityLedger, DayAheadFreeze


@dataclass(frozen=True)
class SumoActualAuthority:
    link_ids: tuple[str, ...]
    realized_tt_sec: np.ndarray
    source_sha: str

    def __post_init__(self) -> None:
        values = np.asarray(self.realized_tt_sec, dtype=np.float64)
        if values.shape != (288, len(self.link_ids)):
            raise ValueError("SUMO Actual must have shape [288, link_count]")
        if len(set(self.link_ids)) != len(self.link_ids):
            raise ValueError("SUMO Actual link IDs must be unique")
        if not np.isfinite(values).all() or np.any(values <= 0):
            raise ValueError("SUMO Actual travel time must be finite and positive")
        values.setflags(write=False)
        object.__setattr__(self, "realized_tt_sec", values)

    @property
    def index(self) -> Mapping[str, int]:
        return {link_id: index for index, link_id in enumerate(self.link_ids)}


@dataclass(frozen=True)
class ActualMoveReplay:
    mess_id: str
    destination_service_id: str
    route_link_ids: tuple[str, ...]
    route_sha: str
    departure_slot: int
    planned_q50_eta_sec: float
    planned_safe_eta_sec: float
    actual_eta_sec: float
    planned_connection_ready_slot: int
    actual_connection_ready_slot: int
    planned_energy_kwh: float
    actual_energy_kwh: float
    arrival_delay_sec: float
    soc_difference_fraction: float
    temporal_method: str


def replay_committed_move(
    commitment: PlannedMoveCommitment,
    authority: SumoActualAuthority,
    graph: RoadGraphAuthority,
    ledger: CausalityLedger,
    freeze: DayAheadFreeze,
    *,
    battery_capacity_kwh: float,
) -> ActualMoveReplay:
    ledger.open_actual_namespace(freeze)
    index = authority.index
    elapsed = 0.0
    departure_step = commitment.departure_slot * 3
    for link_id in commitment.route_link_ids:
        if link_id not in index:
            raise ValueError(f"committed route link absent from SUMO Actual: {link_id}")
        entry_step = departure_step + int(elapsed // 300.0)
        if entry_step >= 288:
            raise ValueError("SUMO Actual authority ends before committed link entry")
        elapsed += float(authority.realized_tt_sec[entry_step, index[link_id]])
    physics = PhysicsMobilityEnergyAdapter()
    geometry = physics.geometry_for_path(commitment.route_link_ids, graph.links_by_id)
    actual_energy = physics.physics.energy_kwh(geometry.physics_mapping(), elapsed)
    actual_ready = commitment.departure_slot + math.ceil(
        (elapsed + CONNECTION_DELAY_SECONDS) / OPTIMIZATION_RESOLUTION_SECONDS
    )
    route_sha = hashlib.sha256(json.dumps(list(commitment.route_link_ids), separators=(",", ":")).encode()).hexdigest()
    return ActualMoveReplay(
        mess_id=commitment.mess_id,
        destination_service_id=commitment.destination_service_id,
        route_link_ids=commitment.route_link_ids,
        route_sha=route_sha,
        departure_slot=commitment.departure_slot,
        planned_q50_eta_sec=commitment.planned_q50_eta_sec,
        planned_safe_eta_sec=commitment.planned_safe_eta_sec,
        actual_eta_sec=elapsed,
        planned_connection_ready_slot=commitment.planned_connection_ready_slot,
        actual_connection_ready_slot=actual_ready,
        planned_energy_kwh=commitment.planned_safe_energy_kwh,
        actual_energy_kwh=actual_energy,
        arrival_delay_sec=elapsed - commitment.planned_q50_eta_sec,
        soc_difference_fraction=(commitment.planned_safe_energy_kwh - actual_energy) / battery_capacity_kwh,
        temporal_method="LINK_ENTRY_TIME_PIECEWISE_CONSTANT_5MIN",
    )

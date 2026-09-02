"""Deterministic planned-trajectory extraction and future execution commitments."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json

from .contracts import MobilityContractError
from .mess_mobility_milp import MessMobilityBlock


def _number(value: float) -> float:
    value = float(value)
    return 0.0 if abs(value) < 1e-9 else round(value, 9)


@dataclass(frozen=True)
class MessTrajectorySlot:
    mess_id: str
    slot: int
    mode: str
    service_id: str | None
    origin_service_id: str | None
    destination_service_id: str | None
    route_link_ids: tuple[str, ...]
    departure_slot: int | None
    route_q10_eta_sec: float
    route_q50_eta_sec: float
    route_q90_eta_sec: float
    travel_slots_15min: int
    connection_ready_slot: int | None
    energy_nominal_kwh: float
    energy_safe_kwh: float
    p_kw: float
    q_kvar: float
    battery_energy_kwh: float
    soc_fraction: float

    def to_dict(self) -> dict[str, object]:
        result = dict(self.__dict__)
        result["route_link_ids"] = list(self.route_link_ids)
        return result


@dataclass(frozen=True)
class PlannedMoveCommitment:
    mess_id: str
    origin_service_id: str
    destination_service_id: str
    route_link_ids: tuple[str, ...]
    departure_slot: int
    planned_q50_eta_sec: float
    planned_q90_eta_sec: float
    planned_connection_ready_slot: int
    planned_safe_energy_kwh: float
    execution_rule: str = (
        "REPLAY_SELECTED_DESTINATION_AND_ROUTE_WITH_REALIZED_TIME_AND_PHYSICS_ENERGY;"
        "NO_REROUTING_WITHOUT_FUTURE_SCIENTIFIC_AUTHORITY"
    )


@dataclass(frozen=True)
class MessTrajectory:
    slots: tuple[MessTrajectorySlot, ...]

    def canonical_json_bytes(self) -> bytes:
        return json.dumps(
            [row.to_dict() for row in self.slots],
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")

    @property
    def canonical_sha256(self) -> str:
        return hashlib.sha256(self.canonical_json_bytes()).hexdigest()

    def planned_move_commitments(self) -> tuple[PlannedMoveCommitment, ...]:
        return tuple(
            PlannedMoveCommitment(
                mess_id=row.mess_id,
                origin_service_id=str(row.origin_service_id),
                destination_service_id=str(row.destination_service_id),
                route_link_ids=row.route_link_ids,
                departure_slot=int(row.departure_slot),
                planned_q50_eta_sec=row.route_q50_eta_sec,
                planned_q90_eta_sec=row.route_q90_eta_sec,
                planned_connection_ready_slot=int(row.connection_ready_slot),
                planned_safe_energy_kwh=row.energy_safe_kwh,
            )
            for row in self.slots
            if row.departure_slot == row.slot and row.mode == "TRANSIT"
        )


def extract_mess_trajectory(block: MessMobilityBlock) -> MessTrajectory:
    if block.model.SolCount < 1:
        raise MobilityContractError("MESS trajectory requires a feasible solved model")
    inputs = block.inputs
    authority = inputs.electrical_authority
    selected_moves = {
        key: block.move_route[key]
        for key, variable in block.move.items()
        if variable.X > 0.5
    }
    rows: list[MessTrajectorySlot] = []
    for mess_id in inputs.mess_ids:
        for slot in range(inputs.horizon_slots):
            connected = [
                service
                for service in inputs.route_table.service_ids
                if block.stay[mess_id, slot, service].X > 0.5
            ]
            active = [
                (key, route)
                for key, route in selected_moves.items()
                if key[0] == mess_id
                and key[1] <= slot < key[1] + route.connection_ready_slots_15min
            ]
            if len(connected) + len(active) != 1:
                raise MobilityContractError(
                    f"solved MESS state is not unique: {mess_id} slot={slot}"
                )
            p_kw = sum(
                block.p_discharge[mess_id, slot, service].X
                - block.p_charge[mess_id, slot, service].X
                for service in inputs.route_table.service_ids
            )
            q_kvar = sum(
                block.q[mess_id, slot, service].X
                for service in inputs.route_table.service_ids
            )
            battery = _number(block.energy[mess_id, slot].X)
            if connected:
                row = MessTrajectorySlot(
                    mess_id, slot, "CONNECTED", connected[0], None, None, (), None,
                    0.0, 0.0, 0.0, 0, None, 0.0, 0.0,
                    _number(p_kw), _number(q_kvar), battery,
                    _number(battery / authority.capacity_kwh),
                )
            else:
                key, route = active[0]
                _, departure, origin, destination = key
                mode = (
                    "TRANSIT"
                    if slot < departure + route.travel_slots_15min
                    else "CONNECTION_DELAY"
                )
                row = MessTrajectorySlot(
                    mess_id=mess_id,
                    slot=slot,
                    mode=mode,
                    service_id=None,
                    origin_service_id=origin,
                    destination_service_id=destination,
                    route_link_ids=route.route_link_ids,
                    departure_slot=departure,
                    route_q10_eta_sec=route.route_q10_eta_sec,
                    route_q50_eta_sec=route.route_q50_eta_sec,
                    route_q90_eta_sec=route.route_q90_eta_sec,
                    travel_slots_15min=route.travel_slots_15min,
                    connection_ready_slot=departure + route.connection_ready_slots_15min,
                    energy_nominal_kwh=route.energy_nominal_kwh,
                    energy_safe_kwh=route.energy_safe_kwh,
                    p_kw=_number(p_kw),
                    q_kvar=_number(q_kvar),
                    battery_energy_kwh=battery,
                    soc_fraction=_number(battery / authority.capacity_kwh),
                )
            rows.append(row)
    return MessTrajectory(tuple(rows))

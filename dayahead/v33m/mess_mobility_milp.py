"""Objective-free 15-minute MESS destination/mobility/PQ/SoC Gurobi block."""

from __future__ import annotations

from dataclasses import dataclass, fields
import math
from types import MappingProxyType
from typing import Mapping, Sequence

import gurobipy as gp
from gurobipy import GRB

from dayahead import mess_physics
from pfr.slow_fast import FastLayerLimits

from .contracts import MobilityContractError, RouteParameters15Min
from .grid_interface import ServicePCCMapping
from .route_table import MobilityRouteTable


END_OF_HORIZON_MOVE_RULE = "READY_ARRIVAL_MUST_BE_WITHIN_MODELED_HORIZON"


def _fast_limit_default(name: str) -> float:
    field = next(item for item in fields(FastLayerLimits) if item.name == name)
    return float(field.default)


@dataclass(frozen=True)
class MessElectricalAuthority:
    capacity_kwh: float
    energy_min_kwh: float
    energy_max_kwh: float
    initial_energy_kwh: float
    terminal_energy_kwh: float
    active_power_limit_kw: float
    pcs_kva: float
    pcs_polygon_faces: int
    interval_hours: float
    charge_efficiency: float
    discharge_efficiency: float

    @classmethod
    def from_repository(cls) -> "MessElectricalAuthority":
        return cls(
            capacity_kwh=mess_physics.CAPACITY_KWH,
            energy_min_kwh=mess_physics.E_MIN_KWH,
            energy_max_kwh=mess_physics.E_MAX_KWH,
            initial_energy_kwh=mess_physics.E_INITIAL_KWH,
            terminal_energy_kwh=mess_physics.E_TERMINAL_KWH,
            active_power_limit_kw=mess_physics.P_LIMIT_KW,
            pcs_kva=mess_physics.PCS_KVA,
            pcs_polygon_faces=mess_physics.PCS_POLYGON_FACES,
            interval_hours=mess_physics.DT_HOURS,
            charge_efficiency=_fast_limit_default("charge_efficiency"),
            discharge_efficiency=_fast_limit_default("discharge_efficiency"),
        )

    def validate(self) -> None:
        finite_positive = (
            self.capacity_kwh,
            self.energy_max_kwh,
            self.active_power_limit_kw,
            self.pcs_kva,
            self.interval_hours,
            self.charge_efficiency,
            self.discharge_efficiency,
        )
        if any(not math.isfinite(value) or value <= 0.0 for value in finite_positive):
            raise MobilityContractError("MESS electrical authority must be finite and positive")
        if not 0.0 <= self.energy_min_kwh <= self.initial_energy_kwh <= self.energy_max_kwh:
            raise MobilityContractError("MESS initial energy is outside frozen bounds")
        if not self.energy_min_kwh <= self.terminal_energy_kwh <= self.energy_max_kwh:
            raise MobilityContractError("MESS terminal energy is outside frozen bounds")
        if not 0.0 < self.charge_efficiency <= 1.0:
            raise MobilityContractError("MESS charge efficiency is invalid")
        if not 0.0 < self.discharge_efficiency <= 1.0:
            raise MobilityContractError("MESS discharge efficiency is invalid")
        if self.pcs_polygon_faces < 4:
            raise MobilityContractError("MESS PCS polygon needs at least four faces")


@dataclass(frozen=True)
class MessMobilityInputs:
    route_table: MobilityRouteTable
    horizon_slots: int
    mess_ids: tuple[str, ...]
    initial_service_by_mess: Mapping[str, str]
    service_pcc_mapping: ServicePCCMapping
    electrical_authority: MessElectricalAuthority
    initial_energy_by_mess: Mapping[str, float]

    @classmethod
    def create(
        cls,
        route_table: MobilityRouteTable,
        horizon_slots: int,
        initial_service_by_mess: Mapping[str, str],
        service_pcc_mapping: ServicePCCMapping,
        *,
        electrical_authority: MessElectricalAuthority | None = None,
        initial_energy_by_mess: Mapping[str, float] | None = None,
    ) -> "MessMobilityInputs":
        authority = electrical_authority or MessElectricalAuthority.from_repository()
        mess_ids = tuple(sorted(str(key) for key in initial_service_by_mess))
        energies = (
            {mess_id: authority.initial_energy_kwh for mess_id in mess_ids}
            if initial_energy_by_mess is None
            else {mess_id: float(initial_energy_by_mess[mess_id]) for mess_id in mess_ids}
        )
        result = cls(
            route_table=route_table,
            horizon_slots=int(horizon_slots),
            mess_ids=mess_ids,
            initial_service_by_mess=MappingProxyType(dict(initial_service_by_mess)),
            service_pcc_mapping=service_pcc_mapping,
            electrical_authority=authority,
            initial_energy_by_mess=MappingProxyType(energies),
        )
        result.validate()
        return result

    def validate(self) -> None:
        self.electrical_authority.validate()
        if self.horizon_slots <= 0:
            raise MobilityContractError("MESS horizon must be positive")
        if tuple(range(self.horizon_slots)) != self.route_table.departure_slots:
            raise MobilityContractError("route table must cover every modeled departure slot")
        services = set(self.route_table.service_ids)
        if set(self.initial_service_by_mess) != set(self.mess_ids):
            raise MobilityContractError("initial MESS location keys do not match fleet")
        if any(location not in services for location in self.initial_service_by_mess.values()):
            raise MobilityContractError("initial MESS location is outside route table")
        if not services.issubset(self.service_pcc_mapping.service_to_pcc):
            raise MobilityContractError("service/PCC mapping does not cover route table")
        if set(self.initial_energy_by_mess) != set(self.mess_ids):
            raise MobilityContractError("initial MESS energy keys do not match fleet")
        for energy in self.initial_energy_by_mess.values():
            if not self.electrical_authority.energy_min_kwh <= energy <= self.electrical_authority.energy_max_kwh:
                raise MobilityContractError("initial MESS energy violates frozen bounds")


@dataclass
class MessMobilityBlock:
    model: gp.Model
    inputs: MessMobilityInputs
    occupancy: Mapping[tuple[str, int, str], gp.Var]
    stay: Mapping[tuple[str, int, str], gp.Var]
    move: Mapping[tuple[str, int, str, str], gp.Var]
    discharge_mode: Mapping[tuple[str, int], gp.Var]
    p_discharge: Mapping[tuple[str, int, str], gp.Var]
    p_charge: Mapping[tuple[str, int, str], gp.Var]
    q: Mapping[tuple[str, int, str], gp.Var]
    energy: Mapping[tuple[str, int], gp.Var]
    p_injection_by_service_slot: Mapping[tuple[str, int], gp.LinExpr]
    q_injection_by_service_slot: Mapping[tuple[str, int], gp.LinExpr]
    p_injection_by_pcc_slot: Mapping[tuple[str, int], gp.LinExpr]
    q_injection_by_pcc_slot: Mapping[tuple[str, int], gp.LinExpr]
    total_travel_energy: gp.LinExpr
    number_move_departures: gp.LinExpr
    total_unavailable_slots: gp.LinExpr
    deterministic_move_ordinal: gp.LinExpr
    move_route: Mapping[tuple[str, int, str, str], RouteParameters15Min]

    @property
    def binary_variable_count(self) -> int:
        self.model.update()
        return int(self.model.NumBinVars)

    @property
    def continuous_variable_count(self) -> int:
        self.model.update()
        return sum(variable.VType == GRB.CONTINUOUS for variable in self.model.getVars())

    @property
    def constraint_count(self) -> int:
        self.model.update()
        return int(self.model.NumConstrs)


def _sum(items: Sequence[gp.Var] | list[gp.Var]) -> gp.LinExpr:
    return gp.quicksum(items)


def add_mess_mobility_block(model: gp.Model, inputs: MessMobilityInputs) -> MessMobilityBlock:
    """Add feasibility/actuation only; the parent model retains objective ownership."""
    inputs.validate()
    horizon = inputs.horizon_slots
    services = inputs.route_table.service_ids
    mess_ids = inputs.mess_ids
    authority = inputs.electrical_authority

    occupancy_keys = [
        (mess_id, slot, service)
        for mess_id in mess_ids
        for slot in range(horizon + 1)
        for service in services
    ]
    stay_keys = [
        (mess_id, slot, service)
        for mess_id in mess_ids
        for slot in range(horizon)
        for service in services
    ]
    move_route: dict[tuple[str, int, str, str], RouteParameters15Min] = {}
    for mess_id in mess_ids:
        for slot in range(horizon):
            for origin in services:
                for destination in services:
                    if origin == destination:
                        continue
                    route = inputs.route_table[slot, origin, destination]
                    ready = slot + route.connection_ready_slots_15min
                    if route.connection_ready_slots_15min > 0 and ready <= horizon:
                        move_route[(mess_id, slot, origin, destination)] = route

    occupancy = model.addVars(occupancy_keys, vtype=GRB.BINARY, name="mess_z")
    stay = model.addVars(stay_keys, vtype=GRB.BINARY, name="mess_stay")
    move = model.addVars(sorted(move_route), vtype=GRB.BINARY, name="mess_move")
    direction = model.addVars(
        [(mess_id, slot) for mess_id in mess_ids for slot in range(horizon)],
        vtype=GRB.BINARY,
        name="mess_discharge_mode",
    )
    dispatch_keys = stay_keys
    p_dis = model.addVars(dispatch_keys, lb=0.0, name="mess_p_dis_kw")
    p_ch = model.addVars(dispatch_keys, lb=0.0, name="mess_p_ch_kw")
    q = model.addVars(dispatch_keys, lb=-GRB.INFINITY, name="mess_q_kvar")
    energy = model.addVars(
        [(mess_id, slot) for mess_id in mess_ids for slot in range(horizon + 1)],
        lb=authority.energy_min_kwh,
        ub=authority.energy_max_kwh,
        name="mess_energy_kwh",
    )

    incoming_moves: dict[tuple[str, int, str], list[gp.Var]] = {}
    outgoing_moves: dict[tuple[str, int, str], list[gp.Var]] = {}
    departures: dict[tuple[str, int], list[tuple[gp.Var, RouteParameters15Min]]] = {}
    for key, variable in move.items():
        mess_id, slot, origin, destination = key
        route = move_route[key]
        ready = slot + route.connection_ready_slots_15min
        incoming_moves.setdefault((mess_id, ready, destination), []).append(variable)
        outgoing_moves.setdefault((mess_id, slot, origin), []).append(variable)
        departures.setdefault((mess_id, slot), []).append((variable, route))

    for mess_id in mess_ids:
        initial_service = inputs.initial_service_by_mess[mess_id]
        for service in services:
            model.addConstr(
                occupancy[mess_id, 0, service] == (1 if service == initial_service else 0),
                name=f"mess_initial[{mess_id},{service}]",
            )
        for slot in range(1, horizon + 1):
            for service in services:
                incoming = [stay[mess_id, slot - 1, service]]
                incoming.extend(incoming_moves.get((mess_id, slot, service), ()))
                model.addConstr(
                    occupancy[mess_id, slot, service] == _sum(incoming),
                    name=f"mess_flow_in[{mess_id},{slot},{service}]",
                )
        for slot in range(horizon):
            for service in services:
                outgoing = [stay[mess_id, slot, service]]
                outgoing.extend(outgoing_moves.get((mess_id, slot, service), ()))
                model.addConstr(
                    _sum(outgoing) == occupancy[mess_id, slot, service],
                    name=f"mess_flow_out[{mess_id},{slot},{service}]",
                )
        model.addConstr(
            _sum([occupancy[mess_id, horizon, service] for service in services]) == 1,
            name=f"mess_terminal_location[{mess_id}]",
        )

    apothem = authority.pcs_kva * math.cos(math.pi / authority.pcs_polygon_faces)
    p_service: dict[tuple[str, int], gp.LinExpr] = {}
    q_service: dict[tuple[str, int], gp.LinExpr] = {}
    for mess_id in mess_ids:
        for slot in range(horizon):
            total_dis = _sum([p_dis[mess_id, slot, service] for service in services])
            total_ch = _sum([p_ch[mess_id, slot, service] for service in services])
            total_q = _sum([q[mess_id, slot, service] for service in services])
            connected = _sum([stay[mess_id, slot, service] for service in services])
            model.addConstr(
                direction[mess_id, slot] <= connected,
                name=f"mess_transit_direction_symmetry[{mess_id},{slot}]",
            )
            model.addConstr(
                total_dis <= authority.active_power_limit_kw * direction[mess_id, slot],
                name=f"mess_discharge_direction[{mess_id},{slot}]",
            )
            model.addConstr(
                total_ch <= authority.active_power_limit_kw * (1 - direction[mess_id, slot]),
                name=f"mess_charge_direction[{mess_id},{slot}]",
            )
            for service in services:
                gate = stay[mess_id, slot, service]
                model.addConstr(
                    p_dis[mess_id, slot, service] + p_ch[mess_id, slot, service]
                    <= authority.active_power_limit_kw * gate,
                    name=f"mess_p_gate[{mess_id},{slot},{service}]",
                )
                model.addConstr(
                    q[mess_id, slot, service] <= authority.pcs_kva * gate,
                    name=f"mess_q_pos_gate[{mess_id},{slot},{service}]",
                )
                model.addConstr(
                    q[mess_id, slot, service] >= -authority.pcs_kva * gate,
                    name=f"mess_q_neg_gate[{mess_id},{slot},{service}]",
                )
            p_net = total_dis - total_ch
            for face in range(authority.pcs_polygon_faces):
                angle = 2.0 * math.pi * face / authority.pcs_polygon_faces
                model.addConstr(
                    math.cos(angle) * p_net + math.sin(angle) * total_q
                    <= apothem * connected,
                    name=f"mess_pcs_face[{mess_id},{slot},{face}]",
                )

            departure_energy = gp.quicksum(
                route.energy_safe_kwh * variable
                for variable, route in departures.get((mess_id, slot), ())
            )
            model.addConstr(
                energy[mess_id, slot] >= authority.energy_min_kwh + departure_energy,
                name=f"mess_departure_energy_floor[{mess_id},{slot}]",
            )
            model.addConstr(
                energy[mess_id, slot + 1]
                == energy[mess_id, slot]
                + authority.charge_efficiency * authority.interval_hours * total_ch
                - authority.interval_hours * total_dis / authority.discharge_efficiency
                - departure_energy,
                name=f"mess_soc[{mess_id},{slot}]",
            )
        model.addConstr(
            energy[mess_id, 0] == inputs.initial_energy_by_mess[mess_id],
            name=f"mess_initial_energy[{mess_id}]",
        )
        model.addConstr(
            energy[mess_id, horizon] == authority.terminal_energy_kwh,
            name=f"mess_terminal_energy[{mess_id}]",
        )

    for service in services:
        for slot in range(horizon):
            p_service[service, slot] = gp.quicksum(
                p_dis[mess_id, slot, service] - p_ch[mess_id, slot, service]
                for mess_id in mess_ids
            )
            q_service[service, slot] = gp.quicksum(
                q[mess_id, slot, service] for mess_id in mess_ids
            )
    p_pcc: dict[tuple[str, int], gp.LinExpr] = {}
    q_pcc: dict[tuple[str, int], gp.LinExpr] = {}
    pcc_ids = sorted(
        {inputs.service_pcc_mapping.service_to_pcc[service] for service in services}
    )
    for pcc in pcc_ids:
        mapped_services = [
            service
            for service in services
            if inputs.service_pcc_mapping.service_to_pcc[service] == pcc
        ]
        for slot in range(horizon):
            p_pcc[pcc, slot] = gp.quicksum(p_service[service, slot] for service in mapped_services)
            q_pcc[pcc, slot] = gp.quicksum(q_service[service, slot] for service in mapped_services)

    sorted_moves = sorted(move)
    block = MessMobilityBlock(
        model=model,
        inputs=inputs,
        occupancy=occupancy,
        stay=stay,
        move=move,
        discharge_mode=direction,
        p_discharge=p_dis,
        p_charge=p_ch,
        q=q,
        energy=energy,
        p_injection_by_service_slot=MappingProxyType(p_service),
        q_injection_by_service_slot=MappingProxyType(q_service),
        p_injection_by_pcc_slot=MappingProxyType(p_pcc),
        q_injection_by_pcc_slot=MappingProxyType(q_pcc),
        total_travel_energy=gp.quicksum(
            move_route[key].energy_safe_kwh * move[key] for key in sorted_moves
        ),
        number_move_departures=gp.quicksum(move[key] for key in sorted_moves),
        total_unavailable_slots=gp.quicksum(
            move_route[key].connection_ready_slots_15min * move[key]
            for key in sorted_moves
        ),
        deterministic_move_ordinal=gp.quicksum(
            (index + 1) * move[key] for index, key in enumerate(sorted_moves)
        ),
        move_route=MappingProxyType(move_route),
    )
    model.update()
    return block

"""V35R3 Apr-01-only workload envelopes and mobility opportunity search.

Fresh/Actual data are deliberately absent from this module.  Every decision
is constructed from the frozen D-1 workload, route, and Planning authorities.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from types import MappingProxyType
from typing import Mapping, Sequence

import gurobipy as gp
from gurobipy import GRB
import numpy as np

from dayahead.grid_lp import LINE_POLYGON_FACES
from dayahead.v28r2.electrical_subproblem import (
    SlotCoefficients,
    anchored_polygon_parameters,
    is_dominated_mess_current_row,
)
from dayahead.v28r2.variable_registry import build_resource_model
from dayahead.v33m.mess_mobility_milp import MessElectricalAuthority
from dayahead.v33m.route_table import MobilityRouteTable
from dayahead.v34.correction import StaticCorrection, bind_squared_voltage_bounds


APR01 = "2025-04-01"
HORIZON = 96
# Candidate schedules are polished one order tighter than the production
# FeasibilityTol so a partial MIPStart is unambiguously feasible when imported
# into the full model.  This is numerical hygiene, not a scientific margin.
NUMERIC_TOLERANCE = 1e-8
_POLYGON_CACHE: dict[str, tuple[np.ndarray, np.ndarray]] = {}


def _cached_polygon_parameters(coefficients: SlotCoefficients) -> tuple[np.ndarray, np.ndarray]:
    cached = _POLYGON_CACHE.get(coefficients.coefficient_sha256)
    if cached is None:
        bias, correction, _ = anchored_polygon_parameters(coefficients)
        cached = (bias, correction)
        _POLYGON_CACHE[coefficients.coefficient_sha256] = cached
    return cached


def _cached_anchored_polygon_loading(
    coefficients: SlotCoefficients, controls: np.ndarray,
) -> np.ndarray:
    p = coefficients.flow_p_constant + coefficients.flow_p_matrix @ controls
    q = coefficients.flow_q_constant + coefficients.flow_q_matrix @ controls
    limits = np.asarray(coefficients.branch_limits, dtype=float)
    apothem = limits * math.cos(math.pi / LINE_POLYGON_FACES)
    angles = 2.0 * math.pi * np.arange(LINE_POLYGON_FACES) / LINE_POLYGON_FACES
    values = (
        np.cos(angles)[:, None] * p[None, :]
        + np.sin(angles)[:, None] * q[None, :]
    ) / apothem[None, :]
    bias, correction = _cached_polygon_parameters(coefficients)
    return np.max(values, axis=0) + bias + correction.T @ (controls - coefficients.anchor)


def assert_apr01_only(day: str) -> None:
    """Reject every date except the sole date authorized by V35R3."""

    if str(day) != APR01:
        raise PermissionError(f"V35R3_APR01_ONLY:{day}")


def fixed_critical_windows(binding_slot: int) -> Mapping[str, tuple[int, ...]]:
    """Return the predeclared W1/W3/W5 windows, clipped only at day edges."""

    slot = int(binding_slot)
    if not 0 <= slot < HORIZON:
        raise ValueError("V35R3_BINDING_SLOT_OUTSIDE_HORIZON")
    return MappingProxyType({
        "W1": tuple(range(max(0, slot), min(HORIZON, slot + 1))),
        "W3": tuple(range(max(0, slot - 1), min(HORIZON, slot + 2))),
        "W5": tuple(range(max(0, slot - 2), min(HORIZON, slot + 3))),
    })


@dataclass(frozen=True)
class AidcEnvelopeResult:
    window: str
    slots: tuple[int, ...]
    baseline_nodeh: float
    minimum_nodeh: float
    removable_nodeh: float
    arrays: Mapping[str, np.ndarray]
    binding_constraints: tuple[str, ...]
    status: str


def solve_aidc_flexibility_envelope(
    data: object,
    voltage_authority: object,
    baseline_workload: np.ndarray,
    *,
    window: str,
    slots: Sequence[int],
    deterministic_tiebreak: bool = False,
) -> AidcEnvelopeResult:
    """Solve the exact production resource model without any grid rows.

    B1 activates the frozen controllable cohorts.  ``mess_disabled`` removes
    the unrelated legacy MESS block.  No voltage/current/Fresh constraint or
    value is present in the model.
    """

    chosen = tuple(int(slot) for slot in slots)
    if not chosen or any(not 0 <= slot < HORIZON for slot in chosen):
        raise ValueError("V35R3_AIDC_WINDOW_AXIS")
    baseline = np.asarray(baseline_workload, dtype=float)
    expected = (len(data.cohort_ids), len(data.rack_ids), HORIZON)
    if baseline.shape != expected or not np.isfinite(baseline).all():
        raise ValueError("V35R3_AIDC_BASELINE_AXIS")
    registry = build_resource_model(data, voltage_authority, "B1", mess_disabled=True)
    primary = gp.quicksum(
        registry.x[cohort, rack, slot]
        for cohort in data.cohort_ids
        for rack in data.rack_ids
        for slot in chosen
    )
    registry.model.setObjective(primary, GRB.MINIMIZE)
    registry.model.optimize()
    if registry.model.Status != GRB.OPTIMAL:
        raise RuntimeError(f"V35R3_AIDC_ENVELOPE_STATUS:{registry.model.Status}")
    optimum = float(registry.model.ObjVal)
    if deterministic_tiebreak:
        # Preserve the primary optimum to the already-frozen feasibility
        # tolerance, then select one canonical cohort/rack/slot allocation.
        registry.model.addConstr(
            primary <= optimum + float(registry.model.Params.FeasibilityTol),
            name="v35r3_primary_window_hold",
        )
        keys = tuple(sorted(registry.x))
        registry.model.setObjective(
            gp.quicksum((index + 1.0) / len(keys) * registry.x[key] for index, key in enumerate(keys)),
            GRB.MINIMIZE,
        )
        registry.model.optimize()
        if registry.model.Status != GRB.OPTIMAL:
            raise RuntimeError(f"V35R3_AIDC_TIEBREAK_STATUS:{registry.model.Status}")
    arrays = registry.primal_arrays()
    minimum = float(np.asarray(arrays["workload_service_nodeh"])[:, :, chosen].sum())
    baseline_window = float(baseline[:, :, chosen].sum())
    tolerance = 2.0 * float(registry.model.Params.FeasibilityTol)
    binding = tuple(sorted(
        row.ConstrName for row in registry.model.getConstrs()
        if (
            row.ConstrName.startswith(("service_", "rack_gpu_hard", "trust_aidc_"))
            and abs(float(row.Slack)) <= tolerance
        )
    ))
    return AidcEnvelopeResult(
        window=str(window),
        slots=chosen,
        baseline_nodeh=baseline_window,
        minimum_nodeh=minimum,
        removable_nodeh=max(0.0, baseline_window - minimum),
        arrays=MappingProxyType(arrays),
        binding_constraints=binding,
        status="OPTIMAL",
    )


@dataclass(frozen=True)
class MobilityCandidate:
    candidate_id: str
    mess_id: str
    origin: str
    destination: str
    departure_slot: int | None
    connection_ready_slot: int | None
    travel_slots: int
    q50_eta_seconds: float
    safe_eta_seconds: float
    safe_energy_kwh: float
    route_link_ids: tuple[str, ...]
    is_stay: bool = False
    deterministic_full_move_ordinal: int = 0


@dataclass(frozen=True)
class CandidateEnumeration:
    candidates: tuple[MobilityCandidate, ...]
    rejected_counts: Mapping[str, int]


def enumerate_initial_relocations(
    *,
    day: str,
    mess_id: str,
    initial_service: str,
    route_table: MobilityRouteTable,
    authority: MessElectricalAuthority | None = None,
) -> CandidateEnumeration:
    """Enumerate every exact one-relocation opportunity from the initial depot.

    This is an opportunity/warm-start set, not a restriction on the full
    multi-relocation production formulation.
    """

    assert_apr01_only(day)
    electrical = authority or MessElectricalAuthority.from_repository()
    if initial_service not in route_table.service_ids:
        raise ValueError("V35R3_INITIAL_SERVICE_OUTSIDE_ROUTE_TABLE")
    rows = [MobilityCandidate(
        candidate_id=f"{mess_id}:STAY:{initial_service}",
        mess_id=mess_id,
        origin=initial_service,
        destination=initial_service,
        departure_slot=None,
        connection_ready_slot=None,
        travel_slots=0,
        q50_eta_seconds=0.0,
        safe_eta_seconds=0.0,
        safe_energy_kwh=0.0,
        route_link_ids=(),
        is_stay=True,
    )]
    full_move_keys = sorted(
        (mess_id, slot, origin, destination)
        for slot in route_table.departure_slots
        for origin in route_table.service_ids
        for destination in route_table.service_ids
        if origin != destination
        and route_table[slot, origin, destination].connection_ready_slots_15min > 0
        and slot + route_table[slot, origin, destination].connection_ready_slots_15min <= HORIZON
    )
    full_ordinal = {key: index + 1 for index, key in enumerate(full_move_keys)}
    rejected = {
        "self_destination_as_STAY": HORIZON,
        "arrival_beyond_horizon": 0,
        "unreachable_route": 0,
        "travel_energy_infeasible": 0,
        "terminal_energy_infeasible": 0,
    }
    apothem = electrical.pcs_kva * math.cos(math.pi / electrical.pcs_polygon_faces)
    max_charge_kw = min(electrical.active_power_limit_kw, apothem)
    for destination in route_table.service_ids:
        if destination == initial_service:
            continue
        for departure in route_table.departure_slots:
            route = route_table[departure, initial_service, destination]
            if not route.route_link_ids:
                rejected["unreachable_route"] += 1
                continue
            ready = departure + route.connection_ready_slots_15min
            if route.connection_ready_slots_15min <= 0 or ready > HORIZON:
                rejected["arrival_beyond_horizon"] += 1
                continue
            max_energy_at_departure = min(
                electrical.energy_max_kwh,
                electrical.initial_energy_kwh
                + departure * electrical.interval_hours * electrical.charge_efficiency * max_charge_kw,
            )
            if max_energy_at_departure < electrical.energy_min_kwh + route.energy_safe_kwh - NUMERIC_TOLERANCE:
                rejected["travel_energy_infeasible"] += 1
                continue
            connected_slots = departure + (HORIZON - ready)
            max_terminal = min(
                electrical.energy_max_kwh,
                electrical.initial_energy_kwh
                + connected_slots * electrical.interval_hours * electrical.charge_efficiency * max_charge_kw
                - route.energy_safe_kwh,
            )
            if max_terminal < electrical.terminal_energy_kwh - NUMERIC_TOLERANCE:
                rejected["terminal_energy_infeasible"] += 1
                continue
            rows.append(MobilityCandidate(
                candidate_id=f"{mess_id}:MOVE:{initial_service}:{destination}:{departure:02d}",
                mess_id=mess_id,
                origin=initial_service,
                destination=destination,
                departure_slot=int(departure),
                connection_ready_slot=int(ready),
                travel_slots=int(route.travel_slots_15min),
                q50_eta_seconds=float(route.route_q50_eta_sec),
                safe_eta_seconds=float(route.route_safe_eta_sec),
                safe_energy_kwh=float(route.energy_safe_kwh),
                route_link_ids=tuple(route.route_link_ids),
                deterministic_full_move_ordinal=full_ordinal[(mess_id, departure, initial_service, destination)],
            ))
    return CandidateEnumeration(tuple(rows), MappingProxyType(rejected))


@dataclass
class OpportunityModel:
    model: gp.Model
    candidates: tuple[MobilityCandidate, ...]
    select: Mapping[str, gp.Var]
    p_discharge: Mapping[tuple[int, str], gp.Var]
    p_charge: Mapping[tuple[int, str], gp.Var]
    q: Mapping[tuple[int, str], gp.Var]
    energy: Mapping[int, gp.Var]
    direction: Mapping[int, gp.Var]
    eta: gp.Var
    services: tuple[str, ...]
    aidc: np.ndarray
    coefficients: tuple[SlotCoefficients, ...]
    fixed_p: Mapping[tuple[str, int], float]
    fixed_q: Mapping[tuple[str, int], float]
    correction: StaticCorrection | None
    added_line_states: set[tuple[int, int]]
    added_voltage_states: set[tuple[int, int]]
    added_transformer_current_states: set[tuple[int, int]]
    added_transformer_kva_states: set[tuple[int, int]]


def _candidate_service(candidate: MobilityCandidate, slot: int) -> str | None:
    if candidate.is_stay:
        return candidate.origin
    assert candidate.departure_slot is not None and candidate.connection_ready_slot is not None
    if slot < candidate.departure_slot:
        return candidate.origin
    if slot >= candidate.connection_ready_slot:
        return candidate.destination
    return None


def build_mess_opportunity_model(
    *,
    candidates: Sequence[MobilityCandidate],
    aidc_pcc_kw_96x12: np.ndarray,
    coefficients: Sequence[SlotCoefficients],
    voltage_authority: object,
    fixed_mess_p_by_service: Mapping[tuple[str, int], float] | None = None,
    fixed_mess_q_by_service: Mapping[tuple[str, int], float] | None = None,
    correction: StaticCorrection | None = None,
    critical_states: Sequence[tuple[int, int]] | None = None,
) -> OpportunityModel:
    """Build the exact fixed-one-relocation P/Q/SoC opportunity model.

    Candidate selection is a compact D-1 search used only to supply a feasible
    incumbent to the unchanged general multi-move production model.
    """

    rows = tuple(candidates)
    if not rows or sum(row.is_stay for row in rows) != 1:
        raise ValueError("V35R3_OPPORTUNITY_REQUIRES_ONE_STAY")
    mess_ids = {row.mess_id for row in rows}
    origins = {row.origin for row in rows}
    if len(mess_ids) != 1 or len(origins) != 1:
        raise ValueError("V35R3_OPPORTUNITY_SINGLE_VEHICLE_ORIGIN")
    aidc = np.asarray(aidc_pcc_kw_96x12, dtype=float)
    if aidc.shape != (HORIZON, 12) or len(coefficients) != HORIZON:
        raise ValueError("V35R3_OPPORTUNITY_AXIS")
    services = tuple(name[10:-1] for name in map(str, voltage_authority["control_names"]) if name.startswith("mess_p_kw["))
    if len(services) != 24 or set(services) != set(row.destination for row in rows):
        raise ValueError("V35R3_OPPORTUNITY_SERVICE_AXIS")
    fixed_p = {} if fixed_mess_p_by_service is None else dict(fixed_mess_p_by_service)
    fixed_q = {} if fixed_mess_q_by_service is None else dict(fixed_mess_q_by_service)
    authority = MessElectricalAuthority.from_repository()
    model = gp.Model(f"v35r3_opportunity_{next(iter(mess_ids))}")
    model.Params.OutputFlag = 0
    model.Params.Threads = 4
    model.Params.Seed = 20260828
    model.Params.MIPGap = 1e-7
    model.Params.FeasibilityTol = NUMERIC_TOLERANCE
    model.Params.OptimalityTol = NUMERIC_TOLERANCE
    model.Params.MIPFocus = 1
    model.Params.SoftMemLimit = 8.0
    model.Params.NodefileStart = 1.0
    select = model.addVars([row.candidate_id for row in rows], vtype=GRB.BINARY, name="opportunity")
    model.addConstr(gp.quicksum(select.values()) == 1, name="opportunity_choose_one")
    dispatch_keys = [(slot, service) for slot in range(HORIZON) for service in services]
    p_dis = model.addVars(dispatch_keys, lb=0.0, name="op_p_dis_kw")
    p_ch = model.addVars(dispatch_keys, lb=0.0, name="op_p_ch_kw")
    q = model.addVars(dispatch_keys, lb=-GRB.INFINITY, name="op_q_kvar")
    # The fixed-candidate opportunity problem first uses the convex hull of
    # the direction disjunction.  A solution is certified only when it has no
    # simultaneous charge/discharge, in which case it is also feasible for
    # the original binary-direction formulation and the relaxation lower
    # bound proves exact optimality.  Non-integral cases are promoted back to
    # binary by ``solve_opportunity_candidate_certified``.
    direction = model.addVars(range(HORIZON), lb=0.0, ub=1.0, name="op_discharge_mode")
    energy = model.addVars(range(HORIZON + 1), lb=authority.energy_min_kwh, ub=authority.energy_max_kwh, name="op_energy_kwh")
    model.addConstr(energy[0] == authority.initial_energy_kwh, name="op_initial_energy")
    apothem = authority.pcs_kva * math.cos(math.pi / authority.pcs_polygon_faces)
    connected_by: dict[tuple[int, str], list[gp.Var]] = {}
    departure_energy_by: dict[int, list[tuple[float, gp.Var]]] = {}
    for row in rows:
        variable = select[row.candidate_id]
        for slot in range(HORIZON):
            service = _candidate_service(row, slot)
            if service is not None:
                connected_by.setdefault((slot, service), []).append(variable)
        if not row.is_stay:
            assert row.departure_slot is not None
            departure_energy_by.setdefault(row.departure_slot, []).append((row.safe_energy_kwh, variable))
    for slot in range(HORIZON):
        gates = {
            service: gp.quicksum(connected_by.get((slot, service), ()))
            for service in services
        }
        connected = gp.quicksum(gates.values())
        total_dis = gp.quicksum(p_dis[slot, service] for service in services)
        total_ch = gp.quicksum(p_ch[slot, service] for service in services)
        total_q = gp.quicksum(q[slot, service] for service in services)
        model.addConstr(direction[slot] <= connected, name=f"op_direction_gate[{slot}]")
        model.addConstr(total_dis <= authority.active_power_limit_kw * direction[slot], name=f"op_discharge[{slot}]")
        model.addConstr(total_ch <= authority.active_power_limit_kw * (1 - direction[slot]), name=f"op_charge[{slot}]")
        for service in services:
            gate = gates[service]
            model.addConstr(p_dis[slot, service] + p_ch[slot, service] <= authority.active_power_limit_kw * gate, name=f"op_p_gate[{slot},{service}]")
            model.addConstr(q[slot, service] <= authority.pcs_kva * gate, name=f"op_q_pos_gate[{slot},{service}]")
            model.addConstr(q[slot, service] >= -authority.pcs_kva * gate, name=f"op_q_neg_gate[{slot},{service}]")
        for face in range(authority.pcs_polygon_faces):
            angle = 2.0 * math.pi * face / authority.pcs_polygon_faces
            model.addConstr(
                math.cos(angle) * (total_dis - total_ch) + math.sin(angle) * total_q <= apothem * connected,
                name=f"op_pcs_face[{slot},{face}]",
            )
        departure_energy = gp.quicksum(value * variable for value, variable in departure_energy_by.get(slot, ()))
        model.addConstr(energy[slot] >= authority.energy_min_kwh + departure_energy, name=f"op_departure_floor[{slot}]")
        model.addConstr(
            energy[slot + 1] == energy[slot]
            + authority.charge_efficiency * authority.interval_hours * total_ch
            - authority.interval_hours * total_dis / authority.discharge_efficiency
            - departure_energy,
            name=f"op_soc[{slot}]",
        )
    model.addConstr(energy[HORIZON] == authority.terminal_energy_kwh, name="op_terminal_energy")

    controls = tuple(map(str, voltage_authority["control_names"]))
    p_services = tuple(name[10:-1] for name in controls[12:36])
    q_services = tuple(name[12:-1] for name in controls[36:60])
    if p_services != q_services or p_services != services:
        raise RuntimeError("V35R3_COMMON_CONTROL_AXIS")
    node_names = tuple(map(str, voltage_authority["node_names"]))
    reduced_states = None if critical_states is None else frozenset(
        (int(slot), int(index)) for slot, index in critical_states
    )

    def sparse_expression(base: float, vector: np.ndarray, slot: int) -> gp.LinExpr:
        constant = float(base + vector[:12] @ aidc[slot])
        constant += sum(float(vector[12 + index]) * float(fixed_p.get((service, slot), 0.0)) for index, service in enumerate(services))
        constant += sum(float(vector[36 + index]) * float(fixed_q.get((service, slot), 0.0)) for index, service in enumerate(services))
        variables = (
            [p_dis[slot, service] for service in services]
            + [p_ch[slot, service] for service in services]
            + [q[slot, service] for service in services]
        )
        scalars = np.concatenate((vector[12:36], -vector[12:36], vector[36:60]))
        nonzero = np.flatnonzero(np.abs(scalars) > 1e-15)
        return gp.LinExpr([float(scalars[index]) for index in nonzero], [variables[index] for index in nonzero]) + constant

    eta = model.addVar(lb=0.0, ub=1.0, name="op_rho_planning")
    for slot, coefficient in enumerate(coefficients):
        if reduced_states is None:
            for index, node in enumerate(node_names):
                expression = sparse_expression(float(coefficient.voltage_constant[index]), coefficient.voltage_matrix[:, index], slot)
                phase = "ABC"[int(node.rsplit(".", 1)[1]) - 1]
                up, low = (0.0, 0.0) if correction is None else correction.value_for(node, phase, slot)
                lower, upper = bind_squared_voltage_bounds(up, low)
                voltage = model.addVar(lb=lower, ub=upper, name=f"op_v_squared[{slot},{index}]")
                model.addConstr(voltage == expression, name=f"op_voltage_affine[{slot},{index}]")
        bias, tangent_delta, _ = anchored_polygon_parameters(coefficient)
        for index, branch in enumerate(coefficient.branch_names):
            line_state_selected = (
                reduced_states is None or (slot, index) in reduced_states
            )
            if (
                line_state_selected
                and not branch.startswith("transformer.")
                and not is_dominated_mess_current_row(branch)
            ):
                p_flow = model.addVar(lb=-GRB.INFINITY, name=f"op_line_p[{slot},{index}]")
                q_flow = model.addVar(lb=-GRB.INFINITY, name=f"op_line_q[{slot},{index}]")
                correction_value = model.addVar(lb=-GRB.INFINITY, name=f"op_line_corr[{slot},{index}]")
                model.addConstr(p_flow == sparse_expression(float(coefficient.flow_p_constant[index]), coefficient.flow_p_matrix[index], slot))
                model.addConstr(q_flow == sparse_expression(float(coefficient.flow_q_constant[index]), coefficient.flow_q_matrix[index], slot))
                model.addConstr(correction_value == sparse_expression(-float(tangent_delta[:, index] @ coefficient.anchor), tangent_delta[:, index], slot))
                line_apothem = float(coefficient.branch_limits[index]) * math.cos(math.pi / LINE_POLYGON_FACES)
                for face in range(LINE_POLYGON_FACES):
                    angle = 2.0 * math.pi * face / LINE_POLYGON_FACES
                    model.addConstr(
                        eta >= (math.cos(angle) * p_flow + math.sin(angle) * q_flow) / line_apothem + correction_value + float(bias[index]),
                        name=f"op_line_face[{slot},{index},{face}]",
                    )
            rating = coefficient.transformer_ratings[index]
            if reduced_states is None and rating is not None:
                p_flow = model.addVar(lb=-GRB.INFINITY, name=f"op_tx_p[{slot},{index}]")
                q_flow = model.addVar(lb=-GRB.INFINITY, name=f"op_tx_q[{slot},{index}]")
                model.addConstr(p_flow == sparse_expression(float(coefficient.flow_p_constant[index]), coefficient.flow_p_matrix[index], slot))
                model.addConstr(q_flow == sparse_expression(float(coefficient.flow_q_constant[index]), coefficient.flow_q_matrix[index], slot))
                tx_apothem = float(rating) * math.cos(math.pi / LINE_POLYGON_FACES)
                for face in range(LINE_POLYGON_FACES):
                    angle = 2.0 * math.pi * face / LINE_POLYGON_FACES
                    model.addConstr(
                        math.cos(angle) * p_flow + math.sin(angle) * q_flow <= tx_apothem,
                        name=f"op_tx_face[{slot},{index},{face}]",
                    )
    travel = gp.quicksum(row.safe_energy_kwh * select[row.candidate_id] for row in rows)
    moves = gp.quicksum(select[row.candidate_id] for row in rows if not row.is_stay)
    ordinal = gp.quicksum((index + 1) * select[row.candidate_id] for index, row in enumerate(rows))
    model.setObjective(eta + 1e-8 * travel + 1e-10 * moves + 1e-16 * ordinal, GRB.MINIMIZE)
    model.update()
    stay = next(row for row in rows if row.is_stay)
    for row in rows:
        select[row.candidate_id].Start = float(row is stay)
    for variable in p_dis.values():
        variable.Start = 0.0
    for variable in p_ch.values():
        variable.Start = 0.0
    for variable in q.values():
        variable.Start = 0.0
    for variable in direction.values():
        variable.Start = 0.0
    for variable in energy.values():
        variable.Start = authority.initial_energy_kwh
    all_line_states = {
        (slot, index)
        for slot, coefficient in enumerate(coefficients)
        for index, branch in enumerate(coefficient.branch_names)
        if not branch.startswith("transformer.") and not is_dominated_mess_current_row(branch)
    }
    all_voltage_states = {
        (slot, index) for slot in range(HORIZON) for index in range(len(node_names))
    }
    all_tx_states = {
        (slot, index)
        for slot, coefficient in enumerate(coefficients)
        for index, rating in enumerate(coefficient.transformer_ratings)
        if rating is not None
    }
    initial_line = all_line_states if reduced_states is None else set(reduced_states) & all_line_states
    return OpportunityModel(
        model, rows, select, p_dis, p_ch, q, energy, direction, eta, services,
        aidc, tuple(coefficients), MappingProxyType(fixed_p), MappingProxyType(fixed_q), correction,
        set(initial_line),
        set(all_voltage_states if reduced_states is None else ()),
        set(all_tx_states if reduced_states is None else ()),
        set(all_tx_states if reduced_states is None else ()),
    )


def selected_candidate(model: OpportunityModel) -> MobilityCandidate:
    chosen = [row for row in model.candidates if model.select[row.candidate_id].X > 0.5]
    if len(chosen) != 1:
        raise RuntimeError("V35R3_OPPORTUNITY_SELECTION_NOT_UNIQUE")
    return chosen[0]


def fix_opportunity_candidate(model: OpportunityModel, candidate_id: str) -> None:
    """Fix exactly one opportunity; the choose-one row fixes all alternatives."""

    if candidate_id not in model.select:
        raise KeyError(candidate_id)
    for key, variable in model.select.items():
        variable.LB = variable.UB = float(key == candidate_id)
    model.model.update()


def release_opportunity_candidates(model: OpportunityModel) -> None:
    for variable in model.select.values():
        variable.LB = 0.0
        variable.UB = 1.0
    model.model.update()


def opportunity_dispatch(model: OpportunityModel) -> dict[str, object]:
    """Extract a solved candidate's complete restricted P/Q/SoC state."""

    if model.model.SolCount < 1:
        raise RuntimeError("V35R3_OPPORTUNITY_HAS_NO_INCUMBENT")
    candidate = selected_candidate(model)
    p_dis = np.asarray([
        sum(float(model.p_discharge[slot, service].X) for service in model.services)
        for slot in range(HORIZON)
    ])
    p_ch = np.asarray([
        sum(float(model.p_charge[slot, service].X) for service in model.services)
        for slot in range(HORIZON)
    ])
    q = np.asarray([
        sum(float(model.q[slot, service].X) for service in model.services)
        for slot in range(HORIZON)
    ])
    return {
        "candidate": candidate,
        "objective": float(model.model.ObjVal),
        "rho": float(model.eta.X),
        "p_discharge_kw": p_dis,
        "p_charge_kw": p_ch,
        "p_kw": p_dis - p_ch,
        "q_kvar": q,
        "energy_kwh": np.asarray([float(model.energy[slot].X) for slot in range(HORIZON + 1)]),
        "terminal_energy_kwh": float(model.energy[HORIZON].X),
        "simultaneous_charge_discharge_slots": [
            int(slot) for slot in range(HORIZON)
            if p_dis[slot] > NUMERIC_TOLERANCE and p_ch[slot] > NUMERIC_TOLERANCE
        ],
        "post_arrival_sum_abs_p_kw_slots": float(np.abs(p_dis - p_ch)[candidate.connection_ready_slot or 0:].sum()),
        "post_arrival_sum_abs_q_kvar_slots": float(np.abs(q)[candidate.connection_ready_slot or 0:].sum()),
    }


def evaluate_opportunity_dispatch(
    *,
    dispatch: Mapping[str, object],
    coefficients: Sequence[SlotCoefficients],
    aidc_pcc_kw_96x12: np.ndarray,
    services: Sequence[str],
    fixed_mess_p_by_service: Mapping[tuple[str, int], float] | None = None,
    fixed_mess_q_by_service: Mapping[tuple[str, int], float] | None = None,
    correction: StaticCorrection | None = None,
) -> dict[str, object]:
    """Evaluate every omitted Planning row and certify a reduced solve.

    Equality of the reduced objective lower bound and the complete feasible
    evaluation is an exact optimality certificate for the fixed candidate.
    """

    candidate = dispatch["candidate"]
    if not isinstance(candidate, MobilityCandidate):
        raise TypeError("V35R3_OPPORTUNITY_CANDIDATE_TYPE")
    p = np.asarray(dispatch["p_kw"], dtype=float)
    q = np.asarray(dispatch["q_kvar"], dtype=float)
    aidc = np.asarray(aidc_pcc_kw_96x12, dtype=float)
    service_axis = tuple(map(str, services))
    fixed_p = {} if fixed_mess_p_by_service is None else dict(fixed_mess_p_by_service)
    fixed_q = {} if fixed_mess_q_by_service is None else dict(fixed_mess_q_by_service)
    if p.shape != (HORIZON,) or q.shape != (HORIZON,) or aidc.shape != (HORIZON, 12):
        raise ValueError("V35R3_OPPORTUNITY_EVALUATION_AXIS")
    rho = -math.inf
    binding_slot = -1
    binding_asset = ""
    vmin = math.inf
    vmax = -math.inf
    voltage_violations = line_violations = tx_current_violations = tx_kva_violations = 0
    line_separation_states: list[tuple[int, int]] = []
    voltage_violation_states: list[tuple[int, int]] = []
    tx_current_violation_states: list[tuple[int, int]] = []
    tx_kva_violation_states: list[tuple[int, int]] = []
    reduced_rho = float(dispatch["rho"])
    for slot, coefficient in enumerate(coefficients):
        active_service = _candidate_service(candidate, slot)
        p_values = [float(fixed_p.get((service, slot), 0.0)) for service in service_axis]
        q_values = [float(fixed_q.get((service, slot), 0.0)) for service in service_axis]
        if active_service is not None:
            index = service_axis.index(active_service)
            p_values[index] += float(p[slot])
            q_values[index] += float(q[slot])
        controls = np.asarray(list(aidc[slot]) + p_values + q_values, dtype=float)
        squared = coefficient.voltage_constant + coefficient.voltage_matrix.T @ controls
        volts = np.sqrt(np.maximum(0.0, squared))
        vmin = min(vmin, float(volts.min()))
        vmax = max(vmax, float(volts.max()))
        if correction is None:
            bad_voltage = np.flatnonzero(
                (squared < 0.95**2 - NUMERIC_TOLERANCE)
                | (squared > 1.05**2 + NUMERIC_TOLERANCE)
            )
            voltage_violations += int(len(bad_voltage))
            voltage_violation_states.extend((slot, int(index)) for index in bad_voltage)
        else:
            # Static correction is not used on Apr-01; retaining this branch
            # makes accidental corrected-phase use fail closed.
            raise ValueError("V35R3_APR01_CORRECTION_NOT_ALLOWED")
        current = _cached_anchored_polygon_loading(coefficient, controls)
        affine_current = coefficient.current_constant + coefficient.current_matrix.T @ controls
        for index, branch in enumerate(coefficient.branch_names):
            if branch.startswith("transformer."):
                if not is_dominated_mess_current_row(branch):
                    bad = float(affine_current[index]) > 1.0 + NUMERIC_TOLERANCE
                    tx_current_violations += int(bad)
                    if bad:
                        tx_current_violation_states.append((slot, index))
                continue
            if is_dominated_mess_current_row(branch):
                continue
            value = float(current[index])
            line_violations += int(value > 1.0 + NUMERIC_TOLERANCE)
            if value > rho:
                rho = value
                binding_slot = slot
                binding_asset = str(branch)
            if value > reduced_rho + NUMERIC_TOLERANCE:
                line_separation_states.append((slot, index))
        flow_p = coefficient.flow_p_constant + coefficient.flow_p_matrix @ controls
        flow_q = coefficient.flow_q_constant + coefficient.flow_q_matrix @ controls
        for index, rating in enumerate(coefficient.transformer_ratings):
            if rating is not None:
                bad = math.hypot(float(flow_p[index]), float(flow_q[index])) > float(rating) + NUMERIC_TOLERANCE
                tx_kva_violations += int(bad)
                if bad:
                    tx_kva_violation_states.append((slot, index))
    exact = (
        voltage_violations == line_violations == tx_current_violations == tx_kva_violations == 0
        and abs(rho - reduced_rho) <= 2.0 * NUMERIC_TOLERANCE
        and not dispatch.get("simultaneous_charge_discharge_slots")
    )
    return {
        "rho": float(rho),
        "reduced_rho": reduced_rho,
        "exact_optimality_certificate": bool(exact),
        "binding_asset": binding_asset,
        "binding_slot": int(binding_slot),
        "Vmin_pu": float(vmin),
        "Vmax_pu": float(vmax),
        "voltage_violation_count": int(voltage_violations),
        "line_current_violation_count": int(line_violations),
        "transformer_current_violation_count": int(tx_current_violations),
        "transformer_kva_violation_count": int(tx_kva_violations),
        "line_separation_states": line_separation_states,
        "voltage_violation_states": voltage_violation_states,
        "transformer_current_violation_states": tx_current_violation_states,
        "transformer_kva_violation_states": tx_kva_violation_states,
    }


def _opportunity_sparse_expression(
    opportunity: OpportunityModel,
    base: float,
    vector: np.ndarray,
    slot: int,
) -> gp.LinExpr:
    services = opportunity.services
    constant = float(base + vector[:12] @ opportunity.aidc[slot])
    constant += sum(
        float(vector[12 + index]) * float(opportunity.fixed_p.get((service, slot), 0.0))
        for index, service in enumerate(services)
    )
    constant += sum(
        float(vector[36 + index]) * float(opportunity.fixed_q.get((service, slot), 0.0))
        for index, service in enumerate(services)
    )
    variables = (
        [opportunity.p_discharge[slot, service] for service in services]
        + [opportunity.p_charge[slot, service] for service in services]
        + [opportunity.q[slot, service] for service in services]
    )
    scalars = np.concatenate((vector[12:36], -vector[12:36], vector[36:60]))
    nonzero = np.flatnonzero(np.abs(scalars) > 1e-15)
    return gp.LinExpr(
        [float(scalars[index]) for index in nonzero],
        [variables[index] for index in nonzero],
    ) + constant


def add_opportunity_separation_rows(
    opportunity: OpportunityModel,
    evaluation: Mapping[str, object],
) -> int:
    """Add only violated/missing full-Planning rows to a reduced model."""

    model = opportunity.model
    added = 0
    for slot, index in evaluation["line_separation_states"]:
        key = (int(slot), int(index))
        if key in opportunity.added_line_states:
            continue
        coefficient = opportunity.coefficients[key[0]]
        bias, tangent_delta = _cached_polygon_parameters(coefficient)
        p_flow = _opportunity_sparse_expression(
            opportunity, float(coefficient.flow_p_constant[key[1]]),
            coefficient.flow_p_matrix[key[1]], key[0],
        )
        q_flow = _opportunity_sparse_expression(
            opportunity, float(coefficient.flow_q_constant[key[1]]),
            coefficient.flow_q_matrix[key[1]], key[0],
        )
        correction_value = _opportunity_sparse_expression(
            opportunity, -float(tangent_delta[:, key[1]] @ coefficient.anchor),
            tangent_delta[:, key[1]], key[0],
        )
        apothem = float(coefficient.branch_limits[key[1]]) * math.cos(math.pi / LINE_POLYGON_FACES)
        for face in range(LINE_POLYGON_FACES):
            angle = 2.0 * math.pi * face / LINE_POLYGON_FACES
            model.addConstr(
                opportunity.eta >= (
                    math.cos(angle) * p_flow + math.sin(angle) * q_flow
                ) / apothem + correction_value + float(bias[key[1]]),
                name=f"op_sep_line_face[{key[0]},{key[1]},{face}]",
            )
        opportunity.added_line_states.add(key)
        added += 1
    for slot, index in evaluation["voltage_violation_states"]:
        key = (int(slot), int(index))
        if key in opportunity.added_voltage_states:
            continue
        coefficient = opportunity.coefficients[key[0]]
        expression = _opportunity_sparse_expression(
            opportunity, float(coefficient.voltage_constant[key[1]]),
            coefficient.voltage_matrix[:, key[1]], key[0],
        )
        voltage = model.addVar(
            lb=0.95**2, ub=1.05**2,
            name=f"op_sep_v_squared[{key[0]},{key[1]}]",
        )
        model.addConstr(
            voltage == expression,
            name=f"op_sep_voltage_affine[{key[0]},{key[1]}]",
        )
        opportunity.added_voltage_states.add(key)
        added += 1
    for slot, index in evaluation["transformer_current_violation_states"]:
        key = (int(slot), int(index))
        if key in opportunity.added_transformer_current_states:
            continue
        coefficient = opportunity.coefficients[key[0]]
        expression = _opportunity_sparse_expression(
            opportunity, float(coefficient.current_constant[key[1]]),
            coefficient.current_matrix[:, key[1]], key[0],
        )
        model.addConstr(
            expression <= 1.0,
            name=f"op_sep_tx_current[{key[0]},{key[1]}]",
        )
        opportunity.added_transformer_current_states.add(key)
        added += 1
    for slot, index in evaluation["transformer_kva_violation_states"]:
        key = (int(slot), int(index))
        if key in opportunity.added_transformer_kva_states:
            continue
        coefficient = opportunity.coefficients[key[0]]
        p_flow = _opportunity_sparse_expression(
            opportunity, float(coefficient.flow_p_constant[key[1]]),
            coefficient.flow_p_matrix[key[1]], key[0],
        )
        q_flow = _opportunity_sparse_expression(
            opportunity, float(coefficient.flow_q_constant[key[1]]),
            coefficient.flow_q_matrix[key[1]], key[0],
        )
        rating = coefficient.transformer_ratings[key[1]]
        if rating is None:
            raise RuntimeError("V35R3_TRANSFORMER_RATING_AXIS")
        apothem = float(rating) * math.cos(math.pi / LINE_POLYGON_FACES)
        for face in range(LINE_POLYGON_FACES):
            angle = 2.0 * math.pi * face / LINE_POLYGON_FACES
            model.addConstr(
                math.cos(angle) * p_flow + math.sin(angle) * q_flow <= apothem,
                name=f"op_sep_tx_face[{key[0]},{key[1]},{face}]",
            )
        opportunity.added_transformer_kva_states.add(key)
        added += 1
    if added:
        model.update()
    return added


def solve_opportunity_candidate_certified(
    opportunity: OpportunityModel,
    candidate_id: str,
    *,
    max_separation_rounds: int = 20,
) -> tuple[dict[str, object], dict[str, object], int]:
    """Solve one fixed candidate and certify it against every Planning row."""

    fix_opportunity_candidate(opportunity, candidate_id)
    total_added = 0
    for _round_index in range(max_separation_rounds):
        opportunity.model.optimize()
        if opportunity.model.Status != GRB.OPTIMAL or opportunity.model.SolCount < 1:
            raise RuntimeError(
                f"V35R3_RESTRICTED_CANDIDATE_STATUS:{candidate_id}:{opportunity.model.Status}"
            )
        dispatch = opportunity_dispatch(opportunity)
        evaluation = evaluate_opportunity_dispatch(
            dispatch=dispatch,
            coefficients=opportunity.coefficients,
            aidc_pcc_kw_96x12=opportunity.aidc,
            services=opportunity.services,
            fixed_mess_p_by_service=opportunity.fixed_p,
            fixed_mess_q_by_service=opportunity.fixed_q,
            correction=opportunity.correction,
        )
        if evaluation["exact_optimality_certificate"]:
            return dispatch, evaluation, total_added
        added = add_opportunity_separation_rows(opportunity, evaluation)
        total_added += added
        if dispatch.get("simultaneous_charge_discharge_slots"):
            for variable in opportunity.direction.values():
                variable.VType = GRB.BINARY
            opportunity.model.update()
            added += 1
        if added == 0:
            raise RuntimeError(f"V35R3_RESTRICTED_CERTIFICATE_STALLED:{candidate_id}")
    raise RuntimeError(f"V35R3_RESTRICTED_CERTIFICATE_ROUND_LIMIT:{candidate_id}")


@dataclass
class FixedCandidateModel:
    model: gp.Model
    candidate: MobilityCandidate
    p_discharge: Mapping[int, gp.Var]
    p_charge: Mapping[int, gp.Var]
    q: Mapping[int, gp.Var]
    energy: Mapping[int, gp.Var]
    direction: Mapping[int, gp.Var]
    eta: gp.Var
    services: tuple[str, ...]
    aidc: np.ndarray
    coefficients: tuple[SlotCoefficients, ...]
    fixed_p: Mapping[tuple[str, int], float]
    fixed_q: Mapping[tuple[str, int], float]
    added_line_states: set[tuple[int, int]]
    added_voltage_states: set[tuple[int, int]]
    added_transformer_current_states: set[tuple[int, int]]
    added_transformer_kva_states: set[tuple[int, int]]


def _fixed_expression(
    item: FixedCandidateModel, base: float, vector: np.ndarray, slot: int,
) -> gp.LinExpr:
    constant = float(base + vector[:12] @ item.aidc[slot])
    constant += sum(
        float(vector[12 + index]) * float(item.fixed_p.get((service, slot), 0.0))
        + float(vector[36 + index]) * float(item.fixed_q.get((service, slot), 0.0))
        for index, service in enumerate(item.services)
    )
    service = _candidate_service(item.candidate, slot)
    if service is None:
        return gp.LinExpr(constant)
    index = item.services.index(service)
    return (
        float(vector[12 + index]) * (item.p_discharge[slot] - item.p_charge[slot])
        + float(vector[36 + index]) * item.q[slot]
        + constant
    )


def _add_fixed_line(item: FixedCandidateModel, slot: int, index: int) -> None:
    key = (int(slot), int(index))
    if key in item.added_line_states:
        return
    coefficient = item.coefficients[key[0]]
    branch = coefficient.branch_names[key[1]]
    if branch.startswith("transformer.") or is_dominated_mess_current_row(branch):
        raise ValueError("V35R3_FIXED_LINE_STATE_AXIS")
    bias, correction = _cached_polygon_parameters(coefficient)
    p_flow = _fixed_expression(item, float(coefficient.flow_p_constant[key[1]]), coefficient.flow_p_matrix[key[1]], key[0])
    q_flow = _fixed_expression(item, float(coefficient.flow_q_constant[key[1]]), coefficient.flow_q_matrix[key[1]], key[0])
    tangent = _fixed_expression(item, -float(correction[:, key[1]] @ coefficient.anchor), correction[:, key[1]], key[0])
    apothem = float(coefficient.branch_limits[key[1]]) * math.cos(math.pi / LINE_POLYGON_FACES)
    for face in range(LINE_POLYGON_FACES):
        angle = 2.0 * math.pi * face / LINE_POLYGON_FACES
        item.model.addConstr(
            item.eta >= (math.cos(angle) * p_flow + math.sin(angle) * q_flow) / apothem
            + tangent + float(bias[key[1]]),
            name=f"fixed_line[{key[0]},{key[1]},{face}]",
        )
    item.added_line_states.add(key)


def _add_fixed_voltage(item: FixedCandidateModel, slot: int, index: int) -> None:
    key = (int(slot), int(index))
    if key in item.added_voltage_states:
        return
    coefficient = item.coefficients[key[0]]
    expression = _fixed_expression(item, float(coefficient.voltage_constant[key[1]]), coefficient.voltage_matrix[:, key[1]], key[0])
    voltage = item.model.addVar(lb=0.95**2, ub=1.05**2, name=f"fixed_v[{key[0]},{key[1]}]")
    item.model.addConstr(voltage == expression, name=f"fixed_v_affine[{key[0]},{key[1]}]")
    item.added_voltage_states.add(key)


def _add_fixed_tx_current(item: FixedCandidateModel, slot: int, index: int) -> None:
    key = (int(slot), int(index))
    if key in item.added_transformer_current_states:
        return
    coefficient = item.coefficients[key[0]]
    item.model.addConstr(
        _fixed_expression(item, float(coefficient.current_constant[key[1]]), coefficient.current_matrix[:, key[1]], key[0]) <= 1.0,
        name=f"fixed_tx_current[{key[0]},{key[1]}]",
    )
    item.added_transformer_current_states.add(key)


def _add_fixed_tx_kva(item: FixedCandidateModel, slot: int, index: int) -> None:
    key = (int(slot), int(index))
    if key in item.added_transformer_kva_states:
        return
    coefficient = item.coefficients[key[0]]
    rating = coefficient.transformer_ratings[key[1]]
    if rating is None:
        raise ValueError("V35R3_FIXED_TX_STATE_AXIS")
    p_flow = _fixed_expression(item, float(coefficient.flow_p_constant[key[1]]), coefficient.flow_p_matrix[key[1]], key[0])
    q_flow = _fixed_expression(item, float(coefficient.flow_q_constant[key[1]]), coefficient.flow_q_matrix[key[1]], key[0])
    apothem = float(rating) * math.cos(math.pi / LINE_POLYGON_FACES)
    for face in range(LINE_POLYGON_FACES):
        angle = 2.0 * math.pi * face / LINE_POLYGON_FACES
        item.model.addConstr(
            math.cos(angle) * p_flow + math.sin(angle) * q_flow <= apothem,
            name=f"fixed_tx_kva[{key[0]},{key[1]},{face}]",
        )
    item.added_transformer_kva_states.add(key)


def build_fixed_candidate_model(
    *,
    candidate: MobilityCandidate,
    aidc_pcc_kw_96x12: np.ndarray,
    coefficients: Sequence[SlotCoefficients],
    services: Sequence[str],
    fixed_mess_p_by_service: Mapping[tuple[str, int], float] | None = None,
    fixed_mess_q_by_service: Mapping[tuple[str, int], float] | None = None,
    line_states: Sequence[tuple[int, int]] = (),
    voltage_states: Sequence[tuple[int, int]] = (),
    transformer_current_states: Sequence[tuple[int, int]] = (),
    transformer_kva_states: Sequence[tuple[int, int]] = (),
) -> FixedCandidateModel:
    """Build one small exact fixed-route P/Q/SoC relaxation."""

    aidc = np.asarray(aidc_pcc_kw_96x12, dtype=float)
    coeff = tuple(coefficients)
    service_axis = tuple(map(str, services))
    if aidc.shape != (HORIZON, 12) or len(coeff) != HORIZON:
        raise ValueError("V35R3_FIXED_CANDIDATE_AXIS")
    authority = MessElectricalAuthority.from_repository()
    model = gp.Model(f"v35r3_fixed_{candidate.candidate_id}")
    model.Params.OutputFlag = 0
    model.Params.Threads = 1
    model.Params.Seed = 20260828
    model.Params.FeasibilityTol = NUMERIC_TOLERANCE
    model.Params.OptimalityTol = NUMERIC_TOLERANCE
    p_dis = model.addVars(range(HORIZON), lb=0.0, name="fixed_p_dis")
    p_ch = model.addVars(range(HORIZON), lb=0.0, name="fixed_p_ch")
    q = model.addVars(range(HORIZON), lb=-GRB.INFINITY, name="fixed_q")
    direction = model.addVars(range(HORIZON), lb=0.0, ub=1.0, name="fixed_direction")
    energy = model.addVars(range(HORIZON + 1), lb=authority.energy_min_kwh, ub=authority.energy_max_kwh, name="fixed_energy")
    eta = model.addVar(lb=0.0, ub=1.0, name="fixed_rho")
    model.addConstr(energy[0] == authority.initial_energy_kwh)
    apothem = authority.pcs_kva * math.cos(math.pi / authority.pcs_polygon_faces)
    for slot in range(HORIZON):
        connected = float(_candidate_service(candidate, slot) is not None)
        model.addConstr(direction[slot] <= connected)
        model.addConstr(p_dis[slot] <= authority.active_power_limit_kw * direction[slot])
        model.addConstr(p_ch[slot] <= authority.active_power_limit_kw * (connected - direction[slot]))
        model.addConstr(q[slot] <= authority.pcs_kva * connected)
        model.addConstr(q[slot] >= -authority.pcs_kva * connected)
        for face in range(authority.pcs_polygon_faces):
            angle = 2.0 * math.pi * face / authority.pcs_polygon_faces
            model.addConstr(
                math.cos(angle) * (p_dis[slot] - p_ch[slot]) + math.sin(angle) * q[slot]
                <= apothem * connected
            )
        travel = candidate.safe_energy_kwh if candidate.departure_slot == slot else 0.0
        model.addConstr(energy[slot] >= authority.energy_min_kwh + travel)
        model.addConstr(
            energy[slot + 1] == energy[slot]
            + authority.charge_efficiency * authority.interval_hours * p_ch[slot]
            - authority.interval_hours * p_dis[slot] / authority.discharge_efficiency
            - travel
        )
    model.addConstr(energy[HORIZON] == authority.terminal_energy_kwh)
    constant = (
        1e-8 * candidate.safe_energy_kwh
        + (0.0 if candidate.is_stay else 1e-10)
        + 1e-16 * candidate.deterministic_full_move_ordinal
    )
    model.setObjective(eta + constant, GRB.MINIMIZE)
    item = FixedCandidateModel(
        model, candidate, p_dis, p_ch, q, energy, direction, eta, service_axis,
        aidc, coeff,
        MappingProxyType({} if fixed_mess_p_by_service is None else dict(fixed_mess_p_by_service)),
        MappingProxyType({} if fixed_mess_q_by_service is None else dict(fixed_mess_q_by_service)),
        set(), set(), set(), set(),
    )
    for slot, index in line_states:
        _add_fixed_line(item, slot, index)
    for slot, index in voltage_states:
        _add_fixed_voltage(item, slot, index)
    for slot, index in transformer_current_states:
        _add_fixed_tx_current(item, slot, index)
    for slot, index in transformer_kva_states:
        _add_fixed_tx_kva(item, slot, index)
    model.update()
    return item


def fixed_candidate_dispatch(item: FixedCandidateModel) -> dict[str, object]:
    p_dis = np.asarray([float(item.p_discharge[slot].X) for slot in range(HORIZON)])
    p_ch = np.asarray([float(item.p_charge[slot].X) for slot in range(HORIZON)])
    q = np.asarray([float(item.q[slot].X) for slot in range(HORIZON)])
    return {
        "candidate": item.candidate,
        "objective": float(item.model.ObjVal),
        "rho": float(item.eta.X),
        "p_discharge_kw": p_dis,
        "p_charge_kw": p_ch,
        "p_kw": p_dis - p_ch,
        "q_kvar": q,
        "energy_kwh": np.asarray([float(item.energy[slot].X) for slot in range(HORIZON + 1)]),
        "terminal_energy_kwh": float(item.energy[HORIZON].X),
        "simultaneous_charge_discharge_slots": [
            slot for slot in range(HORIZON)
            if p_dis[slot] > NUMERIC_TOLERANCE and p_ch[slot] > NUMERIC_TOLERANCE
        ],
        "post_arrival_sum_abs_p_kw_slots": float(np.abs(p_dis - p_ch)[item.candidate.connection_ready_slot or 0:].sum()),
        "post_arrival_sum_abs_q_kvar_slots": float(np.abs(q)[item.candidate.connection_ready_slot or 0:].sum()),
    }


def solve_fixed_candidate_certified(
    item: FixedCandidateModel, *, max_separation_rounds: int = 20,
) -> tuple[dict[str, object], dict[str, object]]:
    for _round_index in range(max_separation_rounds):
        item.model.optimize()
        if item.model.Status != GRB.OPTIMAL:
            raise RuntimeError(f"V35R3_FIXED_CANDIDATE_STATUS:{item.model.Status}")
        dispatch = fixed_candidate_dispatch(item)
        evaluation = evaluate_opportunity_dispatch(
            dispatch=dispatch, coefficients=item.coefficients,
            aidc_pcc_kw_96x12=item.aidc, services=item.services,
            fixed_mess_p_by_service=item.fixed_p, fixed_mess_q_by_service=item.fixed_q,
        )
        if evaluation["exact_optimality_certificate"]:
            return dispatch, evaluation
        before = sum(map(len, (
            item.added_line_states, item.added_voltage_states,
            item.added_transformer_current_states, item.added_transformer_kva_states,
        )))
        for state in evaluation["line_separation_states"]:
            _add_fixed_line(item, *state)
        for state in evaluation["voltage_violation_states"]:
            _add_fixed_voltage(item, *state)
        for state in evaluation["transformer_current_violation_states"]:
            _add_fixed_tx_current(item, *state)
        for state in evaluation["transformer_kva_violation_states"]:
            _add_fixed_tx_kva(item, *state)
        if dispatch["simultaneous_charge_discharge_slots"]:
            for variable in item.direction.values():
                variable.VType = GRB.BINARY
        item.model.update()
        after = sum(map(len, (
            item.added_line_states, item.added_voltage_states,
            item.added_transformer_current_states, item.added_transformer_kva_states,
        )))
        if after == before and not dispatch["simultaneous_charge_discharge_slots"]:
            raise RuntimeError(f"V35R3_FIXED_CERTIFICATE_STALLED:{item.candidate.candidate_id}")
    raise RuntimeError(f"V35R3_FIXED_CERTIFICATE_ROUND_LIMIT:{item.candidate.candidate_id}")

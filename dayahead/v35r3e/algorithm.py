"""Deterministic Planning-only screening for MESS warm-start candidates.

The screen ranks the complete one-relocation opportunity library cheaply.
It never changes or replaces the unrestricted multi-relocation production
MILP; selected candidates are only exact-solved to construct MIPStarts.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
import time
from types import MappingProxyType
from typing import Iterable, Mapping, Sequence

import numpy as np

from dayahead.grid_lp import LINE_POLYGON_FACES
from dayahead.v28r2.electrical_subproblem import (
    SlotCoefficients,
    anchored_polygon_loading,
    anchored_polygon_parameters,
    is_dominated_mess_current_row,
)
from dayahead.v33m.mess_mobility_milp import MessElectricalAuthority
from dayahead.v33m.route_table import MobilityRouteTable
from dayahead.v35.execution import MESS_INITIAL
from dayahead.v35r3.algorithm import MobilityCandidate, enumerate_initial_relocations


APR01 = "2025-04-01"
HORIZON = 96
LIBRARY_VERSION = "V35R3E_STATIC_ONE_RELOCATION_OPPORTUNITY_V1"
SCREEN_VARIANTS = ("S0", "S1", "S2", "S3", "S4")
K_GRID = (10, 20, 30, 50, 100, 200)
CERTIFICATION_K_GRID = (5, 10, 20, 30, 50, 100, 200, 400, 800, 2208)
NUMERICAL_REGRET_TOLERANCE = 1e-6
_SUPPORT_VECTOR_CACHE: dict[tuple[str, int, int, float, float], tuple[np.ndarray, np.ndarray]] = {}
_SLOT_RHO_CACHE: dict[tuple[str, int, int, float, float], tuple[float, float]] = {}
_CONTEXT_SUPPORT_CACHE: dict[str, tuple[np.ndarray, np.ndarray]] = {}
_POLYGON_PARAMETER_CACHE: dict[str, tuple[np.ndarray, np.ndarray]] = {}


def _anchored_loading_points(
    coefficient: SlotCoefficients,
    base: np.ndarray,
    p_index: int,
    q_index: int,
    points: np.ndarray,
) -> np.ndarray:
    """Vectorized frozen polygon loading for a small set of P/Q points."""

    cached = _POLYGON_PARAMETER_CACHE.get(coefficient.coefficient_sha256)
    if cached is None:
        bias, correction, _anchor = anchored_polygon_parameters(coefficient)
        cached = (bias, correction)
        _POLYGON_PARAMETER_CACHE[coefficient.coefficient_sha256] = cached
    bias, correction = cached
    flow_p_base = coefficient.flow_p_constant + coefficient.flow_p_matrix @ base
    flow_q_base = coefficient.flow_q_constant + coefficient.flow_q_matrix @ base
    flow_p = (
        flow_p_base[None, :]
        + points[:, 0, None] * coefficient.flow_p_matrix[:, p_index][None, :]
        + points[:, 1, None] * coefficient.flow_p_matrix[:, q_index][None, :]
    )
    flow_q = (
        flow_q_base[None, :]
        + points[:, 0, None] * coefficient.flow_q_matrix[:, p_index][None, :]
        + points[:, 1, None] * coefficient.flow_q_matrix[:, q_index][None, :]
    )
    apothem = np.asarray(coefficient.branch_limits, dtype=float) * math.cos(
        math.pi / LINE_POLYGON_FACES
    )
    angles = 2.0 * math.pi * np.arange(LINE_POLYGON_FACES) / LINE_POLYGON_FACES
    faces = (
        np.cos(angles)[:, None, None] * flow_p[None, :, :]
        + np.sin(angles)[:, None, None] * flow_q[None, :, :]
    ) / apothem[None, None, :]
    correction_value = (
        correction.T @ (base - coefficient.anchor)
    )[None, :] + points[:, 0, None] * correction[p_index][None, :] + points[:, 1, None] * correction[q_index][None, :]
    return np.max(faces, axis=0) + bias[None, :] + correction_value


def assert_apr01_only(day: str) -> None:
    if str(day) != APR01:
        raise PermissionError(f"V35R3E_APR01_ONLY:{day}")


def _canonical_sha(value: object) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class StaticCandidate:
    candidate_id: str
    vehicle_id: str
    origin_service_node: str
    destination_service_node: str
    departure_slot: int | None
    candidate_type: str
    static_od_identity: str
    static_topology_identity: str
    route_template_origin: str
    route_template_destination: str
    static_feasibility: str
    library_version: str = LIBRARY_VERSION


@dataclass(frozen=True)
class StaticLibrary:
    candidates: tuple[StaticCandidate, ...]
    library_sha: str
    generation_wallclock_seconds: float


def build_static_candidate_library(
    *,
    mess_ids: Sequence[str],
    service_ids: Sequence[str],
    route_graph_sha: str,
) -> StaticLibrary:
    """Materialize IDs/geometry only; no route or optimization solve occurs."""

    started = time.perf_counter()
    services = tuple(map(str, service_ids))
    rows: list[StaticCandidate] = []
    for mess_id in map(str, mess_ids):
        origin = str(MESS_INITIAL[mess_id])
        rows.append(StaticCandidate(
            candidate_id=f"{mess_id}:STAY:{origin}",
            vehicle_id=mess_id,
            origin_service_node=origin,
            destination_service_node=origin,
            departure_slot=None,
            candidate_type="STAY",
            static_od_identity=f"{origin}>{origin}",
            static_topology_identity=str(route_graph_sha),
            route_template_origin=origin,
            route_template_destination=origin,
            static_feasibility="STATIC_VALID_STAY",
        ))
        for destination in services:
            if destination == origin:
                continue
            for departure in range(HORIZON):
                rows.append(StaticCandidate(
                    candidate_id=f"{mess_id}:MOVE:{origin}:{destination}:{departure:02d}",
                    vehicle_id=mess_id,
                    origin_service_node=origin,
                    destination_service_node=destination,
                    departure_slot=departure,
                    candidate_type="MOVE",
                    static_od_identity=f"{origin}>{destination}",
                    static_topology_identity=str(route_graph_sha),
                    route_template_origin=origin,
                    route_template_destination=destination,
                    static_feasibility="REQUIRES_DAILY_ROUTE_AND_SOC_UPDATE",
                ))
    candidates = tuple(rows)
    payload = {
        "library_version": LIBRARY_VERSION,
        "route_graph_sha": str(route_graph_sha),
        "candidates": [asdict(row) for row in candidates],
    }
    return StaticLibrary(
        candidates,
        _canonical_sha(payload),
        time.perf_counter() - started,
    )


@dataclass(frozen=True)
class PlanningScreenContext:
    services: tuple[str, ...]
    coefficients: tuple[SlotCoefficients, ...]
    controls_96x60: np.ndarray
    line_mask: np.ndarray
    baseline_loading: np.ndarray
    critical_states: tuple[tuple[int, int], ...]
    global_state: tuple[int, int]
    service_gradients_p: np.ndarray
    service_gradients_q: np.ndarray
    sequential_previous_mess_count: int
    authority_sha: str


def build_planning_screen_context(
    *,
    aidc_pcc_kw_96x12: np.ndarray,
    coefficients: Sequence[SlotCoefficients],
    services: Sequence[str],
    fixed_mess_p_by_service: Mapping[tuple[str, int], float] | None = None,
    fixed_mess_q_by_service: Mapping[tuple[str, int], float] | None = None,
    sequential_previous_mess_count: int = 0,
) -> PlanningScreenContext:
    """Freeze current D-1 line states and active-face P/Q sensitivities."""

    aidc = np.asarray(aidc_pcc_kw_96x12, dtype=float)
    coeff = tuple(coefficients)
    service_axis = tuple(map(str, services))
    if aidc.shape != (HORIZON, 12) or len(coeff) != HORIZON or len(service_axis) != 24:
        raise ValueError("V35R3E_PLANNING_CONTEXT_AXIS")
    fixed_p = {} if fixed_mess_p_by_service is None else fixed_mess_p_by_service
    fixed_q = {} if fixed_mess_q_by_service is None else fixed_mess_q_by_service
    controls = np.zeros((HORIZON, 60), dtype=float)
    loading_rows = []
    gradients_p = []
    gradients_q = []
    line_mask = np.asarray([
        not name.startswith("transformer.") and not is_dominated_mess_current_row(name)
        for name in coeff[0].branch_names
    ], dtype=bool)
    line_indices = np.flatnonzero(line_mask)
    for slot, coefficient in enumerate(coeff):
        controls[slot, :12] = aidc[slot]
        controls[slot, 12:36] = [float(fixed_p.get((service, slot), 0.0)) for service in service_axis]
        controls[slot, 36:60] = [float(fixed_q.get((service, slot), 0.0)) for service in service_axis]
        loading = anchored_polygon_loading(coefficient, controls[slot])
        loading_rows.append(loading)
        flow_p = coefficient.flow_p_constant + coefficient.flow_p_matrix @ controls[slot]
        flow_q = coefficient.flow_q_constant + coefficient.flow_q_matrix @ controls[slot]
        _bias, tangent_delta, _anchor = anchored_polygon_parameters(coefficient)
        apothem = np.asarray(coefficient.branch_limits, dtype=float) * math.cos(
            math.pi / LINE_POLYGON_FACES
        )
        angles = 2.0 * math.pi * np.arange(LINE_POLYGON_FACES) / LINE_POLYGON_FACES
        faces = (
            np.cos(angles)[:, None] * flow_p[None, :]
            + np.sin(angles)[:, None] * flow_q[None, :]
        ) / apothem[None, :]
        active = np.argmax(faces, axis=0)
        c = np.cos(angles[active]) / apothem
        s = np.sin(angles[active]) / apothem
        gradient = (
            c[:, None] * coefficient.flow_p_matrix
            + s[:, None] * coefficient.flow_q_matrix
            + tangent_delta.T
        )
        gradients_p.append(gradient[:, 12:36])
        gradients_q.append(gradient[:, 36:60])
    baseline = np.asarray(loading_rows, dtype=float)
    gp = np.asarray(gradients_p, dtype=float)
    gq = np.asarray(gradients_q, dtype=float)
    line_values = baseline[:, line_mask]
    maximum = np.unravel_index(int(np.argmax(line_values)), line_values.shape)
    global_state = (int(maximum[0]), int(line_indices[maximum[1]]))
    top_flat = np.argsort(line_values, axis=None)[-20:]
    states = {
        (int(slot), int(line_indices[column]))
        for slot, column in zip(*np.unravel_index(top_flat, line_values.shape), strict=True)
    }
    rho = float(line_values.max())
    states.update(
        (int(slot), int(line_indices[column]))
        for slot, column in zip(*np.where(line_values >= 0.98 * rho - 1e-12), strict=True)
    )
    states.update(
        (slot, global_state[1])
        for slot in range(max(0, global_state[0] - 2), min(HORIZON, global_state[0] + 3))
    )
    authority_sha = _canonical_sha({
        "coefficient_shas": [row.coefficient_sha256 for row in coeff],
        "controls_sha": hashlib.sha256(controls.tobytes()).hexdigest(),
        "critical_states": sorted(states),
        "sequential_previous_mess_count": int(sequential_previous_mess_count),
    })
    return PlanningScreenContext(
        service_axis, coeff, controls, line_mask, baseline, tuple(sorted(states)),
        global_state, gp, gq, int(sequential_previous_mess_count), authority_sha,
    )


def _candidate_location(candidate: MobilityCandidate, slot: int) -> str | None:
    if candidate.is_stay:
        return candidate.origin
    if slot < int(candidate.departure_slot):
        return candidate.origin
    if slot >= int(candidate.connection_ready_slot):
        return candidate.destination
    return None


def _energy_limited_p_bounds(
    candidate: MobilityCandidate, slot: int, authority: MessElectricalAuthority,
) -> tuple[float, float]:
    """Transparent one-slot support bounds; no dispatch optimization."""

    if _candidate_location(candidate, slot) is None:
        return 0.0, 0.0
    apothem = authority.pcs_kva * math.cos(math.pi / authority.pcs_polygon_faces)
    p_limit = min(authority.active_power_limit_kw, apothem)
    travel = 0.0 if candidate.is_stay else float(candidate.safe_energy_kwh)
    departure = HORIZON if candidate.is_stay else int(candidate.departure_slot)
    ready = 0 if candidate.is_stay else int(candidate.connection_ready_slot)
    if slot < departure:
        max_energy = min(
            authority.energy_max_kwh,
            authority.initial_energy_kwh
            + slot * authority.interval_hours * authority.charge_efficiency * p_limit,
        )
        min_energy = max(
            authority.energy_min_kwh,
            authority.initial_energy_kwh
            - slot * authority.interval_hours * p_limit / authority.discharge_efficiency,
        )
    else:
        max_departure = min(
            authority.energy_max_kwh,
            authority.initial_energy_kwh
            + departure * authority.interval_hours * authority.charge_efficiency * p_limit,
        )
        min_departure = max(
            authority.energy_min_kwh + travel,
            authority.initial_energy_kwh
            - departure * authority.interval_hours * p_limit / authority.discharge_efficiency,
        )
        connected_before = max(0, slot - ready)
        max_energy = min(
            authority.energy_max_kwh,
            max_departure - travel
            + connected_before * authority.interval_hours * authority.charge_efficiency * p_limit,
        )
        min_energy = max(
            authority.energy_min_kwh,
            min_departure - travel
            - connected_before * authority.interval_hours * p_limit / authority.discharge_efficiency,
        )
    remaining_connected = HORIZON - slot - 1
    terminal_floor = max(
        authority.energy_min_kwh,
        authority.terminal_energy_kwh
        - remaining_connected * authority.interval_hours * authority.charge_efficiency * p_limit,
    )
    terminal_ceiling = min(
        authority.energy_max_kwh,
        authority.terminal_energy_kwh
        + remaining_connected * authority.interval_hours * p_limit / authority.discharge_efficiency,
    )
    discharge = min(
        p_limit,
        max(0.0, max_energy - terminal_floor)
        * authority.discharge_efficiency / authority.interval_hours,
    )
    charge = min(
        p_limit,
        max(0.0, terminal_ceiling - min_energy)
        / (authority.charge_efficiency * authority.interval_hours),
    )
    return float(discharge), float(charge)


def _best_linear_support(
    gp: np.ndarray,
    gq: np.ndarray,
    discharge_kw: float,
    charge_kw: float,
    authority: MessElectricalAuthority,
    *,
    use_pq_envelope: bool,
) -> np.ndarray:
    if not use_pq_envelope:
        generic = min(authority.active_power_limit_kw, authority.pcs_kva)
        return generic * np.hypot(gp, gq)
    apothem = authority.pcs_kva * math.cos(math.pi / authority.pcs_polygon_faces)
    angles = 2.0 * math.pi * np.arange(authority.pcs_polygon_faces) / authority.pcs_polygon_faces
    p = apothem * np.cos(angles)
    q = apothem * np.sin(angles)
    p = np.clip(p, -float(charge_kw), float(discharge_kw))
    values = gp[:, None] * p[None, :] + gq[:, None] * q[None, :]
    return np.maximum(0.0, -np.min(values, axis=1))


def _planning_feasible_support_vectors(
    context: PlanningScreenContext,
    *,
    slot: int,
    service: int,
    discharge_kw: float,
    charge_kw: float,
    authority: MessElectricalAuthority,
) -> tuple[np.ndarray, np.ndarray]:
    """Enumerate a small deterministic, physically filtered PCS envelope."""

    cache_key = (
        context.authority_sha,
        int(slot),
        int(service),
        round(float(discharge_kw), 6),
        round(float(charge_kw), 6),
    )
    cached = _SUPPORT_VECTOR_CACHE.get(cache_key)
    if cached is not None:
        return cached

    apothem = authority.pcs_kva * math.cos(math.pi / authority.pcs_polygon_faces)
    angles = 2.0 * math.pi * np.arange(authority.pcs_polygon_faces) / authority.pcs_polygon_faces
    p = np.clip(apothem * np.cos(angles), -float(charge_kw), float(discharge_kw))
    q = apothem * np.sin(angles)
    p = np.concatenate((p, [0.0, float(discharge_kw), -float(charge_kw), 0.0, 0.0]))
    q = np.concatenate((q, [0.0, 0.0, 0.0, apothem, -apothem]))
    points = np.unique(np.round(np.column_stack((p, q)), 10), axis=0)
    coefficient = context.coefficients[slot]
    base = context.controls_96x60[slot]
    p_index = 12 + service
    q_index = 36 + service
    squared_base = coefficient.voltage_constant + coefficient.voltage_matrix.T @ base
    squared = (
        squared_base[None, :]
        + points[:, 0, None] * coefficient.voltage_matrix[p_index][None, :]
        + points[:, 1, None] * coefficient.voltage_matrix[q_index][None, :]
    )
    valid = np.all(
        (squared >= 0.95**2 - 1e-8) & (squared <= 1.05**2 + 1e-8), axis=1,
    )
    branch_names = np.asarray(coefficient.branch_names).astype(str)
    tx_current = np.asarray([
        name.startswith("transformer.") and not is_dominated_mess_current_row(name)
        for name in branch_names
    ])
    if np.any(tx_current):
        affine_base = coefficient.current_constant + coefficient.current_matrix.T @ base
        affine = (
            affine_base[None, tx_current]
            + points[:, 0, None] * coefficient.current_matrix[p_index, tx_current][None, :]
            + points[:, 1, None] * coefficient.current_matrix[q_index, tx_current][None, :]
        )
        valid &= np.all(affine <= 1.0 + 1e-8, axis=1)
    flow_p_base = coefficient.flow_p_constant + coefficient.flow_p_matrix @ base
    flow_q_base = coefficient.flow_q_constant + coefficient.flow_q_matrix @ base
    flow_p = (
        flow_p_base[None, :]
        + points[:, 0, None] * coefficient.flow_p_matrix[:, p_index][None, :]
        + points[:, 1, None] * coefficient.flow_p_matrix[:, q_index][None, :]
    )
    flow_q = (
        flow_q_base[None, :]
        + points[:, 0, None] * coefficient.flow_q_matrix[:, p_index][None, :]
        + points[:, 1, None] * coefficient.flow_q_matrix[:, q_index][None, :]
    )
    # For feasibility use the exact frozen polygon surrogate at each point.
    line_loading = _anchored_loading_points(
        coefficient, base, p_index, q_index, points,
    )[:, context.line_mask]
    valid &= np.all(line_loading <= 1.0 + 1e-8, axis=1)
    ratings = np.asarray([
        np.nan if rating is None else float(rating)
        for rating in coefficient.transformer_ratings
    ])
    tx = np.isfinite(ratings)
    if np.any(tx):
        tx_apothem = ratings[tx] * math.cos(math.pi / LINE_POLYGON_FACES)
        face_angles = 2.0 * math.pi * np.arange(LINE_POLYGON_FACES) / LINE_POLYGON_FACES
        tx_faces = (
            np.cos(face_angles)[:, None, None] * flow_p[None, :, tx]
            + np.sin(face_angles)[:, None, None] * flow_q[None, :, tx]
        )
        valid &= np.all(tx_faces <= tx_apothem[None, None, :] + 1e-8, axis=(0, 2))
    if not np.any(valid):
        result = (np.asarray([0.0]), np.asarray([0.0]))
    else:
        result = (points[valid, 0], points[valid, 1])
    _SUPPORT_VECTOR_CACHE[cache_key] = result
    return result


def _joint_slot_prediction(
    context: PlanningScreenContext,
    *,
    slot: int,
    branches: Sequence[int],
    service: int,
    discharge_kw: float,
    charge_kw: float,
    authority: MessElectricalAuthority,
) -> np.ndarray:
    p, q = _planning_feasible_support_vectors(
        context,
        slot=slot,
        service=service,
        discharge_kw=discharge_kw,
        charge_kw=charge_kw,
        authority=authority,
    )
    base = context.baseline_loading[slot, branches]
    gp = context.service_gradients_p[slot, branches, service]
    gq = context.service_gradients_q[slot, branches, service]
    values = base[:, None] + gp[:, None] * p[None, :] + gq[:, None] * q[None, :]
    maximum = np.max(values, axis=0)
    mean = np.mean(values, axis=0)
    choice = int(np.lexsort((mean, maximum))[0])
    return values[:, choice]


def _exact_slot_support_summary(
    context: PlanningScreenContext,
    *,
    slot: int,
    service: int,
    discharge_kw: float,
    charge_kw: float,
    authority: MessElectricalAuthority,
) -> tuple[float, float]:
    """Minimum full-line rho over the finite support envelope, without a solve."""

    key = (
        context.authority_sha,
        int(slot),
        int(service),
        round(float(discharge_kw), 6),
        round(float(charge_kw), 6),
    )
    cached = _SLOT_RHO_CACHE.get(key)
    if cached is not None:
        return cached
    p, q = _planning_feasible_support_vectors(
        context,
        slot=slot,
        service=service,
        discharge_kw=discharge_kw,
        charge_kw=charge_kw,
        authority=authority,
    )
    coefficient = context.coefficients[slot]
    base = context.controls_96x60[slot]
    p_index = 12 + service
    q_index = 36 + service
    points = np.column_stack((p, q))
    line = _anchored_loading_points(
        coefficient, base, p_index, q_index, points,
    )[:, context.line_mask]
    values = list(zip(np.max(line, axis=1), np.mean(line, axis=1), strict=True))
    result = min(values, key=lambda row: (row[0], row[1]))
    _SLOT_RHO_CACHE[key] = result
    return result


def _precomputed_context_support(
    context: PlanningScreenContext,
    authority: MessElectricalAuthority,
) -> tuple[np.ndarray, np.ndarray]:
    """Compute each (slot, service) support value once per dynamic authority."""

    cached = _CONTEXT_SUPPORT_CACHE.get(context.authority_sha)
    if cached is not None:
        return cached
    apothem = authority.pcs_kva * math.cos(math.pi / authority.pcs_polygon_faces)
    p_limit = min(authority.active_power_limit_kw, apothem)
    rho = np.empty((HORIZON, len(context.services)), dtype=float)
    mean = np.empty_like(rho)
    for slot in range(HORIZON):
        for service in range(len(context.services)):
            rho[slot, service], mean[slot, service] = _exact_slot_support_summary(
                context,
                slot=slot,
                service=service,
                discharge_kw=p_limit,
                charge_kw=p_limit,
                authority=authority,
            )
    _CONTEXT_SUPPORT_CACHE[context.authority_sha] = (rho, mean)
    return rho, mean


def candidate_screen_score(
    candidate: MobilityCandidate,
    context: PlanningScreenContext,
    *,
    variant: str,
) -> tuple[float, Mapping[str, float | int | str]]:
    if variant not in SCREEN_VARIANTS:
        raise ValueError(f"V35R3E_SCREEN_VARIANT:{variant}")
    authority = MessElectricalAuthority.from_repository()
    service_index = {service: index for index, service in enumerate(context.services)}
    global_slot, global_branch = context.global_state
    destination = service_index[candidate.destination]
    gp_global = context.service_gradients_p[global_slot, global_branch, destination]
    gq_global = context.service_gradients_q[global_slot, global_branch, destination]
    if variant == "S0":
        potential = authority.pcs_kva * math.hypot(float(gp_global), float(gq_global))
        score = potential - 1e-8 * float(candidate.safe_energy_kwh)
        return float(score), MappingProxyType({
            "predicted_objective": float(context.baseline_loading[global_slot, global_branch] - potential),
            "support_state_count": 1,
            "authority_sha": context.authority_sha,
        })

    if variant in {"S3", "S4"}:
        support_rho, support_mean = _precomputed_context_support(context, authority)
        base_line = context.baseline_loading[:, context.line_mask]
        slot_rho = np.max(base_line, axis=1).copy()
        slot_mean = np.mean(base_line, axis=1).copy()
        supported = 0
        for slot in range(HORIZON):
            location = _candidate_location(candidate, slot)
            if location is None:
                continue
            service = service_index[location]
            slot_rho[slot] = support_rho[slot, service]
            slot_mean[slot] = support_mean[slot, service]
            supported += 1
        predicted_objective = float(np.max(slot_rho))
        critical_slots = {slot for slot, _branch in context.critical_states}
        predicted_mean = float(np.mean([slot_rho[slot] for slot in sorted(critical_slots)]))
        production_estimate = (
            predicted_objective
            + 1e-8 * float(candidate.safe_energy_kwh)
            + (0.0 if candidate.is_stay else 1e-10)
            + 1e-16 * int(candidate.deterministic_full_move_ordinal)
        )
        return float(-production_estimate), MappingProxyType({
            "predicted_objective": float(production_estimate),
            "predicted_mean_critical_loading": predicted_mean,
            "predicted_mean_all_line_loading": float(np.mean(slot_mean)),
            "support_state_count": int(supported),
            "authority_sha": context.authority_sha,
        })

    state_by_slot: dict[int, list[int]] = {}
    for slot, branch in context.critical_states:
        state_by_slot.setdefault(slot, []).append(branch)
    predicted = []
    supported_states = 0
    for slot, branches in state_by_slot.items():
        base = context.baseline_loading[slot, branches]
        location = _candidate_location(candidate, slot)
        if location is None:
            predicted.extend(map(float, base))
            continue
        service = service_index[location]
        gp = context.service_gradients_p[slot, branches, service]
        gq = context.service_gradients_q[slot, branches, service]
        if variant == "S1":
            discharge = charge = min(authority.active_power_limit_kw, authority.pcs_kva)
        else:
            discharge, charge = _energy_limited_p_bounds(candidate, slot, authority)
        reduction = _best_linear_support(
            gp, gq, discharge, charge, authority,
            use_pq_envelope=False,
        )
        slot_prediction = base - reduction
        predicted.extend(map(float, slot_prediction))
        supported_states += len(branches)
    predicted_objective = max(predicted) if predicted else float(
        context.baseline_loading[context.global_state]
    )
    # These are the exact frozen production tie-break coefficients.  They
    # discriminate near-equivalent departures without a fitted weight.
    predicted_mean = float(np.mean(predicted)) if predicted else predicted_objective
    production_estimate = (
        predicted_objective
        + 1e-8 * float(candidate.safe_energy_kwh)
        + (0.0 if candidate.is_stay else 1e-10)
        + 1e-16 * int(candidate.deterministic_full_move_ordinal)
    )
    return float(-production_estimate), MappingProxyType({
        "predicted_objective": float(production_estimate),
        "predicted_mean_critical_loading": predicted_mean,
        "support_state_count": int(supported_states),
        "authority_sha": context.authority_sha,
    })


def screen_dynamic_candidates(
    *,
    day: str,
    case: str,
    mess_id: str,
    route_table: MobilityRouteTable,
    context: PlanningScreenContext,
    variant: str,
) -> tuple[list[dict[str, object]], float]:
    assert_apr01_only(day)
    started = time.perf_counter()
    enumeration = enumerate_initial_relocations(
        day=day,
        mess_id=mess_id,
        initial_service=MESS_INITIAL[mess_id],
        route_table=route_table,
    )
    rows = []
    for candidate in enumeration.candidates:
        score, detail = candidate_screen_score(candidate, context, variant=variant)
        rows.append({
            "day": day,
            "case": str(case),
            "mess_id": mess_id,
            "candidate_id": candidate.candidate_id,
            "candidate_type": "STAY" if candidate.is_stay else "MOVE",
            "origin": candidate.origin,
            "destination": candidate.destination,
            "departure_slot": candidate.departure_slot,
            "connection_ready_slot": candidate.connection_ready_slot,
            "q10_route_semantics": "SAME_Q50_ROUTE_EVALUATED_UNDER_Q10",
            "q50_eta_seconds": candidate.q50_eta_seconds,
            "safe_eta_seconds": candidate.safe_eta_seconds,
            "safe_energy_kwh": candidate.safe_energy_kwh,
            "post_arrival_slots": HORIZON - int(candidate.connection_ready_slot or 0),
            "screen_variant": variant,
            "cheap_score": score,
            **dict(detail),
        })
    rows.sort(key=lambda row: (
        -float(row["cheap_score"]),
        float(row.get("predicted_mean_critical_loading", row["predicted_objective"])),
        str(row["candidate_id"]),
    ))
    for rank, row in enumerate(rows, start=1):
        row["cheap_rank_all"] = rank
    move_rank = 0
    for row in rows:
        if row["candidate_type"] == "MOVE":
            move_rank += 1
            row["cheap_rank_move"] = move_rank
        else:
            row["cheap_rank_move"] = None
    return rows, time.perf_counter() - started


def ranking_metrics(
    screening_rows: Sequence[Mapping[str, object]],
    exact_objective_by_candidate: Mapping[str, float],
    *,
    k_values: Iterable[int] = CERTIFICATION_K_GRID,
) -> dict[str, object]:
    exact = {
        str(candidate_id): float(objective)
        for candidate_id, objective in exact_objective_by_candidate.items()
    }
    move_rows = [row for row in screening_rows if row["candidate_type"] == "MOVE"]
    missing = set(exact) - {str(row["candidate_id"]) for row in screening_rows}
    if missing:
        raise ValueError(f"V35R3E_GROUND_TRUTH_CANDIDATE_MISSING:{sorted(missing)[:3]}")
    global_best_id, global_best = min(exact.items(), key=lambda item: (item[1], item[0]))
    exact_best_rank = next(
        int(row["cheap_rank_move"])
        for row in move_rows if row["candidate_id"] == global_best_id
    )
    metrics = {}
    for k in map(int, k_values):
        ids = [str(row["candidate_id"]) for row in move_rows[:k]]
        eligible = [(candidate_id, exact[candidate_id]) for candidate_id in ids]
        selected_id, selected = min(eligible, key=lambda item: (item[1], item[0]))
        regret = selected - global_best
        metrics[str(k)] = {
            "recall_exact_best": global_best_id in ids,
            "best_candidate_id_in_topk": selected_id,
            "best_objective_in_topk": selected,
            "absolute_regret": regret,
            "relative_regret": regret / max(abs(global_best), 1e-12),
        }
    return {
        "global_best_candidate_id": global_best_id,
        "global_best_objective": global_best,
        "exact_best_cheap_rank": exact_best_rank,
        "by_k": metrics,
    }


def choose_certified_k(
    metrics_by_solve: Mapping[str, Mapping[str, object]],
    *,
    tolerance: float = NUMERICAL_REGRET_TOLERANCE,
) -> tuple[int | None, str]:
    for k in K_GRID:
        acceptable = True
        large_benefit_captured = True
        for solve_id, payload in metrics_by_solve.items():
            item = payload["by_k"][str(k)]
            acceptable = acceptable and (
                bool(item["recall_exact_best"])
                or float(item["absolute_regret"]) <= tolerance
            )
            if solve_id in {"B2/MESS01", "B3/MESS01"}:
                large_benefit_captured = large_benefit_captured and bool(item["recall_exact_best"])
        if acceptable and large_benefit_captured:
            return k, (
                "SMALLEST_K_WITH_ALL_EXACT_BEST_RECALLED_OR_ABSOLUTE_REGRET_"
                f"LE_{tolerance:g}_AND_B2_B3_MESS01_EXACT_BEST_RECALLED"
            )
    return None, "NO_K_LE_200_CERTIFIED;ADAPTIVE_LARGER_K_REQUIRED"

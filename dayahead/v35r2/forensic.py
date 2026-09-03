"""Pure, testable V35R2 forensic calculations.

The module intentionally owns no campaign entry point.  Every public day
guard is closed at 2025-04-20 so a diagnostic caller cannot accidentally
cross the task's development-authority boundary.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping, Sequence

import numpy as np

from dayahead.grid_lp import LINE_POLYGON_FACES


APR01_20 = tuple(f"2025-04-{day:02d}" for day in range(1, 21))
DIAGNOSTIC_DAYS = ("2025-04-01", "2025-04-10", "2025-04-20")
CASES = ("B0", "B1", "B2", "B3")


def require_apr01_20(day: str) -> str:
    value = str(day)
    if value not in APR01_20:
        raise PermissionError(f"V35R2_APR20_AUTHORITY_BOUNDARY:{value}")
    return value


def require_diagnostic_day(day: str) -> str:
    value = require_apr01_20(day)
    if value not in DIAGNOSTIC_DAYS:
        raise PermissionError(f"V35R2_FRESH_DIAGNOSTIC_DAY_NOT_PREDECLARED:{value}")
    return value


def polygon_loading(
    p_kw: np.ndarray | float,
    q_kvar: np.ndarray | float,
    rating_kva: np.ndarray | float,
    *,
    faces: int = LINE_POLYGON_FACES,
) -> np.ndarray:
    """Return the established inner-polygon normalized loading epigraph.

    A value <= 1 satisfies every face of the project's frozen apparent-power
    polygon.  The maximum face projection is used, rather than a signed
    tangent to current magnitude.
    """

    if int(faces) < 4:
        raise ValueError("V35R2_CURRENT_POLYGON_FACE_COUNT")
    p = np.asarray(p_kw, dtype=float)
    q = np.asarray(q_kvar, dtype=float)
    rating = np.asarray(rating_kva, dtype=float)
    if np.any(~np.isfinite(p)) or np.any(~np.isfinite(q)) or np.any(~np.isfinite(rating)):
        raise ValueError("V35R2_CURRENT_POLYGON_NONFINITE")
    if np.any(rating <= 0):
        raise ValueError("V35R2_CURRENT_POLYGON_RATING")
    p, q, rating = np.broadcast_arrays(p, q, rating)
    apothem = rating * math.cos(math.pi / int(faces))
    projections = np.stack(
        [
            math.cos(2.0 * math.pi * face / int(faces)) * p
            + math.sin(2.0 * math.pi * face / int(faces)) * q
            for face in range(int(faces))
        ],
        axis=0,
    )
    return np.max(projections, axis=0) / apothem


def exact_apparent_loading(
    p_kw: np.ndarray | float,
    q_kvar: np.ndarray | float,
    rating_kva: np.ndarray | float,
) -> np.ndarray:
    rating = np.asarray(rating_kva, dtype=float)
    if np.any(~np.isfinite(rating)) or np.any(rating <= 0):
        raise ValueError("V35R2_EXACT_CURRENT_RATING")
    return np.hypot(np.asarray(p_kw, dtype=float), np.asarray(q_kvar, dtype=float)) / rating


def anchored_polygon_parameters(coefficient: object) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return bias, linear correction, and anchor polygon loading by branch.

    The resulting epigraph preserves the audited AC-current tangent's value
    and gradient at the frozen anchor while borrowing only the curvature from
    the project's pre-existing P/Q apparent-power polygon.
    """

    anchor = np.asarray(coefficient.anchor, dtype=float)
    p_anchor = np.asarray(coefficient.flow_p_constant, dtype=float) + np.asarray(
        coefficient.flow_p_matrix, dtype=float,
    ) @ anchor
    q_anchor = np.asarray(coefficient.flow_q_constant, dtype=float) + np.asarray(
        coefficient.flow_q_matrix, dtype=float,
    ) @ anchor
    limits = np.asarray(coefficient.branch_limits, dtype=float)
    apothem = limits * math.cos(math.pi / LINE_POLYGON_FACES)
    angles = 2.0 * math.pi * np.arange(LINE_POLYGON_FACES) / LINE_POLYGON_FACES
    c = np.cos(angles)
    s = np.sin(angles)
    projections = (
        c[:, None] * p_anchor[None, :] + s[:, None] * q_anchor[None, :]
    ) / apothem[None, :]
    active = np.argmax(projections, axis=0)
    polygon_anchor = projections[active, np.arange(len(limits))]
    sp = np.asarray(coefficient.flow_p_matrix, dtype=float)
    sq = np.asarray(coefficient.flow_q_matrix, dtype=float)
    polygon_gradient = np.column_stack([
        (c[face] * sp[branch] + s[face] * sq[branch]) / apothem[branch]
        for branch, face in enumerate(active)
    ])
    current_gradient = np.asarray(coefficient.current_matrix, dtype=float)
    if polygon_gradient.shape != current_gradient.shape:
        raise ValueError("V35R2_ANCHORED_POLYGON_GRADIENT_AXIS")
    correction = current_gradient - polygon_gradient
    current_anchor = np.asarray(coefficient.current_constant, dtype=float) + current_gradient.T @ anchor
    bias = current_anchor - polygon_anchor
    return bias, correction, polygon_anchor


def anchored_polygon_loading(coefficient: object, controls: np.ndarray) -> np.ndarray:
    """Evaluate the value-and-gradient-matched convex current surrogate."""

    x = np.asarray(controls, dtype=float)
    if x.shape != np.asarray(coefficient.anchor).shape or not np.isfinite(x).all():
        raise ValueError("V35R2_ANCHORED_POLYGON_CONTROL_AXIS")
    p = np.asarray(coefficient.flow_p_constant, dtype=float) + np.asarray(
        coefficient.flow_p_matrix, dtype=float,
    ) @ x
    q = np.asarray(coefficient.flow_q_constant, dtype=float) + np.asarray(
        coefficient.flow_q_matrix, dtype=float,
    ) @ x
    base = polygon_loading(p, q, np.asarray(coefficient.branch_limits, dtype=float))
    bias, correction, _anchor = anchored_polygon_parameters(coefficient)
    return base + bias + correction.T @ (x - np.asarray(coefficient.anchor, dtype=float))


def central_slope(minus: np.ndarray | float, plus: np.ndarray | float, step: float) -> np.ndarray:
    delta = float(step)
    if not math.isfinite(delta) or delta <= 0:
        raise ValueError("V35R2_FINITE_DIFFERENCE_STEP")
    left = np.asarray(minus, dtype=float)
    right = np.asarray(plus, dtype=float)
    if left.shape != right.shape or np.any(~np.isfinite(left)) or np.any(~np.isfinite(right)):
        raise ValueError("V35R2_FINITE_DIFFERENCE_AXIS")
    return (right - left) / (2.0 * delta)


def residual_metrics(fresh: np.ndarray, planning: np.ndarray) -> dict[str, float | int]:
    actual = np.asarray(fresh, dtype=float)
    model = np.asarray(planning, dtype=float)
    if actual.shape != model.shape or not actual.size:
        raise ValueError("V35R2_CURRENT_RESIDUAL_AXIS")
    residual = actual - model
    if not np.isfinite(residual).all():
        raise ValueError("V35R2_CURRENT_RESIDUAL_NONFINITE")
    absolute = np.abs(residual)
    return {
        "count": int(residual.size),
        "signed_mean": float(residual.mean()),
        "MAE": float(absolute.mean()),
        "RMSE": float(np.sqrt(np.mean(residual * residual))),
        "P95": float(np.quantile(absolute, 0.95)),
        "P99": float(np.quantile(absolute, 0.99)),
        "max": float(absolute.max()),
    }


def effect_metrics(
    planning_off: np.ndarray,
    planning_on: np.ndarray,
    fresh_off: np.ndarray,
    fresh_on: np.ndarray,
    *,
    active_tolerance: float = 1e-9,
) -> dict[str, float | int]:
    arrays = tuple(np.asarray(value, dtype=float) for value in (
        planning_off, planning_on, fresh_off, fresh_on,
    ))
    if len({value.shape for value in arrays}) != 1 or not arrays[0].size:
        raise ValueError("V35R2_EFFECT_AXIS")
    if any(not np.isfinite(value).all() for value in arrays):
        raise ValueError("V35R2_EFFECT_NONFINITE")
    plan = arrays[1] - arrays[0]
    fresh = arrays[3] - arrays[2]
    active = (np.abs(plan) > active_tolerance) | (np.abs(fresh) > active_tolerance)
    sign = np.sign(plan[active]) == np.sign(fresh[active])
    return {
        "cell_count": int(plan.size),
        "active_cell_count": int(active.sum()),
        "effect_RMSE": float(np.sqrt(np.mean((fresh - plan) ** 2))),
        "effect_MAE": float(np.mean(np.abs(fresh - plan))),
        "active_sign_match_rate": float(sign.mean()) if sign.size else 1.0,
        "planning_mean_abs_effect": float(np.mean(np.abs(plan))),
        "fresh_mean_abs_effect": float(np.mean(np.abs(fresh))),
        "planning_max_abs_effect": float(np.max(np.abs(plan))),
        "fresh_max_abs_effect": float(np.max(np.abs(fresh))),
    }


def critical_index(values: np.ndarray, line_mask: np.ndarray) -> tuple[int, int, float]:
    array = np.asarray(values, dtype=float)
    mask = np.asarray(line_mask, dtype=bool)
    if array.ndim != 2 or mask.shape != (array.shape[1],) or not mask.any():
        raise ValueError("V35R2_CRITICAL_AXIS")
    line_indices = np.flatnonzero(mask)
    local = np.unravel_index(int(np.argmax(array[:, mask])), array[:, mask].shape)
    return int(local[0]), int(line_indices[local[1]]), float(array[local[0], line_indices[local[1]]])


def critical_identity(
    planning: tuple[int, str, str],
    fresh: tuple[int, str, str],
) -> str:
    p_slot, p_branch, p_phase = planning
    f_slot, f_branch, f_phase = fresh
    if (p_slot, p_branch, p_phase) == (f_slot, f_branch, f_phase):
        return "EXACT_LINE_PHASE_SLOT"
    if (p_branch, p_phase) == (f_branch, f_phase):
        return "SAME_LINE_PHASE_DIFFERENT_SLOT"
    return "DIFFERENT_LINE_OR_PHASE"


def q_exploit_detect(
    q_values: Sequence[float],
    planning_rho: Sequence[float],
    fresh_rho: Sequence[float],
    *,
    material_drop: float = 1e-3,
    reproduction_ratio: float = 0.35,
) -> dict[str, object]:
    q = np.asarray(q_values, dtype=float)
    plan = np.asarray(planning_rho, dtype=float)
    fresh = np.asarray(fresh_rho, dtype=float)
    if q.ndim != plan.ndim or q.ndim != fresh.ndim or q.ndim != 1 or len(q) < 3:
        raise ValueError("V35R2_Q_SWEEP_AXIS")
    if not (np.isfinite(q).all() and np.isfinite(plan).all() and np.isfinite(fresh).all()):
        raise ValueError("V35R2_Q_SWEEP_NONFINITE")
    zero = int(np.argmin(np.abs(q)))
    plan_improvement = float(plan[zero] - np.min(plan))
    fresh_at_plan_best = float(fresh[zero] - fresh[int(np.argmin(plan))])
    opposite = bool(plan_improvement > material_drop and fresh_at_plan_best < -material_drop)
    weak = bool(
        plan_improvement > material_drop
        and fresh_at_plan_best < reproduction_ratio * plan_improvement
    )
    return {
        "planning_best_Q_kvar": float(q[int(np.argmin(plan))]),
        "fresh_best_Q_kvar": float(q[int(np.argmin(fresh))]),
        "planning_predicted_improvement": plan_improvement,
        "fresh_improvement_at_planning_best_Q": fresh_at_plan_best,
        "fresh_to_planning_reproduction_ratio": (
            fresh_at_plan_best / plan_improvement if plan_improvement > 0 else 1.0
        ),
        "opposite_direction": opposite,
        "exploit_confirmed": bool(weak or opposite),
    }


def aidc_shift_temporal_authority(
    off_workload: np.ndarray,
    on_workload: np.ndarray,
    binding_slots: Sequence[int],
    *,
    near_radius: int = 2,
) -> dict[str, float | int]:
    """Partition relocated node-hours into binding, near, and other slots."""

    off = np.asarray(off_workload, dtype=float)
    on = np.asarray(on_workload, dtype=float)
    if off.shape != on.shape or off.ndim < 1 or off.shape[-1] != 96:
        raise ValueError("V35R2_AIDC_TEMPORAL_AXIS")
    shifted_by_slot = 0.5 * np.abs(on - off).sum(axis=tuple(range(off.ndim - 1)))
    binding = {int(slot) for slot in binding_slots}
    if not binding or any(slot < 0 or slot >= 96 for slot in binding):
        raise ValueError("V35R2_AIDC_BINDING_SLOT")
    near = {
        slot
        for center in binding
        for slot in range(max(0, center - int(near_radius)), min(96, center + int(near_radius) + 1))
    } - binding
    at_binding = float(shifted_by_slot[list(sorted(binding))].sum())
    near_binding = float(shifted_by_slot[list(sorted(near))].sum()) if near else 0.0
    total = float(shifted_by_slot.sum())
    return {
        "binding_slot_count": len(binding),
        "near_slot_count": len(near),
        "shifted_nodeh_total": total,
        "shifted_nodeh_at_binding_slots": at_binding,
        "shifted_nodeh_near_binding_slots": near_binding,
        "shifted_nodeh_other_slots": max(0.0, total - at_binding - near_binding),
        "binding_share": at_binding / total if total > 0 else 0.0,
        "binding_plus_near_share": (at_binding + near_binding) / total if total > 0 else 0.0,
    }


def electrical_diversity(
    service_to_pcc: Mapping[str, str],
    fingerprints: Mapping[str, Sequence[float]],
    *,
    equivalence_tolerance: float = 1e-10,
) -> dict[str, object]:
    services = tuple(sorted(map(str, service_to_pcc)))
    if len(services) != 24 or set(services) != set(map(str, fingerprints)):
        raise ValueError("V35R2_SERVICE_MAPPING_AXIS")
    vectors = {service: np.asarray(fingerprints[service], dtype=float) for service in services}
    if len({vector.shape for vector in vectors.values()}) != 1:
        raise ValueError("V35R2_SERVICE_FINGERPRINT_AXIS")
    groups: list[list[str]] = []
    for service in services:
        for group in groups:
            if np.max(np.abs(vectors[service] - vectors[group[0]])) <= equivalence_tolerance:
                group.append(service)
                break
        else:
            groups.append([service])
    return {
        "service_count": len(services),
        "unique_electrical_PCC_count": len(set(service_to_pcc.values())),
        "distinct_sensitivity_fingerprint_count": len(groups),
        "equivalent_service_groups": [group for group in groups if len(group) > 1],
        "maximum_pairwise_fingerprint_distance": float(max(
            np.linalg.norm(vectors[left] - vectors[right], ord=np.inf)
            for index, left in enumerate(services)
            for right in services[index + 1 :]
        )),
    }


def deterministic_farthest_point_cover(
    distances: Mapping[tuple[str, str], float],
    eligible_services: Sequence[str],
    *,
    count: int,
    seed: str | None = None,
) -> tuple[str, ...]:
    """Select depots from road distance only with lexical tie-breaking."""

    services = tuple(sorted(map(str, eligible_services)))
    if not services or not 1 <= int(count) <= len(services):
        raise ValueError("V35R2_DEPOT_COVER_AXIS")
    first = services[0] if seed is None else str(seed)
    if first not in services:
        raise ValueError("V35R2_DEPOT_COVER_SEED")
    for left in services:
        for right in services:
            value = 0.0 if left == right else distances.get((left, right))
            if value is None or not math.isfinite(float(value)) or float(value) < 0:
                raise ValueError("V35R2_DEPOT_COVER_DISTANCE")
    selected = [first]
    while len(selected) < int(count):
        candidates = []
        for service in services:
            if service in selected:
                continue
            minimum = min(float(distances[(chosen, service)]) for chosen in selected)
            candidates.append((minimum, service))
        # max distance, then lexicographically smallest service.
        best_distance = max(value for value, _service in candidates)
        selected.append(min(
            service for value, service in candidates
            if math.isclose(value, best_distance, rel_tol=0.0, abs_tol=1e-12)
        ))
    return tuple(selected)


@dataclass(frozen=True)
class InvalidationScope:
    preserved_case_days: tuple[str, ...]
    invalidated_case_days: tuple[str, ...]
    correction_rebuild_required: bool


def move_feasibility(
    *,
    departure_slot: int,
    connection_ready_slots: int,
    horizon_slots: int,
    energy_before_kwh: float,
    travel_energy_kwh: float,
    minimum_energy_kwh: float,
) -> dict[str, object]:
    """Audit end-of-horizon, travel-energy, and post-arrival eligibility."""

    departure = int(departure_slot)
    ready = departure + int(connection_ready_slots)
    horizon = int(horizon_slots)
    remaining = max(0, horizon - ready)
    energy_after = float(energy_before_kwh) - float(travel_energy_kwh)
    feasible = (
        0 <= departure < horizon
        and int(connection_ready_slots) > 0
        and ready < horizon
        and energy_after >= float(minimum_energy_kwh) - 1e-9
    )
    return {
        "connection_ready_slot": ready,
        "remaining_connected_slots": remaining,
        "energy_after_travel_kWh": energy_after,
        "post_arrival_PQ_eligible": bool(feasible and remaining > 0),
        "feasible": bool(feasible),
    }


def dependency_scoped_invalidation(
    *,
    common_current_changed: bool,
    aidc_mapping_changed: bool,
    mess_mapping_changed: bool,
) -> InvalidationScope:
    all_items = tuple(f"{day}/{case}" for day in APR01_20 for case in CASES)
    if common_current_changed or aidc_mapping_changed:
        invalidated = all_items
    elif mess_mapping_changed:
        invalidated = tuple(f"{day}/{case}" for day in APR01_20 for case in ("B2", "B3"))
    else:
        invalidated = ()
    invalidated_set = set(invalidated)
    preserved = tuple(item for item in all_items if item not in invalidated_set)
    return InvalidationScope(
        preserved,
        invalidated,
        bool(common_current_changed or aidc_mapping_changed or mess_mapping_changed),
    )

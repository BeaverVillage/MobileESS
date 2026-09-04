"""V17-contract voltage-restoration adapter for the V37 integrated MESS path.

The normal candidate/beam search is deliberately outside this module.  Once
that search has selected a complete four-vehicle trajectory, this adapter
holds every mobility decision fixed and permits only MESS P/Q recourse.
"""

from __future__ import annotations

from dataclasses import replace
import hashlib
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from dayahead.mess_physics import PCS_KVA, P_LIMIT_KW
from dayahead.v17_ac_restoration_contract import (
    ACViolation,
    K_MAX,
    RHO,
    RestorationCut,
    ViolationType,
    canonical_sha256,
)
from dayahead.v28r2.opendss_backend import _branch_measurement, _voltage_vector
from dayahead.v28r2.opendss_mapping import (
    FeederAssets,
    apply_frozen_native_state,
    apply_trajectory_slot,
    compile_clean_engine,
)
from dayahead.v28r2.trajectory import FrozenTrajectory
from dayahead.v28r2.opendss_results import OpenDSSResult
from dayahead.v33m.mess_trajectory import MessTrajectory
from dayahead.v34.integrated_mess import IntegratedMessResult, solve_integrated_mess
from dayahead.v35.contracts import MESS_IDS
from dayahead.v35.execution import MESS_INITIAL, _combined_trajectory_arrays
from dayahead.v36.science import canonical_sha256 as schedule_sha256
from dayahead.v37r3.voltage_authority import joint_repaired_coefficients


V_MIN = 0.95
V_MAX = 1.05
HARD_TOLERANCE = 1.0e-9
ANCHOR_REPEAT_TOLERANCE_PU = 1.0e-6
FINITE_DIFFERENCE_STEP = 5.0


def load_fresh_result(path: Path) -> OpenDSSResult:
    import json

    arrays = np.load(path / "OPENDSS_PHASE_ARRAYS.npz", allow_pickle=False)
    manifest = json.loads(
        (path / "OPENDSS_OUTPUT_MANIFEST.json").read_text(encoding="utf-8")
    )
    summary = json.loads((path / "OPENDSS_SUMMARY.json").read_text(encoding="utf-8"))
    branch_kinds = tuple(map(str, arrays["branch_kinds"]))
    transformer_kva = np.asarray(
        arrays["transformer_total_kva_loading_pu"], dtype=float,
    )
    line_mask = np.asarray([kind == "line" for kind in branch_kinds], dtype=bool)
    transformer_kva[:, line_mask] = np.nan
    value = OpenDSSResult(
        day=str(manifest["day"]),
        namespace="DAYAHEAD",
        case=str(manifest["case"]),
        schedule_sha256=str(manifest["schedule_sha256"]),
        node_names=tuple(map(str, arrays["node_names"])),
        node_phases=tuple(map(str, arrays["node_phases"])),
        branch_names=tuple(map(str, arrays["branch_names"])),
        branch_phases=tuple(map(str, arrays["branch_phases"])),
        branch_kinds=branch_kinds,
        convergence=np.asarray(arrays["convergence"], dtype=bool),
        voltage_pu=np.asarray(arrays["voltage_pu"], dtype=float),
        phase_current_a=np.asarray(arrays["phase_current_a"], dtype=float),
        phase_current_loading_pu=np.asarray(
            arrays["phase_current_loading_pu"], dtype=float,
        ),
        transformer_total_kva_loading_pu=transformer_kva,
        losses_kw_kvar=np.asarray(arrays["losses_kw_kvar"], dtype=float),
        regulator_taps=np.asarray(arrays["regulator_taps"], dtype=float),
        capacitor_states=np.asarray(arrays["capacitor_states"], dtype=int),
        opendss_version=str(summary["opendss_version"]),
        elapsed_seconds=float(summary["elapsed_seconds"]),
    )
    value.validate()
    return value


def frozen_trajectory(
    day: str,
    case: str,
    aidc: Any,
    trajectory: MessTrajectory,
    *,
    round_index: int,
) -> FrozenTrajectory:
    p, q, _energy, locations, _modes = _combined_trajectory_arrays(trajectory)
    identity = schedule_sha256({
        "date": day,
        "case": case,
        "restoration_round": int(round_index),
        "AIDC_P": hashlib.sha256(np.asarray(aidc.pcc_p_kw, dtype=float).tobytes()).hexdigest(),
        "AIDC_Q": hashlib.sha256(np.asarray(aidc.pcc_q_kvar, dtype=float).tobytes()).hexdigest(),
        "MESS_trajectory": trajectory.canonical_sha256,
    })
    value = FrozenTrajectory(
        day, "DAYAHEAD", case,
        np.asarray(aidc.pcc_p_kw, dtype=float),
        np.asarray(aidc.pcc_q_kvar, dtype=float),
        p, q, MESS_IDS, locations, identity,
    )
    value.validate()
    return value


def control_matrix(voltage: object, frozen: FrozenTrajectory) -> np.ndarray:
    names = tuple(map(str, voltage["control_names"]))
    services = tuple(name[10:-1] for name in names[12:36])
    values = np.zeros((96, 60), dtype=float)
    values[:, :12] = np.asarray(frozen.pcc_p_kw, dtype=float)
    service_index = {service: index for index, service in enumerate(services)}
    for slot in range(96):
        for mess_index, location in enumerate(frozen.mess_locations_96x4[slot]):
            service = str(location).upper()
            if service.startswith("TRANSIT_"):
                continue
            index = service_index[service]
            values[slot, 12 + index] += float(frozen.mess_p_kw[slot, mess_index])
            values[slot, 36 + index] += float(frozen.mess_q_kvar[slot, mess_index])
    return values


def _state_payload(fresh: Any, slot: int) -> dict[str, Any]:
    return {
        "slot": int(slot),
        "voltage": {
            node: float(value)
            for node, value in zip(fresh.node_names, fresh.voltage_pu[slot], strict=True)
        },
        "phase_current_loading_pu": {
            f"{name}::{phase}": float(value)
            for name, phase, value in zip(
                fresh.branch_names,
                fresh.branch_phases,
                fresh.phase_current_loading_pu[slot],
                strict=True,
            )
        },
        "transformer_total_kva_loading_pu": {
            f"{name}::{phase}": None if np.isnan(value) else float(value)
            for name, phase, value in zip(
                fresh.branch_names,
                fresh.branch_phases,
                fresh.transformer_total_kva_loading_pu[slot],
                strict=True,
            )
        },
    }


def extract_ac_violations(fresh: Any) -> tuple[ACViolation, ...]:
    """Extract every immutable V17 AC violation from a persisted Fresh replay."""

    rows: list[ACViolation] = []
    state_sha_by_slot = {
        slot: canonical_sha256(_state_payload(fresh, slot)) for slot in range(96)
    }
    for slot, node_index in zip(*np.where(
        (fresh.voltage_pu < V_MIN - HARD_TOLERANCE)
        | (fresh.voltage_pu > V_MAX + HARD_TOLERANCE)
    )):
        value = float(fresh.voltage_pu[slot, node_index])
        node = str(fresh.node_names[node_index])
        bus, phase_number = node.rsplit(".", 1)
        upper = value > V_MAX
        rows.append(ACViolation(
            ViolationType.VOLTAGE_UPPER if upper else ViolationType.VOLTAGE_LOWER,
            str(fresh.day), str(fresh.case), int(slot), f"bus.{bus}",
            "ABC"[int(phase_number) - 1], value, V_MAX if upper else V_MIN,
            value - V_MAX if upper else V_MIN - value,
            state_sha_by_slot[int(slot)],
            str(fresh.schedule_sha256),
        ))
    for slot in range(96):
        transformer_kva_seen: set[str] = set()
        for branch_index, (name, phase, kind) in enumerate(zip(
            fresh.branch_names, fresh.branch_phases, fresh.branch_kinds, strict=True,
        )):
            loading = float(fresh.phase_current_loading_pu[slot, branch_index])
            if loading > 1.0 + HARD_TOLERANCE:
                violation_type = (
                    ViolationType.LINE_CURRENT
                    if str(kind) == "line"
                    else ViolationType.TRANSFORMER_CURRENT
                )
                rows.append(ACViolation(
                    violation_type, str(fresh.day), str(fresh.case), slot,
                    str(name), str(phase), loading, 1.0, loading - 1.0,
                    state_sha_by_slot[slot], str(fresh.schedule_sha256),
                ))
            kva = float(fresh.transformer_total_kva_loading_pu[slot, branch_index])
            if (
                str(kind) == "transformer"
                and str(name) not in transformer_kva_seen
                and kva > 1.0 + HARD_TOLERANCE
            ):
                transformer_kva_seen.add(str(name))
                rows.append(ACViolation(
                    ViolationType.TRANSFORMER_KVA,
                    str(fresh.day), str(fresh.case), slot, str(name), None,
                    kva, 1.0, kva - 1.0,
                    state_sha_by_slot[slot], str(fresh.schedule_sha256),
                ))
    return tuple(rows)


def extract_voltage_violations(fresh: Any) -> tuple[ACViolation, ...]:
    """Compatibility name retained for callers from the voltage-only prototype."""

    return extract_ac_violations(fresh)


def restoration_cut_from_payload(payload: Mapping[str, Any]) -> RestorationCut:
    value = dict(payload)
    value["violation_type"] = ViolationType(str(value["violation_type"]))
    for name in ("control_names", "anchor_controls", "coefficients", "local_radius"):
        value[name] = tuple(value[name])
    return RestorationCut(**value)


def _target_node(violation: ACViolation) -> str:
    return (
        f"{violation.asset.split('.', 1)[1]}."
        f"{'ABC'.index(str(violation.phase)) + 1}"
    ).lower()


def _violation_measurements(
    odd: object,
    violations: Sequence[ACViolation],
    nodes: tuple[str, ...],
    voltage_values: np.ndarray,
    branches: Sequence[object],
) -> dict[str, float]:
    node_index = {name.lower(): index for index, name in enumerate(nodes)}
    branch_by_phase = {
        (str(branch.branch_id).lower(), str(branch.phase).upper()): branch
        for branch in branches
    }
    first_branch = {}
    for branch in branches:
        first_branch.setdefault(str(branch.branch_id).lower(), branch)
    values: dict[str, float] = {}
    branch_cache: dict[tuple[str, str | None], tuple[float, float, float]] = {}
    for violation in violations:
        if violation.violation_type in {
            ViolationType.VOLTAGE_UPPER, ViolationType.VOLTAGE_LOWER,
        }:
            values[violation.sha256] = float(
                voltage_values[node_index[_target_node(violation)]]
            )
            continue
        branch_name = str(violation.asset).lower()
        phase = None if violation.phase is None else str(violation.phase).upper()
        key = (branch_name, phase)
        if key not in branch_cache:
            branch = (
                first_branch[branch_name]
                if violation.violation_type == ViolationType.TRANSFORMER_KVA
                else branch_by_phase[(branch_name, str(phase))]
            )
            branch_cache[key] = _branch_measurement(odd, branch)
        measurement = branch_cache[key]
        values[violation.sha256] = float(
            measurement[2]
            if violation.violation_type == ViolationType.TRANSFORMER_KVA
            else measurement[1]
        )
    return values


def _perturbed(
    frozen: FrozenTrajectory,
    *,
    slot: int,
    service: str,
    p_delta: float = 0.0,
    q_delta: float = 0.0,
) -> FrozenTrajectory:
    locations = np.asarray(frozen.mess_locations_96x4).astype(str)
    candidates = [
        index for index, location in enumerate(locations[slot])
        if str(location).upper() == service
    ]
    if not candidates:
        raise RuntimeError(f"V37_R3_PERTURB_INACTIVE_SERVICE:{slot}:{service}")
    index = candidates[0]
    p = np.asarray(frozen.mess_p_kw, dtype=float).copy()
    q = np.asarray(frozen.mess_q_kvar, dtype=float).copy()
    p[slot, index] += float(p_delta)
    q[slot, index] += float(q_delta)
    return replace(frozen, mess_p_kw=p, mess_q_kvar=q)


def _solve_slot(
    odd: object,
    adapter: Mapping[str, object],
    electrical: Any,
    voltage: object,
    frozen: FrozenTrajectory,
    slot: int,
    nodes: tuple[str, ...],
) -> np.ndarray:
    apply_trajectory_slot(odd, adapter, electrical, frozen, slot)
    apply_frozen_native_state(odd, voltage, slot)
    odd.Solution.SolveSnap()
    if not bool(odd.Solution.Converged()):
        raise RuntimeError(f"V37_R3_LOCAL_FRESH_NONCONVERGENCE:{slot}")
    return _voltage_vector(odd, nodes)


def local_fresh_ac_restoration_cuts(
    *,
    source_repo: Path,
    electrical: Any,
    voltage: object,
    frozen: FrozenTrajectory,
    fresh: Any,
    violations: Sequence[ACViolation],
    iteration_index: int,
    margins: Mapping[str, float],
) -> tuple[tuple[RestorationCut, ...], dict[str, Any]]:
    """Generate all V17 current-Fresh-state frozen-tap AC cuts."""

    names = tuple(map(str, voltage["control_names"]))
    nodes = tuple(map(str, voltage["node_names"]))
    controls = control_matrix(voltage, frozen)
    by_slot = {
        slot: tuple(row for row in violations if int(row.slot) == slot)
        for slot in sorted({int(row.slot) for row in violations})
    }
    cuts: list[RestorationCut] = []
    derivative_rows: list[dict[str, Any]] = []
    solve_count = 0
    maximum_anchor_error = 0.0
    assets = FeederAssets.from_repo(source_repo)
    branches = tuple(electrical.legacy_context[3].factories[0].data.branches)
    fresh_axis = tuple(zip(
        map(str.lower, fresh.branch_names), map(str.upper, fresh.branch_phases),
        strict=True,
    ))
    branch_axis = tuple(
        (str(branch.branch_id).lower(), str(branch.phase).upper())
        for branch in branches
    )
    if branch_axis != fresh_axis:
        raise RuntimeError("V37_R3_FRESH_BRANCH_AXIS_MISMATCH")
    for slot, slot_violations in by_slot.items():
        odd, adapter = compile_clean_engine(assets)
        try:
            anchor_voltage = np.empty(len(nodes), dtype=float)
            for history_slot in range(slot + 1):
                anchor_voltage = _solve_slot(
                    odd, adapter, electrical, voltage, frozen, history_slot, nodes,
                )
                solve_count += 1
            anchor_error = float(np.max(np.abs(
                anchor_voltage - np.asarray(fresh.voltage_pu[slot], dtype=float)
            )))
            maximum_anchor_error = max(maximum_anchor_error, anchor_error)
            if anchor_error > ANCHOR_REPEAT_TOLERANCE_PU:
                raise RuntimeError(
                    f"V37_R3_STALE_FRESH_ANCHOR:{slot}:{anchor_error}"
                )
            anchor_measurements = _violation_measurements(
                odd, slot_violations, nodes, anchor_voltage, branches,
            )
            metric_anchor_error = max(
                abs(anchor_measurements[row.sha256] - float(row.actual_value))
                for row in slot_violations
            )
            maximum_anchor_error = max(maximum_anchor_error, metric_anchor_error)
            if metric_anchor_error > ANCHOR_REPEAT_TOLERANCE_PU:
                raise RuntimeError(
                    f"V37_R3_STALE_FRESH_AC_ANCHOR:{slot}:{metric_anchor_error}"
                )
            active_services = sorted({
                str(location).upper()
                for location in frozen.mess_locations_96x4[slot]
                if not str(location).upper().startswith("TRANSIT_")
            })
            derivatives = {
                row.sha256: np.zeros(60, dtype=float) for row in slot_violations
            }
            for service in active_services:
                for kind, offset in (("P", 12), ("Q", 36)):
                    control_index = names.index(
                        f"mess_p_kw[{service}]" if kind == "P"
                        else f"mess_q_kvar[{service}]"
                    )
                    plus = _perturbed(
                        frozen, slot=slot, service=service,
                        p_delta=FINITE_DIFFERENCE_STEP if kind == "P" else 0.0,
                        q_delta=FINITE_DIFFERENCE_STEP if kind == "Q" else 0.0,
                    )
                    plus_voltage = _solve_slot(
                        odd, adapter, electrical, voltage, plus, slot, nodes,
                    )
                    solve_count += 1
                    plus_measurements = _violation_measurements(
                        odd, slot_violations, nodes, plus_voltage, branches,
                    )
                    minus = _perturbed(
                        frozen, slot=slot, service=service,
                        p_delta=-FINITE_DIFFERENCE_STEP if kind == "P" else 0.0,
                        q_delta=-FINITE_DIFFERENCE_STEP if kind == "Q" else 0.0,
                    )
                    minus_voltage = _solve_slot(
                        odd, adapter, electrical, voltage, minus, slot, nodes,
                    )
                    solve_count += 1
                    minus_measurements = _violation_measurements(
                        odd, slot_violations, nodes, minus_voltage, branches,
                    )
                    for row in slot_violations:
                        value = float(
                            plus_measurements[row.sha256]
                            - minus_measurements[row.sha256]
                        ) / (2.0 * FINITE_DIFFERENCE_STEP)
                        derivatives[row.sha256][control_index] = value
                        derivative_rows.append({
                            "iteration_index": int(iteration_index),
                            "violation_sha256": row.sha256,
                            "slot": int(slot),
                            "asset": row.asset,
                            "phase": row.phase,
                            "source_service": service,
                            "control_kind": kind,
                            "control_index": int(control_index),
                            "coefficient_pu_per_unit": value,
                            "finite_difference_step": FINITE_DIFFERENCE_STEP,
                        })
                    _solve_slot(
                        odd, adapter, electrical, voltage, frozen, slot, nodes,
                    )
                    solve_count += 1

            radius = np.zeros(60, dtype=float)
            radius[12:36] = RHO * P_LIMIT_KW
            radius[36:60] = RHO * PCS_KVA
            local_state_sha = canonical_sha256({
                "slot": int(slot),
                "voltage": {
                    node: float(value)
                    for node, value in zip(nodes, anchor_voltage, strict=True)
                },
                "Fresh_trigger_state_sha256": slot_violations[0].fresh_opendss_state_sha256,
                "anchor_repeat_tolerance_pu": ANCHOR_REPEAT_TOLERANCE_PU,
            })
            for row in slot_violations:
                coefficient = derivatives[row.sha256]
                derivative_sha = hashlib.sha256(
                    np.asarray(coefficient, dtype=np.float64).tobytes()
                ).hexdigest()
                voltage_violation = row.violation_type in {
                    ViolationType.VOLTAGE_UPPER, ViolationType.VOLTAGE_LOWER,
                }
                margin = float(
                    margins["m_V_pu"] if voltage_violation else (
                        margins["m_transformer_kva_pu"]
                        if row.violation_type == ViolationType.TRANSFORMER_KVA
                        else margins["m_I_pu"]
                    )
                )
                cuts.append(RestorationCut(
                    violation_sha256=row.sha256,
                    local_ac_operating_point_sha256=local_state_sha,
                    derivative_sha256=derivative_sha,
                    violation_type=row.violation_type,
                    slot=int(slot),
                    relation=">=" if row.violation_type == ViolationType.VOLTAGE_LOWER else "<=",
                    actual_value=float(row.actual_value),
                    hard_limit=float(row.hard_limit),
                    margin=margin,
                    trust_region_rho=RHO,
                    iteration_index=int(iteration_index),
                    control_names=names,
                    anchor_controls=tuple(map(float, controls[slot])),
                    coefficients=tuple(map(float, coefficient)),
                    local_radius=tuple(map(float, radius)),
                ))
        finally:
            odd.Basic.ClearAll()
    return tuple(cuts), {
        "cut_count": len(cuts),
        "Fresh_finite_difference_solve_count": solve_count,
        "violated_slot_count": len(by_slot),
        "maximum_anchor_reproduction_error_pu": maximum_anchor_error,
        "anchor_acceptance_tolerance_pu": ANCHOR_REPEAT_TOLERANCE_PU,
        "frozen_tap_central_difference": True,
        "finite_difference_step": FINITE_DIFFERENCE_STEP,
        "derivatives": derivative_rows,
    }


def local_voltage_restoration_cuts(
    **kwargs: Any,
) -> tuple[tuple[RestorationCut, ...], dict[str, Any]]:
    """Compatibility wrapper for the voltage-only prototype API."""

    if "margin_pu" in kwargs:
        margin = float(kwargs.pop("margin_pu"))
        kwargs["margins"] = {
            "m_V_pu": margin,
            "m_I_pu": margin,
            "m_transformer_kva_pu": margin,
        }
    return local_fresh_ac_restoration_cuts(**kwargs)


def _discrete_signature(trajectory: MessTrajectory) -> str:
    return canonical_sha256({
        "rows": [
            {
                "mess_id": row.mess_id,
                "slot": int(row.slot),
                "mode": row.mode,
                "service_id": row.service_id,
                "origin_service_id": row.origin_service_id,
                "destination_service_id": row.destination_service_id,
                "route_link_ids": list(row.route_link_ids),
                "departure_slot": row.departure_slot,
                "connection_ready_slot": row.connection_ready_slot,
            }
            for row in trajectory.slots
        ]
    })


def solve_fixed_discrete_recourse(
    *,
    repo: Path,
    case: str,
    aidc: Any,
    electrical: Any,
    route_table: Any,
    service_to_pcc: Mapping[str, str],
    selected_trajectory: MessTrajectory,
    restoration_cuts: Sequence[RestorationCut],
) -> IntegratedMessResult:
    coefficients = joint_repaired_coefficients(repo, electrical)
    result = solve_integrated_mess(
        case=case,
        aidc_pcc_kw_96x12=np.asarray(aidc.pcc_p_kw, dtype=float),
        electrical_context=electrical.legacy_context,
        voltage_authority=electrical.voltage,
        current_authority=electrical.current,
        route_table=route_table,
        service_to_pcc=service_to_pcc,
        initial_service_by_mess=MESS_INITIAL,
        grid_coefficients=coefficients,
        restoration_cuts=tuple(restoration_cuts),
        fixed_discrete_trajectory=selected_trajectory,
    )
    if _discrete_signature(result.trajectory) != _discrete_signature(selected_trajectory):
        raise RuntimeError("V37_R3_DISCRETE_MESS_DECISION_MUTATED")
    return result


__all__ = [
    "K_MAX",
    "extract_ac_violations",
    "extract_voltage_violations",
    "frozen_trajectory",
    "load_fresh_result",
    "local_fresh_ac_restoration_cuts",
    "local_voltage_restoration_cuts",
    "restoration_cut_from_payload",
    "solve_fixed_discrete_recourse",
]

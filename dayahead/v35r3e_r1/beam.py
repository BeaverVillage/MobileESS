"""Deterministic state, seed, deduplication, and pruning contracts.

This module changes search only.  A retained seed is always passed to the
original unrestricted multi-relocation MILP; it never fixes a production
decision or changes physical feasibility.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from typing import Iterable, Mapping, Sequence

import numpy as np


DEFAULT_K = 200
BEAM_WIDTH = 2
BEAM_WIDTH_FALLBACK = 4
SEED_WIDTH = 2
OBJECTIVE_TOLERANCE = 1e-6
TRAJECTORY_TOLERANCE = 1e-6
EXACT_RESTRICTED_CANDIDATE_ID_REQUIRED_FOR_PASS = False


def canonical_sha256(value: object) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
        default=float,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def objective_epsilon(reference: float) -> float:
    """Predeclared numerical objective-equivalence tolerance."""

    value = float(reference)
    if not math.isfinite(value):
        raise ValueError("V35R3E_R1_REFERENCE_OBJECTIVE_NOT_FINITE")
    return OBJECTIVE_TOLERANCE * max(1.0, abs(value))


def _quantized(value: object, tolerance: float = TRAJECTORY_TOLERANCE) -> int:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("V35R3E_R1_TRAJECTORY_VALUE_NOT_FINITE")
    return int(round(number / tolerance))


def _normalized_slot(slot: Mapping[str, object]) -> dict[str, object]:
    """Normalize the physical trajectory fields at the committed tolerance."""

    return {
        "mess_id": str(slot["mess_id"]),
        "slot": int(slot["slot"]),
        "mode": str(slot["mode"]),
        "service_id": None if slot.get("service_id") is None else str(slot["service_id"]),
        "origin_service_id": (
            None if slot.get("origin_service_id") is None else str(slot["origin_service_id"])
        ),
        "destination_service_id": (
            None
            if slot.get("destination_service_id") is None
            else str(slot["destination_service_id"])
        ),
        "route_link_ids": list(map(str, slot.get("route_link_ids", ()))),
        "departure_slot": (
            None if slot.get("departure_slot") is None else int(slot["departure_slot"])
        ),
        "connection_ready_slot": (
            None
            if slot.get("connection_ready_slot") is None
            else int(slot["connection_ready_slot"])
        ),
        "p": _quantized(slot["p_kw"]),
        "q": _quantized(slot["q_kvar"]),
        "energy": _quantized(slot["battery_energy_kwh"]),
        "soc": _quantized(slot["soc_fraction"]),
    }


def trajectory_equivalence_sha(slots: Sequence[Mapping[str, object]]) -> str:
    return canonical_sha256([_normalized_slot(slot) for slot in slots])


def restricted_trajectory_signature(
    candidate: object,
    dispatch: Mapping[str, object],
) -> str:
    """Hash route/movement and full restricted P/Q/SoC, not candidate ID alone."""

    def get(name: str) -> object:
        return getattr(candidate, name) if hasattr(candidate, name) else candidate[name]

    payload = {
        "is_stay": bool(get("is_stay")),
        "origin": str(get("origin")),
        "destination": str(get("destination")),
        "departure_slot": None if get("departure_slot") is None else int(get("departure_slot")),
        "connection_ready_slot": (
            None if get("connection_ready_slot") is None else int(get("connection_ready_slot"))
        ),
        "route_link_ids": list(map(str, get("route_link_ids"))),
        "p": [_quantized(value) for value in np.asarray(dispatch["p_kw"], dtype=float)],
        "q": [_quantized(value) for value in np.asarray(dispatch["q_kvar"], dtype=float)],
        "energy": [
            _quantized(value) for value in np.asarray(dispatch["energy_kwh"], dtype=float)
        ],
    }
    return canonical_sha256(payload)


@dataclass(frozen=True)
class BeamState:
    case_id: str
    beam_state_id: str
    parent_state_id: str | None
    completed_vehicles: tuple[str, ...]
    vehicles: tuple[Mapping[str, object], ...]
    trajectory_slots: tuple[Mapping[str, object], ...]
    combined_fixed_p_by_service: tuple[Mapping[str, object], ...]
    combined_fixed_q_by_service: tuple[Mapping[str, object], ...]
    current_planning_objective: float
    solver_objective: float
    best_bound: float | None
    gap: float | None
    state_sha256: str
    trajectory_equivalence_sha256: str

    def to_dict(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "beam_state_id": self.beam_state_id,
            "parent_state_id": self.parent_state_id,
            "completed_vehicles": list(self.completed_vehicles),
            "vehicles": [dict(row) for row in self.vehicles],
            "trajectory_slots": [dict(row) for row in self.trajectory_slots],
            "combined_fixed_p_by_service": [
                dict(row) for row in self.combined_fixed_p_by_service
            ],
            "combined_fixed_q_by_service": [
                dict(row) for row in self.combined_fixed_q_by_service
            ],
            "current_planning_objective": self.current_planning_objective,
            "solver_objective": self.solver_objective,
            "best_bound": self.best_bound,
            "gap": self.gap,
            "state_sha256": self.state_sha256,
            "trajectory_equivalence_sha256": self.trajectory_equivalence_sha256,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "BeamState":
        return cls(
            case_id=str(payload["case_id"]),
            beam_state_id=str(payload["beam_state_id"]),
            parent_state_id=(
                None if payload.get("parent_state_id") is None else str(payload["parent_state_id"])
            ),
            completed_vehicles=tuple(map(str, payload["completed_vehicles"])),
            vehicles=tuple(dict(row) for row in payload["vehicles"]),
            trajectory_slots=tuple(dict(row) for row in payload["trajectory_slots"]),
            combined_fixed_p_by_service=tuple(
                dict(row) for row in payload["combined_fixed_p_by_service"]
            ),
            combined_fixed_q_by_service=tuple(
                dict(row) for row in payload["combined_fixed_q_by_service"]
            ),
            current_planning_objective=float(payload["current_planning_objective"]),
            solver_objective=float(payload["solver_objective"]),
            best_bound=(None if payload.get("best_bound") is None else float(payload["best_bound"])),
            gap=None if payload.get("gap") is None else float(payload["gap"]),
            state_sha256=str(payload["state_sha256"]),
            trajectory_equivalence_sha256=str(payload["trajectory_equivalence_sha256"]),
        )


def state_pruning_key(state: BeamState) -> tuple[float, int, float, int, float, str]:
    bound_finite = state.best_bound is not None and math.isfinite(float(state.best_bound))
    gap_finite = state.gap is not None and math.isfinite(float(state.gap))
    return (
        float(state.current_planning_objective),
        0 if bound_finite else 1,
        float(state.best_bound) if bound_finite else math.inf,
        0 if gap_finite else 1,
        float(state.gap) if gap_finite else math.inf,
        state.state_sha256,
    )


def deduplicate_children(
    children: Iterable[BeamState],
) -> tuple[list[BeamState], list[dict[str, object]]]:
    """Retain the best representative of each tolerance-equivalent fleet state."""

    retained: dict[str, BeamState] = {}
    audit: list[dict[str, object]] = []
    for child in children:
        key = child.trajectory_equivalence_sha256
        previous = retained.get(key)
        if previous is None:
            retained[key] = child
            continue
        winner, loser = min((previous, child), key=state_pruning_key), max(
            (previous, child), key=state_pruning_key
        )
        retained[key] = winner
        audit.append({
            "trajectory_equivalence_sha256": key,
            "retained_state_id": winner.beam_state_id,
            "removed_state_id": loser.beam_state_id,
            "selection_rule": "OBJECTIVE_BOUND_GAP_STATE_SHA",
        })
    return sorted(retained.values(), key=state_pruning_key), audit


def prune_beam(
    children: Sequence[BeamState], width: int,
) -> tuple[list[BeamState], list[BeamState]]:
    if not 1 <= int(width) <= BEAM_WIDTH_FALLBACK:
        raise ValueError("V35R3E_R1_BEAM_WIDTH_OUTSIDE_FROZEN_BOUND")
    ordered = sorted(children, key=state_pruning_key)
    return ordered[: int(width)], ordered[int(width) :]

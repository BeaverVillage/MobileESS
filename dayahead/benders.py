"""Certified bookkeeping shared by Standard BD and CL-MC-BD."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Iterable, Mapping, Sequence

from .grid_lp import FeasibilityCut, GridLPSolution, OptimalityCut


GAMMA_CRIT = 0.98
CERTIFICATION_TOLERANCE = 1e-3


class BendersMethod(str, Enum):
    STANDARD_SINGLE_CUT = "STANDARD_SINGLE_CUT_BD"
    CL_MC_BD = "CL_MC_BD"


@dataclass(frozen=True)
class RegisteredCut:
    cut_id: str
    cut_type: str
    time_index: int
    source_iteration: int
    coefficient_sha256: str
    payload: Mapping[str, object]


class CutRegistry:
    def __init__(self) -> None:
        self._by_hash: dict[str, RegisteredCut] = {}

    @staticmethod
    def _payload(cut: OptimalityCut | FeasibilityCut) -> dict[str, object]:
        return asdict(cut)

    def add(self, cut: OptimalityCut | FeasibilityCut) -> bool:
        payload = self._payload(cut)
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        digest = hashlib.sha256(encoded).hexdigest()
        if digest in self._by_hash:
            return False
        cut_type = "OPTIMALITY" if isinstance(cut, OptimalityCut) else "FEASIBILITY"
        registered = RegisteredCut(
            cut_id=f"CUT-{len(self._by_hash) + 1:06d}",
            cut_type=cut_type,
            time_index=cut.time_index,
            source_iteration=cut.source_iteration,
            coefficient_sha256=digest,
            payload=payload,
        )
        self._by_hash[digest] = registered
        return True

    @property
    def cuts(self) -> tuple[RegisteredCut, ...]:
        return tuple(self._by_hash.values())


def critical_times(solutions: Sequence[GridLPSolution], gamma: float = GAMMA_CRIT) -> tuple[int, ...]:
    loadings = [
        (solution.time_index, asset_phase, value)
        for solution in solutions
        for asset_phase, value in solution.loading.items()
    ]
    if not loadings:
        return ()
    z_tilde = max(value for _time, _asset, value in loadings)
    threshold = gamma * z_tilde
    return tuple(sorted({time_index for time_index, _asset, value in loadings if value >= threshold - 1e-12}))


def cuts_for_iteration(method: BendersMethod, solutions: Sequence[GridLPSolution]) -> tuple[OptimalityCut | FeasibilityCut, ...]:
    if len(solutions) != 96 or {solution.time_index for solution in solutions} != set(range(96)):
        raise ValueError("ALL_96_GRID_LPS_MUST_BE_EVALUATED_EVERY_ITERATION")
    selected: list[OptimalityCut | FeasibilityCut] = []
    selected.extend(solution.feasibility_cut for solution in solutions if not solution.feasible and solution.feasibility_cut)
    feasible = [solution for solution in solutions if solution.feasible]
    if not feasible:
        return tuple(selected)
    if method is BendersMethod.STANDARD_SINGLE_CUT:
        worst = max(feasible, key=lambda item: (float(item.objective), -item.time_index))
        if worst.optimality_cut:
            selected.append(worst.optimality_cut)
    else:
        times = set(critical_times(solutions))
        selected.extend(
            solution.optimality_cut
            for solution in feasible
            if solution.time_index in times and solution.optimality_cut
        )
    return tuple(selected)


@dataclass
class BoundState:
    lower_bound: float = -math.inf
    upper_bound: float = math.inf
    master_incumbent_objective: float | None = None
    gap: float = math.inf

    def update(self, *, master_obj_bound: float, master_incumbent_objective: float | None, solutions: Sequence[GridLPSolution]) -> None:
        self.lower_bound = max(self.lower_bound, float(master_obj_bound))
        self.master_incumbent_objective = master_incumbent_objective
        if len(solutions) != 96:
            raise ValueError("ALL_96_GRID_LPS_MUST_BE_EVALUATED_EVERY_ITERATION")
        if all(solution.feasible for solution in solutions):
            candidate = max(float(solution.objective) for solution in solutions)
            self.upper_bound = min(self.upper_bound, candidate)
        if math.isfinite(self.upper_bound) and math.isfinite(self.lower_bound):
            self.gap = max(0.0, (self.upper_bound - self.lower_bound) / max(abs(self.upper_bound), 1e-6))

    @property
    def certified(self) -> bool:
        return self.gap <= CERTIFICATION_TOLERANCE

    def termination_status(self, *, time_limit: bool = False) -> str:
        if self.certified:
            return "OPTIMAL_CERTIFIED"
        return "TIME_LIMIT_NOT_CERTIFIED" if time_limit else "NOT_CERTIFIED"


def evaluate_all_96(factories: Sequence[object], master: Mapping[str, float], iteration: int) -> tuple[GridLPSolution, ...]:
    if len(factories) != 96:
        raise ValueError("exactly 96 time-local Grid LP factories are required")
    return tuple(factory.solve(index, master, iteration) for index, factory in enumerate(factories))

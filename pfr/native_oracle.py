"""Finite-state positive-path oracle for offline native-control diagnosis.

The oracle may be supplied actual-future evaluators by a diagnostic tool, but
this module is never imported by the production runtime.  Failure to find a
path is not an infeasibility certificate.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Mapping, Optional, Sequence


@dataclass(frozen=True)
class OracleNativeState:
    capacitor_states: tuple[tuple[str, tuple[int, ...]], ...]
    capacitor_dwell_remaining: tuple[tuple[str, int], ...]
    regulator_taps: tuple[tuple[str, int], ...]

    @classmethod
    def create(
        cls,
        *,
        capacitor_states: Mapping[str, Sequence[int]],
        capacitor_dwell_remaining: Mapping[str, int],
        regulator_taps: Mapping[str, int],
    ) -> "OracleNativeState":
        names = {str(name).lower() for name in capacitor_states}
        if names != {str(name).lower() for name in capacitor_dwell_remaining}:
            raise ValueError("oracle dwell state must cover every capacitor")
        dwell = {
            str(name).lower(): int(value)
            for name, value in capacitor_dwell_remaining.items()
        }
        if any(value < 0 for value in dwell.values()):
            raise ValueError("oracle dwell counters cannot be negative")
        return cls(
            capacitor_states=tuple(
                sorted(
                    (str(name).lower(), tuple(int(value) for value in values))
                    for name, values in capacitor_states.items()
                )
            ),
            capacitor_dwell_remaining=tuple(sorted(dwell.items())),
            regulator_taps=tuple(
                sorted(
                    (str(name).lower(), int(value))
                    for name, value in regulator_taps.items()
                )
            ),
        )


@dataclass(frozen=True)
class OracleSearchResult:
    status: str
    path: tuple[OracleNativeState, ...]
    expanded_states: int
    negative_result_is_infeasibility_certificate: bool = False


Successors = Callable[[int, OracleNativeState], Iterable[OracleNativeState]]
Safe = Callable[[int, OracleNativeState], bool]


def find_positive_trajectory(
    *,
    initial: OracleNativeState,
    steps: int,
    successors: Successors,
    safe: Safe,
    maximum_frontier_states: int,
) -> OracleSearchResult:
    """Find one safe path deterministically; a miss is explicitly non-certain."""

    if steps <= 0 or maximum_frontier_states <= 0:
        raise ValueError("oracle bounds must be positive")
    if not safe(0, initial):
        return OracleSearchResult("INITIAL_STATE_UNSAFE", (), 0)
    frontier: dict[OracleNativeState, tuple[OracleNativeState, ...]] = {
        initial: (initial,)
    }
    expanded = 0
    for step in range(1, steps + 1):
        next_frontier: dict[OracleNativeState, tuple[OracleNativeState, ...]] = {}
        for state, path in sorted(
            frontier.items(), key=lambda item: repr(item[0])
        ):
            for candidate in sorted(set(successors(step, state)), key=repr):
                expanded += 1
                if not safe(step, candidate):
                    continue
                next_frontier.setdefault(candidate, path + (candidate,))
        if not next_frontier:
            return OracleSearchResult("NO_PATH_FOUND_WITHIN_BOUND", (), expanded)
        frontier = dict(
            list(
                sorted(next_frontier.items(), key=lambda item: repr(item[0]))
            )[:maximum_frontier_states]
        )
    path = min(frontier.values(), key=lambda value: repr(value[-1]))
    return OracleSearchResult("POSITIVE_SAFE_TRAJECTORY_FOUND", path, expanded)

"""Deterministic 5/15-minute multiresolution route-planning horizon."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class PlanningStage:
    index: int
    start_minute: int
    duration_minutes: int
    covered_five_minute_steps: Tuple[int, ...]


def build_multires_horizon(
    *,
    total_minutes: int = 270,
    fine_minutes: int = 60,
    fine_step_minutes: int = 5,
    coarse_step_minutes: int = 15,
) -> Tuple[PlanningStage, ...]:
    if not (0 < fine_minutes <= total_minutes):
        raise ValueError("fine horizon must be positive and no longer than total horizon")
    if fine_step_minutes <= 0 or coarse_step_minutes <= 0:
        raise ValueError("stage durations must be positive")
    if fine_minutes % fine_step_minutes or (total_minutes - fine_minutes) % coarse_step_minutes:
        raise ValueError("horizon sections must divide exactly into their stage durations")
    if coarse_step_minutes % fine_step_minutes:
        raise ValueError("coarse stages must cover whole fine-grid steps")

    stages = []
    start = 0
    index = 0
    while start < total_minutes:
        duration = fine_step_minutes if start < fine_minutes else coarse_step_minutes
        first_fine = start // fine_step_minutes
        covered = tuple(range(first_fine, first_fine + duration // fine_step_minutes))
        stages.append(PlanningStage(index, start, duration, covered))
        start += duration
        index += 1
    return tuple(stages)

"""Frozen-schedule cohort compute replay; no reassignment or reoptimization."""

from __future__ import annotations

from typing import Mapping, Sequence


def replay_compute(
    reserved: Mapping[tuple[str, str, int], float],
    actual_arrivals: Mapping[str, Sequence[float]],
    rack_headroom_nodeh: Mapping[tuple[str, int], float],
) -> dict[str, object]:
    cohorts=tuple(sorted(actual_arrivals)); racks=tuple(sorted({key[1] for key in reserved}))
    if any(len(actual_arrivals[cohort]) != 96 for cohort in cohorts): raise ValueError("REALIZED_COMPUTE_REPLAY_REQUIRES_96_ARRIVALS")
    backlog={cohort:0.0 for cohort in cohorts}; executed={}; backlog_trace={cohort:[0.0] for cohort in cohorts}
    for slot in range(96):
        for cohort in cohorts: backlog[cohort] += float(actual_arrivals[cohort][slot])
        remaining={rack:float(rack_headroom_nodeh[rack,slot]) for rack in racks}
        for cohort in cohorts:
            for rack in racks:
                planned=float(reserved.get((cohort,rack,slot),0.0)); amount=min(planned,backlog[cohort],remaining[rack])
                executed[cohort,rack,slot]=amount; backlog[cohort]-=amount; remaining[rack]-=amount
        for cohort in cohorts: backlog_trace[cohort].append(backlog[cohort])
    return {"executed":executed,"backlog":{key:tuple(value) for key,value in backlog_trace.items()},"solver_call_count":0,"reassignment_count":0,"execution_rule":"x_exec<=x_DA at identical cohort/rack/time only"}

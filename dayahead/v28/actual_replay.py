"""Fixed-schedule realized-operation replay with no optimization entry point."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np

from .inputs import InputNamespaceGate


SLOTS = 96


@dataclass(frozen=True)
class WorkloadExecution:
    executed: np.ndarray
    backlog: np.ndarray


@dataclass(frozen=True)
class MessExecution:
    p_exec_kw: np.ndarray
    q_exec_kvar: np.ndarray
    missed: tuple[dict[str, object], ...]


def actual_it_residual(
    natural_it_kw: Iterable[float], natural_flexible_it_kw: Iterable[float], *, tolerance_kw: float = 1e-9
) -> np.ndarray:
    natural = np.asarray(tuple(natural_it_kw), dtype=float)
    flexible = np.asarray(tuple(natural_flexible_it_kw), dtype=float)
    if natural.shape != (SLOTS,) or flexible.shape != (SLOTS,):
        raise ValueError("V28_ACTUAL_IT_AXIS_MISMATCH")
    residual = natural - flexible
    if np.min(residual, initial=0.0) < -tolerance_kw:
        raise RuntimeError("FAIL_AIDC_ACTUAL_DECOMPOSITION")
    # Values within numerical tolerance are preserved; there is no clipping.
    return residual


def execute_workload(dayahead: Iterable[float], available: Iterable[float]) -> WorkloadExecution:
    scheduled = np.asarray(tuple(dayahead), dtype=float)
    realized = np.asarray(tuple(available), dtype=float)
    if scheduled.shape != (SLOTS,) or realized.shape != (SLOTS,):
        raise ValueError("V28_WORKLOAD_EXECUTION_AXIS_MISMATCH")
    if np.any(scheduled < 0) or np.any(realized < 0):
        raise ValueError("V28_WORKLOAD_EXECUTION_NEGATIVE_INPUT")
    executed = np.minimum(scheduled, realized)
    backlog = np.cumsum(realized - executed)
    if np.any(executed > scheduled + 1e-12):
        raise RuntimeError("V28_X_EXEC_EXCEEDS_X_DA")
    return WorkloadExecution(executed, backlog)


def execute_mess(
    p_dayahead_kw: Iterable[float],
    q_dayahead_kvar: Iterable[float],
    physically_available: Iterable[bool],
    soc_feasible: Iterable[bool],
) -> MessExecution:
    p_da = np.asarray(tuple(p_dayahead_kw), dtype=float)
    q_da = np.asarray(tuple(q_dayahead_kvar), dtype=float)
    available = np.asarray(tuple(physically_available), dtype=bool)
    feasible = np.asarray(tuple(soc_feasible), dtype=bool)
    if any(value.shape != (SLOTS,) for value in (p_da, q_da, available, feasible)):
        raise ValueError("V28_MESS_EXECUTION_AXIS_MISMATCH")
    allowed = available & feasible
    p_exec = np.where(allowed, p_da, 0.0)
    q_exec = np.where(allowed, q_da, 0.0)
    missed = []
    for slot in np.flatnonzero(~allowed & ((np.abs(p_da) > 1e-12) | (np.abs(q_da) > 1e-12))):
        reason = "NOT_PHYSICALLY_AVAILABLE" if not available[slot] else "TRAVEL_ENERGY_OR_SOC_INFEASIBLE"
        missed.append({"slot": int(slot), "reason": reason, "executed_later": False, "substitute_vehicle": False})
    return MessExecution(p_exec, q_exec, tuple(missed))


def replay_counters() -> dict[str, int]:
    return {
        "actual_reoptimization_calls": 0,
        "event_trigger_calls": 0,
        "local_repair_calls": 0,
        "rolling_mpc_calls": 0,
        "rolling_update_calls": 0,
        "hidden_shedding_GPU_h": 0,
        "GPU_h_facility_scale_multiplications": 0,
        "beta_AIDC_calls": 0,
        "PUE_application_count_per_trajectory": 1,
    }


def authorize_replay(gate: InputNamespaceGate, schedule_sha256: str) -> dict[str, int]:
    gate.open_actual(schedule_sha256)
    gate.assert_actual_access_allowed()
    return replay_counters()

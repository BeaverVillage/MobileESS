"""Cohort-level H100-node-hour backlog and terminal service parity."""

from __future__ import annotations

from typing import Sequence

DT_HOURS = 0.25
AUTHORITY_ID = "REFERENCE_MATCHED_SERVICE_CONSERVATION_V1"


def backlog_trajectory(arrivals_nodeh: Sequence[float], processed_nodeh: Sequence[float]) -> tuple[float, ...]:
    if len(arrivals_nodeh) != 96 or len(processed_nodeh) != 96:
        raise ValueError("SERVICE_CONTRACT_REQUIRES_96_SLOTS")
    backlog = [0.0]
    cumulative_arrival = 0.0
    cumulative_processed = 0.0
    for arrival, processed in zip(arrivals_nodeh, processed_nodeh):
        arrival = float(arrival)
        processed = float(processed)
        if arrival < 0 or processed < 0:
            raise ValueError("NEGATIVE_WORK_MASS_PROHIBITED")
        cumulative_arrival += arrival
        cumulative_processed += processed
        if cumulative_processed > cumulative_arrival + 1e-9:
            raise ValueError("WORK_PROCESSED_BEFORE_ARRIVAL")
        backlog.append(backlog[-1] + arrival - processed)
    return tuple(backlog)


def require_terminal_reference_parity(
    arrivals_nodeh: Sequence[float], da_processed_nodeh: Sequence[float], ref_processed_nodeh: Sequence[float]
) -> tuple[tuple[float, ...], tuple[float, ...]]:
    da = backlog_trajectory(arrivals_nodeh, da_processed_nodeh)
    ref = backlog_trajectory(arrivals_nodeh, ref_processed_nodeh)
    if abs(da[-1] - ref[-1]) > 1e-9:
        raise ValueError("REFERENCE_MATCHED_TERMINAL_SERVICE_PARITY_VIOLATION")
    return da, ref


def active_nodes(processed_nodeh: float) -> float:
    return float(processed_nodeh) / DT_HOURS


def active_gpus(processed_nodeh: float) -> float:
    return 4.0 * active_nodes(processed_nodeh)


def flexible_power_kw(processed_nodeh: float, kappa_kw_per_node: float) -> float:
    return float(kappa_kw_per_node) * active_nodes(processed_nodeh)

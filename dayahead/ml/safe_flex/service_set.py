"""Deterministic intertemporally coupled SAFE-Flex service-set projector."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


SLOTS = 96
TIERS = 6
LATENCIES = 5
DEADLINE_SLOTS = np.asarray([2, 4, 8, 12, 24], dtype=int)


@dataclass
class Projection:
    """One deterministic scheduler-feasibility projection in GPU-hour units."""

    status: str
    reason: str | None
    lower_cumulative_GPU_h: np.ndarray
    upper_cumulative_GPU_h: np.ndarray
    reference_service_GPU_h: np.ndarray
    terminal_backlog_GPU_h: np.ndarray
    hidden_shedding_GPU_h: float
    mass_identity_error_GPU_h: float


def cumulative_bounds(arrivals_GPU_h: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return deadline-required lower and release-limited upper cumulative bounds."""

    arrivals = np.asarray(arrivals_GPU_h, dtype=float)
    if arrivals.shape != (SLOTS, TIERS, LATENCIES):
        raise ValueError(f"V26M_SERVICE_TENSOR_SHAPE:{arrivals.shape}")
    if np.any(arrivals < -1e-12):
        raise ValueError("V26M_NEGATIVE_WORKLOAD")
    upper = np.cumsum(arrivals, axis=0)
    lower = np.zeros_like(upper)
    for latency, delay in enumerate(DEADLINE_SLOTS):
        if delay < SLOTS:
            lower[delay:, :, latency] = upper[:-delay, :, latency]
    return lower, upper


def project_service_set(arrivals_GPU_h: np.ndarray, capacity_GPU_h_per_slot: float) -> Projection:
    """Construct EDF feasible service or an explicit infeasibility reason.

    Release, deadline, nonnegativity and slot-capacity constraints are exact.
    Work with deadlines beyond the horizon is explicit terminal backlog. No
    clipping or hidden shedding is permitted.
    """

    arrivals = np.asarray(arrivals_GPU_h, dtype=float)
    lower, upper = cumulative_bounds(arrivals)
    if not np.isfinite(arrivals).all() or capacity_GPU_h_per_slot <= 0:
        return Projection("SOURCE_INFEASIBLE", "nonfinite arrival or nonpositive capacity", lower, upper, np.zeros_like(arrivals), arrivals.sum(axis=0), 0.0, 0.0)
    queues: list[list[list[list[float]]]] = [[[] for _ in range(LATENCIES)] for _ in range(TIERS)]
    service = np.zeros_like(arrivals)
    for slot in range(SLOTS):
        for tier in range(TIERS):
            for latency in range(LATENCIES):
                mass = float(arrivals[slot, tier, latency])
                if mass > 0:
                    queues[tier][latency].append([float(slot + DEADLINE_SLOTS[latency]), mass])
        candidates = []
        for tier in range(TIERS):
            for latency in range(LATENCIES):
                for entry in queues[tier][latency]:
                    if entry[1] > 1e-12:
                        candidates.append((entry[0], tier, latency, entry))
        candidates.sort(key=lambda item: item[0])
        available = float(capacity_GPU_h_per_slot)
        for _, tier, latency, entry in candidates:
            amount = min(available, entry[1])
            entry[1] -= amount
            service[slot, tier, latency] += amount
            available -= amount
            if available <= 1e-12:
                break
        overdue = sum(entry[1] for deadline, _, _, entry in candidates if deadline <= slot and entry[1] > 1e-9)
        if overdue > 1e-9:
            backlog = np.zeros((TIERS, LATENCIES), dtype=float)
            for tier in range(TIERS):
                for latency in range(LATENCIES):
                    backlog[tier, latency] = sum(entry[1] for entry in queues[tier][latency])
            error = float(abs(arrivals.sum() - service.sum() - backlog.sum()))
            return Projection("DEADLINE_INFEASIBLE", f"overdue_GPU_h={overdue:.12g} at slot={slot}", lower, upper, service, backlog, 0.0, error)
    backlog = np.zeros((TIERS, LATENCIES), dtype=float)
    for tier in range(TIERS):
        for latency in range(LATENCIES):
            backlog[tier, latency] = sum(entry[1] for entry in queues[tier][latency])
    error = float(abs(arrivals.sum() - service.sum() - backlog.sum()))
    return Projection("FEASIBLE", None, lower, upper, service, backlog, 0.0, error)


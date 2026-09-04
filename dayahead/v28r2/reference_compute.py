"""Full-node adapter and deterministic REFERENCE_COMPUTE_SCHEDULE_V2.

The scheduler is deliberately blind to grid, MESS, weather, and actual data.
Its complete input is the D-1 forecast-cohort arrival tensor plus frozen rack
capacity/axis authorities.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Mapping, Sequence

import numpy as np

from dayahead.aidc_power_response import KAPPA_KW_PER_ACTIVE_H100_NODE
from dayahead.v28r2.authority import COHORT_IDS


DT_HOURS = 0.25
CASE_CAPACITY_GPU = 528.0


@dataclass(frozen=True)
class FullNodeDistributionAdapter:
    probabilities: np.ndarray
    cohort_ids: tuple[str, ...] = COHORT_IDS

    def validate(self) -> None:
        values = np.asarray(self.probabilities, dtype=float)
        if values.shape != (7, 96, len(self.cohort_ids)) or not np.isfinite(values).all():
            raise ValueError("V28R2_FULLNODE_ADAPTER_SHAPE_OR_FINITE")
        if np.any(values < 0):
            raise ValueError("V28R2_FULLNODE_ADAPTER_NEGATIVE")
        if not np.allclose(values.sum(axis=(1, 2)), 1.0, rtol=0, atol=1e-12):
            raise ValueError("V28R2_FULLNODE_ADAPTER_DOW_MASS")

    def materialize(self, daily_q50_nodeh: float, day_of_week: int) -> np.ndarray:
        self.validate()
        if daily_q50_nodeh < 0 or not 0 <= day_of_week < 7:
            raise ValueError("V28R2_FULLNODE_ADAPTER_INPUT")
        result = float(daily_q50_nodeh) * self.probabilities[day_of_week]
        tolerance = 1e-9 * max(1.0, float(daily_q50_nodeh))
        if abs(float(result.sum()) - float(daily_q50_nodeh)) > tolerance:
            raise RuntimeError("V28R2_W_MASS_IDENTITY")
        return result


@dataclass(frozen=True)
class ReferenceSchedule:
    cohort_ids: tuple[str, ...]
    rack_ids: tuple[str, ...]
    arrivals_nodeh: np.ndarray
    x_ref_nodeh: np.ndarray
    backlog_nodeh: np.ndarray
    p_f_ref_kw: np.ndarray
    g_f_ref_gpu: np.ndarray

    def validate(self) -> None:
        b, r, t = len(self.cohort_ids), len(self.rack_ids), 96
        if self.arrivals_nodeh.shape != (t, b):
            raise ValueError("V28R2_REFERENCE_ARRIVAL_SHAPE")
        if self.x_ref_nodeh.shape != (b, r, t) or self.backlog_nodeh.shape != (t + 1, b):
            raise ValueError("V28R2_REFERENCE_SCHEDULE_SHAPE")
        if self.p_f_ref_kw.shape != (r, t) or self.g_f_ref_gpu.shape != (r, t):
            raise ValueError("V28R2_REFERENCE_FIXED_CHANNEL_SHAPE")
        arrays = (self.arrivals_nodeh, self.x_ref_nodeh, self.backlog_nodeh, self.p_f_ref_kw, self.g_f_ref_gpu)
        if any(not np.isfinite(value).all() or np.any(value < -1e-12) for value in arrays):
            raise ValueError("V28R2_REFERENCE_NONNEGATIVE_FINITE")
        served = self.x_ref_nodeh.sum(axis=1).T
        expected = self.backlog_nodeh[:-1] + self.arrivals_nodeh - served
        if not np.allclose(self.backlog_nodeh[1:], expected, rtol=0, atol=1e-10):
            raise ValueError("V28R2_REFERENCE_BACKLOG_RECURSION")
        if np.any(self.backlog_nodeh[0] != 0):
            raise ValueError("V28R2_REFERENCE_INITIAL_BACKLOG_NOT_ZERO")

    def canonical_bytes(self) -> bytes:
        self.validate()
        payload = {
            "authority_id": "REFERENCE_COMPUTE_SCHEDULE_V2",
            "cohort_ids": list(self.cohort_ids),
            "rack_ids": list(self.rack_ids),
            "arrivals_nodeh": self.arrivals_nodeh.tolist(),
            "x_ref_nodeh": self.x_ref_nodeh.tolist(),
            "backlog_nodeh": self.backlog_nodeh.tolist(),
            "p_f_ref_kw": self.p_f_ref_kw.tolist(),
            "g_f_ref_gpu": self.g_f_ref_gpu.tolist(),
        }
        return (json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def cohort_node_class(cohort_id: str) -> int:
    if cohort_id not in COHORT_IDS:
        raise ValueError(f"V28R2_UNKNOWN_COHORT:{cohort_id}")
    return int(cohort_id[1:3])


def case_rack_capacity_nodeh_per_slot(
    rack_ids: Sequence[str], gpu_weights: Mapping[str, float]
) -> np.ndarray:
    if set(rack_ids) != set(gpu_weights):
        raise ValueError("V28R2_RACK_WEIGHT_AXIS_MISMATCH")
    weights = np.asarray([gpu_weights[rack] for rack in rack_ids], dtype=float)
    if np.any(weights <= 0) or not np.isclose(weights.sum(), 1.0, rtol=0, atol=1e-12):
        raise ValueError("V28R2_RACK_GPU_WEIGHT_INVALID")
    # GPU capacity / 4 GPUs per node * 0.25 h per slot.
    return CASE_CAPACITY_GPU * weights / 4.0 * DT_HOURS


def build_reference_schedule(
    arrivals_nodeh: np.ndarray,
    *,
    cohort_ids: Sequence[str],
    rack_ids: Sequence[str],
    rack_capacity_nodeh_per_slot: Sequence[float],
    rack_power_envelope_kw: np.ndarray | None = None,
    rack_gpu_envelope_gpu: np.ndarray | None = None,
) -> ReferenceSchedule:
    cohorts = tuple(cohort_ids)
    racks = tuple(rack_ids)
    arrivals = np.asarray(arrivals_nodeh, dtype=float)
    capacities = np.asarray(rack_capacity_nodeh_per_slot, dtype=float)
    if cohorts != tuple(sorted(cohorts)) or len(set(cohorts)) != len(cohorts):
        raise ValueError("V28R2_COHORT_TIEBREAK_AXIS")
    if racks != tuple(sorted(racks)) or len(set(racks)) != len(racks):
        raise ValueError("V28R2_RACK_TIEBREAK_AXIS")
    if arrivals.shape != (96, len(cohorts)) or np.any(arrivals < 0):
        raise ValueError("V28R2_REFERENCE_REQUIRES_96_NONNEGATIVE_COHORT_ARRIVALS")
    if capacities.shape != (len(racks),) or np.any(capacities <= 0):
        raise ValueError("V28R2_REFERENCE_RACK_CAPACITY")
    p_envelope = np.full((len(racks), 96), np.inf) if rack_power_envelope_kw is None else np.asarray(rack_power_envelope_kw, dtype=float)
    g_envelope = np.full((len(racks), 96), np.inf) if rack_gpu_envelope_gpu is None else np.asarray(rack_gpu_envelope_gpu, dtype=float)
    if p_envelope.shape != (len(racks), 96) or g_envelope.shape != (len(racks), 96):
        raise ValueError("V28R2_REFERENCE_ENVELOPE_SHAPE")
    if np.any(p_envelope < 0) or np.any(g_envelope < 0) or np.any(np.isnan(p_envelope)) or np.any(np.isnan(g_envelope)):
        raise ValueError("V28R2_REFERENCE_ENVELOPE_INVALID")

    allocation = np.zeros((len(cohorts), len(racks), 96), dtype=float)
    backlog = np.zeros((97, len(cohorts)), dtype=float)
    for slot in range(96):
        backlog[slot + 1] = backlog[slot] + arrivals[slot]
        remaining = capacities.copy()
        remaining_p = p_envelope[:, slot].copy()
        remaining_g = g_envelope[:, slot].copy()
        for cohort_index in range(len(cohorts)):
            nodes = cohort_node_class(cohorts[cohort_index])
            kappa = KAPPA_KW_PER_ACTIVE_H100_NODE[nodes]
            feasible = np.minimum(remaining, remaining_g * DT_HOURS / 4.0)
            feasible = np.minimum(feasible, remaining_p * DT_HOURS / kappa)
            total_remaining = float(feasible.sum())
            total_served = min(float(backlog[slot + 1, cohort_index]), total_remaining)
            if total_served <= 0 or total_remaining <= 0:
                continue
            # The frozen rack authority is explicitly a capacity-proportional
            # utilization invariant.  Cohorts retain lexical priority while
            # fluid service is spread in proportion to remaining rack capacity.
            served = total_served * feasible / total_remaining
            # Close floating arithmetic in deterministic AIDC/rack order only.
            arithmetic_residual = total_served - float(served.sum())
            if arithmetic_residual:
                served[0] += arithmetic_residual
            allocation[cohort_index, :, slot] = served
            backlog[slot + 1, cohort_index] -= total_served
            remaining -= served
            remaining_g -= served / DT_HOURS * 4.0
            remaining_p -= served / DT_HOURS * kappa
            remaining[np.abs(remaining) <= 1e-14] = 0.0
            remaining_g[np.abs(remaining_g) <= 1e-12] = 0.0
            remaining_p[np.abs(remaining_p) <= 1e-12] = 0.0
            if backlog[slot + 1, cohort_index] <= 1e-12:
                backlog[slot + 1, cohort_index] = 0.0

    p_f_ref = np.zeros((len(racks), 96), dtype=float)
    for cohort_index, cohort in enumerate(cohorts):
        nodes = cohort_node_class(cohort)
        p_f_ref += allocation[cohort_index] / DT_HOURS * KAPPA_KW_PER_ACTIVE_H100_NODE[nodes]
    g_f_ref = allocation.sum(axis=0) / DT_HOURS * 4.0
    result = ReferenceSchedule(cohorts, racks, arrivals, allocation, backlog, p_f_ref, g_f_ref)
    result.validate()
    return result

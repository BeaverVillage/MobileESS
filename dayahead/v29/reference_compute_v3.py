"""Deterministic earliest-feasible V29 reference with causal carry-in."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Mapping, Sequence

import numpy as np

from dayahead.aidc_power_response import KAPPA_KW_PER_ACTIVE_H100_NODE
from dayahead.v28r2.reference_compute import DT_HOURS, cohort_node_class


@dataclass(frozen=True)
class ReferenceScheduleV3:
    cohort_ids: tuple[str, ...]
    rack_ids: tuple[str, ...]
    initial_backlog_nodeh: np.ndarray
    arrivals_nodeh: np.ndarray
    x_ref_nodeh: np.ndarray
    backlog_nodeh: np.ndarray
    p_f_ref_kw: np.ndarray
    g_f_ref_gpu: np.ndarray

    def validate(self) -> None:
        cohorts, racks = len(self.cohort_ids), len(self.rack_ids)
        if self.initial_backlog_nodeh.shape != (cohorts,) or self.arrivals_nodeh.shape != (96, cohorts):
            raise ValueError("V29_REFERENCE_INITIAL_OR_ARRIVAL_AXIS")
        if self.x_ref_nodeh.shape != (cohorts, racks, 96) or self.backlog_nodeh.shape != (97, cohorts):
            raise ValueError("V29_REFERENCE_SCHEDULE_AXIS")
        if not np.allclose(self.backlog_nodeh[0], self.initial_backlog_nodeh, rtol=0, atol=1e-12):
            raise ValueError("V29_REFERENCE_INITIAL_BACKLOG_IDENTITY")
        served = self.x_ref_nodeh.sum(axis=1).T
        if not np.allclose(self.backlog_nodeh[1:], self.backlog_nodeh[:-1] + self.arrivals_nodeh - served, rtol=0, atol=1e-9):
            raise ValueError("V29_REFERENCE_MASS_CONSERVATION")
        if any(np.any(array < -1e-10) or not np.isfinite(array).all() for array in (
            self.initial_backlog_nodeh, self.arrivals_nodeh, self.x_ref_nodeh,
            self.backlog_nodeh, self.p_f_ref_kw, self.g_f_ref_gpu,
        )):
            raise ValueError("V29_REFERENCE_NONNEGATIVE_FINITE")

    def canonical_bytes(self) -> bytes:
        self.validate()
        payload = {
            "authority_id": "REFERENCE_COMPUTE_SCHEDULE_V3",
            "cohort_ids": list(self.cohort_ids), "rack_ids": list(self.rack_ids),
            "initial_backlog_nodeh": self.initial_backlog_nodeh.tolist(),
            "arrivals_nodeh": self.arrivals_nodeh.tolist(),
            "x_ref_nodeh": self.x_ref_nodeh.tolist(),
            "backlog_nodeh": self.backlog_nodeh.tolist(),
            "p_f_ref_kw": self.p_f_ref_kw.tolist(), "g_f_ref_gpu": self.g_f_ref_gpu.tolist(),
        }
        return (json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def build_reference_schedule_v3(
    arrivals_nodeh: np.ndarray, initial_backlog_nodeh: np.ndarray, *,
    cohort_ids: Sequence[str], rack_ids: Sequence[str],
    rack_capacity_nodeh_per_slot: Sequence[float],
    rack_power_envelope_kw: np.ndarray, rack_gpu_envelope_gpu: np.ndarray,
) -> ReferenceScheduleV3:
    cohorts, racks = tuple(cohort_ids), tuple(rack_ids)
    arrivals = np.asarray(arrivals_nodeh, dtype=float)
    initial = np.asarray(initial_backlog_nodeh, dtype=float)
    capacities = np.asarray(rack_capacity_nodeh_per_slot, dtype=float)
    p_envelope = np.asarray(rack_power_envelope_kw, dtype=float)
    g_envelope = np.asarray(rack_gpu_envelope_gpu, dtype=float)
    if cohorts != tuple(sorted(cohorts)) or racks != tuple(sorted(racks)):
        raise ValueError("V29_REFERENCE_TIEBREAK_AXIS")
    if arrivals.shape != (96, len(cohorts)) or initial.shape != (len(cohorts),):
        raise ValueError("V29_REFERENCE_INPUT_AXIS")
    allocation = np.zeros((len(cohorts), len(racks), 96), dtype=float)
    backlog = np.zeros((97, len(cohorts)), dtype=float); backlog[0] = initial
    for slot in range(96):
        backlog[slot + 1] = backlog[slot] + arrivals[slot]
        remaining = capacities.copy(); remaining_p = p_envelope[:, slot].copy(); remaining_g = g_envelope[:, slot].copy()
        for c, name in enumerate(cohorts):
            kappa = KAPPA_KW_PER_ACTIVE_H100_NODE[cohort_node_class(name)]
            feasible = np.minimum(remaining, remaining_g * DT_HOURS / 4.0)
            feasible = np.minimum(feasible, remaining_p * DT_HOURS / kappa)
            possible = float(feasible.sum()); served_total = min(float(backlog[slot + 1, c]), possible)
            if served_total <= 0 or possible <= 0:
                continue
            served = served_total * feasible / possible
            served[0] += served_total - float(served.sum())
            allocation[c, :, slot] = served; backlog[slot + 1, c] -= served_total
            remaining -= served; remaining_g -= served / DT_HOURS * 4.0; remaining_p -= served / DT_HOURS * kappa
            remaining[np.abs(remaining) < 1e-13] = 0; remaining_g[np.abs(remaining_g) < 1e-11] = 0; remaining_p[np.abs(remaining_p) < 1e-11] = 0
            if backlog[slot + 1, c] < 1e-11:
                backlog[slot + 1, c] = 0
    p_f = np.zeros((len(racks), 96))
    for c, name in enumerate(cohorts):
        p_f += allocation[c] / DT_HOURS * KAPPA_KW_PER_ACTIVE_H100_NODE[cohort_node_class(name)]
    g_f = allocation.sum(axis=0) / DT_HOURS * 4.0
    result = ReferenceScheduleV3(cohorts, racks, initial, arrivals, allocation, backlog, p_f, g_f)
    result.validate(); return result

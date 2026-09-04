"""Map-first Q90 reference decomposition for V28R2 planning."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

import numpy as np


LABEL = "Q90_BASED_REFERENCE_DECOMPOSITION_PLANNING_RESIDUAL"


@dataclass(frozen=True)
class ReferenceDelta:
    rack_ids: tuple[str, ...]
    p_res_plan_kw: np.ndarray
    g_res_plan_gpu: np.ndarray
    minimum_raw_p_kw: float
    minimum_raw_g_gpu: float
    p_tolerance_cells: int
    g_tolerance_cells: int

    @property
    def ready(self) -> bool:
        return bool(np.all(self.p_res_plan_kw >= 0) and np.all(self.g_res_plan_gpu >= 0))


def _weights(rack_ids: Sequence[str], values: Mapping[str, float], name: str) -> np.ndarray:
    if set(rack_ids) != set(values):
        raise ValueError(f"V28R2_{name}_WEIGHT_AXIS")
    result = np.asarray([values[rack] for rack in rack_ids], dtype=float)
    if np.any(result < 0) or not np.isclose(result.sum(), 1.0, rtol=0, atol=1e-12):
        raise ValueError(f"V28R2_{name}_WEIGHT_MASS")
    return result


def _canonicalize_tolerance_only(values: np.ndarray, tolerance: float) -> tuple[np.ndarray, int]:
    negative = values < 0
    substantive = values < -tolerance
    if np.any(substantive):
        locations = np.argwhere(substantive)
        first = tuple(int(value) for value in locations[0])
        raise ValueError(f"FAIL_REFERENCE_DELTA_DECOMPOSITION:{first}:{float(values[first])}")
    result = values.copy()
    result[negative] = 0.0
    return result, int(negative.sum())


def build_reference_delta(
    p_it_ref_q90_kw: np.ndarray,
    g_ref_q90_gpu: np.ndarray,
    p_f_ref_kw: np.ndarray,
    g_f_ref_gpu: np.ndarray,
    *,
    rack_ids: Sequence[str],
    power_weights: Mapping[str, float],
    gpu_weights: Mapping[str, float],
    numeric_tolerance: float = 1e-9,
) -> ReferenceDelta:
    racks = tuple(rack_ids)
    p = np.asarray(p_it_ref_q90_kw, dtype=float)
    g = np.asarray(g_ref_q90_gpu, dtype=float)
    p_fixed = np.asarray(p_f_ref_kw, dtype=float)
    g_fixed = np.asarray(g_f_ref_gpu, dtype=float)
    if p.shape != (96,) or g.shape != (96,) or p_fixed.shape != (len(racks), 96) or g_fixed.shape != (len(racks), 96):
        raise ValueError("V28R2_REFERENCE_DELTA_SHAPE")
    if any(np.any(value < 0) or not np.isfinite(value).all() for value in (p, g, p_fixed, g_fixed)):
        raise ValueError("V28R2_REFERENCE_DELTA_INPUT_FINITE_NONNEGATIVE")
    mapped_p = _weights(racks, power_weights, "POWER")[:, None] * p[None, :]
    mapped_g = _weights(racks, gpu_weights, "GPU")[:, None] * g[None, :]
    raw_p = mapped_p - p_fixed
    raw_g = mapped_g - g_fixed
    minimum_p, minimum_g = float(raw_p.min()), float(raw_g.min())
    p_res, p_cells = _canonicalize_tolerance_only(raw_p, numeric_tolerance)
    g_res, g_cells = _canonicalize_tolerance_only(raw_g, numeric_tolerance)
    return ReferenceDelta(racks, p_res, g_res, minimum_p, minimum_g, p_cells, g_cells)

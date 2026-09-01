"""V28 production binding for the accepted V24T C1 thermal mapping only."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np


REPO = Path(__file__).resolve().parents[2]
V24 = REPO / "dayahead/artifacts/v24t_thermal_aware_aidc"
C1_PATH = V24 / "V24T_C1_QUASISTATIC_MODEL.json"
NLR_MEDIAN_IT_KW = 1202.84
FROZEN_AGGREGATE_IT_PEAK_MW = 0.40677599381381907
GFS_NORMALIZATION_FACTOR = 5.987971384940258
NOAA_NORMALIZATION_FACTOR = 6.022241149610517


@dataclass(frozen=True)
class C1Trajectory:
    pcc_kw: np.ndarray
    pue: np.ndarray
    mpue: np.ndarray
    normalization_factor: float
    namespace: str
    pue_application_count: int = 1
    extra_constant_pue_multiplier_count: int = 0
    peak_force_fit_count: int = 0


def _softplus(value: np.ndarray) -> np.ndarray:
    return np.logaddexp(0.0, value)


def _coefficients() -> tuple[np.ndarray, float, np.ndarray]:
    payload = json.loads(C1_PATH.read_text(encoding="utf-8"))
    names = (
        "intercept", "it_mw", "it_mw_squared", "wetbulb_c",
        "wetbulb_excess_c", "it_mw_x_wetbulb_excess_c", "rh_pct",
    )
    coefficients = np.asarray([payload["coefficients"][name] for name in names], dtype=float)
    other = np.asarray([
        payload["other_model_coefficients"]["intercept"],
        payload["other_model_coefficients"]["it_mw"],
    ], dtype=float)
    return coefficients, float(payload["t_ref_c"]), other


def _raw_overhead_kw(equivalent_nlr_it_kw: np.ndarray, wetbulb_c: np.ndarray, rh_pct: np.ndarray) -> np.ndarray:
    coefficients, t_ref_c, other = _coefficients()
    it_mw = equivalent_nlr_it_kw / 1000.0
    excess = np.maximum(wetbulb_c - t_ref_c, 0.0)
    matrix = np.column_stack((
        np.ones_like(it_mw), it_mw, it_mw**2, wetbulb_c, excess,
        it_mw * excess, rh_pct,
    ))
    cooling = _softplus(matrix @ coefficients)
    other_power = _softplus(other[0] + other[1] * it_mw)
    return cooling + other_power


def _normalization(namespace: str) -> float:
    if namespace == "FORECAST_DAYAHEAD_GFS":
        return GFS_NORMALIZATION_FACTOR
    if namespace in {"ACTUAL_REALIZED_NOAA", "PERFECT_INFORMATION_NOAA"}:
        return NOAA_NORMALIZATION_FACTOR
    raise ValueError(f"V28_THERMAL_NAMESPACE_FORBIDDEN:{namespace}")


def c1_trajectory(
    it_power_kw: Iterable[float],
    wetbulb_c: Iterable[float],
    rh_pct: Iterable[float],
    *,
    namespace: str,
) -> C1Trajectory:
    """Apply the frozen C1 response and accepted transfer normalization once."""

    it = np.asarray(tuple(it_power_kw), dtype=np.float64)
    tw = np.asarray(tuple(wetbulb_c), dtype=np.float64)
    rh = np.asarray(tuple(rh_pct), dtype=np.float64)
    if it.shape != (96,) or tw.shape != (96,) or rh.shape != (96,):
        raise ValueError("V28_C1_REQUIRES_EXACTLY_96_SLOTS")
    if np.any(~np.isfinite(it)) or np.any(it < 0) or np.any(~np.isfinite(tw)) or np.any(~np.isfinite(rh)):
        raise ValueError("V28_C1_INPUT_INVALID")
    mean_it = float(np.mean(it))
    if mean_it <= 0:
        zeros = np.zeros(96, dtype=np.float64)
        return C1Trajectory(zeros, np.ones(96), np.ones(96), _normalization(namespace), namespace)
    scale = NLR_MEDIAN_IT_KW / mean_it
    factor = _normalization(namespace)

    def pcc(candidate: np.ndarray) -> np.ndarray:
        raw_overhead = _raw_overhead_kw(candidate * scale, tw, rh)
        # This is algebraically the accepted transfer: Melbourne IT multiplied
        # by the NLR overhead ratio, then normalized.  At IT=0 its continuous
        # limit is used, avoiding division and clipping.
        return candidate + factor / scale * raw_overhead

    pcc_kw = pcc(it)
    pcc_delta = pcc(it * 1.01)
    pue = np.divide(pcc_kw, it, out=np.ones_like(it), where=it > 1e-12)
    mpue = np.divide(pcc_delta - pcc_kw, np.maximum(it * 0.01, 1e-9))
    return C1Trajectory(pcc_kw, pue, mpue, factor, namespace)


def c0_trajectory(it_power_kw: Iterable[float]) -> np.ndarray:
    it = np.asarray(tuple(it_power_kw), dtype=np.float64)
    if it.shape != (96,):
        raise ValueError("V28_C0_REQUIRES_EXACTLY_96_SLOTS")
    return 1.30 * it

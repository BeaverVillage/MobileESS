"""Exact frozen V24T C1 response and LP-compatible affine equalities."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from dayahead.v28.thermal import GFS_NORMALIZATION_FACTOR


FROZEN_NLR_EQUIVALENT_SCALE = 3.4987194698200215


@dataclass(frozen=True)
class C1Parameters:
    intercept: float
    it_mw: float
    it_mw_squared: float
    wetbulb_c: float
    wetbulb_excess_c: float
    it_mw_x_wetbulb_excess_c: float
    rh_pct: float
    t_ref_c: float
    other_intercept: float
    other_it_mw: float


@dataclass(frozen=True)
class AffineCoefficient:
    aidc_id: str
    slot: int
    p_min_kw: float
    p_max_kw: float
    wetbulb_c: float
    rh_pct: float
    slope: float
    intercept_kw: float
    maximum_error_kw: float
    maximum_error_at_kw: float
    minimum_conservatism_kw: float


def load_c1(path: Path) -> C1Parameters:
    payload = json.loads(path.read_text(encoding="utf-8"))
    c = payload["coefficients"]
    other = payload["other_model_coefficients"]
    return C1Parameters(
        *(float(c[name]) for name in (
            "intercept", "it_mw", "it_mw_squared", "wetbulb_c", "wetbulb_excess_c",
            "it_mw_x_wetbulb_excess_c", "rh_pct",
        )),
        float(payload["t_ref_c"]), float(other["intercept"]), float(other["it_mw"]),
    )


def _softplus(value: np.ndarray) -> np.ndarray:
    return np.logaddexp(0.0, value)


def _sigmoid(value: np.ndarray) -> np.ndarray:
    return np.exp(-np.logaddexp(0.0, -value))


def exact_c1_pcc_kw(
    it_kw: np.ndarray | float,
    wetbulb_c: float,
    rh_pct: float,
    parameters: C1Parameters,
    *,
    scale: float = FROZEN_NLR_EQUIVALENT_SCALE,
    normalization_factor: float = GFS_NORMALIZATION_FACTOR,
) -> np.ndarray:
    p = np.asarray(it_kw, dtype=float)
    it_mw = p * scale / 1000.0
    excess = max(float(wetbulb_c) - parameters.t_ref_c, 0.0)
    latent = (
        parameters.intercept + parameters.it_mw * it_mw + parameters.it_mw_squared * it_mw**2
        + parameters.wetbulb_c * wetbulb_c + parameters.wetbulb_excess_c * excess
        + parameters.it_mw_x_wetbulb_excess_c * it_mw * excess + parameters.rh_pct * rh_pct
    )
    other = parameters.other_intercept + parameters.other_it_mw * it_mw
    return p + normalization_factor / scale * (_softplus(latent) + _softplus(other))


def exact_c1_derivative(
    it_kw: np.ndarray | float,
    wetbulb_c: float,
    rh_pct: float,
    parameters: C1Parameters,
    *,
    scale: float = FROZEN_NLR_EQUIVALENT_SCALE,
    normalization_factor: float = GFS_NORMALIZATION_FACTOR,
) -> np.ndarray:
    p = np.asarray(it_kw, dtype=float)
    it_mw = p * scale / 1000.0
    excess = max(float(wetbulb_c) - parameters.t_ref_c, 0.0)
    latent = (
        parameters.intercept + parameters.it_mw * it_mw + parameters.it_mw_squared * it_mw**2
        + parameters.wetbulb_c * wetbulb_c + parameters.wetbulb_excess_c * excess
        + parameters.it_mw_x_wetbulb_excess_c * it_mw * excess + parameters.rh_pct * rh_pct
    )
    dlatent_dp = scale / 1000.0 * (
        parameters.it_mw + parameters.it_mw_x_wetbulb_excess_c * excess
        + 2.0 * parameters.it_mw_squared * it_mw
    )
    other = parameters.other_intercept + parameters.other_it_mw * it_mw
    dother_dp = parameters.other_it_mw * scale / 1000.0
    return 1.0 + normalization_factor / scale * (
        _sigmoid(latent) * dlatent_dp + _sigmoid(other) * dother_dp
    )


def analytic_convexity_certificate(parameters: C1Parameters, p_min_kw: float, p_max_kw: float, wetbulb_c: float) -> bool:
    if p_min_kw < 0 or p_max_kw < p_min_kw:
        return False
    # Frozen C1 has zero quadratic terms, so it is a sum of softplus of
    # affine functions plus P.  softplus is convex for every affine slope.
    return parameters.it_mw_squared == 0.0 and parameters.other_it_mw == 0.0


def endpoint_secant(
    aidc_id: str,
    slot: int,
    p_min_kw: float,
    p_max_kw: float,
    wetbulb_c: float,
    rh_pct: float,
    parameters: C1Parameters,
) -> AffineCoefficient:
    if not analytic_convexity_certificate(parameters, p_min_kw, p_max_kw, wetbulb_c):
        raise ValueError("V28R2_C1_CONVEXITY_NOT_CERTIFIED")
    f_min = float(exact_c1_pcc_kw(p_min_kw, wetbulb_c, rh_pct, parameters))
    if abs(p_max_kw - p_min_kw) <= 1e-12:
        slope = float(exact_c1_derivative(p_min_kw, wetbulb_c, rh_pct, parameters))
        intercept = f_min - slope * p_min_kw
        return AffineCoefficient(aidc_id, slot, p_min_kw, p_max_kw, wetbulb_c, rh_pct, slope, intercept, 0.0, p_min_kw, 0.0)
    f_max = float(exact_c1_pcc_kw(p_max_kw, wetbulb_c, rh_pct, parameters))
    slope = (f_max - f_min) / (p_max_kw - p_min_kw)
    intercept = f_min - slope * p_min_kw
    # For a differentiable convex function, secant-f is concave and reaches
    # its maximum where f'(P)=secant slope.  Bisection gives a certified root
    # bracket; curvature below bounds the remaining numerical uncertainty.
    low, high = p_min_kw, p_max_kw
    for _ in range(80):
        middle = (low + high) / 2.0
        if float(exact_c1_derivative(middle, wetbulb_c, rh_pct, parameters)) < slope:
            low = middle
        else:
            high = middle
    maximum_at = (low + high) / 2.0
    maximum_error = slope * maximum_at + intercept - float(exact_c1_pcc_kw(maximum_at, wetbulb_c, rh_pct, parameters))
    endpoint_errors = np.asarray([
        slope * p_min_kw + intercept - f_min,
        slope * p_max_kw + intercept - f_max,
    ])
    return AffineCoefficient(
        aidc_id, slot, p_min_kw, p_max_kw, wetbulb_c, rh_pct, slope, intercept,
        float(maximum_error), float(maximum_at), float(endpoint_errors.min()),
    )


def add_planning_equality(model, p_it_variable, p_pcc_variable, coefficient: AffineCoefficient):
    """Single common binding used by Monolithic, Standard BD, and CL-MC-BD."""

    return model.addConstr(
        p_pcc_variable == coefficient.slope * p_it_variable + coefficient.intercept_kw,
        name=f"v28r2_c1_eq_{coefficient.aidc_id}_{coefficient.slot:02d}",
    )

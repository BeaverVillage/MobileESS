"""Constrained coherent quantile-function reconciliation for the base CDF."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import minimize

from .contracts import BASE_QUANTILES


TAU = np.asarray(BASE_QUANTILES, float)


def integration_weights() -> np.ndarray:
    """Return linear-quantile integration weights including constant end tails."""

    weights = np.zeros(len(TAU), float)
    weights[0] += TAU[0]
    weights[-1] += 1.0 - TAU[-1]
    for index in range(len(TAU) - 1):
        width = TAU[index + 1] - TAU[index]
        weights[index] += width / 2.0
        weights[index + 1] += width / 2.0
    return weights


WEIGHTS = integration_weights()


@dataclass(frozen=True)
class ReconciledBase:
    """One valid nonnegative piecewise-linear quantile function in GPU-h."""

    raw_mean_GPU_h: float
    quantiles_GPU_h: np.ndarray
    method: str
    optimization_success: bool
    mean_GPU_h: float
    raw_crossing_count: int

    def quantile(self, probability: np.ndarray | float) -> np.ndarray:
        """Evaluate the stable inverse CDF on probabilities in [0,1]."""

        p = np.asarray(probability, float)
        return np.interp(p, TAU, self.quantiles_GPU_h, left=self.quantiles_GPU_h[0], right=self.quantiles_GPU_h[-1])

    def cdf(self, value_GPU_h: np.ndarray | float) -> np.ndarray:
        """Evaluate a right-continuous numerical CDF on nonnegative GPU-h."""

        value = np.asarray(value_GPU_h, float)
        q, unique = np.unique(self.quantiles_GPU_h, return_index=True)
        p = TAU[unique]
        if len(q) == 1:
            return np.where(value < q[0], 0.0, 1.0)
        return np.clip(np.interp(value, q, p, left=0.0, right=1.0), 0.0, 1.0)

    def sample(self, uniforms: np.ndarray) -> np.ndarray:
        """Map deterministic uniforms to nonnegative GPU-h samples."""

        return self.quantile(uniforms)


def reconcile_one(raw_mean_GPU_h: float, raw_quantiles_GPU_h: np.ndarray, method: str) -> ReconciledBase:
    """Project raw quantiles with nonnegative monotonic constraints, never by sorting."""

    raw = np.maximum(np.asarray(raw_quantiles_GPU_h, float), 0.0)
    crossing = int(np.sum(np.diff(raw) < 0.0))
    scale = max(float(np.mean(raw**2)), 1.0)
    roughness = np.diff(np.eye(len(raw)), n=2, axis=0)
    if method == "BR-A":
        target_mean = max(float(raw_mean_GPU_h), 0.0)
        objective = lambda q: float(np.sum((q - raw) ** 2) / scale + 0.01 * np.sum((roughness @ q) ** 2) / scale)
        constraints = [
            {"type": "ineq", "fun": lambda q: q},
            {"type": "ineq", "fun": lambda q: np.diff(q)},
            {"type": "eq", "fun": lambda q: float(np.dot(WEIGHTS, q) - target_mean)},
        ]
    elif method == "BR-B":
        objective = lambda q: float(np.sum((q - raw) ** 2) / scale + 0.005 * np.sum((roughness @ q) ** 2) / scale)
        constraints = [
            {"type": "ineq", "fun": lambda q: q},
            {"type": "ineq", "fun": lambda q: np.diff(q)},
        ]
    else:
        raise ValueError(f"V25M_UNKNOWN_BASE_RECONCILIATION:{method}")
    initial = np.maximum.accumulate(raw)
    if method == "BR-A":
        current = float(np.dot(WEIGHTS, initial))
        initial = np.full_like(initial, target_mean) if current <= 0 else initial * target_mean / current
    result = minimize(objective, initial, method="SLSQP", constraints=constraints, options={"maxiter": 500, "ftol": 1e-10})
    if not result.success:
        raise RuntimeError(f"V25M_BASE_RECONCILIATION_OPTIMIZER:{method}:{result.message}")
    q = np.asarray(result.x, float)
    if np.min(q) < -1e-7 or np.min(np.diff(q)) < -1e-7:
        raise RuntimeError("V25M_BASE_RECONCILIATION_CONSTRAINT")
    q = np.maximum.accumulate(np.maximum(q, 0.0))  # numerical cleanup below solver tolerance only
    mean = float(np.dot(WEIGHTS, q))
    return ReconciledBase(float(raw_mean_GPU_h), q, method, True, mean, crossing)


def reconcile_batch(raw_mean_GPU_h: np.ndarray, raw_quantiles_GPU_h: np.ndarray, method: str) -> list[ReconciledBase]:
    """Reconcile a batch of independent daily base distributions."""

    return [reconcile_one(mean, quantiles, method) for mean, quantiles in zip(raw_mean_GPU_h, raw_quantiles_GPU_h)]


"""Small monotonic reliability gate for GP and analog predictive distributions."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import minimize
from scipy.special import expit


@dataclass(frozen=True)
class ReliabilityGate:
    """Constrained six-parameter gate; alpha is analog-distribution weight."""

    raw_parameters: np.ndarray
    selection: str
    inner_CRPS_gp: float
    inner_CRPS_analog: float
    inner_CRPS_gate_proxy: float

    def alpha(self, features: np.ndarray) -> np.ndarray:
        """Return analog reliability weights in [0,1]."""

        if self.selection == "GP_ONLY":
            return np.zeros(len(features))
        if self.selection == "ANALOG_ONLY":
            return np.ones(len(features))
        raw = self.raw_parameters
        positive = np.log1p(np.exp(raw[1:]))
        score = (
            raw[0]
            - positive[0] * features[:, 0]
            + positive[1] * np.log1p(features[:, 1])
            - positive[2] * features[:, 2]
            - positive[3] * features[:, 3]
            - positive[4] * features[:, 4]
        )
        return expit(score)


def fit_reliability_gate(
    features: np.ndarray, gp_crps: np.ndarray, analog_crps: np.ndarray
) -> ReliabilityGate:
    """Fit monotonic signs on inner-validation CRPS only and require component lift."""

    target = (analog_crps < gp_crps).astype(float)

    def objective(raw: np.ndarray) -> float:
        gate = ReliabilityGate(raw, "MIXTURE", 0.0, 0.0, 0.0)
        alpha = np.clip(gate.alpha(features), 1e-8, 1 - 1e-8)
        loss = -np.mean(target * np.log(alpha) + (1 - target) * np.log(1 - alpha))
        return float(loss + 1e-3 * np.sum(raw**2))

    result = minimize(objective, np.zeros(6), method="L-BFGS-B")
    raw = np.asarray(result.x, float)
    provisional = ReliabilityGate(raw, "MIXTURE", 0.0, 0.0, 0.0)
    alpha = provisional.alpha(features)
    gp_mean = float(np.mean(gp_crps))
    analog_mean = float(np.mean(analog_crps))
    proxy = float(np.mean(alpha * analog_crps + (1.0 - alpha) * gp_crps))
    best = min(gp_mean, analog_mean)
    if proxy >= best - 1e-12:
        selection = "GP_ONLY" if gp_mean <= analog_mean else "ANALOG_ONLY"
    else:
        selection = "MIXTURE"
    return ReliabilityGate(raw, selection, gp_mean, analog_mean, proxy)

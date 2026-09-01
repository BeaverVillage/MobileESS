"""Training-only calibration for conditional exceedance hazards."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import minimize
from scipy.special import expit, logit

from .hazards import EPS, conditional_to_absolute


@dataclass
class SharedBetaHazardCalibrator:
    """Shared beta calibration fitted on an outer-training calibration block only."""

    a: float = 1.0
    b: float = 0.0
    fitted: bool = False

    def fit(self, conditional: np.ndarray, labels: np.ndarray) -> "SharedBetaHazardCalibrator":
        """Fit shared logit slope/intercept with unweighted Bernoulli likelihood."""

        logits, outcomes = [], []
        labels = np.asarray(labels, bool)
        for k in range(conditional.shape[1]):
            eligible = np.ones(len(labels), bool) if k == 0 else labels[:, k - 1]
            logits.extend(logit(np.clip(conditional[eligible, k], EPS, 1.0 - EPS)).tolist())
            outcomes.extend(labels[eligible, k].astype(float).tolist())
        x, y = np.asarray(logits), np.asarray(outcomes)

        def loss(parameters: np.ndarray) -> float:
            eta = parameters[0] * x + parameters[1]
            return float(np.logaddexp(0.0, eta).sum() - np.dot(y, eta) + .02 * np.square(parameters[0] - 1.0))

        result = minimize(
            loss, np.asarray([1.0, 0.0]), method="L-BFGS-B",
            bounds=((1e-3, 10.0), (None, None)),
        )
        if not result.success:
            raise RuntimeError(f"V25M_CALIBRATION_OPTIMIZER:{result.message}")
        self.a, self.b = map(float, result.x)
        self.fitted = True
        return self

    def transform_conditional(self, conditional: np.ndarray) -> np.ndarray:
        """Apply the shared map while preserving conditional-hazard support."""

        if not self.fitted:
            raise RuntimeError("V25M_CALIBRATOR_NOT_FITTED")
        return np.clip(expit(self.a * logit(np.clip(conditional, EPS, 1.0 - EPS)) + self.b), EPS, 1.0 - EPS)

    def transform_absolute(self, conditional: np.ndarray) -> np.ndarray:
        """Return ordered absolute exceedance probabilities after calibration."""

        return conditional_to_absolute(self.transform_conditional(conditional))

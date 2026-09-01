"""Baseline-anchored multi-threshold conditional exceedance hazards."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import minimize
from scipy.special import expit, logit

from .base_reconciliation import ReconciledBase
from .contracts import CONDITIONAL_HAZARD_EPSILON, THRESHOLD_QUANTILES


EPS = CONDITIONAL_HAZARD_EPSILON


def training_thresholds(target_GPU_h: np.ndarray) -> np.ndarray:
    """Return P60/P70/P80/P90/P95 using training targets only, in GPU-h."""

    return np.quantile(np.asarray(target_GPU_h, float), THRESHOLD_QUANTILES)


def exceedance_labels(target_GPU_h: np.ndarray, thresholds_GPU_h: np.ndarray) -> np.ndarray:
    """Return strict exceedance indicators with shape ``[days,5]``."""

    return np.asarray(target_GPU_h, float)[:, None] > np.asarray(thresholds_GPU_h, float)[None, :]


def base_exceedance_probabilities(bases: list[ReconciledBase], thresholds_GPU_h: np.ndarray) -> np.ndarray:
    """Evaluate exceedance probabilities from coherent base CDFs."""

    return np.asarray([[1.0 - float(base.cdf(value)) for value in thresholds_GPU_h] for base in bases])


def absolute_to_conditional(probabilities: np.ndarray) -> np.ndarray:
    """Convert ordered absolute exceedance probabilities to conditional hazards."""

    p = np.clip(np.asarray(probabilities, float), EPS, 1.0 - EPS)
    conditional = np.empty_like(p)
    conditional[:, 0] = p[:, 0]
    conditional[:, 1:] = p[:, 1:] / np.maximum(p[:, :-1], EPS)
    return np.clip(conditional, EPS, 1.0 - EPS)


def conditional_to_absolute(conditional: np.ndarray) -> np.ndarray:
    """Multiply conditional hazards so absolute exceedance probabilities are ordered."""

    r = np.clip(np.asarray(conditional, float), EPS, 1.0 - EPS)
    return np.cumprod(r, axis=1)


@dataclass
class AnchoredHazardLadder:
    """Shared pressure trunk with five small baseline-offset residual heads."""

    coefficients: np.ndarray | None = None
    feature_median: np.ndarray | None = None
    feature_IQR: np.ndarray | None = None
    anchor_penalty: float = 0.20
    adjacent_penalty: float = 0.02

    def fit(self, features: np.ndarray, labels: np.ndarray, base_absolute: np.ndarray) -> "AnchoredHazardLadder":
        """Fit residual logits on cross-fitted base hazards using unweighted likelihood."""

        x = np.asarray(features, float)
        self.feature_median = np.median(x, axis=0)
        self.feature_IQR = np.maximum(np.quantile(x, .75, axis=0) - np.quantile(x, .25, axis=0), 1e-6)
        x = np.clip((x - self.feature_median) / self.feature_IQR, -25.0, 25.0)
        x = np.column_stack((np.ones(len(x)), x))
        labels = np.asarray(labels, bool)
        base_conditional = absolute_to_conditional(base_absolute)
        dimensions = (5, x.shape[1])

        def objective(flat: np.ndarray) -> tuple[float, np.ndarray]:
            beta = flat.reshape(dimensions)
            loss = 0.0
            gradient = np.zeros_like(beta)
            for k in range(5):
                eligible = np.ones(len(x), bool) if k == 0 else labels[:, k - 1]
                if not np.any(eligible):
                    continue
                eta = logit(base_conditional[eligible, k]) + x[eligible] @ beta[k]
                y = labels[eligible, k].astype(float)
                loss += float(np.logaddexp(0.0, eta).sum() - np.dot(y, eta))
                gradient[k] += x[eligible].T @ (expit(eta) - y)
            loss += self.anchor_penalty * float(np.square(beta).sum())
            gradient += 2.0 * self.anchor_penalty * beta
            # Smooth L1 keeps the preregistered adjacent-head shrinkage while giving
            # L-BFGS-B a stable derivative at exactly equal neighbouring heads.
            difference = np.diff(beta, axis=0)
            root = np.sqrt(np.square(difference) + 1e-8)
            loss += self.adjacent_penalty * float(root.sum())
            adjacent_gradient = self.adjacent_penalty * difference / root
            gradient[:-1] -= adjacent_gradient
            gradient[1:] += adjacent_gradient
            return loss, gradient.ravel()

        result = minimize(objective, np.zeros(np.prod(dimensions)), method="L-BFGS-B", jac=True, options={"maxiter": 500})
        if not result.success or not np.all(np.isfinite(result.x)):
            raise RuntimeError(f"V25M_HAZARD_OPTIMIZER:{result.message}")
        self.coefficients = result.x.reshape(dimensions)
        return self

    def predict_conditional(self, features: np.ndarray, base_absolute: np.ndarray) -> np.ndarray:
        """Return bounded conditional hazards without silent NaN repair."""

        if self.coefficients is None or self.feature_median is None or self.feature_IQR is None:
            raise RuntimeError("V25M_HAZARD_NOT_FITTED")
        x = np.clip((np.asarray(features, float) - self.feature_median) / self.feature_IQR, -25.0, 25.0)
        x = np.column_stack((np.ones(len(x)), x))
        offsets = logit(absolute_to_conditional(base_absolute))
        conditional = expit(offsets + x @ self.coefficients.T)
        if not np.all(np.isfinite(conditional)):
            raise RuntimeError("V25M_HAZARD_NONFINITE")
        return np.clip(conditional, EPS, 1.0 - EPS)

    def predict_absolute(self, features: np.ndarray, base_absolute: np.ndarray) -> np.ndarray:
        """Return structurally monotone P60–P95 absolute exceedance probabilities."""

        return conditional_to_absolute(self.predict_conditional(features, base_absolute))

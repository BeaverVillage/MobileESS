"""Training-only scalar conformal quantile calibration."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class QuantileCalibration:
    """Additive corrections fitted only on an inner chronological calibration split."""

    q50_additive_GPU_h: float
    q90_additive_GPU_h: float

    def apply(self, q50: np.ndarray, q90: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        calibrated_q50 = np.maximum(0.0, np.asarray(q50) + self.q50_additive_GPU_h)
        calibrated_q90 = np.maximum(calibrated_q50, np.asarray(q90) + self.q90_additive_GPU_h)
        return calibrated_q50, calibrated_q90


def fit_additive_calibration(actual: np.ndarray, q50: np.ndarray, q90: np.ndarray) -> QuantileCalibration:
    """Fit empirical residual quantiles on training-only calibration days."""

    residual50 = np.asarray(actual) - np.asarray(q50)
    residual90 = np.asarray(actual) - np.asarray(q90)
    return QuantileCalibration(float(np.quantile(residual50, 0.5)), float(np.quantile(residual90, 0.9)))

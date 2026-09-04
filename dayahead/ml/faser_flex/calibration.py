"""Training-only monotone quantile calibration for FASER distributions."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class QuantileCalibration:
    """Additive Q50/Q90 corrections learned on a chronological calibration block."""

    q50_additive_GPU_h: float
    q90_additive_GPU_h: float

    def apply(self, q50: np.ndarray, q90: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Apply support-preserving monotone calibration without altering the mean."""

        median = np.maximum(0.0, np.asarray(q50, float) + self.q50_additive_GPU_h)
        upper = np.maximum(
            median, np.asarray(q90, float) + self.q90_additive_GPU_h
        )
        return median, upper


def fit_quantile_calibration(
    actual: np.ndarray, q50: np.ndarray, q90: np.ndarray
) -> QuantileCalibration:
    """Fit empirical residual corrections on training-only calibration days."""

    return QuantileCalibration(
        float(np.quantile(actual - q50, 0.50)),
        float(np.quantile(actual - q90, 0.90)),
    )

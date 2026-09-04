"""Blocked-OOF one-sided route Safe-ETA calibration."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Sequence

import numpy as np


@dataclass(frozen=True)
class RouteSafeEtaCalibration:
    margins_sec: tuple[float, float, float, float]
    quantile: float = 0.9
    fit_namespace: str = "BLOCKED_OOF_ONLY"

    @classmethod
    def fit(cls, residuals_by_band: Sequence[Sequence[float]], quantile: float = 0.9):
        if len(residuals_by_band) != 4 or not 0.0 < quantile < 1.0:
            raise ValueError("four lead bands and a valid one-sided quantile are required")
        margins = []
        for values in residuals_by_band:
            array = np.asarray(values, dtype=float)
            if array.size == 0 or not np.isfinite(array).all():
                raise ValueError("OOF calibration residuals must be finite and non-empty")
            rank = min(array.size - 1, math.ceil((array.size + 1) * quantile) - 1)
            margins.append(max(0.0, float(np.sort(array)[rank])))
        return cls(tuple(margins), quantile)

    def margin_for_departure_slot(self, departure_slot_15: int) -> float:
        if not 0 <= departure_slot_15 < 96:
            raise ValueError("departure slot must be in [0,95]")
        return self.margins_sec[departure_slot_15 // 24]

    def safe_eta(self, q50_route_eta_sec: float, departure_slot_15: int) -> float:
        return float(q50_route_eta_sec) + self.margin_for_departure_slot(departure_slot_15)

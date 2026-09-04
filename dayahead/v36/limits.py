"""One-shot Planning safety margins without changing frozen objectives."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Mapping


@dataclass(frozen=True)
class PlanningMargins:
    vlow_pu: float = 0.0
    vhigh_pu: float = 0.0
    rho_pu: float = 0.0
    transformer_pu: float = 0.0

    def validate(self, vmin: float, vmax: float) -> None:
        values = (self.vlow_pu, self.vhigh_pu, self.rho_pu, self.transformer_pu)
        if not all(math.isfinite(value) and value >= 0 for value in values):
            raise ValueError("V36_MARGIN_NONFINITE_OR_NEGATIVE")
        if vmin + self.vlow_pu >= vmax - self.vhigh_pu:
            raise RuntimeError("CALIBRATION_MARGIN_STRUCTURAL_INFEASIBILITY")
        if 1.0 - self.rho_pu <= 0 or 1.0 - self.transformer_pu <= 0:
            raise RuntimeError("CALIBRATION_MARGIN_STRUCTURAL_INFEASIBILITY")

    def to_dict(self) -> dict[str, float]:
        return {
            "m_Vlow": self.vlow_pu, "m_Vhigh": self.vhigh_pu,
            "m_rho": self.rho_pu, "m_xfmr": self.transformer_pu,
        }


def derive_case_day_margins(rows: list[Mapping[str, Any]]) -> PlanningMargins:
    if len(rows) != 28:
        raise ValueError("V36_CALIBRATION_REQUIRES_28_CASE_DAYS")
    keys = ("r_Vlow", "r_Vhigh", "r_rho", "r_xfmr")
    for row in rows:
        if not all(math.isfinite(float(row[key])) and float(row[key]) >= 0 for key in keys):
            raise ValueError("V36_CALIBRATION_RESIDUAL_INVALID")
    # ceil((28+1)*.95)=28, clipped to n: the deterministic order statistic is max.
    return PlanningMargins(*(max(float(row[key]) for row in rows) for key in keys))

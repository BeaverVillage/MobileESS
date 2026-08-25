"""Canonical electrical-stress semantics shared by planning and evaluation.

The optimizer uses a causal network surrogate.  Fresh OpenDSS remains the
authority for executed three-phase AC feasibility and the realized stress KPI.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable


OBJECTIVE_AUTHORITY = "ELECTRICAL_STRESS_OBJECTIVE_V1"
VOLTAGE_MIN_PU = 0.95
VOLTAGE_MAX_PU = 1.05


def _finite_nonnegative(name: str, value: float) -> float:
    value = float(value)
    if not math.isfinite(value) or value < 0.0:
        raise ValueError(f"{name} must be finite and nonnegative")
    return value


@dataclass(frozen=True)
class ElectricalStress:
    """Dimensionless stress components on their physical operating limits."""

    voltage: float
    line: float
    transformer: float

    def __post_init__(self) -> None:
        _finite_nonnegative("voltage stress", self.voltage)
        _finite_nonnegative("line stress", self.line)
        _finite_nonnegative("transformer stress", self.transformer)

    @property
    def worst(self) -> float:
        return max(float(self.voltage), float(self.line), float(self.transformer))

    def as_dict(self) -> dict[str, float | str]:
        return {
            "objective_authority": OBJECTIVE_AUTHORITY,
            "voltage_stress_pu": float(self.voltage),
            "line_stress_pu": float(self.line),
            "transformer_stress_pu": float(self.transformer),
            "worst_electrical_stress_pu": self.worst,
        }


def voltage_stress_from_extrema(
    minimum_voltage_pu: float,
    maximum_voltage_pu: float,
) -> float:
    """Return normalized distance from 1 pu toward the nearer voltage limit.

    Values below/above 1 pu are normalized by the corresponding 0.05-pu
    operating band.  The metric remains meaningful outside the hard-safe set:
    a value greater than one denotes a voltage-limit violation.
    """

    vmin = float(minimum_voltage_pu)
    vmax = float(maximum_voltage_pu)
    if not all(math.isfinite(value) for value in (vmin, vmax)) or vmin > vmax:
        raise ValueError("voltage extrema must be finite and ordered")
    return max(
        0.0,
        (1.0 - vmin) / (1.0 - VOLTAGE_MIN_PU),
        (vmax - 1.0) / (VOLTAGE_MAX_PU - 1.0),
    )


def stress_from_extrema(
    *,
    minimum_voltage_pu: float,
    maximum_voltage_pu: float,
    maximum_line_loading_fraction: float,
    maximum_transformer_loading_fraction: float,
) -> ElectricalStress:
    """Build the frozen exact/surrogate-compatible stress tuple."""

    return ElectricalStress(
        voltage=voltage_stress_from_extrema(
            minimum_voltage_pu, maximum_voltage_pu
        ),
        line=_finite_nonnegative(
            "maximum line loading", maximum_line_loading_fraction
        ),
        transformer=_finite_nonnegative(
            "maximum transformer loading", maximum_transformer_loading_fraction
        ),
    )


def trajectory_summary(
    samples: Iterable[ElectricalStress], *, step_hours: float
) -> dict[str, float | str]:
    """Return the lexicographic primary and exposure KPIs for a trajectory."""

    dt = float(step_hours)
    if not math.isfinite(dt) or dt <= 0.0:
        raise ValueError("step_hours must be finite and positive")
    rows = tuple(samples)
    worst = max((row.worst for row in rows), default=0.0)
    exposure = sum(row.worst for row in rows) * dt
    return {
        "objective_authority": OBJECTIVE_AUTHORITY,
        "worst_electrical_stress_pu": float(worst),
        "electrical_stress_exposure_pu_hours": float(exposure),
    }

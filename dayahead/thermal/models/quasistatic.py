"""C1 nonnegative quasi-static NLR cooling model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import ArrayLike, NDArray


FEATURE_NAMES = (
    "intercept",
    "it_mw",
    "it_mw_squared",
    "wetbulb_c",
    "wetbulb_excess_c",
    "it_mw_x_wetbulb_excess_c",
    "rh_pct",
)


def softplus(value: ArrayLike) -> NDArray[np.float64]:
    """Return a numerically stable structural nonnegative transform [kW]."""
    return np.logaddexp(0.0, np.asarray(value, dtype=float))


def inverse_softplus(value: ArrayLike) -> NDArray[np.float64]:
    """Map a positive measured target [kW] to the softplus latent scale."""
    y = np.maximum(np.asarray(value, dtype=float), 1e-9)
    return np.where(y > 30.0, y, y + np.log(-np.expm1(-y)))


def feature_matrix(
    it_power_kw: ArrayLike,
    wetbulb_c: ArrayLike,
    rh_pct: ArrayLike,
    t_ref_c: float,
) -> NDArray[np.float64]:
    """Return C1 design features with IT converted from kW to MW."""
    it = np.asarray(it_power_kw, dtype=float) / 1000.0
    tw = np.asarray(wetbulb_c, dtype=float)
    rh = np.asarray(rh_pct, dtype=float)
    excess = np.maximum(tw - t_ref_c, 0.0)
    return np.column_stack(
        [np.ones_like(it), it, it**2, tw, excess, it * excess, rh]
    )


@dataclass(frozen=True)
class QuasiStaticModel:
    """C1 coefficients in physical feature units and training-only T_ref [degC]."""

    coefficients: tuple[float, ...]
    t_ref_c: float

    def predict_cooling_kw(
        self, it_power_kw: ArrayLike, wetbulb_c: ArrayLike, rh_pct: ArrayLike
    ) -> NDArray[np.float64]:
        """Predict nonnegative cooling-system power [kW]."""
        matrix = feature_matrix(it_power_kw, wetbulb_c, rh_pct, self.t_ref_c)
        return softplus(matrix @ np.asarray(self.coefficients))

    def as_dict(self) -> dict[str, Any]:
        """Serialize C1 with coefficient feature names and units."""
        return {
            "model": "C1_WEATHER_DEPENDENT_QUASISTATIC_PUE",
            "t_ref_c": self.t_ref_c,
            "coefficients": dict(zip(FEATURE_NAMES, self.coefficients)),
            "output": "softplus(latent) kW",
            "constraints": {
                "it_mw": ">=0",
                "it_mw_squared": ">=0",
                "wetbulb_excess_c": ">=0",
                "it_mw_x_wetbulb_excess_c": ">=0",
            },
        }

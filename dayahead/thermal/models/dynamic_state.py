"""C2 causal stable ARX-equivalent thermal-inertia model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import ArrayLike, NDArray
from scipy.signal import lfilter

from .quasistatic import softplus


DYNAMIC_FEATURE_NAMES = (
    "intercept",
    "it_mw",
    "it_mw_squared",
    "wetbulb_c",
    "rh_pct",
    "it_mw_x_wetbulb_c",
    "theta_it_mw",
    "theta_wetbulb_c",
)


def causal_state(values: ArrayLike, rho: float, initial: float | None = None) -> NDArray[np.float64]:
    """Return theta(t) using inputs no later than t-1 at the native cadence."""
    x = np.asarray(values, dtype=float)
    if not 0.0 < rho < 1.0:
        raise ValueError("rho must be strictly between zero and one")
    if len(x) == 0:
        return x.copy()
    initial_value = float(x[0] if initial is None else initial)
    filtered, _ = lfilter([1.0 - rho], [1.0, -rho], x, zi=[rho * initial_value])
    theta = np.empty_like(filtered)
    theta[0] = initial_value
    theta[1:] = filtered[:-1]
    return theta


def dynamic_feature_matrix(
    it_power_kw: ArrayLike,
    wetbulb_c: ArrayLike,
    rh_pct: ArrayLike,
    rho: float,
    initial_it_mw: float | None = None,
    initial_wetbulb_c: float | None = None,
) -> tuple[NDArray[np.float64], NDArray[np.float64], NDArray[np.float64]]:
    """Return causal C2 features and its two equivalent stable input states."""
    it = np.asarray(it_power_kw, dtype=float) / 1000.0
    tw = np.asarray(wetbulb_c, dtype=float)
    rh = np.asarray(rh_pct, dtype=float)
    theta_it = causal_state(it, rho, initial_it_mw)
    theta_tw = causal_state(tw, rho, initial_wetbulb_c)
    matrix = np.column_stack(
        [np.ones_like(it), it, it**2, tw, rh, it * tw, theta_it, theta_tw]
    )
    return matrix, theta_it, theta_tw


@dataclass(frozen=True)
class DynamicThermalModel:
    """C2 stable causal model with one shared rho and two ARX input states."""

    coefficients: tuple[float, ...]
    rho: float
    cadence_minutes: float

    @property
    def tau_minutes(self) -> float:
        """Return the identified thermal time constant [minutes]."""
        return -self.cadence_minutes / np.log(self.rho)

    def predict_cooling_kw(
        self,
        it_power_kw: ArrayLike,
        wetbulb_c: ArrayLike,
        rh_pct: ArrayLike,
        initial_it_mw: float | None = None,
        initial_wetbulb_c: float | None = None,
    ) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
        """Recursively predict cooling [kW] without measured cooling inputs."""
        matrix, theta_it, theta_tw = dynamic_feature_matrix(
            it_power_kw,
            wetbulb_c,
            rh_pct,
            self.rho,
            initial_it_mw,
            initial_wetbulb_c,
        )
        prediction = softplus(matrix @ np.asarray(self.coefficients))
        # Combined normalized signal for diagnostics only; no policy authority.
        theta = theta_it + theta_tw / max(np.nanstd(theta_tw), 1e-9)
        return prediction, theta

    def as_dict(self) -> dict[str, Any]:
        """Serialize stable C2 parameters, units, and causal state semantics."""
        return {
            "model": "C2_THERMAL_INERTIA_DYNAMIC_PUE",
            "form": "stable ARX-equivalent with shared rho and separate IT/wet-bulb state channels",
            "rho": self.rho,
            "cadence_minutes": self.cadence_minutes,
            "tau_minutes": self.tau_minutes,
            "tau_hours": self.tau_minutes / 60.0,
            "coefficients": dict(zip(DYNAMIC_FEATURE_NAMES, self.coefficients)),
            "state_update": "theta_x(t+1)=rho*theta_x(t)+(1-rho)*x(t)",
            "validation_state_inputs": "IT and weather only; measured cooling read count after fold start = 0",
        }

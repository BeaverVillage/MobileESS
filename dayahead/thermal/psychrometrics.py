"""Pressure-aware psychrometric transforms with explicit SI boundaries."""

from __future__ import annotations

import numpy as np
from numpy.typing import ArrayLike, NDArray


def saturation_vapor_pressure_hpa(temp_c: ArrayLike) -> NDArray[np.float64]:
    """Return Buck (1981) saturation vapor pressure [hPa] over water."""
    t = np.asarray(temp_c, dtype=float)
    return 6.1121 * np.exp((18.678 - t / 234.5) * (t / (257.14 + t)))


def relative_humidity_from_dewpoint(
    dry_bulb_c: ArrayLike, dewpoint_c: ArrayLike
) -> NDArray[np.float64]:
    """Return RH [%] from dry-bulb and dewpoint temperatures [degC]."""
    t = np.asarray(dry_bulb_c, dtype=float)
    td = np.asarray(dewpoint_c, dtype=float)
    return np.clip(100.0 * saturation_vapor_pressure_hpa(td) / saturation_vapor_pressure_hpa(t), 0, 100)


def dewpoint_from_relative_humidity(
    dry_bulb_c: ArrayLike, relative_humidity_pct: ArrayLike
) -> NDArray[np.float64]:
    """Return dewpoint [degC] using the inverse Magnus relation."""
    t = np.asarray(dry_bulb_c, dtype=float)
    rh = np.clip(np.asarray(relative_humidity_pct, dtype=float), 1e-6, 100.0)
    alpha = np.log(rh / 100.0) + 17.625 * t / (243.04 + t)
    return 243.04 * alpha / (17.625 - alpha)


def wet_bulb_temperature_c(
    dry_bulb_c: ArrayLike,
    relative_humidity_pct: ArrayLike,
    pressure_pa: ArrayLike | float = 101325.0,
    iterations: int = 32,
) -> NDArray[np.float64]:
    """Return ventilated-psychrometer wet bulb [degC] by bounded bisection.

    The root is ``e = es(Twb) - A*P*(Tdb-Twb)`` with
    ``A=0.00066*(1+0.00115*Twb)`` and pressure in hPa. Bisection is bounded by
    the inverse-Magnus dewpoint and dry bulb, guaranteeing physical ordering.
    """
    t, rh, p = np.broadcast_arrays(
        np.asarray(dry_bulb_c, dtype=float),
        np.asarray(relative_humidity_pct, dtype=float),
        np.asarray(pressure_pa, dtype=float),
    )
    if np.any((rh < 0) | (rh > 100)):
        raise ValueError("relative humidity must be in [0, 100] percent")
    if np.any((p < 50_000) | (p > 110_000)):
        raise ValueError("pressure must be in [50000, 110000] Pa")
    td = dewpoint_from_relative_humidity(t, rh)
    vapor = rh / 100.0 * saturation_vapor_pressure_hpa(t)
    low, high = td.copy(), t.copy()
    p_hpa = p / 100.0
    for _ in range(iterations):
        mid = (low + high) / 2.0
        residual = saturation_vapor_pressure_hpa(mid) - (
            0.00066 * (1.0 + 0.00115 * mid) * p_hpa * (t - mid)
        ) - vapor
        high = np.where(residual > 0, mid, high)
        low = np.where(residual <= 0, mid, low)
    return np.minimum(t, np.maximum(td, (low + high) / 2.0))


def validate_psychrometrics(
    dry_bulb_c: ArrayLike,
    dewpoint_c: ArrayLike,
    relative_humidity_pct: ArrayLike,
    wet_bulb_c: ArrayLike,
    pressure_pa: ArrayLike,
    tolerance_c: float = 0.05,
) -> dict[str, float | bool]:
    """Validate physical ranges for temperatures [degC], RH [%], pressure [Pa]."""
    t, td, rh, tw, p = map(
        lambda value: np.asarray(value, dtype=float),
        (dry_bulb_c, dewpoint_c, relative_humidity_pct, wet_bulb_c, pressure_pa),
    )
    finite = np.isfinite(t) & np.isfinite(td) & np.isfinite(rh) & np.isfinite(tw) & np.isfinite(p)
    return {
        "finite_count": int(finite.sum()),
        "rh_in_range": bool(np.all((rh[finite] >= 0) & (rh[finite] <= 100))),
        "dewpoint_le_drybulb": bool(np.all(td[finite] <= t[finite] + tolerance_c)),
        "wetbulb_ge_dewpoint": bool(np.all(tw[finite] >= td[finite] - tolerance_c)),
        "wetbulb_le_drybulb": bool(np.all(tw[finite] <= t[finite] + tolerance_c)),
        "pressure_physical": bool(np.all((p[finite] >= 50_000) & (p[finite] <= 110_000))),
        "max_wetbulb_above_drybulb_c": float(np.max(tw[finite] - t[finite])) if finite.any() else float("nan"),
        "max_dewpoint_above_drybulb_c": float(np.max(td[finite] - t[finite])) if finite.any() else float("nan"),
    }

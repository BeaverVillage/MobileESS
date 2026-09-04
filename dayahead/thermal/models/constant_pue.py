"""Frozen C0 constant-PUE baseline."""

from __future__ import annotations

import numpy as np
from numpy.typing import ArrayLike, NDArray

from ..contracts import REFERENCE_PUE


def constant_pue(it_power_kw: ArrayLike) -> NDArray[np.float64]:
    """Return C0 PCC power [kW] as exactly 1.30 times IT power [kW]."""
    return REFERENCE_PUE * np.asarray(it_power_kw, dtype=float)

"""Local finite-difference marginal PUE diagnostics."""

from __future__ import annotations

import numpy as np
from numpy.typing import ArrayLike, NDArray


def finite_difference_mpue(
    it_power_kw: ArrayLike,
    pcc_base_kw: ArrayLike,
    pcc_perturbed_kw: ArrayLike,
    relative_delta: float = 0.01,
) -> NDArray[np.float64]:
    """Return dPCC/dIT for a pre-registered 1% local IT perturbation."""
    it = np.asarray(it_power_kw, dtype=float)
    if relative_delta != 0.01:
        raise ValueError("V24T pre-registers a 1% local IT perturbation")
    return (np.asarray(pcc_perturbed_kw) - np.asarray(pcc_base_kw)) / (relative_delta * it)

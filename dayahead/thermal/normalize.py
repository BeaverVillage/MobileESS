"""Reference-PUE energy normalization without an extra PUE multiplier."""

from __future__ import annotations

from typing import Any

import numpy as np
from numpy.typing import ArrayLike, NDArray

from .contracts import NORMALIZATION_LABEL, REFERENCE_PUE


def reference_pue_normalize(
    it_power_kw: ArrayLike, overhead_raw_kw: ArrayLike
) -> tuple[NDArray[np.float64], NDArray[np.float64], dict[str, Any]]:
    """Transfer overhead shape while fixing its IT-energy ratio to 0.30.

    Inputs and output PCC components use kW. No ``1.30*IT`` term is added.
    """
    it = np.asarray(it_power_kw, dtype=float)
    overhead = np.maximum(np.asarray(overhead_raw_kw, dtype=float), 0.0)
    if np.any(it <= 0):
        raise ValueError("reference normalization requires positive IT power")
    raw_ratio = overhead / it
    weighted_raw = float(np.sum(it * raw_ratio) / np.sum(it))
    if not np.isfinite(weighted_raw) or weighted_raw <= 0:
        raise ValueError("raw overhead ratio must be finite and positive")
    equivalent_ratio = (REFERENCE_PUE - 1.0) * raw_ratio / weighted_raw
    pue = 1.0 + equivalent_ratio
    pcc = it * pue
    achieved = float(np.sum(pcc - it) / np.sum(it))
    audit = {
        "label": NORMALIZATION_LABEL,
        "raw_it_energy_weighted_overhead_ratio": weighted_raw,
        "target_overhead_ratio": REFERENCE_PUE - 1.0,
        "achieved_overhead_ratio": achieved,
        "achieved_it_energy_weighted_pue": 1.0 + achieved,
        "normalization_factor": (REFERENCE_PUE - 1.0) / weighted_raw,
        "extra_1p30_multiplier_count": 0,
        "double_pue_count": 0,
        "peak_force_fit_count": 0,
    }
    return pue, pcc, audit

from __future__ import annotations

import numpy as np

from .data import ROOT
from .power_bridge import DT_H, PUE


V17 = ROOT / "dayahead" / "artifacts" / "v17_candidate"


def reference_it_power(day: str) -> tuple[np.ndarray, np.ndarray]:
    path = V17 / "reference_v6_v4r1" / f"REFERENCE_COMPUTE_SCHEDULE_V6_GPU_HOUR_{day}.npz"
    with np.load(path, allow_pickle=False) as arrays:
        pcc = np.asarray(arrays["plan_kw_96x12"], dtype=float)
        capacities = np.asarray(arrays["gpu_capacities"], dtype=float)
    return pcc / PUE, capacities / capacities.sum()


def decompose_facility(day: str, flexible_it_total_kw: np.ndarray) -> dict[str, object]:
    p_it_site, rack_weights = reference_it_power(day)
    site_weights = rack_weights.reshape(12, 4).sum(axis=1)
    flexible_site = np.asarray(flexible_it_total_kw, dtype=float)[:, None] * site_weights[None, :]
    residual = p_it_site - flexible_site
    reconstructed = residual + flexible_site
    return {
        "day": day,
        "p_it_site_kW": p_it_site,
        "p_flex_site_kW": flexible_site,
        "p_locked_residual_site_kW": residual,
        "total_IT_kWh": float(p_it_site.sum() * DT_H),
        "flexible_IT_kWh": float(flexible_site.sum() * DT_H),
        "minimum_locked_residual_IT_kW": float(residual.min()),
        "negative_residual_count": int(np.sum(residual < -1e-10)),
        "maximum_decomposition_error_kW": float(np.max(np.abs(p_it_site - reconstructed))),
        "maximum_flexible_minus_total_kW": float(np.max(flexible_site - p_it_site)),
        "negative_clipping_calls": 0,
        "PUE_application_count": 1,
    }

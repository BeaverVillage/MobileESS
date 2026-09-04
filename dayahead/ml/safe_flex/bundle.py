"""SAFE-Flex bundle schema validation and rejection-aware serialization helpers."""

from __future__ import annotations

import numpy as np


def validate_bundle(bundle: dict[str, object]) -> dict[str, object]:
    """Validate IT-side V5 diagnostic bundle dimensions and firewalls."""

    required = ["forecast_day", "cutoff", "timezone", "cumulative_L_safe", "cumulative_U_safe", "capacity_safe"]
    missing = [key for key in required if key not in bundle]
    lower = np.asarray(bundle.get("cumulative_L_safe", []), dtype=float)
    upper = np.asarray(bundle.get("cumulative_U_safe", []), dtype=float)
    capacity = np.asarray(bundle.get("capacity_safe", []), dtype=float)
    return {
        "missing_fields": missing,
        "L_shape": list(lower.shape), "U_shape": list(upper.shape), "capacity_shape": list(capacity.shape),
        "shape_PASS": lower.shape == (96, 6, 5) and upper.shape == (96, 6, 5) and capacity.shape == (96,),
        "finite_PASS": bool(np.isfinite(lower).all() and np.isfinite(upper).all() and np.isfinite(capacity).all()),
        "PUE_decision_fields": sum("PUE" in key.upper() for key in bundle),
        "facility_scale_decision_fields": sum("FACILITY" in key.upper() for key in bundle),
        "nonempty_PASS": bool(np.all(lower <= upper + 1e-9)) if lower.shape == upper.shape else False,
    }


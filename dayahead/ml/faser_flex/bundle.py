"""FORECAST_BUNDLE_V3 structural and mass-coherence validation."""

from __future__ import annotations

import numpy as np


def validate_forecast_bundle_v3(bundle: dict) -> list[str]:
    """Return schema failures; tensor masses are measured in GPU-h."""

    failures: list[str] = []
    if bundle.get("schema_version") != "FORECAST_BUNDLE_V3":
        failures.append("SCHEMA_VERSION")
    if bundle.get("GPU_h_facility_scale_multiplication_calls") != 0:
        failures.append("GPU_H_SCALE_CALL")
    for row in bundle.get("forecasts", []):
        values = [row["daily_mean_GPU_h"], row["daily_Q50_GPU_h"], row["daily_Q90_GPU_h"]]
        if values[1] > values[2]:
            failures.append(f"QUANTILE_CROSSING:{row['forecast_day']}")
        for label, expected in zip(("mean", "Q50", "Q90"), values):
            tensor = np.asarray(row[f"slot_tier_latency_{label}_GPU_h"], float)
            if tensor.shape != (96, 6, 5):
                failures.append(f"TENSOR_SHAPE:{row['forecast_day']}:{label}")
            if np.min(tensor) < -1e-12:
                failures.append(f"NEGATIVE_TENSOR:{row['forecast_day']}:{label}")
            if abs(float(tensor.sum()) - float(expected)) > 1e-9:
                failures.append(f"MASS_IDENTITY:{row['forecast_day']}:{label}")
    return failures

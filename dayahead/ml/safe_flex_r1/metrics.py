"""Common aggregate SAFE-Flex R1 boundary and validity metrics."""

from __future__ import annotations

import numpy as np


def aggregate_day_metrics(lower: np.ndarray, upper: np.ndarray, ref_lower: np.ndarray, ref_upper: np.ndarray) -> dict[str, float | bool]:
    """Score a 96-slot aggregate cumulative envelope for one day."""

    lower = np.asarray(lower, dtype=float)
    upper = np.asarray(upper, dtype=float)
    ref_lower = np.asarray(ref_lower, dtype=float)
    ref_upper = np.asarray(ref_upper, dtype=float)
    lower_mae = float(np.mean(np.abs(lower - ref_lower)))
    upper_mae = float(np.mean(np.abs(upper - ref_upper)))
    scale = float(max(np.mean(np.abs(ref_lower) + np.abs(ref_upper)), 1.0))
    width = np.maximum(upper - lower, 0.0)
    reference_width = np.maximum(ref_upper - ref_lower, 0.0)
    covered = bool(np.all(lower >= ref_lower - 1e-9) and np.all(upper <= ref_upper + 1e-9))
    nonempty = bool(np.all(lower <= upper + 1e-9))
    return {
        "lower_boundary_MAE_GPU_h": lower_mae,
        "upper_boundary_MAE_GPU_h": upper_mae,
        "aggregate_unmapped_boundary_score": (lower_mae + upper_mae) / scale,
        "simultaneous_inner_coverage": covered,
        "nonempty_set": nonempty,
        "safe_width_GPU_h": float(width.sum()),
        "reference_width_GPU_h": float(reference_width.sum()),
        "capture_ratio": float(width.sum() / reference_width.sum()) if covered and reference_width.sum() > 0 else 0.0,
    }


def mapped_score(unmapped_score: float | np.ndarray, mapping_factor: float) -> float | np.ndarray:
    """Map the aggregate score to the frozen V26 comparator scale."""

    return np.asarray(unmapped_score) * float(mapping_factor)


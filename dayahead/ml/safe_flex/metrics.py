"""Trajectory service-set accuracy, coverage, sharpness, and reserve metrics."""

from __future__ import annotations

import numpy as np


def envelope_metrics(lower: np.ndarray, upper: np.ndarray, ref_lower: np.ndarray, ref_upper: np.ndarray) -> dict[str, float | bool]:
    """Score one predicted inner set against one reference set."""

    lower_mae = float(np.mean(np.abs(lower - ref_lower)))
    upper_mae = float(np.mean(np.abs(upper - ref_upper)))
    # One GPU-hour is the minimum reporting scale; zero-mass reference days
    # must not create 1e9-style normalized-score explosions.
    scale = float(max(np.mean(np.abs(ref_lower) + np.abs(ref_upper)), 1.0))
    covered = bool(np.all(lower >= ref_lower - 1e-9) and np.all(upper <= ref_upper + 1e-9))
    nonempty = bool(np.all(lower <= upper + 1e-9))
    width = float(np.maximum(upper - lower, 0.0).sum())
    ref_width = float(np.maximum(ref_upper - ref_lower, 0.0).sum())
    return {
        "lower_boundary_MAE_GPU_h": lower_mae, "upper_boundary_MAE_GPU_h": upper_mae,
        "normalized_boundary_score": (lower_mae + upper_mae) / scale,
        "hausdorff_boundary_proxy_GPU_h": float(max(np.max(np.abs(lower - ref_lower)), np.max(np.abs(upper - ref_upper)))),
        "simultaneous_inner_coverage": covered, "nonempty_set": nonempty,
        "safe_width_GPU_h": width, "reference_width_GPU_h": ref_width,
        "capture_ratio": width / ref_width if covered and ref_width > 0 else 0.0,
    }

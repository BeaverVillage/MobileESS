"""Causal LightGBM authority helpers for V28."""

from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Iterable

import numpy as np


REPO = Path(__file__).resolve().parents[2]
ARTIFACTS = REPO / "dayahead" / "artifacts" / "v28_final_dayahead_actual"
MODEL_ROOT = ARTIFACTS / "V28_FINAL_LIGHTGBM_FORECAST_MODELS"
APRIL_01_TRAINING_CUTOFF = "2025-03-30"
GENERAL_TRAINING_CUTOFF = "2025-03-31"
SLOTS_PER_DAY = 96
MASS_TOLERANCE_GPU_H = 1e-9


def model_variant_for_day(target_day: str | date) -> str:
    value = target_day.isoformat() if isinstance(target_day, date) else str(target_day)
    return "APRIL_01_CAUSAL_FIT" if value == "2025-04-01" else "GENERAL_THROUGH_MARCH_31_FIT"


def validate_training_cutoff(target_day: str | date, latest_training_day: str | date) -> None:
    target = target_day.isoformat() if isinstance(target_day, date) else str(target_day)
    latest = latest_training_day.isoformat() if isinstance(latest_training_day, date) else str(latest_training_day)
    allowed = APRIL_01_TRAINING_CUTOFF if target == "2025-04-01" else GENERAL_TRAINING_CUTOFF
    if target.startswith(("2025-04", "2025-05")) and latest.startswith(("2025-04", "2025-05")):
        raise ValueError("V28_APRIL_MAY_TRAINING_ROW_FORBIDDEN")
    if latest > allowed:
        raise ValueError(f"V28_TRAINING_CUTOFF_VIOLATION:{target}:{latest}>{allowed}")


def disaggregate_daily_mass(daily_mass_gpu_h: float, normalized_shape: Iterable[float]) -> np.ndarray:
    """Return a nonnegative 96-slot profile whose sum is exact to 1e-9 GPU-h."""

    mass = float(daily_mass_gpu_h)
    shape = np.asarray(tuple(normalized_shape), dtype=np.float64)
    if shape.shape != (SLOTS_PER_DAY,):
        raise ValueError(f"V28_EXPECTED_96_SLOT_SHAPE:{shape.shape}")
    if mass < 0 or not np.isfinite(mass):
        raise ValueError("V28_DAILY_MASS_MUST_BE_FINITE_NONNEGATIVE")
    if np.any(~np.isfinite(shape)) or np.any(shape < 0):
        raise ValueError("V28_TEMPORAL_SHAPE_MUST_BE_FINITE_NONNEGATIVE")
    total = float(shape.sum())
    if total <= 0:
        if mass == 0:
            return np.zeros(SLOTS_PER_DAY, dtype=np.float64)
        raise ValueError("V28_NONZERO_MASS_REQUIRES_POSITIVE_TEMPORAL_SHAPE")
    result = shape / total * mass
    result[-1] += mass - float(result.sum())
    if abs(float(result.sum()) - mass) > MASS_TOLERANCE_GPU_H:
        raise RuntimeError("V28_FORECAST_MASS_CONSERVATION_FAILURE")
    return result


def engineering_site_disaggregation(profile_96: Iterable[float], weights: Iterable[float]) -> np.ndarray:
    profile = np.asarray(tuple(profile_96), dtype=np.float64)
    site_weights = np.asarray(tuple(weights), dtype=np.float64)
    if profile.shape != (96,) or site_weights.shape != (12,):
        raise ValueError("V28_SITE_DISAGGREGATION_AXIS_MISMATCH")
    if np.any(profile < 0) or np.any(site_weights < 0):
        raise ValueError("V28_SITE_DISAGGREGATION_NEGATIVE_INPUT")
    if abs(float(site_weights.sum()) - 1.0) > 1e-12:
        raise ValueError("V28_SITE_WEIGHT_SUM_NOT_ONE")
    result = profile[:, None] * site_weights[None, :]
    if np.max(np.abs(result.sum(axis=1) - profile), initial=0.0) > 1e-9:
        raise RuntimeError("V28_SITE_DISAGGREGATION_CONSERVATION_FAILURE")
    return result


def predict_daily(features: Iterable[float], target_day: str) -> dict[str, float | str]:
    """Load the pre-fitted causal variant and keep mean/Q50 semantics separate."""

    import lightgbm as lgb

    variant = model_variant_for_day(target_day)
    vector = np.asarray(tuple(features), dtype=np.float64)[None, :]
    if vector.shape != (1, 18):
        raise ValueError(f"V28_EXPECTED_18_CAUSAL_FEATURES:{vector.shape}")
    predictions = {}
    for statistic in ("mean", "q50", "q90"):
        model_path = MODEL_ROOT / f"{variant}_{statistic}.txt"
        model = lgb.Booster(model_str=model_path.read_text(encoding="utf-8"))
        predictions[statistic] = max(0.0, float(model.predict(vector)[0]))
    predictions["q90"] = max(float(predictions["q50"]), float(predictions["q90"]))
    predictions["variant"] = variant
    predictions["semantic_identity"] = hashlib.sha256(
        json.dumps(predictions, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return predictions

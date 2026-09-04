"""Pure audit helpers for V33XR3.

This module deliberately contains no optimizer, OpenDSS execution, or production
control imports.  It can analyze already-matched rows, but the repository census
for this task found no frozen Jan--Mar B1 Day-Ahead schedule authority.
"""

from __future__ import annotations

from datetime import date
from typing import Mapping

import numpy as np

from .contracts import (
    CALIBRATION_END,
    END_DAY,
    MATCH_FIELDS,
    START_DAY,
    VALIDATION_START,
)


def _day(value: object) -> date:
    return date.fromisoformat(str(value))


def validate_janmar_day(value: object) -> date:
    """Return a valid Jan--Mar 2025 day; reject every other date."""
    parsed = _day(value)
    if not START_DAY <= parsed <= END_DAY:
        raise ValueError("V33XR3_DATE_OUTSIDE_JANMAR_2025")
    return parsed


def split_population(value: object) -> str:
    """Use the fixed, non-random Jan--Feb calibration / March validation split."""
    parsed = validate_janmar_day(value)
    if parsed <= CALIBRATION_END:
        return "CALIBRATION_JANFEB"
    if parsed >= VALIDATION_START:
        return "VALIDATION_MARCH"
    raise AssertionError("unreachable date split")


def validate_exact_match(planning: Mapping[str, object], fresh: Mapping[str, object]) -> None:
    """Fail closed unless both records describe the exact same Day-Ahead row."""
    if planning.get("namespace") != "DAYAHEAD" or fresh.get("namespace") != "DAYAHEAD":
        raise ValueError("V33XR3_DAYAHEAD_ONLY")
    validate_janmar_day(planning.get("day"))
    validate_janmar_day(fresh.get("day"))
    missing = [field for field in MATCH_FIELDS if field not in planning or field not in fresh]
    if missing:
        raise ValueError(f"V33XR3_MATCH_AUTHORITY_MISSING:{','.join(missing)}")
    mismatched = [field for field in MATCH_FIELDS if planning[field] != fresh[field]]
    if mismatched:
        raise ValueError(f"V33XR3_EXACT_MATCH_FAIL:{','.join(mismatched)}")


def residual_components(v_plan: object, v_fresh: object) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return signed, upper-dangerous, and lower-dangerous voltage residuals."""
    plan = np.asarray(v_plan, dtype=float)
    fresh = np.asarray(v_fresh, dtype=float)
    if plan.shape != fresh.shape:
        raise ValueError("V33XR3_VOLTAGE_SHAPE_MISMATCH")
    signed = fresh - plan
    return signed, np.maximum(0.0, signed), np.maximum(0.0, -signed)

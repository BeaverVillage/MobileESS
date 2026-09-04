"""Canonical fixed-AEST 15-minute time contract."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Iterable

import numpy as np


FIXED_AEST = timezone(timedelta(hours=10), name="FIXED_AEST_UTC_PLUS_10")
RESOLUTION_MINUTES = 15
SLOTS_PER_DAY = 96
DT_HOURS = 0.25


def canonical_axis(day: str | date) -> tuple[datetime, ...]:
    operating_day = date.fromisoformat(day) if isinstance(day, str) else day
    start = datetime.combine(operating_day, time.min, tzinfo=FIXED_AEST)
    return tuple(start + timedelta(minutes=RESOLUTION_MINUTES * slot) for slot in range(SLOTS_PER_DAY))


def dayahead_cutoff(day: str | date) -> datetime:
    operating_day = date.fromisoformat(day) if isinstance(day, str) else day
    return datetime.combine(operating_day - timedelta(days=1), time(18), tzinfo=FIXED_AEST)


def aggregate_interval_average_power(
    power: Iterable[float],
    *,
    source_resolution_minutes: int,
) -> np.ndarray:
    """Aggregate regular interval-average power to 96 energy-conserving slots."""

    if source_resolution_minutes <= 0 or RESOLUTION_MINUTES % source_resolution_minutes:
        raise ValueError("V28_SOURCE_RESOLUTION_MUST_DIVIDE_15_MINUTES")
    values = np.asarray(tuple(power), dtype=np.float64)
    expected = 24 * 60 // source_resolution_minutes
    if values.shape != (expected,) or np.any(~np.isfinite(values)):
        raise ValueError(f"V28_SOURCE_POWER_AXIS_INVALID:{values.shape}:{expected}")
    group = RESOLUTION_MINUTES // source_resolution_minutes
    result = values.reshape(SLOTS_PER_DAY, group).mean(axis=1)
    source_energy = float(values.sum() * source_resolution_minutes / 60.0)
    result_energy = float(result.sum() * DT_HOURS)
    if abs(source_energy - result_energy) > 1e-9 * max(1.0, abs(source_energy)):
        raise RuntimeError("V28_15MIN_ENERGY_CONSERVATION_FAILURE")
    return result

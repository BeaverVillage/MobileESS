"""Causal V23M event samples and exactly mass-coherent cohort targets."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from dayahead.ml.c_mass_tpp.data import AEST
from .contracts import LATENCY_CLASSES, POWER_TIERS, PRODUCTION_CUTOFF_HOUR_AEST


@dataclass(frozen=True)
class CohortTarget:
    """One submission-day target in GPU-h with coherent hourly and 15-min arrays."""

    date: str
    service_mass_GPU_h: float
    hourly_GPU_h: np.ndarray
    slot_15min_GPU_h: np.ndarray


def production_cutoff(target_day: str) -> pd.Timestamp:
    """Return D-1 18:00 AEST for a D-day target."""

    day = pd.Timestamp(target_day, tz=AEST)
    return day - pd.Timedelta(hours=24 - PRODUCTION_CUTOFF_HOUR_AEST)


def causal_history(events: pd.DataFrame, target_day: str, lookback_days: int = 28) -> pd.DataFrame:
    """Select request/submission events causally available before production cutoff."""

    cutoff = production_cutoff(target_day)
    return events.loc[
        events["submit_AEST"].lt(cutoff)
        & events["submit_AEST"].ge(cutoff - pd.Timedelta(days=lookback_days))
    ].copy()


def build_cohort_target(target_jobs: pd.DataFrame, target_day: str) -> CohortTarget:
    """Aggregate submission-day service mass into [24,6,5] and [96,6,5] GPU-h."""

    jobs = target_jobs.loc[target_jobs["target_day"].eq(target_day)]
    hourly = np.zeros((24, len(POWER_TIERS), len(LATENCY_CLASSES)), dtype=np.float64)
    slots = np.zeros((96, len(POWER_TIERS), len(LATENCY_CLASSES)), dtype=np.float64)
    for row in jobs.itertuples(index=False):
        hour = int(row.submit_AEST.hour)
        slot = hour * 4 + int(row.submit_AEST.minute // 15)
        tier = POWER_TIERS.index(str(row.tier))
        latency = LATENCY_CLASSES.index(str(row.latency))
        mass = float(row.service_GPU_h)
        hourly[hour, tier, latency] += mass
        slots[slot, tier, latency] += mass
    total = float(jobs["service_GPU_h"].sum())
    if abs(float(hourly.sum()) - total) > 1e-9:
        raise RuntimeError(f"V23M_HOURLY_MASS_IDENTITY:{target_day}")
    if abs(float(slots.sum()) - total) > 1e-9:
        raise RuntimeError(f"V23M_SLOT_MASS_IDENTITY:{target_day}")
    return CohortTarget(target_day, total, hourly, slots)


def cutoff_augmented_sample_keys(target_days: list[str]) -> list[tuple[str, int]]:
    """Return four causal cutoff keys per day; grouping remains by target calendar day."""

    return [(day, hour) for day in target_days for hour in (0, 6, 12, 18)]

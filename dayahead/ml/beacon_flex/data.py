"""March-only V25M causal daily data and target access."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from dayahead.ml.c_mass_tpp.data import build_daily_samples
from dayahead.ml.faser_flex.data import load_training_authority


@dataclass(frozen=True)
class BeaconTrainingData:
    """March-only daily samples and target values in GPU-h."""

    samples: list
    dates: np.ndarray
    actual_GPU_h: np.ndarray
    macro_features: np.ndarray
    authority: object


def load_beacon_training_data() -> BeaconTrainingData:
    """Load causal request history and targets through 2025-03-31; April remains closed."""

    authority = load_training_authority()
    samples = build_daily_samples(
        authority.events_with_history, authority.flexible_targets, "2024-08-19", "2025-04-01"
    )
    dates = np.asarray([sample.date for sample in samples])
    actual = np.asarray([sample.daily_mass_GPU_h for sample in samples], float)
    macro = np.stack([sample.macro_features for sample in samples])
    return BeaconTrainingData(samples, dates, actual, macro, authority)


def production_cutoff(date: str) -> pd.Timestamp:
    """Return D-1 18:00 in the repository's Australia/Melbourne wall-clock authority."""

    return pd.Timestamp(date, tz="Australia/Melbourne") - pd.Timedelta(hours=6)


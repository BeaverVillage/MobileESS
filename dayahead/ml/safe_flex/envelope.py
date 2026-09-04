"""Reference and forecast cumulative SAFE-Flex envelope construction."""

from __future__ import annotations

import numpy as np
import pandas as pd

from dayahead.ml.c_mass_tpp.data import AEST
from dayahead.ml.safe_flex.observable_share import service_overlap_GPU_h
from dayahead.ml.safe_flex.service_set import cumulative_bounds
from dayahead.ml.safe_flex.state_reconstruction import cutoff_for_day


def reference_arrival_tensor(jobs: pd.DataFrame, day: pd.Timestamp | str) -> np.ndarray:
    """Build realized schedulable K-pending/G/N arrival tensor in GPU-hours.

    Actual event values are reference labels only. Running K work is excluded
    from flexible service and remains locked.
    """

    target = pd.Timestamp(day)
    start = target.tz_localize(AEST) if target.tzinfo is None else target.tz_convert(AEST)
    start = start.normalize(); end = start + pd.Timedelta(days=1); cutoff = cutoff_for_day(target)
    overlap = service_overlap_GPU_h(jobs, target)
    submit = jobs.submit_time
    k_pending = submit.le(cutoff).to_numpy() & jobs.start_time.gt(cutoff).to_numpy()
    gap = submit.gt(cutoff).to_numpy() & submit.lt(start).to_numpy()
    new = submit.ge(start).to_numpy() & submit.lt(end).to_numpy()
    selected = (overlap > 0) & (k_pending | gap | new)
    tensor = np.zeros((96, 6, 5), dtype=float)
    indices = np.flatnonzero(selected)
    for index in indices:
        if k_pending[index] or gap[index]:
            slot = 0
        else:
            timestamp = submit.iloc[index].tz_convert(AEST)
            slot = min(95, timestamp.hour * 4 + timestamp.minute // 15)
        tensor[slot, int(jobs.tier_index.iloc[index]), int(jobs.latency_index.iloc[index])] += overlap[index]
    return tensor


def inner_envelope_from_mass(shape: np.ndarray, q10_GPU_h: float, q90_GPU_h: float) -> tuple[np.ndarray, np.ndarray]:
    """Construct raw inner-set L/U from lower/upper workload mass quantiles."""

    low_arrival = max(float(q10_GPU_h), 0.0) * shape
    high_arrival = max(float(q90_GPU_h), max(float(q10_GPU_h), 0.0)) * shape
    lower, _ = cumulative_bounds(high_arrival)
    _, upper = cumulative_bounds(low_arrival)
    return lower, upper


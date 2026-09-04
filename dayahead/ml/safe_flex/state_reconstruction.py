"""Causal replay of event-censored Kestrel job state at D-1 18:00 AEST."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from dayahead.ml.c_mass_tpp.data import AEST
from dayahead.ml.safe_flex.contracts import STATE_LABEL


@dataclass(frozen=True)
class ReconstructedState:
    """Aggregate state counts at one cutoff; counts are jobs, not GPU-hours.

    Causal boundary: only whether SUBMIT/START/END events have occurred by the
    cutoff is exposed. Numeric timestamps after the cutoff are never returned.
    Source authority: immutable Kestrel accounting-event fields.
    Engineering assumption: this is not an exact historical scheduler snapshot.
    """

    target_day: str
    cutoff_AEST: str
    visible_submitted_jobs: int
    visible_running_jobs: int
    visible_pending_jobs: int
    visible_done_jobs: int
    unsupported_state_count: int
    ambiguous_state_count: int
    source_valid_state_fraction: float


def cutoff_for_day(day: pd.Timestamp | str) -> pd.Timestamp:
    """Return D-1 18:00 in fixed AEST (UTC+10), with units of wall-clock time."""

    target = pd.Timestamp(day)
    if target.tzinfo is None:
        target = target.tz_localize(AEST)
    else:
        target = target.tz_convert(AEST)
    return target.normalize() - pd.Timedelta(hours=6)


def reconstruct_at_cutoff(events: pd.DataFrame, day: pd.Timestamp | str) -> ReconstructedState:
    """Replay event occurrence flags without exposing future timestamp values.

    ``events`` must already satisfy the source-valid submission/request contract.
    Comparisons only establish whether an event has occurred; no future numeric
    START/END value is emitted or used as a feature.
    """

    cutoff = cutoff_for_day(day)
    submitted = events["submit_time"].notna() & events["submit_time"].le(cutoff)
    visible = events.loc[submitted]
    start_seen = visible["start_time"].notna() & visible["start_time"].le(cutoff)
    end_seen = visible["end_time"].notna() & visible["end_time"].le(cutoff)
    ambiguous = end_seen & ~start_seen
    done = end_seen & start_seen
    running = start_seen & ~end_seen
    pending = ~start_seen
    unsupported = np.zeros(len(visible), dtype=bool)
    denominator = len(visible)
    supported = denominator - int(unsupported.sum()) - int(ambiguous.sum())
    target = pd.Timestamp(day).strftime("%Y-%m-%d")
    return ReconstructedState(
        target_day=target,
        cutoff_AEST=cutoff.isoformat(),
        visible_submitted_jobs=int(denominator),
        visible_running_jobs=int(running.sum()),
        visible_pending_jobs=int((pending & ~ambiguous).sum()),
        visible_done_jobs=int(done.sum()),
        unsupported_state_count=int(unsupported.sum()),
        ambiguous_state_count=int(ambiguous.sum()),
        source_valid_state_fraction=float(supported / denominator) if denominator else 1.0,
    )


def reconstruction_audit(events: pd.DataFrame, start: str, end_inclusive: str) -> pd.DataFrame:
    """Build deterministic daily aggregate replay audit (job-count units)."""

    days = pd.date_range(start, end_inclusive, freq="D")
    return pd.DataFrame([reconstruct_at_cutoff(events, day).__dict__ for day in days])


STATE_AUTHORITY_LABEL = STATE_LABEL


"""Causal Kestrel data access for V24M FASER-Flex."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from dayahead.ml.c_mass_tpp.data import (
    AEST,
    conflict_ids,
    load_h100_source,
    semantic_flexible_targets,
    source_valid_input_events,
)

from .contracts import TRAIN_END_EXCLUSIVE, TRAIN_START


@dataclass(frozen=True)
class TrainingAuthority:
    """Training-only event and target frames plus source provenance."""

    events_with_history: pd.DataFrame
    target_window_events: pd.DataFrame
    flexible_targets: pd.DataFrame
    source: dict[str, object]
    conflict_count: int


def load_training_authority() -> TrainingAuthority:
    """Load July-2024 through March-2025 only; April is not opened."""

    raw, source = load_h100_source(min_month=202407, max_month=202503)
    if pd.api.types.is_timedelta64_dtype(raw["wallclock_req"].dtype):
        raw["wallclock_req_h"] = raw["wallclock_req"].dt.total_seconds() / 3600.0
        wallclock_contract = "ARROW_DURATION_NS_TO_PANDAS_TIMEDELTA_TO_SECONDS_TO_HOURS"
    else:
        numeric = pd.to_numeric(raw["wallclock_req"], errors="coerce")
        raw["wallclock_req_h"] = numeric / 3600.0
        wallclock_contract = "NUMERIC_SECONDS_TO_HOURS"
    events = source_valid_input_events(raw)
    start = pd.Timestamp(TRAIN_START, tz=AEST)
    end = pd.Timestamp(TRAIN_END_EXCLUSIVE, tz=AEST)
    target_events = events.loc[
        events.submit_AEST.ge(start) & events.submit_AEST.lt(end)
    ].copy()
    excluded = conflict_ids()
    flexible = semantic_flexible_targets(
        raw, TRAIN_START, TRAIN_END_EXCLUSIVE, excluded
    )
    source = {
        **source,
        "April_members_opened": 0,
        "target_month_max": 202503,
        "wallclock_arrow_type": "duration[ns]",
        "wallclock_pandas_dtype": str(raw["wallclock_req"].dtype),
        "wallclock_conversion_contract": wallclock_contract,
        "wallclock_conversion_bug_inherited_from_prior_loader": False,
    }
    return TrainingAuthority(events, target_events, flexible, source, len(excluded))


def training_dates() -> list[str]:
    """Return every target calendar day in the frozen training interval."""

    return [
        timestamp.date().isoformat()
        for timestamp in pd.date_range(
            pd.Timestamp(TRAIN_START),
            pd.Timestamp(TRAIN_END_EXCLUSIVE) - pd.Timedelta(days=1),
            freq="D",
        )
    ]

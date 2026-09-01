"""Causal strict/family motif definitions and recurrence classification."""

from __future__ import annotations

from collections import defaultdict

import pandas as pd

from dayahead.ml.c_mass_tpp.data import AEST


def strict_motif(row: pd.Series) -> tuple[str, str, str, str, str]:
    """Return the frozen strict motif key for one historical target job."""

    return (
        str(row["account_hash"]),
        str(row["partition"]),
        str(row["qos"]),
        str(row["tier"]),
        str(row["latency"]),
    )


def family_motif(row: pd.Series) -> tuple[str, str, str, str]:
    """Return the frozen family motif key for one historical target job."""

    return (
        str(row["account_hash"]),
        str(row["partition"]),
        str(row["tier"]),
        str(row["latency"]),
    )


def classify_recurrence(jobs: pd.DataFrame, lookback_days: int = 28) -> pd.DataFrame:
    """Classify future target jobs using only motif events before D-1 18:00 AEST."""

    result = jobs.copy().sort_values(["submit_AEST", "id"]).reset_index(drop=True)
    result["strict_motif"] = result.apply(strict_motif, axis=1)
    result["family_motif"] = result.apply(family_motif, axis=1)
    strict_history: dict[tuple[str, ...], list[pd.Timestamp]] = defaultdict(list)
    family_history: dict[tuple[str, ...], list[pd.Timestamp]] = defaultdict(list)
    labels: list[str] = []
    for row in result.itertuples(index=False):
        cutoff = pd.Timestamp(row.target_day, tz=AEST) - pd.Timedelta(hours=6)
        lower = cutoff - pd.Timedelta(days=lookback_days)
        strict_seen = any(lower <= time < cutoff for time in strict_history[row.strict_motif])
        family_seen = any(lower <= time < cutoff for time in family_history[row.family_motif])
        labels.append(
            "STRICT_RECURRENT"
            if strict_seen
            else "FAMILY_RECURRENT"
            if family_seen
            else "INNOVATION"
        )
        strict_history[row.strict_motif].append(row.submit_AEST)
        family_history[row.family_motif].append(row.submit_AEST)
    result["recurrence_class"] = labels
    return result

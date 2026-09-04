"""Causal V29 D-day initial backlog materialization."""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np

from dayahead.v28r2.authority import COHORT_IDS
from .authority import require_carryin_authority


def carryin_by_cohort(repo: Path, day: str) -> np.ndarray:
    require_carryin_authority(repo)
    path = repo / "dayahead/artifacts/v29_grid_responsive_aidc/V29_CARRYIN_BY_DAY_COHORT.csv"
    values = {cohort: 0.0 for cohort in COHORT_IDS}
    with path.open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            if row["day"] == day:
                values[row["cohort_id"]] += float(row["D_day_carryin_nodeh"])
    result = np.asarray([values[cohort] for cohort in COHORT_IDS], dtype=float)
    if np.any(result < 0) or not np.isfinite(result).all():
        raise RuntimeError("V29_CARRYIN_VECTOR_INVALID")
    return result

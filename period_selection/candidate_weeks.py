"""Generate complete observed Monday-to-Monday weeks with 48-hour burn-in."""

from __future__ import annotations

from datetime import timedelta

import pandas as pd

from period_selection import BURN_IN_STEPS, STEPS_PER_WEEK
from period_selection.feature_builder import validate_feature_table


SEASON_ORDER = ("summer", "autumn", "winter", "spring")


def southern_season(month: int) -> str:
    if month in (12, 1, 2):
        return "summer"
    if month in (3, 4, 5):
        return "autumn"
    if month in (6, 7, 8):
        return "winter"
    return "spring"


def generate_candidate_weeks(features: pd.DataFrame) -> pd.DataFrame:
    validate_feature_table(features)
    ts = pd.DatetimeIndex(features["timestamp_aest"])
    first = ts[0]
    last_exclusive = ts[-1] + timedelta(minutes=5)
    monday = first.normalize() + pd.offsets.Week(weekday=0)
    rows = []
    while monday + timedelta(days=7) <= last_exclusive:
        burn = monday - timedelta(hours=48)
        if burn >= first:
            start_index = int(ts.searchsorted(monday))
            burn_index = int(ts.searchsorted(burn))
            if start_index - burn_index != BURN_IN_STEPS:
                raise ValueError("candidate burn-in is not 576 steps")
            if int(ts.searchsorted(monday + timedelta(days=7))) - start_index != STEPS_PER_WEEK:
                raise ValueError("candidate week is not 2016 steps")
            rows.append({
                "candidate_id": f"W{len(rows)+1:02d}_{monday.date().isoformat()}",
                "season": southern_season(monday.month),
                "week_start_aest": monday.isoformat(),
                "week_end_exclusive_aest": (monday + timedelta(days=7)).isoformat(),
                "burn_in_start_aest": burn.isoformat(),
                "burn_in_end_exclusive_aest": monday.isoformat(),
                "start_index": start_index,
                "end_index_exclusive": start_index + STEPS_PER_WEEK,
                "burn_in_start_index": burn_index,
                "week_steps": STEPS_PER_WEEK,
                "burn_in_steps": BURN_IN_STEPS,
            })
        monday += timedelta(days=7)
    result = pd.DataFrame(rows)
    if result.empty or set(result["season"]) != set(SEASON_ORDER):
        raise ValueError("candidate calendar does not cover all four seasons")
    return result

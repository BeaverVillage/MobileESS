"""V29 fixed-schedule Actual binding with causal initial backlog."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping, Sequence

from dayahead.v28r2.actual_replay import replay_actual_case
from dayahead.v28r2.workload_replay import ActualWorkload
from .carryin import carryin_by_cohort


def replay_actual_case_v29(
    repo: Path, day: str, schedule_payload: Mapping[str, object],
    actual: ActualWorkload, mobility_records: Sequence[Mapping[str, object]],
):
    return replay_actual_case(
        repo, day, schedule_payload, actual, mobility_records,
        initial_backlog_nodeh=carryin_by_cohort(repo, day),
    )

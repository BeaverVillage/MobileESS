"""Historical Kestrel source-capacity authority reader."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


AUTHORITY_RELATIVE_PATH = Path(
    "dayahead/artifacts/v18r1_aidc_physical_coherence_repair/"
    "V18R1_KESTREL_CAPACITY_TIMELINE_AUTHORITY.json"
)


def read_observed_capacity_timeline(repo: Path) -> pd.DataFrame:
    """Read monthly observed-use lower bounds in nodes and GPUs.

    Units: nodes and H100 GPUs (four GPUs per observed H100 node).
    Causal/source boundary: values are read directly from the frozen V18R1
    authority. They are explicitly not promoted to installed capacity.
    Engineering assumption: four GPUs per H100 node is the official node layout.
    """

    path = repo / AUTHORITY_RELATIVE_PATH
    payload = json.loads(path.read_text(encoding="utf-8"))
    monthly = payload["raw_nodelist_observation"]["monthly"]
    rows = []
    for period, record in monthly.items():
        nodes = int(record["distinct_H100_nodelist_nodes"])
        rows.append(
            {
                "month": period,
                "C_src_nodes": nodes,
                "GPUs_per_node": 4,
                "C_src_GPU": 4 * nodes,
                "boundary": "OBSERVED_USE_LOWER_BOUND_NOT_INSTALLED_CAPACITY",
                "authority": "V18R1_FROZEN_RAW_NODELIST_OBSERVATION",
            }
        )
    return pd.DataFrame(rows).sort_values("month").reset_index(drop=True)


def capacity_for_day(timeline: pd.DataFrame, day: pd.Timestamp | str) -> int:
    """Return source-observed GPU capacity for the day's calendar month."""

    month = pd.Timestamp(day).strftime("%Y-%m")
    selected = timeline.loc[timeline["month"].eq(month), "C_src_GPU"]
    if len(selected) != 1:
        raise KeyError(f"V26M_CAPACITY_MONTH_UNAVAILABLE:{month}")
    return int(selected.iloc[0])


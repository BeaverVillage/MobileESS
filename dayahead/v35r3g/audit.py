"""Pure helpers and bounded accumulators for V35R3G."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd


def sha256_file(path: Path, chunk_size: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def write_csv(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    frame = pd.DataFrame(list(rows))
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, encoding="utf-8", lineterminator="\n")


def h100_partition(value: object, prefix: str = "gpu-h100") -> bool:
    if value is None or pd.isna(value):
        return False
    return any(token.strip().casefold().startswith(prefix) for token in str(value).split(","))


def list_has_values(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, (list, tuple, set, np.ndarray)):
        return len(value) > 0
    try:
        if pd.isna(value):
            return False
    except (TypeError, ValueError):
        pass
    return str(value).strip().casefold() not in {"", "[]", "{}", "none", "nan", "null"}


def sharing_classification(frame: pd.DataFrame) -> pd.Series:
    count = pd.to_numeric(frame["shared_job_count"], errors="coerce")
    nodes = frame["nodes_shared"].map(list_has_values)
    jobs = frame["jobs_shared"].map(list_has_values)
    shared = count.gt(0) | nodes | jobs
    no_share = count.isna() & ~nodes & ~jobs
    result = pd.Series("SHARING_UNKNOWN", index=frame.index, dtype="string")
    result.loc[shared] = "SHARED_CONFIRMED"
    result.loc[no_share] = "EXCLUSIVE_CONFIRMED"
    return result


def spatial_classification(frame: pd.DataFrame, h100: pd.Series) -> pd.Series:
    sharing = sharing_classification(frame)
    nodes_req = pd.to_numeric(frame["nodes_req"], errors="coerce")
    nodes_used = pd.to_numeric(frame["nodes_used"], errors="coerce")
    gpu_nodes = pd.to_numeric(frame["gpu_nodes_occupied"], errors="coerce")
    gpus = pd.to_numeric(frame["gpus_requested"], errors="coerce")
    allocated = (
        nodes_req.gt(0)
        & nodes_used.gt(0)
        & nodes_req.eq(nodes_used)
        & gpu_nodes.eq(nodes_used)
    )
    full = allocated & gpus.eq(4 * nodes_used)
    partial = allocated & gpus.gt(0) & gpus.lt(4 * nodes_used)
    result = pd.Series("UNKNOWN_SHARING", index=frame.index, dtype="string")
    result.loc[h100 & sharing.eq("SHARED_CONFIRMED")] = "SHARED"
    result.loc[h100 & sharing.eq("EXCLUSIVE_CONFIRMED") & full] = "FULL_NODE_EXCLUSIVE"
    result.loc[h100 & sharing.eq("EXCLUSIVE_CONFIRMED") & partial] = "PARTIAL_EXCLUSIVE"
    return result


ENERGY_PATTERN = re.compile(r"^([+-]?(?:\d+(?:\.\d*)?|\.\d+))([KMGTP]?)$", re.I)
ENERGY_MULTIPLIERS = {"": 1.0, "K": 1e3, "M": 1e6, "G": 1e9, "T": 1e12, "P": 1e15}


def parse_formatted_energy(series: pd.Series) -> pd.Series:
    def parse_one(value: object) -> float:
        if value is None:
            return math.nan
        text = str(value).strip()
        if not text or text.casefold() in {"nan", "none", "null"}:
            return math.nan
        match = ENERGY_PATTERN.fullmatch(text)
        if not match:
            return math.nan
        return float(match.group(1)) * ENERGY_MULTIPLIERS[match.group(2).upper()]

    return series.map(parse_one).astype(float)


@dataclass
class NumericFieldStats:
    non_null: int = 0
    positive: int = 0
    zero: int = 0
    negative: int = 0
    nonfinite: int = 0
    minimum: float | None = None
    maximum: float | None = None

    def update(self, values: pd.Series) -> None:
        numeric = pd.to_numeric(values, errors="coerce").to_numpy(dtype=float)
        self.non_null += int(np.count_nonzero(~np.isnan(numeric)))
        self.nonfinite += int(np.count_nonzero(np.isinf(numeric)))
        finite = numeric[np.isfinite(numeric)]
        if not finite.size:
            return
        self.positive += int(np.count_nonzero(finite > 0))
        self.zero += int(np.count_nonzero(finite == 0))
        self.negative += int(np.count_nonzero(finite < 0))
        low, high = float(finite.min()), float(finite.max())
        self.minimum = low if self.minimum is None else min(self.minimum, low)
        self.maximum = high if self.maximum is None else max(self.maximum, high)

    def as_dict(self) -> dict[str, Any]:
        return {
            "non_null_count": self.non_null,
            "positive_count": self.positive,
            "zero_count": self.zero,
            "negative_count": self.negative,
            "nonfinite_count": self.nonfinite,
            "minimum": self.minimum,
            "maximum": self.maximum,
        }


@dataclass
class CohortAccumulator:
    jobs: int = 0
    valid_runtime_jobs: int = 0
    node_hours: float = 0.0
    gpu_hours: float = 0.0
    energy_joules: float = 0.0
    positive_energy_jobs: int = 0
    first_time: pd.Timestamp | None = None
    last_time: pd.Timestamp | None = None
    dates: set[str] = field(default_factory=set)
    users: set[str] = field(default_factory=set)
    accounts: set[str] = field(default_factory=set)
    partitions: Counter[str] = field(default_factory=Counter)
    qos: Counter[str] = field(default_factory=Counter)
    resource_configurations: Counter[str] = field(default_factory=Counter)

    def update(self, frame: pd.DataFrame, mask: pd.Series) -> None:
        selected = frame.loc[mask]
        if selected.empty:
            return
        self.jobs += len(selected)
        runtime = selected["runtime_seconds"]
        valid_runtime = runtime.gt(0) & np.isfinite(runtime)
        self.valid_runtime_jobs += int(valid_runtime.sum())
        hours = runtime.where(valid_runtime, 0.0) / 3600.0
        nodes = pd.to_numeric(selected["nodes_used"], errors="coerce").fillna(0).clip(lower=0)
        gpus = pd.to_numeric(selected["gpus_requested"], errors="coerce").fillna(0).clip(lower=0)
        self.node_hours += float((hours * nodes).sum())
        self.gpu_hours += float((hours * gpus).sum())
        energy = pd.to_numeric(selected["consumed_energy_raw_joules"], errors="coerce")
        valid_energy = energy.gt(0) & np.isfinite(energy)
        self.positive_energy_jobs += int(valid_energy.sum())
        self.energy_joules += float(energy.where(valid_energy, 0.0).sum())
        times = selected["label_time"].dropna()
        if not times.empty:
            low, high = times.min(), times.max()
            self.first_time = low if self.first_time is None else min(self.first_time, low)
            self.last_time = high if self.last_time is None else max(self.last_time, high)
            self.dates.update(times.dt.date.astype(str).unique().tolist())
        self.users.update(selected["user_hash"].dropna().astype(str).unique().tolist())
        self.accounts.update(selected["account_hash"].dropna().astype(str).unique().tolist())
        self.partitions.update(selected["partition"].fillna("<NULL>").astype(str).tolist())
        self.qos.update(selected["qos"].fillna("<NULL>").astype(str).tolist())
        config = (
            "nodes="
            + selected["nodes_used"].astype("string").fillna("NA")
            + "|gpus="
            + selected["gpus_requested"].astype("string").fillna("NA")
        )
        self.resource_configurations.update(config.tolist())

    def as_dict(self) -> dict[str, Any]:
        return {
            "jobs": self.jobs,
            "valid_runtime_jobs": self.valid_runtime_jobs,
            "node_hours": self.node_hours,
            "GPU_hours": self.gpu_hours,
            "total_reported_energy_joules": self.energy_joules,
            "total_reported_energy_watt_hours": self.energy_joules / 3600.0,
            "positive_energy_jobs": self.positive_energy_jobs,
            "first_label_time_UTC": None if self.first_time is None else self.first_time.isoformat(),
            "last_label_time_UTC": None if self.last_time is None else self.last_time.isoformat(),
            "distinct_label_dates": len(self.dates),
            "distinct_users": len(self.users),
            "distinct_accounts": len(self.accounts),
            "partitions": dict(sorted(self.partitions.items())),
            "qos": dict(sorted(self.qos.items())),
            "resource_configurations": dict(sorted(self.resource_configurations.items())),
        }


def weighted_median(counter: Counter[float]) -> float | None:
    total = sum(counter.values())
    if not total:
        return None
    midpoint = (total - 1) // 2
    cumulative = 0
    lower = upper = None
    targets = {midpoint, total // 2}
    for value in sorted(counter):
        before = cumulative
        cumulative += counter[value]
        for target in targets:
            if before <= target < cumulative:
                if target == midpoint:
                    lower = value
                if target == total // 2:
                    upper = value
        if lower is not None and upper is not None:
            break
    return float((lower + upper) / 2.0)

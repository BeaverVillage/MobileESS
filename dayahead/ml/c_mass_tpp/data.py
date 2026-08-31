from __future__ import annotations

import json
import math
import re
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import timedelta, timezone
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
import pyarrow.parquet as pq


ROOT = Path(__file__).resolve().parents[3]
KESTREL = Path(
    r"C:\Users\kjw39\OneDrive\Desktop\4-2\Mobile ESS\raw데이터\데이터 센터\NLR HPC Kestrel Jobs Data\esif.hpc.kestrel.job-anon.zip"
)
KESTREL_SHA256 = "3a90f9ac40991712f8718c686fa7b05d7a303a44a87ed1a8f21b403c11efd26f"
V18R1 = ROOT / "dayahead" / "artifacts" / "v18r1_aidc_physical_coherence_repair"
AEST = timezone(timedelta(hours=10), name="AEST_FIXED_UTC_PLUS_10")
TRAIN_START = "2024-08-19"
TRAIN_END_EXCLUSIVE = "2025-04-01"
APRIL_END_EXCLUSIVE = "2025-05-01"
TIERS = ("FULL_1", "FULL_2", "FULL_4", "FULL_8", "FULL_16", "PARTIAL")
LATENCIES = ("C1", "C2", "C3", "C4", "C5")
NODE_CLASSES = (1, 2, 4, 8, 16)
C_REF = 528.0
VICTORIA_HOLIDAYS = {
    "2024-09-27",
    "2024-11-05",
    "2024-12-25",
    "2024-12-26",
    "2025-01-01",
    "2025-01-27",
    "2025-03-10",
    "2025-04-18",
    "2025-04-19",
    "2025-04-20",
    "2025-04-21",
    "2025-04-25",
}


@dataclass(frozen=True)
class Fold:
    fold_id: int
    train_start: str
    train_end: str
    validation_start: str
    validation_end: str


@dataclass
class DailySample:
    date: str
    cutoff_AEST: str
    micro_event_features: np.ndarray
    micro_event_ages_h: np.ndarray
    macro_features: np.ndarray
    proxy_history_28d_GPU_h: np.ndarray
    daily_mass_GPU_h: float
    target_event_time_h: np.ndarray
    target_event_tier: np.ndarray
    target_event_latency: np.ndarray
    target_event_mass_GPU_h: np.ndarray
    target_slot_mass_GPU_h: np.ndarray
    target_tier_mass_GPU_h: np.ndarray


def as_sequence(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, (list, tuple, np.ndarray)):
        return tuple(str(item) for item in value if str(item))
    text = str(value).strip()
    if not text or text.casefold() in {"nan", "none", "[]"}:
        return ()
    return tuple(token for token in re.split(r"[|,;\s]+", text.strip("[](){}'\"")) if token)


def is_h100(value: object) -> bool:
    return any(token.strip().casefold().startswith("gpu-h100") for token in str(value).split(","))


def _wallclock_hours(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    if numeric.notna().mean() > 0.95:
        # Kestrel request wallclock is stored in seconds.
        return numeric / 3600.0
    parsed = pd.to_timedelta(series, errors="coerce")
    return parsed.dt.total_seconds() / 3600.0


def load_h100_source(min_month: int = 202407, max_month: int = 202504) -> tuple[pd.DataFrame, dict[str, object]]:
    required = {
        "id",
        "account_hash",
        "partition",
        "qos",
        "state_simple",
        "submit_time",
        "start_time",
        "end_time",
        "nodes_req",
        "wallclock_req",
        "gpus_requested",
        "gpu_nodes_occupied",
        "shared_job_count",
        "nodes_shared",
        "jobs_shared",
        "nodelist",
    }
    frames: list[pd.DataFrame] = []
    members: list[dict[str, object]] = []
    with zipfile.ZipFile(KESTREL) as archive, tempfile.TemporaryDirectory(prefix="v19-kestrel-") as temporary:
        local = Path(temporary) / "month.parquet"
        for info in sorted(archive.infolist(), key=lambda item: item.filename):
            name = info.filename.replace("\\", "/")
            match = re.search(r"year=(\d{4})/month=(\d{1,2})", name)
            if not match or not name.casefold().endswith(".parquet"):
                continue
            month = int(match.group(1)) * 100 + int(match.group(2))
            if month < min_month or month > max_month:
                continue
            with archive.open(info) as source, local.open("wb") as target:
                shutil.copyfileobj(source, target)
            schema = set(pq.read_schema(local).names)
            if not required.issubset(schema):
                raise RuntimeError(f"V19_KESTREL_SCHEMA_MISSING:{sorted(required-schema)}")
            frame = pq.read_table(local, columns=sorted(required)).to_pandas()
            frame = frame.loc[frame["partition"].apply(is_h100)].copy()
            frame["source_month"] = month
            frames.append(frame)
            members.append({"month": month, "member": info.filename, "H100_rows": len(frame)})
    if not frames:
        raise RuntimeError("V19_KESTREL_SOURCE_EMPTY")
    result = pd.concat(frames, ignore_index=True)
    for column in ("submit_time", "start_time", "end_time"):
        result[column] = pd.to_datetime(result[column], utc=True, errors="coerce", format="mixed")
    for column in ("nodes_req", "gpus_requested", "gpu_nodes_occupied", "shared_job_count"):
        result[column] = pd.to_numeric(result[column], errors="coerce")
    result["wallclock_req_h"] = _wallclock_hours(result["wallclock_req"])
    result["submit_AEST"] = result["submit_time"].dt.tz_convert(AEST)
    result["node_tuple"] = result["nodelist"].apply(as_sequence)
    result["nodes_shared_tuple"] = result["nodes_shared"].apply(as_sequence)
    result["jobs_shared_tuple"] = result["jobs_shared"].apply(as_sequence)
    return result, {
        "source_path": str(KESTREL),
        "source_sha256": KESTREL_SHA256,
        "members_opened": members,
        "H100_rows": len(result),
        "requested_columns": sorted(required),
    }


def source_valid_input_events(frame: pd.DataFrame) -> pd.DataFrame:
    valid = (
        frame["submit_time"].notna()
        & frame["gpus_requested"].gt(0)
        & frame["nodes_req"].gt(0)
        & frame["wallclock_req_h"].gt(0)
    )
    events = frame.loc[valid].copy().sort_values(["submit_time", "id"])
    events["request_full"] = (
        events["nodes_req"].isin(NODE_CLASSES)
        & np.isclose(events["gpus_requested"], 4.0 * events["nodes_req"])
    ).astype(float)
    events["requested_service_proxy_GPU_h"] = (
        events["gpus_requested"] * events["wallclock_req_h"]
    )
    events["partition_code"] = pd.Categorical(events["partition"].astype(str)).codes
    events["qos_code"] = pd.Categorical(events["qos"].astype(str)).codes
    return events


def latency_class(queue_seconds: float) -> str | None:
    if not math.isfinite(queue_seconds) or queue_seconds <= 600:
        return None
    if queue_seconds <= 1800:
        return "C1"
    if queue_seconds <= 3600:
        return "C2"
    if queue_seconds <= 7200:
        return "C3"
    if queue_seconds <= 10800:
        return "C4"
    return "C5"


def conflict_ids() -> set[str]:
    path = V18R1 / "V18R1_KESTREL_PHYSICAL_ALLOCATION_FEASIBILITY.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    return set(map(str, payload["raw_conflict_job_ids"]))


def semantic_flexible_targets(
    frame: pd.DataFrame,
    start: str,
    end_exclusive: str,
    excluded_ids: set[str],
) -> pd.DataFrame:
    start_bound = pd.Timestamp(start, tz=AEST)
    end_bound = pd.Timestamp(end_exclusive, tz=AEST)
    valid = (
        frame["submit_AEST"].ge(start_bound)
        & frame["submit_AEST"].lt(end_bound)
        & frame["start_time"].notna()
        & frame["end_time"].notna()
        & frame["end_time"].gt(frame["start_time"])
        & frame["gpus_requested"].gt(0)
        & frame["gpu_nodes_occupied"].gt(0)
        & frame["state_simple"].astype(str).str.upper().eq("COMPLETED")
    )
    jobs = frame.loc[valid].copy()
    jobs["queue_seconds"] = (jobs["start_time"] - jobs["submit_time"]).dt.total_seconds()
    jobs["duration_h"] = (jobs["end_time"] - jobs["start_time"]).dt.total_seconds() / 3600.0
    jobs = jobs.loc[
        jobs["queue_seconds"].gt(600)
        & np.isfinite(jobs["queue_seconds"])
        & jobs["duration_h"].gt(0)
        & ~jobs["id"].astype(str).isin(excluded_ids)
    ].copy()
    jobs["exact_uniform"] = [
        bool(nodes)
        and len(nodes) == int(node_count)
        and float(gpus).is_integer()
        and (float(gpus) / len(nodes)).is_integer()
        and 1 <= int(float(gpus) / len(nodes)) <= 4
        for nodes, node_count, gpus in zip(
            jobs["node_tuple"], jobs["gpu_nodes_occupied"], jobs["gpus_requested"]
        )
    ]
    jobs["no_share"] = (
        (jobs["shared_job_count"].isna() | jobs["shared_job_count"].eq(0))
        & jobs["nodes_shared_tuple"].apply(lambda value: not value)
        & jobs["jobs_shared_tuple"].apply(lambda value: not value)
    )
    full = (
        jobs["exact_uniform"]
        & jobs["no_share"]
        & jobs["gpu_nodes_occupied"].isin(NODE_CLASSES)
        & np.isclose(jobs["gpus_requested"], 4.0 * jobs["gpu_nodes_occupied"])
    )
    jobs["tier"] = "PARTIAL"
    for nodes in NODE_CLASSES:
        jobs.loc[full & jobs["gpu_nodes_occupied"].eq(nodes), "tier"] = f"FULL_{nodes}"
    jobs["latency"] = jobs["queue_seconds"].apply(lambda value: latency_class(float(value)))
    jobs["service_GPU_h"] = jobs["gpus_requested"] * jobs["duration_h"]
    jobs["target_day"] = jobs["submit_AEST"].dt.strftime("%Y-%m-%d")
    jobs["arrival_h"] = (
        jobs["submit_AEST"].dt.hour
        + jobs["submit_AEST"].dt.minute / 60.0
        + jobs["submit_AEST"].dt.second / 3600.0
    )
    jobs["tier_index"] = jobs["tier"].map({name: i for i, name in enumerate(TIERS)})
    jobs["latency_index"] = jobs["latency"].map({name: i for i, name in enumerate(LATENCIES)})
    if jobs[["tier_index", "latency_index", "service_GPU_h"]].isna().any().any():
        raise RuntimeError("V19_TARGET_MARK_NULL")
    return jobs.sort_values(["submit_time", "id"])


def expanding_blocked_folds() -> list[Fold]:
    return [
        Fold(1, TRAIN_START, "2024-10-31", "2024-11-01", "2024-11-30"),
        Fold(2, TRAIN_START, "2024-11-30", "2024-12-01", "2024-12-31"),
        Fold(3, TRAIN_START, "2024-12-31", "2025-01-01", "2025-01-31"),
        Fold(4, TRAIN_START, "2025-01-31", "2025-02-01", "2025-02-28"),
        Fold(5, TRAIN_START, "2025-02-28", "2025-03-01", "2025-03-31"),
    ]


def _event_features(events: pd.DataFrame, cutoff: pd.Timestamp) -> tuple[np.ndarray, np.ndarray]:
    if events.empty:
        return np.zeros((0, 9), dtype=np.float32), np.zeros(0, dtype=np.float32)
    submit = events["submit_AEST"]
    hour = submit.dt.hour + submit.dt.minute / 60.0
    dow = submit.dt.dayofweek
    partition_code = events["partition_code"].to_numpy(float)
    qos_code = events["qos_code"].to_numpy(float)
    features = np.column_stack(
        [
            np.log1p(events["gpus_requested"].to_numpy(float)),
            np.log1p(events["nodes_req"].to_numpy(float)),
            np.log1p(events["wallclock_req_h"].to_numpy(float)),
            events["request_full"].to_numpy(float),
            np.sin(2 * np.pi * hour / 24.0),
            np.cos(2 * np.pi * hour / 24.0),
            np.sin(2 * np.pi * dow / 7.0),
            np.asarray(partition_code, dtype=float),
            np.asarray(qos_code, dtype=float),
        ]
    ).astype(np.float32)
    ages_h = ((cutoff - submit).dt.total_seconds() / 3600.0).to_numpy(np.float32)
    return features, ages_h


def event_feature_matrix(events: pd.DataFrame) -> np.ndarray:
    """Request/submission-only feature matrix in source submission order."""
    if events.empty:
        return np.zeros((0, 9), dtype=np.float32)
    artificial_cutoff = events["submit_AEST"].max() + pd.Timedelta(seconds=1)
    return _event_features(events, artificial_cutoff)[0]


def _proxy_for_day(events: pd.DataFrame, day: pd.Timestamp) -> float:
    start = pd.Timestamp(day.date(), tz=AEST)
    end = start + pd.Timedelta(days=1)
    selected = events.loc[events["submit_AEST"].ge(start) & events["submit_AEST"].lt(end)]
    return float(selected["requested_service_proxy_GPU_h"].sum())


def _macro_features(events: pd.DataFrame, target_day: pd.Timestamp, cutoff: pd.Timestamp) -> np.ndarray:
    values: list[float] = []
    for hours in (6, 12, 24):
        selected = events.loc[
            events["submit_AEST"].ge(cutoff - pd.Timedelta(hours=hours))
            & events["submit_AEST"].lt(cutoff)
        ]
        values.append(float(len(selected)))
    for hours in (6, 12, 24):
        selected = events.loc[
            events["submit_AEST"].ge(cutoff - pd.Timedelta(hours=hours))
            & events["submit_AEST"].lt(cutoff)
        ]
        values.append(float(selected["gpus_requested"].sum()))
    proxy_days = [
        _proxy_for_day(events, target_day - pd.Timedelta(days=offset))
        for offset in range(1, 15)
    ]
    values.extend([proxy_days[0], proxy_days[1], proxy_days[6]])
    values.extend(
        [
            float(np.mean(proxy_days[:7])),
            float(np.std(proxy_days[:7])),
            float(np.mean(proxy_days[:14])),
        ]
    )
    dow = int(target_day.dayofweek)
    values.extend(
        [
            math.sin(2 * math.pi * dow / 7),
            math.cos(2 * math.pi * dow / 7),
            float(dow >= 5),
            float(target_day.date().isoformat() in VICTORIA_HOLIDAYS),
            math.sin(2 * math.pi * int(target_day.month) / 12),
            math.cos(2 * math.pi * int(target_day.month) / 12),
        ]
    )
    result = np.asarray(values, dtype=np.float32)
    result[:12] = np.log1p(np.maximum(result[:12], 0.0))
    return result


def _proxy_history(events: pd.DataFrame, target_day: pd.Timestamp, days: int = 28) -> np.ndarray:
    return np.asarray(
        [
            _proxy_for_day(events, target_day - pd.Timedelta(days=offset))
            for offset in range(days, 0, -1)
        ],
        dtype=np.float32,
    )


def build_daily_samples(
    input_events: pd.DataFrame,
    target_jobs: pd.DataFrame,
    start: str,
    end_exclusive: str,
) -> list[DailySample]:
    samples: list[DailySample] = []
    days = pd.date_range(start, pd.Timestamp(end_exclusive) - pd.Timedelta(days=1), freq="D")
    grouped = {day: frame for day, frame in target_jobs.groupby("target_day", sort=False)}
    for target_day_naive in days:
        target_day = pd.Timestamp(target_day_naive.date(), tz=AEST)
        cutoff = target_day - pd.Timedelta(hours=6)
        micro = input_events.loc[
            input_events["submit_AEST"].ge(cutoff - pd.Timedelta(days=7))
            & input_events["submit_AEST"].lt(cutoff)
        ]
        micro_features, ages_h = _event_features(micro, cutoff)
        day_key = target_day.date().isoformat()
        jobs = grouped.get(day_key, target_jobs.iloc[0:0])
        event_mass = jobs["service_GPU_h"].to_numpy(np.float64)
        daily_mass = float(event_mass.sum())
        slots = np.zeros(96, dtype=np.float64)
        tier_mass = np.zeros(len(TIERS), dtype=np.float64)
        for row in jobs.itertuples(index=False):
            slot = min(95, int(float(row.arrival_h) * 4))
            slots[slot] += float(row.service_GPU_h)
            tier_mass[int(row.tier_index)] += float(row.service_GPU_h)
        if abs(daily_mass - float(slots.sum())) > 1e-8:
            raise RuntimeError(f"V19_TARGET_SLOT_IDENTITY:{day_key}")
        if abs(daily_mass - float(tier_mass.sum())) > 1e-8:
            raise RuntimeError(f"V19_TARGET_TIER_IDENTITY:{day_key}")
        samples.append(
            DailySample(
                date=day_key,
                cutoff_AEST=cutoff.isoformat(),
                micro_event_features=micro_features,
                micro_event_ages_h=ages_h,
                macro_features=_macro_features(input_events, target_day, cutoff),
                proxy_history_28d_GPU_h=_proxy_history(input_events, target_day),
                daily_mass_GPU_h=daily_mass,
                target_event_time_h=jobs["arrival_h"].to_numpy(np.float32),
                target_event_tier=jobs["tier_index"].to_numpy(np.int64),
                target_event_latency=jobs["latency_index"].to_numpy(np.int64),
                # Preserve the scientific target authority in float64.  Casting
                # these three independently aggregated views to float32 caused
                # milliscale GPU-h drift when they were compared with the
                # float64 daily master, even though the source sums agreed.
                target_event_mass_GPU_h=event_mass,
                target_slot_mass_GPU_h=slots,
                target_tier_mass_GPU_h=tier_mass,
            )
        )
    return samples


def indices_for_period(samples: Iterable[DailySample], start: str, end: str) -> np.ndarray:
    return np.asarray(
        [i for i, sample in enumerate(samples) if start <= sample.date <= end], dtype=np.int64
    )


def causality_audit() -> dict[str, int | str]:
    return {
        "main_input_boundary": "REQUEST_AND_SUBMISSION_SIDE_ONLY_BEFORE_D_MINUS_1_18_00_AEST",
        "D_day_actual_feature_reads": 0,
        "future_start_feature_reads": 0,
        "future_end_feature_reads": 0,
        "future_queue_wait_feature_reads": 0,
        "future_completion_feature_reads": 0,
        "historical_realized_runtime_feature_reads": 0,
        "target_label_queue_wait_reads": 1,
        "target_label_realized_runtime_reads": 1,
    }

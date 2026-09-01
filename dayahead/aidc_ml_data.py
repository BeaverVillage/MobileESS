"""April-locked V16 AIDC label and Direct96 sample construction.

Only Kestrel archive members through 2025-04 are opened.  The source ESIF
Parquet is a single combined row group, so its returned dataframe is clipped to
the frozen pre-May axis immediately and is audited by maximum returned
timestamp.  No May/June split loader exists on this execution path.
"""

from __future__ import annotations

import hashlib
import math
import re
import shutil
import tempfile
import zipfile
from dataclasses import dataclass, field
from datetime import timedelta, timezone
from pathlib import Path
from typing import Mapping, Sequence

from .aidc_power_response import KAPPA_KW_PER_ACTIVE_H100_NODE
from .authority import DEFAULT_RAW_ROOT, NLR_SOURCE_SHA256, sha256_file
from .reproduce_nlr_authority import object_empty


AEST = timezone(timedelta(hours=10), name="AEST_FIXED_UTC_PLUS_10")
AXIS_START = "2024-08-01"
AXIS_END_EXCLUSIVE = "2025-05-01"
TRAIN_START = "2024-08-19"
TRAIN_END = "2025-03-31"
VALIDATION_START = "2025-04-01"
VALIDATION_END = "2025-04-30"
NODE_CLASSES = (1, 2, 4, 8, 16)
RUNTIME_BIN_QUANTILES = (1.0 / 3.0, 2.0 / 3.0)


@dataclass
class AccessAudit:
    split_access_counts: dict[str, int] = field(
        default_factory=lambda: {
            "TRAIN_2024AUG19_2025MAR31": 0,
            "VALIDATION_2025APR": 0,
            "PRIMARY_2025MAY": 0,
            "REPLICATION_2025JUN01_25": 0,
        }
    )
    kestrel_archive_members_opened: list[str] = field(default_factory=list)
    max_kestrel_month_opened: int = 0
    esif_returned_max_timestamp: str | None = None
    esif_raw_15min_missing_count: int = 0
    esif_causal_history_imputation_count: int = 0
    d1_expost_eligibility_field_access_count: int = 0

    def record_allowed_splits(self) -> None:
        self.split_access_counts["TRAIN_2024AUG19_2025MAR31"] += 1
        self.split_access_counts["VALIDATION_2025APR"] += 1

    def validate(self) -> None:
        if self.split_access_counts["PRIMARY_2025MAY"] != 0:
            raise RuntimeError("MAY_LOADER_ACCESS_PROHIBITED")
        if self.split_access_counts["REPLICATION_2025JUN01_25"] != 0:
            raise RuntimeError("JUNE_LOADER_ACCESS_PROHIBITED")
        if self.max_kestrel_month_opened > 202504:
            raise RuntimeError("POST_APRIL_KESTREL_MEMBER_OPENED")
        if self.d1_expost_eligibility_field_access_count != 0:
            raise RuntimeError("EXPOST_D1_ELIGIBILITY_FIELD_ACCESS")

    def to_dict(self) -> dict[str, object]:
        self.validate()
        return {
            "split_access_counts": dict(self.split_access_counts),
            "kestrel_archive_member_open_count": len(self.kestrel_archive_members_opened),
            "max_kestrel_month_opened": self.max_kestrel_month_opened,
            "esif_returned_max_timestamp": self.esif_returned_max_timestamp,
            "esif_raw_15min_missing_count": self.esif_raw_15min_missing_count,
            "esif_causal_history_imputation_count": self.esif_causal_history_imputation_count,
            "esif_imputation_rule": "PAST_SAME_SLOT_MEDIAN_UP_TO_7_DAYS; TARGET_DAYS_WITH_MISSING_P_EXCLUDED",
            "may_june_loader_access_count": (
                self.split_access_counts["PRIMARY_2025MAY"]
                + self.split_access_counts["REPLICATION_2025JUN01_25"]
            ),
            "d1_expost_eligibility_field_access_count": self.d1_expost_eligibility_field_access_count,
        }


@dataclass(frozen=True)
class LabelDataset:
    timestamps: object
    values: object
    p_it_observed: object
    target_names: tuple[str, ...]
    cohort_ids: tuple[str, ...]
    runtime_bins_hours_by_node_class: Mapping[int, tuple[float, float]]
    source_paths: Mapping[str, str]
    source_sha256: Mapping[str, str]
    access_audit: Mapping[str, object]
    historical_job_counts: Mapping[str, int]


@dataclass(frozen=True)
class Direct96Samples:
    lookback: int
    feature_names: tuple[str, ...]
    target_names: tuple[str, ...]
    target_scales: object
    train_days: tuple[str, ...]
    validation_days: tuple[str, ...]
    excluded_training_target_days: tuple[str, ...]
    excluded_validation_target_days: tuple[str, ...]
    train_x: object
    train_future: object
    train_y: object
    validation_x: object
    validation_future: object
    validation_y: object


def _h100(value: object) -> bool:
    return any(token.strip().casefold().startswith("gpu-h100") for token in str(value).split(","))


def _find_exact(raw_root: Path, filename: str, expected_sha: str) -> Path:
    matches = sorted(raw_root.rglob(filename))
    exact = [path for path in matches if path.is_file() and sha256_file(path) == expected_sha]
    if not exact:
        raise FileNotFoundError(f"EXACT_RAW_SOURCE_NOT_FOUND:{filename}:{expected_sha}")
    return exact[0]


def _runtime_bins(frame: object) -> dict[int, tuple[float, float]]:
    import numpy as np

    result: dict[int, tuple[float, float]] = {}
    for nodes in NODE_CLASSES:
        values = np.asarray(frame.loc[frame["nodes"].eq(nodes), "runtime_hours"], dtype=float)
        if values.size < 3:
            raise RuntimeError(f"INSUFFICIENT_RUNTIME_BIN_ROWS:{nodes}")
        q1, q2 = np.quantile(values, RUNTIME_BIN_QUANTILES)
        if not math.isfinite(float(q1)) or not math.isfinite(float(q2)):
            raise RuntimeError(f"NONFINITE_RUNTIME_BIN:{nodes}")
        q2 = max(float(q2), math.nextafter(float(q1), math.inf))
        result[nodes] = (float(q1), float(q2))
    return result


def _cohort_id(nodes: int, runtime_hours: float, bins: Mapping[int, tuple[float, float]]) -> str:
    q1, q2 = bins[nodes]
    runtime_bin = 0 if runtime_hours <= q1 else 1 if runtime_hours <= q2 else 2
    return f"N{nodes:02d}_R{runtime_bin:02d}"


def _add_interval_average(
    difference: object,
    partial: object,
    *,
    start_seconds: float,
    end_seconds: float,
    magnitude: float,
    slot_count: int,
) -> None:
    if end_seconds <= 0 or start_seconds >= slot_count * 900:
        return
    start_seconds = max(0.0, start_seconds)
    end_seconds = min(slot_count * 900.0, end_seconds)
    if end_seconds <= start_seconds:
        return
    first = int(start_seconds // 900)
    last = int(math.nextafter(end_seconds, -math.inf) // 900)
    if first == last:
        partial[first] += magnitude * (end_seconds - start_seconds) / 900.0
        return
    partial[first] += magnitude * ((first + 1) * 900.0 - start_seconds) / 900.0
    partial[last] += magnitude * (end_seconds - last * 900.0) / 900.0
    if last > first + 1:
        difference[first + 1] += magnitude
        difference[last] -= magnitude


def _load_kestrel(
    path: Path,
    timestamps: object,
    audit: AccessAudit,
) -> tuple[object, object, tuple[str, ...], dict[int, tuple[float, float]], dict[str, int]]:
    import numpy as np
    import pandas as pd
    import pyarrow.parquet as pq

    required = {
        "partition", "state_simple", "submit_time", "start_time", "end_time",
        "gpu_nodes_occupied", "gpus_requested", "shared_job_count", "nodes_shared", "jobs_shared",
    }
    retained: list[object] = []
    with zipfile.ZipFile(path) as archive, tempfile.TemporaryDirectory(prefix="aidc-g56-") as temporary:
        local = Path(temporary) / "month.parquet"
        for info in archive.infolist():
            if not info.filename.casefold().endswith(".parquet"):
                continue
            match = re.search(r"year=(\d{4})/month=(\d{1,2})", info.filename.replace("\\", "/"))
            if not match:
                continue
            month = int(match.group(1)) * 100 + int(match.group(2))
            if month < 202408 or month > 202504:
                continue
            audit.kestrel_archive_members_opened.append(info.filename)
            audit.max_kestrel_month_opened = max(audit.max_kestrel_month_opened, month)
            with archive.open(info) as source, local.open("wb") as target:
                shutil.copyfileobj(source, target)
            schema = set(pq.ParquetFile(local).schema_arrow.names)
            if not required.issubset(schema):
                raise RuntimeError(f"KESTREL_REQUIRED_SCHEMA_MISSING:{sorted(required-schema)}")
            retained.append(pq.read_table(local, columns=sorted(required)).to_pandas())
    frame = pd.concat(retained, ignore_index=True)
    submit = pd.to_datetime(frame["submit_time"], utc=True, errors="coerce", format="mixed")
    start = pd.to_datetime(frame["start_time"], utc=True, errors="coerce", format="mixed")
    end = pd.to_datetime(frame["end_time"], utc=True, errors="coerce", format="mixed")
    nodes = pd.to_numeric(frame["gpu_nodes_occupied"], errors="coerce")
    gpus = pd.to_numeric(frame["gpus_requested"], errors="coerce")
    sharing = pd.to_numeric(frame["shared_job_count"], errors="coerce")
    valid = (
        frame["partition"].apply(_h100)
        & frame["state_simple"].astype(str).str.upper().eq("COMPLETED")
        & submit.notna() & start.notna() & end.notna() & end.gt(start)
        & nodes.gt(0) & gpus.gt(0)
    )
    jobs = frame.loc[valid, ["nodes_shared", "jobs_shared"]].copy()
    jobs["submit_utc"] = submit[valid]
    jobs["start_utc"] = start[valid]
    jobs["end_utc"] = end[valid]
    jobs["nodes"] = nodes[valid]
    jobs["gpus"] = gpus[valid]
    jobs["share"] = sharing[valid]
    jobs["runtime_hours"] = (jobs["end_utc"] - jobs["start_utc"]).dt.total_seconds() / 3600.0
    no_share = (
        (jobs["share"].isna() | jobs["share"].eq(0))
        & jobs["nodes_shared"].apply(object_empty)
        & jobs["jobs_shared"].apply(object_empty)
    )
    eligible = (
        jobs["nodes"].isin(NODE_CLASSES)
        & np.isclose(jobs["gpus"], 4.0 * jobs["nodes"])
        & jobs["runtime_hours"].gt(0)
        & no_share
    )
    flexible = jobs.loc[eligible].copy()
    development_end_utc = pd.Timestamp(AXIS_END_EXCLUSIVE, tz=AEST).tz_convert("UTC")
    development_start_utc = pd.Timestamp(TRAIN_START, tz=AEST).tz_convert("UTC")
    bin_rows = flexible[
        flexible["submit_utc"].ge(development_start_utc)
        & flexible["submit_utc"].lt(development_end_utc)
    ]
    bins = _runtime_bins(bin_rows)
    cohort_ids = tuple(f"N{nodes:02d}_R{runtime_bin:02d}" for nodes in NODE_CLASSES for runtime_bin in range(3))
    cohort_index = {value: index for index, value in enumerate(cohort_ids)}

    slot_count = len(timestamps)
    axis_start_utc = timestamps[0].tz_convert("UTC")
    origin = axis_start_utc.timestamp()
    difference = np.zeros(slot_count + 1, dtype=np.float64)
    partial = np.zeros(slot_count, dtype=np.float64)
    for row in jobs.itertuples(index=False):
        _add_interval_average(
            difference,
            partial,
            start_seconds=row.start_utc.timestamp() - origin,
            end_seconds=row.end_utc.timestamp() - origin,
            magnitude=float(row.gpus) / 4.0,
            slot_count=slot_count,
        )
    gpu_nodes = partial + np.cumsum(difference[:-1])

    workload = np.zeros((slot_count, len(cohort_ids)), dtype=np.float64)
    for row in flexible.itertuples(index=False):
        slot = int((row.submit_utc.timestamp() - origin) // 900)
        if 0 <= slot < slot_count:
            nodes_i = int(row.nodes)
            cohort = _cohort_id(nodes_i, float(row.runtime_hours), bins)
            workload[slot, cohort_index[cohort]] += nodes_i * float(row.runtime_hours)
    counts = {
        "valid_h100_completed_jobs_through_april_archive_members": int(len(jobs)),
        "eligible_flexible_jobs_through_april_archive_members": int(len(flexible)),
        "runtime_bin_development_plus_april_jobs": int(len(bin_rows)),
    }
    return gpu_nodes, workload, cohort_ids, bins, counts


def _load_esif(path: Path, timestamps: object, audit: AccessAudit) -> tuple[object, object]:
    import numpy as np
    import pandas as pd
    import pyarrow.parquet as pq

    frame = pq.read_table(path, columns=["ts", "it_power_kw"]).to_pandas()
    ts = pd.to_datetime(frame["ts"], errors="coerce")
    if getattr(ts.dt, "tz", None) is None:
        ts = ts.dt.tz_localize("UTC")
    else:
        ts = ts.dt.tz_convert("UTC")
    values = pd.to_numeric(frame["it_power_kw"], errors="coerce")
    start_utc = timestamps[0].tz_convert("UTC")
    end_utc = (timestamps[-1] + pd.Timedelta(minutes=15)).tz_convert("UTC")
    keep = ts.ge(start_utc) & ts.lt(end_utc) & values.notna() & np.isfinite(values) & values.ge(0)
    clipped = pd.Series(np.asarray(values[keep], dtype=float), index=pd.DatetimeIndex(ts[keep]))
    audit.esif_returned_max_timestamp = clipped.index.max().tz_convert(AEST).isoformat()
    quarter_hour = clipped.groupby(clipped.index.floor("15min")).mean()
    quarter_hour.index = quarter_hour.index.tz_convert(AEST)
    result = quarter_hour.reindex(timestamps)
    observed = np.asarray(result.notna(), dtype=bool)
    audit.esif_raw_15min_missing_count = int((~observed).sum())
    filled = np.asarray(result, dtype=np.float64).copy()
    for index in np.flatnonzero(~observed):
        same_slot = [
            filled[index - 96 * lag]
            for lag in range(1, 8)
            if index - 96 * lag >= 0 and observed[index - 96 * lag]
        ]
        if same_slot:
            filled[index] = float(np.median(same_slot))
        else:
            prior = np.flatnonzero(observed[:index])
            if not len(prior):
                raise RuntimeError(f"ESIF_CAUSAL_IMPUTATION_NO_PRIOR:{index}")
            filled[index] = float(filled[prior[-1]])
    audit.esif_causal_history_imputation_count = int((~observed).sum())
    if not np.isfinite(filled).all():
        raise RuntimeError("ESIF_CAUSAL_HISTORY_IMPUTATION_NONFINITE")
    return filled, observed


def load_april_locked_labels(raw_root: Path = DEFAULT_RAW_ROOT) -> LabelDataset:
    import numpy as np
    import pandas as pd

    audit = AccessAudit()
    audit.record_allowed_splits()
    timestamps = pd.date_range(
        pd.Timestamp(AXIS_START, tz=AEST),
        pd.Timestamp(AXIS_END_EXCLUSIVE, tz=AEST),
        freq="15min",
        inclusive="left",
    )
    esif = _find_exact(raw_root, "esif.influx.buildingData.PUE.combined.parquet", NLR_SOURCE_SHA256["esif_parquet"])
    kestrel = _find_exact(raw_root, "esif.hpc.kestrel.job-anon.zip", NLR_SOURCE_SHA256["kestrel_jobs_zip"])
    p_it, p_it_observed = _load_esif(esif, timestamps, audit)
    gpu_nodes, workload, cohort_ids, bins, job_counts = _load_kestrel(kestrel, timestamps, audit)
    values = np.column_stack((p_it, gpu_nodes, workload))
    if values.shape != (len(timestamps), 2 + len(cohort_ids)) or not np.isfinite(values).all():
        raise RuntimeError("AIDC_LABEL_MATRIX_INVALID")
    if np.any(values < 0):
        raise RuntimeError("AIDC_LABEL_MATRIX_NEGATIVE")
    audit.validate()
    target_names = ("P_IT_REF", "G_REF", *(f"W_F::{cohort}" for cohort in cohort_ids))
    return LabelDataset(
        timestamps=timestamps,
        values=values,
        p_it_observed=p_it_observed,
        target_names=tuple(target_names),
        cohort_ids=cohort_ids,
        runtime_bins_hours_by_node_class=bins,
        source_paths={"esif_parquet": str(esif.resolve()), "kestrel_jobs_zip": str(kestrel.resolve())},
        source_sha256={"esif_parquet": sha256_file(esif), "kestrel_jobs_zip": sha256_file(kestrel)},
        access_audit=audit.to_dict(),
        historical_job_counts=job_counts,
    )


def calendar_features(timestamps: object) -> object:
    import numpy as np

    slot = np.asarray(timestamps.hour * 4 + timestamps.minute // 15, dtype=float)
    dow = np.asarray(timestamps.dayofweek, dtype=float)
    doy = np.asarray(timestamps.dayofyear, dtype=float)
    return np.column_stack(
        (
            np.sin(2 * np.pi * slot / 96.0),
            np.cos(2 * np.pi * slot / 96.0),
            np.sin(2 * np.pi * dow / 7.0),
            np.cos(2 * np.pi * dow / 7.0),
            np.sin(2 * np.pi * doy / 365.25),
            np.cos(2 * np.pi * doy / 365.25),
        )
    ).astype(np.float32)


def positive_target_scales(labels: LabelDataset) -> object:
    import numpy as np
    import pandas as pd

    cutoff = pd.Timestamp("2025-04-01", tz=AEST)
    train = np.asarray(labels.values[labels.timestamps < cutoff], dtype=float)
    scales = np.ones(train.shape[1], dtype=np.float64)
    for index in range(train.shape[1]):
        positive = train[:, index][train[:, index] > 0]
        if positive.size:
            scales[index] = max(float(np.quantile(positive, 0.95)), 1e-6)
    if not np.isfinite(scales).all() or np.any(scales <= 0):
        raise RuntimeError("POSITIVE_TARGET_SCALE_INVALID")
    return scales


def build_direct96_samples(labels: LabelDataset, lookback: int, scales: object | None = None) -> Direct96Samples:
    import numpy as np
    import pandas as pd

    if lookback not in {672, 1344}:
        raise ValueError("DIRECT96_LOOKBACK_NOT_FROZEN")
    values = np.asarray(labels.values, dtype=np.float64)
    scales_array = np.asarray(positive_target_scales(labels) if scales is None else scales, dtype=np.float64)
    if scales_array.shape != (values.shape[1],) or np.any(scales_array <= 0):
        raise ValueError("TARGET_SCALE_SHAPE_OR_SIGN_INVALID")
    scaled = values / scales_array
    calendar = calendar_features(labels.timestamps)
    p_observed_feature = np.asarray(labels.p_it_observed, dtype=np.float32)[:, None]
    features = np.column_stack((scaled, p_observed_feature, calendar)).astype(np.float32)
    timestamp_to_index = {timestamp: index for index, timestamp in enumerate(labels.timestamps)}
    train_x: list[object] = []
    train_future: list[object] = []
    train_y: list[object] = []
    validation_x: list[object] = []
    validation_future: list[object] = []
    validation_y: list[object] = []
    train_days: list[str] = []
    validation_days: list[str] = []
    excluded_training_target_days: list[str] = []
    excluded_validation_target_days: list[str] = []
    for day in pd.date_range(TRAIN_START, VALIDATION_END, freq="D"):
        day_start = pd.Timestamp(day.date(), tz=AEST)
        cutoff = day_start - pd.Timedelta(hours=6)
        history_start = cutoff - pd.Timedelta(minutes=15 * lookback)
        first = timestamp_to_index.get(history_start)
        cutoff_index = timestamp_to_index.get(cutoff)
        target_first = timestamp_to_index.get(day_start)
        if first is None or cutoff_index is None or target_first is None:
            raise RuntimeError(f"DIRECT96_AXIS_LOOKUP_FAILED:{day.date()}:{lookback}")
        target_end = target_first + 96
        x = features[first:cutoff_index]
        future = calendar[target_first:target_end]
        y = scaled[target_first:target_end]
        if x.shape != (lookback, features.shape[1]) or future.shape != (96, 6) or y.shape != (96, values.shape[1]):
            raise RuntimeError("DIRECT96_SHAPE_CONTRACT_FAILED")
        target_p_observed = bool(np.asarray(labels.p_it_observed[target_first:target_end]).all())
        if day.date() <= pd.Timestamp(TRAIN_END).date():
            if not target_p_observed:
                excluded_training_target_days.append(day.date().isoformat())
                continue
            train_days.append(day.date().isoformat())
            train_x.append(x)
            train_future.append(future)
            train_y.append(y)
        else:
            if not target_p_observed:
                excluded_validation_target_days.append(day.date().isoformat())
                continue
            validation_days.append(day.date().isoformat())
            validation_x.append(x)
            validation_future.append(future)
            validation_y.append(y)
    feature_names = (
        *labels.target_names,
        "P_IT_REF_observed",
        "tod_sin", "tod_cos", "dow_sin", "dow_cos", "doy_sin", "doy_cos",
    )
    return Direct96Samples(
        lookback=lookback,
        feature_names=tuple(feature_names),
        target_names=labels.target_names,
        target_scales=scales_array,
        train_days=tuple(train_days),
        validation_days=tuple(validation_days),
        excluded_training_target_days=tuple(excluded_training_target_days),
        excluded_validation_target_days=tuple(excluded_validation_target_days),
        train_x=np.stack(train_x),
        train_future=np.stack(train_future),
        train_y=np.stack(train_y).astype(np.float32),
        validation_x=np.stack(validation_x),
        validation_future=np.stack(validation_future),
        validation_y=np.stack(validation_y).astype(np.float32),
    )


def dataset_fingerprint(labels: LabelDataset) -> str:
    import numpy as np

    digest = hashlib.sha256()
    digest.update("|".join(labels.target_names).encode("utf-8"))
    digest.update(np.asarray(labels.values, dtype="<f8").tobytes(order="C"))
    return digest.hexdigest()

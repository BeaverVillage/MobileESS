"""Source-backed, pre-April labels for the V28R2 optimizer channels.

P and G describe total reference operation.  W is deliberately narrower: it
contains only the final-re-freeze full-node controllable workload.  The loader
never opens an April, May, or June Kestrel member.
"""

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

import numpy as np
import pandas as pd

from dayahead.authority import DEFAULT_RAW_ROOT, NLR_SOURCE_SHA256, sha256_file
from dayahead.reproduce_nlr_authority import object_empty
from dayahead.v28r2.authority import COHORT_IDS, CONTROLLABLE_NODE_CLASSES


AEST = timezone(timedelta(hours=10), name="AEST_FIXED_UTC_PLUS_10")
AXIS_START = "2024-08-01"
AXIS_END_EXCLUSIVE = "2025-04-01"
TRAIN_START = "2024-08-19"


@dataclass(frozen=True)
class OptimizerLabels:
    timestamps: pd.DatetimeIndex
    p_it_kw: np.ndarray
    p_observed: np.ndarray
    g_h100_gpu: np.ndarray
    w_nodeh: np.ndarray
    cohort_ids: tuple[str, ...]
    source_paths: dict[str, str]
    source_sha256: dict[str, str]
    audit: dict[str, object]


def _find_exact(root: Path, filename: str, expected_sha256: str) -> Path:
    matches = sorted(p for p in root.rglob(filename) if p.is_file() and sha256_file(p) == expected_sha256)
    if not matches:
        raise FileNotFoundError(f"V28R2_EXACT_SOURCE_NOT_FOUND:{filename}")
    # Byte-identical mirrors are not competing authorities.  Select the stable
    # lexical first path while binding the expected content digest.
    return matches[0]


def _h100(value: object) -> bool:
    return any(token.strip().casefold().startswith("gpu-h100") for token in str(value).split(","))


def _add_interval_average(
    difference: np.ndarray,
    partial: np.ndarray,
    start_seconds: float,
    end_seconds: float,
    magnitude: float,
) -> None:
    slot_count = len(partial)
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


def _cohort_bins(repo: Path) -> dict[int, tuple[float, float]]:
    source = repo / "dayahead/artifacts/v16/AIDC_COHORT_CONTRACT.json"
    payload = json.loads(source.read_text(encoding="utf-8"))
    if tuple(payload["cohort_ids"]) != COHORT_IDS:
        raise RuntimeError("V28R2_FROZEN_COHORT_AXIS_MISMATCH")
    return {
        int(nodes): (float(values["q33_hours"]), float(values["q67_hours"]))
        for nodes, values in payload["runtime_bins_hours_by_node_class"].items()
    }


def _cohort(nodes: int, runtime_hours: float, bins: dict[int, tuple[float, float]]) -> str:
    q33, q67 = bins[nodes]
    runtime_class = 0 if runtime_hours <= q33 else 1 if runtime_hours <= q67 else 2
    return f"N{nodes:02d}_R{runtime_class:02d}"


def _load_esif(path: Path, timestamps: pd.DatetimeIndex) -> tuple[np.ndarray, np.ndarray]:
    import pyarrow.parquet as pq

    frame = pq.read_table(path, columns=["ts", "it_power_kw"]).to_pandas()
    ts = pd.to_datetime(frame["ts"], utc=True, errors="coerce", format="mixed")
    value = pd.to_numeric(frame["it_power_kw"], errors="coerce")
    start = timestamps[0].tz_convert("UTC")
    end = pd.Timestamp(AXIS_END_EXCLUSIVE, tz=AEST).tz_convert("UTC")
    keep = ts.ge(start) & ts.lt(end) & value.ge(0) & np.isfinite(value)
    series = pd.Series(np.asarray(value[keep], dtype=float), index=pd.DatetimeIndex(ts[keep]))
    quarter_hour = series.groupby(series.index.floor("15min")).mean()
    quarter_hour.index = quarter_hour.index.tz_convert(AEST)
    result = quarter_hour.reindex(timestamps)
    return np.asarray(result, dtype=float), np.asarray(result.notna(), dtype=bool)


def _load_kestrel(
    path: Path,
    timestamps: pd.DatetimeIndex,
    bins: dict[int, tuple[float, float]],
) -> tuple[np.ndarray, np.ndarray, dict[str, object]]:
    import pyarrow.parquet as pq

    columns = {
        "partition", "state_simple", "submit_time", "start_time", "end_time",
        "gpu_nodes_occupied", "gpus_requested", "shared_job_count", "nodes_shared", "jobs_shared",
    }
    frames: list[pd.DataFrame] = []
    opened: list[str] = []
    with zipfile.ZipFile(path) as archive, tempfile.TemporaryDirectory(prefix="v28r2-labels-") as temporary:
        local = Path(temporary) / "month.parquet"
        for info in archive.infolist():
            match = re.search(r"year=(\d{4})/month=(\d{1,2})", info.filename.replace("\\", "/"))
            if not info.filename.casefold().endswith(".parquet") or not match:
                continue
            month = int(match.group(1)) * 100 + int(match.group(2))
            # April's archive member is needed for jobs submitted before the
            # boundary but completed/filed after it.  Target timestamps remain
            # strictly before April through the fixed output axis below.
            if not 202408 <= month <= 202504:
                continue
            opened.append(info.filename)
            with archive.open(info) as source, local.open("wb") as target:
                shutil.copyfileobj(source, target)
            missing = columns - set(pq.ParquetFile(local).schema_arrow.names)
            if missing:
                raise RuntimeError(f"V28R2_KESTREL_SCHEMA_MISSING:{sorted(missing)}")
            frames.append(pq.read_table(local, columns=sorted(columns)).to_pandas())
    frame = pd.concat(frames, ignore_index=True)
    submit = pd.to_datetime(frame["submit_time"], utc=True, errors="coerce", format="mixed")
    start = pd.to_datetime(frame["start_time"], utc=True, errors="coerce", format="mixed")
    end = pd.to_datetime(frame["end_time"], utc=True, errors="coerce", format="mixed")
    nodes = pd.to_numeric(frame["gpu_nodes_occupied"], errors="coerce")
    gpus = pd.to_numeric(frame["gpus_requested"], errors="coerce")
    share = pd.to_numeric(frame["shared_job_count"], errors="coerce")
    valid = (
        frame["partition"].apply(_h100)
        & frame["state_simple"].astype(str).str.upper().eq("COMPLETED")
        & submit.notna() & start.notna() & end.notna() & end.gt(start)
        & nodes.gt(0) & gpus.gt(0)
    )
    jobs = frame.loc[valid, ["nodes_shared", "jobs_shared"]].copy()
    jobs["submit"] = submit[valid]
    jobs["start"] = start[valid]
    jobs["end"] = end[valid]
    jobs["nodes"] = nodes[valid]
    jobs["gpus"] = gpus[valid]
    jobs["share"] = share[valid]
    jobs["runtime_hours"] = (jobs["end"] - jobs["start"]).dt.total_seconds() / 3600.0

    axis_start = timestamps[0].tz_convert("UTC").timestamp()
    difference = np.zeros(len(timestamps) + 1, dtype=float)
    partial = np.zeros(len(timestamps), dtype=float)
    for row in jobs.itertuples(index=False):
        _add_interval_average(
            difference, partial,
            row.start.timestamp() - axis_start,
            row.end.timestamp() - axis_start,
            float(row.gpus),
        )
    g_gpu = partial + np.cumsum(difference[:-1])

    no_share = (
        (jobs["share"].isna() | jobs["share"].eq(0))
        & jobs["nodes_shared"].apply(object_empty)
        & jobs["jobs_shared"].apply(object_empty)
    )
    eligible = jobs[
        jobs["nodes"].isin(CONTROLLABLE_NODE_CLASSES)
        & np.isclose(jobs["gpus"], 4.0 * jobs["nodes"])
        & jobs["runtime_hours"].gt(0)
        & no_share
    ].copy()
    cohort_index = {cohort: index for index, cohort in enumerate(COHORT_IDS)}
    w_nodeh = np.zeros((len(timestamps), len(COHORT_IDS)), dtype=float)
    for row in eligible.itertuples(index=False):
        slot = int((row.submit.timestamp() - axis_start) // 900)
        if 0 <= slot < len(timestamps):
            cohort = _cohort(int(row.nodes), float(row.runtime_hours), bins)
            w_nodeh[slot, cohort_index[cohort]] += float(row.nodes) * float(row.runtime_hours)
    training_start_utc = pd.Timestamp(TRAIN_START, tz=AEST).tz_convert("UTC")
    training_end_utc = pd.Timestamp(AXIS_END_EXCLUSIVE, tz=AEST).tz_convert("UTC")
    eligible_training = eligible[eligible["submit"].ge(training_start_utc) & eligible["submit"].lt(training_end_utc)]
    return g_gpu, w_nodeh, {
        "kestrel_archive_members_opened": opened,
        "maximum_kestrel_month_opened": 202504,
        "April_archive_member_role": "boundary_completion_for_pre_April_submit_targets_only",
        "maximum_target_timestamp_exclusive": AXIS_END_EXCLUSIVE,
        "valid_total_reference_h100_jobs": int(len(jobs)),
        "strict_fullnode_eligible_jobs": int(len(eligible)),
        "strict_fullnode_training_jobs": int(len(eligible_training)),
        "strict_fullnode_node_hours": float(w_nodeh.sum()),
        "G_unit": "H100_GPU_equivalent_15min_average",
        "W_unit": "H100_node_hour_arrival",
    }


def load_optimizer_labels(repo: Path, raw_root: Path = DEFAULT_RAW_ROOT) -> OptimizerLabels:
    timestamps = pd.date_range(AXIS_START, AXIS_END_EXCLUSIVE, freq="15min", inclusive="left", tz=AEST)
    esif = _find_exact(raw_root, "esif.influx.buildingData.PUE.combined.parquet", NLR_SOURCE_SHA256["esif_parquet"])
    kestrel = _find_exact(raw_root, "esif.hpc.kestrel.job-anon.zip", NLR_SOURCE_SHA256["kestrel_jobs_zip"])
    p_it_kw, p_observed = _load_esif(esif, timestamps)
    g_gpu, w_nodeh, audit = _load_kestrel(kestrel, timestamps, _cohort_bins(repo))
    audit.update({
        "axis_start": AXIS_START,
        "axis_end_exclusive": AXIS_END_EXCLUSIVE,
        "timezone": "FIXED_AEST_UTC_PLUS_10",
        "resolution_minutes": 15,
        "slots_per_day": 96,
        "April_training_rows": 0,
        "May_training_rows": 0,
        "p_missing_slots": int((~p_observed).sum()),
        "partial_and_shared_retained_in_total_G": True,
        "partial_and_shared_controllable_W": False,
    })
    training = (timestamps >= pd.Timestamp(TRAIN_START, tz=AEST))
    audit["strict_fullnode_training_jobs_equivalent_check"] = "submit-time slot mass on 2024-08-19 through 2025-03-31"
    audit["strict_fullnode_training_node_hours"] = float(w_nodeh[training].sum())
    return OptimizerLabels(
        timestamps=timestamps,
        p_it_kw=p_it_kw,
        p_observed=p_observed,
        g_h100_gpu=g_gpu,
        w_nodeh=w_nodeh,
        cohort_ids=COHORT_IDS,
        source_paths={"esif": str(esif), "kestrel": str(kestrel)},
        source_sha256={"esif": sha256_file(esif), "kestrel": sha256_file(kestrel)},
        audit=audit,
    )

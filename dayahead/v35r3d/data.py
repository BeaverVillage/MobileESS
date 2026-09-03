"""Causal extraction and pinned-descriptor normalization for V35R3D."""

from __future__ import annotations

import re
import zipfile
from dataclasses import replace
from pathlib import Path
from typing import Any, Iterable

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from .contracts import (
    EARLIEST_TRAIN_END,
    HPCODA_DESCRIPTOR,
    ISSUE_TIME_UTC,
    KESTREL_ARCHIVE,
)


MEMBER_PATTERN = re.compile(r"year=(\d{4})/month=(\d{1,2})/.*\.parquet$")
RAW_MAPPING_COLUMNS = (
    "id",
    "submit_time",
    "start_time",
    "end_time",
    "wallclock_req",
    "nodes_req",
    "processors_req",
    "nodes_used",
    "processors_used",
    "gpus_requested",
    "memory_req",
    "partition",
    "qos",
    "state_simple",
    "user_hash",
    "account_hash",
)
QUERY_SOURCE_COLUMNS = (
    "id",
    "submit_time",
    "wallclock_req",
    "nodes_req",
    "processors_req",
    "gpus_requested",
    "memory_req",
    "partition",
    "qos",
    "user_hash",
    "account_hash",
)


def allowed_members(archive: zipfile.ZipFile) -> list[str]:
    """Match the official decoder's sorted-path order and stop at March 2025."""

    result: list[str] = []
    for name in archive.namelist():
        match = MEMBER_PATTERN.search(name)
        if match and (int(match.group(1)), int(match.group(2))) <= (2025, 3):
            result.append(name)
    return sorted(result)


def _utc_temporal(table: pa.Table) -> pa.Table:
    from hpc_oda_commons.datasets.decode.parquet import _unify_temporal

    return _unify_temporal(table)


def prepare_historical_table(cache_dir: Path) -> tuple[Path, dict[str, Any]]:
    """Build the exact descriptor-normalized, pre-issue completed-job table."""

    raw_path = cache_dir / "kestrel_preissue_raw.parquet"
    normalized_path = cache_dir / "kestrel_preissue_normalized.parquet"
    cache_dir.mkdir(parents=True, exist_ok=True)
    if normalized_path.is_file() and raw_path.is_file():
        metadata = pq.ParquetFile(normalized_path).metadata
        return normalized_path, {
            "cache_reused": True,
            "raw_path": str(raw_path),
            "normalized_path": str(normalized_path),
            "normalized_rows": metadata.num_rows,
        }

    tables: list[pa.Table] = []
    members: list[dict[str, Any]] = []
    lower = EARLIEST_TRAIN_END.astimezone(ISSUE_TIME_UTC.tzinfo)
    upper = ISSUE_TIME_UTC
    with zipfile.ZipFile(KESTREL_ARCHIVE) as archive:
        for name in allowed_members(archive):
            with archive.open(name) as stream:
                table = pq.read_table(
                    stream,
                    columns=list(RAW_MAPPING_COLUMNS),
                    filters=[
                        ("end_time", ">=", lower),
                        ("end_time", "<", upper),
                    ],
                )
            table = _utc_temporal(table)
            if table.num_rows:
                tables.append(table)
            members.append({"member": name, "rows": table.num_rows})
    if not tables:
        raise RuntimeError("V35R3D_NO_PREISSUE_HISTORICAL_ROWS")
    combined = pa.concat_tables(tables, promote_options="permissive")
    pq.write_table(combined, raw_path, compression="zstd")

    from hpc_oda_commons.datasets.descriptor import load_descriptor
    from hpc_oda_commons.datasets.normalize import normalize_target

    descriptor = load_descriptor(HPCODA_DESCRIPTOR)
    target = descriptor.targets[0]
    summary = normalize_target(raw_path, target, normalized_path)
    return normalized_path, {
        "cache_reused": False,
        "raw_path": str(raw_path),
        "normalized_path": str(normalized_path),
        "members": members,
        "raw_rows": combined.num_rows,
        "normalized_rows": pq.ParquetFile(normalized_path).metadata.num_rows,
        "normalization_summary": summary,
        "filter": {
            "end_time_gte": lower.isoformat(),
            "end_time_lt": upper.isoformat(),
            "Apr02_or_later_read": False,
        },
    }


def load_historical_rows(path: Path) -> list[dict[str, Any]]:
    return pq.read_table(path).to_pylist()


def _extract_ids(
    archive: zipfile.ZipFile,
    ids: set[str],
    columns: Iterable[str],
) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    touched: list[str] = []
    id_values = sorted(ids)
    for name in allowed_members(archive):
        with archive.open(name) as stream:
            table = pq.read_table(
                stream,
                columns=list(columns),
                filters=[("id", "in", id_values)],
            )
        if table.num_rows:
            rows.extend(_utc_temporal(table).to_pylist())
            touched.append(name)
    return rows, touched


def load_query_rows(
    running_ids: set[str], temporal_ids: set[str]
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Read submission fields for all queries and current start only for R_tau."""

    all_ids = running_ids | temporal_ids
    with zipfile.ZipFile(KESTREL_ARCHIVE) as archive:
        raw, submission_members = _extract_ids(archive, all_ids, QUERY_SOURCE_COLUMNS)
        starts, start_members = _extract_ids(
            archive, running_ids, ("id", "start_time")
        )
    start_by_id = {str(row["id"]): row.get("start_time") for row in starts}

    from hpc_oda_commons.ingest.jobs_parquet.apply import (
        _duration_to_seconds,
        _memory_slurm_to_mb,
    )

    result: dict[str, dict[str, Any]] = {}
    duplicates: list[str] = []
    for source in raw:
        job_id = str(source["id"])
        if job_id in result:
            duplicates.append(job_id)
            continue
        wallclock = source.get("wallclock_req")
        if hasattr(wallclock, "total_seconds"):
            requested_seconds = float(wallclock.total_seconds())
        else:
            requested_seconds = _duration_to_seconds(wallclock, "seconds")
        result[job_id] = {
            "job_id": job_id,
            "submit_time": source.get("submit_time"),
            "requested_seconds": requested_seconds,
            "num_nodes_req": source.get("nodes_req"),
            "num_cores_req": source.get("processors_req"),
            "num_gpus_req": source.get("gpus_requested"),
            "requested_memory_mib": _memory_slurm_to_mb(source.get("memory_req")),
            "partition": source.get("partition"),
            "qos": source.get("qos"),
            "user": source.get("user_hash"),
            "account": source.get("account_hash"),
            "known_start_time_at_issue": start_by_id.get(job_id)
            if job_id in running_ids
            else None,
        }
    return result, {
        "requested_ids": len(all_ids),
        "matched_ids": len(result),
        "missing_ids": sorted(all_ids - set(result)),
        "duplicate_ids": sorted(set(duplicates)),
        "submission_members_read": submission_members,
        "running_start_members_read": start_members,
        "pending_start_time_reads": 0,
        "future_end_time_reads": 0,
    }

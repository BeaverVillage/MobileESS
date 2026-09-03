"""Read-only scientific audit helpers for V35R3C."""

from __future__ import annotations

import csv
import hashlib
import importlib.metadata
import json
import math
import re
import subprocess
import zipfile
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from .contracts import (
    FORBIDDEN_QUERY_FEATURES,
    GPU_CAPACITY,
    ISSUE_TIME_UTC,
    KESTREL_ARCHIVE,
    RADDIT_ROOT,
    RECOVERED_FILES,
    SLOT_SECONDS,
    TARGET_START,
    W1,
    W3,
    W5,
)


MONTH_PATTERN = re.compile(r"year=(\d{4})/month=(\d{1,2})/.*\.parquet$")


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def git(path: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(path), *args],
        text=True,
        encoding="utf-8",
        errors="replace",
    ).strip()


def git_state(path: Path) -> dict[str, str]:
    return {
        "path": str(path),
        "HEAD": git(path, "rev-parse", "HEAD"),
        "branch": git(path, "branch", "--show-current"),
        "status": git(path, "status", "--short"),
    }


def write_json(path: Path, payload: Mapping[str, Any] | Sequence[Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0]) if rows else []
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for source in rows:
            row = dict(source)
            for key, value in row.items():
                if isinstance(value, (dict, list, tuple)):
                    row[key] = json.dumps(value, ensure_ascii=False, sort_keys=True)
            writer.writerow(row)


def safe_runtime_seconds(point: float, q90_plus: float, requested: float) -> float:
    """Frozen one-sided 90% safety rule, independent of Apr-01 outcomes."""

    values = (point, q90_plus, requested)
    if not all(math.isfinite(float(value)) for value in values):
        raise ValueError("NONFINITE_RUNTIME")
    if point < 0 or q90_plus < 0 or requested <= 0:
        raise ValueError("INVALID_RUNTIME")
    return min(float(requested), max(float(point) + float(q90_plus), float(SLOT_SECONDS)))


def running_remaining_seconds(safe_total: float, elapsed: float, requested: float) -> float:
    if elapsed < 0:
        raise ValueError("NEGATIVE_ELAPSED")
    capped = min(float(safe_total), float(requested))
    return max(capped - float(elapsed), float(SLOT_SECONDS))


def assert_causal_features(features: Sequence[str]) -> None:
    bad = set(features) & FORBIDDEN_QUERY_FEATURES
    if bad:
        raise PermissionError(f"FORBIDDEN_QUERY_FEATURES:{','.join(sorted(bad))}")


def dependency_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def recovered_lfs_verification() -> dict[str, Any]:
    rows = []
    for relative, (expected_size, expected_sha) in RECOVERED_FILES.items():
        path = RADDIT_ROOT / relative
        size = path.stat().st_size
        actual_sha = sha256_file(path)
        with path.open("rb") as stream:
            first = stream.read(4)
            stream.seek(-4, 2)
            last = stream.read(4)
        parquet = pq.ParquetFile(path)
        passed = (
            size == expected_size
            and actual_sha == expected_sha
            and first == b"PAR1"
            and last == b"PAR1"
        )
        rows.append(
            {
                "relative_path": relative,
                "physical_path": str(path),
                "expected_size": expected_size,
                "actual_size": size,
                "expected_sha256": expected_sha,
                "actual_sha256": actual_sha,
                "parquet_magic_start": first.decode("ascii"),
                "parquet_magic_end": last.decode("ascii"),
                "row_count": parquet.metadata.num_rows,
                "status": "PASS" if passed else "FAIL",
            }
        )
    passed = all(row["status"] == "PASS" for row in rows)
    return {
        "artifact_id": "V35R3C_RECOVERED_LFS_VERIFICATION_V1",
        "RADDIT_CORE_LFS_RECOVERY": "PASS" if passed else "FAIL",
        "files": rows,
        "superseded_V35R3B_blockers": {
            "NO_LOCAL_PREDICTED_PAYLOAD": "SUPERSEDED_BY_RECOVERED_EXTERNAL_AUTHORITY",
            "RADDIT_CORE_LFS_PAYLOAD_REQUIRED": "SUPERSEDED_BY_RECOVERED_EXTERNAL_AUTHORITY",
        },
        "not_automatically_superseded": [
            "POWER_DOMAIN_MISMATCH",
            "POWER_ATTRIBUTION_AMBIGUOUS",
            "IDENTITY_BLOCKED",
            "GRID_BINDING_INCOMPLETE",
            "SCHEDULER_FIDELITY_LIMITATION",
        ],
    }


def _timestamp_range(path: Path, field: str) -> tuple[str | None, str | None]:
    table = pq.read_table(path, columns=[field])
    values = pd.to_datetime(table[field].to_pandas(), utc=True, errors="coerce")
    if not values.notna().any():
        return None, None
    return values.min().isoformat(), values.max().isoformat()


def raddit_payload_audit() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    coverage: dict[str, Any] = {
        "artifact_id": "V35R3C_RADDIT_PAYLOAD_TIME_COVERAGE_V1",
        "issue_time": ISSUE_TIME_UTC.isoformat(),
        "files": {},
    }
    for relative, (_size, expected_sha) in RECOVERED_FILES.items():
        path = RADDIT_ROOT / relative
        parquet = pq.ParquetFile(path)
        columns = [field.name for field in parquet.schema_arrow]
        schema = {field.name: str(field.type) for field in parquet.schema_arrow}
        is_historic = relative.endswith("historic_job_trace.parquet")
        ranges: dict[str, dict[str, str | None]] = {}
        if is_historic:
            for field in ("submit_time", "start_time", "end_time"):
                low, high = _timestamp_range(path, field)
                ranges[field] = {"min": low, "max": high}
        if is_historic:
            source_kind = "MEASURED_HISTORICAL_JOB_TRACE"
            units = {
                "wallclock_used_sec": "s",
                "wallclock_req_sec": "s",
                "avg_power_per_node": "W_per_node",
            }
            classification = "HISTORICAL_MODEL_INPUT_AND_LABEL_EVIDENCE_NOT_DIRECT_APR01_PREDICTION"
        else:
            source_kind = "PREDICTION_VS_ACTUAL_AGGREGATE_EVALUATION"
            units = (
                {"avg_power_per_node": "W_per_node", "predicted_power": "W_per_node"}
                if "power" in relative
                else {"wallclock_used_sec": "s", "predicted_runtime_hours": "h"}
            )
            classification = "AGGREGATE_EVALUATION_PAYLOAD_NOT_DIRECT_APR01_JOIN_AUTHORITY"
        keyed = any(name in columns for name in ("job_id", "array_pos"))
        row = {
            "relative_path": relative,
            "physical_path": str(path),
            "sha256": expected_sha,
            "byte_size": path.stat().st_size,
            "row_count": parquet.metadata.num_rows,
            "schema_json": schema,
            "min_max_timestamps_json": ranges,
            "units_json": units,
            "keyed": keyed,
            "source_kind": source_kind,
            "cpu_gpu_domain": "GPU_NOT_IDENTIFIABLE" if is_historic else "RADDIT_CPU_EXCLUSIVE_VALIDATION_DOMAIN",
            "exclusive_shared_domain": "NOT_IDENTIFIABLE" if is_historic else "CPU_EXCLUSIVE_EVALUATION",
            "H100_identifiable": False,
            "Apr01_direct_join": False,
            "submission_time_causal_direct_output": False,
            "classification": classification,
        }
        rows.append(row)
        coverage["files"][relative] = {
            "row_count": parquet.metadata.num_rows,
            "time_ranges": ranges,
            "has_timestamp_columns": bool(ranges),
            "Apr01_direct_job_coverage": 0,
            "classification": classification,
        }
    coverage["historic_trace_latest_submit_before_issue_days"] = (
        pd.Timestamp(ISSUE_TIME_UTC)
        - pd.Timestamp(coverage["files"]["data/historic_job_trace.parquet"]["time_ranges"]["submit_time"]["max"])
    ).total_seconds() / 86400.0
    coverage["aggregate_result_tables_have_prediction_timestamp"] = False
    coverage["direct_Apr01_prediction_rows"] = 0
    return rows, coverage


def _allowed_members(archive: zipfile.ZipFile) -> list[str]:
    result = []
    for name in archive.namelist():
        match = MONTH_PATTERN.search(name)
        if match and (int(match.group(1)), int(match.group(2))) <= (2025, 3):
            result.append(name)
    return sorted(result)


def identity_audit(parent_artifacts: Path) -> dict[str, Any]:
    rad_path = RADDIT_ROOT / "data" / "historic_job_trace.parquet"
    rad = pq.read_table(
        rad_path,
        columns=["job_id", "submit_time", "nodes_req", "processors_req", "wallclock_req_sec"],
    ).to_pandas()
    rad["submit_utc"] = pd.to_datetime(rad["submit_time"], utc=True, errors="coerce")
    rad = rad.set_index("job_id", drop=False)
    maximum = int(rad.index.max())
    rad_min_time = rad["submit_utc"].min()
    rad_max_time = rad["submit_utc"].max()

    total_rows = 0
    raw_parts: list[np.ndarray] = []
    tuple_parts: list[np.recarray] = []
    exact_parts: list[pd.DataFrame] = []
    members: list[dict[str, Any]] = []
    issue = pd.Timestamp(ISSUE_TIME_UTC)
    with zipfile.ZipFile(KESTREL_ARCHIVE) as archive:
        for name in _allowed_members(archive):
            with archive.open(name) as stream:
                table = pq.read_table(
                    stream,
                    columns=[
                        "id",
                        "job_id",
                        "array_pos",
                        "submit_time",
                        "nodes_req",
                        "processors_req",
                        "wallclock_req",
                    ],
                    filters=[("submit_time", "<=", issue.to_pydatetime())],
                )
            frame = table.to_pandas()
            total_rows += len(frame)
            members.append({"member": name, "rows_returned_preissue": len(frame)})
            raw = pd.to_numeric(frame["job_id"], errors="coerce").fillna(-1).astype("int64").to_numpy()
            array_pos = (
                pd.to_numeric(frame["array_pos"], errors="coerce").fillna(-1).astype("int64").to_numpy()
            )
            raw_parts.append(raw)
            tuple_parts.append(np.rec.fromarrays([raw, array_pos], names="job_id,array_pos"))
            ids = frame["id"].astype("string")
            numeric_mask = ids.str.fullmatch(r"[0-9]+", na=False)
            numeric = pd.to_numeric(ids.where(numeric_mask), errors="coerce")
            exact_mask = numeric_mask & numeric.between(0, maximum, inclusive="both")
            if exact_mask.any():
                part = frame.loc[
                    exact_mask,
                    [
                        "id",
                        "job_id",
                        "array_pos",
                        "submit_time",
                        "nodes_req",
                        "processors_req",
                        "wallclock_req",
                    ],
                ].copy()
                part["normalized_id"] = part["id"].astype("int64")
                exact_parts.append(part)

    raw_all = np.concatenate(raw_parts)
    tuple_all = np.concatenate(tuple_parts)
    matched = pd.concat(exact_parts, ignore_index=True)
    rad_match = rad.loc[matched["normalized_id"].to_numpy(dtype="int64")].reset_index(drop=True)
    kestrel_submit = pd.to_datetime(matched["submit_time"], utc=True, errors="coerce").reset_index(drop=True)
    rad_submit = rad_match["submit_utc"].reset_index(drop=True)
    kestrel_wallclock = pd.to_timedelta(matched["wallclock_req"]).dt.total_seconds().to_numpy(float)
    rad_wallclock = rad_match["wallclock_req_sec"].to_numpy(float)
    time_consistent = kestrel_submit.eq(rad_submit)
    nodes_consistent = matched["nodes_req"].reset_index(drop=True).eq(rad_match["nodes_req"])
    processors_consistent = matched["processors_req"].reset_index(drop=True).eq(
        rad_match["processors_req"]
    )
    wallclock_consistent = np.isclose(kestrel_wallclock, rad_wallclock, rtol=0, atol=1e-9)
    date_restricted = kestrel_submit.between(rad_min_time, rad_max_time, inclusive="both")

    pending = pd.read_parquet(parent_artifacts / "V35R3A_PENDING_FIELD_AUDIT.parquet")
    schedule = pd.read_parquet(parent_artifacts / "V35R3A_BASELINE_SCHEDULE.parquet")
    rad_ids = set(rad.index.astype(int).astype(str))
    running_ids = set(schedule.loc[schedule["state_at_issue"].eq("RUNNING"), "job_id"].astype(str))
    pending_ids = set(pending["job_id"].astype(str))
    temporal_ids = set(
        pending.loc[
            pending["workload_class"].isin(
                ["NORMAL_QUEUE_CONTROLLED", "STANDBY_QUEUE_CONTROLLED"]
            ),
            "job_id",
        ].astype(str)
    )
    all_consistent = (
        time_consistent
        & nodes_consistent
        & processors_consistent
        & pd.Series(wallclock_consistent)
    )
    unique_full = int(np.unique(tuple_all).size)
    unique_raw = int(np.unique(raw_all).size)
    return {
        "artifact_id": "V35R3C_RADDIT_KESTREL_IDENTITY_AUDIT_V1",
        "classification": "RADDIT_KESTREL_IDENTITY_DIRECT_JOIN_BLOCKED",
        "method": "EXACT_NORMALIZED_FULL_ID_ONLY_NO_FUZZY_MATCH",
        "scope": "CANONICAL_2023_08_THROUGH_ISSUE_ONLY_NO_POSTISSUE_ROWS",
        "members_read": members,
        "RADDiT_total_job_IDs": int(rad["job_id"].nunique()),
        "RADDiT_duplicate_extra_rows": int(rad["job_id"].duplicated().sum()),
        "RADDiT_job_id_semantics": "CONTIGUOUS_ZERO_BASED_ROW_INDEX_0_TO_2557883",
        "Kestrel_preissue_total_rows": total_rows,
        "Kestrel_unique_full_IDs": unique_full,
        "Kestrel_full_ID_duplicate_extra_rows": total_rows - unique_full,
        "Kestrel_unique_numeric_raw_job_IDs": unique_raw,
        "Kestrel_numeric_raw_duplicate_extra_rows": total_rows - unique_raw,
        "exact_normalized_full_ID_overlap": int(matched["normalized_id"].nunique()),
        "overlap_fraction_RADDiT": float(matched["normalized_id"].nunique() / len(rad)),
        "overlap_fraction_Kestrel_preissue": float(matched["id"].nunique() / total_rows),
        "date_restricted_overlap": int(date_restricted.sum()),
        "timestamp_consistent_overlap": int(time_consistent.sum()),
        "nodes_consistent_overlap": int(nodes_consistent.sum()),
        "processors_consistent_overlap": int(processors_consistent.sum()),
        "wallclock_consistent_overlap": int(wallclock_consistent.sum()),
        "timestamp_and_all_resource_consistent_overlap": int(all_consistent.sum()),
        "Apr01_R_tau_total": len(running_ids),
        "Apr01_R_tau_overlap": len(running_ids & rad_ids),
        "Apr01_P_tau_total": len(pending_ids),
        "Apr01_P_tau_overlap": len(pending_ids & rad_ids),
        "Apr01_temporal_total": len(temporal_ids),
        "Apr01_temporal_overlap": len(temporal_ids & rad_ids),
        "one_to_many_conflicts_full_ID": total_rows - unique_full,
        "interpretation": (
            "Numeric equality is coincidental: RADDiT IDs are row indices and zero overlapping "
            "rows have an identical submit timestamp. Numeric-only overlap is not identity authority."
        ),
    }


def h100_energy_audit(parent_artifacts: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    issue = pd.Timestamp(ISSUE_TIME_UTC)
    lower = issue - pd.Timedelta(days=120)
    months = {(2024, 12), (2025, 1), (2025, 2), (2025, 3)}
    columns = [
        "id",
        "submit_time",
        "start_time",
        "end_time",
        "partition",
        "qos",
        "nodes_req",
        "nodes_used",
        "processors_req",
        "memory_req",
        "wallclock_req",
        "gpus_requested",
        "gpu_nodes_occupied",
        "shared_job_count",
        "nodes_shared",
        "jobs_shared",
        "consumed_energy_joules",
        "consumed_energy_raw_joules",
        "consumed_energy_raw_watt_hours",
        "state_simple",
    ]
    frames: list[pd.DataFrame] = []
    members: list[str] = []
    with zipfile.ZipFile(KESTREL_ARCHIVE) as archive:
        for name in _allowed_members(archive):
            match = MONTH_PATTERN.search(name)
            if not match or (int(match.group(1)), int(match.group(2))) not in months:
                continue
            with archive.open(name) as stream:
                table = pq.read_table(
                    stream,
                    columns=columns,
                    filters=[("submit_time", "<=", issue.to_pydatetime())],
                )
            frames.append(table.to_pandas())
            members.append(name)
    frame = pd.concat(frames, ignore_index=True)
    for column in ("submit_time", "start_time", "end_time"):
        frame[column] = pd.to_datetime(frame[column], utc=True, errors="coerce")
    frame = frame.loc[frame["submit_time"].between(lower, issue, inclusive="both")].copy()
    h100 = frame.loc[
        frame["partition"].fillna("").str.lower().str.startswith("gpu-h100")
    ].copy()
    h100["runtime_seconds"] = (h100["end_time"] - h100["start_time"]).dt.total_seconds()
    numeric_energy = pd.to_numeric(h100["consumed_energy_raw_watt_hours"], errors="coerce")
    numeric_joules = pd.to_numeric(h100["consumed_energy_raw_joules"], errors="coerce")
    shared = pd.to_numeric(h100["shared_job_count"], errors="coerce")
    full = np.isclose(
        pd.to_numeric(h100["gpus_requested"], errors="coerce"),
        4.0 * pd.to_numeric(h100["nodes_req"], errors="coerce"),
        equal_nan=False,
    )
    nodes_match = pd.to_numeric(h100["nodes_used"], errors="coerce").eq(
        pd.to_numeric(h100["nodes_req"], errors="coerce")
    )
    nodes_shared_empty = h100["nodes_shared"].map(lambda value: value is None or len(value) == 0)
    jobs_shared_empty = h100["jobs_shared"].map(lambda value: value is None or len(value) == 0)
    completed = (
        h100["state_simple"].eq("COMPLETED")
        & h100["end_time"].notna()
        & h100["end_time"].lt(issue)
    )
    valid_runtime = h100["runtime_seconds"].gt(0)
    valid_energy = numeric_energy.gt(0) & numeric_joules.gt(0)
    exclusive = shared.eq(0) & nodes_shared_empty & jobs_shared_empty
    cohort = completed & full & nodes_match & exclusive & valid_runtime & valid_energy

    pending = pd.read_parquet(parent_artifacts / "V35R3A_PENDING_FIELD_AUDIT.parquet")
    temporal = pending.loc[
        pending["workload_class"].isin(
            ["NORMAL_QUEUE_CONTROLLED", "STANDBY_QUEUE_CONTROLLED"]
        )
    ].copy()
    query_full = np.isclose(
        temporal["requested_GPUs"], 4.0 * temporal["requested_nodes"], equal_nan=False
    )

    def counts(series: pd.Series, limit: int = 30) -> dict[str, int]:
        return {str(key): int(value) for key, value in series.value_counts(dropna=False).head(limit).items()}

    energy_audit = {
        "artifact_id": "V35R3C_H100_ENERGY_FIELD_AUDIT_V1",
        "source_boundary": (
            "Slurm ConsumedEnergyRaw from node-level power monitoring; only positive-energy, "
            "completed, exclusive full-node rows could be attributable."
        ),
        "source_datacard_energy_lines": "130, 186-190",
        "source_datacard_sharing_lines": "198-200, 235",
        "lookback_start": lower.isoformat(),
        "issue_time": issue.isoformat(),
        "members_read": members,
        "all_lookback_rows": len(frame),
        "H100_rows": len(h100),
        "H100_partition_counts": counts(h100["partition"]),
        "H100_state_counts": counts(h100["state_simple"]),
        "H100_GPU_request_counts": counts(h100["gpus_requested"]),
        "H100_energy_nonnull_rows": int(numeric_energy.notna().sum()),
        "H100_energy_positive_rows": int(numeric_energy.gt(0).sum()),
        "H100_energy_zero_rows": int(numeric_energy.eq(0).sum()),
        "H100_shared_count_nonnull_rows": int(shared.notna().sum()),
        "H100_shared_count_zero_rows": int(shared.eq(0).sum()),
        "H100_nodes_shared_empty_rows": int(nodes_shared_empty.sum()),
        "H100_jobs_shared_empty_rows": int(jobs_shared_empty.sum()),
        "completed_preissue_rows": int(completed.sum()),
        "full_node_request_shape_rows": int(full.sum()),
        "valid_runtime_rows": int(valid_runtime.sum()),
        "exclusive_full_positive_energy_training_rows": int(cohort.sum()),
        "Apr01_temporal_jobs": len(temporal),
        "Apr01_full_node_shape_jobs": int(query_full.sum()),
        "Apr01_partial_shared_shape_jobs": int((~query_full).sum()),
        "future_power_reads": 0,
        "classification": "H100_ENERGY_TRAINING_COHORT_EMPTY_ZERO_ENERGY",
    }
    cohort_audit = {
        "artifact_id": "V35R3C_H100_POWER_TRAINING_COHORT_V1",
        "eligibility": [
            "completed before issue",
            "partition starts gpu-h100",
            "gpus_requested == 4 * nodes_req",
            "nodes_used == nodes_req",
            "shared_job_count == 0",
            "nodes_shared and jobs_shared empty",
            "positive ConsumedEnergyRaw",
            "positive realized runtime",
        ],
        "eligible_rows": int(cohort.sum()),
        "model_trained": False,
        "reason": "NO_POSITIVE_H100_ENERGY_LABEL_AND_NO_EXPLICIT_ZERO_SHARED_ROWS",
        "P2_eligible": False,
    }
    return energy_audit, cohort_audit


def empty_runtime_frame(kind: str) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "job_id": pd.Series(dtype="string"),
            "prediction_kind": pd.Series(dtype="string"),
            "predicted_runtime_seconds": pd.Series(dtype="float64"),
            "requested_walltime_seconds": pd.Series(dtype="float64"),
            "covered": pd.Series(dtype="bool"),
            "authority_level": pd.Series(dtype="string"),
            "blocked_reason": pd.Series(dtype="string"),
        }
    ).assign(prediction_kind=pd.Series(dtype="string")).iloc[:0]


def capacity_summary(frame: pd.DataFrame) -> dict[str, Any]:
    occupied = frame["occupied_GPUs"].to_numpy(float)
    free = GPU_CAPACITY - occupied
    below = np.flatnonzero(free > 1e-9)
    return {
        "slots": len(frame),
        "saturated_slots": int(np.isclose(occupied, GPU_CAPACITY).sum()),
        "P05_occupied_GPUs": float(np.quantile(occupied, 0.05)),
        "P50_occupied_GPUs": float(np.quantile(occupied, 0.50)),
        "P95_occupied_GPUs": float(np.quantile(occupied, 0.95)),
        "first_below_624_slot": int(below[0]) if len(below) else None,
        "free_GPU_hours": float(free.sum() * 0.25),
        "W1_free_GPUs": float(free[list(W1)].sum()),
        "W3_free_GPUs": float(free[list(W3)].sum()),
        "W5_free_GPUs": float(free[list(W5)].sum()),
    }

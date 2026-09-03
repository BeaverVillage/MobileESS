"""Science-neutral helpers for local authority, join, and profile audits."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import re
import stat
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from .contracts import FORBIDDEN_CAUSAL_FEATURES, GPU_CAPACITY, SLOT_MINUTES, TARGET_SLOTS


LFS_HEADER = b"version https://git-lfs.github.com/spec/v1"
LFS_PATTERN = re.compile(
    rb"\Aversion https://git-lfs\.github\.com/spec/v1\r?\n"
    rb"oid sha256:([0-9a-f]{64})\r?\nsize ([0-9]+)\r?\n?\Z"
)


def sha256_file(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def lfs_pointer_info(path: Path) -> dict[str, Any] | None:
    """Return validated Git-LFS metadata, never mistaking a pointer for Parquet."""

    if not path.is_file() or path.stat().st_size > 1024:
        return None
    payload = path.read_bytes()
    if not payload.startswith(LFS_HEADER):
        return None
    match = LFS_PATTERN.match(payload)
    if not match:
        raise ValueError(f"MALFORMED_GIT_LFS_POINTER:{path}")
    return {
        "oid_sha256": match.group(1).decode("ascii"),
        "expected_size": int(match.group(2)),
        "pointer_size": len(payload),
    }


def local_lfs_object(path: Path, oid: str) -> Path | None:
    """Locate an already-present LFS object without invoking Git LFS or network."""

    current = path.parent
    while current != current.parent:
        marker = current / ".git"
        if marker.exists():
            git_dir = marker
            if marker.is_file():
                text = marker.read_text(encoding="utf-8").strip()
                git_dir = (current / text.removeprefix("gitdir: ")).resolve()
            candidate = git_dir / "lfs" / "objects" / oid[:2] / oid[2:4] / oid
            return candidate if candidate.is_file() else None
        current = current.parent
    return None


def normalize_job_key(value: object) -> str | None:
    """Normalize exact identifiers only; no fuzzy or timestamp matching."""

    if value is None or pd.isna(value):
        return None
    if isinstance(value, (int, np.integer)):
        return str(int(value))
    if isinstance(value, (float, np.floating)):
        if not math.isfinite(float(value)) or not float(value).is_integer():
            raise ValueError(f"NON_INTEGRAL_NUMERIC_JOB_KEY:{value}")
        return str(int(value))
    text = str(value).strip()
    if not text:
        return None
    if re.fullmatch(r"[0-9]+\.0+", text):
        return text.split(".", 1)[0]
    return text


def exact_key_join(
    left: pd.DataFrame,
    right: pd.DataFrame,
    *,
    left_key: str,
    right_key: str,
) -> pd.DataFrame:
    """Perform a J1 exact join and reject duplicate authority keys."""

    lhs = left.copy()
    rhs = right.copy()
    lhs["_exact_job_key"] = lhs[left_key].map(normalize_job_key)
    rhs["_exact_job_key"] = rhs[right_key].map(normalize_job_key)
    duplicates = rhs.loc[rhs["_exact_job_key"].notna(), "_exact_job_key"].duplicated(keep=False)
    if duplicates.any():
        keys = sorted(rhs.loc[duplicates, "_exact_job_key"].unique())
        raise ValueError(f"DUPLICATE_AUTHORITY_JOB_KEY:{','.join(keys[:10])}")
    return lhs.merge(rhs.drop(columns=[right_key]), on="_exact_job_key", how="left", validate="m:1")


def assert_no_fuzzy_join(method: str) -> None:
    if method not in {"J1_EXACT_KEY", "J2_DOCUMENTED_TRANSFORM", "J3_MODEL_INFERENCE"}:
        raise PermissionError(f"FUZZY_PRODUCTION_JOIN_FORBIDDEN:{method}")


def causal_feature_audit(features: Iterable[str]) -> dict[str, int]:
    normalized = {str(value).strip().lower() for value in features}
    forbidden = normalized & FORBIDDEN_CAUSAL_FEATURES
    if forbidden:
        raise PermissionError(f"FORBIDDEN_FUTURE_FEATURES:{','.join(sorted(forbidden))}")
    return {
        "future_start_feature_reads": 0,
        "future_end_feature_reads": 0,
        "realized_runtime_feature_reads": 0,
        "realized_power_feature_reads": 0,
        "post_issue_job_identity_reads_KQ0": 0,
        "Fresh_reads_during_policy_selection": 0,
    }


def remaining_duration_slots(
    predicted_total_runtime_seconds: float,
    elapsed_at_issue_seconds: float,
    *,
    slot_seconds: int = SLOT_MINUTES * 60,
) -> int:
    """Causal predicted-runtime rule for a running job, when authority exists."""

    if predicted_total_runtime_seconds < 0 or elapsed_at_issue_seconds < 0:
        raise ValueError("NEGATIVE_RUNTIME_FORBIDDEN")
    return max(1, math.ceil(max(predicted_total_runtime_seconds - elapsed_at_issue_seconds, slot_seconds) / slot_seconds))


def requested_duration_slots(requested_walltime_seconds: float) -> int:
    if requested_walltime_seconds <= 0:
        raise ValueError("NONPOSITIVE_REQUESTED_WALLTIME")
    return math.ceil(requested_walltime_seconds / (SLOT_MINUTES * 60))


def target_gpu_profile(schedule: pd.DataFrame, *, target_offset_slots: int = 24) -> np.ndarray:
    """Build Apr-01 occupancy without reading any Apr-02 state or realized data."""

    profile = np.zeros(TARGET_SLOTS, dtype=float)
    for row in schedule.itertuples(index=False):
        start = max(0, int(row.scheduled_start_slot) - target_offset_slots)
        end = min(TARGET_SLOTS, int(row.scheduled_end_slot) - target_offset_slots)
        if end > start:
            profile[start:end] += float(row.requested_gpus)
    if np.any(profile > GPU_CAPACITY + 1e-9):
        raise AssertionError("V35R3B_GPU_CAPACITY_VIOLATION")
    return profile


def profile_energy_gpu_hours(profile: Sequence[float]) -> float:
    return float(np.asarray(profile, dtype=float).sum() * SLOT_MINUTES / 60.0)


def power_profile_from_jobs(
    rows: Sequence[Mapping[str, Any]],
    *,
    shared_power_incremental_proven: bool,
) -> np.ndarray:
    """Construct job-power profile only when shared-node attribution is proven."""

    profile = np.zeros(TARGET_SLOTS, dtype=float)
    for row in rows:
        if bool(row.get("partial_or_shared")) and not shared_power_incremental_proven:
            raise PermissionError("POWER_ATTRIBUTION_AMBIGUOUS")
        unit = row.get("power_unit_semantics")
        value = float(row["predicted_power_kw"])
        if unit == "TOTAL_JOB_IT_KW":
            power = value
        elif unit == "PER_GPU_KW":
            power = value * float(row["requested_gpus"])
        elif unit == "PER_NODE_KW":
            power = value * float(row["requested_nodes"])
        else:
            raise ValueError(f"UNKNOWN_POWER_UNIT_SEMANTICS:{unit}")
        start = max(0, int(row["start_slot"]))
        end = min(TARGET_SLOTS, int(row["end_slot"]))
        profile[start:end] += power
    return profile


def deterministic_rank(candidates: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """Fixed, non-random S2/S5 ranking and tie-break contract."""

    return sorted(
        candidates,
        key=lambda row: (
            -float(row["predicted_w5_it_reduction_kw"]),
            float(row.get("planning_rho", math.inf)),
            float(row.get("critical_exposure", math.inf)),
            int(row.get("reprioritized_jobs", 2)),
            float(row.get("total_sitefactor", math.inf)),
            str(row["candidate_id"]),
        ),
    )


def top_k_escalation(candidate_count: int) -> list[int]:
    stages = [value for value in (50, 200, 1000) if value < candidate_count]
    stages.append(candidate_count)
    return stages


def _git(path: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(path), *args], text=True, encoding="utf-8", errors="replace"
    ).strip()


def git_repository_state(path: Path) -> dict[str, Any]:
    return {
        "path": str(path),
        "HEAD": _git(path, "rev-parse", "HEAD"),
        "branch": _git(path, "branch", "--show-current"),
        "status": _git(path, "status", "--short"),
        "remotes": _git(path, "remote", "-v"),
    }


def _windows_offline(path_stat: os.stat_result) -> bool:
    attributes = getattr(path_stat, "st_file_attributes", 0)
    return bool(attributes & 0x1000)


def _schema_for_file(path: Path, pointer: dict[str, Any] | None) -> dict[str, Any]:
    suffix = path.suffix.lower()
    if pointer:
        return {"format": "GIT_LFS_POINTER", "row_count": None, "columns": None}
    if suffix == ".parquet":
        parquet = pq.ParquetFile(path)
        return {
            "format": "PARQUET",
            "row_count": parquet.metadata.num_rows,
            "columns": [field.name for field in parquet.schema_arrow],
            "schema": str(parquet.schema_arrow),
        }
    if suffix in {".csv", ".tsv"}:
        separator = "\t" if suffix == ".tsv" else ","
        frame = pd.read_csv(path, sep=separator, nrows=5)
        return {
            "format": suffix[1:].upper(),
            "row_count": None,
            "columns": [str(value) for value in frame.columns],
            "schema": ";".join(f"{name}:{dtype}" for name, dtype in frame.dtypes.items()),
        }
    if suffix == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        return {
            "format": "JSON",
            "row_count": len(payload) if isinstance(payload, list) else None,
            "columns": sorted(payload) if isinstance(payload, dict) else None,
            "schema": type(payload).__name__,
        }
    if suffix == ".ipynb":
        notebook = json.loads(path.read_text(encoding="utf-8"))
        cells = notebook.get("cells", [])
        return {
            "format": "JUPYTER_NOTEBOOK_JSON",
            "row_count": len(cells),
            "columns": None,
            "schema": f"cells={len(cells)};output_cells={sum(bool(cell.get('outputs')) for cell in cells)}",
        }
    if suffix in {".pkl", ".pickle", ".joblib"}:
        return {
            "format": "PICKLE_UNTRUSTED_NOT_DESERIALIZED",
            "row_count": None,
            "columns": None,
            "schema": "UNAVAILABLE_WITHOUT_UNSAFE_CODE_EXECUTION",
        }
    return {"format": suffix[1:].upper() or "NO_EXTENSION", "row_count": None, "columns": None}


def inventory_authority(root: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Hash and inspect every non-.git authority file without following links."""

    rows: list[dict[str, Any]] = []
    errors: Counter[str] = Counter()
    for path in sorted(root.rglob("*"), key=lambda item: str(item).lower()):
        relative_path = path.relative_to(root)
        if ".git" in relative_path.parts:
            continue
        try:
            path_stat = path.lstat()
        except OSError as exc:
            if path.suffix or path.name:
                rows.append(
                    {
                        "repository": relative_path.parts[0],
                        "relative_path": relative_path.as_posix(),
                        "absolute_path": str(path),
                        "extension": path.suffix.lower(),
                        "size_bytes": None,
                        "offline_placeholder": False,
                        "zero_byte": False,
                        "readable": False,
                        "sha256": None,
                        "lfs_pointer": False,
                        "lfs_oid": None,
                        "lfs_expected_size": None,
                        "lfs_object_cached_locally": False,
                        "format": "UNREADABLE_PATH",
                        "row_count": None,
                        "columns": None,
                        "schema": None,
                        "parse_error": f"{type(exc).__name__}:{exc}",
                    }
                )
                errors[type(exc).__name__] += 1
            continue
        is_link = stat.S_ISLNK(path_stat.st_mode)
        is_regular = stat.S_ISREG(path_stat.st_mode)
        if not is_link and not is_regular:
            continue
        relative = relative_path.as_posix()
        repository = relative.split("/", 1)[0]
        row: dict[str, Any] = {
            "repository": repository,
            "relative_path": relative,
            "absolute_path": str(path),
            "extension": path.suffix.lower(),
            "size_bytes": path_stat.st_size,
            "offline_placeholder": _windows_offline(path_stat),
            "zero_byte": path_stat.st_size == 0,
            "readable": False,
            "sha256": None,
            "lfs_pointer": False,
            "lfs_oid": None,
            "lfs_expected_size": None,
            "lfs_object_cached_locally": False,
            "format": None,
            "row_count": None,
            "columns": None,
            "schema": None,
            "parse_error": None,
        }
        if is_link:
            row["format"] = "UNREADABLE_SYMLINK_OR_REPARSE"
            row["parse_error"] = "SYMLINK_TARGET_UNAVAILABLE_ON_WINDOWS_NOT_OPENED"
            errors["UNREADABLE_SYMLINK_OR_REPARSE"] += 1
            rows.append(row)
            continue
        if row["offline_placeholder"]:
            row["parse_error"] = "ONEDRIVE_OFFLINE_PLACEHOLDER_NOT_OPENED"
            errors[row["parse_error"]] += 1
            rows.append(row)
            continue
        try:
            pointer = lfs_pointer_info(path)
            row["sha256"] = sha256_file(path)
            row["readable"] = True
            if pointer:
                row.update(
                    {
                        "lfs_pointer": True,
                        "lfs_oid": pointer["oid_sha256"],
                        "lfs_expected_size": pointer["expected_size"],
                        "lfs_object_cached_locally": local_lfs_object(path, pointer["oid_sha256"])
                        is not None,
                    }
                )
            row.update(_schema_for_file(path, pointer))
        except Exception as exc:  # inventory is fail-closed but exhaustive
            row["parse_error"] = f"{type(exc).__name__}:{exc}"
            errors[type(exc).__name__] += 1
        rows.append(row)
    fingerprint_payload = [
        (row["relative_path"], row["size_bytes"], row["sha256"], row["offline_placeholder"])
        for row in rows
    ]
    summary = {
        "root": str(root),
        "file_count": len(rows),
        "total_bytes": int(sum(int(row["size_bytes"] or 0) for row in rows)),
        "readable_count": sum(bool(row["readable"]) for row in rows),
        "zero_byte_count": sum(bool(row["zero_byte"]) for row in rows),
        "offline_placeholder_count": sum(bool(row["offline_placeholder"]) for row in rows),
        "lfs_pointer_count": sum(bool(row["lfs_pointer"]) for row in rows),
        "lfs_objects_cached_locally": sum(bool(row["lfs_object_cached_locally"]) for row in rows),
        "real_parquet_count": sum(row["format"] == "PARQUET" for row in rows),
        "parse_error_counts": dict(errors),
        "content_fingerprint_sha256": hashlib.sha256(
            json.dumps(fingerprint_payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
    }
    return rows, summary


def write_csv(path: Path, rows: Sequence[Mapping[str, Any]], fieldnames: Sequence[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        fieldnames = list(rows[0]) if rows else []
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for source in rows:
            row = dict(source)
            for key, value in row.items():
                if isinstance(value, (dict, list, tuple)):
                    row[key] = json.dumps(value, ensure_ascii=False, sort_keys=True)
            writer.writerow(row)


def write_json(path: Path, payload: Mapping[str, Any] | Sequence[Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )

"""Hash-bound atomic storage and dependency-aware V35 checkpoint validation."""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Iterable, Mapping, Sequence

import numpy as np

from .contracts import CHECKPOINT_FIELDS, SLOTS


def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
        default=lambda item: item.item() if isinstance(item, np.generic) else str(item),
    ).encode("utf-8")


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def array_sha256(value: np.ndarray) -> str:
    array = np.ascontiguousarray(np.asarray(value))
    digest = hashlib.sha256()
    digest.update(str(array.dtype).encode("ascii"))
    digest.update(str(array.shape).encode("ascii"))
    digest.update(array.tobytes(order="C"))
    return digest.hexdigest()


def atomic_json(path: Path, value: object) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(json.dumps(
        value,
        indent=2,
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
        default=lambda item: item.item() if isinstance(item, np.generic) else str(item),
    ).encode("utf-8") + b"\n")
    os.replace(temporary, path)
    json.loads(path.read_text(encoding="utf-8"))
    if path.stat().st_size <= 0:
        raise RuntimeError("V35_JSON_ZERO_SIZE_AFTER_WRITE")
    return sha256_file(path)


def atomic_csv(path: Path, rows: Sequence[Mapping[str, object]], fieldnames: Sequence[str]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(fieldnames), extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    with path.open(encoding="utf-8", newline="") as stream:
        reloaded = list(csv.DictReader(stream))
    if len(reloaded) != len(rows):
        raise RuntimeError("V35_CSV_RELOAD_ROW_COUNT")
    return sha256_file(path)


def validate_npz(
    path: Path,
    expected_shapes: Mapping[str, tuple[int, ...]],
    *,
    require_finite: Iterable[str] = (),
) -> dict[str, object]:
    if not path.is_file() or path.stat().st_size <= 0:
        raise RuntimeError("V35_NPZ_MISSING_OR_EMPTY")
    finite = set(require_finite)
    observed: dict[str, list[int]] = {}
    with np.load(path, allow_pickle=False) as payload:
        missing = sorted(set(expected_shapes) - set(payload.files))
        if missing:
            raise RuntimeError("V35_NPZ_ARRAY_MISSING:" + ",".join(missing))
        for name, shape in expected_shapes.items():
            array = np.asarray(payload[name])
            if array.shape != tuple(shape):
                raise RuntimeError(f"V35_NPZ_SHAPE:{name}:{array.shape}:{shape}")
            if name in finite and not np.isfinite(array).all():
                raise RuntimeError(f"V35_NPZ_NONFINITE:{name}")
            observed[name] = list(array.shape)
    return {"path": str(path), "sha256": sha256_file(path), "shapes": observed, "status": "PASS"}


def atomic_npz(
    path: Path,
    arrays: Mapping[str, object],
    expected_shapes: Mapping[str, tuple[int, ...]],
    *,
    require_finite: Iterable[str] = (),
) -> dict[str, object]:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("wb") as stream:
        np.savez_compressed(stream, **arrays)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    return validate_npz(path, expected_shapes, require_finite=require_finite)


@dataclass(frozen=True)
class CheckpointDependencies:
    code_HEAD: str
    science_authority_SHA: str
    forecast_SHA: str
    route_table_SHA: str | None
    AIDC_schedule_SHA: str
    MESS_trajectory_SHA: str | None
    combined_schedule_SHA: str
    Planning_SHA: str
    Fresh_SHA: str
    Actual_SHA: str
    solver_settings_SHA: str
    storage_schema_SHA: str

    def validate(self) -> None:
        for name, value in asdict(self).items():
            allowed_lengths = {40, 64} if name == "code_HEAD" else {64}
            if value is not None and (
                not isinstance(value, str)
                or len(value) not in allowed_lengths
                or any(character not in "0123456789abcdef" for character in value.lower())
            ):
                raise ValueError(f"V35_CHECKPOINT_DEPENDENCY_SHA:{name}")


def checkpoint_payload(
    *,
    phase: str,
    day: str,
    case: str,
    run_id: str,
    timestamp: str,
    dependencies: CheckpointDependencies,
    status: str = "PASS",
    storage_files: Sequence[Mapping[str, object]] = (),
) -> dict[str, object]:
    dependencies.validate()
    payload = {
        "phase": phase,
        "day": day,
        "case": case,
        "run_id": run_id,
        **asdict(dependencies),
        "status": status,
        "timestamp": timestamp,
        "storage_files": list(storage_files),
    }
    missing = sorted(set(CHECKPOINT_FIELDS) - set(payload))
    if missing:
        raise RuntimeError("V35_CHECKPOINT_SCHEMA_MISSING:" + ",".join(missing))
    return payload


def checkpoint_is_reusable(path: Path, expected: CheckpointDependencies) -> bool:
    try:
        expected.validate()
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return False
    if payload.get("status") != "PASS" or any(field not in payload for field in CHECKPOINT_FIELDS):
        return False
    if any(payload.get(name) != value for name, value in asdict(expected).items()):
        return False
    for record in payload.get("storage_files", []):
        try:
            artifact = Path(str(record["path"]))
            if not artifact.is_file() or artifact.stat().st_size <= 0 or sha256_file(artifact) != record["sha256"]:
                return False
        except (KeyError, OSError, TypeError):
            return False
    return True


def rebind_serialization_only_checkpoint(
    path: Path,
    *,
    old_code_head: str,
    new_code_head: str,
    history_path: Path,
) -> dict[str, object]:
    """Create a successor checkpoint without touching scientific bytes.

    This is limited to a reviewed serialization-only code change.  The old
    immutable checkpoint is copied to history, every referenced file is
    re-hashed, and only code_HEAD plus an explicit recovery ledger are changed.
    """

    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("status") != "PASS" or payload.get("code_HEAD") != old_code_head:
        raise RuntimeError("V35_SERIALIZATION_REBIND_SOURCE_CHECKPOINT")
    for record in payload.get("storage_files", []):
        artifact = Path(str(record["path"]))
        if not artifact.is_file() or sha256_file(artifact) != record["sha256"]:
            raise RuntimeError("V35_SERIALIZATION_REBIND_STORAGE_SHA")
    history_path.parent.mkdir(parents=True, exist_ok=True)
    if history_path.exists():
        raise FileExistsError("V35_SERIALIZATION_REBIND_HISTORY_EXISTS")
    history_path.write_bytes(path.read_bytes())
    if sha256_file(history_path) != sha256_file(path):
        raise RuntimeError("V35_SERIALIZATION_REBIND_HISTORY_SHA")
    payload["code_HEAD"] = new_code_head
    payload["recovery_rebind"] = {
        "classification": "ENGINEERING_SERIALIZATION_DEFECT",
        "old_code_HEAD": old_code_head,
        "new_code_HEAD": new_code_head,
        "scientific_files_changed": 0,
        "all_storage_file_SHAs_reverified": True,
        "immutable_pre_rebind_checkpoint": str(history_path.resolve()),
    }
    atomic_json(path, payload)
    return payload["recovery_rebind"]


def invalidation_scope(change_class: str) -> tuple[str, ...]:
    mapping = {
        "SERIALIZATION_REPORT_ONLY": ("ARTIFACT_REGENERATION",),
        "CASE_LOCAL_B0": ("B0",),
        "CASE_LOCAL_B1": ("B1",),
        "CASE_LOCAL_B2": ("B2",),
        "CASE_LOCAL_B3": ("B3",),
        "MESS_ONLY": ("B2", "B3"),
        "AIDC_ONLY": ("B1", "B3"),
        "COMMON_GRID_PHYSICAL_OBJECTIVE": ("B0", "B1", "B2", "B3"),
        "CORRECTION_CALCULATION": ("CORRECTION_FREEZE", "PROSPECTIVE_SELECTION", "CORRECTED_VALIDATION"),
    }
    if change_class not in mapping:
        raise ValueError("V35_UNKNOWN_INVALIDATION_CLASS")
    return mapping[change_class]


def storage_schema_sha256() -> str:
    return canonical_sha256({
        "version": "V35_STORAGE_SCHEMA_V1",
        "slots": SLOTS,
        "checkpoint_fields": list(CHECKPOINT_FIELDS),
        "numeric_policy": "FINITE_EXCEPT_EXPLICIT_NULL_OPTIONAL_SOLVER_FIELDS",
        "reload_required": True,
    })

"""Exact-byte lineage verification and canonical serialization."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

import numpy as np

from .contracts import AIDC_HEAD, MESS_HEAD, SCIENCE_AUTHORITIES, SOURCE_REPOSITORY


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False, default=_json_default,
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _json_default(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if hasattr(value, "to_dict"):
        return value.to_dict()
    raise TypeError(type(value).__name__)


def git_bytes(commit: str, path: str, repository: Path = SOURCE_REPOSITORY) -> bytes:
    return subprocess.check_output(
        ["git", "-C", str(repository), "show", f"{commit}:{path}"]
    )


def git_blob(commit: str, path: str, repository: Path = SOURCE_REPOSITORY) -> str:
    return subprocess.check_output(
        ["git", "-C", str(repository), "rev-parse", f"{commit}:{path}"],
        text=True, encoding="utf-8",
    ).strip()


def git_head(repository: Path) -> str:
    return subprocess.check_output(
        ["git", "-C", str(repository), "rev-parse", "HEAD"], text=True,
        encoding="utf-8",
    ).strip()


def verify_science() -> dict[str, Any]:
    rows: dict[str, Any] = {}
    for name, source in SCIENCE_AUTHORITIES.items():
        raw = git_bytes(str(source["commit"]), str(source["path"]))
        digest = hashlib.sha256(raw).hexdigest()
        blob = git_blob(str(source["commit"]), str(source["path"]))
        passed = digest == source["sha256"] and blob == source["git_blob"]
        rows[name] = {**source, "observed_sha256": digest, "observed_git_blob": blob, "PASS": passed}
        if not passed:
            raise RuntimeError(f"V36_FROZEN_SCIENCE_DRIFT:{name}")
    return {
        "contract_id": "V36_FROZEN_SCIENCE_MANIFEST_V1",
        "source_AIDC_HEAD": AIDC_HEAD,
        "source_MESS_HEAD": MESS_HEAD,
        "authorities": rows,
        "all_exact": True,
        "AIDC_science_changed": "NO",
        "MESS_science_changed": "NO",
        "C1_changed": "NO",
        "objective_changed": "NO",
        "IDC_LOCATION_CHANGED": "NO",
        "IDC_LOCATION_OPTIMIZATION_RUNS": 0,
    }


def source_json(name: str) -> dict[str, Any]:
    source = SCIENCE_AUTHORITIES[name]
    return json.loads(git_bytes(str(source["commit"]), str(source["path"])))

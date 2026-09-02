"""Deterministic V30 artifact writers and manifest."""

from __future__ import annotations

import csv
import hashlib
from pathlib import Path
from typing import Mapping, Sequence

from .contracts import write_json


def write_csv(path: Path, rows: Sequence[Mapping[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8", newline="\n")
        return
    fields = list(rows[0])
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def finalize_manifest(out: Path) -> dict[str, object]:
    target = out / "V30_ARTIFACT_SHA256.json"
    files = []
    for path in sorted(p for p in out.iterdir() if p.is_file() and p != target):
        files.append({"path": path.name, "sha256": sha256(path), "byte_count": path.stat().st_size})
    aggregate = hashlib.sha256("".join(f"{row['path']}:{row['sha256']}\n" for row in files).encode()).hexdigest()
    payload = {
        "artifact_id": "V30_ARTIFACT_SHA256_V1", "status": "PASS",
        "artifact_root": "dayahead/artifacts/v30_two_stage_aidc_recourse",
        "self_excluded": True, "file_count": len(files),
        "byte_count": sum(int(row["byte_count"]) for row in files),
        "aggregate_manifest_sha256": aggregate, "files": files,
    }
    write_json(target, payload)
    return payload

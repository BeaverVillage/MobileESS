"""Archive the incomplete Apr-04 schema-failure attempt without hiding it."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from dayahead.v29r1.source_resume import write_json
from dayahead.v29r2.anchor_forensic import OUT_REL


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    repo = Path(__file__).resolve().parents[2]
    out = repo / OUT_REL
    archive = repo / "cache/v29r2_failed_attempts/apr04_schema_failure_e7c3943"
    archive.mkdir(parents=True, exist_ok=False)
    candidates = sorted(out.glob("V29R2_APR04_*"))
    if not candidates:
        raise RuntimeError("V29R2_NO_INCOMPLETE_APR04_ARTIFACTS_TO_ARCHIVE")
    records = []
    for source in candidates:
        if not source.is_file():
            raise RuntimeError(f"V29R2_UNEXPECTED_APR04_PATH:{source}")
        records.append({
            "name": source.name,
            "byte_count": source.stat().st_size,
            "sha256": _sha256(source),
        })
        shutil.move(str(source), str(archive / source.name))
    payload = {
        "artifact_id": "V29R2_APR04_FAILED_ATTEMPT_2_V1",
        "status": "INVALIDATED_IMPLEMENTATION_BUG",
        "marker_head": "e7c3943",
        "freeze_head": "2c1b6c8112a0a1b0afd38db9f3ad677f9400c225",
        "failure": "V29R2_APR04_COMPARISON_HETEROGENEOUS_CSV_SCHEMA",
        "failure_stage": "final V29 read-only comparison CSV serialization",
        "Actual_optimizer_calls": 0,
        "scientific_results_authorized": False,
        "archived_file_count": len(records),
        "archived_files": records,
        "archive_location": str(archive),
        "next_action": "fix schema only, rerun full regression and preservation, create a replacement freeze, rerun Apr-04 from the beginning",
    }
    write_json(out / "V29R2_APR04_FAILED_ATTEMPT_2.json", payload)
    print(json.dumps({"status": payload["status"], "archived": len(records)}))


if __name__ == "__main__":
    main()

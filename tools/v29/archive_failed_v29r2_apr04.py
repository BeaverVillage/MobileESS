"""Archive an invalidated Apr-04 attempt without hiding it."""

from __future__ import annotations

import argparse
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
    parser = argparse.ArgumentParser()
    parser.add_argument("--attempt", type=int, required=True)
    parser.add_argument("--marker-head", required=True)
    parser.add_argument("--freeze-head", required=True)
    parser.add_argument("--failure", required=True)
    parser.add_argument("--failure-stage", required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    out = repo / OUT_REL
    archive = repo / f"cache/v29r2_failed_attempts/apr04_attempt_{args.attempt}_{args.marker_head[:7]}"
    archive.mkdir(parents=True, exist_ok=False)
    candidates = sorted(
        path for path in out.glob("V29R2_APR04_*")
        if not path.name.startswith("V29R2_APR04_FAILED_ATTEMPT_")
    )
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
        "artifact_id": f"V29R2_APR04_FAILED_ATTEMPT_{args.attempt}_V1",
        "status": "INVALIDATED_IMPLEMENTATION_BUG",
        "marker_head": args.marker_head,
        "freeze_head": args.freeze_head,
        "failure": args.failure,
        "failure_stage": args.failure_stage,
        "Actual_optimizer_calls": 0,
        "scientific_results_authorized": False,
        "archived_file_count": len(records),
        "archived_files": records,
        "archive_location": str(archive),
        "next_action": "fix schema only, rerun full regression and preservation, create a replacement freeze, rerun Apr-04 from the beginning",
    }
    write_json(out / f"V29R2_APR04_FAILED_ATTEMPT_{args.attempt}.json", payload)
    print(json.dumps({"status": payload["status"], "archived": len(records)}))


if __name__ == "__main__":
    main()

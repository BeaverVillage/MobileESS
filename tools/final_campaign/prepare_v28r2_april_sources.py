#!/usr/bin/env python3
"""Execute and freeze V28R2 April 30/30 source coverage."""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from dayahead.v28r2.source_manifest import CATEGORIES, sha256_file, verify_day_manifest
from dayahead.v28r2.source_preflight import APRIL_DAYS, day_root, prepare_all

OUT = REPO / "dayahead/artifacts/v28r2_heavy_backend"


def atomic_json(path: Path, payload: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gfs-workers", type=int, default=12)
    parser.add_argument("--rebuild", action="store_true", help="rematerialize source files instead of verifying the frozen cache")
    parser.add_argument("--freeze-authority-artifacts", action="store_true", help="rewrite tracked authority summaries (release engineering only)")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    manifests = (
        prepare_all(REPO, gfs_workers=args.gfs_workers)
        if args.rebuild
        else {day: day_root(REPO, day) / "source_day_manifest.json" for day in APRIL_DAYS}
    )
    rows = []
    hashes = {}
    for day in APRIL_DAYS:
        path = manifests[day]
        payload = json.loads(path.read_text(encoding="utf-8"))
        verify_day_manifest(payload, base_dir=path.parent)
        hashes[path.relative_to(REPO).as_posix()] = sha256_file(path)
        for category in CATEGORIES:
            evidence = payload["categories"][category]
            rows.append({
                "day": day, "category": category, "status": evidence["status"],
                "path": evidence.get("path", ""), "sha256": evidence.get("sha256", ""),
                "authority_evidence": evidence.get("authority_evidence", ""),
            })
    ready = len(rows) == 30 * 13 and all(row["status"] in {"SOURCE_PRESENT", "MATERIALIZED", "NOT_APPLICABLE_BY_AUTHORITY"} for row in rows)
    coverage = {
        "artifact_id": "V28R2_APRIL_SOURCE_COVERAGE_V1",
        "status": "PASS" if ready else "V28R2_BLOCK_APRIL_SOURCE_COVERAGE_INCOMPLETE",
        "required_days": list(APRIL_DAYS), "required_day_count": 30,
        "covered_day_count": len(manifests), "required_categories": list(CATEGORIES),
        "category_count_per_day": 13, "matrix_row_count": len(rows),
        "GFS_contract": {"cycle": "06Z D-1", "leads": "f008-f032", "full_GRIB_download_count": 0},
        "forecast_for_actual_substitution_count": 0,
        "APRIL_SOURCE_COVERAGE_READY": ready,
        "mode": "REBUILD" if args.rebuild else "VERIFY_EXISTING_READ_ONLY",
    }
    if args.freeze_authority_artifacts:
        matrix = OUT / "V28R2_APRIL_SOURCE_AUTHORITY_MATRIX.csv"
        temporary = matrix.with_suffix(".tmp")
        with temporary.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader(); writer.writerows(rows)
        os.replace(temporary, matrix)
        frozen_coverage = dict(coverage)
        frozen_coverage.pop("mode", None)
        atomic_json(OUT / "V28R2_APRIL_SOURCE_COVERAGE.json", frozen_coverage)
        hashes[matrix.relative_to(REPO).as_posix()] = sha256_file(matrix)
        atomic_json(OUT / "V28R2_APRIL_SOURCE_SHA256.json", {
            "artifact_id": "V28R2_APRIL_SOURCE_SHA256_V1", "files": hashes,
        })
    if args.json:
        print(json.dumps(coverage, indent=2))
    else:
        print(f"[source {'PASS' if ready else 'FAIL'}] {len(manifests)}/30 days | {len(rows)}/390 categories | {coverage['mode']}")
    return 0 if ready else 2


if __name__ == "__main__":
    raise SystemExit(main())

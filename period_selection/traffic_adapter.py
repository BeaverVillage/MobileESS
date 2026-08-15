"""Materialize identical 2024/2025 traffic features from the frozen SCATS pipeline."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd

from period_selection.feature_builder import TRAFFIC_FREEZE, _traffic_features, fixed_aest_axis


def sha256_file(path: Path, chunk_size: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def materialize_traffic_years(
    traffic_root: Path,
    output_dir: Path,
    threshold: float,
    verify_daily_hashes: bool = True,
) -> dict[str, Any]:
    global TRAFFIC_FREEZE
    TRAFFIC_FREEZE = traffic_root
    # _traffic_features reads its module-level binding; update it explicitly.
    import period_selection.feature_builder as builder
    builder.TRAFFIC_FREEZE = traffic_root

    manifest_path = traffic_root / "freeze_assets/dataset/date_splits_2019_2025.csv"
    manifest = pd.read_csv(manifest_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    audits = []
    artifacts = {}
    for year in (2024, 2025):
        rows = manifest[manifest["year"] == year].sort_values("date")
        expected_days = 366 if year == 2024 else 365
        missing_files = []
        hash_mismatches = []
        bad_row_contract = []
        for row in rows.itertuples(index=False):
            path = Path(row.final_parquet)
            if not path.is_file():
                missing_files.append(str(path))
                continue
            if int(row.rows) != 288 * 509:
                bad_row_contract.append(str(path))
            if verify_daily_hashes and sha256_file(path) != str(row.final_sha256):
                hash_mismatches.append(str(path))
        if len(rows) != expected_days or missing_files or hash_mismatches or bad_row_contract:
            raise ValueError(
                f"{year} traffic fails closed: days={len(rows)}, missing={len(missing_files)}, "
                f"hash_mismatch={len(hash_mismatches)}, row_contract={len(bad_row_contract)}"
            )
        features = _traffic_features(year, threshold)
        frame = pd.DataFrame({"timestamp_aest": fixed_aest_axis(year), **features})
        output_path = output_dir / f"SCATS_TRAFFIC_FEATURES_{year}_5MIN.parquet"
        frame.to_parquet(output_path, index=False, compression="zstd")
        artifact_hash = sha256_file(output_path)
        artifacts[output_path.name] = {"sha256": artifact_hash, "rows": len(frame)}
        audits.append({
            "year": year,
            "days": len(rows),
            "links_per_slot": 509,
            "slots_per_day": 288,
            "daily_rows": 288 * 509,
            "daily_files_hash_verified": len(rows) if verify_daily_hashes else 0,
            "missing_files": 0,
            "hash_mismatches": 0,
            "feature_columns": list(features),
            "traffic_congestion_tti_threshold": threshold,
        })
    payload = {
        "schema_version": "same_frozen_scats_adapter_2024_2025_v1",
        "manifest_path": str(manifest_path),
        "manifest_sha256": sha256_file(manifest_path),
        "years": audits,
        "artifacts": artifacts,
        "raw_zip_gate_note": "Processed features are materialized, but representative-week selection remains blocked until documented raw SCATS ZIPs are locally CRC/SHA-audited.",
    }
    (output_dir / "SCATS_TRAFFIC_ADAPTER_AUDIT_2024_2025.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--traffic-root", type=Path, default=TRAFFIC_FREEZE)
    parser.add_argument("--output-dir", type=Path, default=Path("period_selection/output"))
    parser.add_argument("--threshold", type=float, default=1.5)
    parser.add_argument("--skip-daily-hashes", action="store_true")
    args = parser.parse_args()
    payload = materialize_traffic_years(
        args.traffic_root, args.output_dir, args.threshold, not args.skip_daily_hashes
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

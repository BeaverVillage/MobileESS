"""Independently reproduce the K2/K3.5 F30 cohort from the raw Kestrel ZIP."""

from __future__ import annotations

import argparse
import json
import os
import re
import zipfile
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow.parquet as pq

from period_selection.kestrel_adapter import F30_SOURCE, F30_SOURCE_ROWS, EXPECTED_2025_F30_ROWS, _utc_bounds


RAW_KESTREL_ZIP = Path(os.environ.get(
    "MOBILE_ESS_KESTREL_RAW_ZIP",
    "data/raw/kestrel/esif.hpc.kestrel.job-anon.zip",
))
RAW_COLUMNS = [
    "id", "partition", "state_simple", "submit_time", "start_time", "end_time",
    "gpus_requested", "shared_job_count",
]
H100_PATTERN = re.compile(r"(?:^|,)gpu-h100(?:s|l)?(?:-stdby)?(?:$|,)")


def _read_raw_candidates(path: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    pieces = []
    partitions = []
    schemas: set[tuple[str, ...]] = set()
    with zipfile.ZipFile(path) as archive:
        names = sorted(name for name in archive.namelist() if name.endswith(".parquet"))
        for name in names:
            with archive.open(name) as stream:
                parquet = pq.ParquetFile(stream)
                schema = tuple(parquet.schema_arrow.names)
                schemas.add(schema)
                table = parquet.read(columns=RAW_COLUMNS)
            frame = table.to_pandas()
            raw_rows = len(frame)
            normalized = frame["partition"].fillna("").astype(str).str.lower().str.replace(" ", "", regex=False)
            mask = (
                normalized.str.contains(H100_PATTERN, regex=True)
                & frame["state_simple"].eq("COMPLETED")
                & pd.to_numeric(frame["gpus_requested"], errors="coerce").gt(0)
            )
            filtered = frame.loc[mask].copy()
            filtered["partition_norm"] = normalized.loc[mask]
            pieces.append(filtered)
            match = re.search(r"year=(\d{4})/month=(\d+)", name)
            partitions.append({
                "entry": name,
                "year": int(match.group(1)) if match else None,
                "month": int(match.group(2)) if match else None,
                "raw_rows": raw_rows,
                "h100_completed_positive_gpu_rows": len(filtered),
                "schema_column_count": len(schema),
            })
    candidates = pd.concat(pieces, ignore_index=True)
    audit = {
        "parquet_partitions": len(partitions),
        "partition_metadata": partitions,
        "total_raw_rows": sum(item["raw_rows"] for item in partitions),
        "h100_completed_positive_gpu_rows_before_dedup": len(candidates),
        "schema_variants": len(schemas),
        "schema_columns": list(next(iter(schemas))) if len(schemas) == 1 else [],
    }
    return candidates, audit


def reproduce_raw_f30(raw_zip: Path, processed_source: Path) -> dict[str, Any]:
    if not raw_zip.is_file():
        raise FileNotFoundError(raw_zip)
    candidates, raw_audit = _read_raw_candidates(raw_zip)
    for name in ("submit_time", "start_time", "end_time"):
        candidates[name] = pd.to_datetime(candidates[name], utc=True, errors="coerce")
    candidates = candidates.sort_values(
        ["id", "submit_time", "start_time", "end_time"], kind="stable", na_position="last"
    )
    candidates["duplicate_rank"] = candidates.groupby("id", sort=False).cumcount() + 1
    candidates["duplicate_id_count"] = candidates.groupby("id", sort=False)["id"].transform("size")
    runtime_s = (candidates["end_time"] - candidates["start_time"]).dt.total_seconds()
    queue_s = (candidates["start_time"] - candidates["submit_time"]).dt.total_seconds()
    clean_mask = (
        ~candidates["partition_norm"].str.contains("-stdby", regex=False)
        & candidates["submit_time"].notna()
        & candidates["start_time"].notna()
        & candidates["end_time"].notna()
        & runtime_s.gt(0)
        & queue_s.ge(0)
        & pd.to_numeric(candidates["gpus_requested"], errors="coerce").gt(0)
        & candidates["duplicate_rank"].eq(1)
    )
    clean = candidates.loc[clean_mask].copy()
    clean["runtime_s"] = runtime_s.loc[clean_mask]
    clean["queue_wait_s_calc"] = queue_s.loc[clean_mask]
    f30 = clean.loc[(clean["runtime_s"] >= 1800) & (clean["queue_wait_s_calc"] >= 900)].copy()

    processed = pd.read_parquet(processed_source, columns=["id", "is_flexible_F30", "submit_time_utc"])
    processed_f30 = processed.loc[processed["is_flexible_F30"].astype(bool)].copy()
    processed_f30["submit_time_utc"] = pd.to_datetime(processed_f30["submit_time_utc"], utc=True)
    years = []
    for year in (2024, 2025):
        start, end = _utc_bounds(year)
        raw_year = f30.loc[f30["submit_time"].ge(start) & f30["submit_time"].lt(end)]
        processed_year = processed_f30.loc[
            processed_f30["submit_time_utc"].ge(start) & processed_f30["submit_time_utc"].lt(end)
        ]
        raw_ids = set(raw_year["id"].astype(str))
        processed_ids = set(processed_year["id"].astype(str))
        years.append({
            "year": year,
            "raw_reproduced_f30_rows": len(raw_year),
            "raw_reproduced_unique_ids": len(raw_ids),
            "processed_f30_rows": len(processed_year),
            "id_sets_identical": raw_ids == processed_ids,
            "only_in_raw": len(raw_ids - processed_ids),
            "only_in_processed": len(processed_ids - raw_ids),
            "expected_frozen_2025_count_pass": year != 2025 or len(raw_year) == EXPECTED_2025_F30_ROWS,
        })
    payload = {
        "schema_version": "kestrel_raw_f30_reproduction_v1",
        "raw_zip": str(raw_zip),
        "processed_source": str(processed_source),
        "raw_archive": raw_audit,
        "contracts": {
            "h100_regex": H100_PATTERN.pattern,
            "state": "COMPLETED",
            "standby_excluded": True,
            "positive_gpu": True,
            "valid_time_order": True,
            "deduplicate_by_id": "earliest submit/start/end",
            "f30": "runtime_s >= 1800 AND queue_wait_s_calc >= 900",
            "fixed_year_axis": "AEST UTC+10 without DST",
        },
        "primary_clean_rows": len(clean),
        "processed_source_rows_expected": F30_SOURCE_ROWS,
        "primary_clean_count_matches_processed": len(clean) == F30_SOURCE_ROWS,
        "all_f30_rows": len(f30),
        "years": years,
        "pass": len(clean) == F30_SOURCE_ROWS and all(item["id_sets_identical"] for item in years),
    }
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-zip", type=Path, default=RAW_KESTREL_ZIP)
    parser.add_argument("--processed-source", type=Path, default=F30_SOURCE)
    parser.add_argument(
        "--output", type=Path,
        default=Path("period_selection/audit/KESTREL_RAW_F30_REPRODUCTION_2024_2025.json"),
    )
    args = parser.parse_args()
    payload = reproduce_raw_f30(args.raw_zip, args.processed_source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: payload[key] for key in ("primary_clean_rows", "all_f30_rows", "years", "pass")}, ensure_ascii=False, indent=2))
    return 0 if payload["pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

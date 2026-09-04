"""Read-only raw-data inventory and AIDC source coverage audit."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping, Sequence

from .authority import DEFAULT_RAW_ROOT, NLR_SOURCE_SHA256, sha256_file


class RawPreflightError(RuntimeError):
    pass


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _classify(relative: str) -> str:
    normalized = relative.casefold()
    if "nlr kestrel jobs" in normalized or "nlr hpc kestrel jobs" in normalized:
        return "KESTREL_JOBS"
    if "nlr esif pue" in normalized or "facility pue" in normalized or "pue·" in normalized:
        return "NLR_ESIF_PUE"
    if "h100b200" in normalized:
        return "H100_B200_TELEMETRY"
    if "scats" in normalized:
        return "SCATS"
    if normalized.startswith(("aemo/", "aemo\\")) or "/aemo/" in normalized or "\\aemo\\" in normalized:
        return "AEMO_DA"
    return "OTHER_RAW"


def inventory(raw_root: Path, *, full_hashes: bool) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not raw_root.is_dir():
        raise RawPreflightError("FAIL_RAW_DATA_ROOT_NOT_FOUND")
    records: list[dict[str, Any]] = []
    for path in sorted((item for item in raw_root.rglob("*") if item.is_file()), key=lambda item: item.as_posix().casefold()):
        stat = path.stat()
        relative = path.relative_to(raw_root).as_posix()
        record = {
            "relative_path": relative,
            "bytes": stat.st_size,
            "modified_time_utc": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
            "family": _classify(relative),
        }
        if full_hashes:
            record["sha256"] = sha256_file(path)
        records.append(record)
    counts = Counter(record["family"] for record in records)
    return records, {
        "file_count": len(records),
        "total_bytes": sum(record["bytes"] for record in records),
        "family_file_counts": dict(sorted(counts.items())),
        "full_file_sha256_complete": full_hashes,
    }


def zip_contract(path: Path) -> dict[str, Any]:
    with zipfile.ZipFile(path) as archive:
        files = [item for item in archive.infolist() if not item.is_dir()]
        extensions = Counter(PurePosixPath(item.filename).suffix.casefold() for item in files)
        months = sorted(
            {
                (int(match.group(1)), int(match.group(2)))
                for item in files
                if (match := re.search(r"year=(\d{4})/month=(\d{1,2})", item.filename))
            }
        )
        return {
            "path": str(path),
            "sha256": sha256_file(path),
            "member_count": len(files),
            "uncompressed_bytes": sum(item.file_size for item in files),
            "extensions": dict(sorted(extensions.items())),
            "hive_year_month_partitions": [f"{year:04d}-{month:02d}" for year, month in months],
            "first_members": [item.filename for item in files[:5]],
            "last_members": [item.filename for item in files[-5:]],
        }


def _parquet_module():
    try:
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise RawPreflightError("pyarrow is required for scientific parquet preflight") from exc
    return pq


def parquet_contract(path: Path, *, statistic_columns: Sequence[str]) -> dict[str, Any]:
    pq = _parquet_module()
    parquet = pq.ParquetFile(path)
    names = parquet.schema_arrow.names
    statistics: dict[str, Any] = {}
    for name in statistic_columns:
        if name not in names:
            statistics[name] = {"status": "MISSING_COLUMN"}
            continue
        index = names.index(name)
        minimum = None
        maximum = None
        null_count = 0
        groups_with_statistics = 0
        for group_index in range(parquet.metadata.num_row_groups):
            stats = parquet.metadata.row_group(group_index).column(index).statistics
            if stats is None:
                continue
            groups_with_statistics += 1
            null_count += int(stats.null_count or 0)
            if stats.has_min_max:
                minimum = stats.min if minimum is None or stats.min < minimum else minimum
                maximum = stats.max if maximum is None or stats.max > maximum else maximum
        statistics[name] = {
            "min": str(minimum),
            "max": str(maximum),
            "null_count": null_count,
            "row_groups_with_statistics": groups_with_statistics,
        }
    return {
        "path": str(path),
        "sha256": sha256_file(path),
        "rows": parquet.metadata.num_rows,
        "row_groups": parquet.metadata.num_row_groups,
        "schema": [str(field) for field in parquet.schema_arrow],
        "statistics": statistics,
    }


def zipped_parquet_contract(path: Path, *, statistic_columns: Sequence[str]) -> dict[str, Any]:
    pq = _parquet_module()
    members: list[dict[str, Any]] = []
    with zipfile.ZipFile(path) as archive, tempfile.TemporaryDirectory(prefix="aidc-preflight-") as temporary:
        temp = Path(temporary) / "member.parquet"
        for info in archive.infolist():
            if not info.filename.casefold().endswith(".parquet"):
                continue
            with archive.open(info) as source, temp.open("wb") as target:
                for block in iter(lambda: source.read(8 << 20), b""):
                    target.write(block)
            # Pass an owned stream instead of a path so Windows can close the
            # file deterministically before the temporary directory is removed.
            with temp.open("rb") as parquet_stream:
                parquet = pq.ParquetFile(parquet_stream)
                names = parquet.schema_arrow.names
                stats_result: dict[str, Any] = {}
                for name in statistic_columns:
                    if name not in names:
                        stats_result[name] = {"status": "MISSING_COLUMN"}
                        continue
                    index = names.index(name)
                    minimum = None
                    maximum = None
                    null_count = 0
                    for group_index in range(parquet.metadata.num_row_groups):
                        stats = parquet.metadata.row_group(group_index).column(index).statistics
                        if stats is None:
                            continue
                        null_count += int(stats.null_count or 0)
                        if stats.has_min_max:
                            minimum = stats.min if minimum is None or stats.min < minimum else minimum
                            maximum = stats.max if maximum is None or stats.max > maximum else maximum
                    stats_result[name] = {"min": str(minimum), "max": str(maximum), "null_count": null_count}
                members.append({
                    "member": info.filename,
                    "rows": parquet.metadata.num_rows,
                    "schema": [str(field) for field in parquet.schema_arrow],
                    "statistics": stats_result,
                })
                del parquet
    return {
        **zip_contract(path),
        "parquet_member_count": len(members),
        "rows": sum(item["rows"] for item in members),
        "members": members,
    }


def _required_path(root: Path, *parts: str) -> Path:
    path = root.joinpath(*parts)
    if not path.is_file():
        raise RawPreflightError(f"required raw source is missing: {path}")
    return path


def _choose_exact_source(raw_root: Path, filename: str, expected_sha256: str, *, required_member: str | None = None) -> tuple[Path, list[dict[str, object]]]:
    candidates = []
    for path in raw_root.rglob(filename):
        if required_member is not None:
            try:
                with zipfile.ZipFile(path) as archive:
                    if required_member not in archive.namelist():
                        continue
            except zipfile.BadZipFile:
                continue
        digest = sha256_file(path)
        candidates.append({"path": str(path), "bytes": path.stat().st_size, "sha256": digest})
    if not candidates:
        raise RawPreflightError(f"required raw source is missing: {filename}")
    if any(record["sha256"] != expected_sha256 for record in candidates):
        raise RawPreflightError(f"FAIL_RAW_SHA_MISMATCH:{filename}")
    return Path(str(candidates[0]["path"])), candidates


def audit(raw_root: Path, *, full_hashes: bool) -> dict[str, Any]:
    records, summary = inventory(raw_root, full_hashes=full_hashes)
    kestrel, kestrel_copies = _choose_exact_source(raw_root, "esif.hpc.kestrel.job-anon.zip", NLR_SOURCE_SHA256["kestrel_jobs_zip"])
    pue, pue_copies = _choose_exact_source(raw_root, "esif.influx.buildingData.PUE.combined.parquet", NLR_SOURCE_SHA256["esif_parquet"])
    esif_csv, esif_csv_copies = _choose_exact_source(raw_root, "esif.influx.buildingData.PUE.combined.csv.zip", NLR_SOURCE_SHA256["esif_official_csv_zip"])
    dataset312, dataset312_copies = _choose_exact_source(
        raw_root, "dataset.zip", NLR_SOURCE_SHA256["dataset312_zip"],
        required_member="01_aggregated_datasets/training/metadata.csv",
    )
    kestrel_audit = zipped_parquet_contract(
        kestrel,
        statistic_columns=("id", "submit_time", "start_time", "end_time", "gpus_requested", "partition", "state_simple"),
    )
    pue_audit = parquet_contract(pue, statistic_columns=("ts", "it_power_kw", "pue"))
    esif_csv_audit = zip_contract(esif_csv)
    dataset312_audit = zip_contract(dataset312)
    failures: list[str] = []
    findings: list[str] = []
    pue_last = pue_audit["statistics"]["ts"]["max"]
    if pue_last < "2025-06-25":
        failures.append("AIDC_P_REF_LABEL_REQUIRED_JUN25_COVERAGE_MISSING")
    if "2025-06" not in kestrel_audit["hive_year_month_partitions"]:
        failures.append("AIDC_W_G_LABEL_REQUIRED_JUN25_COVERAGE_MISSING")
    if not full_hashes:
        failures.append("FULL_RAW_INVENTORY_SHA256_NOT_MATERIALIZED")
    aemo_files = [record for record in records if record["family"] == "AEMO_DA" and record["relative_path"].casefold().endswith(".zip")]
    scats_files = [record for record in records if record["family"] == "SCATS" and record["relative_path"].casefold().endswith(".zip")]
    if not aemo_files:
        failures.append("FAIL_AEMO_SOURCE_NOT_FOUND")
    if not scats_files:
        failures.append("FAIL_SCATS_SOURCE_NOT_FOUND")
    return {
        "authority_id": "AIDC_RAW_PREFLIGHT_V16",
        "raw_root": str(raw_root),
        "read_only_source_root": True,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS" if not failures else "FAIL",
        "failures": failures,
        "scientific_coverage_findings": findings,
        "inventory_summary": summary,
        "inventory": records,
        "key_sources": {
            "kestrel_jobs": {**kestrel_audit, "copies": kestrel_copies},
            "nlr_esif_pue_it_power": {**pue_audit, "copies": pue_copies},
            "nlr_esif_official_csv_timezone_authority": {**esif_csv_audit, "copies": esif_csv_copies},
            "dataset312_parameter_only": {**dataset312_audit, "copies": dataset312_copies},
            "aemo_archive_file_count": len(aemo_files),
            "scats_archive_file_count": len(scats_files),
        },
        "source_hierarchy": "ESIF_FACILITY_TOTAL_IT_PLUS_KESTREL_SUBSYSTEM_STATE;DATASET312_PARAMETER_ONLY",
        "polaris_york_excluded": True,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-root", type=Path, default=DEFAULT_RAW_ROOT)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--full-inventory-hashes", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = audit(args.raw_root, full_hashes=args.full_inventory_hashes)
    except RawPreflightError as exc:
        result = {
            "authority_id": "AIDC_RAW_PREFLIGHT_V1",
            "raw_root": str(args.raw_root),
            "status": "FAIL",
            "failures": [str(exc)],
        }
    _atomic_json(args.output, result)
    print(json.dumps({"status": result["status"], "failures": result.get("failures", [])}, ensure_ascii=False))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())

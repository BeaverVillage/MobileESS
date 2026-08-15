"""Audit the local 2024/2025 raw sources used for period selection.

This module is deliberately read-only.  It distinguishes a file documented in
Google Drive from a file that is physically available to the local pipeline,
verifies ZIP CRCs and SHA-256, and audits the three AEMO VIC1 series without
silently repairing gaps.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import re
import zipfile
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable


RAW_ROOT = Path(os.environ.get("MOBILE_ESS_RAW_ROOT", "data/raw"))

SCATS_DRIVE_INVENTORY = {
    "traffic_signal_volume_data_2024.zip": ("1BwbzjwaNKRjwvhEkKV1ZD8ABPZpFLn7m", 1_891_703_241),
    "traffic_signal_volume_data_january_2025.zip": ("1Zkfj1VPFarW1bR4DoXL-QnGwLItL8ldw", None),
    "traffic_signal_volume_data_february_2025.zip": ("1aI-sv-MHqrhhqIGPFAdwOSWXQtjXNSQG", None),
    "traffic_signal_volume_data_march_2025.zip": ("1GpXx03gV4oFwjqUf_bDC6-hB9tOprHiC", None),
    "traffic_signal_volume_data_april_2025.zip": ("15JBc9nrrhGiDTILeQQFhv40CBCI0Cci2", None),
    "traffic_signal_volume_data_may_2025.zip": ("1krCdsZH7JoiServewicR0v1AauNpo7BQ", None),
    "traffic_signal_volume_data_june_2025.zip": ("1eu6ah7Vke-e_EI9xguezi2bykGIJDu5m", None),
    "traffic_signal_volume_data_july_2025.zip": ("1xS18TdQNMhuJ0gqtSm-bdeiA21hLu2zz", None),
    "traffic_signal_volume_data_august_2025.zip": ("1B0imWIDZnyajCSgdX50LMQtk4oKZRy20", None),
    "traffic_signal_volume_data_september_2025.zip": ("1lmw86hy2T7Vv7sYrHgPP8iXZ0UXBHu0k", None),
    "traffic_signal_volume_data_october_2025.zip": ("1L9OqZ2UZ3oxFH1GZNTvJt-lCNr_ieCLV", None),
    "traffic_signal_volume_data_november_2025.zip": ("1zrSbIyWsHpP8P3Iv9CmYDR5g78rviVf_", None),
    "traffic_signal_volume_data_december_2025.zip": ("1RC8WmzR2fblciAqfdbSPYA7z8cfsGsmo", None),
}

AEMO_CONTRACTS = {
    "DISPATCHREGIONSUM": {
        "table": ("DISPATCH", "REGIONSUM"),
        "timestamp": "SETTLEMENTDATE",
        "value": "TOTALDEMAND",
        "resolution_minutes": 5,
    },
    "DISPATCHPRICE": {
        "table": ("DISPATCH", "PRICE"),
        "timestamp": "SETTLEMENTDATE",
        "value": "RRP",
        "resolution_minutes": 5,
    },
    "ROOFTOP_PV_ACTUAL": {
        "table": ("ROOFTOP", "ACTUAL"),
        "timestamp": "INTERVAL_DATETIME",
        "value": "POWER",
        "resolution_minutes": 30,
    },
}


@dataclass
class ZipAudit:
    family: str
    year: int | None
    path: str
    filename: str
    documented_drive_id: str | None = None
    expected_size_bytes: int | None = None
    physically_found: bool = False
    size_bytes: int | None = None
    sha256: str | None = None
    zip_crc_ok: bool = False
    zip_entry_count: int | None = None
    status: str = "LOCAL_MISSING"
    reason: str = ""


@dataclass
class SeriesAudit:
    family: str
    year: int
    source_files: list[str]
    schema_versions: list[str] = field(default_factory=list)
    selected_rows: int = 0
    unique_timestamps: int = 0
    expected_timestamps: int = 0
    exact_duplicate_rows: int = 0
    conflicting_duplicate_timestamps: int = 0
    blank_value_rows: int = 0
    blank_value_timestamps: list[str] = field(default_factory=list)
    nonfinite_value_rows: int = 0
    nonfinite_value_timestamps: list[str] = field(default_factory=list)
    missing_timestamps: list[str] = field(default_factory=list)
    first_timestamp: str | None = None
    last_timestamp: str | None = None
    minimum: float | None = None
    maximum: float | None = None
    status: str = "UNAUDITED"
    repair_applied: bool = False
    repair_policy: str = "NONE_FAIL_CLOSED"


def sha256_file(path: Path, chunk_size: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def audit_zip(path: Path, family: str, year: int | None = None,
              drive_id: str | None = None, expected_size: int | None = None) -> ZipAudit:
    record = ZipAudit(
        family=family,
        year=year,
        path=str(path),
        filename=path.name,
        documented_drive_id=drive_id,
        expected_size_bytes=expected_size,
    )
    if not path.is_file():
        record.reason = "Documented Drive file is not physically present under the local raw-data root."
        return record
    record.physically_found = True
    record.size_bytes = path.stat().st_size
    record.sha256 = sha256_file(path)
    try:
        with zipfile.ZipFile(path) as archive:
            record.zip_entry_count = len(archive.infolist())
            bad = archive.testzip()
        record.zip_crc_ok = bad is None
        record.status = "VERIFIED_LOCAL" if record.zip_crc_ok else "CRC_FAILED"
        record.reason = "SHA-256 recorded and all ZIP entry CRCs passed." if bad is None else f"CRC failed: {bad}"
    except (OSError, zipfile.BadZipFile) as error:
        record.status = "INVALID_ZIP"
        record.reason = str(error)
    if expected_size is not None and record.size_bytes != expected_size:
        record.status = "SIZE_MISMATCH"
        record.reason = f"Local size {record.size_bytes} differs from Drive metadata {expected_size}."
    return record


def _aemo_paths(raw_root: Path, family: str, year: int) -> list[Path]:
    if year == 2024:
        root = raw_root / f"2024 {family}"
        return sorted(root.glob("*.zip"))
    if family in ("DISPATCHREGIONSUM", "DISPATCHPRICE"):
        root = raw_root / "전력 데이터 AEMO Victoria"
        return sorted(p for p in root.glob("*.zip") if family in p.name and "2025" in p.name)
    root = raw_root / "AEMO rooftop PV 자료"
    return sorted(p for p in root.rglob("*.zip") if family in p.name and "2025" in p.name)


def _parse_timestamp(value: str) -> datetime:
    return datetime.strptime(value.strip().strip('"'), "%Y/%m/%d %H:%M:%S")


def _expected_interval_ending(year: int, minutes: int) -> list[datetime]:
    start = datetime(year, 1, 1) + timedelta(minutes=minutes)
    end = datetime(year + 1, 1, 1)
    count = int((end - datetime(year, 1, 1)).total_seconds() // (minutes * 60))
    return [start + i * timedelta(minutes=minutes) for i in range(count)]


def _iter_aemo_rows(paths: Iterable[Path], table: tuple[str, str]) -> Iterable[tuple[str, dict[str, str]]]:
    for path in paths:
        with zipfile.ZipFile(path) as archive:
            for member in archive.infolist():
                if member.is_dir() or not member.filename.upper().endswith(".CSV"):
                    continue
                headers: dict[tuple[str, str, str], list[str]] = {}
                with archive.open(member) as raw, io.TextIOWrapper(raw, encoding="utf-8-sig", errors="replace", newline="") as text:
                    for row in csv.reader(text):
                        if len(row) < 4:
                            continue
                        key = (row[1].strip(), row[2].strip(), row[3].strip())
                        if row[0] == "I":
                            headers[key] = row[4:]
                        elif row[0] == "D" and key[:2] == table and key in headers:
                            values = row[4:]
                            if len(values) < len(headers[key]):
                                values += [""] * (len(headers[key]) - len(values))
                            yield key[2], dict(zip(headers[key], values))


def audit_aemo_series(paths: list[Path], family: str, year: int) -> SeriesAudit:
    contract = AEMO_CONTRACTS[family]
    audit = SeriesAudit(family=family, year=year, source_files=[str(p) for p in paths])
    values_by_timestamp: dict[datetime, list[float | None]] = defaultdict(list)
    versions: set[str] = set()
    for version, row in _iter_aemo_rows(paths, contract["table"]):
        if row.get("REGIONID") != "VIC1":
            continue
        if family != "ROOFTOP_PV_ACTUAL" and row.get("INTERVENTION", "0") not in ("", "0"):
            continue
        if family == "ROOFTOP_PV_ACTUAL" and row.get("TYPE") != "MEASUREMENT":
            continue
        timestamp_text = row.get(contract["timestamp"], "")
        if not timestamp_text:
            continue
        timestamp = _parse_timestamp(timestamp_text)
        axis_start = datetime(year, 1, 1)
        axis_end = datetime(year + 1, 1, 1)
        if not (axis_start < timestamp <= axis_end):
            continue
        raw_value = row.get(contract["value"], "").strip()
        value: float | None
        if not raw_value:
            value = None
            audit.blank_value_rows += 1
            audit.blank_value_timestamps.append(timestamp.isoformat(sep=" "))
        else:
            try:
                value = float(raw_value)
                if value != value or value in (float("inf"), float("-inf")):
                    audit.nonfinite_value_rows += 1
                    audit.nonfinite_value_timestamps.append(timestamp.isoformat(sep=" "))
            except ValueError:
                value = None
                audit.nonfinite_value_rows += 1
                audit.nonfinite_value_timestamps.append(timestamp.isoformat(sep=" "))
        values_by_timestamp[timestamp].append(value)
        audit.selected_rows += 1
        versions.add(version)

    expected = _expected_interval_ending(year, int(contract["resolution_minutes"]))
    expected_set = set(expected)
    audit.expected_timestamps = len(expected)
    audit.unique_timestamps = len(values_by_timestamp)
    audit.schema_versions = sorted(versions)
    audit.missing_timestamps = [x.isoformat(sep=" ") for x in expected if x not in values_by_timestamp]
    finite_values: list[float] = []
    for timestamp, observations in values_by_timestamp.items():
        if len(observations) > 1:
            first = observations[0]
            if all(value == first for value in observations[1:]):
                audit.exact_duplicate_rows += len(observations) - 1
            else:
                audit.conflicting_duplicate_timestamps += 1
        finite_values.extend(value for value in observations if value is not None and value == value)
    if values_by_timestamp:
        audit.first_timestamp = min(values_by_timestamp).isoformat(sep=" ")
        audit.last_timestamp = max(values_by_timestamp).isoformat(sep=" ")
    if finite_values:
        audit.minimum = min(finite_values)
        audit.maximum = max(finite_values)
    invalid_extra = len(set(values_by_timestamp) - expected_set)
    unresolved = (
        len(paths) != 12
        or bool(audit.missing_timestamps)
        or audit.blank_value_rows > 0
        or audit.nonfinite_value_rows > 0
        or audit.conflicting_duplicate_timestamps > 0
        or invalid_extra > 0
    )
    if unresolved:
        audit.status = "AVAILABLE_WITH_UNRESOLVED_GAPS"
    elif audit.exact_duplicate_rows:
        audit.status = "VERIFIED_COMPLETE_AFTER_EXACT_DEDUPLICATION"
    else:
        audit.status = "VERIFIED_COMPLETE"
    return audit


def _traffic_records(raw_root: Path) -> list[ZipAudit]:
    traffic_root = raw_root / "교통 장기 데이터 Victoria SCATS"
    local_by_name = {p.name.lower(): p for p in traffic_root.rglob("*.zip")} if traffic_root.is_dir() else {}
    records = []
    for name, (drive_id, expected_size) in SCATS_DRIVE_INVENTORY.items():
        local = local_by_name.get(name.lower(), traffic_root / name)
        year = 2024 if "2024" in name else 2025
        records.append(audit_zip(local, "SCATS", year, drive_id, expected_size))
    return records


def build_raw_audit(raw_root: Path = RAW_ROOT, verify_all_zip_hashes: bool = True) -> dict[str, Any]:
    zip_records: list[ZipAudit] = []
    series_records: list[SeriesAudit] = []
    for year in (2024, 2025):
        for family in AEMO_CONTRACTS:
            paths = _aemo_paths(raw_root, family, year)
            for path in paths:
                if verify_all_zip_hashes:
                    zip_records.append(audit_zip(path, family, year))
            series_records.append(audit_aemo_series(paths, family, year))
    zip_records.extend(_traffic_records(raw_root))
    kestrel_candidates = list(raw_root.rglob("esif.hpc.kestrel.job-anon.zip"))
    if kestrel_candidates:
        zip_records.append(audit_zip(kestrel_candidates[0], "KESTREL_JOBS", None))
    else:
        zip_records.append(audit_zip(raw_root / "esif.hpc.kestrel.job-anon.zip", "KESTREL_JOBS", None))

    scats_missing = [r.filename for r in zip_records if r.family == "SCATS" and not r.physically_found]
    aemo_unresolved = [f"{r.year}:{r.family}" for r in series_records if not r.status.startswith("VERIFIED_COMPLETE")]
    kestrel_ok = any(r.family == "KESTREL_JOBS" and r.status == "VERIFIED_LOCAL" for r in zip_records)
    summary = {
        "schema_version": "rep_period_raw_inventory_v2",
        "raw_root": str(raw_root),
        "new_external_download_required": False,
        "existing_drive_sync_required": bool(scats_missing),
        "scats_local_missing": scats_missing,
        "aemo_unresolved": aemo_unresolved,
        "kestrel_local_verified": kestrel_ok,
        "period_selection_gate": "BLOCKED" if scats_missing or aemo_unresolved or not kestrel_ok else "READY",
        "restrictions": [
            "No Gurobi, R25T, R25V, R26, SUMO, OpenDSS, or controller execution.",
            "No silent repair or imputation of source gaps.",
            "DISPATCHREGIONSUM.TOTALDEMAND is a regional-pattern feature, not a 131-bus feeder tensor.",
            "WAN is Job-derived as arriving GPUh multiplied by 3 GB/GPUh.",
        ],
    }
    return {
        "summary": summary,
        "zip_files": [asdict(r) for r in zip_records],
        "aemo_series": [asdict(r) for r in series_records],
    }


def write_raw_audit(payload: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "REP_PERIOD_RAW_INVENTORY_2024_2025.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with (output_dir / "REP_PERIOD_RAW_FILES_2024_2025.csv").open("w", encoding="utf-8", newline="") as stream:
        rows = payload["zip_files"]
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    summary = payload["summary"]
    lines = [
        "# 2024–2025 representative-period raw-data audit", "",
        f"- Selection gate: **{summary['period_selection_gate']}**",
        f"- New external dataset required: **{str(summary['new_external_download_required']).lower()}**",
        f"- Existing Drive files requiring local sync: **{len(summary['scats_local_missing'])}**", "",
        "## AEMO series", "",
        "| Year | Family | Status | Rows | Unique | Expected | Exact duplicates | Blank | Missing |",
        "|---:|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for record in payload["aemo_series"]:
        lines.append(
            f"| {record['year']} | {record['family']} | {record['status']} | {record['selected_rows']} | "
            f"{record['unique_timestamps']} | {record['expected_timestamps']} | {record['exact_duplicate_rows']} | "
            f"{record['blank_value_rows']} | {len(record['missing_timestamps'])} |"
        )
    lines += ["", "## Unresolved AEMO timestamps", ""]
    unresolved = [record for record in payload["aemo_series"] if record["status"] == "AVAILABLE_WITH_UNRESOLVED_GAPS"]
    for record in unresolved:
        lines.append(f"### {record['year']} {record['family']}")
        lines.append("")
        lines.append(f"- Missing: {', '.join(f'`{value}`' for value in record['missing_timestamps']) or 'None'}")
        lines.append(f"- Blank: {', '.join(f'`{value}`' for value in record['blank_value_timestamps']) or 'None'}")
        lines.append("- Repair: none; fail closed pending an explicitly approved repair rule.")
        lines.append("")
    lines += ["", "## Local SCATS gaps", ""]
    lines += [f"- `{name}`" for name in summary["scats_local_missing"]] or ["- None"]
    lines += ["", "No missing source is replaced by a different dataset, and no AEMO gap is silently imputed."]
    (output_dir / "REP_PERIOD_RAW_AUDIT_2024_2025.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-root", type=Path, default=RAW_ROOT)
    parser.add_argument("--output-dir", type=Path, default=Path("period_selection/audit"))
    parser.add_argument("--skip-aemo-zip-hashes", action="store_true")
    args = parser.parse_args()
    payload = build_raw_audit(args.raw_root, not args.skip_aemo_zip_hashes)
    write_raw_audit(payload, args.output_dir)
    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))
    return 0 if payload["summary"]["period_selection_gate"] == "READY" else 2


if __name__ == "__main__":
    raise SystemExit(main())

"""Fail-closed official AEMO D-1 vintage selection for V16.1.

Only an explicitly supplied monthly archive is opened.  Callers inventorying
locked months must use ordinary file stat/hash operations and must never pass
those archives to the selectors in this module.
"""

from __future__ import annotations

import csv
import io
import json
import zipfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from typing import Iterable


FIXED_AEST = timezone(timedelta(hours=10), name="AEST")
OPERATING_DAY = "2025-04-15"
CUTOFF = datetime(2025, 4, 14, 18, 0, tzinfo=FIXED_AEST)
SOURCE_TIMESTAMPS = tuple(
    datetime(2025, 4, 15, 0, 30, tzinfo=FIXED_AEST) + timedelta(minutes=30 * index)
    for index in range(48)
)


class AEMOVintageError(RuntimeError):
    """A source cannot produce one eligible, complete next-day vintage."""


@dataclass(frozen=True)
class SelectedVintage:
    family: str
    archive_path: str
    archive_sha256: str
    member_name: str
    region: str
    identity: dict[str, str]
    issue_time: datetime
    timestamps: tuple[datetime, ...]
    values: tuple[float, ...]
    value_field: str
    candidate_count: int
    complete_eligible_candidate_count: int

    def canonical_payload(self) -> dict[str, object]:
        return {
            "family": self.family,
            "archive_sha256": self.archive_sha256,
            "member_name": self.member_name,
            "region": self.region,
            "identity": dict(sorted(self.identity.items())),
            "issue_time_fixed_aest": self.issue_time.isoformat(),
            "timestamps_fixed_aest": [value.isoformat() for value in self.timestamps],
            "value_field": self.value_field,
            "values": list(self.values),
        }

    @property
    def trajectory_sha256(self) -> str:
        encoded = json.dumps(
            self.canonical_payload(), sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
        return sha256(encoded).hexdigest()


def sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _parse_aemo_datetime(value: str) -> datetime:
    return datetime.strptime(value.strip(), "%Y/%m/%d %H:%M:%S").replace(tzinfo=FIXED_AEST)


def _rows(path: Path) -> tuple[str, Iterable[dict[str, str]]]:
    archive = zipfile.ZipFile(path)
    members = archive.namelist()
    if len(members) != 1:
        archive.close()
        raise AEMOVintageError("AEMO_ARCHIVE_MEMBER_COUNT_NOT_ONE")
    raw = archive.open(members[0])
    text = io.TextIOWrapper(raw, encoding="utf-8-sig", newline="")
    reader = csv.reader(text)

    def records() -> Iterable[dict[str, str]]:
        header: list[str] | None = None
        try:
            for row in reader:
                if not row:
                    continue
                if row[0] == "I":
                    header = row
                elif row[0] == "D" and header is not None:
                    yield dict(zip(header, row, strict=False))
        finally:
            text.close()
            archive.close()

    return members[0], records()


def select_demand_vintage(path: Path) -> SelectedVintage:
    """Select the latest complete VIC1 PREDISPATCH run at/before cutoff."""

    member, records = _rows(path)
    groups: dict[tuple[str, str], dict[datetime, tuple[float, datetime]]] = {}
    touching: set[tuple[str, str]] = set()
    for row in records:
        if row.get("REGIONID") != "VIC1":
            continue
        required = ("PREDISPATCHSEQNO", "RUNNO", "LASTCHANGED", "DATETIME", "TOTALDEMAND")
        if any(not row.get(field) for field in required):
            raise AEMOVintageError("AEMO_DEMAND_RUN_IDENTITY_SCHEMA_INCOMPLETE")
        target = _parse_aemo_datetime(row["DATETIME"])
        if target not in SOURCE_TIMESTAMPS:
            continue
        key = (row["PREDISPATCHSEQNO"], row["RUNNO"])
        touching.add(key)
        issue = _parse_aemo_datetime(row["LASTCHANGED"])
        value = float(row["TOTALDEMAND"])
        prior = groups.setdefault(key, {}).get(target)
        if prior is not None and prior != (value, issue):
            raise AEMOVintageError("AEMO_DEMAND_DUPLICATE_TARGET_CONFLICT")
        groups[key][target] = (value, issue)
    candidates: list[tuple[datetime, tuple[str, str], dict[datetime, tuple[float, datetime]]]] = []
    for key, rows_by_time in groups.items():
        if tuple(sorted(rows_by_time)) != SOURCE_TIMESTAMPS:
            continue
        issues = {record[1] for record in rows_by_time.values()}
        if len(issues) != 1:
            raise AEMOVintageError("AEMO_DEMAND_RUN_HAS_NONUNIQUE_ISSUE_TIME")
        issue = next(iter(issues))
        if issue <= CUTOFF:
            candidates.append((issue, key, rows_by_time))
    if not candidates:
        raise AEMOVintageError("FAIL_AEMO_COMPLETE_VINTAGE_NOT_FOUND")
    issue, key, selected = max(candidates, key=lambda item: (item[0], item[1]))
    return SelectedVintage(
        family="PREDISPATCHREGIONSUM_ALL",
        archive_path=str(path.resolve()),
        archive_sha256=sha256_file(path),
        member_name=member,
        region="VIC1",
        identity={"PREDISPATCHSEQNO": key[0], "RUNNO": key[1]},
        issue_time=issue,
        timestamps=SOURCE_TIMESTAMPS,
        values=tuple(selected[target][0] for target in SOURCE_TIMESTAMPS),
        value_field="TOTALDEMAND",
        candidate_count=len(touching),
        complete_eligible_candidate_count=len(candidates),
    )


def select_pv_vintage(path: Path) -> SelectedVintage:
    """Select the latest complete VIC1 rooftop-PV forecast version."""

    member, records = _rows(path)
    groups: dict[str, dict[datetime, float]] = {}
    touching: set[str] = set()
    for row in records:
        if row.get("REGIONID") != "VIC1":
            continue
        required = ("VERSION_DATETIME", "INTERVAL_DATETIME", "POWERMEAN")
        if any(not row.get(field) for field in required):
            raise AEMOVintageError("AEMO_PV_VERSION_SCHEMA_INCOMPLETE")
        target = _parse_aemo_datetime(row["INTERVAL_DATETIME"])
        if target not in SOURCE_TIMESTAMPS:
            continue
        version = row["VERSION_DATETIME"]
        touching.add(version)
        value = float(row["POWERMEAN"])
        prior = groups.setdefault(version, {}).get(target)
        if prior is not None and prior != value:
            raise AEMOVintageError("AEMO_PV_DUPLICATE_TARGET_CONFLICT")
        groups[version][target] = value
    candidates: list[tuple[datetime, str, dict[datetime, float]]] = []
    for version, rows_by_time in groups.items():
        if tuple(sorted(rows_by_time)) != SOURCE_TIMESTAMPS:
            continue
        issue = _parse_aemo_datetime(version)
        if issue <= CUTOFF:
            candidates.append((issue, version, rows_by_time))
    if not candidates:
        raise AEMOVintageError("FAIL_AEMO_COMPLETE_VINTAGE_NOT_FOUND")
    issue, version, selected = max(candidates, key=lambda item: (item[0], item[1]))
    return SelectedVintage(
        family="ROOFTOP_PV_FORECAST",
        archive_path=str(path.resolve()),
        archive_sha256=sha256_file(path),
        member_name=member,
        region="VIC1",
        identity={"VERSION_DATETIME": version},
        issue_time=issue,
        timestamps=SOURCE_TIMESTAMPS,
        values=tuple(selected[target] for target in SOURCE_TIMESTAMPS),
        value_field="POWERMEAN",
        candidate_count=len(touching),
        complete_eligible_candidate_count=len(candidates),
    )


def pwc_hold_30_to_15(values: tuple[float, ...]) -> tuple[float, ...]:
    if len(values) != 48:
        raise ValueError("AEMO_SOURCE_AXIS_MUST_HAVE_EXACTLY_48_SLOTS")
    return tuple(value for source in values for value in (float(source), float(source)))


def optimizer_timestamps() -> tuple[datetime, ...]:
    return tuple(
        datetime(2025, 4, 15, 0, 15, tzinfo=FIXED_AEST) + timedelta(minutes=15 * index)
        for index in range(96)
    )


def mapped_input_sha256(demand: SelectedVintage, pv: SelectedVintage) -> str:
    payload = {
        "timestamps_fixed_aest": [value.isoformat() for value in optimizer_timestamps()],
        "demand_mw": list(pwc_hold_30_to_15(demand.values)),
        "rooftop_pv_mw": list(pwc_hold_30_to_15(pv.values)),
        "mapping": "PWC_HOLD",
    }
    return sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    ).hexdigest()

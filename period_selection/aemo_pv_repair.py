"""Apply the explicitly authorized repair to seven rooftop-PV observations.

Raw AEMO archives are never modified. This module exact-deduplicates the
monthly extracts, verifies that the observed defects are exactly the approved
set, uses a same-timestamp satellite observation where available, and linearly
interpolates only when both measurement and satellite observations are absent.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from period_selection.raw_source_audit import AEMO_CONTRACTS, RAW_ROOT, _aemo_paths, _iter_aemo_rows


AEST = timezone(timedelta(hours=10), name="AEST")
AUTHORIZED_DEFECTS = {
    2024: {
        "2024-09-05 13:00:00": "MISSING",
        "2024-09-05 13:30:00": "MISSING",
        "2024-09-05 14:00:00": "BLANK",
        "2024-12-10 10:30:00": "BLANK",
        "2024-12-10 11:00:00": "BLANK",
    },
    2025: {
        "2025-08-09 16:30:00": "BLANK",
        "2025-08-09 17:00:00": "BLANK",
    },
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _raw_observations(
    year: int,
) -> tuple[dict[datetime, list[float | None]], dict[datetime, list[float | None]], list[Path]]:
    family = "ROOFTOP_PV_ACTUAL"
    contract = AEMO_CONTRACTS[family]
    paths = _aemo_paths(RAW_ROOT, family, year)
    if len(paths) != 12:
        raise ValueError(f"{year} rooftop PV requires 12 monthly archives, found {len(paths)}")
    observations: dict[datetime, list[float | None]] = {}
    satellites: dict[datetime, list[float | None]] = {}
    for _, row in _iter_aemo_rows(paths, contract["table"]):
        if row.get("REGIONID") != "VIC1" or row.get("TYPE") not in ("MEASUREMENT", "SATELLITE"):
            continue
        timestamp = datetime.strptime(row[contract["timestamp"]], "%Y/%m/%d %H:%M:%S")
        if not (datetime(year, 1, 1) < timestamp <= datetime(year + 1, 1, 1)):
            continue
        raw = row.get(contract["value"], "").strip()
        target = observations if row.get("TYPE") == "MEASUREMENT" else satellites
        target.setdefault(timestamp, []).append(float(raw) if raw else None)
    return observations, satellites, paths


def repair_year(year: int, output_dir: Path) -> dict[str, Any]:
    observations, satellites, paths = _raw_observations(year)
    expected = pd.date_range(
        datetime(year, 1, 1, 0, 30), datetime(year + 1, 1, 1), freq="30min"
    )
    missing = {stamp.to_pydatetime() for stamp in expected if stamp.to_pydatetime() not in observations}
    blank = {stamp for stamp, values in observations.items() if any(value is None for value in values)}
    conflicts = {
        stamp
        for stamp, values in observations.items()
        if len({value for value in values if value is not None}) > 1
    }
    if conflicts:
        raise ValueError(f"{year} rooftop PV has conflicting duplicates: {sorted(conflicts)}")

    observed_defects = {
        **{stamp.strftime("%Y-%m-%d %H:%M:%S"): "MISSING" for stamp in missing},
        **{stamp.strftime("%Y-%m-%d %H:%M:%S"): "BLANK" for stamp in blank},
    }
    if observed_defects != AUTHORIZED_DEFECTS[year]:
        raise ValueError(
            f"{year} rooftop PV defects differ from authorization; "
            f"observed={observed_defects}, authorized={AUTHORIZED_DEFECTS[year]}"
        )

    values: dict[datetime, float] = {}
    exact_duplicate_rows = 0
    for stamp, rows in observations.items():
        finite = [value for value in rows if value is not None]
        if len(rows) > 1:
            exact_duplicate_rows += len(rows) - 1
        if finite:
            values[stamp] = finite[0]
    series = pd.Series(values, dtype=float).reindex(expected)
    repaired = series.interpolate(method="time", limit_area="inside")
    authorized_index = pd.DatetimeIndex([pd.Timestamp(stamp) for stamp in AUTHORIZED_DEFECTS[year]])
    unauthorized_fill = series.isna() & ~series.index.isin(authorized_index)
    if unauthorized_fill.any() or repaired.loc[authorized_index].isna().any():
        raise ValueError(f"{year} repair would fill an unauthorized or unbracketed timestamp")

    repair_rows: list[dict[str, Any]] = []
    status = np.full(len(expected), "ORIGINAL", dtype=object)
    for stamp in authorized_index:
        pos = expected.get_loc(stamp)
        left_pos = pos - 1
        while left_pos >= 0 and pd.isna(series.iloc[left_pos]):
            left_pos -= 1
        right_pos = pos + 1
        while right_pos < len(series) and pd.isna(series.iloc[right_pos]):
            right_pos += 1
        if left_pos < 0 or right_pos >= len(series):
            raise ValueError(f"{year} {stamp} is not bracketed")
        left_stamp, right_stamp = expected[left_pos], expected[right_pos]
        if left_stamp.date() != stamp.date() or right_stamp.date() != stamp.date():
            raise ValueError(f"{year} {stamp} repair crosses a calendar-day boundary")
        fraction = (stamp - left_stamp) / (right_stamp - left_stamp)
        satellite_values = {
            value for value in satellites.get(stamp.to_pydatetime(), []) if value is not None
        }
        if len(satellite_values) > 1:
            raise ValueError(f"{year} {stamp} has conflicting same-timestamp satellite values")
        if satellite_values:
            value = float(next(iter(satellite_values)))
            repair_method = "SAME_TIMESTAMP_SATELLITE_FALLBACK"
        else:
            value = float(repaired.loc[stamp])
            repair_method = "LINEAR_INTERPOLATION_NO_SATELLITE_AVAILABLE"
        if not np.isfinite(value) or value < 0:
            raise ValueError(f"{year} {stamp} repair is negative or non-finite")
        repaired.loc[stamp] = value
        status[pos] = repair_method
        repair_rows.append({
            "timestamp": stamp.strftime("%Y-%m-%d %H:%M:%S"),
            "source_issue": AUTHORIZED_DEFECTS[year][stamp.strftime("%Y-%m-%d %H:%M:%S")],
            "left_timestamp": left_stamp.strftime("%Y-%m-%d %H:%M:%S"),
            "left_power_mw": float(series.iloc[left_pos]),
            "right_timestamp": right_stamp.strftime("%Y-%m-%d %H:%M:%S"),
            "right_power_mw": float(series.iloc[right_pos]),
            "interpolation_fraction": float(fraction),
            "same_timestamp_satellite_power_mw": (
                value if repair_method == "SAME_TIMESTAMP_SATELLITE_FALLBACK" else None
            ),
            "repair_method": repair_method,
            "repaired_power_mw": value,
        })

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"AEMO_ROOFTOP_PV_ACTUAL_REPAIRED_{year}_30MIN.parquet"
    frame = pd.DataFrame({
        "interval_end_aest": expected.tz_localize(AEST),
        "power_mw": repaired.to_numpy(dtype=float),
        "repair_status": status,
    })
    if len(frame) != len(expected) or not np.isfinite(frame["power_mw"]).all():
        raise ValueError(f"{year} repaired rooftop PV does not cover the full annual axis")
    frame.to_parquet(output_path, index=False, compression="zstd")
    return {
        "year": year,
        "source_archives": [{"path": str(path), "sha256": sha256_file(path)} for path in paths],
        "exact_duplicate_rows_removed": exact_duplicate_rows,
        "authorized_defects": AUTHORIZED_DEFECTS[year],
        "repairs": repair_rows,
        "output_path": str(output_path),
        "output_rows": len(frame),
        "output_sha256": sha256_file(output_path),
        "validation": "PASS",
    }


def write_repaired_outputs(output_dir: Path, audit_dir: Path) -> dict[str, Any]:
    years = [repair_year(year, output_dir) for year in (2024, 2025)]
    methods = [repair["repair_method"] for item in years for repair in item["repairs"]]
    if methods.count("SAME_TIMESTAMP_SATELLITE_FALLBACK") != 5 or methods.count(
        "LINEAR_INTERPOLATION_NO_SATELLITE_AVAILABLE"
    ) != 2:
        raise ValueError(f"unexpected rooftop-PV repair method counts: {methods}")
    payload = {
        "schema_version": "aemo_rooftop_pv_audited_repair_v1",
        "policy": "exact deduplication; same-timestamp satellite fallback where available; linear interpolation only when measurement and satellite are both absent",
        "raw_archives_modified": False,
        "years": years,
        "total_repaired_timestamps": sum(len(item["repairs"]) for item in years),
        "same_timestamp_satellite_fallback_count": methods.count(
            "SAME_TIMESTAMP_SATELLITE_FALLBACK"
        ),
        "linear_interpolation_no_satellite_count": methods.count(
            "LINEAR_INTERPOLATION_NO_SATELLITE_AVAILABLE"
        ),
        "status": "VERIFIED_COMPLETE_AFTER_AUDITED_REPAIR",
        "validation": "PASS",
    }
    audit_dir.mkdir(parents=True, exist_ok=True)
    audit_path = audit_dir / "AEMO_ROOFTOP_PV_AUDITED_REPAIR_2024_2025.json"
    audit_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=Path("period_selection/output"))
    parser.add_argument("--audit-dir", type=Path, default=Path("period_selection/audit"))
    args = parser.parse_args()
    result = write_repaired_outputs(args.output_dir, args.audit_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Build identical 2024/2025 exogenous-only representative-period features."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from period_selection import FORBIDDEN_FEATURE_TOKENS
from period_selection.aemo_pv_repair import AUTHORIZED_DEFECTS, sha256_file
from period_selection.raw_source_audit import AEMO_CONTRACTS, RAW_ROOT, _aemo_paths, _iter_aemo_rows


TRAFFIC_FREEZE = Path(os.environ.get(
    "MOBILE_ESS_TRAFFIC_FREEZE",
    "data/processed/scats_traffic_freeze",
))
AEST = timezone(timedelta(hours=10), name="AEST")
STEPS_PER_DAY = 288

FEATURE_COLUMNS = [
    "regional_total_demand_mw",
    "rooftop_pv_actual_mw",
    "vic1_rrp_aud_per_mwh",
    "traffic_mean_tti",
    "traffic_p95_tti",
    "traffic_congested_fraction",
    "job_arrival_count",
    "arriving_gpu",
    "arriving_gpuh",
    "arriving_wan_nominal_gb",
]


def annual_steps(year: int) -> int:
    return (366 if pd.Timestamp(year=year, month=12, day=31).dayofyear == 366 else 365) * STEPS_PER_DAY


def fixed_aest_axis(year: int) -> pd.DatetimeIndex:
    return pd.date_range(datetime(year, 1, 1, tzinfo=AEST), periods=annual_steps(year), freq="5min")


def fixed_aest_axis_2025() -> pd.DatetimeIndex:
    """Backward-compatible wrapper used by existing callers and tests."""
    return fixed_aest_axis(2025)


def validate_feature_table(frame: pd.DataFrame, year: int | None = None) -> None:
    expected = ["timestamp_aest", *FEATURE_COLUMNS]
    if list(frame.columns) != expected:
        raise ValueError(f"feature columns differ from contract: {list(frame.columns)}")
    ts = pd.DatetimeIndex(frame["timestamp_aest"])
    if len(ts) == 0:
        raise ValueError("empty feature table")
    selected_year = int(ts[0].year) if year is None else year
    if len(frame) != annual_steps(selected_year):
        raise ValueError(f"row count {len(frame)} != {annual_steps(selected_year)}")
    if ts.tz is None or {x.utcoffset() for x in ts[::STEPS_PER_DAY]} != {timedelta(hours=10)}:
        raise ValueError("timestamps must use fixed UTC+10 without DST")
    if ts.has_duplicates or not ts.equals(fixed_aest_axis(selected_year)):
        raise ValueError("missing, duplicated, reordered, or non-5-minute timestamp")
    values = frame[FEATURE_COLUMNS].to_numpy(dtype=float)
    if not np.isfinite(values).all():
        row, column = np.argwhere(~np.isfinite(values))[0]
        raise ValueError(f"non-finite feature at row={row} col={FEATURE_COLUMNS[column]}")
    lowered = " ".join(frame.columns).lower()
    bad = [token for token in FORBIDDEN_FEATURE_TOKENS if token in lowered]
    if bad:
        raise ValueError(f"forbidden controller/outcome feature tokens: {bad}")


def _strict_aemo_series(year: int, family: str) -> pd.Series:
    contract = AEMO_CONTRACTS[family]
    observations: dict[datetime, list[float | None]] = {}
    for _, row in _iter_aemo_rows(_aemo_paths(RAW_ROOT, family, year), contract["table"]):
        if row.get("REGIONID") != "VIC1":
            continue
        if family != "ROOFTOP_PV_ACTUAL" and row.get("INTERVENTION", "0") not in ("", "0"):
            continue
        if family == "ROOFTOP_PV_ACTUAL" and row.get("TYPE") != "MEASUREMENT":
            continue
        timestamp = datetime.strptime(row[contract["timestamp"]], "%Y/%m/%d %H:%M:%S")
        if not (datetime(year, 1, 1) < timestamp <= datetime(year + 1, 1, 1)):
            continue
        raw = row.get(contract["value"], "").strip()
        value = float(raw) if raw else None
        observations.setdefault(timestamp, []).append(value)

    minutes = int(contract["resolution_minutes"])
    expected = pd.date_range(
        datetime(year, 1, 1) + timedelta(minutes=minutes),
        datetime(year + 1, 1, 1),
        freq=f"{minutes}min",
    )
    missing = [timestamp for timestamp in expected if timestamp.to_pydatetime() not in observations]
    blanks = [timestamp for timestamp, values in observations.items() if any(value is None for value in values)]
    conflicts = [
        timestamp for timestamp, values in observations.items()
        if len(values) > 1 and any(value != values[0] for value in values[1:])
    ]
    if missing or blanks or conflicts:
        raise ValueError(
            f"{year} {family} fails closed: missing={len(missing)}, blank={len(blanks)}, "
            f"conflicting_duplicates={len(conflicts)}; no repair policy is authorized"
        )
    deduplicated = {timestamp: values[0] for timestamp, values in observations.items()}
    series = pd.Series(deduplicated, dtype=float).sort_index()
    if len(series) != len(expected) or not np.isfinite(series.to_numpy()).all():
        raise ValueError(f"{year} {family} is incomplete or non-finite after exact deduplication")
    return series


def _load_repaired_pv(year: int, output_root: Path, audit_path: Path) -> pd.Series:
    if not audit_path.is_file():
        raise FileNotFoundError(f"audited rooftop-PV repair manifest is required: {audit_path}")
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    if audit.get("validation") != "PASS" or audit.get("status") != "VERIFIED_COMPLETE_AFTER_AUDITED_REPAIR":
        raise ValueError("rooftop-PV repair manifest did not pass")
    year_audit = next((item for item in audit.get("years", []) if item.get("year") == year), None)
    if year_audit is None or year_audit.get("authorized_defects") != AUTHORIZED_DEFECTS[year]:
        raise ValueError(f"{year} rooftop-PV repair authorization does not match the frozen contract")
    path = output_root / f"AEMO_ROOFTOP_PV_ACTUAL_REPAIRED_{year}_30MIN.parquet"
    if not path.is_file() or sha256_file(path) != year_audit.get("output_sha256"):
        raise ValueError(f"{year} repaired rooftop-PV artifact is missing or has changed")
    frame = pd.read_parquet(path)
    expected = pd.date_range(
        datetime(year, 1, 1, 0, 30, tzinfo=AEST),
        datetime(year + 1, 1, 1, tzinfo=AEST),
        freq="30min",
    )
    timestamps = pd.DatetimeIndex(frame["interval_end_aest"])
    values = frame["power_mw"].to_numpy(dtype=float)
    if len(frame) != len(expected) or not timestamps.equals(expected) or not np.isfinite(values).all():
        raise ValueError(f"{year} repaired rooftop-PV artifact has an invalid axis or values")
    return pd.Series(values, index=expected.tz_localize(None), dtype=float)


def _aemo_features(year: int, pv_output_root: Path, pv_audit_path: Path) -> dict[str, np.ndarray]:
    demand = _strict_aemo_series(year, "DISPATCHREGIONSUM")
    price = _strict_aemo_series(year, "DISPATCHPRICE")
    pv = _load_repaired_pv(year, pv_output_root, pv_audit_path)
    # AEMO timestamps are interval-ending.  Dispatch/price are mapped to the
    # corresponding 5-minute interval start.  Each 30-minute PV measurement is
    # expanded over its six constituent 5-minute intervals, preserving energy.
    return {
        "regional_total_demand_mw": demand.to_numpy(dtype=float),
        "rooftop_pv_actual_mw": np.repeat(pv.to_numpy(dtype=float), 6),
        "vic1_rrp_aud_per_mwh": price.to_numpy(dtype=float),
    }


def _traffic_features(year: int, threshold: float) -> dict[str, np.ndarray]:
    split_path = TRAFFIC_FREEZE / "freeze_assets/dataset/date_splits_2019_2025.csv"
    if not split_path.is_file():
        raise FileNotFoundError(split_path)
    manifest = pd.read_csv(split_path)
    date_col = "date" if "date" in manifest else "calendar_date"
    path_col = next((name for name in ("final_parquet", "path", "parquet_path") if name in manifest), None)
    if path_col is None:
        raise ValueError("traffic manifest has no recognized parquet path column")
    rows = manifest[pd.to_datetime(manifest[date_col]).dt.year == year].copy()
    days = 366 if annual_steps(year) == 366 * STEPS_PER_DAY else 365
    if len(rows) != days or rows[date_col].duplicated().any():
        raise ValueError(f"traffic manifest must contain exactly {days} unique {year} dates")
    mean = np.empty(annual_steps(year), dtype=float)
    p95 = np.empty_like(mean)
    congested = np.empty_like(mean)
    for day_index, row in enumerate(rows.sort_values(date_col).to_dict("records")):
        path = Path(row[path_col])
        if not path.is_file():
            raise FileNotFoundError(path)
        daily = pd.read_parquet(path, columns=["slot5", "final_tti"])
        grouped = daily.groupby("slot5", sort=True)["final_tti"]
        if grouped.ngroups != STEPS_PER_DAY or grouped.size().nunique() != 1:
            raise ValueError(f"traffic coverage is not uniform: {path}")
        start, stop = day_index * STEPS_PER_DAY, (day_index + 1) * STEPS_PER_DAY
        mean[start:stop] = grouped.mean().to_numpy(dtype=float)
        p95[start:stop] = grouped.quantile(0.95).to_numpy(dtype=float)
        congested[start:stop] = grouped.apply(lambda values: float((values > threshold).mean())).to_numpy(dtype=float)
    return {
        "traffic_mean_tti": mean,
        "traffic_p95_tti": p95,
        "traffic_congested_fraction": congested,
    }


def _job_features(year: int, output_root: Path = Path("period_selection/output")) -> dict[str, np.ndarray]:
    path = output_root / f"F30_JOB_WAN_FEATURES_{year}_5MIN.parquet"
    if not path.is_file():
        raise FileNotFoundError(f"run period_selection.kestrel_adapter first: {path}")
    frame = pd.read_parquet(path)
    required = ["job_arrival_count", "arriving_gpu", "arriving_gpuh", "arriving_wan_nominal_gb"]
    if list(frame.columns) != required or len(frame) != annual_steps(year):
        raise ValueError(f"invalid {year} Job/WAN feature table")
    if not np.allclose(frame["arriving_wan_nominal_gb"], frame["arriving_gpuh"] * 3.0, rtol=0, atol=1e-10):
        raise ValueError("WAN must equal arriving GPUh * 3 GB/GPUh")
    return {name: frame[name].to_numpy(dtype=float) for name in required}


def assert_raw_gate(audit_path: Path, pv_audit_path: Path, pv_output_root: Path) -> None:
    if not audit_path.is_file():
        raise FileNotFoundError(f"raw audit is required before feature construction: {audit_path}")
    payload = json.loads(audit_path.read_text(encoding="utf-8"))
    summary = payload["summary"]
    permitted_source_gaps = {"2024:ROOFTOP_PV_ACTUAL", "2025:ROOFTOP_PV_ACTUAL"}
    if (
        summary["scats_local_missing"]
        or not summary["kestrel_local_verified"]
        or set(summary["aemo_unresolved"]) != permitted_source_gaps
    ):
        raise RuntimeError(
            "raw-data source gate is not eligible for the authorized repair: "
            f"SCATS missing={summary['scats_local_missing']}; "
            f"AEMO unresolved={summary['aemo_unresolved']}"
        )
    for year in (2024, 2025):
        _load_repaired_pv(year, pv_output_root, pv_audit_path)


def build_feature_table(year: int, config: dict[str, Any], enforce_raw_gate: bool = True) -> pd.DataFrame:
    pv_audit_path = Path(config.get(
        "pv_repair_audit_path", "period_selection/audit/AEMO_ROOFTOP_PV_AUDITED_REPAIR_2024_2025.json"
    ))
    pv_output_root = Path(config.get("pv_repair_output_root", "period_selection/output"))
    if enforce_raw_gate:
        assert_raw_gate(
            Path(config.get("raw_audit_path", "period_selection/audit/REP_PERIOD_RAW_INVENTORY_2024_2025.json")),
            pv_audit_path,
            pv_output_root,
        )
    data: dict[str, Any] = {"timestamp_aest": fixed_aest_axis(year)}
    data.update(_aemo_features(year, pv_output_root, pv_audit_path))
    data.update(_traffic_features(year, float(config["traffic_congestion_tti_threshold"])))
    data.update(_job_features(year))
    frame = pd.DataFrame(data)[["timestamp_aest", *FEATURE_COLUMNS]]
    validate_feature_table(frame, year)
    return frame


def load_config(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_feature_tables(config_path: Path, output_dir: Path) -> dict[int, pd.DataFrame]:
    config = load_config(config_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    tables = {}
    for year in (2024, 2025):
        table = build_feature_table(year, config)
        table.to_parquet(output_dir / f"REP_WEEK_FEATURES_{year}.parquet", index=False, compression="zstd")
        tables[year] = table
    return tables

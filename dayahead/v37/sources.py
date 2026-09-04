"""Materialize only contract-runnable May inputs without opening May outcomes."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict
from datetime import date, datetime, time, timedelta
import json
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import pandas as pd

from dayahead.authority import DEFAULT_RAW_ROOT, NLR_SOURCE_SHA256, sha256_file
from dayahead.final_science_inputs_v16_3 import select_month_vintages
from dayahead.thermal.contracts import GFS_LEADS, GFS_VARIABLES
from dayahead.thermal.psychrometrics import relative_humidity_from_dewpoint, wet_bulb_temperature_c
from dayahead.v28r2.source_cache import atomic_json, day_root
from dayahead.v28r2.source_manifest import canonical_sha256
from dayahead.v28r2.source_preflight import AEST, STATION_LAT, STATION_LON, _gfs_one


def archive_month_for_operating_day(day: str) -> str:
    """Return YYYYMM for the immutable D-1 18:00 fixed-AEST cutoff."""

    operating = date.fromisoformat(day)
    cutoff = datetime.combine(operating - timedelta(days=1), time(18), AEST)
    return cutoff.strftime("%Y%m")


def cross_month_archive_paths(day: str) -> tuple[Path, Path]:
    archive_month = archive_month_for_operating_day(day)
    root = DEFAULT_RAW_ROOT / "AEMO"
    demand_matches = sorted(
        (root / "Day-Ahead demand forecast").glob(f"*{archive_month}010000.zip")
    )
    pv_matches = sorted(
        (root / "AEMO Rooftop PV — forecast + actual" / "Forecast").glob(
            f"*{archive_month}010000.zip"
        )
    )
    if len(demand_matches) != 1 or len(pv_matches) != 1:
        raise FileNotFoundError(
            f"V37_D1_ARCHIVE_MONTH_LOOKUP:{day}:{archive_month}:"
            f"demand={len(demand_matches)}:pv={len(pv_matches)}"
        )
    return demand_matches[0], pv_matches[0]


def select_cross_month_vintages(days: Sequence[str]) -> tuple[
    dict[str, dict[str, object]], dict[str, list[str]], dict[str, dict[str, str]]
]:
    """Run the frozen selector against the archive month of each D-1 cutoff."""

    grouped: dict[tuple[Path, Path], list[str]] = defaultdict(list)
    archive_evidence: dict[str, dict[str, str]] = {}
    failures: dict[str, list[str]] = {}
    for day in map(str, days):
        try:
            demand, pv = cross_month_archive_paths(day)
        except FileNotFoundError as error:
            failures[day] = [str(error)]
            continue
        grouped[(demand, pv)].append(day)
        archive_evidence[day] = {
            "archive_month": archive_month_for_operating_day(day),
            "demand_path": str(demand.resolve()), "pv_path": str(pv.resolve()),
        }
    selected: dict[str, dict[str, object]] = {}
    for (demand, pv), grouped_days in grouped.items():
        values, group_failures = select_month_vintages(
            demand_path=demand, pv_path=pv, days=grouped_days,
            expected_shas={"demand": sha256_file(demand), "pv": sha256_file(pv)},
        )
        selected.update(values)
        failures.update(group_failures)
    return selected, failures, archive_evidence


def _materialize_gfs(source_repo: Path, days: Sequence[str], workers: int = 12) -> dict[str, str]:
    failures: dict[str, str] = {}
    tasks = [
        (day, lead) for day in days
        if not (day_root(source_repo, day) / "gfs_d1_weather.parquet").is_file()
        for lead in GFS_LEADS
    ]
    manifests: dict[tuple[str, int], dict[str, Any]] = {}
    if tasks:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(_gfs_one, source_repo, day, lead): (day, lead) for day, lead in tasks}
            for future in as_completed(futures):
                day, lead = futures[future]
                try:
                    manifests[(day, lead)] = future.result()
                except Exception as error:  # each unavailable day fails closed independently
                    failures.setdefault(day, f"GFS_D_MINUS_1_UNAVAILABLE:{type(error).__name__}:{error}")
    for day in days:
        output = day_root(source_repo, day) / "gfs_d1_weather.parquet"
        if output.is_file() and output.stat().st_size > 0:
            continue
        if day in failures or any((day, lead) not in manifests for lead in GFS_LEADS):
            failures.setdefault(day, "GFS_D_MINUS_1_INCOMPLETE")
            continue
        rows, source_records = [], []
        # Decoder is imported only when at least one missing day was actually
        # materialized above.  Existing immutable files have no eccodes
        # runtime dependency during readiness validation.
        from dayahead.thermal.gfs_decode import decode_nearest

        for lead in GFS_LEADS:
            payload = manifests[(day, lead)]
            decoded = {}
            for record in payload["records"]:
                value = decode_nearest(Path(record["path"]).read_bytes(), STATION_LAT, STATION_LON)
                decoded[record["variable"]] = value
                source_records.append(record)
            initialization = pd.Timestamp(payload["records"][0]["initialization_utc"])
            rows.append({
                "initialization_utc": initialization,
                "lead_hours": lead,
                "valid_time_utc": initialization + pd.Timedelta(hours=lead),
                "t_db_c": decoded["TMP"]["value"] - 273.15,
                "t_dew_c": decoded["DPT"]["value"] - 273.15,
                "rh_pct_raw": decoded["RH"]["value"],
                "pressure_pa": decoded["PRES"]["value"],
                "u10_mps": decoded["UGRD"]["value"],
                "v10_mps": decoded["VGRD"]["value"],
                "grid_latitude": decoded["TMP"]["grid_latitude"],
                "grid_longitude": decoded["TMP"]["grid_longitude"],
                "distance_km": decoded["TMP"]["distance_km"],
            })
        hourly = pd.DataFrame(rows).sort_values("valid_time_utc")
        hourly["rh_pct"] = relative_humidity_from_dewpoint(hourly["t_db_c"], hourly["t_dew_c"])
        hourly["wind_speed_mps"] = np.hypot(hourly["u10_mps"], hourly["v10_mps"])
        hourly["t_wb_c"] = wet_bulb_temperature_c(hourly["t_db_c"], hourly["rh_pct"], hourly["pressure_pa"])
        index = pd.DatetimeIndex(hourly["valid_time_utc"]).tz_convert(AEST)
        hourly.index = index
        target = pd.date_range(day, periods=96, freq="15min", tz=AEST)
        forcing = hourly.drop(columns=["initialization_utc", "valid_time_utc"]).reindex(
            index.union(target)
        ).sort_index().interpolate(method="time").reindex(target)
        forcing.insert(0, "ts_fixed_aest", target)
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_suffix(".parquet.tmp")
        forcing.to_parquet(temporary, index=False)
        temporary.replace(output)
        atomic_json(day_root(source_repo, day) / "gfs_source_manifest.json", {
            "day": day, "cycle": "06Z D-1", "leads": list(GFS_LEADS),
            "variables": GFS_VARIABLES, "records": source_records,
        })
    return failures


def _materialize_aemo(source_repo: Path, days: Sequence[str]) -> tuple[dict[str, str], dict[str, dict[str, str]]]:
    selected, failures, evidence = select_cross_month_vintages(days)
    output_failures = {day: ";".join(reasons) for day, reasons in failures.items()}
    for day, payload in selected.items():
        atomic_json(day_root(source_repo, day) / "aemo_forecast.json", {
            **payload, "cross_month_archive_authority": evidence[day],
        })
    return output_failures, evidence


def _materialize_kestrel(source_repo: Path, days: Sequence[str]) -> tuple[dict[str, str], dict[str, Any]]:
    """Materialize D-1 scheduler state, never a realized D-day execution slice."""

    from .aidc_materializer import load_state_source, snapshot_at_issue

    source = (
        DEFAULT_RAW_ROOT / "데이터 센터" / "NLR HPC Kestrel Jobs Data"
        / "esif.hpc.kestrel.job-anon.zip"
    )
    if not source.is_file() or sha256_file(source) != NLR_SOURCE_SHA256["kestrel_jobs_zip"]:
        return ({day: "KESTREL_ARCHIVE_AUTHORITY_MISSING" for day in days}, {})
    try:
        frame, source_audit = load_state_source(tuple(map(str, days)), archive_path=source)
    except Exception as error:
        reason = f"KESTREL_D1_SOURCE:{type(error).__name__}:{error}"
        return ({day: reason for day in map(str, days)}, {})
    failures: dict[str, str] = {}
    per_day: dict[str, Any] = {}
    for day in map(str, days):
        try:
            snapshot = snapshot_at_issue(frame, day)
            output = day_root(source_repo, day) / "kestrel_d1_scheduler_snapshot.parquet"
            output.parent.mkdir(parents=True, exist_ok=True)
            temporary = output.with_suffix(".parquet.tmp")
            snapshot.to_parquet(temporary, index=False)
            temporary.replace(output)
            per_day[day] = {
                **dict(snapshot.attrs["state_audit"]),
                "path": str(output.resolve()), "sha256": sha256_file(output),
                "RUNNING": int(snapshot["state_at_issue"].eq("RUNNING").sum()),
                "PENDING": int(snapshot["state_at_issue"].eq("PENDING").sum()),
                "status": "PASS",
            }
        except Exception as error:
            failures[day] = f"KESTREL_D1_SNAPSHOT:{type(error).__name__}:{error}"
    return failures, {"source": source_audit, "dates": per_day}


def materialize_sources(source_repo: Path, days: Sequence[str], workers: int = 12) -> dict[str, Any]:
    selected_days = tuple(map(str, days))
    aemo_failures, archive_evidence = _materialize_aemo(source_repo, selected_days)
    gfs_failures = _materialize_gfs(source_repo, selected_days, workers=workers)
    kestrel_failures, kestrel_audit = _materialize_kestrel(source_repo, selected_days)
    failures: dict[str, list[str]] = {}
    for day in selected_days:
        reasons = []
        if day in aemo_failures:
            reasons.append(aemo_failures[day])
        if day in gfs_failures:
            reasons.append(gfs_failures[day])
        if day in kestrel_failures:
            reasons.append(kestrel_failures[day])
        if reasons:
            failures[day] = reasons
            continue
        root = day_root(source_repo, day)
        mobility = root / "traffic_mobility.json"
        atomic_json(mobility, {
            "day": day, "mess": [],
            "role": "LEGACY_FORMULATION_CONTEXT_ONLY_NOT_PRODUCTION_TRAFFIC_READINESS",
        })
        files = {
            name: {"path": str(path.resolve()), "sha256": sha256_file(path), "bytes": path.stat().st_size}
            for name, path in {
                "gfs_d1_weather": root / "gfs_d1_weather.parquet",
                "aemo_forecast": root / "aemo_forecast.json",
                "kestrel_d1_scheduler_snapshot": root / "kestrel_d1_scheduler_snapshot.parquet",
            }.items()
        }
        payload = {
            "artifact_id": "V37_MAY_MINIMUM_SOURCE_DAY_MANIFEST_V1", "day": day,
            "status": "PASS", "files": files,
            "science_note": "V36 frozen science; May inputs are evaluation inputs only.",
        }
        payload["source_day_sha256"] = canonical_sha256(payload)
        atomic_json(root / "source_day_manifest.json", payload)
    runnable = [day for day in selected_days if day not in failures]
    complete = len(selected_days) > 0 and len(runnable) == len(selected_days) and not failures
    return {
        "artifact_id": "V37_MAY_SOURCE_MATERIALIZATION_V1",
        "status": "PASS" if complete else "FAIL",
        "requested_dates": list(selected_days), "runnable_dates": runnable,
        "requested_count": len(selected_days), "runnable_count": len(runnable),
        "failed_count": len(failures),
        "failed_dates": failures, "archive_evidence": archive_evidence,
        "kestrel_D1_snapshot_audit": kestrel_audit,
        "archive_selection_rule": "MONTH_OF_D_MINUS_1_18_FIXED_AEST_CUTOFF",
        "May_results_read_for_materialization": False,
    }

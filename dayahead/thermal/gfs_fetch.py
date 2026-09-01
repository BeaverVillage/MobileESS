"""Causal historical GFS 06Z IDX preflight and byte-range downloader."""

from __future__ import annotations

import hashlib
import json
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from .contracts import (
    ARTIFACT_ROOT,
    AUTHORIZED_DAYS,
    DOWNLOAD_CAP_BYTES,
    GFS_BASE,
    GFS_LEADS,
    GFS_VARIABLES,
    RAW_ROOT,
    D1ForecastWindow,
)
from .gfs_decode import decode_nearest
from .gfs_idx import IdxMessage, parse_idx, select_messages
from .psychrometrics import relative_humidity_from_dewpoint, wet_bulb_temperature_c
from .utils import sha256_file, write_json


def gfs_url(initialization: datetime, lead: int) -> str:
    """Return the NOAA AWS HTTPS URL for one 0.25-degree GFS lead."""
    if initialization.tzinfo is None or initialization.astimezone(timezone.utc).hour != 6:
        raise ValueError("only timezone-aware 06Z GFS initialization is allowed")
    if lead not in GFS_LEADS:
        raise ValueError("only f008 through f032 are allowed")
    day = initialization.astimezone(timezone.utc).strftime("%Y%m%d")
    return f"{GFS_BASE}/gfs.{day}/06/atmos/gfs.t06z.pgrb2.0p25.f{lead:03d}"


def _cache_root(raw_root: Path) -> Path:
    return raw_root / "기상" / "NOAA_GFS_D1"


def _head_size(session: requests.Session, url: str) -> tuple[int, str | None]:
    response = session.head(url, timeout=60)
    response.raise_for_status()
    size = int(response.headers["Content-Length"])
    return size, response.headers.get("ETag")


def _preflight_one(
    initialization: datetime, lead: int, cache_root: Path
) -> dict[str, Any]:
    url = gfs_url(initialization, lead)
    with requests.Session() as session:
        idx_response = session.get(url + ".idx", timeout=60)
        idx_response.raise_for_status()
        size, etag = _head_size(session, url)
    messages = parse_idx(idx_response.text, size)
    selected = select_messages(messages, GFS_VARIABLES)
    init_text = initialization.astimezone(timezone.utc).strftime("%Y%m%d%H")
    idx_path = cache_root / "idx" / init_text / f"f{lead:03d}.idx"
    idx_path.parent.mkdir(parents=True, exist_ok=True)
    idx_path.write_text(idx_response.text, encoding="utf-8")
    return {
        "initialization_utc": initialization.astimezone(timezone.utc).isoformat(),
        "lead_hours": lead,
        "url": url,
        "idx_url": url + ".idx",
        "idx_path": str(idx_path.resolve()),
        "idx_sha256": sha256_file(idx_path),
        "etag": etag,
        "object_size_bytes": size,
        "selected": {key: asdict(value) for key, value in selected.items()},
        "selected_bytes": sum(item.byte_count for item in selected.values()),
    }


def build_download_preflight(
    repo: Path, raw_root: Path = RAW_ROOT, workers: int = 12
) -> dict[str, Any]:
    """Fetch only IDX/HEAD metadata and estimate all authorized range bytes."""
    cache_root = _cache_root(raw_root)
    tasks = []
    for day in AUTHORIZED_DAYS:
        window = D1ForecastWindow(day)
        window.validate()
        for lead in GFS_LEADS:
            tasks.append((window.initialization_utc, lead))
    records: list[dict[str, Any]] = []
    errors: list[dict[str, str | int]] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(_preflight_one, init, lead, cache_root): (init, lead)
            for init, lead in tasks
        }
        for future in as_completed(futures):
            init, lead = futures[future]
            try:
                records.append(future.result())
            except Exception as error:
                errors.append({"initialization_utc": init.isoformat(), "lead_hours": lead, "error": str(error)})
    records.sort(key=lambda item: (item["initialization_utc"], item["lead_hours"]))
    projected = sum(item["selected_bytes"] for item in records)
    preflight = {
        "artifact_id": "V24T_GFS_DOWNLOAD_PREFLIGHT",
        "source": "NOAA GFS AWS Open Data noaa-gfs-bdp-pds via HTTPS",
        "timezone_contract": "D-1 18:00 fixed AEST = 08:00 UTC; use prior-day 06Z",
        "authorized_days": [str(day) for day in AUTHORIZED_DAYS],
        "number_of_days": len(AUTHORIZED_DAYS),
        "number_of_leads_per_day": len(GFS_LEADS),
        "number_of_messages_per_lead": len(GFS_VARIABLES),
        "expected_idx_file_count": len(tasks),
        "successful_idx_file_count": len(records),
        "message_count": len(records) * len(GFS_VARIABLES),
        "projected_download_bytes": projected,
        "projected_download_gib": projected / 1024**3,
        "download_cap_bytes": DOWNLOAD_CAP_BYTES,
        "under_cap": projected <= DOWNLOAD_CAP_BYTES,
        "full_grib_download_allowed": False,
        "errors": errors,
        "files": records,
    }
    write_json(repo / ARTIFACT_ROOT / "V24T_GFS_DOWNLOAD_PREFLIGHT.json", preflight)
    return preflight


def _range_get(url: str, message: IdxMessage) -> tuple[bytes, dict[str, Any]]:
    headers = {"Range": message.range_header, "Accept-Encoding": "identity"}
    last_error: Exception | None = None
    for _ in range(3):
        try:
            response = requests.get(url, headers=headers, timeout=120)
            if response.status_code != 206:
                raise RuntimeError(
                    f"refused non-range response {response.status_code}; no full-GRIB fallback"
                )
            if len(response.content) != message.byte_count:
                raise RuntimeError("range byte count mismatch")
            return response.content, {
                "url": url,
                "etag": response.headers.get("ETag"),
                "byte_range": message.range_header,
                "byte_count": len(response.content),
                "sha256": hashlib.sha256(response.content).hexdigest(),
            }
        except Exception as error:
            last_error = error
    raise RuntimeError(str(last_error))


def _download_file(
    record: dict[str, Any]
) -> tuple[dict[str, bytes], list[dict[str, Any]]]:
    contents: dict[str, bytes] = {}
    manifest: list[dict[str, Any]] = []
    for variable in GFS_VARIABLES:
        message = IdxMessage(**record["selected"][variable])
        content, source = _range_get(record["url"], message)
        contents[variable] = content
        manifest.append(
            {
                **source,
                "forecast_initialization_utc": record["initialization_utc"],
                "lead_hours": record["lead_hours"],
                "variable": variable,
                "level": GFS_VARIABLES[variable],
                "full_field_retained": False,
            }
        )
    return contents, manifest


def fetch_gfs_ranges(repo: Path, raw_root: Path = RAW_ROOT, workers: int = 8) -> dict[str, Any]:
    """Download only six selected ranges per lead, decode, and discard full fields."""
    preflight_path = repo / ARTIFACT_ROOT / "V24T_GFS_DOWNLOAD_PREFLIGHT.json"
    preflight = json.loads(preflight_path.read_text(encoding="utf-8")) if preflight_path.exists() else build_download_preflight(repo, raw_root)
    if preflight["errors"] or preflight["successful_idx_file_count"] != preflight["expected_idx_file_count"]:
        raise RuntimeError("GFS IDX preflight incomplete")
    if not preflight["under_cap"]:
        raise RuntimeError("projected GFS range download exceeds 20 GiB cap")
    authority = json.loads((repo / ARTIFACT_ROOT / "V24T_MELBOURNE_ACTUAL_WEATHER_AUTHORITY.json").read_text(encoding="utf-8"))
    station_lat = float(authority["latitude"])
    station_lon = float(authority["longitude"])
    rows: list[dict[str, Any]] = []
    source_records: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        future_map = {
            pool.submit(_download_file, record): record
            for record in preflight["files"]
        }
        for future in as_completed(future_map):
            record = future_map[future]
            try:
                contents, manifest = future.result()
                # ecCodes' C parser is deliberately kept on this single caller
                # thread; only HTTP transfers run concurrently.
                decoded = {
                    variable: decode_nearest(content, station_lat, station_lon)
                    for variable, content in contents.items()
                }
                for item in manifest:
                    value = decoded[item["variable"]]
                    item.update(
                        grid_latitude=value["grid_latitude"],
                        grid_longitude=value["grid_longitude"],
                        distance_km=value["distance_km"],
                    )
                init = pd.Timestamp(record["initialization_utc"])
                lead = int(record["lead_hours"])
                row = {
                    "initialization_utc": init,
                    "lead_hours": lead,
                    "valid_time_utc": init + pd.Timedelta(hours=lead),
                    "t_db_c": decoded["TMP"]["value"] - 273.15,
                    "t_dew_c": decoded["DPT"]["value"] - 273.15,
                    "rh_pct_raw": decoded["RH"]["value"],
                    "pressure_pa": decoded["PRES"]["value"],
                    "u10_mps": decoded["UGRD"]["value"],
                    "v10_mps": decoded["VGRD"]["value"],
                    "grid_latitude": decoded["TMP"]["grid_latitude"],
                    "grid_longitude": decoded["TMP"]["grid_longitude"],
                    "distance_km": decoded["TMP"]["distance_km"],
                }
                rows.append(row)
                source_records.extend(manifest)
            except Exception as error:
                errors.append({"initialization_utc": record["initialization_utc"], "lead_hours": record["lead_hours"], "error": str(error)})
    frame = pd.DataFrame(rows).sort_values(["initialization_utc", "lead_hours"]).reset_index(drop=True)
    if not frame.empty:
        frame["rh_pct"] = relative_humidity_from_dewpoint(frame["t_db_c"], frame["t_dew_c"])
        frame["wind_speed_mps"] = (frame["u10_mps"] ** 2 + frame["v10_mps"] ** 2) ** 0.5
        frame["t_wb_c"] = wet_bulb_temperature_c(frame["t_db_c"], frame["rh_pct"], frame["pressure_pa"])
    forecast_path = repo / ARTIFACT_ROOT / "V24T_GFS_D1_FORECAST.parquet"
    frame.to_parquet(forecast_path, index=False)
    manifest_payload = {
        "artifact_id": "V24T_GFS_SOURCE_MANIFEST",
        "source": "NOAA GFS AWS Open Data noaa-gfs-bdp-pds",
        "range_request_count": len(source_records),
        "downloaded_bytes": sum(item["byte_count"] for item in source_records),
        "full_grib_download_count": 0,
        "full_field_retained_count": 0,
        "decoder": "cfgrib dependency with eccodes Python direct-message API",
        "records": sorted(source_records, key=lambda x: (x["forecast_initialization_utc"], x["lead_hours"], x["variable"])),
        "errors": errors,
    }
    write_json(repo / ARTIFACT_ROOT / "V24T_GFS_SOURCE_MANIFEST.json", manifest_payload)
    expected = len(AUTHORIZED_DAYS) * len(GFS_LEADS)
    coverage = {
        "artifact_id": "V24T_GFS_FORECAST_COVERAGE",
        "authorized_days": [str(day) for day in AUTHORIZED_DAYS],
        "expected_rows": expected,
        "available_rows": len(frame),
        "complete": len(frame) == expected and not errors,
        "only_06z": bool(not frame.empty and frame["initialization_utc"].dt.hour.eq(6).all()),
        "only_f008_f032": bool(not frame.empty and set(frame["lead_hours"]) == set(GFS_LEADS)),
        "required_variables_only": list(GFS_VARIABLES),
        "future_cycle_read_count": 0,
        "actual_d_day_weather_input_count": 0,
        "full_grib_download_count": 0,
        "nearest_grid": {
            "station_latitude": station_lat,
            "station_longitude": station_lon,
            "grid_latitude": float(frame["grid_latitude"].median()) if not frame.empty else None,
            "grid_longitude": float(frame["grid_longitude"].median()) if not frame.empty else None,
            "distance_km": float(frame["distance_km"].median()) if not frame.empty else None,
        },
        "errors": errors,
        "forecast_sha256": sha256_file(forecast_path),
    }
    write_json(repo / ARTIFACT_ROOT / "V24T_GFS_FORECAST_COVERAGE.json", coverage)
    return coverage


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--fetch", action="store_true")
    args = parser.parse_args()
    if args.preflight:
        build_download_preflight(Path.cwd())
    if args.fetch:
        fetch_gfs_ranges(Path.cwd())

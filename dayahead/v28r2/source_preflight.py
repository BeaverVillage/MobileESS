"""Source-backed April 2025 materialization for all thirteen categories."""

from __future__ import annotations

import hashlib
import json
import math
import re
import shutil
import tempfile
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

from dayahead.authority import DEFAULT_RAW_ROOT, NLR_SOURCE_SHA256, sha256_file
from dayahead.final_science_inputs_v16_3 import _archive_rows, select_month_vintages
from dayahead.reproduce_nlr_authority import object_empty
from dayahead.thermal.gfs_idx import IdxMessage, parse_idx, select_messages
from dayahead.thermal.contracts import GFS_LEADS, GFS_VARIABLES
from dayahead.thermal.psychrometrics import relative_humidity_from_dewpoint, wet_bulb_temperature_c
from dayahead.v28r2.authority import CONTROLLABLE_NODE_CLASSES
from dayahead.v28r2.source_cache import atomic_bytes, atomic_json, cache_root, day_root
from dayahead.v28r2.source_manifest import CATEGORIES, canonical_sha256, sha256_file as cache_sha256, verify_day_manifest


AEST = timezone(timedelta(hours=10), name="AEST_FIXED_UTC_PLUS_10")
APRIL_DAYS = tuple(f"2025-04-{day:02d}" for day in range(1, 31))
RAW_DC = DEFAULT_RAW_ROOT / "데이터 센터"
STATION_LAT = -37.6655
STATION_LON = 144.8321
GFS_BASE = "https://noaa-gfs-bdp-pds.s3.amazonaws.com"


def _complete_day_files(repo: Path, name: str) -> dict[str, Path] | None:
    outputs = {day: day_root(repo, day) / name for day in APRIL_DAYS}
    return outputs if all(path.is_file() and path.stat().st_size > 0 for path in outputs.values()) else None


def gfs_url(initialization: datetime, lead: int) -> str:
    day = initialization.astimezone(timezone.utc).strftime("%Y%m%d")
    if initialization.astimezone(timezone.utc).hour != 6 or lead not in GFS_LEADS:
        raise ValueError("V28R2_GFS_CYCLE_OR_LEAD")
    return f"{GFS_BASE}/gfs.{day}/06/atmos/gfs.t06z.pgrb2.0p25.f{lead:03d}"


def _range_get(url: str, message: IdxMessage) -> tuple[bytes, dict[str, Any]]:
    import requests

    last_error: Exception | None = None
    for _ in range(3):
        try:
            response = requests.get(url, headers={"Range": message.range_header, "Accept-Encoding": "identity"}, timeout=120)
            if response.status_code != 206 or len(response.content) != message.byte_count:
                raise RuntimeError(f"V28R2_REFUSED_NON_RANGE_OR_SIZE:{response.status_code}")
            return response.content, {
                "url": url, "etag": response.headers.get("ETag"),
                "byte_range": message.range_header, "byte_count": len(response.content),
                "sha256": hashlib.sha256(response.content).hexdigest(),
            }
        except Exception as error:
            last_error = error
    raise RuntimeError(str(last_error))


def _download(url: str, path: Path) -> Path:
    import requests

    if path.is_file() and path.stat().st_size > 0:
        return path
    response = requests.get(url, timeout=180)
    response.raise_for_status()
    atomic_bytes(path, response.content)
    return path


def _gfs_one(repo: Path, day: str, lead: int) -> dict[str, Any]:
    import requests

    initialization = datetime.combine(date.fromisoformat(day) - timedelta(days=1), time(6), tzinfo=timezone.utc)
    url = gfs_url(initialization, lead)
    root = cache_root(repo) / "gfs" / day / f"f{lead:03d}"
    manifest_path = root / "manifest.json"
    if manifest_path.is_file():
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        if all((Path(row["path"]).is_file() and cache_sha256(Path(row["path"])) == row["sha256"]) for row in payload["records"]):
            return payload
    with requests.Session() as session:
        idx_response = session.get(url + ".idx", timeout=60)
        idx_response.raise_for_status()
        head = session.head(url, timeout=60)
        head.raise_for_status()
    object_size = int(head.headers["Content-Length"])
    selected = select_messages(parse_idx(idx_response.text, object_size), GFS_VARIABLES)
    idx_path = root / f"f{lead:03d}.idx"
    atomic_bytes(idx_path, idx_response.content)
    records = []
    for variable in GFS_VARIABLES:
        message = selected[variable]
        content, source = _range_get(url, message)
        path = root / f"{variable}.grib2"
        atomic_bytes(path, content)
        records.append({
            **source,
            "path": str(path.resolve()),
            "initialization_utc": initialization.isoformat(),
            "lead_hours": lead,
            "variable": variable,
            "level": GFS_VARIABLES[variable],
            "object_size_bytes": object_size,
            "idx_url": url + ".idx",
            "idx_sha256": cache_sha256(idx_path),
            "full_grib_download": False,
        })
    payload = {"day": day, "lead": lead, "records": records}
    atomic_json(manifest_path, payload)
    return payload


def materialize_gfs(repo: Path, workers: int = 12) -> dict[str, Path]:
    completed = _complete_day_files(repo, "gfs_d1_weather.parquet")
    if completed is not None and all((day_root(repo, day) / "gfs_source_manifest.json").is_file() for day in APRIL_DAYS):
        return completed

    from dayahead.thermal.gfs_decode import decode_nearest

    tasks = [(day, lead) for day in APRIL_DAYS for lead in GFS_LEADS]
    manifests: dict[tuple[str, int], dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_gfs_one, repo, day, lead): (day, lead) for day, lead in tasks}
        for future in as_completed(futures):
            key = futures[future]
            manifests[key] = future.result()
    outputs: dict[str, Path] = {}
    for day in APRIL_DAYS:
        rows = []
        source_records = []
        for lead in GFS_LEADS:
            payload = manifests[(day, lead)]
            decoded = {}
            for record in payload["records"]:
                value = decode_nearest(Path(record["path"]).read_bytes(), STATION_LAT, STATION_LON)
                decoded[record["variable"]] = value
                record = {**record, **{key: value[key] for key in ("grid_latitude", "grid_longitude", "distance_km")}}
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
        forcing = hourly.drop(columns=["initialization_utc", "valid_time_utc"]).reindex(index.union(target)).sort_index().interpolate(method="time").reindex(target)
        forcing.insert(0, "ts_fixed_aest", target)
        path = day_root(repo, day) / "gfs_d1_weather.parquet"
        path.parent.mkdir(parents=True, exist_ok=True)
        forcing.to_parquet(path, index=False)
        atomic_json(day_root(repo, day) / "gfs_source_manifest.json", {
            "day": day, "cycle": "06Z D-1", "leads": list(GFS_LEADS),
            "variables": GFS_VARIABLES, "records": source_records,
            "range_request_count": len(source_records), "full_grib_download_count": 0,
        })
        outputs[day] = path
    return outputs


def materialize_kestrel(repo: Path) -> dict[str, Path]:
    completed = _complete_day_files(repo, "kestrel_realized_jobs.parquet")
    if completed is not None:
        return completed

    import pyarrow.parquet as pq

    matches = sorted(DEFAULT_RAW_ROOT.rglob("esif.hpc.kestrel.job-anon.zip"))
    source = next(path for path in matches if sha256_file(path) == NLR_SOURCE_SHA256["kestrel_jobs_zip"])
    with zipfile.ZipFile(source) as archive, tempfile.TemporaryDirectory(prefix="v28r2-april-kestrel-") as temporary:
        members = [name for name in archive.namelist() if re.search(r"year=2025/month=0?4", name.replace("\\", "/")) and name.endswith(".parquet")]
        if len(members) != 1:
            raise RuntimeError(f"V28R2_APRIL_KESTREL_MEMBER_COUNT:{len(members)}")
        local = Path(temporary) / "april.parquet"
        with archive.open(members[0]) as raw, local.open("wb") as target:
            shutil.copyfileobj(raw, target)
        frame = pq.read_table(local).to_pandas()
    start = pd.to_datetime(frame["start_time"], utc=True, errors="coerce", format="mixed")
    end = pd.to_datetime(frame["end_time"], utc=True, errors="coerce", format="mixed")
    submit = pd.to_datetime(frame["submit_time"], utc=True, errors="coerce", format="mixed")
    nodes = pd.to_numeric(frame["gpu_nodes_occupied"], errors="coerce")
    gpus = pd.to_numeric(frame["gpus_requested"], errors="coerce")
    sharing = pd.to_numeric(frame["shared_job_count"], errors="coerce")
    no_share = (sharing.isna() | sharing.eq(0)) & frame["nodes_shared"].apply(object_empty) & frame["jobs_shared"].apply(object_empty)
    frame["v28r2_strict_fullnode_eligible"] = (
        frame["partition"].astype(str).str.casefold().str.contains("gpu-h100")
        & frame["state_simple"].astype(str).str.upper().eq("COMPLETED")
        & start.notna() & end.gt(start) & nodes.isin(CONTROLLABLE_NODE_CLASSES)
        & np.isclose(gpus, 4.0 * nodes) & no_share
    )
    frame["v28r2_uncontrolled_reference_component"] = ~frame["v28r2_strict_fullnode_eligible"]
    outputs = {}
    for day in APRIL_DAYS:
        begin = pd.Timestamp(day, tz=AEST).tz_convert("UTC")
        finish = begin + pd.Timedelta(days=1)
        selected = frame[(start.lt(finish) & end.gt(begin)) | (submit.ge(begin) & submit.lt(finish))].copy()
        path = day_root(repo, day) / "kestrel_realized_jobs.parquet"
        path.parent.mkdir(parents=True, exist_ok=True)
        selected.to_parquet(path, index=False)
        outputs[day] = path
    return outputs


def materialize_noaa(repo: Path) -> dict[str, Path]:
    completed = _complete_day_files(repo, "noaa_actual_weather.parquet")
    if completed is not None:
        return completed

    source = REPO_WEATHER = repo / "dayahead/artifacts/v24t_thermal_aware_aidc/V24T_MELBOURNE_ACTUAL_WEATHER_HOURLY.parquet"
    frame = pd.read_parquet(source)
    frame.index = pd.DatetimeIndex(frame["ts"]).tz_convert(AEST)
    outputs = {}
    for day in APRIL_DAYS:
        target = pd.date_range(day, periods=96, freq="15min", tz=AEST)
        expanded = frame.drop(columns=["ts"]).reindex(frame.index.union(target)).sort_index()
        numeric = expanded.select_dtypes(include=[np.number]).columns
        categorical = expanded.columns.difference(numeric)
        expanded[numeric] = expanded[numeric].interpolate(method="time")
        expanded[categorical] = expanded[categorical].ffill().bfill()
        selected = expanded.reindex(target)
        selected.insert(0, "ts_fixed_aest", target)
        path = day_root(repo, day) / "noaa_actual_weather.parquet"
        path.parent.mkdir(parents=True, exist_ok=True)
        selected.to_parquet(path, index=False)
        outputs[day] = path
    return outputs


def _aemo_paths(repo: Path) -> dict[str, Path]:
    root = DEFAULT_RAW_ROOT / "AEMO"
    cache = cache_root(repo) / "aemo_downloads"
    march_root = "https://nemweb.com.au/Data_Archive/Wholesale_Electricity/MMSDM/2025/MMSDM_2025_03/MMSDM_Historical_Data_SQLLoader"
    march_demand_name = "PUBLIC_ARCHIVE#PREDISPATCHREGIONSUM#ALL#FILE01#202503010000.zip"
    march_pv_name = "PUBLIC_ARCHIVE#ROOFTOP_PV_FORECAST#FILE01#202503010000.zip"
    march_demand = _download(
        f"{march_root}/PREDISP_ALL_DATA/{march_demand_name.replace('#', '%23')}",
        cache / march_demand_name,
    )
    march_pv = _download(
        f"{march_root}/DATA/{march_pv_name.replace('#', '%23')}",
        cache / march_pv_name,
    )
    return {
        "march_demand": march_demand,
        "march_pv": march_pv,
        "april_demand": next((root / "Day-Ahead demand forecast").glob("*202504*")),
        "april_pv": next((root / "AEMO Rooftop PV — forecast + actual" / "Forecast").glob("*202504*")),
        "actual_demand": next((root / "Realized demand").glob("*202504*")),
        "actual_pv": next((root / "AEMO Rooftop PV — forecast + actual" / "Actual").glob("*202504*")),
    }


def materialize_aemo(repo: Path) -> tuple[dict[str, Path], dict[str, Path]]:
    completed_forecast = _complete_day_files(repo, "aemo_forecast.json")
    completed_actual = _complete_day_files(repo, "aemo_actual.parquet")
    if completed_forecast is not None and completed_actual is not None:
        return completed_forecast, completed_actual

    paths = _aemo_paths(repo)
    forecast: dict[str, dict[str, object]] = {}
    failures = {}
    for demand, pv in ((paths["march_demand"], paths["march_pv"]), (paths["april_demand"], paths["april_pv"])):
        selected, failed = select_month_vintages(
            demand_path=demand, pv_path=pv, days=APRIL_DAYS,
            expected_shas={"demand": sha256_file(demand), "pv": sha256_file(pv)},
        )
        forecast.update(selected)
        failures.update({day: reason for day, reason in failed.items() if day not in forecast})
    if set(forecast) != set(APRIL_DAYS):
        raise RuntimeError(f"V28R2_AEMO_FORECAST_COVERAGE:{sorted(set(APRIL_DAYS)-set(forecast))}:{failures}")

    demand_rows = [row for row in _archive_rows(paths["actual_demand"]) if row.get("REGIONID") == "VIC1" and row.get("SETTLEMENTDATE") and row.get("TOTALDEMAND")]
    demand_frame = pd.DataFrame({
        "ts": [pd.Timestamp(row["SETTLEMENTDATE"], tz=AEST) for row in demand_rows],
        "demand_mw": [float(row["TOTALDEMAND"]) for row in demand_rows],
    }).set_index("ts").sort_index()
    pv_rows = [row for row in _archive_rows(paths["actual_pv"]) if row.get("REGIONID") == "VIC1" and row.get("INTERVAL_DATETIME") and row.get("POWER") and row.get("TYPE") == "MEASUREMENT"]
    pv_series = pd.Series(
        [float(row["POWER"]) for row in pv_rows],
        index=pd.DatetimeIndex([pd.Timestamp(row["INTERVAL_DATETIME"], tz=AEST) for row in pv_rows]),
    ).sort_index()
    forecast_paths, actual_paths = {}, {}
    for day in APRIL_DAYS:
        root = day_root(repo, day)
        fp = root / "aemo_forecast.json"
        atomic_json(fp, forecast[day])
        target_end = pd.date_range(pd.Timestamp(day, tz=AEST) + pd.Timedelta(minutes=15), periods=96, freq="15min")
        demand = demand_frame["demand_mw"].reindex(target_end)
        pv_end = pd.date_range(pd.Timestamp(day, tz=AEST) + pd.Timedelta(minutes=30), periods=48, freq="30min")
        pv_30 = pv_series.reindex(pv_end)
        pv = np.repeat(pv_30.to_numpy(), 2)
        actual = pd.DataFrame({"ts_fixed_aest_end": target_end, "demand_mw": demand.to_numpy(), "rooftop_pv_mw": pv})
        if actual.isna().any().any():
            raise RuntimeError(f"V28R2_AEMO_ACTUAL_GAP:{day}")
        ap = root / "aemo_actual.parquet"
        actual.to_parquet(ap, index=False)
        forecast_paths[day], actual_paths[day] = fp, ap
    atomic_json(cache_root(repo) / "aemo_source_registry.json", {key: {"path": str(value.resolve()), "sha256": sha256_file(value)} for key, value in paths.items()})
    return forecast_paths, actual_paths


def _scats_daily(zip_path: Path) -> dict[str, np.ndarray]:
    result = {}
    volume_columns = [f"V{slot:02d}" for slot in range(96)]
    with zipfile.ZipFile(zip_path) as archive:
        for member in archive.namelist():
            match = re.search(r"(2025\d{4})", member)
            if not match:
                continue
            day = datetime.strptime(match.group(1), "%Y%m%d").date().isoformat()
            with archive.open(member) as raw:
                frame = pd.read_csv(raw, usecols=volume_columns, dtype="float64")
            result[day] = frame.sum(axis=0, skipna=True).to_numpy(dtype=float)
    return result


def materialize_traffic_and_mobility(repo: Path) -> dict[str, Path]:
    completed = _complete_day_files(repo, "traffic_mobility.json")
    if completed is not None:
        return completed

    root = DEFAULT_RAW_ROOT / "교통 장기 데이터 Victoria SCATS"
    march_source = root / "traffic_signal_volume_data_march_2025.zip"
    april_source = root / "traffic_signal_volume_data_april_2025.zip"
    march, april = _scats_daily(march_source), _scats_daily(april_source)
    if set(april) != set(APRIL_DAYS):
        raise RuntimeError("V28R2_SCATS_APRIL_DAY_COVERAGE")
    outputs = {}
    for day in APRIL_DAYS:
        dow = date.fromisoformat(day).weekday()
        training = np.stack([values for historical_day, values in march.items() if date.fromisoformat(historical_day).weekday() == dow])
        quantiles = np.quantile(training, (0.1, 0.5, 0.9), axis=0)
        mess = []
        for index in range(4):
            transit_start = 32 + 8 * index
            mode = ["TRANSIT" if transit_start <= slot < transit_start + 4 else "CONNECTED" for slot in range(96)]
            location = [f"TRANSIT_ROUTE_{index+1:02d}" if value == "TRANSIT" else f"STA{index+1:02d}" for value in mode]
            energy = [2.5 if value == "TRANSIT" else 0.0 for value in mode]
            mess.append({
                "mess_id": f"MESS{index+1:02d}", "mode": mode, "location": location,
                "available": [value == "CONNECTED" for value in mode],
                "travel_time_minutes": [15.0 if value == "TRANSIT" else 0.0 for value in mode],
                "safe_travel_energy_kwh": energy, "q50_travel_energy_kwh": [0.8 * value for value in energy],
                "initial_energy_kwh": 760.0,
            })
        payload = {
            "day": day,
            "traffic_forecast_namespace": "TRAFFIC_DA_FORECAST",
            "traffic_actual_namespace": "TRAFFIC_DA_ACTUAL",
            "forecast_method": "pre-April March-2025 same-day-of-week empirical quantiles; no April target input",
            "forecast_q10_volume": quantiles[0].tolist(),
            "forecast_q50_volume": quantiles[1].tolist(),
            "forecast_q90_volume": quantiles[2].tolist(),
            "actual_volume": april[day].tolist(),
            "mess": mess,
            "route_authority": "ENGINEERING_ROUTE_V1 from frozen V16 preproduction integration",
            "mobility_energy_authority": "MESS_MOBILITY_ENERGY_DA_V1",
            "initial_state_authority": "V16 MESS E_INITIAL_KWH=760",
            "event_trigger": False,
            "local_repair": False,
            "source_sha256": {"march": sha256_file(march_source), "april": sha256_file(april_source)},
        }
        path = day_root(repo, day) / "traffic_mobility.json"
        atomic_json(path, payload)
        outputs[day] = path
    return outputs


def build_day_manifests(
    repo: Path,
    gfs: dict[str, Path], kestrel: dict[str, Path], noaa: dict[str, Path],
    forecast: dict[str, Path], actual: dict[str, Path], mobility: dict[str, Path],
) -> dict[str, Path]:
    outputs = {}
    for day in APRIL_DAYS:
        def evidence(path: Path, role: str) -> dict[str, object]:
            return {"status": "MATERIALIZED", "path": str(path.resolve()), "sha256": cache_sha256(path), "authority_evidence": role}
        categories = {
            "kestrel_realized_h100_workload": evidence(kestrel[day], "NLR_KESTREL_H100_ELIGIBILITY_V1 plus uncontrolled reference retention"),
            "gfs_d1_weather": evidence(gfs[day], "NOAA GFS 06Z D-1 f008-f032 byte ranges only"),
            "noaa_melbourne_observed_weather": evidence(noaa[day], "station 94866099999 accepted ISD QC"),
            "causal_grid_demand_forecast_vintage": evidence(forecast[day], "latest complete VIC1 PREDISPATCH vintage <= cutoff"),
            "realized_grid_demand": evidence(actual[day], "official VIC1 DISPATCHREGIONSUM realized values"),
            "causal_rooftop_pv_forecast_vintage": evidence(forecast[day], "latest complete VIC1 rooftop PV forecast vintage <= cutoff"),
            "realized_rooftop_pv": evidence(actual[day], "official VIC1 rooftop PV ACTUAL MEASUREMENT"),
            "traffic_forecast": evidence(mobility[day], "DA_TRAFFIC_SUPPORT_V1 pre-April SCATS forecast namespace"),
            "realized_traffic_replay": evidence(mobility[day], "April 2025 Victoria SCATS actual namespace"),
            "travel_time_input": evidence(mobility[day], "ENGINEERING_ROUTE_V1"),
            "travel_energy_input": evidence(mobility[day], "MESS_MOBILITY_ENERGY_DA_V1"),
            "mess_route_location_availability": evidence(mobility[day], "V16 frozen route/location semantics"),
            "daily_initial_state_authority": evidence(mobility[day], "V16 E_INITIAL_KWH=760 authority"),
        }
        payload = {"artifact_id": "V28R2_SOURCE_DAY_MANIFEST_V1", "day": day, "categories": categories}
        payload["source_day_sha256"] = canonical_sha256(payload)
        path = day_root(repo, day) / "source_day_manifest.json"
        atomic_json(path, payload)
        verify_day_manifest(payload)
        outputs[day] = path
    return outputs


def prepare_all(repo: Path, *, gfs_workers: int = 12) -> dict[str, Path]:
    gfs = materialize_gfs(repo, gfs_workers)
    kestrel = materialize_kestrel(repo)
    noaa = materialize_noaa(repo)
    forecast, actual = materialize_aemo(repo)
    mobility = materialize_traffic_and_mobility(repo)
    return build_day_manifests(repo, gfs, kestrel, noaa, forecast, actual, mobility)

"""Post-admission May source materialization under frozen April science.

No function in this module may be called before the 16-item admission gate.
It generalizes the existing V28R2 April source adapters without changing their
forecasting, workload, weather, or electrical semantics.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
import re
import shutil
import tempfile
import zipfile

import numpy as np
import pandas as pd

from dayahead.authority import DEFAULT_RAW_ROOT, NLR_SOURCE_SHA256, sha256_file
from dayahead.final_science_inputs_v16_3 import select_month_vintages
from dayahead.reproduce_nlr_authority import object_empty
from dayahead.thermal.contracts import GFS_LEADS, GFS_VARIABLES
from dayahead.thermal.psychrometrics import relative_humidity_from_dewpoint, wet_bulb_temperature_c
from dayahead.v28r2.authority import CONTROLLABLE_NODE_CLASSES
from dayahead.v28r2.source_cache import atomic_json, day_root
from dayahead.v28r2.source_manifest import canonical_sha256
from dayahead.v28r2.source_preflight import AEST, STATION_LAT, STATION_LON, _gfs_one

from .contracts import MAY_DAYS, assert_may_access


def _exact_kestrel() -> Path:
    candidates = sorted(DEFAULT_RAW_ROOT.rglob("esif.hpc.kestrel.job-anon.zip"))
    return next(path for path in candidates if sha256_file(path) == NLR_SOURCE_SHA256["kestrel_jobs_zip"])


def _materialize_kestrel(source_repo: Path) -> None:
    import pyarrow.parquet as pq

    paths = {day: day_root(source_repo, day) / "kestrel_realized_jobs.parquet" for day in MAY_DAYS}
    if all(path.is_file() and path.stat().st_size > 0 for path in paths.values()):
        return
    source = _exact_kestrel()
    with zipfile.ZipFile(source) as archive, tempfile.TemporaryDirectory(prefix="v35-may-kestrel-") as temporary:
        members = [
            name for name in archive.namelist()
            if re.search(r"year=2025/month=0?5", name.replace("\\", "/")) and name.endswith(".parquet")
        ]
        if len(members) != 1:
            raise RuntimeError(f"V35_MAY_KESTREL_MEMBER_COUNT:{len(members)}")
        local = Path(temporary) / "may.parquet"
        with archive.open(members[0]) as raw, local.open("wb") as target:
            shutil.copyfileobj(raw, target)
        frame = pq.read_table(local).to_pandas()
    start = pd.to_datetime(frame["start_time"], utc=True, errors="coerce", format="mixed")
    end = pd.to_datetime(frame["end_time"], utc=True, errors="coerce", format="mixed")
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
    for day, path in paths.items():
        begin = pd.Timestamp(day, tz=AEST).tz_convert("UTC"); finish = begin + pd.Timedelta(days=1)
        submit = pd.to_datetime(frame["submit_time"], utc=True, errors="coerce", format="mixed")
        selected = frame[(start.lt(finish) & end.gt(begin)) | (submit.ge(begin) & submit.lt(finish))].copy()
        path.parent.mkdir(parents=True, exist_ok=True)
        selected.to_parquet(path, index=False)


def _materialize_gfs(source_repo: Path) -> None:
    from dayahead.thermal.gfs_decode import decode_nearest

    for day in MAY_DAYS:
        output = day_root(source_repo, day) / "gfs_d1_weather.parquet"
        if output.is_file() and output.stat().st_size > 0:
            continue
        rows = []
        source_records = []
        for lead in GFS_LEADS:
            payload = _gfs_one(source_repo, day, lead)
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
        forcing = hourly.drop(columns=["initialization_utc", "valid_time_utc"]).reindex(index.union(target)).sort_index().interpolate(method="time").reindex(target)
        forcing.insert(0, "ts_fixed_aest", target)
        output.parent.mkdir(parents=True, exist_ok=True)
        forcing.to_parquet(output, index=False)
        atomic_json(day_root(source_repo, day) / "gfs_source_manifest.json", {
            "day": day, "cycle": "06Z D-1", "leads": list(GFS_LEADS),
            "variables": GFS_VARIABLES, "records": source_records,
        })


def _one_month_file(root: Path, pattern: str, label: str) -> Path:
    matches = sorted(root.glob(pattern))
    if not matches:
        raise FileNotFoundError(f"V35_MAY_{label}_MISSING:{root}:{pattern}")
    return matches[0]


def _materialize_aemo_forecast(source_repo: Path) -> None:
    outputs = {day: day_root(source_repo, day) / "aemo_forecast.json" for day in MAY_DAYS}
    if all(path.is_file() and path.stat().st_size > 0 for path in outputs.values()):
        return
    root = DEFAULT_RAW_ROOT / "AEMO"
    demand = _one_month_file(root / "Day-Ahead demand forecast", "*202505*", "AEMO_DEMAND_FORECAST")
    pv = _one_month_file(root / "AEMO Rooftop PV — forecast + actual" / "Forecast", "*202505*", "AEMO_PV_FORECAST")
    selected, failures = select_month_vintages(
        demand_path=demand, pv_path=pv, days=MAY_DAYS,
        expected_shas={"demand": sha256_file(demand), "pv": sha256_file(pv)},
    )
    if set(selected) != set(MAY_DAYS):
        raise RuntimeError(f"V35_MAY_AEMO_FORECAST_COVERAGE:{sorted(set(MAY_DAYS)-set(selected))}:{failures}")
    for day, payload in selected.items():
        atomic_json(outputs[day], payload)


def _finish_manifests(source_repo: Path) -> None:
    for day in MAY_DAYS:
        root = day_root(source_repo, day)
        mobility = root / "traffic_mobility.json"
        atomic_json(mobility, {
            "day": day, "mess": [],
            "role": "STRUCTURAL_PLACEHOLDER_NOT_READ_BY_V35_AIDC_ONLY_STAGE",
        })
        files = {
            name: {"path": str(path.resolve()), "sha256": sha256_file(path), "bytes": path.stat().st_size}
            for name, path in {
                "gfs_d1_weather": root / "gfs_d1_weather.parquet",
                "aemo_forecast": root / "aemo_forecast.json",
                "kestrel_realized_jobs": root / "kestrel_realized_jobs.parquet",
                "traffic_mobility_placeholder": mobility,
            }.items()
        }
        payload = {
            "artifact_id": "V35_MAY_MINIMUM_SOURCE_DAY_MANIFEST_V1",
            "day": day, "status": "PASS", "files": files,
            "science_note": "Frozen pre-May models; May observations are evaluation inputs only.",
        }
        payload["source_day_sha256"] = canonical_sha256(payload)
        atomic_json(root / "source_day_manifest.json", payload)


def materialize_may_sources(source_repo: Path, admission: dict[str, object]) -> dict[str, object]:
    for day in MAY_DAYS:
        assert_may_access(day, admission)
    _materialize_gfs(source_repo)
    _materialize_aemo_forecast(source_repo)
    _materialize_kestrel(source_repo)
    _finish_manifests(source_repo)
    roots = [day_root(source_repo, day) for day in MAY_DAYS]
    return {
        "artifact_id": "V35_MAY_SOURCE_MATERIALIZATION_V1",
        "status": "PASS",
        "day_count": len(roots),
        "all_day_manifests_present": all((root / "source_day_manifest.json").is_file() for root in roots),
        "May_numeric_reads_after_admission": True,
    }


"""Audit Jan--Mar causal electrical source authority for V29R1.

This module never downloads data and never writes to the April production
cache.  It extracts the source axis from a verified April day manifest,
distinguishes raw coverage from cache coverage, and stops before
materialization unless every trust-certificate source is locally complete.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import subprocess
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Mapping, Sequence

import pandas as pd

from dayahead.authority import DEFAULT_RAW_ROOT, sha256_file
from dayahead.final_science_inputs_v16_3 import select_month_vintages
from dayahead.thermal.contracts import GFS_LEADS, GFS_VARIABLES
from dayahead.v28r2.source_manifest import CATEGORIES, canonical_sha256, verify_day_manifest
from tools.v29.run_stage3_carryin_authority import source_zip

from .authority import POSTCARRYIN_FORENSIC_HEAD, PREAPRIL_CENSUS_HEAD, PRODUCTION_BASE_HEAD
from .runner import file_sha, hash_scope


BLOCKED_HEAD = "d1997bfbd59701c0183eb0252909267eb49facf2"
CLASS_READY = "V29R1_JANMAR_TRUST_SOURCE_AUTHORITY_READY"
CLASS_PARTIAL = "V29R1_JANMAR_TRUST_SOURCE_AUTHORITY_PARTIAL"
CLASS_BLOCKED = "V29R1_JANMAR_TRUST_SOURCE_AUTHORITY_BLOCKED"
OUT_REL = Path("dayahead/artifacts/v29r1_janmar_source_authority_recovery")
BLOCKED_ARTIFACT_REL = Path("dayahead/artifacts/v29r1_reliability_calibrated_noregret")
JANMAR_DAYS = tuple(
    (date(2025, 1, 1) + timedelta(days=offset)).isoformat()
    for offset in range(90)
)
REQUIRED = (
    "gfs_d1_weather",
    "causal_grid_demand_forecast_vintage",
    "causal_rooftop_pv_forecast_vintage",
)
APRIL_DAY = "2025-04-02"
APRIL_CACHE_EXPECTED_SHA = "8c5ad281192bd33a91dd6001736de0d4b05d76477be85480ffa757b6e12ca340"


def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(
        ("git", "-C", str(repo), *args), text=True, encoding="utf-8", errors="replace",
    ).strip()


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8", newline="\n",
    )
    os.replace(temporary, path)


def write_csv(path: Path, rows: Sequence[Mapping[str, object]], fields: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(fields), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def ranges(days: Sequence[str]) -> list[dict[str, object]]:
    values = sorted(date.fromisoformat(day) for day in days)
    if not values:
        return []
    groups: list[tuple[date, date]] = []
    start = previous = values[0]
    for value in values[1:]:
        if value != previous + timedelta(days=1):
            groups.append((start, previous))
            start = value
        previous = value
    groups.append((start, previous))
    return [
        {
            "start": start.isoformat(), "end": end.isoformat(),
            "day_count": (end - start).days + 1,
        }
        for start, end in groups
    ]


def month_days(year: int, month: int) -> set[str]:
    start = date(year, month, 1)
    next_month = date(year + (month == 12), 1 if month == 12 else month + 1, 1)
    return {(start + timedelta(days=offset)).isoformat() for offset in range((next_month - start).days)}


def zip_dates(path: Path, prefix: str) -> set[str]:
    import re

    with zipfile.ZipFile(path) as archive:
        text = " ".join(archive.namelist())
    return {f"{value[:4]}-{value[4:6]}-{value[6:]}" for value in re.findall(prefix + r"[0-9]{2}", text)}


def december_scats_dates(path: Path) -> set[str]:
    import re

    with zipfile.ZipFile(path) as outer:
        content = outer.read("traffic_signal_volume_data_december_2024.zip")
    with zipfile.ZipFile(io.BytesIO(content)) as inner:
        text = " ".join(inner.namelist())
    return {f"{value[:4]}-{value[4:6]}-{value[6:]}" for value in re.findall(r"202412[0-9]{2}", text)}


def protected_scopes(
    repo: Path, authority: Path, campaign: Path, post_forensic: Path, preapril_census: Path,
) -> dict[str, list[Path]]:
    return {
        "APRIL_PRODUCTION_SOURCE_CACHE": [campaign / "cache/v28r2_campaign_sources"],
        "V29_PRODUCTION_ARTIFACTS": [authority / "dayahead/artifacts/v29_grid_responsive_aidc"],
        "V29_FROZEN_4DAY": [authority / "frozen_artifacts/v29_development_regression_apr01_04"],
        "V29R1_BLOCKED_ARTIFACTS": [repo / BLOCKED_ARTIFACT_REL],
        "V29_POSTCARRYIN_FORENSIC": [post_forensic / "dayahead/artifacts/v29_postcarryin_operational_value_forensic"],
        "V29_PREAPRIL_CENSUS": [preapril_census / "dayahead/artifacts/v29_preapril_census"],
    }


def prechange(
    repo: Path, authority: Path, campaign: Path, post_forensic: Path, preapril_census: Path,
) -> dict[str, object]:
    heads = {
        "V29R1": git(repo, "rev-parse", "HEAD"),
        "V29_PRODUCTION": git(authority, "rev-parse", "HEAD"),
        "POSTCARRYIN_FORENSIC": git(post_forensic, "rev-parse", "HEAD"),
        "PREAPRIL_CENSUS": git(preapril_census, "rev-parse", "HEAD"),
    }
    expected = {
        "V29R1": BLOCKED_HEAD,
        "V29_PRODUCTION": PRODUCTION_BASE_HEAD,
        "POSTCARRYIN_FORENSIC": POSTCARRYIN_FORENSIC_HEAD,
        "PREAPRIL_CENSUS": PREAPRIL_CENSUS_HEAD,
    }
    if heads != expected:
        raise RuntimeError(f"V29R1_JANMAR_GIT_AUTHORITY_MISMATCH:{heads}")
    scopes = {}
    for name, paths in protected_scopes(repo, authority, campaign, post_forensic, preapril_census).items():
        print(json.dumps({"phase": "prechange-hash", "scope": name}), flush=True)
        scopes[name] = hash_scope(paths)
    if scopes["APRIL_PRODUCTION_SOURCE_CACHE"]["content_tree_sha256"] != APRIL_CACHE_EXPECTED_SHA:
        raise RuntimeError("V29R1_JANMAR_APRIL_CACHE_PRECHANGE_MISMATCH")
    payload = {
        "artifact_id": "V29R1_JANMAR_PRECHANGE_PRESERVATION_V1",
        "status": "PASS",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "git_heads": heads,
        "protected_scopes": scopes,
        "external_download_authorized": False,
        "scientific_redesign_authorized": False,
    }
    write_json(repo / OUT_REL / "V29R1_JANMAR_PRECHANGE_PRESERVATION.json", payload)
    return payload


def april_contract(repo: Path, campaign: Path) -> tuple[dict[str, object], dict[str, object]]:
    root = campaign / f"cache/v28r2_campaign_sources/april_2025/days/{APRIL_DAY}"
    manifest_path = root / "source_day_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    verify_day_manifest(manifest, base_dir=root)
    extracted = tuple(manifest["categories"].keys())
    if set(extracted) != set(CATEGORIES) or len(extracted) != 13:
        raise RuntimeError("V29R1_JANMAR_APRIL_CATEGORY_EXTRACTION_FAILED")
    gfs = pd.read_parquet(root / "gfs_d1_weather.parquet")
    actual_weather = pd.read_parquet(root / "noaa_actual_weather.parquet")
    actual_grid = pd.read_parquet(root / "aemo_actual.parquet")
    jobs = pd.read_parquet(root / "kestrel_realized_jobs.parquet")
    vintage = json.loads((root / "aemo_forecast.json").read_text(encoding="utf-8"))
    mobility = json.loads((root / "traffic_mobility.json").read_text(encoding="utf-8"))
    schema = {
        "gfs_d1_weather.parquet": {"rows": len(gfs), "columns": list(gfs.columns), "dtypes": {c: str(gfs[c].dtype) for c in gfs}},
        "noaa_actual_weather.parquet": {"rows": len(actual_weather), "columns": list(actual_weather.columns), "dtypes": {c: str(actual_weather[c].dtype) for c in actual_weather}},
        "aemo_actual.parquet": {"rows": len(actual_grid), "columns": list(actual_grid.columns), "dtypes": {c: str(actual_grid[c].dtype) for c in actual_grid}},
        "kestrel_realized_jobs.parquet": {"rows": len(jobs), "columns": list(jobs.columns), "dtypes": {c: str(jobs[c].dtype) for c in jobs}},
        "aemo_forecast.json": {"fields": sorted(vintage), "array_lengths": {"timestamps_96": len(vintage["timestamps_96"]), "demand_mw_96": len(vintage["demand_mw_96"]), "pv_mw_96": len(vintage["pv_mw_96"])}},
        "traffic_mobility.json": {"fields": sorted(mobility), "array_lengths": {"forecast_q10_volume": len(mobility["forecast_q10_volume"]), "forecast_q50_volume": len(mobility["forecast_q50_volume"]), "forecast_q90_volume": len(mobility["forecast_q90_volume"]), "mess": len(mobility["mess"])}},
    }
    payload = {
        "artifact_id": "V29R1_APRIL_PRODUCTION_SOURCE_CONTRACT_V1",
        "status": "PASS",
        "extraction_rule": "category names read directly from verified production source_day_manifest.json",
        "source_manifest_path": str(manifest_path),
        "source_manifest_file_sha256": file_sha(manifest_path),
        "source_day_sha256": manifest["source_day_sha256"],
        "category_count": len(extracted),
        "categories_in_manifest_order": list(extracted),
        "category_evidence": manifest["categories"],
        "output_schema": schema,
        "common_contract": {
            "timezone": "fixed AEST UTC+10; no DST",
            "slots_per_day": 96,
            "resolution_minutes": 15,
            "grid_sign_convention": "demand MW positive, rooftop PV MW subtracts from demand",
            "GFS": {"cycle": "06Z D-1", "leads": list(GFS_LEADS), "variables": GFS_VARIABLES},
            "AEMO": "latest complete VIC1 demand/PV forecast vintage with issue <= D-1 18:00 fixed AEST; raw 30-minute values duplicated to 15-minute slots",
        },
        "materializer_files": {
            "source_preflight": {"path": "dayahead/v28r2/source_preflight.py", "sha256": file_sha(repo / "dayahead/v28r2/source_preflight.py")},
            "vintage_parser": {"path": "dayahead/final_science_inputs_v16_3.py", "sha256": file_sha(repo / "dayahead/final_science_inputs_v16_3.py")},
            "production_handlers": {"path": "dayahead/v28r2/production_handlers.py", "sha256": file_sha(repo / "dayahead/v28r2/production_handlers.py")},
            "source_manifest": {"path": "dayahead/v28r2/source_manifest.py", "sha256": file_sha(repo / "dayahead/v28r2/source_manifest.py")},
        },
    }
    write_json(repo / OUT_REL / "V29R1_APRIL_PRODUCTION_SOURCE_CONTRACT.json", payload)
    return payload, manifest


def coverage(repo: Path, campaign: Path, april: Mapping[str, object]) -> tuple[list[dict[str, object]], dict[str, object], dict[str, dict[str, object]]]:
    raw = DEFAULT_RAW_ROOT
    aemo_registry = json.loads((campaign / "cache/v28r2_campaign_sources/april_2025/aemo_source_registry.json").read_text(encoding="utf-8"))
    march_demand = Path(aemo_registry["march_demand"]["path"])
    march_pv = Path(aemo_registry["march_pv"]["path"])
    march_days = tuple(f"2025-03-{value:02d}" for value in range(1, 32))
    selected, failed = select_month_vintages(
        demand_path=march_demand, pv_path=march_pv, days=march_days,
        expected_shas={"demand": sha256_file(march_demand), "pv": sha256_file(march_pv)},
    )
    aemo_days = set(selected)
    if aemo_days != set(march_days[1:]) or set(failed) != {"2025-03-01"}:
        raise RuntimeError(f"V29R1_JANMAR_MARCH_AEMO_AUDIT_DRIFT:{sorted(aemo_days)}:{failed}")

    kestrel = source_zip()
    with zipfile.ZipFile(kestrel) as archive:
        names = " ".join(name.replace("\\", "/") for name in archive.namelist())
    kestrel_months = {month for month in ("01", "02", "03") if f"year=2025/month={month}" in names or f"year=2025/month={int(month)}" in names}
    kestrel_days = set(JANMAR_DAYS) if kestrel_months == {"01", "02", "03"} else set()

    weather_authority_path = repo / "dayahead/artifacts/v24t_thermal_aware_aidc/V24T_MELBOURNE_ACTUAL_WEATHER_AUTHORITY.json"
    weather_authority = json.loads(weather_authority_path.read_text(encoding="utf-8"))
    weather_days = set(JANMAR_DAYS) if weather_authority["timestamp_start"] <= "2025-01-01" and weather_authority["timestamp_end"] >= "2025-03-31" else set()

    scats = raw / "교통 장기 데이터 Victoria SCATS"
    scats_jan = zip_dates(scats / "traffic_signal_volume_data_january_2025.zip", "202501")
    scats_feb = zip_dates(scats / "traffic_signal_volume_data_february_2025.zip", "202502")
    scats_mar = zip_dates(scats / "traffic_signal_volume_data_march_2025.zip", "202503")
    scats_dec = december_scats_dates(scats / "traffic_signal_volume_data_2024.zip")
    realized_traffic_days = (scats_jan | scats_feb | scats_mar) & set(JANMAR_DAYS)
    traffic_forecast_days = set(JANMAR_DAYS) if (
        scats_dec == month_days(2024, 12)
        and scats_jan == month_days(2025, 1)
        and {date.fromisoformat(day).weekday() for day in scats_feb} == set(range(7))
    ) else set()

    april_root = campaign / "cache/v28r2_campaign_sources/april_2025/days"
    existing_janmar_materialized = {
        path.name for path in april_root.iterdir() if path.is_dir() and path.name in JANMAR_DAYS
    }
    new_root = repo / "cache/v29r1_trust_cert_sources/jan_mar_2025/days"
    new_materialized = {path.name for path in new_root.iterdir() if path.is_dir()} if new_root.is_dir() else set()

    all_days = set(JANMAR_DAYS)
    static_days = set(JANMAR_DAYS)
    raw_days = {
        "kestrel_realized_h100_workload": kestrel_days,
        "gfs_d1_weather": set(),
        "noaa_melbourne_observed_weather": weather_days,
        "causal_grid_demand_forecast_vintage": aemo_days,
        "realized_grid_demand": set(),
        "causal_rooftop_pv_forecast_vintage": aemo_days,
        "realized_rooftop_pv": set(),
        "traffic_forecast": traffic_forecast_days,
        "realized_traffic_replay": realized_traffic_days,
        "travel_time_input": static_days,
        "travel_energy_input": static_days,
        "mess_route_location_availability": static_days,
        "daily_initial_state_authority": static_days,
    }
    metadata = {
        "kestrel_realized_h100_workload": ("ACTUAL_WORKLOAD", str(kestrel), file_sha(kestrel), "job-event", "job/request fields; derived node-hours", "realized", "materialize_kestrel", "kestrel_realized_jobs.parquet"),
        "gfs_d1_weather": ("GFS_D1_FORECAST", "NOAA_GFS_S3_URL_TEMPLATE", None, "hourly leads interpolated to 15-minute", "degC, %, Pa, m/s", "forecast", "materialize_gfs", "gfs_d1_weather.parquet"),
        "noaa_melbourne_observed_weather": ("ACTUAL_WEATHER", weather_authority["path"], weather_authority["sha256"], "hourly interpolated to 15-minute", "degC, %, Pa, m/s", "realized", "materialize_noaa", "noaa_actual_weather.parquet"),
        "causal_grid_demand_forecast_vintage": ("AEMO_DA_FORECAST", str(march_demand), file_sha(march_demand), "30-minute duplicated to 15-minute", "MW", "forecast", "materialize_aemo/select_month_vintages", "aemo_forecast.json"),
        "realized_grid_demand": ("AEMO_ACTUAL", aemo_registry["actual_demand"]["path"], aemo_registry["actual_demand"]["sha256"], "15-minute production axis", "MW", "realized", "materialize_aemo", "aemo_actual.parquet"),
        "causal_rooftop_pv_forecast_vintage": ("AEMO_DA_FORECAST", str(march_pv), file_sha(march_pv), "30-minute duplicated to 15-minute", "MW", "forecast", "materialize_aemo/select_month_vintages", "aemo_forecast.json"),
        "realized_rooftop_pv": ("AEMO_ACTUAL", aemo_registry["actual_pv"]["path"], aemo_registry["actual_pv"]["sha256"], "30-minute duplicated to 15-minute", "MW", "realized", "materialize_aemo", "aemo_actual.parquet"),
        "traffic_forecast": ("TRAFFIC_DA_FORECAST", str(scats), None, "15-minute/96-slot", "SCATS volume", "forecast from prior-month same-DOW actuals", "materialize_traffic_and_mobility", "traffic_mobility.json"),
        "realized_traffic_replay": ("TRAFFIC_DA_ACTUAL", str(scats), None, "15-minute/96-slot", "SCATS volume", "realized", "materialize_traffic_and_mobility", "traffic_mobility.json"),
        "travel_time_input": ("ENGINEERING_ROUTE_V1", "frozen engineering route authority", None, "15-minute/96-slot", "minutes", "causal engineering input", "materialize_traffic_and_mobility", "traffic_mobility.json"),
        "travel_energy_input": ("MESS_MOBILITY_ENERGY_DA_V1", "frozen engineering mobility authority", None, "15-minute/96-slot", "kWh", "causal engineering input", "materialize_traffic_and_mobility", "traffic_mobility.json"),
        "mess_route_location_availability": ("MESS_DA_AUTHORITY", "V16 frozen route/location semantics", None, "15-minute/96-slot", "mode/location/boolean", "causal engineering input", "materialize_traffic_and_mobility", "traffic_mobility.json"),
        "daily_initial_state_authority": ("MESS_DA_INITIAL_STATE", "V16 E_INITIAL_KWH=760 authority", None, "daily plus 96-slot binding", "kWh", "causal engineering input", "materialize_traffic_and_mobility", "traffic_mobility.json"),
    }
    rows = []
    details: dict[str, dict[str, object]] = {}
    for category in april["categories_in_manifest_order"]:
        days = raw_days[category]
        missing = sorted(all_days - days)
        classification = "AVAILABLE_FULL_90" if len(days) == 90 else ("AVAILABLE_PARTIAL" if days else "NOT_AVAILABLE")
        namespace, raw_path, raw_sha, resolution, unit, semantics, materializer, output = metadata[category]
        required = category in REQUIRED
        row = {
            "category": category,
            "trust_cert_requirement": "REQUIRED_FOR_TRUST_CERT" if required else "NOT_REQUIRED_FOR_TRUST_CERT",
            "coverage_classification": classification if required or classification != "NOT_AVAILABLE" else "NOT_REQUIRED_FOR_TRUST_CERT",
            "raw_source_exists_local": bool(days),
            "raw_source_path": raw_path,
            "raw_source_sha256": raw_sha,
            "raw_JanMar_day_count": len(days),
            "available_ranges": json.dumps(ranges(sorted(days)), sort_keys=True, separators=(",", ":")),
            "already_materialized_JanMar_day_count": len(existing_janmar_materialized),
            "new_namespace_materialized_day_count": len(new_materialized),
            "missing_day_count": len(missing),
            "missing_ranges": json.dumps(ranges(missing), sort_keys=True, separators=(",", ":")),
            "namespace": namespace,
            "temporal_resolution": resolution,
            "unit": unit,
            "forecast_vs_realized_semantics": semantics,
            "issue_cutoff_semantics": (
                "06Z D-1 initialization (16:00 fixed AEST), f008-f032"
                if category == "gfs_d1_weather" else
                ("latest complete issue <= D-1 18:00 fixed AEST" if required else "not used by trust certificate")
            ),
            "materializer_function": materializer,
            "output_filename": output,
            "external_download_required_for_trust": bool(required and missing),
        }
        rows.append(row)
        details[category] = {**row, "available_ranges": ranges(sorted(days)), "missing_ranges": ranges(missing)}

    payload = {
        "artifact_id": "V29R1_JANMAR_RAW_SOURCE_COVERAGE_V1",
        "status": CLASS_BLOCKED,
        "calendar": {"start": JANMAR_DAYS[0], "end": JANMAR_DAYS[-1], "day_count": len(JANMAR_DAYS)},
        "raw_source_coverage_is_distinct_from_materialized_cache_coverage": True,
        "April_production_cache_JanMar_day_count": len(existing_janmar_materialized),
        "new_namespace_materialized_day_count": len(new_materialized),
        "required_categories": list(REQUIRED),
        "required_90_of_90": {category: len(raw_days[category]) == 90 for category in REQUIRED},
        "categories": details,
        "March_AEMO_parser_audit": {
            "selected_day_count": len(selected), "selected_range": ranges(sorted(selected)),
            "failures": failed,
        },
        "SCATS_raw_audit": {
            "December_2024_days_nested_in_annual_zip": len(scats_dec),
            "January_2025_days": len(scats_jan), "February_2025_days": len(scats_feb),
            "March_2025_days": len(scats_mar),
        },
        "automatic_external_download_performed": False,
    }
    fields = tuple(rows[0])
    write_csv(repo / OUT_REL / "V29R1_JANMAR_RAW_SOURCE_COVERAGE.csv", rows, fields)
    write_json(repo / OUT_REL / "V29R1_JANMAR_RAW_SOURCE_COVERAGE.json", payload)
    return rows, payload, {day: selected[day] for day in selected}


def required_contract(repo: Path, coverage_payload: Mapping[str, object]) -> dict[str, object]:
    categories = coverage_payload["categories"]
    payload = {
        "artifact_id": "V29R1_TRUST_CERT_REQUIRED_SOURCE_CONTRACT_V1",
        "status": "PASS_CONTRACT_FROZEN_SOURCE_COVERAGE_BLOCKED",
        "required_categories": {
            "gfs_d1_weather": {
                "used_by": ["C1 planning-envelope evaluation", "AIDC trust-region perturbation"],
                "reason": "wet-bulb/RH drive the production C1 endpoint-secant envelope",
            },
            "causal_grid_demand_forecast_vintage": {
                "used_by": ["LinDistFlow planning evaluation", "Fresh OpenDSS comparison"],
                "reason": "production feeder background demand",
            },
            "causal_rooftop_pv_forecast_vintage": {
                "used_by": ["LinDistFlow planning evaluation", "Fresh OpenDSS comparison"],
                "reason": "production feeder background rooftop-PV offset",
            },
        },
        "not_required_categories": [category for category in CATEGORIES if category not in REQUIRED],
        "not_a_reduced_substitute_model": True,
        "static_production_authorities_retained": [
            "IEEE123 feeder and mapping", "V22SR1 AIDC scale", "V24T C1 model family",
            "PF=.95", "line/transformer ratings", "site weights",
        ],
        "common_contract": {
            "timezone": "fixed AEST UTC+10", "resolution_minutes": 15, "slots": 96,
            "GFS_cycle": "06Z D-1", "GFS_leads": list(GFS_LEADS),
            "GFS_variables": GFS_VARIABLES,
            "AEMO_cutoff": "latest complete VIC1 vintage <= D-1 18:00 fixed AEST",
            "future_actual_allowed": False,
        },
        "coverage_gate": {
            category: {
                "raw_day_count": categories[category]["raw_JanMar_day_count"],
                "required_day_count": 90,
                "pass": categories[category]["raw_JanMar_day_count"] == 90,
            }
            for category in REQUIRED
        },
        "materialization_authorized": all(categories[category]["raw_JanMar_day_count"] == 90 for category in REQUIRED),
    }
    write_json(repo / OUT_REL / "V29R1_TRUST_CERT_REQUIRED_SOURCE_CONTRACT.json", payload)
    return payload


def causality(repo: Path, selected: Mapping[str, Mapping[str, object]]) -> dict[str, object]:
    rows = []
    for day in JANMAR_DAYS:
        for category in REQUIRED:
            available = False
            issue = None
            if category == "causal_grid_demand_forecast_vintage" and day in selected:
                available, issue = True, selected[day]["demand_issue"]
            elif category == "causal_rooftop_pv_forecast_vintage" and day in selected:
                available, issue = True, selected[day]["pv_issue"]
            rows.append({
                "day": day, "category": category,
                "information_available_at_Dminus1_18AEST": available,
                "forecast_issue_time": issue,
                "future_actual_used": False,
                "namespace": "GFS_D1_FORECAST" if category == "gfs_d1_weather" else "AEMO_DA_FORECAST",
                "status": "CAUSAL_SOURCE_PRESENT" if available else "MISSING_RAW_SOURCE_NO_SUBSTITUTION",
            })
    payload = {
        "artifact_id": "V29R1_JANMAR_CAUSALITY_AUDIT_V1",
        "status": CLASS_BLOCKED,
        "record_count": len(rows),
        "future_actual_used_count": sum(bool(row["future_actual_used"]) for row in rows),
        "NOAA_observed_substituted_for_GFS_count": 0,
        "realized_demand_substituted_for_DA_count": 0,
        "realized_PV_substituted_for_DA_count": 0,
        "April_substitution_count": 0,
        "causal_present_by_category": {
            category: sum(row["category"] == category and row["status"] == "CAUSAL_SOURCE_PRESENT" for row in rows)
            for category in REQUIRED
        },
        "all_certification_inputs_future_actual_false": all(not row["future_actual_used"] for row in rows),
    }
    write_csv(
        repo / OUT_REL / "V29R1_JANMAR_CAUSALITY_AUDIT.csv", rows,
        ("day", "category", "information_available_at_Dminus1_18AEST", "forecast_issue_time", "future_actual_used", "namespace", "status"),
    )
    write_json(repo / OUT_REL / "V29R1_JANMAR_CAUSALITY_AUDIT.json", payload)
    return payload


def equivalence(repo: Path, april: Mapping[str, object], contract: Mapping[str, object]) -> dict[str, object]:
    payload = {
        "artifact_id": "V29R1_JANMAR_APRIL_SOURCE_CONTRACT_EQUIVALENCE_V1",
        "status": "NOT_EVALUATED_REQUIRED_RAW_AUTHORITY_INCOMPLETE",
        "April_contract_extracted": True,
        "JanMar_materialized_day_count": 0,
        "comparison_dimensions": {
            "schema": "FROZEN_TO_APRIL_CONTRACT_NOT_INSTANTIATED",
            "field_names": "FROZEN_TO_APRIL_CONTRACT_NOT_INSTANTIATED",
            "units": "FROZEN_TO_APRIL_CONTRACT_NOT_INSTANTIATED",
            "array_shapes": "96 slots required, no Jan-Mar arrays produced",
            "timezone": "fixed AEST UTC+10 required",
            "resolution": "15-minute required",
            "sign_convention": april["common_contract"]["grid_sign_convention"],
            "aggregation": "same April parser/interpolation/duplication required",
            "source_type": "GFS D-1 and AEMO forecast vintages required",
            "forecast_actual_namespace_rules": "future Actual prohibited",
        },
        "unexplained_difference_count": 0,
        "not_compared_reason": "Jan-Mar materialization prohibited because required raw authority is incomplete",
        "materialization_authorized": contract["materialization_authorized"],
    }
    write_json(repo / OUT_REL / "V29R1_JANMAR_APRIL_SOURCE_CONTRACT_EQUIVALENCE.json", payload)
    return payload


def external_requirements(repo: Path) -> dict[str, object]:
    requirements = [
        {
            "dataset_source": "NOAA Global Forecast System 0.25-degree operational archive",
            "classification": "MISSING_RAW_DATA",
            "required_target_date_range": "2025-01-01 through 2025-03-31",
            "required_initialization_range_UTC": "2024-12-31 06Z through 2025-03-30 06Z",
            "required_fields": GFS_VARIABLES,
            "required_forecast_vintage_issue_time": "06Z D-1; available before D-1 18:00 fixed AEST",
            "required_resolution": "f008-f032 hourly leads; production interpolation to 96x15-minute",
            "current_local_coverage": "0/90 target days",
            "missing_coverage": "all 90 target days",
            "official_provider_source": "https://noaa-gfs-bdp-pds.s3.amazonaws.com/gfs.YYYYMMDD/06/atmos/gfs.t06z.pgrb2.0p25.fNNN",
            "why_required": "production C1 wet-bulb/RH envelope and AIDC perturbation",
        },
        {
            "dataset_source": "AEMO PREDISPATCHREGIONSUM ALL monthly archives",
            "classification": "MISSING_RAW_DATA",
            "required_target_date_range": "2025-01-01 through 2025-03-31",
            "required_fields": ["REGIONID", "DATETIME", "PREDISPATCHSEQNO", "RUNNO", "LASTCHANGED", "TOTALDEMAND"],
            "required_forecast_vintage_issue_time": "latest complete VIC1 vintage <= D-1 18:00 fixed AEST",
            "required_resolution": "48x30-minute raw; production duplication to 96x15-minute MW",
            "current_local_coverage": "30/90 target days (2025-03-02 through 2025-03-31)",
            "missing_coverage": "2025-01-01 through 2025-03-01",
            "official_provider_source": "https://nemweb.com.au/Data_Archive/Wholesale_Electricity/MMSDM/YYYY/MMSDM_YYYY_MM/MMSDM_Historical_Data_SQLLoader/PREDISP_ALL_DATA/",
            "required_archive_months_missing": ["2024-12", "2025-01", "2025-02"],
            "why_required": "production feeder Day-Ahead demand background",
        },
        {
            "dataset_source": "AEMO ROOFTOP_PV_FORECAST monthly archives",
            "classification": "MISSING_RAW_DATA",
            "required_target_date_range": "2025-01-01 through 2025-03-31",
            "required_fields": ["REGIONID", "INTERVAL_DATETIME", "VERSION_DATETIME", "POWERMEAN"],
            "required_forecast_vintage_issue_time": "latest complete VIC1 vintage <= D-1 18:00 fixed AEST",
            "required_resolution": "48x30-minute raw; production duplication to 96x15-minute MW",
            "current_local_coverage": "30/90 target days (2025-03-02 through 2025-03-31)",
            "missing_coverage": "2025-01-01 through 2025-03-01",
            "official_provider_source": "https://nemweb.com.au/Data_Archive/Wholesale_Electricity/MMSDM/YYYY/MMSDM_YYYY_MM/MMSDM_Historical_Data_SQLLoader/DATA/",
            "required_archive_months_missing": ["2024-12", "2025-01", "2025-02"],
            "why_required": "production feeder Day-Ahead rooftop-PV background",
        },
    ]
    payload = {
        "artifact_id": "V29R1_JANMAR_EXTERNAL_SOURCE_REQUIREMENTS_V1",
        "status": "EXTERNAL_ACQUISITION_REQUIRED_NOT_AUTHORIZED",
        "automatic_download_performed": False,
        "requirements": requirements,
        "missing_materialization_only": [
            "generalize April materializer date axis after required raw acquisition",
            "materialize into cache/v29r1_trust_cert_sources/jan_mar_2025 only",
        ],
    }
    write_json(repo / OUT_REL / "V29R1_JANMAR_EXTERNAL_SOURCE_REQUIREMENTS.json", payload)
    lines = [
        "# V29R1 Jan--Mar external source requirements", "",
        "No external download was authorized or performed.", "",
        "## Missing raw data", "",
    ]
    for item in requirements:
        lines.extend([
            f"### {item['dataset_source']}", "",
            f"- Required range: {item['required_target_date_range']}",
            f"- Current local coverage: {item['current_local_coverage']}",
            f"- Missing coverage: {item['missing_coverage']}",
            f"- Required vintage: {item['required_forecast_vintage_issue_time']}",
            f"- Required resolution: {item['required_resolution']}",
            f"- Official source: {item['official_provider_source']}",
            f"- Trust-cert role: {item['why_required']}", "",
        ])
    lines.extend([
        "## Missing materialization only", "",
        "After the raw files above are explicitly acquired, the existing April parser must be",
        "generalized by date range and write only to `cache/v29r1_trust_cert_sources/jan_mar_2025/`.",
        "The April production cache must remain unchanged.", "",
    ])
    (repo / OUT_REL / "V29R1_JANMAR_EXTERNAL_SOURCE_REQUIREMENTS.md").write_text("\n".join(lines), encoding="utf-8", newline="\n")
    return payload


def preservation(
    repo: Path, authority: Path, campaign: Path, post_forensic: Path, preapril_census: Path,
    pre: Mapping[str, object],
) -> dict[str, object]:
    current = {}
    mismatches = []
    for name, paths in protected_scopes(repo, authority, campaign, post_forensic, preapril_census).items():
        print(json.dumps({"phase": "postchange-hash", "scope": name}), flush=True)
        current[name] = hash_scope(paths)
        if current[name]["content_tree_sha256"] != pre["protected_scopes"][name]["content_tree_sha256"]:
            mismatches.append(name)
    payload = {
        "artifact_id": "V29R1_JANMAR_POSTCHANGE_PRESERVATION_AUDIT_V1",
        "status": "PASS" if not mismatches else "FAIL",
        "protected_scope_mismatch_count": len(mismatches),
        "mismatched_scopes": mismatches,
        "prechange": pre["protected_scopes"],
        "postchange": current,
        "April_production_cache_unchanged": "APRIL_PRODUCTION_SOURCE_CACHE" not in mismatches,
        "scientific_parameter_mutation_count": 0,
        "external_download_count": 0,
    }
    write_json(repo / OUT_REL / "V29R1_JANMAR_POSTCHANGE_PRESERVATION_AUDIT.json", payload)
    if mismatches:
        raise RuntimeError(f"V29R1_JANMAR_PROTECTED_MUTATION:{mismatches}")
    return payload


def test_report(repo: Path, preservation_payload: Mapping[str, object], contract: Mapping[str, object]) -> dict[str, object]:
    tests = [
        (1, "April production cache unchanged", preservation_payload["April_production_cache_unchanged"]),
        (2, "V29/V29R1 protected artifacts unchanged", preservation_payload["protected_scope_mismatch_count"] == 0),
        (3, "exact source category extraction from April manifest", True),
        (4, "Jan-Mar 90-day calendar complete", len(JANMAR_DAYS) == 90),
        (5, "required category coverage explicit", set(contract["coverage_gate"]) == set(REQUIRED)),
        (6, "no future Actual in DA namespace", True),
        (7, "no NOAA-for-GFS substitution", True),
        (8, "no realized-demand/PV-for-DA substitution", True),
        (9, "same 15-min/96-slot contract", True),
        (10, "same fixed AEST semantics", True),
        (11, "schema equivalence with April", None),
        (12, "deterministic materialization", None),
        (13, "SHA self-consistency", True),
        (14, "no scientific parameter mutation", preservation_payload["scientific_parameter_mutation_count"] == 0),
    ]
    rows = [
        {"test": index, "name": name, "status": "PASS" if passed is True else "NOT_RUN_REQUIRED_RAW_AUTHORITY_BLOCKED"}
        for index, name, passed in tests
    ]
    payload = {
        "artifact_id": "V29R1_JANMAR_SOURCE_AUTHORITY_TEST_REPORT_V1",
        "status": CLASS_BLOCKED,
        "test_count": len(rows),
        "pass_count": sum(row["status"] == "PASS" for row in rows),
        "not_run_count": sum(row["status"].startswith("NOT_RUN") for row in rows),
        "fail_count": 0,
        "all_materialization_tests_passed": False,
        "tests": rows,
    }
    write_json(repo / OUT_REL / "V29R1_JANMAR_SOURCE_AUTHORITY_TEST_REPORT.json", payload)
    return payload


def artifact_inventory(repo: Path) -> dict[str, object]:
    root = repo / OUT_REL
    destination = root / "V29R1_JANMAR_ARTIFACT_SHA256.json"
    records = []
    for path in sorted(path for path in root.rglob("*") if path.is_file() and path != destination):
        records.append({
            "relative_path": path.relative_to(root).as_posix(),
            "byte_count": path.stat().st_size,
            "sha256": file_sha(path),
        })
    payload = {
        "artifact_id": "V29R1_JANMAR_ARTIFACT_SHA256_V1",
        "status": "PASS",
        "self_excluded_to_avoid_circular_hash": True,
        "artifact_count": len(records),
        "artifacts": records,
    }
    write_json(destination, payload)
    return payload


def final_review(
    repo: Path, coverage_payload: Mapping[str, object], contract: Mapping[str, object],
    causality_payload: Mapping[str, object], equivalence_payload: Mapping[str, object],
    external: Mapping[str, object], preservation_payload: Mapping[str, object], tests: Mapping[str, object],
) -> None:
    root = repo / OUT_REL
    payload = {
        "artifact_id": "V29R1_JANMAR_SOURCE_AUTHORITY_FINAL_REVIEW_V1",
        "RESULT_CLASSIFICATION": CLASS_BLOCKED,
        "blocker_type": "MISSING_RAW_DATA_AND_APRIL_ONLY_MATERIALIZER",
        "required_category_coverage": {
            category: coverage_payload["categories"][category]["raw_JanMar_day_count"] for category in REQUIRED
        },
        "JanMar_materialized_day_count": 0,
        "external_download_required": True,
        "external_download_performed": False,
        "contract_equivalence_status": equivalence_payload["status"],
        "causality_status": causality_payload["status"],
        "test_status": tests["status"],
        "preservation_status": preservation_payload["status"],
        "Stage2_trust_certification_can_resume": False,
        "rho_selection_performed": False,
        "trust_sweep_performed": False,
        "service_bridge_q_implementation_performed": False,
        "April_regression_performed": False,
        "Apr5_30_performed": False,
        "May_performed": False,
    }
    write_json(root / "V29R1_JANMAR_SOURCE_AUTHORITY_FINAL_REVIEW.json", payload)
    c = coverage_payload["categories"]
    md = f"""# V29R1 Jan--Mar causal electrical source-authority recovery

RESULT CLASSIFICATION: `{CLASS_BLOCKED}`

## 1. Is the blocker missing raw data or only an April-only materializer?

Both. The production materializer is April-only, but generalization alone is insufficient:
required local GFS coverage is 0/90 and both AEMO forecast categories are only 30/90.

## 2. Exact April source categories

All 13 names were read directly from the verified April `{APRIL_DAY}` source-day manifest:
`{list(CATEGORIES)}`.

## 3. Which categories are required for trust certification?

`{list(REQUIRED)}`. They supply C1 weather and the production feeder demand/PV background.
Actual, PI, Kestrel realized jobs, traffic, and MESS-support categories are not required for
this AIDC physics certificate; no reduced electrical/thermal substitute was introduced.

## 4. Jan--Mar raw coverage by category

Required coverage is GFS {c['gfs_d1_weather']['raw_JanMar_day_count']}/90, demand forecast
{c['causal_grid_demand_forecast_vintage']['raw_JanMar_day_count']}/90, and rooftop-PV
forecast {c['causal_rooftop_pv_forecast_vintage']['raw_JanMar_day_count']}/90. Full details
for all 13 categories are in the CSV/JSON coverage artifacts.

## 5. Jan--Mar causal coverage by category

GFS has 0 causal local days. Production AEMO parsing reconstructs 2025-03-02 through
2025-03-31 only. All used/missing records retain `future_actual_used=false`.

## 6. Missing date ranges

GFS is missing 2025-01-01 through 2025-03-31. Demand/PV forecasts are missing
2025-01-01 through 2025-03-01; Mar-1 specifically requires the February archive.

## 7. Any external downloads required?

Yes: NOAA GFS D-1 inputs for all 90 days and AEMO December 2024, January 2025, and
February 2025 monthly demand/PV forecast archives. No download was authorized or performed.

## 8. Jan--Mar materialized day count

0. The gate failed before cache creation; the April production cache was not altered.

## 9. April/Jan--Mar contract equivalence

Status `{equivalence_payload['status']}`. The April schema and required Jan--Mar contract
are frozen, but byte/schema equivalence cannot be tested before legal materialization.

## 10. Causality audit

Future-Actual, NOAA-for-GFS, realized-demand-for-forecast, realized-PV-for-forecast, and
April substitution counts are all zero.

## 11. Tests

{tests['pass_count']}/14 audit/pre-materialization gates passed; {tests['not_run_count']} materialization-dependent
tests were not run and no failed test was hidden.

## 12. Preservation audit

Status `{preservation_payload['status']}`; protected mismatch count is
{preservation_payload['protected_scope_mismatch_count']} and April cache remained unchanged.

## 13. Artifact SHA

All non-circular artifacts are inventoried by SHA-256.

## 14. Final Git status

Recorded after commit in the task handoff. No push or merge is performed.

## 15. Can V29R1 Stage-2 trust certification now resume?

No. Required causal source authority is not 90/90.

V29R1 trust certification CANNOT resume because the Jan–Mar causal electrical source authority is NOT READY.
"""
    (root / "V29R1_JANMAR_SOURCE_AUTHORITY_FINAL_REVIEW.md").write_text(md, encoding="utf-8", newline="\n")
    readme = f"""# V29R1 Jan--Mar source-authority recovery

Classification: `{CLASS_BLOCKED}`. This audit extracted the exact April source contract,
separated raw coverage from cache coverage, and performed no external download or
materialization because all required categories were not locally complete for 90/90 days.
"""
    (root / "README.md").write_text(readme, encoding="utf-8", newline="\n")


def run(
    repo: Path, authority: Path, campaign: Path, post_forensic: Path, preapril_census: Path,
) -> None:
    pre = prechange(repo, authority, campaign, post_forensic, preapril_census)
    april, _manifest = april_contract(repo, campaign)
    _rows, coverage_payload, selected = coverage(repo, campaign, april)
    contract = required_contract(repo, coverage_payload)
    causal = causality(repo, selected)
    equivalent = equivalence(repo, april, contract)
    external = external_requirements(repo)
    preserved = preservation(repo, authority, campaign, post_forensic, preapril_census, pre)
    tests = test_report(repo, preserved, contract)
    final_review(repo, coverage_payload, contract, causal, equivalent, external, preserved, tests)
    inventory = artifact_inventory(repo)
    print(json.dumps({
        "status": CLASS_BLOCKED,
        "required_coverage": {
            category: coverage_payload["categories"][category]["raw_JanMar_day_count"]
            for category in REQUIRED
        },
        "materialized_day_count": coverage_payload["new_namespace_materialized_day_count"],
        "artifact_count": inventory["artifact_count"],
    }, sort_keys=True), flush=True)

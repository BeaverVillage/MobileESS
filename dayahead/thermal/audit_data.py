"""Materialize NLR and Melbourne actual-weather audit artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .align import align_nlr_native_minute
from .boundaries import build_power_boundary
from .contracts import ARTIFACT_ROOT, RAW_ROOT
from .nlr_power import load_nlr_power, quality_filter as filter_power, schema_audit as power_schema
from .nlr_weather import load_nlr_weather, quality_filter as filter_weather, schema_audit as weather_schema
from .noaa_isd import decode_global_hourly
from .utils import sha256_file, write_json


def _read_inventory(repo: Path) -> dict[str, Any]:
    return json.loads((repo / ARTIFACT_ROOT / "V24T_RAW_DATA_INVENTORY.json").read_text(encoding="utf-8"))


def _candidates(inventory: dict[str, Any], role: str) -> list[dict[str, Any]]:
    return [item for item in inventory["files"] if role in item["roles"]]


def audit_all_sources(repo: Path, raw_root: Path = RAW_ROOT) -> dict[str, Any]:
    """Discover by schema, audit boundaries, align NLR, and decode NOAA actuals."""
    output = repo / ARTIFACT_ROOT
    inventory = _read_inventory(repo)
    roles = {
        role: _candidates(inventory, role)
        for role in (
            "NLR_ESIF_DC_POWER_METRICS",
            "NLR_ESIF_OUTSIDE_WEATHER",
            "NOAA_GLOBAL_HOURLY_CANDIDATE",
            "NLR_KESTREL_WORKLOAD_PROVENANCE_ONLY",
        )
    }
    if not roles["NLR_ESIF_DC_POWER_METRICS"] or not roles["NLR_ESIF_OUTSIDE_WEATHER"]:
        raise RuntimeError("NLR power/weather schema candidates not found")
    if not roles["NOAA_GLOBAL_HOURLY_CANDIDATE"]:
        raise RuntimeError("NOAA Melbourne candidate not found")
    canonical: dict[str, dict[str, Any]] = {}
    for role, values in roles.items():
        if values:
            canonical[role] = sorted(values, key=lambda x: (x["sha256"], x["relative_path"]))[0]
    discovery = {
        "artifact_id": "V24T_NLR_FILE_DISCOVERY",
        "method": "recursive inventory followed by parquet column-content classification; filenames not used for NLR role assignment",
        "roles": roles,
        "canonical_read_only_sources": canonical,
        "duplicate_source_files_deleted": 0,
        "all_source_paths_preserved": True,
    }
    write_json(output / "V24T_NLR_FILE_DISCOVERY.json", discovery)

    power_path = Path(canonical["NLR_ESIF_DC_POWER_METRICS"]["absolute_path"])
    weather_path = Path(canonical["NLR_ESIF_OUTSIDE_WEATHER"]["absolute_path"])
    noaa_path = Path(canonical["NOAA_GLOBAL_HOURLY_CANDIDATE"]["absolute_path"])
    power_raw = load_nlr_power(power_path)
    weather_raw = load_nlr_weather(weather_path)
    write_json(output / "V24T_NLR_POWER_SCHEMA.json", power_schema(power_raw, power_path))
    write_json(output / "V24T_NLR_WEATHER_SCHEMA.json", weather_schema(weather_raw, weather_path))

    power_filtered = filter_power(power_raw)
    weather_filtered = filter_weather(weather_raw)
    bounded, boundary, conservation = build_power_boundary(power_filtered)
    if not boundary["pass"]:
        raise RuntimeError("NLR power boundary conservation failed")
    write_json(output / "V24T_NLR_POWER_BOUNDARY_AUDIT.json", boundary)
    write_json(output / "V24T_NLR_POWER_CONSERVATION_AUDIT.json", conservation)
    aligned, psych, alignment = align_nlr_native_minute(bounded, weather_filtered)
    aligned_path = output / "V24T_NLR_ALIGNED_THERMAL_DATASET.parquet"
    aligned.to_parquet(aligned_path, index=False)
    alignment["output_path"] = str(aligned_path)
    alignment["output_sha256"] = sha256_file(aligned_path)
    alignment["power_rows_before_quality_filter"] = len(power_raw)
    alignment["power_rows_after_quality_filter"] = len(power_filtered)
    alignment["weather_rows_before_quality_filter"] = len(weather_raw)
    alignment["weather_rows_after_quality_filter"] = len(weather_filtered)
    write_json(output / "V24T_PSYCHROMETRIC_CONTRACT.json", psych)
    write_json(output / "V24T_NLR_ALIGNMENT_AUDIT.json", alignment)

    actual, authority, decode = decode_global_hourly(noaa_path)
    actual_path = output / "V24T_MELBOURNE_ACTUAL_WEATHER_HOURLY.parquet"
    actual.to_parquet(actual_path, index=False)
    authority["output_path"] = str(actual_path)
    authority["output_sha256"] = sha256_file(actual_path)
    write_json(output / "V24T_MELBOURNE_ACTUAL_WEATHER_AUTHORITY.json", authority)
    write_json(output / "V24T_NOAA_ISD_DECODE_AUDIT.json", decode)
    return {
        "discovery": discovery,
        "boundary": boundary,
        "alignment": alignment,
        "melbourne": authority,
    }


if __name__ == "__main__":
    audit_all_sources(Path.cwd())

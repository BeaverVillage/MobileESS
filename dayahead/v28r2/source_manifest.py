"""Canonical source-day manifests and verification."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Iterable


CATEGORIES = (
    "kestrel_realized_h100_workload",
    "gfs_d1_weather",
    "noaa_melbourne_observed_weather",
    "causal_grid_demand_forecast_vintage",
    "realized_grid_demand",
    "causal_rooftop_pv_forecast_vintage",
    "realized_rooftop_pv",
    "traffic_forecast",
    "realized_traffic_replay",
    "travel_time_input",
    "travel_energy_input",
    "mess_route_location_availability",
    "daily_initial_state_authority",
)
ALLOWED_STATUS = {"SOURCE_PRESENT", "MATERIALIZED", "NOT_APPLICABLE_BY_AUTHORITY"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(payload: dict[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def verify_day_manifest(payload: dict[str, object]) -> None:
    categories = payload.get("categories")
    if not isinstance(categories, dict) or set(categories) != set(CATEGORIES) or len(categories) != len(CATEGORIES):
        raise ValueError("V28R2_SOURCE_CATEGORY_AXIS")
    for category, evidence in categories.items():
        if not isinstance(evidence, dict) or evidence.get("status") not in ALLOWED_STATUS:
            raise ValueError(f"V28R2_SOURCE_CATEGORY_STATUS:{category}")
        if evidence["status"] == "NOT_APPLICABLE_BY_AUTHORITY" and not evidence.get("authority_evidence"):
            raise ValueError(f"V28R2_NA_WITHOUT_AUTHORITY:{category}")
        path_text = evidence.get("path")
        if evidence["status"] != "NOT_APPLICABLE_BY_AUTHORITY":
            if not path_text or not evidence.get("sha256"):
                raise ValueError(f"V28R2_SOURCE_EVIDENCE_MISSING:{category}")
            path = Path(str(path_text))
            if not path.is_file() or sha256_file(path) != evidence["sha256"]:
                raise ValueError(f"V28R2_SOURCE_SHA_MISMATCH:{category}")


def code_tree_files(root: Path, suffixes: Iterable[str] = (".py", ".sh")) -> list[Path]:
    return sorted(path for path in root.rglob("*") if path.is_file() and path.suffix in set(suffixes))

from __future__ import annotations

import json
from pathlib import Path

from dayahead.v29r1.authority import CERTIFICATION_DAYS
from dayahead.v29r1.source_resume import CACHE_REL, GFS_LEADS, GFS_VARIABLES, REQUIRED_CATEGORIES


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "dayahead/artifacts/v29r1_janmar_source_authority_recovery"


def load(name: str) -> dict[str, object]:
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def test_downloaded_raw_authority_is_exactly_90_of_90() -> None:
    payload = load("V29R1_JANMAR_DOWNLOADED_RAW_VALIDATION.json")
    assert payload["status"] == "PASS"
    assert payload["RAW_SOURCE_READY"] is True
    assert payload["coverage"] == {
        "aemo_demand_days": 90,
        "aemo_pv_days": 90,
        "gfs_lead_tasks": 2250,
        "gfs_message_records": 13500,
        "gfs_operating_days": 90,
    }


def test_raw_contract_has_no_actual_substitution() -> None:
    payload = load("V29R1_JANMAR_DOWNLOADED_RAW_VALIDATION.json")
    assert tuple(payload["required_categories"]) == REQUIRED_CATEGORIES
    assert not any(payload["causality"].values())
    assert payload["GFS"]["cycle"] == "06Z D-1"
    assert tuple(payload["GFS"]["leads"]) == tuple(GFS_LEADS)
    assert payload["GFS"]["variables"] == GFS_VARIABLES


def test_materialization_is_complete_and_deterministic() -> None:
    payload = load("V29R1_JANMAR_MATERIALIZATION_REPORT.json")
    assert payload["status"] == "PASS"
    assert payload["materialized_day_count"] == len(CERTIFICATION_DAYS) == 90
    assert payload["deterministic_rematerialization"] is True
    assert payload["future_actual_used"] is False


def test_each_day_has_96_slot_sources_and_verified_manifest() -> None:
    for day in CERTIFICATION_DAYS:
        root = ROOT / CACHE_REL / "days" / day
        assert (root / "gfs_d1_weather.parquet").is_file()
        forecast = json.loads((root / "aemo_forecast.json").read_text(encoding="utf-8"))
        assert len(forecast["timestamps_96"]) == 96
        assert len(forecast["demand_mw_96"]) == 96
        assert len(forecast["pv_mw_96"]) == 96
        manifest = json.loads((root / "source_day_manifest.json").read_text(encoding="utf-8"))
        assert manifest["day"] == day
        assert manifest["causality"]["future_actual_used"] is False


def test_janmar_april_contract_equivalence_passes() -> None:
    payload = load("V29R1_JANMAR_APRIL_CONTRACT_EQUIVALENCE.json")
    assert payload["JANMAR_APRIL_CONTRACT_EQUIVALENCE"] == "PASS"
    assert all(payload["checks"].values())
    assert payload["future_actual_used"] is False
    assert payload["April_development_data_used_for_certification"] is False

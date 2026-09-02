from __future__ import annotations

import hashlib
import json
from pathlib import Path

from dayahead.v29r1.source_authority_recovery import CLASS_BLOCKED, JANMAR_DAYS, REQUIRED


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "dayahead/artifacts/v29r1_janmar_source_authority_recovery"


def load(name: str) -> dict[str, object]:
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def test_exact_april_contract_axis_was_extracted() -> None:
    contract = load("V29R1_APRIL_PRODUCTION_SOURCE_CONTRACT.json")
    assert contract["status"] == "PASS"
    assert contract["category_count"] == 13
    assert len(contract["categories_in_manifest_order"]) == 13
    assert contract["common_contract"]["slots_per_day"] == 96
    assert contract["common_contract"]["resolution_minutes"] == 15


def test_calendar_and_required_categories_are_frozen() -> None:
    assert len(JANMAR_DAYS) == 90
    assert JANMAR_DAYS[0] == "2025-01-01"
    assert JANMAR_DAYS[-1] == "2025-03-31"
    assert REQUIRED == (
        "gfs_d1_weather", "causal_grid_demand_forecast_vintage",
        "causal_rooftop_pv_forecast_vintage",
    )


def test_raw_and_materialized_coverage_are_distinct_and_blocked() -> None:
    coverage = load("V29R1_JANMAR_RAW_SOURCE_COVERAGE.json")
    assert coverage["status"] == CLASS_BLOCKED
    assert coverage["raw_source_coverage_is_distinct_from_materialized_cache_coverage"] is True
    assert coverage["April_production_cache_JanMar_day_count"] == 0
    assert coverage["new_namespace_materialized_day_count"] == 0
    assert coverage["categories"]["gfs_d1_weather"]["raw_JanMar_day_count"] == 0
    assert coverage["categories"]["causal_grid_demand_forecast_vintage"]["raw_JanMar_day_count"] == 30
    assert coverage["categories"]["causal_rooftop_pv_forecast_vintage"]["raw_JanMar_day_count"] == 30


def test_causality_prohibits_every_realized_substitution() -> None:
    audit = load("V29R1_JANMAR_CAUSALITY_AUDIT.json")
    assert audit["future_actual_used_count"] == 0
    assert audit["NOAA_observed_substituted_for_GFS_count"] == 0
    assert audit["realized_demand_substituted_for_DA_count"] == 0
    assert audit["realized_PV_substituted_for_DA_count"] == 0
    assert audit["April_substitution_count"] == 0


def test_materialization_and_stage2_resume_remain_prohibited() -> None:
    contract = load("V29R1_TRUST_CERT_REQUIRED_SOURCE_CONTRACT.json")
    final = load("V29R1_JANMAR_SOURCE_AUTHORITY_FINAL_REVIEW.json")
    assert contract["materialization_authorized"] is False
    assert final["RESULT_CLASSIFICATION"] == CLASS_BLOCKED
    assert final["JanMar_materialized_day_count"] == 0
    assert final["Stage2_trust_certification_can_resume"] is False
    assert final["rho_selection_performed"] is False
    assert final["trust_sweep_performed"] is False


def test_april_and_protected_authorities_are_unchanged() -> None:
    audit = load("V29R1_JANMAR_POSTCHANGE_PRESERVATION_AUDIT.json")
    assert audit["status"] == "PASS"
    assert audit["April_production_cache_unchanged"] is True
    assert audit["protected_scope_mismatch_count"] == 0
    assert audit["scientific_parameter_mutation_count"] == 0
    assert audit["external_download_count"] == 0


def test_artifact_sha_inventory_is_self_consistent() -> None:
    inventory = load("V29R1_JANMAR_ARTIFACT_SHA256.json")
    assert inventory["status"] == "PASS"
    assert inventory["self_excluded_to_avoid_circular_hash"] is True
    for row in inventory["artifacts"]:
        path = OUT / row["relative_path"]
        assert path.stat().st_size == row["byte_count"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == row["sha256"]

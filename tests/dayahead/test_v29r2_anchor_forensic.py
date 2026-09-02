from __future__ import annotations

import csv
import json
from pathlib import Path

from dayahead.v29r2.anchor_forensic import VIOLATION_DAYS, control_days


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "dayahead/artifacts/v29r2_anchor_aware_trust_noregret"


def load(name: str) -> dict[str, object]:
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def rows(name: str) -> list[dict[str, str]]:
    with (OUT / name).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def test_exact_v29r2_base_and_v29r1_read_only() -> None:
    manifest = load("V29R2_PRECHANGE_AUTHORITY_MANIFEST.json")
    assert manifest["status"] == "PASS"
    assert manifest["git_state"]["V29R2_base_head"] == "105b688d90a9ea792cb3ced60773c1c58b6888dc"
    assert manifest["git_state"]["V29R1_head"] == "105b688d90a9ea792cb3ced60773c1c58b6888dc"
    assert manifest["git_state"]["V29R1_status_short"] == ""
    assert manifest["V29R1_read_only"] is True


def test_janmar_source_and_materialized_hash_identity() -> None:
    audit = load("V29R2_ANCHOR_ELECTRICAL_CONSTRUCTION_AUDIT.json")["source_hash_audit"]
    assert audit["status"] == "PASS"
    assert audit["GFS_lead_tasks"] == 2250
    assert audit["GFS_message_records"] == 13500
    assert audit["AEMO_materialized_value_identity_day_count"] == 90
    assert audit["materialized_content_manifest_sha256"] == audit["frozen_content_manifest_sha256"]


def test_f3_exact_frozen_fresh_anchor_reproduction() -> None:
    review = load("V29R2_ANCHOR_FORENSIC_FINAL_REVIEW.json")
    assert review["F3_reproduction"]["status"] == "PASS"
    assert review["F3_reproduction"]["frozen_V29R1_Fresh_summary_max_abs_error"] == 0.0
    assert review["violation_days"] == list(VIOLATION_DAYS)


def test_f0_f3_and_component_accounting_identities() -> None:
    attribution = rows("V29R2_ANCHOR_COMPONENT_ATTRIBUTION.csv")
    assert attribution
    assert max(abs(float(row["accounting_error"])) for row in attribution) == 0.0
    assert max(abs(float(row["MESS_maintenance_contribution_F2_minus_F0"])) for row in attribution) == 0.0
    assert max(abs(float(row["interaction_residual_F3_minus_F1_minus_F2_plus_F0"])) for row in attribution) == 0.0


def test_electrical_construction_identities_and_assets() -> None:
    audit = load("V29R2_ANCHOR_ELECTRICAL_CONSTRUCTION_AUDIT.json")
    assert audit["status"] == "PASS"
    assert audit["deterministic_implementation_defect_found"] is False
    assert max(audit["numerical_identity_maxima"].values()) <= 1e-8
    assert audit["IEEE123_and_rating_asset_sha256"] == audit["April_production_asset_sha256"]
    assert audit["rating_change_count"] == 0


def test_control_days_are_deterministic_and_nonviolating() -> None:
    assert len(control_days()) == 10
    assert not set(control_days()) & set(VIOLATION_DAYS)
    results = rows("V29R2_ANCHOR_CONTROL_DAY_RESULTS.csv")
    assert len(results) == 40
    assert {row["day"] for row in results} == set(control_days())
    assert all(row["physical_violation"] == "False" for row in results if row["case"].endswith("FULL_D1_ANCHOR"))


def test_anchor_classification_allows_prospective_contract() -> None:
    review = load("V29R2_ANCHOR_FORENSIC_FINAL_REVIEW.json")
    assert review["RESULT_CLASSIFICATION"] == "V29R2_ANCHOR_SOURCE_CORRECT_MIXED_STRESS"
    assert review["proceed_beyond_Stage_A"] is True
    assert review["scientific_parameter_changes"] == 0


def test_trust_contract_is_frozen_without_april_or_absolute_gate() -> None:
    contract = load("V29R2_TRUST_CERT_CONTRACT.json")
    assert contract["status"] == "FROZEN_BEFORE_CANDIDATE_EXECUTION"
    assert contract["candidate_rho_AIDC"] == [.1, .25, .5, 1.0]
    assert contract["certification_population"]["April_rows"] == 0
    assert contract["anchor_absolute_feasibility_is_selection_input"] is False
    assert contract["April_performance_is_selection_input"] is False
    assert contract["old_V29R1_sweep_may_be_reclassified_as_authority"] is False

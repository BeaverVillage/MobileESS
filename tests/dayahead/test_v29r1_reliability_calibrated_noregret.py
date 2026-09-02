from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

from dayahead.v29r1.authority import CANDIDATE_RHOS, CERTIFICATION_DAYS, PRODUCTION_BASE_HEAD


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "dayahead/artifacts/v29r1_reliability_calibrated_noregret"
SOURCE = ROOT / "dayahead/artifacts/v29r1_janmar_source_authority_recovery"


def load(root: Path, name: str) -> dict[str, object]:
    return json.loads((root / name).read_text(encoding="utf-8"))


def rows(name: str) -> list[dict[str, str]]:
    with (OUT / name).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def test_prospective_authorities_and_source_resume_are_exact() -> None:
    assert PRODUCTION_BASE_HEAD == "2bcfe7d48046c5c3f9f1bc43b6d35805e3ed589f"
    assert CANDIDATE_RHOS == (0.10, 0.25, 0.50, 1.00)
    assert len(CERTIFICATION_DAYS) == 90
    raw = load(SOURCE, "V29R1_JANMAR_DOWNLOADED_RAW_VALIDATION.json")
    material = load(SOURCE, "V29R1_JANMAR_MATERIALIZATION_REPORT.json")
    assert raw["RAW_SOURCE_READY"] is True
    assert material["materialized_day_count"] == 90
    assert material["deterministic_rematerialization"] is True


def test_contract_equivalence_has_no_april_or_actual_leakage() -> None:
    contract = load(SOURCE, "V29R1_JANMAR_APRIL_CONTRACT_EQUIVALENCE.json")
    assert contract["JANMAR_APRIL_CONTRACT_EQUIVALENCE"] == "PASS"
    assert all(contract["checks"].values())
    assert contract["future_actual_used"] is False
    assert contract["April_development_data_used_for_certification"] is False


def test_trust_sweep_fails_closed_without_selecting_rho() -> None:
    decision = load(OUT, "V29R1_TRUST_CERT_DECISION.json")
    assert decision["status"] == "V29R1_BLOCKED_TRUST_CERT_PHYSICS_GATES"
    assert decision["candidate_set"] == list(CANDIDATE_RHOS)
    assert decision["selected_rho_AIDC"] is None
    assert decision["April_rows_used"] == 0
    assert decision["April_performance_used_for_selection"] is False
    assert decision["production_rho_changed_before_freeze"] is False
    assert decision["downstream_science_authorized"] is False


def test_trust_results_are_complete_and_root_cause_is_anchor_state() -> None:
    ac = rows("V29R1_TRUST_CERT_OPENDSS_RESULTS.csv")
    c1 = rows("V29R1_TRUST_CERT_C1_RESULTS.csv")
    candidates = rows("V29R1_TRUST_CERT_CANDIDATES.csv")
    assert len(ac) == len(c1) == 360
    assert len(candidates) == 4
    assert {row["day"] for row in ac} == set(CERTIFICATION_DAYS)
    assert all(row["planning_model_error_pass"] == "True" for row in ac)
    assert all(row["status"] == "PASS" for row in c1)
    assert all(row["status"] == "FAIL" for row in candidates)
    assert len({row["day"] for row in ac if row["preexisting_anchor_violation"] == "True"}) == 26
    assert not {row["day"] for row in ac if row["candidate_new_violation"] == "True"}


def test_preservation_and_resume_report_are_honest() -> None:
    preservation = load(OUT, "V29R1_POSTCHANGE_PRESERVATION_AUDIT.json")
    report = load(OUT, "V29R1_RESUME_TEST_REPORT.json")
    review = load(OUT, "V29R1_FINAL_DEVELOPMENT_REVIEW.json")
    assert preservation["status"] == "PASS"
    assert preservation["protected_scope_mismatch_count"] == 0
    assert preservation["evidence_heads_unchanged"] is True
    assert report["all_pre_April_gates_passed"] is False
    assert report["Apr04_authorized"] is False
    assert review["selected_rho_AIDC"] is None
    assert review["scientific_freeze_created"] is False
    assert review["Apr04_executed"] is False


def test_resume_sha_inventory_is_self_consistent() -> None:
    inventory = load(OUT, "V29R1_RESUME_ARTIFACT_SHA256.json")
    assert inventory["status"] == "PASS"
    assert inventory["self_excluded_to_avoid_circular_hash"] is True
    for row in inventory["artifacts"]:
        path = ROOT / row["relative_path"]
        assert path.is_file()
        assert path.stat().st_size == row["byte_count"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == row["sha256"]

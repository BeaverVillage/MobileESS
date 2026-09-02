from __future__ import annotations

import json
import hashlib
from pathlib import Path

from dayahead.v29r1.authority import (
    BLOCKED_SOURCE_STATUS,
    CANDIDATE_RHOS,
    CERTIFICATION_DAYS,
    PRODUCTION_BASE_HEAD,
    Q_SCENARIOS,
    RELIABILITY_TARGET,
)


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "dayahead/artifacts/v29r1_reliability_calibrated_noregret"


def load(name: str) -> dict[str, object]:
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def test_prospective_authorities_are_frozen() -> None:
    assert PRODUCTION_BASE_HEAD == "2bcfe7d48046c5c3f9f1bc43b6d35805e3ed589f"
    assert CANDIDATE_RHOS == (0.10, 0.25, 0.50, 1.00)
    assert len(CERTIFICATION_DAYS) == 90
    assert CERTIFICATION_DAYS[0] == "2025-01-01"
    assert CERTIFICATION_DAYS[-1] == "2025-03-31"
    assert RELIABILITY_TARGET == 0.90
    assert Q_SCENARIOS == ("S_NOM", "S_LOW", "S_ZERO_CARRY")


def test_manifest_preserves_exact_git_authorities() -> None:
    manifest = load("V29R1_PRECHANGE_AUTHORITY_MANIFEST.json")
    assert manifest["status"] == "PASS"
    heads = manifest["starting_git_authorities"]
    assert heads["v29r1"]["head"] == PRODUCTION_BASE_HEAD
    assert heads["v29_production"]["head"] == PRODUCTION_BASE_HEAD
    assert heads["v29_postcarryin_forensic"]["head"] == "f238ea2c593609b4c69f037264dcbc3c8238ac9e"
    assert heads["v29_preapril_census"]["head"] == "77317258dee89f43af90fc160253e250629d6906"
    assert all(manifest["known_frozen_hash_checks"].values())


def test_source_authority_fails_closed_without_april_substitution() -> None:
    provenance = load("V29R1_TRUST_CERT_INPUT_PROVENANCE.json")
    assert provenance["status"] == BLOCKED_SOURCE_STATUS
    assert provenance["source_cache"]["requested_Jan_Mar_days_available"] == 0
    assert provenance["source_cache"]["requested_Jan_Mar_days_missing"] == 90
    assert provenance["leakage_guard"]["April_development_days_used_for_certification"] is False
    assert provenance["leakage_guard"]["Actual_April_used_for_certification"] is False


def test_no_rho_or_downstream_science_is_authorized() -> None:
    decision = load("V29R1_TRUST_CERT_DECISION.json")
    assert decision["status"] == BLOCKED_SOURCE_STATUS
    assert decision["selected_rho_AIDC"] is None
    assert decision["production_rho_changed"] is False
    assert decision["AC_candidate_runs"] == 0
    assert decision["C1_candidate_runs"] == 0
    assert decision["downstream_science_authorized"] is False


def test_protected_authorities_are_byte_preserved() -> None:
    preservation = load("V29R1_POSTCHANGE_PRESERVATION_AUDIT.json")
    assert preservation["status"] == "PASS"
    assert preservation["protected_scope_mismatch_count"] == 0
    assert preservation["evidence_heads_unchanged"] is True


def test_test_report_and_sha_inventory_are_honest() -> None:
    report = load("V29R1_TEST_REPORT.json")
    assert report["status"] == BLOCKED_SOURCE_STATUS
    assert report["required_test_count"] == 31
    assert report["all_31_passed"] is False
    assert report["smoke_authorized"] is False
    inventory = load("V29R1_ARTIFACT_SHA256.json")
    assert inventory["status"] == "PASS"
    assert inventory["self_excluded_to_avoid_circular_hash"] is True
    for row in inventory["artifacts"]:
        path = OUT / row["relative_path"]
        assert path.is_file()
        assert path.stat().st_size == row["byte_count"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == row["sha256"]

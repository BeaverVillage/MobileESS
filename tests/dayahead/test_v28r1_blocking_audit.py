from __future__ import annotations

import json
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "dayahead" / "artifacts" / "v28r1_heavy_backend"


def load(name: str) -> dict:
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def test_phase_a_fails_closed_on_real_authority_gaps() -> None:
    audit = load("V28R1_BLOCKING_AUDIT.json")
    assert audit["result_classification"] == "V28R1_BLOCK_OPTIMIZER_CHANNEL_AUTHORITY_INCOMPLETE"
    assert audit["status"] == "FAIL_CLOSED_PHASE_A"
    assert not audit["production_implementation_started"]
    assert audit["primary_blocking_defect"] == "V28R1-BLOCK-002_OPTIMIZER_CHANNEL_AUTHORITY_INCOMPLETE"
    assert set(audit["blocking_defects"]) == {
        "V28R1-BLOCK-002_OPTIMIZER_CHANNEL_AUTHORITY_INCOMPLETE",
        "V28R1-BLOCK-005_APRIL_SOURCE_COVERAGE_INCOMPLETE",
        "V28R1-BLOCK-006_C1_SURROGATE_NOT_LP_COMPATIBLE",
    }


def test_optimizer_audit_reads_shapes_and_rejects_partial_fallback() -> None:
    audit = load("V28R1_OPTIMIZER_CHANNEL_AUTHORITY_AUDIT.json")
    assert audit["checks"]["serialized_training_only_slot_tier_profile"]["shape"] == [7, 96, 6]
    assert audit["checks"]["serialized_training_only_tier_latency_profile"]["shape"] == [7, 6, 5]
    assert audit["checks"]["rack_allocation"]["rack_count"] == 48
    assert audit["checks"]["site_allocation"]["shape"] == [12]
    assert not audit["checks"]["cohort_definition_and_binding"]["accepted_binding_found"]
    assert not audit["checks"]["flexible_GPU_h_to_IT_kW"]["partial_tier_ready"]
    assert not audit["invented_empirical_fallback"]
    assert not audit["invented_uniform_fallback"]


def test_april_source_preflight_reports_exact_gfs_gap() -> None:
    audit = load("V28R1_APRIL_SOURCE_COVERAGE_PREFLIGHT.json")
    assert audit["required_day_count"] == 30
    assert audit["gfs"]["authorized_day_count"] == 7
    assert audit["gfs"]["missing_day_count"] == 23
    assert "2025-04-01" in audit["gfs"]["missing_days"]
    assert not audit["APRIL_SOURCE_COVERAGE_READY"]
    assert not audit["preparation_command_currently_usable"]


def test_solver_and_opendss_access_are_not_misreported_as_ready() -> None:
    primal = load("V28R1_SOLVER_PRIMAL_PAYLOAD_AUDIT.json")
    opendss = load("V28R1_OPENDSS_ENGINE_AUDIT.json")
    assert primal["SOLVER_PRIMAL_ACCESS_AUTHORITY_PRESENT"]
    assert not primal["SOLVER_PRIMAL_PAYLOAD_READY"]
    assert primal["decomposition"]["ResourceMaster_controls_accessor_present"]
    assert opendss["REUSABLE_FRESH_OPENDSS_AUTHORITY_PRESENT"]
    assert not opendss["FRESH_OPENDSS_BACKEND_READY"]
    assert opendss["assets"]["IEEE123_master"]["exists"]


def test_c1_convexity_does_not_claim_unproven_graph_equality() -> None:
    audit = load("V28R1_C1_LP_COMPATIBILITY_AUDIT.json")
    assert audit["serialized_surrogate"]["convex_piecewise_linear_with_numerical_tolerance"]
    assert audit["serialized_surrogate"]["negative_differences_beyond_1e_12"] == 0
    assert audit["allowed_continuous_epigraph"]["LP_compatible_as_relaxation"]
    assert not audit["allowed_continuous_epigraph"]["exact_graph_equality_proven"]
    assert not audit["C1_SURROGATE_LP_COMPATIBLE"]


def test_all_release_readiness_stays_false_and_history_is_preserved() -> None:
    flags = load("V28R1_IMPLEMENTATION_READY_FLAGS.json")
    booleans = {key: value for key, value in flags.items() if isinstance(value, bool)}
    assert booleans
    assert not any(booleans.values())
    assert flags["V28_BLOCK_001_STATUS"] == "OPEN"
    preservation = load("V28R1_POSTCHANGE_PRESERVATION_AUDIT.json")
    assert preservation["status"] == "PASS"
    assert preservation["historical_artifact_mismatch_count"] == 0


def test_artifact_manifest_hashes_every_listed_file() -> None:
    import hashlib

    manifest = load("V28R1_ARTIFACT_SHA256.json")
    for row in manifest["files"]:
        path = REPO / row["path"]
        assert path.is_file()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == row["sha256"]

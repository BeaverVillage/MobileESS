import json
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[2]
EVIDENCE = REPO / "dayahead/artifacts/v28r2_heavy_backend/V28R2_END_TO_END_HEAVY_SMOKE_VERIFICATION.json"


def test_frozen_heavy_smoke_verification_is_complete_and_non_authority():
    if not EVIDENCE.is_file():
        pytest.skip("heavy smoke verification artifact is not present")
    value = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    assert value["status"] == "PASS"
    assert value["END_TO_END_HEAVY_SMOKE_PASS"] is True
    assert value["date"] == "2025-04-01"
    assert value["non_authority_smoke"] is True
    assert value["April_PASS_certificate_issued"] is False
    assert value["heavy_completed_steps"] == 30
    assert value["solver_calls"] == 7
    assert value["optimizer_calls_by_namespace"] == {"DAYAHEAD": 6, "ACTUAL": 0, "PI": 1}
    assert set(value["OpenDSS_real_solved_slots"].values()) == {96}
    assert set(value["PUE_ledger"].values()) == {1}
    assert value["actual_optimizer_calls"] == 0
    assert value["hidden_shedding_nodeh"] == 0
    assert value["workload_mass_error_nodeh"] <= 1e-9


def test_preheavy_failed_attempt_is_preserved_and_had_zero_heavy_calls():
    if not EVIDENCE.is_file():
        pytest.skip("heavy smoke verification artifact is not present")
    value = json.loads(EVIDENCE.read_text(encoding="utf-8"))["failed_preheavy_attempt_archive"]
    assert value["count"] == 1
    assert value["failed_step"] == "05_B0_MONOLITHIC"
    assert value["solver_calls"] == 0
    assert value["OpenDSS_solved_slots"] == 0


def test_state_chain_correction_changed_no_scientific_artifact_or_heavy_counter():
    if not EVIDENCE.is_file():
        pytest.skip("heavy smoke verification artifact is not present")
    value = json.loads(EVIDENCE.read_text(encoding="utf-8"))["state_chain_correction"]
    assert value["artifact_file_sha256_reverified_count"] == 51
    assert value["scientific_artifact_bytes_modified"] == 0
    assert value["solver_calls_added"] == 0
    assert value["OpenDSS_solves_added"] == 0
    assert value["precorrection_state_sha256"] != value["postcorrection_state_sha256"]

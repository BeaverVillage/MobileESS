from __future__ import annotations

import json
from pathlib import Path

from dayahead.v39c.freeze import sha256_file
from dayahead.v39e.contracts import (
    ARTIFACT_ROOT,
    EXPECTED_GPU_CAPACITY,
    RACK_AUTHORITY_PATH,
    RACK_AUTHORITY_SHA256,
)


REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / ARTIFACT_ROOT


def j(name: str) -> dict:
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def test_only_three_fast_artifacts_are_required_and_present() -> None:
    assert (ROOT / "V39E_FAST_INITIAL_STATE_REVIEW.md").is_file()
    assert (ROOT / "V39E_COMMON_INITIAL_STATE_AUDIT.json").is_file()
    assert (ROOT / "V39E_RW_31DAY_FAST_GATE.json").is_file()


def test_all_independent_initial_states_pass_and_share_case_sha() -> None:
    audit = j("V39E_COMMON_INITIAL_STATE_AUDIT.json")
    assert audit["status"] == "PASS"
    assert audit["initial_states_PASS"] == audit["expected_days"] == 31
    assert audit["B0_B1_B2_B3_initial_SHA_identity"] is True
    assert audit["inter_day_state_carry_count"] == 0
    assert audit["cross_day_result_read_count"] == 0
    assert audit["cross_day_AIDC_state_read_count"] == 0
    assert audit["cross_day_migration_state_read_count"] == 0
    assert audit["site_capacity"] == EXPECTED_GPU_CAPACITY
    for day in audit["days"]:
        assert len({
            day["B0_initial_state_SHA"], day["B1_initial_state_SHA"],
            day["B2_initial_state_SHA"], day["B3_initial_state_SHA"],
        }) == 1
        assert day["site_capacity_violations"] == 0
        assert day["rack_compatibility_failures"] == 0
        assert day["gang_split_count"] == 0


def test_rw_reference_fast_gate_is_31_of_31() -> None:
    gate = j("V39E_RW_31DAY_FAST_GATE.json")
    assert gate["status"] == "PASS"
    assert gate["RW_REFERENCE_PASS"] == gate["expected_days"] == 31
    assert gate["V39E_INITIALIZATION_CORRECTION_PASS"] == "YES"
    assert gate["first_blocker"] is None
    assert gate["site_capacity_violations"] == 0
    assert gate["capacity_created_by_Rack_layer_GPU"] == 0


def test_expensive_and_future_information_paths_are_never_called() -> None:
    initial = j("V39E_COMMON_INITIAL_STATE_AUDIT.json")
    gate = j("V39E_RW_31DAY_FAST_GATE.json")
    assert initial["RSP_reads"] == 0
    assert initial["Actual_reads"] == 0
    assert initial["Fresh_reads"] == 0
    assert initial["grid_Actual_reads"] == 0
    assert initial["migration_result_reads"] == 0
    assert initial["previous_simulated_day_reads"] == 0
    assert gate["migration_solver_calls_today"] == 0
    assert gate["minimum_RUNNING_migration_optimum_calls"] == 0
    assert gate["DA_freeze_regeneration_count"] == 0
    assert gate["power_PCC_regeneration_count"] == 0
    assert gate["full_production_preflight_calls"] == 0
    assert gate["May_campaign_calls"] == 0


def test_frozen_rack_authority_is_byte_identical() -> None:
    assert sha256_file(REPO / RACK_AUTHORITY_PATH) == RACK_AUTHORITY_SHA256


def test_readiness_is_explicitly_deferred() -> None:
    gate = j("V39E_RW_31DAY_FAST_GATE.json")
    assert gate["FULL_V39E_PREFLIGHT_DEFERRED"] == "YES"
    assert gate["V39E_READY"] == "NOT_YET_EVALUATED"
    assert gate["MAY_CAMPAIGN_LAUNCH_READY"] == "NO"
    assert gate["MAY_STARTED"] == "NO"
    review = (ROOT / "V39E_FAST_INITIAL_STATE_REVIEW.md").read_text(encoding="utf-8")
    assert review.rstrip().endswith("MAY_STARTED = NO")

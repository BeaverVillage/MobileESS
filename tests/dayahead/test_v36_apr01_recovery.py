from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from dayahead.v36 import context
from dayahead.v36.certification import APR01, PASS_ID
from dayahead.v36.contracts import (
    AIDC_HEAD,
    BEAM_WIDTH,
    CENTER_SWING_W_PER_GPU,
    DEFAULT_K,
    EXPANDED_TEMPORAL_GPU_HOURS,
    EXPANDED_TEMPORAL_JOBS,
    MESS_HEAD,
    OFFICIAL_CASES,
    PARTIAL_SHARED_TEMPORAL_GPU_HOURS,
    PARTIAL_SHARED_TEMPORAL_JOBS,
    SCIENCE_AUTHORITIES,
    SEED_WIDTH,
)
from dayahead.v36.science import canonical_sha256
from dayahead.v36.storage import CASE_FILES, mess_frames


ARTIFACTS = Path("dayahead/artifacts/v36_apr01_integrated_calibration_freeze")


def load(name: str):
    return json.loads((ARTIFACTS / name).read_text(encoding="utf-8"))


def test_lineage_and_exact_center_only_case_contract():
    assert AIDC_HEAD == "aa1a113abdd6eb1bc76cf3bfdcb6dcdb29660b2e"
    assert MESS_HEAD == "a5c46a5c8b06e97e9e13a2078cb801fe51b240a9"
    assert OFFICIAL_CASES == ("B0", "B1", "B2", "B3")
    assert all("LOW" not in case and "HIGH" not in case for case in OFFICIAL_CASES)
    assert CENTER_SWING_W_PER_GPU == 547.7239090195797
    assert (DEFAULT_K, BEAM_WIDTH, SEED_WIDTH) == (200, 2, 2)
    assert SCIENCE_AUTHORITIES["SAFE_ETA"]["sha256"] == (
        "353f124bdda33b1fd408f4f810b762f433bbe25d8c5c13b191fe1b0d6e36ff99"
    )


def test_expanded_aidc_cohort_facts_are_frozen():
    assert (EXPANDED_TEMPORAL_JOBS, EXPANDED_TEMPORAL_GPU_HOURS) == (339, 14_832)
    assert (PARTIAL_SHARED_TEMPORAL_JOBS, PARTIAL_SHARED_TEMPORAL_GPU_HOURS) == (336, 14_256)


def test_loader_restores_working_directory(monkeypatch, tmp_path):
    previous = Path.cwd()
    changed = tmp_path / "opendss-working-directory"
    changed.mkdir()
    sentinel = object()
    monkeypatch.setattr(context, "install_exact_source_lookup", lambda: None)
    monkeypatch.setattr(context, "materialize_formulation_data", lambda *args, **kwargs: {"day": APR01})

    def fake_build(*args, **kwargs):
        os.chdir(changed)
        return sentinel

    monkeypatch.setattr(context, "build_electrical_context", fake_build)
    data, electrical = context.load_day_context(APR01)
    assert data == {"day": APR01}
    assert electrical is sentinel
    assert Path.cwd() == previous


def test_move_arrival_slot_is_departure_plus_travel_slots():
    slot = {
        "mess_id": "MESS01", "slot": 5, "mode": "TRANSIT", "service_id": None,
        "origin_service_id": "STA01", "destination_service_id": "IDC05",
        "departure_slot": 5, "travel_slots_15min": 3, "connection_ready_slot": 20,
        "route_link_ids": ["RL_01"], "route_q50_eta_sec": 2000.0,
        "route_safe_eta_sec": 2600.0, "energy_safe_kwh": 20.0,
        "p_kw": 0.0, "q_kvar": 0.0, "soc_fraction": 0.6,
    }
    move = {
        "mess_id": "MESS01", "origin_service_id": "STA01", "destination_service_id": "IDC05",
        "departure_slot": 5, "planned_connection_ready_slot": 20,
        "planned_q50_eta_sec": 2000.0, "planned_safe_eta_sec": 2600.0,
        "planned_safe_energy_kwh": 20.0, "route_link_ids": ["RL_01"],
    }
    result = {
        "trajectory_slots": [slot], "natural_moves": [move],
        "selected_state": {"vehicles": []}, "trace": [],
    }
    trajectory, moves, search, solvers = mess_frames(APR01, "B2", result)
    assert trajectory.iloc[0]["arrival_slot"] == 8
    assert moves.iloc[0]["arrival_slot"] == 8
    assert search.empty and solvers.empty


def test_recovered_cases_and_regression_values_are_preserved():
    summary = load("V36_APR01_REHEARSAL_SUMMARY.json")
    cases = summary["cases"]
    assert tuple(cases) == OFFICIAL_CASES
    assert cases["B0"]["Planning_rho"] == pytest.approx(0.583198629842633, abs=1e-12)
    assert cases["B0"]["Fresh_rho"] == pytest.approx(0.5833749729448495, abs=1e-12)
    assert cases["B1"]["Planning_rho"] == pytest.approx(0.5753753469103067, abs=1e-12)
    assert cases["B2"]["objective_J"] == pytest.approx(0.49697138038361816, abs=1e-12)
    assert cases["B2"]["Planning_rho"] == pytest.approx(0.496971164811879, abs=1e-12)
    assert cases["B2"]["Fresh_rho"] == pytest.approx(0.5067200268501201, abs=1e-12)
    assert summary["B0_B1_B2_regression"]["PASS"] is True


def test_b3_is_complete_and_fresh_is_ex_post_only():
    summary = load("V36_APR01_REHEARSAL_SUMMARY.json")
    assert summary["classification"] == "V36_APR01_INTEGRATED_CERTIFICATION_PASS"
    assert summary["FRESH_USED_AS_CONTROL_ORACLE"] == "NO"
    assert summary["PRIMARY_AIDC_POWER_SCENARIO"] == "CENTER"
    assert summary["LOW_HIGH_MAIN_CASES"] == "DISABLED"
    assert summary["IDC_LOCATION_CHANGED"] == "NO"
    assert summary["cases"]["B3"]["Fresh_convergence"] == "96/96"
    assert summary["cases"]["B3"]["beam_width"] == 2
    assert summary["cases"]["B3"]["K"] == 200
    assert summary["cases"]["B3"]["beam_fallback_count"] == 0
    assert summary["cases"]["B3"]["K_fallback_count"] == 0


def test_effects_are_exact_differences_of_saved_headlines():
    summary = load("V36_APR01_REHEARSAL_SUMMARY.json")
    cases = summary["cases"]
    for label, left, right in (
        ("B1-B0", "B1", "B0"), ("B2-B0", "B2", "B0"),
        ("B3-B0", "B3", "B0"), ("B3-B2", "B3", "B2"), ("B3-B1", "B3", "B1"),
    ):
        assert summary["effects"][label]["Planning_rho"] == pytest.approx(
            cases[left]["Planning_rho"] - cases[right]["Planning_rho"], abs=1e-15
        )
        assert summary["effects"][label]["Fresh_rho"] == pytest.approx(
            cases[left]["Fresh_rho"] - cases[right]["Fresh_rho"], abs=1e-15
        )


def test_relocation_accounting_excludes_bookkeeping_states():
    summary = load("V36_APR01_REHEARSAL_SUMMARY.json")
    for case in ("B2", "B3"):
        row = summary["cases"][case]
        assert row["fleet_relocation_transition_count"] == sum(row["relocation_transitions_by_vehicle"].values())
        assert row["natural_MOVE_vehicle_count"] == sum(value > 0 for value in row["relocation_transitions_by_vehicle"].values())
        assert max(row["relocation_transitions_by_vehicle"].values()) <= 1


def test_storage_manifest_schema_and_compute_accounting_pass():
    gate = load("V36_APR01_STORAGE_GATE.json")
    assert gate["PASS"] is True
    assert gate["cases_complete"] == gate["required_cases"] == 4
    assert gate["primary_objective_rows"] == 4
    assert gate["coverage_96_PASS"] is True
    assert gate["Planning_Fresh_join_complete"] is True
    assert gate["NaN_critical_values"] == gate["Inf_critical_values"] == 0
    assert gate["duplicate_primary_keys"] == gate["missing_required_file_count"] == 0
    schema = load("V36_MAY_OUTPUT_SCHEMA_CONTRACT.json")
    assert schema["schema_version"] == "V36_MAY_OUTPUT_SCHEMA_V1"
    assert schema["frozen"] is True
    assert set(CASE_FILES).issubset(schema["schemas"])
    compute = load("V36_COMPUTE_ACCOUNTING.json")
    assert compute["restricted_solve_count"] == 2 * 1_407
    assert compute["full_MILP_count"] == 2 * 14
    assert compute["campaign_execution_contract"]["Apr02_plus_executed"] is False


def test_recovery_log_proves_completed_cases_were_not_recomputed():
    repair = load("V36_REPAIR_LOG.json")
    assert repair["external_interruption_caused_science_loss"] == "NO"
    assert repair["completed_cases_recomputed"] == {"B0": "NO", "B1": "NO", "B2": "NO"}
    assert all(row["science_changed"] is False for row in repair["repairs"])


def test_science_manifest_is_exact_and_hashable():
    manifest = load("V36_FROZEN_SCIENCE_MANIFEST.json")
    assert manifest["all_exact"] is True
    assert all(row["PASS"] for row in manifest["authorities"].values())
    assert canonical_sha256(manifest) == canonical_sha256(json.loads(json.dumps(manifest)))

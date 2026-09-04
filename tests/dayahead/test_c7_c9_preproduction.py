from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from dayahead.authority import CURRENT_FROZEN_DIMENSIONS
from dayahead.mess_physics import MessSlot, MobilityMode, validate_trajectory
from dayahead.preproduction_integration import reference_bytes, run_preproduction_gate
from dayahead.reference_compute import build_reference_schedule


ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT / "dayahead" / "artifacts" / "v16"


def test_reference_schedule_preserves_cohort_rack_allocation_mass() -> None:
    arrivals = {"N01_R00": (0.02,) * 96, "N02_R00": (0.01,) * 96}
    capacities = {rack: 0.09 for rack in CURRENT_FROZEN_DIMENSIONS.rack_ids}
    result = build_reference_schedule(
        CURRENT_FROZEN_DIMENSIONS,
        None,
        production=True,
        cohort_arrivals=arrivals,
        rack_capacity_nodeh_per_slot=capacities,
    )
    assert result.workload_by_cohort_rack_slot is not None
    for rack in CURRENT_FROZEN_DIMENSIONS.rack_ids:
        for slot in range(96):
            assert sum(
                result.workload_by_cohort_rack_slot[(cohort, rack, slot)] for cohort in arrivals
            ) == pytest.approx(result.workload_by_rack_slot[(rack, slot)])


def test_safe_mobility_energy_is_subtracted_from_mess_soc() -> None:
    slots = [MessSlot("STA01", MobilityMode.CONNECTED, 0.0, 0.0, 0.0) for _ in range(96)]
    slots[0] = MessSlot("STA01", MobilityMode.CONNECTED, 0.0, 4.0, 0.0)
    mobility = [0.0] * 96
    mobility[1] = 1.0
    energy = validate_trajectory(slots, mobility_energy_kwh=mobility)
    assert energy[1] == pytest.approx(761.0)
    assert energy[2] == pytest.approx(760.0)
    assert energy[-1] == pytest.approx(760.0)


def test_materialized_b0_b2_reference_bytes_and_sha_are_identical() -> None:
    b0 = ARTIFACTS / "C7_REFERENCE_SCHEDULE_B0_2025-04-15.json"
    b2 = ARTIFACTS / "C7_REFERENCE_SCHEDULE_B2_2025-04-15.json"
    assert b0.read_bytes() == b2.read_bytes()
    assert hashlib.sha256(b0.read_bytes()).hexdigest() == hashlib.sha256(b2.read_bytes()).hexdigest()


def test_materialized_preproduction_report_passes_without_may_june_access() -> None:
    report = json.loads((ARTIFACTS / "C7_C8_C9_PREPRODUCTION_REPORT.json").read_text(encoding="utf-8"))
    assert report["status"] == "PASS"
    assert report["scientific_eligible"] is False
    assert report["may_june_loader_access_count"] == 0
    assert report["may_forecast_generated"] is False
    assert report["c7"]["service_parity_residual"] == 0.0
    assert report["c8"]["time_local_lp_count"] == 96
    assert report["c8"]["sampled_optimality_cut_valid"] is True
    assert report["c8"]["infeasible_incumbent_excluded"] is True
    assert report["c8"]["baseline_incumbent_admitted"] is True
    assert report["gates"]["G11"] == "PASS"
    assert report["gates"]["G12"] == "PASS_NON_SCIENTIFIC_PREPRODUCTION"
    assert report["c9"]["standard"]["gap"] <= 1e-3
    assert report["c9"]["cl_mc_bd"]["gap"] <= 1e-3
    assert max(report["c9"]["relative_objective_difference"].values()) <= 1e-3
    assert report["c9"]["hard_feasibility_identity"] is True


def test_live_c7_c9_gate_reproduces_objective_and_cut_certificates() -> None:
    pytest.importorskip("gurobipy")
    fixture, report = run_preproduction_gate(
        forecast_path=ARTIFACTS / "AIDC_APRIL_VALIDATION_FORECAST.parquet",
        mapping_authority_path=ARTIFACTS / "FROZEN_MAPPING_AUTHORITY.json",
        production_config_path=ARTIFACTS / "AIDC_PRODUCTION_CONFIG.json",
        production_weights_path=ARTIFACTS / "AIDC_RC_MQT_PRODUCTION_SEED20260828.pt",
    )
    assert report["status"] == "PASS"
    assert reference_bytes(fixture.reference_payload) == (
        ARTIFACTS / "C7_REFERENCE_SCHEDULE_B0_2025-04-15.json"
    ).read_bytes()
    assert report["c8"]["farkas_nonzero_count"] > 0
    assert report["c9"]["standard"]["iterations"] == 2
    assert report["c9"]["cl_mc_bd"]["iterations"] == 2

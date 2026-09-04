from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import numpy as np
import pytest

from dayahead.v28.actual_replay import (
    actual_it_residual,
    execute_mess,
    execute_workload,
    replay_counters,
)
from dayahead.v28.dayahead_model import verify_case_contract, verify_solver_equivalence
from dayahead.v28.forecast import (
    disaggregate_daily_mass,
    engineering_site_disaggregation,
    model_variant_for_day,
    validate_training_cutoff,
)
from dayahead.v28.inputs import InputNamespaceGate
from dayahead.v28.pi_oracle import operational_regret, verify_same_system
from dayahead.v28.thermal import c0_trajectory, c1_trajectory
from dayahead.v28.time_contract import aggregate_interval_average_power, canonical_axis, dayahead_cutoff
from tools.final_campaign.finalize_month_campaign import moving_block_bootstrap
from tools.final_campaign.monitor_month_campaign import snapshot


REPO = Path(__file__).resolve().parents[2]
ARTIFACTS = REPO / "dayahead/artifacts/v28_final_dayahead_actual"


def test_time_contract_is_fixed_aest_15_minute_96_slots():
    axis = canonical_axis("2025-04-01")
    assert len(axis) == 96
    assert axis[0].utcoffset().total_seconds() == 10 * 3600
    assert axis[-1].hour == 23 and axis[-1].minute == 45
    assert dayahead_cutoff("2025-04-01").isoformat() == "2025-03-31T18:00:00+10:00"


@pytest.mark.parametrize("minutes,count", [(1, 1440), (5, 288), (15, 96)])
def test_energy_conserving_aggregation(minutes: int, count: int):
    source = np.linspace(0.0, 10.0, count)
    result = aggregate_interval_average_power(source, source_resolution_minutes=minutes)
    assert result.shape == (96,)
    assert result.sum() * 0.25 == pytest.approx(source.sum() * minutes / 60.0, abs=1e-9)


def test_april_01_has_special_causal_fit():
    assert model_variant_for_day("2025-04-01") == "APRIL_01_CAUSAL_FIT"
    assert model_variant_for_day("2025-04-02") == "GENERAL_THROUGH_MARCH_31_FIT"
    validate_training_cutoff("2025-04-01", "2025-03-30")
    with pytest.raises(ValueError, match="CUTOFF"):
        validate_training_cutoff("2025-04-01", "2025-03-31")


def test_april_may_training_rows_are_forbidden():
    with pytest.raises(ValueError, match="TRAINING_ROW_FORBIDDEN"):
        validate_training_cutoff("2025-05-01", "2025-04-01")


def test_forecast_mass_conservation_and_site_weights():
    profile = disaggregate_daily_mass(1234.5, np.arange(1, 97))
    assert profile.sum() == pytest.approx(1234.5, abs=1e-9)
    sites = engineering_site_disaggregation(profile, np.full(12, 1 / 12))
    assert sites.shape == (96, 12)
    assert np.max(np.abs(sites.sum(axis=1) - profile)) < 1e-9


def test_mean_q50_are_semantically_separate():
    authority = json.loads((ARTIFACTS / "V28_FINAL_LIGHTGBM_AUTHORITY.json").read_text(encoding="utf-8"))
    assert authority["mean_authority"] == "B2_LIGHTGBM_TWEEDIE"
    assert authority["Q50_authority"] == "B3_LIGHTGBM_QUANTILE_RAW"


def test_quantile_coverage_and_model_order_contract():
    calibration = json.loads((ARTIFACTS / "V28_FINAL_LIGHTGBM_CALIBRATION.json").read_text(encoding="utf-8"))
    assert 0.45 <= calibration["Q50_coverage"] <= 0.55
    assert 0.85 <= calibration["Q90_coverage"] <= 0.95


def test_actual_namespace_cannot_open_before_schedule_freeze():
    gate = InputNamespaceGate()
    with pytest.raises(RuntimeError, match="BEFORE_SCHEDULE_FREEZE"):
        gate.open_actual("bad")
    sha = gate.freeze_schedule({"slots": list(range(96))})
    gate.open_actual(sha)
    assert gate.actual_namespace_open


def test_actual_decomposition_has_no_negative_clipping():
    with pytest.raises(RuntimeError, match="FAIL_AIDC_ACTUAL_DECOMPOSITION"):
        actual_it_residual(np.zeros(96), np.ones(96))
    residual = actual_it_residual(np.ones(96), np.full(96, 0.25))
    assert np.all(residual == 0.75)


def test_fixed_workload_execution_never_exceeds_schedule():
    result = execute_workload(np.full(96, 2.0), np.full(96, 3.0))
    assert np.all(result.executed == 2.0)
    assert result.backlog[-1] == 96.0


def test_mess_missed_commands_are_not_shifted():
    available = np.ones(96, dtype=bool); available[3] = False
    result = execute_mess(np.ones(96), np.ones(96), available, np.ones(96, dtype=bool))
    assert result.p_exec_kw[3] == result.q_exec_kvar[3] == 0
    assert result.missed == ({"slot": 3, "reason": "NOT_PHYSICALLY_AVAILABLE", "executed_later": False, "substitute_vehicle": False},)


def test_runtime_counters_prohibit_reoptimization_and_legacy_scale():
    counters = replay_counters()
    for key in ("actual_reoptimization_calls", "event_trigger_calls", "local_repair_calls", "rolling_mpc_calls", "GPU_h_facility_scale_multiplications", "beta_AIDC_calls"):
        assert counters[key] == 0
    assert counters["PUE_application_count_per_trajectory"] == 1


def test_c1_is_primary_and_pue_applied_once():
    it = np.linspace(300.0, 400.0, 96)
    result = c1_trajectory(it, np.full(96, 15.0), np.full(96, 60.0), namespace="FORECAST_DAYAHEAD_GFS")
    assert result.pue_application_count == 1
    assert result.extra_constant_pue_multiplier_count == 0
    assert result.peak_force_fit_count == 0
    assert np.all(result.pcc_kw >= it)
    assert np.allclose(c0_trajectory(it), 1.30 * it)


def test_c2_not_bound_in_v28_production_modules():
    text = "\n".join(path.read_text(encoding="utf-8") for path in (REPO / "dayahead/v28").glob("*.py") if path.name != "monolithic_authority.py")
    assert "dynamic_state" not in text
    authority = json.loads((ARTIFACTS / "V28_FINAL_THERMAL_PCC_AUTHORITY.json").read_text(encoding="utf-8"))
    assert authority["C2_production_calls"] == 0


def test_b0_b2_reference_schedule_identity_enforced():
    good = {case: {"reference_compute_schedule_sha256": "same"} for case in ("B0", "B1", "B2", "B3")}
    verify_case_contract(good)
    good["B2"]["reference_compute_schedule_sha256"] = "different"
    with pytest.raises(RuntimeError, match="B0_B2"):
        verify_case_contract(good)


def test_solver_equivalence_is_fail_closed():
    good = {name: {"hard_feasible": True, "objective": 1.0} for name in ("MONOLITHIC", "STANDARD_BD", "CL_MC_BD")}
    verify_solver_equivalence(good)
    good["CL_MC_BD"]["objective"] = 1.1
    with pytest.raises(RuntimeError, match="OBJECTIVE_MISMATCH"):
        verify_solver_equivalence(good)


def test_pi_uses_identical_system_and_regret_definition():
    keys = {key: key for key in ("resolution_minutes", "slots_per_day", "aidc_sites", "mess_units", "capacities_sha256", "objective", "constraints_sha256", "feeder_sha256", "thermal_authority_sha256", "opendss_settings_sha256", "solver_tolerance")}
    verify_same_system(keys, dict(keys))
    actual = {"rho_max_AC": 1.0, "objective": 2.0, "peak_PCC_MW": 0.5, "terminal_backlog_GPU_h": 1.0, "MESS_throughput_kWh": 3.0, "thermal_overhead_kWh": 4.0}
    pi = {"rho_max_AC": 0.9, "objective": 1.5, "peak_PCC_MW": 0.4, "terminal_backlog_GPU_h": 0.0, "MESS_throughput_kWh": 4.0, "thermal_overhead_kWh": 3.5}
    assert operational_regret(actual, pi)["R_op_AC"] == pytest.approx(0.1)


def test_monitor_is_read_only_and_reports_fixed_parallelism():
    before = subprocess.check_output(("git", "status", "--porcelain"), cwd=REPO)
    value = snapshot("april", False, False)
    after = subprocess.check_output(("git", "status", "--porcelain"), cwd=REPO)
    assert before == after
    assert value["Day_workers"] == 2 and value["Gurobi_threads"] == 4 and value["read_only"]


def test_bootstrap_is_seeded_and_requires_31_days():
    first = moving_block_bootstrap(range(31), replicates=100)
    second = moving_block_bootstrap(range(31), replicates=100)
    assert first == second and first["seed"] == 20260901 and first["block_days"] == 7
    with pytest.raises(ValueError, match="31"):
        moving_block_bootstrap(range(30), replicates=10)


def test_historical_v17_v27_artifacts_have_no_v28_diff():
    names = subprocess.check_output(
        ("git", "diff", "--name-only", "a9f75e603a74cd3f938aa7eb7dfa537fd4ea0662", "--", "dayahead/artifacts/v17_candidate", "dayahead/artifacts/v22s_r1_final_operating_scale", "dayahead/artifacts/v27m_safe_flex_r1"),
        cwd=REPO, text=True,
    ).splitlines()
    assert names == []


def test_no_full_month_flags_are_prematurely_true():
    flags_path = ARTIFACTS / "V28_IMPLEMENTATION_READY_FLAGS.json"
    if flags_path.is_file():
        flags = json.loads(flags_path.read_text(encoding="utf-8"))
        assert flags["APRIL_FULL_MONTH_PREFLIGHT_PASS"] is False
        assert flags["MAY_FINAL_SCIENCE_COMPLETE"] is False
        assert flags["FINAL_GRID_SCIENCE_AUTHORIZED"] is False


def test_smoke_did_not_create_april_pass_certificate():
    path = REPO / "frozen_artifacts/v28_april_full_month_preflight/2025-04-01/APRIL_DAY_CERTIFICATE_2025_04_01.json"
    assert not path.exists()

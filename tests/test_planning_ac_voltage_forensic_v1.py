import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "dayahead" / "artifacts" / "v16_2"


def _load(name: str) -> dict:
    return json.loads((ARTIFACTS / name).read_text(encoding="utf-8"))


def test_voltage_forensic_is_fail_closed_and_reproducible() -> None:
    payload = _load("PLANNING_AC_VOLTAGE_FORENSIC_V1.json")
    assert payload["checkpoint"]["head"] == "476c19aa708ac9145ddc39b66fe80a40f50fa8e8"
    assert payload["primary_classification"] == "VOLT_CLASS_E_COMBINED_CONTROL_AND_LINEARIZATION_LIMITATION"
    assert payload["beta_candidate_recommended"] is None
    assert payload["production_code_changed"] is False
    assert payload["production_files_changed"] == []
    assert payload["next_decision"] == "READY_FOR_V16_3_PLANNING_MODEL_REFREEZE_REVIEW"
    assert len(payload["source_shas"]) >= 8
    assert len(payload["diagnostic_code_sha256"]) == 64
    for key in (
        "scientific_authority_changes", "beta_production_changes", "AIDC_raw_data_changes",
        "alpha_grid_changes", "native_feeder_rating_changes", "u080_changes",
        "voltage_limit_changes", "kappa_changes", "PUE_changes", "PF_changes",
        "may_scientific_loader_access_count", "june_scientific_loader_access_count",
        "G13_calls", "G14_calls", "C12_calls",
    ):
        assert payload[key] == 0


def test_canonical_same_node_voltage_and_control_ab_evidence() -> None:
    payload = _load("PLANNING_AC_VOLTAGE_FORENSIC_V1.json")
    cases = {row["case_id"]: row for row in payload["canonical_cases"]}
    assert set(cases) == {"CASE_A", "CASE_B", "CASE_C"}
    assert cases["CASE_A"]["operating_day"] == "2025-04-17"
    assert cases["CASE_A"]["slot"] == 66
    assert cases["CASE_A"]["same_node_phase"] == "114.A"
    assert cases["CASE_B"]["beta_AIDC"] == 1e-6
    assert cases["CASE_C"]["operating_day"] == "2025-04-02"
    for row in cases.values():
        mismatch = row["mismatch"]
        assert mismatch["planning_v_squared"] >= 0
        assert abs(mismatch["planning_voltage_pu"] ** 2 - mismatch["planning_v_squared"]) < 1e-12
        assert mismatch["native_capacitor_states"] == mismatch["planning_capacitor_states"]
        assert all(value == 1.0 for value in mismatch["planning_assumed_regulator_taps"].values())
        ab = row["control_state_A_B_at_limiting_slot"]
        for state in ("AC_NATIVE", "AC_PLANNING_CONTROL_STATE"):
            assert ab[state]["vmin_pu"] > 0
            assert ab[state]["vmax_pu"] > 0
            assert ab[state]["line_l10"]["current_max_a"] > 0
            assert ab[state]["reg1a"]["current_max_a"] > 0
    a = cases["CASE_A"]["mismatch"]
    assert a["planning_vs_native_abs_error"] > 0.08
    assert a["planning_vs_frozen_control_abs_error"] < 0.005
    assert payload["control_explained_fraction_case_A"] > 0.95


def test_path_conversion_control_and_linear_replay_evidence() -> None:
    path = _load("VOLTAGE_PATH_DECOMPOSITION_V1.json")
    assert {row["label"] for row in path["paths"]} == {"LIMITING_BUS_114_A", "WORST_AIDC_PCC"}
    limiting = next(row for row in path["paths"] if row["label"] == "LIMITING_BUS_114_A")
    assert limiting["rows"][0]["sending_bus"] == "150"
    assert limiting["rows"][-1]["receiving_bus"] == "114"
    assert any(row["branch_name"] == "transformer.reg1a" for row in limiting["rows"])
    assert any(row["branch_name"] == "transformer.reg4a" for row in limiting["rows"])
    assert len(path["largest_drop_contributors"]) == 5

    controls = _load("REGULATOR_CAPACITOR_CONTROL_AUDIT_V1.json")
    assert controls["conversion_rule_status"] == "PASS"
    assert controls["all_nominal_no_load_identity_errors_within_tolerance"] is True
    assert all(str(value).startswith("PASS") for value in controls["conversion_rule_checks"].values())
    regulator_names = {row["transformer"] for row in controls["regulators"]}
    assert regulator_names == {"reg1a", "reg2a", "reg3a", "reg3c", "reg4a", "reg4b", "reg4c"}
    assert all(not row["dynamic_capcontrol_present"] for row in controls["capacitors"])
    assert all(row["capacitor_state_difference_count"] == 0 for row in controls["case_control_comparisons"])

    forensic = _load("PLANNING_AC_VOLTAGE_FORENSIC_V1.json")
    loss = forensic["loss_and_linearization_diagnostic_case_A"]
    assert loss["after_control_alignment_max_abs_error_pu"] > 0.01
    assert loss["after_control_alignment_mean_abs_error_pu"] > 0.005
    assert loss["limiting_bus_after_control_alignment_error_pu"] > 0.01
    assert loss["fitted_correction_factor_used"] is False


def test_shadow_remains_nonproduction_and_decomposition_safe() -> None:
    shadow = _load("TAP_CONTROL_AWARE_PLANNING_DIAGNOSTIC_V1.json")
    assert shadow["status"] == "SHADOW_ONLY_NOT_PRODUCTION"
    assert shadow["production_activation"] is False
    assert shadow["case_A_false_undervoltage_removed"] is True
    assert shadow["remains_LP"] is True
    assert shadow["preserves_time_local_grid_LP"] is True
    assert shadow["preserves_Pi_Farkas_structure_if_taps_are_exogenous_constants"] is True
    assert shadow["OpenDSS_calls_inside_Benders"] == 0
    assert shadow["D_minus_1_schedule_constructed"] is False
    assert shadow["requires_prospective_V16_3_scientific_refreeze"] is True

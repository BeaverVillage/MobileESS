import json
from pathlib import Path

from dayahead.authority import sha256_file


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "dayahead/artifacts/v16_3_aidc_grid_value_forensic"


def load(name):
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def test_firewall_and_historical_science_are_exact():
    root = load("V16_3_AIDC_GRID_VALUE_ROOT_CAUSE_FORENSIC.json")
    assert root["checkpoint"]["authority_commit"] == "2246063175977f152f3ac8df8f65a861cc7bbd22"
    assert root["checkpoint"]["decomposition_completion_commit"] == "1c46d6510be6be6e00f3305821cbe3bbbd79bdd9"
    assert root["historical_artifacts_modified"] == 0
    assert all(value == 0 for value in root["firewall"].values())
    final = ROOT / "dayahead/artifacts/v16_3_final"
    assert all(sha256_file(final / name) == digest for name, digest in root["historical_artifact_sha256_before"].items())


def test_reference_coherence_and_grid_value_are_not_conflated():
    root = load("V16_3_AIDC_GRID_VALUE_ROOT_CAUSE_FORENSIC.json")
    assert set(root["science_separation"]) == {"REFERENCE_COHERENCE", "GRID_VALUE"}
    assert "13-day" in root["science_separation"]["REFERENCE_COHERENCE"]
    assert "21-day" in root["science_separation"]["GRID_VALUE"]


def test_line_l10_cutset_has_one_upstream_and_eleven_downstream_sites():
    value = load("V16_3_AIDC_TOPOLOGY_CUTSET_AUDIT.json")
    cut = value["line_l10_cut_set"]
    assert cut["AIDC_upstream_of_line_l10"] == ["AIDC01"]
    assert cut["upstream_count"] == 1 and cut["downstream_count"] == 11
    assert len(value["sites"]) == 12
    assert all(site["phase_connectivity"] == ["A", "B", "C"] for site in value["sites"])
    assert value["topology_identity"]["spatial_redistribution_with_conserved_total_active_power_can_change_line_l10_flow"]


def test_frozen_sensitivity_and_magnitude_evidence_is_complete():
    value = load("V16_3_AIDC_SENSITIVITY_DIVERSITY_AUDIT.json")
    assert len(value["common_feasible_days"]) == 21
    assert value["observation_count"] == len(value["observations"])
    assert all(len(row["AIDC_sensitivity_12_pu_per_facility_kw"]) == 12 for row in value["observations"])
    assert all(len(row["pairwise_absolute_difference_matrix"]) == 12 for row in value["observations"])
    assert value["projection_comparison"]["median_abs_Delta_Icrit_from_MESS_pu"] > 1e5 * value["projection_comparison"]["median_abs_Delta_Icrit_from_AIDC_pu"]
    assert "ALIGNMENT_CANCELLATION_NOT_PRIMARY" in value["magnitude_sensitivity_alignment_aggregate"]["primary_mechanism"]
    assert value["trust_region_audit"]["outside_rho_solves"] == 0
    assert not value["trust_region_audit"]["material_at_1e_minus_3_threshold"]


def test_flexible_power_and_kappa_identities_pass_at_full_matrix_shape():
    value = load("V16_3_AIDC_FLEXIBLE_POWER_SCALE_AUDIT.json")
    assert value["status"] == "PASS_NO_IMPLEMENTATION_DEFECT"
    assert len(value["per_day"]) == 21
    for day in value["per_day"]:
        assert all(len(matrix) == 96 and all(len(row) == 12 for row in matrix) for matrix in day["matrices_96x12_kw"].values())
        assert all(len(series) == 96 for series in day["system_ratio_96"].values())
    audit = value["kappa_cohort_audit"]
    assert max(audit["identity_max_abs_errors"].values()) <= 1e-7
    assert not audit["missing_beta"] and not audit["double_beta"] and not audit["code_indexing_defect"]
    assert audit["dt_applied_once"] and audit["kappa_applied_once"]


def test_best_possible_bound_is_optimistic_read_only_and_near_zero():
    value = load("V16_3_AIDC_BEST_POSSIBLE_RELIEF_BOUND.json")
    assert len(value["per_day"]) == 21
    assert all(row["status"] == "OPTIMAL_ANALYTICAL_UPPER_BOUND" for row in value["per_day"])
    assert value["aggregate"]["solver_calls"] == 21 and value["aggregate"]["OpenDSS_calls"] == 0
    assert value["aggregate"]["maximum_best_possible_AIDC_only_relief"] <= 1e-3
    assert all(row["service_parity_max_abs_nodeh"] <= 1e-7 for row in value["per_day"])


def test_v17_outputs_are_design_only_and_outcome_firewalled():
    coherence = load("V17_AIDC_COHERENCE_CORRECTION_DESIGN_CANDIDATE.json")
    diversity = load("V17_AIDC_ELECTRICAL_DIVERSITY_CASE_DESIGN_CANDIDATE.json")
    assert coherence["status"] == "DESIGN_ONLY_NOT_IMPLEMENTED" and not coherence["clipping_main_fix"]
    assert len(coherence["alternatives"]) == 3
    assert diversity["status"] == "DESIGN_ONLY_NOT_EXECUTED" and diversity["selected_sites"] is None
    assert "May/June" in diversity["selection_data_firewall"]["forbidden"]


def test_primary_classification_and_next_decision_are_exact():
    value = load("V16_3_AIDC_GRID_VALUE_ROOT_CAUSE_FORENSIC.json")
    assert value["primary_classification"] == "AIDC_CAUSE_B_FLEXIBLE_POWER_SCALE_LIMITED"
    assert value["next_decision"] == "CURRENT_V16_3_AIDC_RESULT_IS_PHYSICALLY_EXPLAINED"
    assert not value["root_cause_tests"]["implementation_defect"]
    assert value["root_cause_tests"]["flexible_power_scale_limited"]
    assert value["root_cause_tests"]["best_possible_relief_near_zero"]

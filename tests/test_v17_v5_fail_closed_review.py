from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "dayahead/artifacts/v17_candidate"


def _read(name: str):
    return json.loads((ARTIFACTS / name).read_text(encoding="utf-8"))


def test_v5_surrogate_failure_closes_freeze_and_all_downstream_execution() -> None:
    current = _read("V17_V5_7DAY_CURRENT_SURROGATE_VALIDATION.json")
    failure = current["first_gate_failure"]
    assert current["status"] == "FAIL_CLOSED_ON_PREDECLARED_RHO_PROBE"
    assert failure["operating_day"] == "2025-04-02"
    assert failure["slot"] == 23
    assert failure["probe_id"] == "C_01_DISCHARGE"
    assert failure["current_metrics"]["false_current_feasible_count"] == 0
    assert failure["current_metrics"]["max_abs_normalized_current_error_pu"] > current["tolerances"]["max_abs_normalized_current_error_pu"]
    freeze = _read("V17_V5_7DAY_PRE_EVALUATION_FREEZE_MANIFEST.json")
    assert freeze["pre_evaluation_freeze_minted"] is False
    assert freeze["accepted_rho"] is None
    for name in (
        "V17_V5_7DAY_B0_B1_B2_B3_RESULTS.json",
        "V17_V5_7DAY_DUAL_FRESH_AC_RESULTS.json",
        "V17_V5_7DAY_AIDC_GRID_VALUE_FORENSIC.json",
        "V17_V5_7DAY_AIDC_ONLY_UPPER_BOUND.json",
    ):
        payload = _read(name)
        assert payload["status"] == "NOT_EXECUTED_PRE_EVALUATION_FREEZE_NOT_MINTED"
        assert payload["scientific_result_rows"] == 0
        assert payload["solver_calls"] == 0
        assert payload["Fresh_OpenDSS_calls"] == 0


def test_v5_final_classification_and_firewall_are_exact() -> None:
    review = _read("V17_V5_7DAY_FINAL_REVIEW.json")
    assert review["classification"] == "V17_V5_E_SURROGATE_OR_AC_VALIDATION_FAILURE"
    assert review["resume_decision"] == "V17_V5_FURTHER_CORRECTION_REQUIRED"
    assert review["B0_B1_B2_B3"] == "NOT_EXECUTED"
    assert review["dual_Fresh_AC"] == "NOT_EXECUTED"
    for key in (
        "May_scientific_input_reads", "June_scientific_input_reads",
        "May_result_content_reads", "June_result_content_reads",
        "grid_benefit_selected_parameters", "AIDC_site_changes",
        "beta_changes", "kappa_changes", "PUE_changes", "PF_changes",
        "OpenDSS_calls_inside_Benders",
    ):
        assert review[key] == 0

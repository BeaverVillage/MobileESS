from __future__ import annotations

import json
from pathlib import Path


def test_joint_review_passes_with_v1_retained_and_no_future_reads() -> None:
    root = Path(__file__).resolve().parents[1]
    review = json.loads((root / "dayahead/artifacts/v17_candidate/V17_AC_LOOP_AIDC_POWER_V2_COMBINED_REVIEW.json").read_text(encoding="utf-8"))
    assert review["TRACK_A_CLASSIFICATION"] == "V17_AC_LOOP_A_COMMON_CLOSED_LOOP_IMPLEMENTED_PASS"
    assert review["TRACK_B_CLASSIFICATION"] == "V17_AIDC_POWER_V2_C_PARTIAL_NODE_POWER_NOT_IDENTIFIABLE"
    assert review["combined_state"] == "V17_JOINT_B_AC_LOOP_PASS_AIDC_V2_NOT_IDENTIFIABLE"
    assert review["April_resume_decision"] == "READY_FOR_APRIL_RESUME"
    assert review["remaining_April_resumed"] is False
    assert review["Track_A"]["all_28_final_primary_PASS"] is True
    assert review["Track_A"]["all_28_final_secondary_PASS"] is True
    assert review["Track_B"]["V2_authority_minted"] is False
    assert review["Track_B"]["V1_retained"] is True
    assert review["prechange_preservation"] == {
        "all_byte_identical": True,
        "file_count": 209,
        "sha256_mismatch_count": 0,
    }
    assert review["readiness"]["active_H_J_surrogate_correspond_to_active_V1_boundary"] is True
    assert review["git_commits_before_final_review"]["AIDC_Power_V2_implementation_commit"] is None
    for key in (
        "May_scientific_input_reads", "June_scientific_input_reads",
        "May_result_content_reads", "June_result_content_reads",
        "remaining_April_day_runs", "AIDC_site_changes", "beta_changes",
        "PUE_changes", "PF_changes", "effect_selected_parameters",
        "grid_benefit_selected_parameters", "OpenDSS_calls_inside_Benders",
    ):
        assert review[key] == 0

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "dayahead/artifacts/v17_candidate/V17_AIDC_POWER_V3R2_EAGLE_FINAL_REVIEW.json"


def test_v3r2_final_review_is_fail_closed_and_resume_safe() -> None:
    review = json.loads(PATH.read_text(encoding="utf-8"))
    assert review["primary_classification"] == "V17_AIDC_POWER_V3R2_G_MARGINAL_POWER_NOT_IDENTIFIABLE"
    assert review["Eagle_state_evidence"]["co_resident_samples"] == 0
    assert review["V3R2_authority_minted"] is False
    assert review["RCMQT_V3R2"]["performed"] is False
    assert review["same_7day_V3R2"]["performed"] is False
    assert review["active_final_AIDC_power_boundary"] == "V17_AIDC_POWER_MODEL_V1_FROZEN_KAPPA_BOUNDARY"
    assert review["READY_FOR_APRIL_RESUME"] is True
    assert review["prechange_authority_preservation"]["pass"] is True
    assert review["May_scientific_input_reads"] == 0
    assert review["June_scientific_input_reads"] == 0
    assert review["remaining_April_day_runs"] == 0

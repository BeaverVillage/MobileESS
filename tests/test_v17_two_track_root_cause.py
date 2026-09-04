import json
from pathlib import Path


def test_two_track_evidence_is_fail_closed_and_unit_clean() -> None:
    root = Path(__file__).resolve().parents[1]
    output = root / "dayahead/artifacts/v17_candidate"
    forensic = json.loads((output / "V17_AIDC_FLEXIBLE_SCALE_ATTRITION_FORENSIC.json").read_text(encoding="utf-8"))
    power = json.loads((output / "V17_AIDC_POWER_BOUNDARY_IDENTITY_AUDIT.json").read_text(encoding="utf-8"))
    forecast = json.loads((output / "V17_AIDC_FORECAST_SCALE_AUDIT.json").read_text(encoding="utf-8"))
    trace = json.loads((output / "V17_APR12_B2_AC_RESTORATION_CONTROL_FLOW_TRACE.json").read_text(encoding="utf-8"))
    combined = json.loads((output / "V17_AIDC_SCALE_AND_AC_LOOP_COMBINED_REVIEW.json").read_text(encoding="utf-8"))

    assert forensic["classification"] == "V17_AIDC_SCALE_B_POWER_MODEL_COMPATIBILITY_BOUNDARY_DOMINANT"
    assert forensic["separate_fraction_answers"]["approximately_0_2_percent_is_job_count_fraction"] is False
    assert power["status"] == "PASS"
    assert forecast["status"] == "PASS_NO_FORECAST_OR_ADAPTER_ATTENUATION_DEFECT"
    assert trace["classification"] == "V17_AC_RESTORATION_AUTHORITY_AMBIGUOUS"
    assert trace["requested_trace_fields"]["resolve_invoked"] is False
    assert combined["resume_decision"] == "APRIL_RESUME_BLOCKED"
    assert all(value == 0 for value in combined["counters"].values())

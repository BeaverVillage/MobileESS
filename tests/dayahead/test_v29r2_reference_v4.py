from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "dayahead/artifacts/v29r2_anchor_aware_trust_noregret"


def test_reference_v4_contract_is_grid_blind_and_noncontrolling_for_uncertainty() -> None:
    contract = json.loads((OUT / "V29R2_REFERENCE_V4_CONTRACT.json").read_text(encoding="utf-8"))
    assert contract["status"] == "PASS"
    assert contract["controllable_carryin_actuator"] == "H0_LOW only"
    assert contract["grid_loading_reads"] == contract["MESS_state_reads"] == contract["Actual_reads"] == 0
    assert contract["negative_residual_clipping"] is False
    assert contract["PARTIAL_shared_controllable"] is False
    assert contract["running_job_preemption"] is False
    assert contract["synthetic_deadline"] is False
    assert contract["B0_B2_single_serialized_object"] is True
    assert contract["April_fit_rows"] == 0
    assert contract["Apr04_optimizer_result_reads"] == 0
    assert contract["Apr04_Actual_reads"] == 0


def test_reference_v4_sha_residual_and_mass_identities_pass() -> None:
    sha = json.loads((OUT / "V29R2_REFERENCE_V4_SHA_REPORT.json").read_text(encoding="utf-8"))
    residual = json.loads((OUT / "V29R2_REFERENCE_V4_RESIDUAL_AUDIT.json").read_text(encoding="utf-8"))
    assert sha["status"] == residual["status"] == "PASS"
    assert sha["B0_B2_byte_identity_all_days"] is True
    assert residual["minimum_P_RES_kw"] >= 0
    assert residual["minimum_G_RES_gpu"] >= 0
    assert residual["negative_residual_clipping_call_count"] == 0
    assert residual["substantive_negative_residual_count"] == 0
    assert residual["minimum_raw_P_RES_kw"] >= -1e-9
    assert residual["minimum_raw_G_RES_gpu"] >= -1e-9
    assert residual["maximum_P_total_double_count_error_kw"] <= 1e-8
    assert residual["maximum_G_total_double_count_error_gpu"] <= 1e-8
    assert residual["maximum_uncertain_remainder_identity_error"] == 0
    assert residual["uncertain_remainder_counted_as_controllable"] is False
    for row in sha["days"]:
        assert row["B0_reference_V4_sha256"] == row["B2_reference_V4_sha256"]
        assert row["B0_B2_reference_bytes_identical"] is True
        assert abs(row["reference_mass_error_nodeh"]) <= 1e-8

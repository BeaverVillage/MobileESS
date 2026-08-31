from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "dayahead" / "artifacts" / "v17_candidate"


def load(name: str) -> dict:
    return json.loads((ARTIFACTS / name).read_text(encoding="utf-8"))


def file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def test_kestrel_cohorts_reproduce_and_remain_disjoint() -> None:
    cohort = load("V17_AIDC_POWER_V3_COHORT_IDENTIFIABILITY.json")
    assert cohort["reproduction_identity"]["pass"]
    assert cohort["disjoint_set_validation"]["mutually_exclusive"]
    assert cohort["disjoint_set_validation"]["jobs_sum_exact"]
    assert cohort["disjoint_set_validation"]["node_equivalent_hours_sum_abs_error"] <= 1e-9
    by_name = {row["group"]: row for row in cohort["groups"]}
    assert by_name["U1_EXCLUSIVE_PARTIAL_NODE"]["jobs"] == 2416
    assert by_name["U2_SHARED_PARTIAL_OR_SHARED_NODE"]["jobs"] == 67874
    assert by_name["U3_FULL_NODE_BUT_UNSUPPORTED_NODE_COUNT"]["jobs"] == 378


def test_u2_semantics_do_not_invent_mig_time_slice_or_utilization() -> None:
    audit = load("V17_Kestrel_U2_SHARING_SEMANTICS_AUDIT.json")
    observables = audit["observables"]
    assert observables["exact_physical_node_identity_known"]
    assert observables["per_device_GPU_assignment_known"] is False
    assert observables["GPU_utilization_known"] is False
    assert observables["same_GPU_vs_separate_GPU_co_residency_known"] is False
    assert observables["MIG_state_known"] is False
    assert observables["time_slicing_known"] is False
    assert audit["external_semantic_transfer_classification"] == "V17_EXT_SHARE_D_NOT_SEMANTICALLY_IDENTIFIABLE"


def test_no_kestrel_external_row_merge_or_parameter_transfer() -> None:
    names = [
        "V17_Kestrel_U2_SHARING_SEMANTICS_AUDIT.json",
        "V17_AIDC_POWER_V3_COHORT_IDENTIFIABILITY.json",
        "V17_AIDC_POWER_MODEL_V3_EXTERNAL_CONTRACT.json",
        "V17_AIDC_POWER_MODEL_V3_EXTERNAL_VALIDATION.json",
    ]
    for name in names:
        payload = load(name)
        assert payload["rowwise_external_to_Kestrel_merges"] == 0
        assert payload["effect_selected_power_parameters"] == 0
        assert payload["grid_benefit_selected_power_parameters"] == 0
        assert payload["arbitrary_flexible_scaling_calls"] == 0


def test_acceptance_contract_is_prospective_and_blocks_random_row_leakage() -> None:
    contract = load("V17_AIDC_POWER_V3_EXTERNAL_ACCEPTANCE_CONTRACT.json")
    assert contract["created_before_final_held_out_error_reads"]
    assert contract["final_held_out_error_reads"] == 0
    assert "random telemetry-row split prohibited" in contract["split_rule"]
    assert contract["numerical_acceptance_threshold"] is None
    assert contract["status"] == "FAIL_CLOSED_NO_PROSPECTIVE_NUMERICAL_THRESHOLD"


def test_v3_not_minted_and_v1_coverage_unchanged() -> None:
    contract = load("V17_AIDC_POWER_MODEL_V3_EXTERNAL_CONTRACT.json")
    validation = load("V17_AIDC_POWER_MODEL_V3_EXTERNAL_VALIDATION.json")
    coverage = load("V17_AIDC_POWER_V1_V3_COVERAGE_COMPARISON.json")
    assert contract["status"] == "NOT_MINTED"
    assert contract["active_boundary"] == "V17_AIDC_POWER_MODEL_V1_FROZEN_KAPPA_BOUNDARY"
    assert contract["V1_kappa_changes"] == 0
    assert validation["status"] == "NOT_RUN_NOT_AUTHORIZED"
    assert coverage["V1_modelable"] == coverage["V3_modelable"]
    assert coverage["incremental_coverage_fraction"] == {"jobs": 0.0, "node_equivalent_hours": 0.0}


def test_prechange_authority_v1_v2_rcmqt_v5_hj_and_restoration_are_byte_identical() -> None:
    manifest = load("V17_AIDC_POWER_V3_EXTERNAL_PRECHANGE_MANIFEST.json")
    for record in manifest["files"]:
        path = ROOT / record["path"]
        assert path.is_file(), record["path"]
        assert file_sha(path) == record["sha256"], record["path"]
    assert file_sha(ARTIFACTS / "V17_AIDC_POWER_MODEL_V2_CONTRACT.json") == manifest["rejected_V2_contract_sha256"]
    assert file_sha(ARTIFACTS / "V17_AIDC_POWER_MODEL_V2_VALIDATION.json") == manifest["rejected_V2_validation_sha256"]


def test_rcmqt_target_and_dependent_science_rebuilds_were_not_triggered() -> None:
    contract = load("V17_AIDC_POWER_MODEL_V3_EXTERNAL_CONTRACT.json")
    assert contract["status"] == "NOT_MINTED"
    assert not (ARTIFACTS / "V17_RCMQT_V3_TARGET_SEMANTICS_CONTRACT.json").exists()
    assert not (ARTIFACTS / "V17_RCMQT_V3_TRAINING_REPORT.json").exists()
    assert not (ARTIFACTS / "V17_AIDC_POWER_V3_7DAY_PRE_EVALUATION_FREEZE.json").exists()
    assert contract["remaining_April_day_runs"] == 0


def test_may_june_and_opendss_benders_firewalls_hold_everywhere() -> None:
    for path in ARTIFACTS.glob("V17_*H100*.json"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if "May_scientific_input_reads" in payload:
            assert payload["May_scientific_input_reads"] == 0
            assert payload["June_scientific_input_reads"] == 0
            assert payload["May_result_content_reads"] == 0
            assert payload["June_result_content_reads"] == 0
            assert payload["OpenDSS_calls_inside_Benders"] == 0


def test_final_review_is_fail_closed_v1_active_and_hash_complete() -> None:
    review = load("V17_AIDC_POWER_V3_EXTERNAL_FINAL_REVIEW.json")
    assert review["status"] == "V17_AIDC_POWER_V3_EXTERNAL_NOT_AUTHORIZED"
    assert review["primary_classification"] == "V17_AIDC_POWER_V3_E_EXTERNAL_POWER_NOT_IDENTIFIABLE"
    assert review["active_final_AIDC_power_boundary"] == "V17_AIDC_POWER_MODEL_V1_FROZEN_KAPPA_BOUNDARY"
    assert review["READY_FOR_APRIL_RESUME"] is True
    assert review["V3_authority_minted"] is False
    assert review["RCMQT_V3"]["performed"] is False
    assert review["same_7day_V3_science"]["performed"] is False
    for name, record in review["artifact_sha256"].items():
        assert file_sha(ARTIFACTS / name) == record["sha256"]

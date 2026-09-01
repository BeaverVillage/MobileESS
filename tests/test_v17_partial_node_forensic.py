from __future__ import annotations

import json
from pathlib import Path


def test_partial_node_forensic_is_fail_closed_and_partitioned() -> None:
    root = Path(__file__).resolve().parents[1]
    artifacts = root / "dayahead/artifacts/v17_candidate"
    source = json.loads((artifacts / "V17_AIDC_PARTIAL_NODE_SOURCE_AUDIT.json").read_text(encoding="utf-8"))
    decomposition = json.loads((artifacts / "V17_AIDC_UNMODELED_COHORT_DECOMPOSITION.json").read_text(encoding="utf-8"))
    identity = json.loads((artifacts / "V17_AIDC_PARTIAL_NODE_POWER_IDENTIFIABILITY.json").read_text(encoding="utf-8"))
    validation = json.loads((artifacts / "V17_AIDC_POWER_MODEL_V2_VALIDATION.json").read_text(encoding="utf-8"))
    contract = json.loads((artifacts / "V17_AIDC_POWER_MODEL_V2_CONTRACT.json").read_text(encoding="utf-8"))
    boundary = json.loads((artifacts / "V17_AIDC_POWER_V1_V2_BOUNDARY_COMPARISON.json").read_text(encoding="utf-8"))
    classification = "V17_AIDC_POWER_V2_C_PARTIAL_NODE_POWER_NOT_IDENTIFIABLE"
    assert source["source"]["sha256"] == "dcad6de800fb565d850b163902e2eddae48aabd1ed1c7336f9a1cdaf3012f137"
    assert source["available_fields"]["per_GPU_NVML_power"]["available"] is True
    assert source["available_fields"]["CPU_RAPL_package_power"]["available"] is True
    assert source["available_fields"]["number_of_powered_or_active_GPUs"]["available"] is False
    assert source["available_fields"]["per_device_GPU_utilization"]["available"] is False
    assert source["available_fields"]["direct_partial_node_or_partial_GPU_ground_truth"]["available"] is False
    assert source["utilization_firewall"]["not_GPU_allocation_occupancy"] is True
    assert decomposition["partition_checks"]["jobs_sum_exact"] is True
    assert decomposition["partition_checks"]["node_equivalent_hours_sum_abs_error"] <= 1e-6
    assert {row["group"] for row in decomposition["groups"]} == {
        "U1_EXCLUSIVE_PARTIAL_NODE", "U2_SHARED_PARTIAL_OR_SHARED_NODE",
        "U3_FULL_NODE_BUT_UNSUPPORTED_NODE_COUNT", "U4_OTHER_POWER_UNMODELED",
    }
    assert identity["classification"] == classification
    assert identity["scientific_boundary_expansion_authorized"] is False
    assert validation["status"] == "REJECTED_NOT_AUTHORIZED"
    assert contract["status"] == "REJECTED_NOT_AUTHORIZED" and contract["authority_minted"] is False
    assert boundary["active_boundary"] == "V1"
    assert boundary["V2_incremental_recovered_node_equivalent_hours"] == 0.0
    for payload in (source, decomposition, identity, validation, contract, boundary):
        assert payload["Dataset312_Kestrel_row_merge_count"] == 0
        assert payload["May_scientific_input_reads"] == 0
        assert payload["June_scientific_input_reads"] == 0
        assert payload["remaining_April_day_runs"] == 0

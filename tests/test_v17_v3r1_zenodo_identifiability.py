from __future__ import annotations

import json
from pathlib import Path

from dayahead.v17_v3r1_zenodo import zero_counters


ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "dayahead" / "artifacts" / "v17_candidate"


def load(name: str) -> dict:
    return json.loads((ARTIFACTS / name).read_text(encoding="utf-8"))


def test_raw_inventory_and_measurement_boundaries() -> None:
    inventory = load("V17_EUROSYS_ZENODO_RAW_DATA_INVENTORY.json")
    provenance = load("V17_EUROSYS_ZENODO_MEASUREMENT_PROVENANCE.json")
    assert inventory["telemetry_file_count"] == 62
    assert inventory["H100_telemetry_file_count"] == 24
    assert inventory["benchmark_result_file_count"] == 125
    assert provenance["power_boundaries"]["GPU_device_board_power"] is True
    assert provenance["power_boundaries"]["node_aggregate_power"] is False
    assert provenance["power_boundaries"]["CPU_package_power"] is False


def test_hardware_transfer_is_parameter_shape_only_and_v1_preserved() -> None:
    transfer = load("V17_V3R1_H100_HARDWARE_TRANSFER_MATRIX.json")
    contract = load("V17_AIDC_POWER_MODEL_V3R1_CONTRACT.json")
    assert transfer["direct_absolute_external_kW_transfer_authorized"] is False
    assert transfer["Dataset312_kappa_changes"] == 0
    assert contract["status"] == "NOT_MINTED"
    assert contract["V1_kappa_changes"] == 0


def test_u2_reproduction_and_semantic_firewall() -> None:
    reproduction = load("V17_V3R1_Kestrel_U2_REPRODUCTION.json")
    bridge = load("V17_V3R1_EXTERNAL_TO_KESTREL_SEMANTIC_BRIDGE.json")
    assert reproduction["U2"]["jobs"] == 67874
    assert abs(reproduction["U2"]["node_equivalent_hours"] - 122237.74291666666) < 1e-9
    assert bridge["U2_classification"] == "SEMANTICALLY_INCOMPATIBLE"
    assert "per-device GPU placement" in bridge["U2_unknown"]
    assert bridge["rowwise_external_to_Kestrel_merges"] == 0


def test_utilization_allocation_and_sharing_not_conflated() -> None:
    bridge = load("V17_V3R1_EXTERNAL_TO_KESTREL_SEMANTIC_BRIDGE.json")
    text = json.dumps(bridge)
    assert "MIG state" in text
    assert bridge["marginal_power_of_schedulable_work"]["identifiable"] is False
    assert bridge["job_attributed_power"]["source_backed"] is False


def test_experiment_split_prevents_row_leakage() -> None:
    split = load("V17_V3R1_EXTERNAL_SPLIT_CONTRACT.json")
    acceptance = load("V17_AIDC_POWER_V3R1_ACCEPTANCE_CONTRACT.json")
    assert split["random_row_split_allowed"] is False
    assert split["temporal_samples_from_same_run_may_cross_splits"] is False
    assert split["fit_calls"] == 0
    assert acceptance["created_before_fit"] is True
    assert acceptance["numerical_acceptance_threshold"] is None


def test_u2_ex_post_reconstruction_is_not_activated() -> None:
    coverage = load("V17_V3R1_U2_AGGREGATE_STATE_COVERAGE.json")
    ident = load("V17_AIDC_POWER_V3R1_COHORT_IDENTIFIABILITY.json")
    assert coverage["per_device_GPU_placement_reconstructed"] is False
    assert coverage["D1_future_physical_node_assignment_available"] is False
    assert coverage["active_point_model_support_node_hours"] == 0.0
    assert ident["classifications"]["U2"] == "SEMANTICALLY_INCOMPATIBLE"


def test_no_forbidden_reads_runs_or_effect_selection() -> None:
    expected = zero_counters()
    names = [
        "V17_EUROSYS_ZENODO_RAW_DATA_INVENTORY.json",
        "V17_EUROSYS_ZENODO_MEASUREMENT_PROVENANCE.json",
        "V17_V3R1_H100_HARDWARE_TRANSFER_MATRIX.json",
        "V17_V3R1_Kestrel_U2_REPRODUCTION.json",
        "V17_V3R1_EXTERNAL_TO_KESTREL_SEMANTIC_BRIDGE.json",
        "V17_V3R1_U2_AGGREGATE_STATE_COVERAGE.json",
        "V17_AIDC_POWER_V3R1_COHORT_IDENTIFIABILITY.json",
        "V17_AIDC_POWER_MODEL_V3R1_CONTRACT.json",
        "V17_AIDC_POWER_MODEL_V3R1_VALIDATION.json",
    ]
    for name in names:
        payload = load(name)
        for key, value in expected.items():
            assert payload[key] == value

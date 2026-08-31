from __future__ import annotations

import json
from pathlib import Path

import pytest

from dayahead.v17_v3r2_eagle_forensic import (
    EAGLE_NODES,
    assert_block_split,
    assert_common_features,
    assert_disjoint_sets,
    assert_eagle_only_join,
    assert_no_eagle_absolute_kw_to_h100,
    assert_node_energy_not_job_power,
    zero_counters,
)


ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "dayahead" / "artifacts" / "v17_candidate"


def load(name: str) -> dict:
    return json.loads((ARTIFACTS / name).read_text(encoding="utf-8"))


def test_cross_machine_row_merge_and_absolute_power_transfer_are_forbidden() -> None:
    with pytest.raises(RuntimeError, match="ROWWISE_EAGLE_KESTREL_MERGE_FORBIDDEN"):
        assert_eagle_only_join("EAGLE", "KESTREL")
    assert_eagle_only_join("EAGLE_JOBS", "EAGLE_TELEMETRY")
    with pytest.raises(RuntimeError, match="ABSOLUTE_KW_TO_H100_FORBIDDEN"):
        assert_no_eagle_absolute_kw_to_h100(source_hardware="V100_PCIE", target_hardware="H100_SXM", absolute=True)


def test_feature_and_split_firewalls() -> None:
    assert_common_features(["concurrent_job_count", "sum_requested_gpus", "sum_requested_cpus"])
    with pytest.raises(RuntimeError, match="NONCAUSAL_OR_LABEL_FEATURE"):
        assert_common_features(["future_node_id"])
    assert_block_split(["nodeA:2024-01-01"], ["nodeA:2024-01-02"])
    with pytest.raises(RuntimeError, match="HELDOUT_BLOCK_LEAKAGE"):
        assert_block_split(["block1"], ["block1"])


def test_node_energy_and_disjoint_cohort_firewalls() -> None:
    with pytest.raises(RuntimeError, match="SHARED_NODE_ENERGY_AS_JOB_POWER_FORBIDDEN"):
        assert_node_energy_not_job_power(source_semantics="NODE_AGGREGATE_ENERGY", requested_interpretation="INDIVIDUAL_JOB_POWER")
    assert_disjoint_sets({"a"}, {"b"}, {"c"})
    with pytest.raises(RuntimeError, match="COHORT_OVERLAP"):
        assert_disjoint_sets({"a"}, {"a"})


def test_discovery_and_time_contract_are_source_backed() -> None:
    discovery = load("V17_EAGLE_DATASET_DISCOVERY.json")
    hardware = load("V17_EAGLE_HARDWARE_MEASUREMENT_AUTHORITY.json")
    timing = load("V17_EAGLE_TEMPORAL_ALIGNMENT_CONTRACT.json")
    assert discovery["status"] == "PASS_ALL_THREE_OFFICIAL_EAGLE_SOURCES_IDENTIFIED"
    assert discovery["raw_roots_access_mode"] == "READ_ONLY"
    assert tuple(hardware["hardware"]["node_ids"]) == EAGLE_NODES
    assert hardware["compatibility_to_dataset312"] == "DIMENSIONLESS_RESPONSE_TRANSFER_ONLY"
    assert timing["alignment_rule"]["timezone"] == "UTC"
    assert timing["alignment_rule"]["heldout_offset_selection"] is False


def test_all_v3r2_discovery_counters_are_zero() -> None:
    for name in [
        "V17_EAGLE_DATASET_DISCOVERY.json",
        "V17_EAGLE_SOURCE_AUTHORITY_MANIFEST.json",
        "V17_EAGLE_HARDWARE_MEASUREMENT_AUTHORITY.json",
        "V17_EAGLE_JOB_ENERGY_SCHEMA_AUDIT.json",
        "V17_EAGLE_GPU_NODE_TELEMETRY_SCHEMA_AUDIT.json",
        "V17_EAGLE_TEMPORAL_ALIGNMENT_CONTRACT.json",
    ]:
        payload = load(name)
        for key, value in zero_counters().items():
            assert payload[key] == value


def test_kestrel_native_energy_is_not_reinterpreted_as_u2_power() -> None:
    audit = load("V17_KESTREL_NATIVE_ENERGY_FIELD_AUDIT.json")
    reproduction = load("V17_V3R2_KESTREL_U2_REPRODUCTION.json")
    identity = load("V17_V3R2_KESTREL_U2_ENERGY_IDENTIFIABILITY.json")
    assert reproduction["U2"]["jobs"] == 67_874
    assert abs(reproduction["U2"]["node_equivalent_hours"] - 122_237.74291666666) < 1e-9
    assert audit["U2_statistics"]["energy_positive"] == 0
    assert audit["U2_statistics"]["energy_null"] == 67_871
    assert audit["U2_statistics"]["energy_zero"] == 3
    assert audit["direct_job_power_authorized"] is False
    assert identity["classification"] == "KESTREL_NODE_ENERGY_NOT_IDENTIFIABLE"
    assert identity["P_job_equals_energy_over_runtime_authorized"] is False


def test_kestrel_u2_interval_manifest_is_ex_post_only() -> None:
    manifest = load("V17_V3R2_KESTREL_U2_NODE_INTERVALS_MANIFEST.json")
    assert manifest["fully_reconstructable_ex_post_jobs"] == 62_498
    assert manifest["future_physical_node_assignment_available_D1"] is False
    assert "GPU device assignment" in manifest["forbidden_inferences"]

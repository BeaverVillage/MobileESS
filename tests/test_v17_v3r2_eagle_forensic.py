from __future__ import annotations

import json
import hashlib
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


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
    assert discovery["sources"]["ganglia"]["sha256"] == "f8e14651bf3cad97e83fe22a704734bffdc1307afa935430da2b37833db34e1f"
    assert discovery["sources"]["ilo"]["sha256"] == "ee73ff938dd1ede6c3e1064e0fb042bcdb35f7e1a9bc582e2fa420fe7e50cda3"
    assert discovery["sources"]["jobs_energy"]["sha256"] == "966ca575cc50b3273719b39781e32728ae066ece4af699fb5d73d9db4362ecce"


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


def test_eagle_shared_state_is_absent_and_not_forced() -> None:
    states = load("V17_EAGLE_SHARED_NODE_STATE_DATASET.json")
    validation = load("V17_EAGLE_SHARED_MARGINAL_POWER_VALIDATION.json")
    assert states["EAGLE_U2_ANALOG_samples"] == 0
    assert states["counts"]["max_exact_concurrent_jobs"] == 1
    assert validation["EAGLE_SHARED_MARGINAL_CLASSIFICATION"] == "EAGLE_SHARED_MARGINAL_D_NOT_IDENTIFIABLE"
    assert validation["candidate_point_model_authorized"] is False
    assert validation["same_total_gpu_changed_concurrent_job_count_transition_count"] == 0


def test_eagle_split_is_blocked_not_random_row() -> None:
    split = load("V17_EAGLE_SHARED_POWER_SPLIT_CONTRACT.json")
    assert split["split_unit"] == "physical-node UTC calendar day"
    assert split["random_telemetry_row_split"] is False
    assert split["adjacent_day_embargo"] is True
    assert split["final_metrics_read_before_contract"] is False


def test_v100_absolute_transfer_and_v3r2_activation_are_rejected() -> None:
    transfer = load("V17_V3R2_V100_TO_H100_RESPONSE_TRANSFER_AUDIT.json")
    contract = load("V17_AIDC_POWER_MODEL_V3R2_CONTRACT.json")
    validation = load("V17_AIDC_POWER_MODEL_V3R2_VALIDATION.json")
    assert transfer["Eagle_absolute_kW_to_H100_authorized"] is False
    assert transfer["candidate_dimensionless_response_identified"] is False
    assert contract["minted"] is False
    assert contract["V1_kappa_modified"] is False
    assert validation["primary_classification"] == "V17_AIDC_POWER_V3R2_G_MARGINAL_POWER_NOT_IDENTIFIABLE"


def test_d1_future_state_and_incremental_coverage_fail_closed() -> None:
    d1 = load("V17_AIDC_POWER_V3R2_D1_CAUSALITY_AUDIT.json")
    cohort = load("V17_AIDC_POWER_V3R2_COHORT_IDENTIFIABILITY.json")
    coverage = load("V17_AIDC_POWER_V1_V3R2_COVERAGE_COMPARISON.json")
    decision = load("V17_AIDC_POWER_V3R2_ACTIVATION_DECISION.json")
    assert d1["future_physical_node_ID_available"] is False
    assert d1["SHARED_OCCUPANCY_CLASS_defined"] is False
    assert cohort["U2A"]["jobs"] == 0
    assert cohort["U2A_U2B_U2C_disjoint"] is True
    assert coverage["incremental_coverage"] == 0.0
    assert decision["ACTIVE_BOUNDARY"] == "V17_AIDC_POWER_MODEL_V1_FROZEN_KAPPA_BOUNDARY"
    assert decision["READY_FOR_APRIL_RESUME"] is True
    assert decision["same_7day_regression_performed"] is False


def test_u1_u2_u3_and_u2_subcohort_set_identities() -> None:
    reproduction = load("V17_V3R2_KESTREL_U2_REPRODUCTION.json")
    cohort = load("V17_AIDC_POWER_V3R2_COHORT_IDENTIFIABILITY.json")
    unmodeled_jobs = sum(reproduction[name]["jobs"] for name in ["U1", "U2", "U3", "U4"])
    assert unmodeled_jobs == reproduction["semantic_flexible"]["jobs"] - reproduction["V1_modelable"]["jobs"]
    assert cohort["U2A"]["jobs"] + cohort["U2B"]["jobs"] + cohort["U2C"]["jobs"] == reproduction["U2"]["jobs"]
    nodeh = cohort["U2A"]["node_equivalent_hours"] + cohort["U2B"]["node_equivalent_hours"] + cohort["U2C"]["node_equivalent_hours"]
    assert abs(nodeh - reproduction["U2"]["node_equivalent_hours"]) < 1e-9


def test_active_v1_hj_ac_and_rejected_extensions_remain_byte_identical() -> None:
    expected = {
        ROOT / "dayahead/aidc_power_response.py": "517806b68de0554658cddd230e797190995f331062c17e6f2c32f4929b3579e3",
        ARTIFACTS / "ac_cache_v5/data/D1_AC_ANCHOR_CURRENT_SENSITIVITY_2025-04-02.npz": "ab1bd172795f195ec4022abfb8fc67fcc0cafeb838672dc29ef05e579bdcd83f",
        ARTIFACTS / "V17_AC_RESTORATION_OUTER_LOOP_CONTRACT_V1.json": "97ef76db29f40ff47f734bd8b3d95db83057574c352117104d3b75bdef7ca3c5",
        ARTIFACTS / "V17_AIDC_POWER_MODEL_V2_CONTRACT.json": "882dfbdf24abade96bd2aacd1dae66dfd7a25e89885d9d62a902bc273dad937b",
        ARTIFACTS / "V17_AIDC_POWER_MODEL_V2_VALIDATION.json": "36b93cbeb224223a98dfcf7c2d47c5b8c3fa0f8b358f205082595451d76ccb68",
        ARTIFACTS / "V17_AIDC_POWER_MODEL_V3_EXTERNAL_CONTRACT.json": "2436416fb24b5c2e21c18e9f84e9ede09776714a6097074c133ac659bcd594f7",
        ARTIFACTS / "V17_AIDC_POWER_MODEL_V3_EXTERNAL_VALIDATION.json": "2cf97a7085b2d2488a025c1db40374b883e5a7f0b0c45613334b52dec6e23277",
        ARTIFACTS / "V17_AIDC_POWER_V3R1_ZENODO_FINAL_REVIEW.json": "9aad900b62b4ff9f2e000a8eb7784027bcbd03e181b898196c341593debaf4df",
    }
    for path, digest in expected.items():
        assert sha256(path) == digest


def test_all_v3r2_artifacts_preserve_april_may_june_firewall() -> None:
    for path in ARTIFACTS.glob("V17_*V3R2*.json"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        for key, expected in zero_counters().items():
            if key in payload:
                assert payload[key] == expected, (path.name, key)

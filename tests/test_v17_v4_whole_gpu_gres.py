from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from dayahead.v17_v4_whole_gpu_gres import _nvml_rows


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "dayahead/artifacts/v17_candidate"


def load(name: str) -> dict:
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def test_frozen_prechange_records_remain_byte_identical() -> None:
    manifest = load("V17_AIDC_POWER_V4_WHOLE_GPU_GRES_PRECHANGE_MANIFEST.json")
    assert manifest["head"] == "1515076b4d4a88c1da2cae24c9dcac7e577d5b02"
    assert manifest["record_count"] >= 250
    for row in manifest["records"]:
        path = ROOT / row["path"]
        assert path.is_file(), row["path"]
        assert path.stat().st_size == row["bytes"], row["path"]
        assert sha256(path) == row["sha256"], row["path"]


def test_u2_fail_closed_on_exact_node_time_capacity_gate() -> None:
    audit = load("V17_KESTREL_WHOLE_GPU_GRES_SEMANTICS_AUDIT.json")
    assert audit["U2"]["jobs"] == 67_874
    assert audit["U2"]["gpus_requested_distribution"] == {"1": 64_333, "2": 3_531, "3": 6, "4": 4}
    assert audit["gates"]["u2_gpus_requested_integer_1_to_4"] is True
    assert audit["gates"]["u2_uniform_integer_multi_node_distribution_identifiable"] is True
    assert audit["gates"]["no_MPS_MIG_shard_evidence_in_available_fields"] is True
    assert audit["gates"]["node_time_concurrent_GPU_sum_le_4"] is False
    sweep = audit["node_time_capacity_sweep"]
    assert sweep["maximum_concurrent_allocated_GPUs"] == 5
    assert sweep["violation_count"] == 1
    violation = sweep["violations"][0]
    assert violation["node"] == "x3107c0s17b0n0"
    assert violation["active_job_ids"] == ["7539787", "7543918", "7545385"]
    assert audit["U2_reclassification"] == "U2_WHOLE_GPU_GRES_RECLASSIFICATION_NOT_AUTHORIZED"


def test_dataset312_board_only_quantiles_and_boundary() -> None:
    board = load("V17_DATASET312_PER_GPU_BOARD_POWER_AUTHORITY.json")
    assert board["NVML_log_count"] == 299
    assert board["per_GPU_trace_count"] == 1_196
    assert board["complete_run_count"] == 46
    assert board["idle_subtraction_W_per_GPU"] == 72.5
    assert board["kappa_GPU_Q10_kW"] == pytest.approx(0.3941881609951147, abs=1e-15)
    assert board["kappa_GPU_Q50_kW"] == pytest.approx(0.48563611660901085, abs=1e-15)
    assert board["kappa_GPU_Q90_kW"] == pytest.approx(0.5391969931144363, abs=1e-15)
    assert board["CPU_host_incremental_power_role"] == "REMAINS_IN_P_IT_REF_RESIDUAL_NOT_FLEXIBLE_DELTA"
    assert board["arbitrary_scaling"] is False


def test_scientific_data_is_cross_validation_only() -> None:
    cross = load("V17_SCIENTIFIC_DATA_H100_PER_GPU_CROSS_VALIDATION.json")
    assert cross["status"] == "PASS_PHYSICAL_CROSS_VALIDATION_ONLY"
    assert all(cross["gates"].values())
    assert cross["Dataset312_parameter_changes_from_cross_validation"] == 0
    assert "not coefficient fitting" in cross["role"]


def test_gpu_hour_coverage_is_reproduced_not_target_fitted() -> None:
    coverage = load("V17_AIDC_POWER_V1_V4_GPU_HOUR_COVERAGE_COMPARISON.json")
    assert coverage["semantic_flexible"]["GPU_hours"] == pytest.approx(610_761.1522222199)
    assert coverage["V1"]["GPU_hours"] == pytest.approx(73_532.97555555624)
    assert coverage["new_U2"]["GPU_hours"] == pytest.approx(488_950.9716666713)
    assert coverage["V1_plus_U2_V4"]["coverage_fraction"] == pytest.approx(0.9209556717477224)
    assert coverage["candidate_V1_plus_U2_support_reaches_90_percent"] is True
    assert coverage["active_V1_support_reaches_90_percent"] is False
    assert coverage["expected_92_0956_percent_checked_not_hardcoded"] is True
    assert coverage["coefficient_tuning_to_reach_90_percent"] == 0


def test_v4_not_minted_and_no_downstream_execution() -> None:
    contract = load("V17_AIDC_POWER_MODEL_V4_WHOLE_GPU_GRES_CONTRACT.json")
    assert contract["status"] == "FAIL_CLOSED_NOT_AUTHORIZED"
    assert contract["active_final_AIDC_power_boundary"] == "V17_AIDC_POWER_MODEL_V1_FROZEN_KAPPA_BOUNDARY"
    assert contract["RC_MQT_V4_retraining_authorized"] is False
    assert contract["same_7_day_science_run_authorized"] is False
    assert len(contract["RC_MQT_target_axes"]) == 20
    assert contract["April_scientific_input_reads_before_freeze"] == 0
    assert contract["May_scientific_input_reads"] == 0
    assert contract["June_scientific_input_reads"] == 0
    assert contract["remaining_April_day_runs"] == 0


def test_nvml_parser_keeps_utilization_separate_from_board_power() -> None:
    sample = """# timestamp reading-time[ns] gpu-0[mW] gpu-1[mW] gpu-0[C] gpu-1[C]\n2025-01-01_00:00:00 12 100000 200000 40 41\n"""
    assert _nvml_rows(sample) == {0: [100.0], 1: [200.0]}

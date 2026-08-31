from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from dayahead.v17_reference_scheduler_v6 import GPU_COUNTS, build_reference_schedule_v6_gpu_hour
from dayahead.v17_deferrability_semantics import LATENCY_CLASSES


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "dayahead/artifacts/v17_candidate"


def load(name: str) -> dict:
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def test_conflict_source_rows_are_preserved_not_repaired() -> None:
    audit = load("V17_AIDC_POWER_V4R1_CONFLICT_SOURCE_AUDIT.json")
    assert audit["status"] == "PASS_NO_SOURCE_BACKED_RECORD_CORRECTION"
    assert set(audit["rows"]) == {"7539787", "7543918", "7545385"}
    assert all(value == 1 for value in audit["duplicate_job_records"].values())
    assert audit["rows"]["7545385"]["frozen_latency_class"] == "FIXED"
    assert audit["rows"]["7545385"]["frozen_U2_member"] is False
    assert audit["timestamp_correction_calls"] == 0
    assert audit["GPU_clipping_calls"] == 0


def test_global_hyperedge_quarantine_cleans_capacity_sweep() -> None:
    sweep = load("V17_AIDC_POWER_V4R1_GLOBAL_CAPACITY_SWEEP.json")
    assert sweep["original"]["maximum_concurrent_allocated_GPUs"] == 5
    assert sweep["original"]["violation_interval_count"] == 1
    assert sweep["original"]["conflict_job_union_Q"] == ["7539787", "7543918", "7545385"]
    assert sweep["cleaned_after_removing_entire_Q"]["maximum_concurrent_allocated_GPUs"] == 4
    assert sweep["cleaned_after_removing_entire_Q"]["violation_interval_count"] == 0


def test_quarantine_and_coverage_are_source_reproduced() -> None:
    quarantine = load("V17_AIDC_POWER_V4R1_QUARANTINE_MANIFEST.json")
    coverage = load("V17_AIDC_POWER_V1_V4R1_COVERAGE_COMPARISON.json")
    assert quarantine["Q_jobs"] == 3
    assert quarantine["Q_GPU_hours"] == pytest.approx(6.800833333333334)
    assert quarantine["Q_node_equivalent_hours"] == pytest.approx(1.7002083333333335)
    assert quarantine["U2_QUARANTINED_intersection_Q"] == ["7539787", "7543918"]
    assert quarantine["Q_members_outside_frozen_U2"] == ["7545385"]
    assert quarantine["U2_CLEAN_jobs"] == 67_872
    assert coverage["V1_plus_V4R1_U2_CLEAN"]["coverage_fraction"] == pytest.approx(0.9209445408280355)
    assert coverage["coverage_used_as_acceptance_gate"] is False


def test_v4r1_contract_freezes_board_only_power_before_april() -> None:
    contract = load("V17_AIDC_POWER_MODEL_V4R1_CONTRACT.json")
    assert contract["authority_id"] == "V17_AIDC_POWER_MODEL_V4R1_WHOLE_GPU_CLEAN_GRES"
    assert contract["status"] == "PASS_PROSPECTIVE_AUTHORITY_FROZEN_BEFORE_APRIL"
    assert contract["sensitivity_coefficients_kW_per_GPU"] == {
        "Q10": 0.3941881609951147, "Q50": 0.48563611660901085, "Q90": 0.5391969931144363,
    }
    assert contract["primary_coefficient"] == "Q50"
    assert contract["CPU_host_incremental_power"] == "retained in P_IT_REF residual"
    assert contract["April_scientific_input_reads_before_freeze"] == 0


def test_reference_v6_service_parity_capacity_and_permutation_invariance() -> None:
    arrivals = {(latency, gpu): [0.0] * 96 for latency in LATENCY_CLASSES for gpu in GPU_COUNTS}
    arrivals[("C1", 1)][0] = 1.0
    arrivals[("C2", 4)][1] = 2.0
    capacities = {"R03": 0.75, "R01": 0.25, "R02": 0.50}
    first = build_reference_schedule_v6_gpu_hour(arrivals, capacities)
    second = build_reference_schedule_v6_gpu_hour(arrivals, dict(reversed(list(capacities.items()))))
    assert first.service_by_class_gpu_rack_slot == second.service_by_class_gpu_rack_slot
    assert first.evidence["service_parity_max_abs_error_GPU_hour"] <= 1e-12
    assert first.evidence["terminal_backlog_GPU_hour"] == 0.0
    for slot in range(96):
        for rack, capacity in capacities.items():
            used = sum(first.service_by_class_gpu_rack_slot[(latency, gpu, rack, slot)] for latency in LATENCY_CLASSES for gpu in GPU_COUNTS)
            assert used <= capacity + 1e-12

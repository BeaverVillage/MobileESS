from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from dayahead.v28r2.authority import AUTHORITY_PRECEDENCE, COHORT_IDS, WorkloadEligibilityBinding


def eligible_row() -> dict:
    return {
        "partition": "gpu-h100",
        "state_simple": "COMPLETED",
        "start_time": datetime(2025, 1, 1, tzinfo=timezone.utc),
        "end_time": datetime(2025, 1, 1, 1, tzinfo=timezone.utc),
        "gpu_nodes_occupied": 4,
        "gpus_requested": 16,
        "shared_job_count": None,
        "nodes_shared": None,
        "jobs_shared": [],
    }


def test_latest_refreeze_precedes_v21() -> None:
    assert AUTHORITY_PRECEDENCE[0] == "2026-08-29_FINAL_SCIENTIFIC_REFREEZE"
    assert AUTHORITY_PRECEDENCE[-1] == "V21_AND_EARLIER_HISTORICAL_EVIDENCE_ONLY"


def test_fullnode_only_historical_eligibility() -> None:
    binding = WorkloadEligibilityBinding()
    binding.validate()
    assert binding.historical_label_eligible(eligible_row())
    partial = {**eligible_row(), "gpus_requested": 15}
    shared = {**eligible_row(), "shared_job_count": 1}
    unsupported = {**eligible_row(), "gpu_nodes_occupied": 3, "gpus_requested": 12}
    assert not binding.historical_label_eligible(partial)
    assert not binding.historical_label_eligible(shared)
    assert not binding.historical_label_eligible(unsupported)
    assert not binding.partial_controllable
    assert binding.partial_reference_embedded


def test_d1_record_is_forecast_cohort_only() -> None:
    binding = WorkloadEligibilityBinding()
    binding.validate_d1_record(
        {
            "cohort_id": COHORT_IDS[0],
            "target_slot": 0,
            "forecast_q50_nodeh": 1.0,
            "forecast_issue_cutoff": "2025-03-31T18:00:00+10:00",
            "forecast_vintage_id": "test",
            "node_class": 1,
            "runtime_class": 0,
        }
    )
    with pytest.raises(ValueError, match="D1_EXPOST"):
        binding.validate_d1_record(
            {"cohort_id": COHORT_IDS[0], "target_slot": 0, "forecast_q50_nodeh": 1.0, "start_time": "future"}
        )


def test_frozen_artifacts_record_partial_as_reference_only() -> None:
    repo = Path(__file__).resolve().parents[2]
    import json

    value = json.loads((repo / "dayahead/artifacts/v28r2_heavy_backend/V28R2_WORKLOAD_ELIGIBILITY_BINDING.json").read_text(encoding="utf-8"))
    assert value["WORKLOAD_ELIGIBILITY_READY"]
    assert not value["partial_controllable"]
    assert value["partial_reference_embedded"]
    assert not value["PARTIAL_CPU_package_increment_invented"]

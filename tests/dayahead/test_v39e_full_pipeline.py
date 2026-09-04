from __future__ import annotations

from dayahead.v38.authority import CapacityAuthority, RackPool
from dayahead.v39a.spatial import ActivityJob
from dayahead.v39e.contracts import (
    GUROBI_THREADS_PER_MODEL,
    MAX_PARALLEL_DAY_WORKERS,
)
from dayahead.v39e.full_spatial import (
    deterministic_rack_labels,
    plan_fixed_temporal_schedule,
)


def toy_authority() -> CapacityAuthority:
    return CapacityAuthority(
        site_capacity={"AIDC01": 64},
        historical_site_capacity={"AIDC01": 64.0},
        rack_pools=(RackPool("AIDC01", "AIDC01_LP01", 32.0),),
        source_sha256="toy",
    )


def test_runtime_only_parallelism_contract() -> None:
    assert MAX_PARALLEL_DAY_WORKERS == 4
    assert GUROBI_THREADS_PER_MODEL == 4
    assert MAX_PARALLEL_DAY_WORKERS * GUROBI_THREADS_PER_MODEL == 16


def test_rack_compatibility_is_non_additive_under_site_capacity() -> None:
    jobs = (
        ActivityJob("job-a", "PENDING", 32, 0, 96),
        ActivityJob("job-b", "PENDING", 32, 0, 96),
    )
    result = plan_fixed_temporal_schedule(
        jobs, toy_authority(), {}, name="V39E_TEST_NON_ADDITIVE",
        allow_running_migration=False,
    )
    assert result["status"] == "OPTIMAL"
    assert result["rack_capacity_summed_as_site_capacity"] is False
    assert result["capacity_created_by_rack_layer_GPU"] == 0
    assert {row["logical_Rack_compatibility_label"] for row in result["assignments"]} == {
        "AIDC01_LP01"
    }


def test_actual_rack_labels_do_not_create_or_move_capacity() -> None:
    assignments = [
        {
            "job_uid": f"job-{index}",
            "destination_AIDC": "AIDC01",
            "requested_GPU": 32,
            "active_start_slot": 0,
            "active_end_slot": 96,
        }
        for index in range(2)
    ]
    result = deterministic_rack_labels(assignments, toy_authority())
    assert result["status"] == "PASS"
    assert result["failure_count"] == 0
    assert result["rack_capacity_summed_as_site_capacity"] is False
    assert result["capacity_created_by_rack_layer_GPU"] == 0
    assert result["DA_selected_AIDC_mutation_count"] == 0
    assert result["DA_selected_time_mutation_count"] == 0

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from dayahead.v38.authority import CapacityAuthority, RackPool
from dayahead.v39a.spatial import ActivityJob
from dayahead.v39c import freeze as freeze_module
from dayahead.v39e.contracts import (
    GUROBI_THREADS_PER_MODEL,
    MAX_PARALLEL_DAY_WORKERS,
)
from dayahead.v39e.full_spatial import (
    deterministic_rack_labels,
    plan_fixed_temporal_schedule,
)
from dayahead.tools.run_v39e_may_day import _install_windows_safe_k_archive


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


def test_v39_atomic_json_retries_windows_reader_lock(tmp_path: Path) -> None:
    path = tmp_path / "progress.json"
    real_replace = freeze_module.os.replace
    attempts = 0

    def locked_then_available(source: object, target: object) -> None:
        nonlocal attempts
        attempts += 1
        if attempts <= 25:
            raise PermissionError("synthetic reader lock")
        real_replace(source, target)

    with (
        patch.object(freeze_module.os, "replace", side_effect=locked_then_available),
        patch.object(freeze_module.time, "sleep", return_value=None),
    ):
        freeze_module.atomic_json(path, {"status": "RUNNING"})

    assert attempts == 26
    assert path.read_text(encoding="utf-8").endswith("\n")
    assert not list(tmp_path.glob("*.tmp"))


def test_v39e_k_archive_uses_short_windows_safe_names(tmp_path: Path) -> None:
    import dayahead.v37.runner as runner

    originals = (
        runner._archive_local_attempt,
        runner._archived_k_attempt,
        getattr(runner, "_v39e_windows_safe_k_archive", False),
    )
    search_root = tmp_path / ("x" * 120)
    search_root.mkdir()
    (search_root / "RESTRICTED_VALUES.csv").write_text(
        "candidate_id,exact_optimality_certificate\n"
        "candidate-1,V37_FAIL_CLOSED:synthetic\n",
        encoding="utf-8",
    )
    (search_root / "SEEDS.json").write_text("[]\n", encoding="utf-8")
    (search_root / "LOCAL_SEARCH.json").write_text("{}\n", encoding="utf-8")
    try:
        if hasattr(runner, "_v39e_windows_safe_k_archive"):
            delattr(runner, "_v39e_windows_safe_k_archive")
        _install_windows_safe_k_archive()
        runner._archive_local_attempt(search_root, "200")
        assert (search_root / "RV.K200.A1.csv").is_file()
        assert (search_root / "S.K200.A1.json").is_file()
        assert (search_root / "LS.K200.A1.json").is_file()
        restored = runner._archived_k_attempt(search_root, "200")
        assert restored is not None
        assert restored["status"] == "CERTIFICATION_FAILURE_RESTORED"
        assert restored["uncertified_candidate_count"] == 1
    finally:
        runner._archive_local_attempt = originals[0]
        runner._archived_k_attempt = originals[1]
        runner._v39e_windows_safe_k_archive = originals[2]


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

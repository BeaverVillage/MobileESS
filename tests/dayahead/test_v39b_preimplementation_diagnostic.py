from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

from dayahead.v38.authority import load_capacity_authority
from dayahead.v39a.spatial import ActivityJob
from dayahead.v39b.contracts import (
    ARTIFACT_ROOT,
    CAPACITY_AUTHORITY_SHA256,
    DIAGNOSTIC_LABEL,
    INFEASIBLE_DAY_MODES,
    SITE_CAPACITY,
    SOURCE_HEAD,
    TARGET_OFFSET_SLOTS,
)
from dayahead.v39b.diagnostic import _solve_relief, exact_slot_packing, sha256_file


REPO = Path(__file__).resolve().parents[2]
ARTIFACT = REPO / ARTIFACT_ROOT


def j(name: str) -> dict:
    return json.loads((ARTIFACT / name).read_text(encoding="utf-8"))


def test_start_authority_and_capacity_are_exact() -> None:
    capacity = load_capacity_authority(REPO)
    assert capacity.source_sha256 == CAPACITY_AUTHORITY_SHA256
    assert dict(capacity.site_capacity) == SITE_CAPACITY
    assert sum(capacity.site_capacity.values()) == 624
    audit = j("V39B_CONFLICT_JOB_CENSUS_AUDIT.json")
    assert audit["source_HEAD"] == SOURCE_HEAD
    assert audit["infeasible_day_modes"] == len(INFEASIBLE_DAY_MODES) == 14


def test_d1_classification_uses_only_visible_running_and_pending_jobs() -> None:
    audit = j("V39B_D1_CAUSAL_CONFLICT_AUDIT.json")
    counts = audit["classification_counts_unique_day_mode_job"]
    assert counts["ALREADY_RUNNING_AT_CUTOFF"] > 0
    assert counts["PENDING_KNOWN_AT_CUTOFF"] > 0
    assert counts.get("NOT_YET_KNOWN_AT_CUTOFF", 0) == 0
    assert counts.get("UNKNOWN_AUTHORITY_INSUFFICIENT", 0) == 0
    assert audit["causal_visibility_NO"] == 0


def test_no_future_or_actual_information_was_read() -> None:
    audit = j("V39B_D1_CAUSAL_CONFLICT_AUDIT.json")
    for field in (
        "future_runtime_reads", "future_execution_reads", "May_result_reads",
        "Fresh_reads", "Actual_grid_reads", "Actual_traffic_reads",
    ):
        assert audit[field] == 0
    assert audit["future_read_count"] == 0


def test_slot_coordinate_mapping_is_authority_backed() -> None:
    audit = j("V39B_SLOT_COORDINATE_AUDIT.json")
    assert audit["status"] == "PASS"
    assert audit["stored_schedule_coordinate"]["slots"] == 120
    assert audit["production_day_coordinate"]["slots"] == 96
    assert audit["target_offset_slots"] == TARGET_OFFSET_SLOTS == 24
    assert audit["timezone"] == "AEST_FIXED_UTC_PLUS_10"


def test_exact_site_packing_rejects_15_indivisible_32_gpu_gangs() -> None:
    jobs = tuple(ActivityJob(f"j{i}", "PENDING", 32, 0, 1) for i in range(15))
    result = exact_slot_packing(
        jobs, load_capacity_authority(REPO), name="V39B_TEST_15X32"
    )
    assert result["status"] == "INFEASIBLE_SLOT_LOCAL"


def test_exact_site_packing_preserves_gang_indivisibility() -> None:
    capacity = load_capacity_authority(REPO)
    impossible = tuple(
        ActivityJob(f"j60-{index}", "PENDING", 60, 0, 1) for index in range(7)
    )
    result = exact_slot_packing(impossible, capacity, name="V39B_TEST_3X60")
    assert result["status"] == "INFEASIBLE_SLOT_LOCAL"
    assert sum(capacity.site_capacity.values()) > 420
    assert sum(capacity.site_capacity[site] // 60 for site in capacity.aidc_ids) == 6


def test_all_exact_conflict_slots_and_large_gang_certificate_are_recorded() -> None:
    audit = j("V39B_SLOT_LOCAL_PACKING_AUDIT.json")
    assert audit["INFEASIBLE_SLOT_LOCAL"] == 1042
    assert audit["FEASIBLE"] == 14 * 96 - 1042
    certificate = audit["first_large_gang_minimal_conflict_subset"]
    assert certificate["subset_jobs"] == 15
    assert certificate["subset_GPU"] == 480
    assert len(certificate["job_uids"]) == 15


def test_nonshiftable_only_floor_is_feasible_in_every_conflict_slot() -> None:
    audit = j("V39B_NONSHIFTABLE_FLOOR_AUDIT.json")
    assert audit["classification"] == "CASE_B_NONSHIFTABLE_JOBS_SPATIALLY_FEASIBLE"
    assert audit["slots_tested"] == 1042
    assert audit["nonshiftable_floor_feasible_slots"] == 1042
    assert audit["nonshiftable_floor_infeasible_slots"] == 0


def test_required_relief_is_an_exact_slot_removal_lower_bound() -> None:
    capacity = load_capacity_authority(REPO)
    jobs = tuple(ActivityJob(f"j{i}", "PENDING", 32, 0, 1) for i in range(15))
    result = _solve_relief(
        jobs, capacity, lambda _job: True,
        primary="jobs", name="V39B_TEST_RELIEF_15X32",
    )
    assert result["status"] == "OPTIMAL"
    assert result["removed_jobs"] == 1
    assert result["removed_GPU"] == 32
    audit = j("V39B_REQUIRED_TEMPORAL_RELIEF.json")
    assert audit["minimum_jobs_over_all_conflict_slots"] == 1
    assert audit["minimum_GPU_over_all_conflict_slots"] == 32


def test_shiftable_relief_is_only_an_isolated_slot_screen() -> None:
    audit = j("V39B_AVAILABLE_FLEXIBLE_RELIEF.json")
    assert audit["authorized_shiftable_relief_can_repair_each_slot_in_isolation"] is True
    assert audit["alternate_window_feasibility_known"] is False
    assert all(
        row["alternate_start_windows"] == "UNKNOWN_NOT_AUTHORIZED"
        for row in audit["slot_results"]
    )


def test_missing_deadline_or_window_is_not_invented() -> None:
    audit = j("V39B_FLEXIBILITY_AUTHORITY_AUDIT.json")
    contract = audit["recovered_contract"]
    assert audit["status"] == "FAIL_CLOSED_MISSING_BOUNDED_WINDOW_AUTHORITY"
    assert contract["latest_legal_start"] == "UNKNOWN"
    assert contract["deadline"] == "UNKNOWN"
    assert contract["maximum_shift"] == "UNKNOWN"
    assert contract["search_guard_is_scientific_deadline"] is False


def test_temporal_recourse_is_diagnostic_only_and_not_built_without_authority() -> None:
    audit = j("V39B_DIAGNOSTIC_TEMPORAL_RECOURSE.json")
    assert audit["model_label"] == DIAGNOSTIC_LABEL
    assert audit["solver_model_built"] is False
    assert audit["TEMPORAL_RECOURSE_BEST_CASE_FEASIBLE"] == "UNKNOWN"
    assert audit["jobs_shifted_in_minimum_witness"] is None
    assert audit["production_schedule_written"] is False


def test_rw_rsp_semantics_do_not_redefine_the_reference_baseline() -> None:
    audit = j("V39B_RW_RSP_BASELINE_SEMANTICS_AUDIT.json")
    assert audit["RW_raw_execution_replay"] is False
    assert audit["same_physical_constraints"] is True
    assert audit["REFERENCE_BASELINE_REDEFINITION_REQUIRED"] == "NO"
    assert "tier/FIFO first-fit" in audit["RSP_authoritative_meaning"]


def test_production_inputs_are_byte_unchanged_and_no_schedule_is_created() -> None:
    audit = j("V39B_CONFLICT_JOB_CENSUS_AUDIT.json")
    for relative, expected in audit["input_hashes"].items():
        assert sha256_file(REPO / relative) == expected
    output_names = {path.name for path in ARTIFACT.iterdir()}
    assert not any("SCHEDULE.parquet" in name for name in output_names)
    assert all("WITNESS" not in name for name in output_names)
    assert audit["production_mutation_count"] == 0


def test_parquet_metadata_and_no_may_launch() -> None:
    census = pd.read_parquet(ARTIFACT / "V39B_CONFLICT_JOB_CENSUS.parquet")
    roots = pd.read_parquet(ARTIFACT / "V39B_CONFLICT_ROOT_CAUSE_TABLE.parquet")
    for frame in (census, roots):
        assert set(frame["diagnostic_label"]) == {DIAGNOSTIC_LABEL}
        assert set(frame["source_HEAD"]) == {SOURCE_HEAD}
        assert set(frame["production_mutation_count"]) == {0}
        assert set(frame["future_read_count"]) == {0}
    report = j("V39B_DIAGNOSTIC_TEST_REPORT.json")
    assert report["MAY_STARTED"] == "NO"
    assert not (ARTIFACT / "V39B_FULL_CAUSAL_FEASIBILITY_DIAGNOSTIC.json").exists()


def test_root_cause_table_is_complete_and_fail_closed() -> None:
    roots = pd.read_parquet(ARTIFACT / "V39B_CONFLICT_ROOT_CAUSE_TABLE.parquet")
    assert len(roots) == 1042
    assert set(roots["root_cause"]) == {
        "FLEXIBLE_PENDING_OVERLAP", "MIXED_GANG_FRAGMENTATION",
    }
    assert set(roots["authority_blocker"]) == {"UNKNOWN_AUTHORITY_BLOCKER"}
    assert set(roots["best_case_temporal_feasible"]) == {
        "UNKNOWN_NOT_RUN_MISSING_WINDOW_AUTHORITY"
    }


def test_artifact_bytes_are_hashable_and_final_gate_stays_closed() -> None:
    review = (ARTIFACT / "V39B_PREIMPLEMENTATION_FINAL_REVIEW.md").read_text(
        encoding="utf-8"
    )
    assert "V39B_IMPLEMENTATION_READY = NO" in review
    assert review.rstrip().endswith("MAY_STARTED = NO")
    assert hashlib.sha256(review.encode()).hexdigest()

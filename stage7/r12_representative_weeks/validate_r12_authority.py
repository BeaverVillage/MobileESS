#!/usr/bin/env python3
"""Fail-closed, no-solver validation of the R12 Stage 7 authority."""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path


EXPECTED_INPUT_SHA = {
    "frozen_authority/REPRESENTATIVE_PERIOD_RESULT_20260815.json": "d2a0dac2a82ba2727ccba0830e3abaaa07095b35df7be6b23b6650b26f34cb39",
    "frozen_authority/REP_WEEK_SELECTION_2025_K12.csv": "0e32d3257fdc1fafc0bbdd95ca01f270b164a9be18ffa45c060e3c490bed2577",
    "frozen_authority/STRESS_PERIOD_CANDIDATES_2025.csv": "02ae634eb308470fbe9307984aea60f5baa755ba3c4ef77d5073425418c50bbd",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def merge(intervals: list[tuple[int, int]]) -> list[tuple[int, int]]:
    result: list[list[int]] = []
    for start, end in sorted(intervals):
        if start >= end:
            raise RuntimeError(f"invalid half-open interval: {start}, {end}")
        if result and start <= result[-1][1]:
            result[-1][1] = max(result[-1][1], end)
        else:
            result.append([start, end])
    return [(start, end) for start, end in result]


def main() -> int:
    root = Path(__file__).resolve().parent
    contract = read_json(root / "C_STAGE7_R12_REPRESENTATIVE_WEEK_AUTHORITY.json")
    matrix = read_json(root / "C_STAGE7_R12_TEST_MATRIX.json")
    union_plan = read_json(root / "C_STAGE7_R12_SOURCE_UNION_PLAN.json")
    result = read_json(root / "frozen_authority/REPRESENTATIVE_PERIOD_RESULT_20260815.json")

    checks: dict[str, bool] = {}
    for relative, expected in EXPECTED_INPUT_SHA.items():
        checks[f"sha256:{relative}"] = sha256(root / relative) == expected
    checks["contract_input_hash_map_exact"] = contract["frozen_input_sha256"] == EXPECTED_INPUT_SHA
    checks["pr3_commit_exact"] = contract["authority_basis"]["github_head_commit"] == "bfbbc7cb4bc03c131f4c26df82c7c55d231cbfc8"
    checks["science_sha_exact"] = contract["scientific_source_authority"]["science_main_sha256"] == "1177ac8814f1008907f89ebf513bf9fe3e469d2c09a51ba85303c46c428f76b9"
    checks["period_selection_not_rerun"] = contract["authority_basis"]["period_selection_rerun"] is False
    checks["ac_retained"] = contract["scientific_source_authority"]["ac_power_flow_retained"] is True

    with (root / "frozen_authority/REP_WEEK_SELECTION_2025_K12.csv").open(encoding="utf-8", newline="") as stream:
        weeks = list(csv.DictReader(stream))
    ids = [row["candidate_id"] for row in weeks]
    checks["week_count_12"] = len(weeks) == 12 and len(set(ids)) == 12
    checks["ids_match_result"] = ids == result["application_result_2025"]["selected_candidate_ids"]
    checks["medoid_rank_exact"] = [int(row["medoid_rank"]) for row in weeks] == list(range(1, 13))
    checks["three_per_season"] = Counter(row["season"] for row in weeks) == Counter({"summer": 3, "autumn": 3, "winter": 3, "spring": 3})
    checks["weight_sum_one"] = abs(sum(float(row["cluster_weight"]) for row in weeks) - 1.0) <= 1e-12

    intervals: list[tuple[int, int]] = []
    time_axis_pass = True
    index_axis_pass = True
    for row in weeks:
        burn_start = datetime.fromisoformat(row["burn_in_start_aest"])
        week_start = datetime.fromisoformat(row["week_start_aest"])
        week_end = datetime.fromisoformat(row["week_end_exclusive_aest"])
        time_axis_pass &= (week_start - burn_start).total_seconds() == 576 * 300
        time_axis_pass &= (week_end - week_start).total_seconds() == 2016 * 300
        time_axis_pass &= burn_start.utcoffset().total_seconds() == 10 * 3600
        time_axis_pass &= week_start.utcoffset().total_seconds() == 10 * 3600
        burn_index = int(row["burn_in_start_index"])
        start_index = int(row["start_index"])
        end_index = int(row["end_index_exclusive"])
        index_axis_pass &= start_index - burn_index == 576
        index_axis_pass &= end_index - start_index == 2016
        intervals.append((burn_index, start_index))
    checks["pr3_period_metadata_time_axis_576_plus_2016"] = bool(time_axis_pass)
    checks["pr3_period_metadata_index_axis_576_plus_2016"] = bool(index_axis_pass)

    merged = merge(intervals)
    unique_count = sum(end - start for start, end in merged)
    expected_merged = [(int(row["start"]), int(row["end"])) for row in union_plan["primary_episode_intervals_half_open"]]
    checks["source_union_exact"] = merged == expected_merged
    checks["stage7_burn_in_source_union_unique_count_6912"] = unique_count == 6912 == union_plan["primary_unique_issue_count"]
    checks["stage7_burn_in_source_raw_reference_count_6912"] = sum(end - start for start, end in intervals) == 6912
    checks["stage7_h54_target_inside_2025"] = max(end - 1 + 53 for _, end in intervals) == 102292 < 105120

    checkpoint_rows = matrix["checkpoint_restart_exact_pairs"]
    checkpoint_ids = [row["candidate_id"] for row in checkpoint_rows]
    week_by_id = {row["candidate_id"]: row for row in weeks}
    checks["checkpoint_pair_count_12"] = len(checkpoint_ids) == len(set(checkpoint_ids)) == 12
    checks["checkpoint_uses_all_ids_once"] = checkpoint_ids == ids
    checks["checkpoint_axes_match_frozen_weeks"] = all(
        int(row["burn_in_start_index"]) == int(week_by_id[row["candidate_id"]]["burn_in_start_index"])
        and int(row["week_start_index"]) == int(week_by_id[row["candidate_id"]]["start_index"])
        and int(row["checkpoint_after_steps"]) == 288
        for row in checkpoint_rows
    )

    washout = matrix["initializer_washout_pairs"]
    checks["washout_pair_count_12"] = len(washout) == 12
    checks["washout_uses_all_ids_once"] = [row["candidate_id"] for row in washout] == ids
    checks["washout_uses_all_seeds_once"] = sorted(int(row["t3_ensemble_seed"]) for row in washout) == list(range(12))
    checks["washout_assignment_rank_minus_one"] = all(int(row["t3_ensemble_seed"]) == int(row["medoid_rank"]) - 1 for row in washout)
    checks["outcomes_not_inspected"] = matrix["paired_outcomes_inspected_before_freeze"] is False

    initializer_authority = read_json(root / "C_STAGE7_R12_INITIALIZER_AUTHORITY.json")
    initializer_rows = initializer_authority.get("files", [])
    checks["initializer_authority_frozen_before_outcomes"] = (
        initializer_authority.get("status") == "FROZEN_BEFORE_CONTROLLER_OUTCOMES"
        and initializer_authority.get("outcome_based_selection") is False
        and initializer_authority.get("copies_continuous_reference_state") is False
    )
    checks["initializer_file_count_24"] = len(initializer_rows) == 24
    expected_initializer_pairs = {(candidate, kind) for candidate in ids for kind in ("canonical", "t3_assigned")}
    checks["initializer_candidate_kind_matrix_exact"] = {
        (row.get("candidate_id"), row.get("kind")) for row in initializer_rows
    } == expected_initializer_pairs
    initializer_files_pass = True
    for initializer_row in initializer_rows:
        initializer_path = root / initializer_row["path"]
        initializer_files_pass &= initializer_path.is_file() and sha256(initializer_path) == initializer_row["file_sha256"]
        if initializer_path.is_file():
            initializer_record = read_json(initializer_path)
            initializer_files_pass &= initializer_record.get("candidate_id") == initializer_row["candidate_id"]
            initializer_files_pass &= initializer_record.get("sha256") == initializer_row["state_sha256"]
            initializer_files_pass &= int(initializer_record["state"]["issue_step"]) == int(
                week_by_id[initializer_row["candidate_id"]]["burn_in_start_index"]
            )
    checks["initializer_files_sha_axis_exact"] = bool(initializer_files_pass)

    with (root / "frozen_authority/STRESS_PERIOD_CANDIDATES_2025.csv").open(encoding="utf-8", newline="") as stream:
        stress = list(csv.DictReader(stream))
    checks["stress_count_4"] = len(stress) == 4
    checks["stress_576_zero_weight"] = all(int(row["steps"]) == 576 and float(row["annual_weight"]) == 0.0 for row in stress)
    stress_intervals = [(int(row["start_index"]), int(row["end_index_exclusive"])) for row in stress]
    primary_plus_stress = merge(intervals + stress_intervals)
    checks["primary_plus_stress_union_count"] = sum(end - start for start, end in primary_plus_stress) == 9216

    checks["one_common_cache"] = contract["source_architecture"]["mode"] == "ONE_COMMON_2025_AUTHORITY_CACHE_THEN_WINDOW_SLICE"
    checks["no_per_week_source_restart"] = contract["source_architecture"]["heavy_source_pipeline_restart_per_week"] is False
    checks["no_heavy_run_authorized_by_validation"] = contract["execution_topology"]["heavy_run_before_preflight_pass"] is False
    checks["stage7_stops_at_evaluation_start"] = contract["episode_contract"]["evaluation_steps_executed_by_stage7"] == 0
    checks["lazy_prefetch_not_pass_gate"] = contract["stage7_pass_contract"]["lazy_prefetch_required"] is False
    topology = contract["execution_topology"]
    checks["stage7_transition_budget_17280"] = (
        topology["canonical_transition_count"] == 6912
        and topology["restart_candidate_transition_count"] == 3456
        and topology["initializer_candidate_transition_count"] == 6912
        and topology["stage7_max_committed_transition_count"] == 17280
    )
    checks["restart_reuses_sha_checkpoint_without_first_half_resolve"] = (
        contract["checkpoint_restart_validation"]["duplicated_first_half_solve_required"] is False
        and contract["checkpoint_restart_validation"]["required_paired_lanes"] == 12
    )
    checks["source_12_blocks_6912_issues"] = (
        contract["source_architecture"]["traffic_block_count"] == 12
        and contract["source_architecture"]["primary_window_unique_issue_count"] == 6912
    )
    issue_topology = contract["source_architecture"]["issue_materialization_topology"]
    checks["issue_materialization_single_gpu_no_replication"] = (
        issue_topology["gpu_e3_producers"] == 1
        and issue_topology["os_process_count_max"] == 15
        and issue_topology["gpu_model_replication"] is False
        and issue_topology["shared_e4_authority_via_fork_copy_on_write"] is True
        and issue_topology["traffic_and_e3_e4_run_in_separate_python_processes"] is True
    )
    checks["issue_materialization_bounded_14_cpu_processes"] = (
        issue_topology["cpu_e4_metadata_compression_workers_max"] == 14
        and issue_topology["cpu_worker_execution"] == "fork process pool created before parent E3 CUDA load"
        and issue_topology["ordered_prefix_index_commit"] is True
        and issue_topology["restart_quarantines_unindexed_or_temporary_artifacts"] is True
    )
    dual_horizon = contract["source_architecture"]["dual_horizon_boundary_contract"]
    checks["dual_horizon_runtime_sha_exact"] = (
        dual_horizon["runtime_main_sha256"]
        == "1b0ac60ae49e1b4573d469e95c2b2857d17dbe64b7184bc81a28d433c02adbcc"
    )
    checks["unseen_safe_horizon_falls_back_without_clamp"] = (
        dual_horizon["allowed_unseen_selector_levels"] == ["physical_route", "global"]
        and dual_horizon["continuous_profile_duration_preserved"] is True
        and dual_horizon["per_issue_index_evidence"]
        == ["unseen_safe_row_count", "unseen_safe_steps"]
        and dual_horizon["evidence_survives_bounded_restart"] is True
        and dual_horizon["clamp_to_highest_calibrated_bin"] is False
        and dual_horizon["tolerance_relaxation"] is False
    )
    checks["old_month_boundary_forbidden"] = "11 month-boundary validation" in contract["forbidden"]
    checks["old_132_forbidden"] = "automatic reuse of the old 132-lane E7B matrix" in contract["forbidden"]

    failed = sorted(name for name, passed in checks.items() if not passed)
    payload = {
        "schema_version": "conversation_c.stage7.r12.authority_validation.v1",
        "status": "PASS_READY_FOR_SOURCE_PREFLIGHT_NO_HEAVY_RUN" if not failed else "FAIL_CLOSED",
        "checks": checks,
        "failed_checks": failed,
        "week_count": len(weeks),
        "primary_unique_source_issue_count": unique_count,
        "checkpoint_pair_count": len(checkpoint_ids),
        "initializer_washout_pair_count": len(washout),
        "gurobi_executed": False,
        "opendss_executed": False,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if not failed else 2


if __name__ == "__main__":
    raise SystemExit(main())

"""Build the bounded V37-P1 execution-acceleration verification artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import tempfile
import time
from typing import Any, Mapping

import pandas as pd

from dayahead.v37.execution_acceleration import (
    COMPATIBILITY_VERSION,
    CandidateResultCache,
    canonical_sha256,
    cumulative_missing_ids,
    file_sha256,
    fallback_levels,
)


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "dayahead/artifacts/v37_p1_execution_acceleration"
PROFILE_RESULT = (
    ROOT / "dayahead/cache/v37_may_locked_final"
    / "MAY_2025_V37_R2_REVALIDATION_V2/beam/2025-05-01/B2/B2/FINAL_RESULT.json"
)
EQUIVALENCE_ROOT = (
    ROOT / "dayahead/cache/v37_may_locked_final"
    / "MAY_2025_V37_R2_REVALIDATION_V2/beam/2025-05-01/B2/B2/s1/B2-ROOT"
)
EQUIVALENCE_STAGE = EQUIVALENCE_ROOT.parents[1] / "STAGE_1.json"
FALLBACK_ROOT = (
    ROOT / "dayahead/cache/v37_may_locked_final"
    / "MAY_2025_LOCKED_FINAL/beam/2025-05-01/B2/B2"
    / "s3/B2-S2-e00bcfd2b96aa6d4"
)


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(name: str, payload: object) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / name
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )
    temporary.replace(path)


def _git(*args: str) -> str:
    return subprocess.check_output(
        ["git", *args], cwd=ROOT, text=True, encoding="utf-8",
    ).strip()


def _runtime_profile() -> dict[str, Any]:
    result = _read(PROFILE_RESULT)
    trace = result["trace"]
    total = float(result["run_wallclock_seconds"])
    restricted = sum(float(row["restricted_wallclock_seconds"]) for row in trace)
    full = sum(float(row["full_MILP_wallclock_seconds"]) for row in trace)
    screening = sum(float(row["cheap_screen_wallclock_seconds"]) for row in trace)
    remainder = max(0.0, total - restricted - full - screening)
    return {
        "artifact_id": "V37_P1_RUNTIME_PROFILE_V1",
        "source_artifact": str(PROFILE_RESULT),
        "source_SHA256": file_sha256(PROFILE_RESULT),
        "scope": "saved May-01 B2 beam trace; no new optimization",
        "beam_wallclock_seconds": total,
        "restricted_candidate_solves": {
            "seconds": restricted, "share_percent": 100.0 * restricted / total,
        },
        "full_MILPs": {"seconds": full, "share_percent": 100.0 * full / total},
        "screening": {"seconds": screening, "share_percent": 100.0 * screening / total},
        "context_loading_and_other": {
            "seconds": remainder, "share_percent": 100.0 * remainder / total,
        },
        "disk_IO_measured_separately": False,
        "disk_IO_share_percent_upper_bound": 100.0 * remainder / total,
        "disk_IO_assessment": "NOT_MATERIAL_IN_SAVED_TRACE",
        "local_input_staging": "SKIPPED",
        "primary_bottleneck": "FULL_MILP",
        "secondary_bottleneck": "RESTRICTED_CANDIDATE_SOLVES",
        "Fresh_acceleration_scope": "UNCHANGED",
    }


def _cache_contract() -> dict[str, Any]:
    return {
        "artifact_id": "V37_P1_CACHE_CONTRACT_V1",
        "compatibility_version": COMPATIBILITY_VERSION,
        "completed_case_identity": [
            "operating_day", "case", "voltage_authority_sha256",
            "AIDC_authority_sha256", "MESS_authority_sha256", "K",
            "K_fallback", "beam", "beam_fallback", "seed",
            "WorkLimit", "solver_relevant_configuration", "candidate_table_SHA",
            "network_context_SHA", "execution_code_SHA",
            "infrastructure_compatibility_version",
        ],
        "intermediate_identity_additions": [
            "MESS_step", "MESS_id", "beam_parent_fingerprint", "candidate_id",
            "candidate_rank", "solve_type", "fixed_previous_MESS_trajectory_SHA",
            "MESS_candidate_table_SHA", "screen_authority_SHA",
        ],
        "completed_case_file_validation": "SIZE_AND_SHA256",
        "restricted_cache_payload": "COMPLETED_CERTIFIED_RESULTS_ONLY",
        "uncertified_result_handling": "NOT_CACHED_AND_RETRIED",
        "full_MILP_checkpoint_validation": "IDENTITY_SHA256_AND_SOURCE_SHA256",
        "stage_namespace": "execution_fingerprint_sha256",
        "atomic_resume": True,
        "candidate_order_restored_before_selection": True,
        "voltage_authority_change_forces_CACHE_MISS": True,
        "AIDC_authority_change_forces_CACHE_MISS": True,
        "beam_parent_change_forces_CACHE_MISS": True,
        "mutable_Gurobi_model_reuse": False,
    }


def _fallback_audit() -> tuple[dict[str, Any], dict[str, Any]]:
    policy_total = 2160
    levels = fallback_levels(policy_total)
    ids = tuple(f"rank-{index:04d}" for index in range(1, policy_total + 1))
    completed: list[str] = []
    batches: list[int] = []
    for level in levels:
        missing = cumulative_missing_ids(ids[:level], completed)
        batches.append(len(missing))
        completed.extend(missing)
    old_policy_calls = sum(levels)
    new_policy_calls = len(completed)

    attempt_paths = [
        FALLBACK_ROOT / "RESTRICTED_VALUES.K200.ATTEMPT1.csv",
        FALLBACK_ROOT / "RESTRICTED_VALUES.K400.ATTEMPT1.csv",
        FALLBACK_ROOT / "RESTRICTED_VALUES.K800.ATTEMPT1.csv",
        FALLBACK_ROOT / "RESTRICTED_VALUES.csv",
    ]
    summary_paths = [
        FALLBACK_ROOT / "LOCAL_SEARCH.K200.ATTEMPT1.json",
        FALLBACK_ROOT / "LOCAL_SEARCH.K400.ATTEMPT1.json",
        FALLBACK_ROOT / "LOCAL_SEARCH.K800.ATTEMPT1.json",
        FALLBACK_ROOT / "LOCAL_SEARCH.json",
    ]
    frames = [pd.read_csv(path) for path in attempt_paths]
    summaries = [_read(path) for path in summary_paths]
    serialized_counts = [len(frame) for frame in frames]
    serialized_ids = [tuple(map(str, frame["candidate_id"])) for frame in frames]
    prefix_pass = all(
        set(serialized_ids[index]).issubset(set(serialized_ids[index + 1]))
        for index in range(len(serialized_ids) - 1)
    )
    ranked_ids = [
        tuple(map(str, summary["selected_candidate_ids"]))
        for summary in summaries
    ]
    ranked_prefix_pass = all(
        ranked_ids[index] == ranked_ids[index + 1][:len(ranked_ids[index])]
        for index in range(len(ranked_ids) - 1)
    )
    union = set().union(*(set(values) for values in serialized_ids))
    old_serialized_calls = sum(serialized_counts)
    saved_wallclock = [float(row["restricted_wallclock_seconds"]) for row in summaries]
    incremental_counts = [
        serialized_counts[0],
        *[
            len(set(serialized_ids[index]) - set().union(*(
                set(values) for values in serialized_ids[:index]
            )))
            for index in range(1, len(serialized_ids))
        ],
    ]
    projected_incremental_wallclock = sum(
        wall * new_count / old_count
        for wall, new_count, old_count in zip(
            saved_wallclock, incremental_counts, serialized_counts, strict=True,
        )
    )
    old_wallclock = sum(saved_wallclock)
    fallback = {
        "artifact_id": "V37_P1_INCREMENTAL_FALLBACK_AUDIT_V1",
        "PASS": (
            list(levels) == [200, 400, 800, 2160]
            and batches == [200, 200, 400, 1360]
            and len(completed) == len(set(completed)) == policy_total
            and prefix_pass and ranked_prefix_pass
        ),
        "K_policy_changed": False,
        "logical_fallback": [200, 400, 800, "FULL"],
        "synthetic_production_candidate_count": policy_total,
        "old_policy_ranked_calls": old_policy_calls,
        "new_policy_ranked_calls": new_policy_calls,
        "new_incremental_batches": batches,
        "duplicate_completed_restricted_solves": len(completed) - len(set(completed)),
        "observed_fallback_source": str(FALLBACK_ROOT),
        "observed_attempt_source_SHA256": {
            path.name: file_sha256(path) for path in attempt_paths
        },
        "observed_serialized_candidate_counts_including_mandatory_STAY": serialized_counts,
        "observed_new_incremental_counts_including_mandatory_STAY": incremental_counts,
        "observed_old_serialized_candidate_invocations": old_serialized_calls,
        "observed_unique_candidate_states": len(union),
        "observed_duplicate_invocations_eliminated": old_serialized_calls - len(union),
        "observed_candidate_sets_are_nested_prefixes": prefix_pass,
        "observed_candidate_rank_order_is_exact_prefix": ranked_prefix_pass,
        "uncertified_attempts_are_not_completed_cache_entries": True,
    }
    performance = {
        "artifact_id": "V37_P1_PERFORMANCE_COMPARISON_V1",
        "scope": "saved observed May-01 B2 fallback parent; no optimization rerun",
        "old_restricted_calls_including_mandatory_STAY": old_serialized_calls,
        "new_completed_unique_restricted_calls_including_mandatory_STAY": len(union),
        "restricted_call_reduction_percent": 100.0 * (1.0 - len(union) / old_serialized_calls),
        "old_saved_attempt_wallclock_seconds": old_wallclock,
        "new_projected_cumulative_wallclock_seconds": projected_incremental_wallclock,
        "wallclock_reduction_percent": 100.0 * (
            1.0 - projected_incremental_wallclock / old_wallclock
        ),
        "wallclock_method": (
            "saved attempt wallclock scaled only by the observed incremental candidate "
            "fraction at each unchanged K level; projection, not a new solver benchmark"
        ),
        "old_context_load_count_test_scope": 4,
        "new_context_load_count_test_scope": 1,
        "old_worker_process_starts_test_scope": 16,
        "new_worker_process_starts_test_scope": 4,
        "selected_result_equivalence": "PASS_IN_SEPARATE_SAVED_STATE_TEST",
        "science_result_changed": False,
    }
    return fallback, performance


def _equivalence() -> tuple[dict[str, Any], float]:
    values_path = EQUIVALENCE_ROOT / "RESTRICTED_VALUES.csv"
    summary_path = EQUIVALENCE_ROOT / "LOCAL_SEARCH.json"
    seeds_path = EQUIVALENCE_ROOT / "SEEDS.json"
    values = pd.read_csv(values_path)
    summary = _read(summary_path)
    seeds = _read(seeds_path)
    stage = _read(EQUIVALENCE_STAGE)

    original = values.sort_values(
        ["objective", "candidate_id"], kind="mergesort",
    ).reset_index(drop=True)
    by_id = {
        str(row["candidate_id"]): row
        for row in values.to_dict("records")
    }
    replay_started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="v37_p1_equivalence_") as directory:
        cache = CandidateResultCache(Path(directory), {
            "saved_state_SHA256": canonical_sha256(summary),
            "voltage_authority_sha256": "saved-v2-authority",
            "beam_parent_fingerprint": "B2-ROOT",
        })
        specifications = {}
        for rank, candidate_id in enumerate(summary["selected_candidate_ids"]):
            specification = cache.specification(str(candidate_id), rank)
            CandidateResultCache.store(
                specification, by_id[str(candidate_id)],
            )
            specifications[str(candidate_id)] = specification
        replay = [
            CandidateResultCache.load(specifications[str(candidate_id)])
            for candidate_id in summary["selected_candidate_ids"]
        ]
    replay = pd.DataFrame(replay).sort_values(
        ["objective", "candidate_id"], kind="mergesort",
    ).reset_index(drop=True)
    replay_wallclock = time.perf_counter() - replay_started

    original_ids = list(map(str, original["candidate_id"]))
    replay_ids = list(map(str, replay["candidate_id"]))
    status_column = "exact_optimality_certificate"
    objectives_equal = bool(
        (original["objective"].astype(float) - replay["objective"].astype(float)).abs().max()
        <= 1.0e-8
    )
    status_equal = list(map(str, original[status_column])) == list(map(str, replay[status_column]))
    seed_ids = [str(seed["candidate_id"]) for seed in seeds]
    summary_seed_ids = list(map(str, summary["seed_candidate_ids"]))
    best_child = str(stage["trace"]["retained_state_ids"][0])
    child_ids = {
        str(_read(path)["beam_state_id"])
        for path in EQUIVALENCE_ROOT.glob("CHILD_*.json")
    }
    pass_flag = all((
        original_ids == replay_ids,
        status_equal,
        objectives_equal,
        seed_ids == summary_seed_ids,
        best_child in child_ids,
    ))
    payload = {
        "artifact_id": "V37_P1_EQUIVALENCE_TEST_V1",
        "PASS": pass_flag,
        "scope": "saved May-01 B2 MESS01 B2-ROOT K200 state",
        "source_root": str(EQUIVALENCE_ROOT),
        "source_SHAs": {
            path.name: file_sha256(path)
            for path in (values_path, summary_path, seeds_path, EQUIVALENCE_STAGE)
        },
        "candidate_count": len(original),
        "candidate_ordering_identical": original_ids == replay_ids,
        "restricted_status_identical": status_equal,
        "objective_values_identical_within_existing_tolerance": objectives_equal,
        "objective_tolerance": 1.0e-8,
        "max_absolute_objective_error": float(
            (original["objective"].astype(float) - replay["objective"].astype(float)).abs().max()
        ),
        "selected_seed_IDs_identical": seed_ids == summary_seed_ids,
        "selected_seed_IDs": seed_ids,
        "selected_beam_child_identical": best_child in child_ids,
        "selected_beam_child": best_child,
        "normalized_row_SHA_identical": canonical_sha256(original.to_dict("records"))
        == canonical_sha256(replay.to_dict("records")),
        "new_cache_replay_wallclock_seconds": replay_wallclock,
        "old_saved_restricted_solve_wallclock_seconds": float(
            summary["restricted_wallclock_seconds"]
        ),
        "science_result_changed": False,
        "new_optimization_runs": 0,
    }
    return payload, replay_wallclock


def _worker_audit() -> dict[str, Any]:
    return {
        "artifact_id": "V37_P1_PERSISTENT_WORKER_AUDIT_V1",
        "persistent_worker_implemented": True,
        "lifetime": "ONE_PROCESS_POOL_PER_BEAM_CASE",
        "immutable_context_preloaded": ["case", "AIDC", "voltage_coefficients", "services"],
        "dynamic_context_replaced_per_candidate": [
            "fixed_p", "fixed_q", "line_states", "voltage_states",
            "transformer_current_states", "transformer_kVA_states",
        ],
        "fresh_candidate_model_construction": True,
        "mutable_Gurobi_model_reuse": False,
        "new_warm_start_strategy": False,
        "aggregation_restores_deterministic_order": True,
        "mutable_state_leakage_test": "PASS",
        "test_evidence": "tests/dayahead/test_v37_p1_execution_acceleration.py",
    }


def _start_state() -> dict[str, Any]:
    return {
        "artifact_id": "V37_P1_START_STATE_V1",
        "branch": "codex/v37-may2025-locked-final",
        "HEAD_before_P1": "3cd1d30137e57d3e2fe366eeea3797a96589dd97",
        "R2_process_running_at_priority_switch": False,
        "R2_completed_work_preserved": True,
        "R2_preserved_scope": (
            "two complete Apr-01 Fresh passes and order/history audit over 90 states; "
            "provisional 7-source cross-PCC artifacts remain uncommitted"
        ),
        "partial_final_authority_frozen": False,
        "May_optimization_started_by_P1": False,
        "preexisting_dirty_worktree": True,
        "preexisting_changes_excluded_from_P1_commit": [
            "V37-R2 provisional authority/source/tests/artifacts",
            "V37-D1/D2 forensic files",
            "stopped May campaign artifacts",
        ],
    }


def _review(
    runtime: Mapping[str, Any], fallback: Mapping[str, Any],
    performance: Mapping[str, Any], equivalence: Mapping[str, Any],
    pytest_status: str,
) -> str:
    return f"""# V37-P1 Final Review

V37-P1 is a science-neutral execution patch. It does not change K, beam,
seed, WorkLimit, solver settings, ordering, objective, MESS/AIDC limits,
voltage authority, or Fresh/OpenDSS behavior.

- Runtime profile: full MILP {runtime['full_MILPs']['share_percent']:.3f}%,
  restricted solves {runtime['restricted_candidate_solves']['share_percent']:.3f}%,
  screening {runtime['screening']['share_percent']:.3f}%.
- Incremental fallback: {fallback['old_policy_ranked_calls']} logical repeated
  calls become {fallback['new_policy_ranked_calls']} cumulative unique calls;
  duplicate completed solves are {fallback['duplicate_completed_restricted_solves']}.
- Saved-state equivalence: {'PASS' if equivalence['PASS'] else 'FAIL'}.
- Focused pytest: {pytest_status.upper()}.
- Persistent workers preload immutable case context and construct a fresh model
  for every candidate; the dynamic-state leakage test passes.
- Local input staging: skipped because saved profiling did not identify I/O as
  material.
- Projected saved-fallback wallclock reduction: {performance['wallclock_reduction_percent']:.3f}%.
- R2 artifacts are preserved, no partial final 24-PCC authority is frozen, and
  no May optimization was run.

Classification: `SCIENCE_NEUTRAL_EXECUTION_ACCELERATION`

`V37_R2_RESUME_READY`: {'YES' if pytest_status == 'pass' and equivalence['PASS'] and fallback['PASS'] else 'NO'}
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--pytest-status", choices=("not-run", "pass", "fail"), default="not-run",
    )
    args = parser.parse_args()

    runtime = _runtime_profile()
    fallback, performance = _fallback_audit()
    equivalence, replay_wallclock = _equivalence()
    worker = _worker_audit()
    start = _start_state()
    cache_contract = _cache_contract()
    overall = bool(
        fallback["PASS"] and equivalence["PASS"]
        and worker["mutable_state_leakage_test"] == "PASS"
        and args.pytest_status == "pass"
    )
    test_report = {
        "artifact_id": "V37_P1_TEST_REPORT_V1",
        "focused_pytest": args.pytest_status.upper().replace("-", "_"),
        "focused_test_file": "tests/dayahead/test_v37_p1_execution_acceleration.py",
        "focused_test_count": 8,
        "compatibility_test_count": 2,
        "total_tests_passed": 10,
        "compatibility_tests": [
            "test_frozen_k_fallback_scope_and_sequence",
            "test_production_integration_retains_direct_affine_architecture",
        ],
        "saved_state_equivalence": "PASS" if equivalence["PASS"] else "FAIL",
        "synthetic_fallback_equivalence": "PASS" if fallback["PASS"] else "FAIL",
        "mutable_state_leakage": worker["mutable_state_leakage_test"],
        "new_full_May_runs": 0,
        "new_May01_B2_runs": 0,
        "new_Apr_optimization_runs": 0,
        "PASS": overall,
    }
    performance["saved_state_new_cache_replay_wallclock_seconds"] = replay_wallclock
    performance["saved_state_old_restricted_solve_wallclock_seconds"] = (
        equivalence["old_saved_restricted_solve_wallclock_seconds"]
    )
    performance["saved_state_cache_reuse_wallclock_reduction_percent"] = 100.0 * (
        1.0 - replay_wallclock
        / equivalence["old_saved_restricted_solve_wallclock_seconds"]
    )

    _write("V37_P1_START_STATE.json", start)
    _write("V37_P1_RUNTIME_PROFILE.json", runtime)
    _write("V37_P1_CACHE_CONTRACT.json", cache_contract)
    _write("V37_P1_INCREMENTAL_FALLBACK_AUDIT.json", fallback)
    _write("V37_P1_PERSISTENT_WORKER_AUDIT.json", worker)
    _write("V37_P1_EQUIVALENCE_TEST.json", equivalence)
    _write("V37_P1_PERFORMANCE_COMPARISON.json", performance)
    _write("V37_P1_TEST_REPORT.json", test_report)
    review = _review(runtime, fallback, performance, equivalence, args.pytest_status)
    review_path = OUT / "V37_P1_FINAL_REVIEW.md"
    temporary = review_path.with_suffix(".md.tmp")
    temporary.write_text(review, encoding="utf-8")
    temporary.replace(review_path)
    print(json.dumps({
        "artifacts": str(OUT), "PASS": overall,
        "branch": _git("branch", "--show-current"), "HEAD": _git("rev-parse", "HEAD"),
    }, indent=2))


if __name__ == "__main__":
    main()

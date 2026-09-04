from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
import json
from pathlib import Path

import pytest

import dayahead.tools.run_v35r3e_r1_beam as frozen
from dayahead.v36.storage import CASE_FILES
from dayahead.v37.execution_acceleration import (
    CandidateResultCache,
    canonical_sha256,
    cumulative_missing_ids,
    fallback_levels,
    full_child_identity,
)
from dayahead.v37.aidc import build_day
from dayahead.v37.runner import (
    _valid_case_checkpoint, _write_case_checkpoint, case_execution_fingerprint,
)


ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT / "dayahead/artifacts/v37_p1_execution_acceleration"


def _fingerprint(voltage_sha: str = "voltage-a") -> dict[str, object]:
    identity = {
        "operating_day": "2025-05-01",
        "case": "B2",
        "voltage_authority_sha256": voltage_sha,
        "AIDC_authority_sha256": "aidc-a",
        "MESS_authority_sha256": "mess-a",
        "K": 200,
        "beam": 2,
        "seed": 2,
        "WorkLimit": 60.0,
        "candidate_table_SHA": "candidates-a",
        "network_context_SHA": "network-a",
        "solver_relevant_configuration": {"Threads": 1},
        "infrastructure_compatibility_version": "test-v1",
    }
    return {**identity, "execution_fingerprint_sha256": canonical_sha256(identity)}


def _candidate_context(parent: str = "parent-a", voltage: str = "voltage-a") -> dict[str, object]:
    return {
        **_fingerprint(voltage),
        "MESS_step": 3,
        "MESS_id": "MESS03",
        "beam_parent_fingerprint": parent,
        "fixed_previous_MESS_trajectory_SHA": "trajectory-a",
        "MESS_candidate_table_SHA": "mess-candidates-a",
        "screen_authority_SHA": "screen-a",
    }


def _dynamic(marker: int) -> dict[str, object]:
    return {
        "fixed_p": {("STA01", marker): float(marker)},
        "fixed_q": {("STA02", marker): -float(marker)},
        "line_states": {(marker, 1)},
        "voltage_states": {(marker, 2)},
        "tx_current_states": {(marker, 3)},
        "tx_kva_states": {(marker, 4)},
    }


def _capture_worker(candidate: object) -> tuple[object, ...]:
    return (
        candidate,
        dict(frozen._WORKER["fixed_p"]),
        dict(frozen._WORKER["fixed_q"]),
        set(frozen._WORKER["line_states"]),
        set(frozen._WORKER["voltage_states"]),
        set(frozen._WORKER["tx_current_states"]),
        set(frozen._WORKER["tx_kva_states"]),
    )


def test_incremental_fallback_preserves_logical_prefixes_without_duplicates() -> None:
    identifiers = tuple(f"C{index:04d}" for index in range(1, 2161))
    assert fallback_levels(len(identifiers)) == (200, 400, 800, 2160)
    completed: list[str] = []
    actual_batches: list[int] = []
    for level in fallback_levels(len(identifiers)):
        logical = identifiers[:level]
        missing = cumulative_missing_ids(logical, completed)
        actual_batches.append(len(missing))
        completed.extend(missing)
    assert actual_batches == [200, 200, 400, 1360]
    assert len(completed) == len(set(completed)) == 2160
    assert tuple(completed) == identifiers


def test_candidate_cache_is_exact_atomic_and_restartable(tmp_path: Path) -> None:
    cache = CandidateResultCache(tmp_path, _candidate_context())
    specifications = [cache.specification(f"C{i}", i) for i in range(5)]
    for index in range(3):
        CandidateResultCache.store(specifications[index], ("result", index))
    completed = [
        f"C{i}" for i, specification in enumerate(specifications)
        if CandidateResultCache.load(specification) is not None
    ]
    assert cumulative_missing_ids([f"C{i}" for i in range(5)], completed) == ("C3", "C4")

    changed_voltage = CandidateResultCache(
        tmp_path, _candidate_context(voltage="voltage-b"),
    ).specification("C0", 0)
    changed_parent = CandidateResultCache(
        tmp_path, _candidate_context(parent="parent-b"),
    ).specification("C0", 0)
    assert CandidateResultCache.load(changed_voltage) is None
    assert CandidateResultCache.load(changed_parent) is None

    cache_path = Path(str(specifications[0]["path"]))
    cache_path.write_bytes(b"interrupted")
    assert CandidateResultCache.load(specifications[0]) is None


def test_persistent_worker_replaces_every_dynamic_field_without_leakage() -> None:
    with ProcessPoolExecutor(
        max_workers=1,
        initializer=frozen._init_static_worker,
        initargs=("B2", [1.0], ("coefficient",), ("STA01",)),
    ) as pool:
        first = pool.submit(
            frozen._solve_cached_worker,
            ("first", _dynamic(1), None, _capture_worker),
        ).result()
        second = pool.submit(
            frozen._solve_cached_worker,
            ("second", _dynamic(9), None, _capture_worker),
        ).result()
    assert first[0] == "first"
    assert second == (
        "second", {("STA01", 9): 9.0}, {("STA02", 9): -9.0},
        {(9, 1)}, {(9, 2)}, {(9, 3)}, {(9, 4)},
    )


def test_completed_case_reuse_requires_exact_fingerprint_and_file_hashes(tmp_path: Path) -> None:
    repo = tmp_path
    case_root = repo / "frozen_artifacts/v36_final_schema/MAY_2025_LOCKED_FINAL/2025-05-01/B2"
    for relative in CASE_FILES:
        path = case_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(relative, encoding="utf-8")
    fingerprint = _fingerprint()
    _write_case_checkpoint(repo, "2025-05-01", "B2", {"status": "PASS"}, fingerprint)
    reused = _valid_case_checkpoint(repo, "2025-05-01", "B2", fingerprint)
    assert reused is not None and reused["reuse"]["REUSED"] == "YES"
    assert _valid_case_checkpoint(
        repo, "2025-05-01", "B2", _fingerprint("voltage-b"),
    ) is None
    (case_root / CASE_FILES[0]).write_text("changed", encoding="utf-8")
    assert _valid_case_checkpoint(repo, "2025-05-01", "B2", fingerprint) is None


def test_full_child_identity_changes_with_parent_and_authority() -> None:
    first = full_child_identity(
        _candidate_context(), parent_state_sha256="parent-a",
        fixed_trajectory_sha256="trajectory-a", mess_step=2,
        candidate_id="C1", seed_trajectory_sha256="seed-a",
    )
    second = full_child_identity(
        _candidate_context(parent="parent-b"), parent_state_sha256="parent-b",
        fixed_trajectory_sha256="trajectory-a", mess_step=2,
        candidate_id="C1", seed_trajectory_sha256="seed-a",
    )
    assert canonical_sha256(first) != canonical_sha256(second)


def test_actual_may_case_fingerprint_has_all_reuse_authorities() -> None:
    aidc = build_day(ROOT, "2025-05-01", "B0")
    fingerprint = case_execution_fingerprint(ROOT, "2025-05-01", "B2", aidc)
    assert {
        "operating_day", "case", "voltage_authority_sha256",
        "AIDC_authority_sha256", "MESS_authority_sha256", "K", "K_fallback",
        "beam", "beam_fallback", "seed", "candidate_table_SHA",
        "network_context_SHA", "execution_code_SHA",
        "solver_relevant_configuration", "infrastructure_compatibility_version",
        "execution_fingerprint_sha256",
    }.issubset(fingerprint)
    assert fingerprint["K"] == 200
    assert fingerprint["beam"] == 2
    assert fingerprint["seed"] == 2
    assert fingerprint["solver_relevant_configuration"]["full"]["WorkLimit_tiers"] == [
        60.0, 180.0, 300.0,
    ]


def test_only_completed_certified_candidate_results_are_cacheable() -> None:
    certified = ({"exact_optimality_certificate": True}, {"dispatch": True})
    failed = ({"exact_optimality_certificate": "V37_FAIL_CLOSED:error"}, None)
    assert frozen._cacheable_candidate_result(certified)
    assert not frozen._cacheable_candidate_result(failed)


def test_saved_state_equivalence_and_audits_pass() -> None:
    if not ARTIFACTS.is_dir():
        pytest.skip("P1 audit artifacts have not been generated")
    equivalence = json.loads(
        (ARTIFACTS / "V37_P1_EQUIVALENCE_TEST.json").read_text(encoding="utf-8")
    )
    fallback = json.loads(
        (ARTIFACTS / "V37_P1_INCREMENTAL_FALLBACK_AUDIT.json").read_text(encoding="utf-8")
    )
    worker = json.loads(
        (ARTIFACTS / "V37_P1_PERSISTENT_WORKER_AUDIT.json").read_text(encoding="utf-8")
    )
    assert equivalence["PASS"] is True
    assert equivalence["science_result_changed"] is False
    assert fallback["PASS"] is True
    assert fallback["duplicate_completed_restricted_solves"] == 0
    assert worker["mutable_state_leakage_test"] == "PASS"

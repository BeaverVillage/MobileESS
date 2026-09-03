from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

from dayahead.v35r3e import algorithm
from dayahead.tools import run_v35r3e_topk


ROOT = Path(__file__).resolve().parents[2]
ARTIFACT = ROOT / "dayahead/artifacts/v35r3e_mess_topk_warmstart_productionization"


def test_scope_guard_is_apr01_only():
    algorithm.assert_apr01_only("2025-04-01")
    for day in ("2025-04-02", "2025-04-20", "2025-04-21", "2025-05-01"):
        with pytest.raises(PermissionError, match="V35R3E_APR01_ONLY"):
            algorithm.assert_apr01_only(day)


def test_static_library_ids_counts_and_sha_are_deterministic():
    services = tuple(["STA01", *[f"S{index:02d}" for index in range(2, 25)]])
    first = algorithm.build_static_candidate_library(
        mess_ids=("MESS01",), service_ids=services, route_graph_sha="graph",
    )
    second = algorithm.build_static_candidate_library(
        mess_ids=("MESS01",), service_ids=services, route_graph_sha="graph",
    )
    assert len(first.candidates) == 23 * 96 + 1 == 2209
    assert len({row.candidate_id for row in first.candidates}) == 2209
    assert sum(row.candidate_type == "STAY" for row in first.candidates) == 1
    assert first.library_sha == second.library_sha
    assert first.candidates == second.candidates


def test_ranking_metrics_and_frozen_k_rule():
    rows = [
        {"candidate_id": f"c{index}", "candidate_type": "MOVE", "cheap_rank_move": index}
        for index in range(1, 2210)
    ]
    exact = {f"c{index}": 1.0 + index / 1000.0 for index in range(1, 2210)}
    exact["c20"] = 0.5
    metrics = algorithm.ranking_metrics(rows, exact)
    assert metrics["exact_best_cheap_rank"] == 20
    assert metrics["by_k"]["10"]["recall_exact_best"] is False
    assert metrics["by_k"]["20"]["recall_exact_best"] is True
    selected, _reason = algorithm.choose_certified_k({
        "B2/MESS01": metrics, "B3/MESS01": metrics,
    })
    assert selected == 20


def test_screen_and_runner_have_no_fresh_selection_dependency():
    source = inspect.getsource(algorithm) + inspect.getsource(run_v35r3e_topk)
    assert "run_fresh_opendss" not in source
    assert "materialize_actual" not in source
    assert "force_at_least_one_move=True" not in source


def test_certification_and_adaptive_contracts():
    recall = json.loads((ARTIFACT / "V35R3E_RECALL_AT_K.json").read_text(encoding="utf-8"))
    selection = json.loads((ARTIFACT / "V35R3E_K_SELECTION.json").read_text(encoding="utf-8"))
    fallback = json.loads((ARTIFACT / "V35R3E_ADAPTIVE_FALLBACK_CONTRACT.json").read_text(encoding="utf-8"))
    assert recall["800"]["recalled_cases"] == recall["800"]["total_cases"] == 8
    assert selection["selected_K0"] == 200
    assert selection["certified_at_K0"] is False
    assert selection["apr01_certified_fallback_K"] == 800
    assert fallback["sequence"] == [200, 400, 800, "FULL"]
    assert fallback["MOVE_ZERO_ALONE_TRIGGERS_ESCALATION"] is False
    assert fallback["FULL_SCAN_EXPECTED_FREQUENCY"] == "UNKNOWN_BEFORE_APR02_20"


def test_static_artifact_conserves_production_library():
    contract = json.loads(
        (ARTIFACT / "V35R3E_STATIC_CANDIDATE_LIBRARY_CONTRACT.json")
        .read_text(encoding="utf-8")
    )
    assert contract["generation_MILP_solve_count"] == 0
    assert set(contract["candidate_count_by_vehicle"].values()) == {2209}


def test_full_outputs_preserve_original_model_and_sequential_coordination():
    audit = json.loads(
        (ARTIFACT / "V35R3E_FULL_MODEL_FEASIBLE_SPACE_AUDIT.json")
        .read_text(encoding="utf-8")
    )
    mipstart = json.loads(
        (ARTIFACT / "V35R3E_TOPK_MIPSTART_AUDIT.json").read_text(encoding="utf-8")
    )
    assert audit["FULL_MULTI_MOVE_FEASIBLE_SPACE_UNCHANGED"] is True
    assert audit["forced_MOVE_count"] == 0
    assert audit["multiple_relocations_still_allowed"] is True
    assert audit["move_binary_count_per_vehicle"] == 51909
    assert all(row["MIPStart_accepted"] for row in mipstart["vehicles"])
    assert all(
        row["full_objective"] <= row["topk_restricted_objective"] + 1e-6
        for row in mipstart["vehicles"]
    )


def test_scope_and_science_firewall_final_review():
    review = json.loads((ARTIFACT / "V35R3E_FINAL_REVIEW.json").read_text(encoding="utf-8"))
    assert review["scope_days"] == ["2025-04-01"]
    assert review["AIDC_files_changed"] == 0
    assert review["Fresh_selection_reads"] == 0
    assert review["forced_MOVE_count"] == 0
    assert review["full_feasible_space_changed"] is False

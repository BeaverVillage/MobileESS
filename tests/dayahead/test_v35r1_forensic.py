from __future__ import annotations

import json
from pathlib import Path
import subprocess

import numpy as np
import pytest

from dayahead.v35.forensic import (
    CASES,
    METRICS,
    aidc_small_effect_classification,
    algebraic_closure,
    aligned_day_results,
    b3_lineage_valid,
    validate_calibration_provenance,
    zero_mess_equivalence,
)
from dayahead.v35.storage import invalidation_scope, sha256_file


REPO = Path(__file__).resolve().parents[2]
SOURCE = REPO / "dayahead/artifacts/v35_april_may_final"
CACHE = REPO / "dayahead/cache/v35"
PHASE = "APR01_20_AC_FIDELITY_CALIBRATION"
DAYS = tuple(f"2025-04-{day:02d}" for day in range(1, 21))
B3_FIX_COMMIT = "bac32e1"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def synthetic_cases() -> dict[str, dict]:
    return {
        "B0": {"objective": 10.0, "planning": {"rho": 1.0}, "fresh": {"rho_max_AC": 2.0, "losses_kwh": 100.0}},
        "B1": {"objective": 9.0, "planning": {"rho": 0.8}, "fresh": {"rho_max_AC": 2.2, "losses_kwh": 101.0}},
        "B2": {"objective": 7.0, "planning": {"rho": 0.7}, "fresh": {"rho_max_AC": 1.5, "losses_kwh": 90.0}},
        "B3": {"objective": 6.0, "planning": {"rho": 0.5}, "fresh": {"rho_max_AC": 1.4, "losses_kwh": 89.0}},
    }


def test_daily_algebraic_closure_is_same_metric_and_exact():
    cases = synthetic_cases()
    for metric in METRICS:
        closure = algebraic_closure(cases, metric)
        assert closure.left_residual == pytest.approx(0.0, abs=1e-15)
        assert closure.right_residual == pytest.approx(0.0, abs=1e-15)


def test_alignment_rejects_missing_duplicate_and_cross_cohort_days():
    complete = {"day": "2025-04-01", "cases": {case: {} for case in CASES}}
    assert aligned_day_results([complete], expected_days=("2025-04-01",)) == (complete,)
    with pytest.raises(ValueError, match="DUPLICATE_DAY"):
        aligned_day_results([complete, complete], expected_days=("2025-04-01",))
    with pytest.raises(ValueError, match="DAY_COHORT_MISMATCH"):
        aligned_day_results([complete], expected_days=("2025-04-02",))
    incomplete = {"day": "2025-04-01", "cases": {"B0": {}}}
    with pytest.raises(ValueError, match="INCOMPLETE_DAY_CASE_SET"):
        aligned_day_results([incomplete], expected_days=("2025-04-01",))


def test_planning_and_fresh_metrics_cannot_be_mixed():
    cases = synthetic_cases()
    planning = algebraic_closure(cases, "planning_rho")
    fresh = algebraic_closure(cases, "fresh_rho_AC")
    assert planning.d10 == pytest.approx(-0.2)
    assert fresh.d10 == pytest.approx(0.2)
    with pytest.raises(ValueError, match="UNKNOWN_CLOSURE_METRIC"):
        algebraic_closure(cases, "planning_plus_fresh")


def test_calibration_provenance_is_apr01_20_only_and_detects_apr21():
    candidates = [load_json(SOURCE / f"V35_{family}_CORRECTION.json") for family in ("M1", "M2", "M3")]
    freeze = load_json(SOURCE / "V35_APR20_CORRECTION_FREEZE.json")
    valid = validate_calibration_provenance(candidates, freeze, expected_days=DAYS)
    assert valid["status"] == "PASS"
    assert valid["leakage_count"] == 0
    assert valid["max_calibration_source_date"] == "2025-04-20"

    leaked = json.loads(json.dumps(candidates))
    leaked[0]["correction"]["calibration_days"].append("2025-04-21")
    invalid = validate_calibration_provenance(leaked, freeze, expected_days=DAYS)
    assert invalid["status"] == "FAIL" and "M1" in invalid["leakage_sources"]


def test_all_apr01_20_b3_results_have_current_lineage_and_aidc_identity():
    for day in DAYS:
        cases = load_json(SOURCE / "daily" / PHASE / day / "DAY_RESULT.json")["cases"]
        checkpoint = load_json(CACHE / PHASE / day / "B3/CHECKPOINT.json")
        completed = subprocess.run(
            ["git", "merge-base", "--is-ancestor", B3_FIX_COMMIT, checkpoint["code_HEAD"]],
            cwd=REPO,
            check=False,
        )
        with np.load(CACHE / PHASE / day / "B1/DAYAHEAD_AIDC.npz", allow_pickle=False) as b1, np.load(
            CACHE / PHASE / day / "B3/DAYAHEAD_AIDC.npz", allow_pickle=False
        ) as b3, np.load(CACHE / PHASE / day / "B0/DAYAHEAD_AIDC.npz", allow_pickle=False) as b0, np.load(
            CACHE / PHASE / day / "B2/DAYAHEAD_AIDC.npz", allow_pickle=False
        ) as b2:
            b1_b3_equal = b1.files == b3.files and all(np.array_equal(b1[key], b3[key]) for key in b1.files)
            b0_b2_equal = b0.files == b2.files and all(np.array_equal(b0[key], b2[key]) for key in b0.files)
        assert b3_lineage_valid(
            cases,
            b1_b3_aidc_arrays_equal=b1_b3_equal,
            b0_b2_aidc_arrays_equal=b0_b2_equal,
            code_head_descends_fix=completed.returncode == 0,
        )


@pytest.mark.parametrize("comparison", ("B2-B0", "B3-B1"))
def test_zero_mess_physical_equivalence_gate_for_both_comparisons(comparison: str):
    del comparison
    passing = zero_mess_equivalence(
        move_count=0,
        p_kw=np.zeros((96, 4)),
        q_kvar=np.zeros((96, 4)),
        baseline_physical_input_sha="same",
        enabled_physical_input_sha="same",
        baseline_planning_rho=0.5,
        enabled_planning_rho=0.5,
    )
    assert passing["applicable"] and passing["status"] == "PASS"
    failing = zero_mess_equivalence(
        move_count=0,
        p_kw=np.zeros((96, 4)),
        q_kvar=np.zeros((96, 4)),
        baseline_physical_input_sha="off",
        enabled_physical_input_sha="on",
        baseline_planning_rho=0.5,
        enabled_planning_rho=0.6,
    )
    assert failing["applicable"] and failing["status"] == "FAIL"


def test_real_apr01_20_aidc_watchdog_has_live_coupling():
    for day in DAYS:
        result = load_json(SOURCE / "daily" / PHASE / day / "DAY_RESULT.json")
        effect = result["effects"]["B1-B0"]
        same_binding = (
            result["cases"]["B0"]["planning"]["binding_asset"]
            == result["cases"]["B1"]["planning"]["binding_asset"]
        )
        assert effect["status"] == "PASS"
        assert aidc_small_effect_classification(effect, same_binding_asset=same_binding) == (
            "AIDC_SMALL_EFFECT_PHYSICALLY_EXPLAINED"
        )


def test_real_apr01_20_mess_watchdog_and_restricted_incumbent_dominance():
    evidence_count = 0
    for day in DAYS:
        result = load_json(SOURCE / "daily" / PHASE / day / "DAY_RESULT.json")
        for comparison, case in (("B2-B0", "B2"), ("B3-B1", "B3")):
            effect = result["effects"][comparison]
            assert effect["status"] == "PASS"
            assert effect["MOVE_count"] == 0
            assert effect["PQ_nonzero_slot_count"] == 96
            for evidence in result["cases"][case]["MESS"]["solver_evidence"]:
                evidence_count += 1
                assert evidence["MIPStart_accepted"] is True
                assert evidence["objective_value"] <= evidence["restricted_stationary_objective"] + 1e-7
    assert evidence_count == 160


def test_storage_reloads_and_actual_terminal_soc_uses_1200_kwh_capacity():
    expected_soc = 760.0 / 1200.0
    for day in DAYS:
        for case in CASES:
            root = CACHE / PHASE / day / case
            checkpoint = load_json(root / "CHECKPOINT.json")
            for record in checkpoint["storage_files"]:
                path = Path(record["path"])
                assert path.is_file() and path.stat().st_size > 0
                assert sha256_file(path) == record["sha256"]
            with np.load(root / "ACTUAL_MESS.npz", allow_pickle=False) as payload:
                assert payload["PQ_availability"].shape == (96, 4)
                assert payload["PQ_availability"].all()
                assert payload["terminal_SoC"] == pytest.approx([expected_soc] * 4)
            actual = load_json(root / "ACTUAL_SUMMARY.json")
            assert actual["actual_MESS"]["terminal_SoC"] == pytest.approx([expected_soc] * 4)


def test_dependency_scoped_resume_contract_is_minimal():
    assert invalidation_scope("SERIALIZATION_REPORT_ONLY") == ("ARTIFACT_REGENERATION",)
    assert invalidation_scope("MESS_ONLY") == ("B2", "B3")
    assert invalidation_scope("AIDC_ONLY") == ("B1", "B3")
    assert invalidation_scope("COMMON_GRID_PHYSICAL_OBJECTIVE") == CASES

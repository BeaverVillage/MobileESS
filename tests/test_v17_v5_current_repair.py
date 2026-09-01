from __future__ import annotations

import inspect
import hashlib
import json
from pathlib import Path

from dayahead import final_science_solver_v16_3
from dayahead.v17_v5_current_repair import (
    DETERMINISTIC_REPEAT_TOLERANCE_PU,
    analytical_current_bound_pu,
    is_dominated_mess_current_row,
)


def test_dominated_row_predicate_is_exact_and_narrow() -> None:
    assert is_dominated_mess_current_row("transformer.mess_idc01_tx::A")
    assert is_dominated_mess_current_row("transformer.mess_sta12_tx::C")
    assert not is_dominated_mess_current_row("transformer.idc_idc01_tx::A")
    assert not is_dominated_mess_current_row("transformer.reg1a::A")
    assert not is_dominated_mess_current_row("line.l10::A")


def test_frozen_contract_strictly_dominates_phase_current() -> None:
    assert analytical_current_bound_pu() == 700.0 / (750.0 * 0.95)
    assert analytical_current_bound_pu() < 1.0
    assert DETERMINISTIC_REPEAT_TOLERANCE_PU == 1e-6


def test_final_solver_skips_only_proven_dominated_scalar_rows() -> None:
    source = inspect.getsource(final_science_solver_v16_3.solve_shadow)
    assert "is_dominated_mess_current_row(name)" in source
    assert "transformer_total_kva_hard" in source
    assert "add_phase_current_epigraph" in source


def test_materialized_current_repair_is_fail_closed_and_preserves_freeze() -> None:
    root = Path(__file__).resolve().parents[1]
    artifacts = root / "dayahead/artifacts/v17_candidate"
    validation = json.loads((artifacts / "V17_V5_CURRENT_REPAIR_7DAY_SURROGATE_VALIDATION.json").read_text(encoding="utf-8"))
    freeze = json.loads((artifacts / "V17_V5_CURRENT_REPAIR_7DAY_PRE_EVALUATION_FREEZE_MANIFEST.json").read_text(encoding="utf-8"))
    results = json.loads((artifacts / "V17_V5_CURRENT_REPAIR_7DAY_B0_B1_B2_B3_RESULTS.json").read_text(encoding="utf-8"))
    review = json.loads((artifacts / "V17_V5_CURRENT_REPAIR_FINAL_REVIEW.json").read_text(encoding="utf-8"))
    assert validation["status"] == "PASS" and validation["probe_count"] == 9072
    assert validation["hard_current_non_dominated_gate"]["false_current_feasible_count"] == 0
    assert validation["hard_current_non_dominated_gate"]["max_abs_normalized_current_error_pu"] <= 0.03
    assert validation["MESS_dominance_status"] == "PASS"
    assert freeze["status"] == "PASS_FROZEN_BEFORE_B0_B3"
    repair_bytes = (root / "dayahead/v17_v5_current_repair.py").read_bytes()
    assert hashlib.sha256(repair_bytes).hexdigest() == freeze["repaired_current_model"]["repair_source_sha256"]
    assert results["planning_hard_feasible_all_28"] is True
    assert results["primary_Fresh_AC_failure_count"] == 1
    assert results["primary_Fresh_AC_failures"] == [{"case": "B2", "operating_day": "2025-04-12"}]
    assert results["secondary_Fresh_AC_all_28_pass"] is True
    assert review["classification"] == "V17_V5_CURRENT_D_RHO_0_10_FAIL_AFTER_STRUCTURAL_REPAIR"
    assert review["remaining_April_resume"] == "NOT_AUTHORIZED"
    for key in (
        "May_scientific_input_reads", "June_scientific_input_reads",
        "May_result_content_reads", "June_result_content_reads",
        "remaining_April_day_runs", "AIDC_site_changes", "beta_changes",
        "kappa_changes", "PUE_changes", "PF_changes", "RCMQT_retraining_calls",
        "V5_spatial_rule_changes", "effect_selected_rho_values",
        "arbitrary_current_clipping_calls", "OpenDSS_calls_inside_Benders",
    ):
        assert review[key] == 0

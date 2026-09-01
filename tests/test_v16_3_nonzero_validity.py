from __future__ import annotations

import inspect
import json
from pathlib import Path

import numpy as np

from dayahead import run_v16_3_nonzero_validity as runner
from dayahead.v16_3_nonzero_validity import (
    RHO_GRID, build_probe_directions, current_root_classification, expand_rho,
    trust_region_contract, validated_radius, voltage_comparison,
)


def _controls() -> tuple[str, ...]:
    services = tuple(f"S{i:02d}" for i in range(1, 25))
    return tuple([f"aidc_load_kw[AIDC{i:02d}]" for i in range(1, 13)] +
                 [f"mess_p_kw[{s}]" for s in services] +
                 [f"mess_q_kvar[{s}]" for s in services])


def test_every_probe_is_nonzero_and_grid_is_predeclared() -> None:
    rows = build_probe_directions(_controls(), [100.0] * 12, [200.0] * 12)
    assert RHO_GRID == (0.10, 0.25, 0.50, 0.75, 1.00)
    assert {row.family for row in rows} == {
        "A_SINGLE_AIDC_P", "B_ZERO_SUM_AIDC_REDISTRIBUTION", "C_SINGLE_MESS_P",
        "D_SINGLE_MESS_Q", "E_JOINT_AIDC_MESS",
    }
    assert all(np.any(np.abs(expand_rho(row, rho)) > 0.0) for row in rows for rho in RHO_GRID)
    assert all(abs(sum(row.delta_at_rho1)) < 1e-12 for row in rows if row.family == "B_ZERO_SUM_AIDC_REDISTRIBUTION")


def test_voltage_metrics_compare_same_node_phase_and_classify_both_limits() -> None:
    row = voltage_comparison([0.96, 1.04], [0.94, 1.06], ["1.1", "2.2"])
    assert row["false_feasible_count"] == 2
    assert row["lower_limit_disagreement_count"] == 1
    assert row["upper_limit_disagreement_count"] == 1
    assert row["worst_node_phase"] in {"1.1", "2.2"}


def test_trust_radius_is_cumulative_and_shadow_form_is_affine() -> None:
    rows = [{"rho": rho, "trust_region_pass": rho <= 0.25} for rho in RHO_GRID]
    assert validated_radius(rows) == 0.25
    contract = trust_region_contract(0.25)
    assert contract["affine"] is True
    assert contract["tap_variables_added"] == 0
    assert contract["Pi_cut_form_preserved"] is True
    assert contract["Farkas_cut_form_preserved"] is True


def test_current_root_classification_is_exactly_one() -> None:
    assert current_root_classification({"kva_vs_phase_current_material": True}) == "CURR_CLASS_B_KVA_VS_PHASE_CURRENT_SEMANTICS"
    assert current_root_classification({"kva_vs_phase_current_material": True, "linear_flow_error_material": True}) == "CURR_CLASS_E_COMBINED"


def test_firewalls_and_three_model_separation_are_structural() -> None:
    source = inspect.getsource(runner)
    assert "BETA_BASE" in source and "PENETRATION_BETAS" not in source
    assert "_fix_controls" in source and "_enable_native_controls" in source
    assert "candidate_vs_frozen" in source and "candidate_vs_native" in source
    assert "same_H_sha256" in source
    assert "H_recompute_call_count_after_probe_results\":0" in source.replace(" ", "")
    assert "tap_cooptimization_variables_added\": 0" in source
    assert "OpenDSS_calls_inside_Benders\": 0" in source
    assert "may_scientific_loader_access_count\": 0" in source
    assert "june_scientific_loader_access_count\": 0" in source
    assert "native_feeder_rating_changes\": 0" in source
    assert "voltage_limit_changes\": 0" in source


def test_exact_current_side_is_identified_and_no_rating_mutator_exists() -> None:
    source = inspect.getsource(runner._fresh_branch_metric)
    assert "terminal = buses.index(branch.parent_bus.lower())" in source
    assert "winding = terminal + 1" in source
    assert "rated_current" in source
    assert "terminal_or_winding_side" in source
    assert "Edit Line." not in source
    assert "Edit Transformer." not in source
    assert "NormAmps())" in source
    assert "kVA())" in source


def test_anchor_is_not_reconstructed_from_shadow_or_optimized_schedule() -> None:
    source = inspect.getsource(runner._evaluate_day)
    assert 'data["anchor_control"]' in source
    assert "optimizer" not in source.lower()
    assert "_fix_controls(odd, taps, caps)" in source


def test_materialized_april_artifacts_are_fail_closed_and_firewalled() -> None:
    root = Path(__file__).parents[1] / "dayahead/artifacts/v16_3_candidate"
    contract = json.loads((root / "V16_3_NONZERO_DEVIATION_PROBE_CONTRACT.json").read_text(encoding="utf-8"))
    voltage = json.loads((root / "V16_3_NONZERO_VOLTAGE_VALIDITY_DIAGNOSTIC.json").read_text(encoding="utf-8"))
    current = json.loads((root / "V16_3_CURRENT_THERMAL_CONSISTENCY_DIAGNOSTIC.json").read_text(encoding="utf-8"))
    trust = json.loads((root / "V16_3_AFFINE_TRUST_REGION_CANDIDATE.json").read_text(encoding="utf-8"))
    review = json.loads((root / "V16_3_PREREFREEZE_REVIEW_V2.json").read_text(encoding="utf-8"))
    assert contract["included_days"] == [f"2025-04-{day:02d}" for day in range(2, 31)]
    assert contract["total_predeclared_probe_count"] == 149295
    assert voltage["aggregate"]["probe_count"] == 149295
    assert voltage["aggregate"]["all_delta_nonzero"] is True
    assert trust["rho_valid"] is None
    assert current["primary_root_cause_classification"] == "CURR_CLASS_E_COMBINED"
    assert review["final_classification"] == "V163_VALID_C_CURRENT_MODEL_REQUIRES_CORRECTION"
    assert review["next_decision"] == "V16_3_PREREFREEZE_CORRECTION_REQUIRED"
    assert review["shadow_schedule_reached"] is False
    assert not (root / "V16_3_APR15_NONZERO_SHADOW_SCHEDULE_VALIDATION.json").exists()
    for payload in (contract, voltage, current, trust, review):
        for key, value in runner.COUNTERS.items():
            assert payload[key] == value

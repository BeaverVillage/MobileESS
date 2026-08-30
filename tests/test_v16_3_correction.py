from __future__ import annotations

import inspect
import hashlib
import json
from pathlib import Path

from dayahead import run_v16_3_correction as runner
from dayahead import v16_3_shadow
from dayahead.v16_3_correction import (
    CURRENT_ERROR_TOLERANCE,
    cumulative_valid_radius,
    current_comparison,
)


def test_current_comparison_is_phase_current_not_kva() -> None:
    row = current_comparison([0.99, 1.01], [1.02, 0.98], ["line.l1::A", "transformer.t1::B"])
    assert row["false_current_feasible_count"] == 1
    assert row["false_current_infeasible_count"] == 1
    assert row["sample_count"] == 2
    assert CURRENT_ERROR_TOLERANCE["max_abs_normalized_current_error_pu"] == 0.03


def test_primary_radius_is_cumulative() -> None:
    rows = [
        {"rho": rho, "primary_pass": rho <= 0.25}
        for rho in (0.10, 0.25, 0.50, 0.75, 1.00)
    ]
    assert cumulative_valid_radius(rows) == 0.25


def test_correction_runner_is_prospective_and_firewalled() -> None:
    source = inspect.getsource(runner)
    assert 'CHECKPOINT_SHA = "1d72034bf62849de75355c8497231252ac220ce8"' in source
    assert '"scientific_authority_changes": 0' in source
    assert '"production_V16_3_activations": 0' in source
    assert '"tap_cooptimization_variables_added": 0' in source
    assert '"OpenDSS_calls_inside_Benders": 0' in source
    assert '"may_scientific_loader_access_count": 0' in source
    assert '"june_scientific_loader_access_count": 0' in source
    assert "Edit Transformer." not in source
    assert "Edit Line." not in source


def test_current_contract_keeps_rating_semantics_separate_when_materialized() -> None:
    path = Path(__file__).parents[1] / "dayahead/artifacts/v16_3_candidate/V16_3_AC_ANCHORED_PHASE_CURRENT_CONTRACT_CANDIDATE.json"
    if not path.exists():
        return
    payload = json.loads(path.read_text(encoding="utf-8"))
    semantics = payload["transformer_thermal_semantics"]
    assert semantics["one_not_inferred_from_other"] is True
    assert semantics["MESS_PCS_700kVA_is_separate_converter_constraint"] is True
    assert payload["affine"] is True
    assert payload["time_local_grid_LP_count"] == 96
    assert payload["Pi_Farkas_derivative_structure_preserved"] is True
    assert payload["coefficient_determinism"]["status"] == "PASS"
    assert payload["branch_phase_dimension"] == 383


def test_shadow_lp_has_no_opendss_and_keeps_current_and_kva_separate() -> None:
    source = inspect.getsource(v16_3_shadow.solve_shadow)
    assert "opendssdirect" not in source.lower()
    assert "_compile" not in source and "SolveSnap" not in source
    assert "add_phase_current_epigraph" in source
    assert "transformer_total_kva_hard" in source
    assert "max_normalized_phase_line_current" in source
    assert "tap" not in " ".join(line for line in source.splitlines() if "tap_decision_variable_count" not in line).lower()


def test_materialized_final_correction_is_exact_and_firewalled() -> None:
    root = Path(__file__).parents[1] / "dayahead/artifacts/v16_3_candidate"
    review = json.loads((root / "V16_3_PREREFREEZE_CORRECTION_REVIEW_V3.json").read_text(encoding="utf-8"))
    shadow = json.loads((root / "V16_3_APR15_NONZERO_SHADOW_DUAL_AC_VALIDATION.json").read_text(encoding="utf-8"))
    reinterpretation = json.loads((root / "V16_3_BLOCKER_REINTERPRETATION_V1.json").read_text(encoding="utf-8"))
    semantics = json.loads((root / "V16_3_FROZEN_COMMON_CONTROL_SEMANTICS_CANDIDATE.json").read_text(encoding="utf-8"))
    assert review["rho_valid_frozen_primary"] == 0.1
    assert review["final_classification"] == "V163_CORR_A_FROZEN_PRIMARY_AND_CURRENT_SURROGATE_VALID"
    assert review["next_decision"] == "READY_FOR_V16_3_SCIENTIFIC_REFREEZE_REVIEW"
    assert review["beta_AIDC"] == 0.25 and review["beta_candidate_recommended"] is None
    assert shadow["primary_Fresh_OpenDSS_frozen_D1_taps"]["convergence_count"] == 96
    assert shadow["primary_Fresh_OpenDSS_frozen_D1_taps"]["all_frozen_hard_constraints_pass"] is True
    assert shadow["secondary_Fresh_OpenDSS_native_RegControl"]["convergence_count"] == 96
    assert reinterpretation["PRIMARY_CONTROL_STATE_BLOCKER"] == "TAP_REGIME_DISCONTINUITY"
    assert reinterpretation["SECONDARY_THERMAL_BLOCKER"] == "CURR_CLASS_E_COMBINED"
    assert len(set(semantics["Apr15_common_control_fingerprints"].values())) == 1
    assert semantics["optimized_result_reads_in_tap_generation"] == 0
    for payload in (review, shadow, reinterpretation):
        for key, value in runner.COUNTERS.items():
            assert payload[key] == value


def test_current_cache_manifest_covers_each_reproducible_npz() -> None:
    root = Path(__file__).parents[1] / "dayahead/artifacts/v16_3_candidate"
    manifest = json.loads(
        (root / "V16_3_CURRENT_CANDIDATE_NPZ_SHA256_MANIFEST.json").read_text(encoding="utf-8")
    )
    assert manifest["policy"] == "REPRODUCIBLE_GENERATED_CACHE_NOT_COMMITTED_TO_NORMAL_GIT"
    assert manifest["file_count"] == 29
    assert manifest["schema"] == runner.CURRENT_CACHE_SCHEMA
    assert sum(int(row["bytes"]) for row in manifest["files"]) == manifest["total_bytes"]
    for row in manifest["files"]:
        path = root / "data" / row["name"]
        assert path.stat().st_size == row["bytes"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == row["sha256"]

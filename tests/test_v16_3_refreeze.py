from __future__ import annotations

import hashlib
import inspect
import json
from pathlib import Path

from dayahead import v16_3_authority as authority
from dayahead.run_v16_3_refreeze import (
    ACTIVATION_COUNTERS,
    APR15_SCHEDULE_SHA256,
    EVIDENCE_CHECKPOINT_SHA,
)


ROOT = Path(__file__).parents[1]
ARTIFACTS = ROOT / "dayahead/artifacts/v16_3"


def _load(name: str) -> dict[str, object]:
    return json.loads((ARTIFACTS / name).read_text(encoding="utf-8"))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_active_authority_constants_are_exact() -> None:
    assert authority.AUTHORITY_ID == "V16_3_DA_AIDC_ICPS_AC_ANCHORED_FROZEN_D1_CONTROL"
    assert authority.CONTROL_SEMANTICS_ID == "D1_FROZEN_COMMON_NATIVE_CONTROL_STATE"
    assert authority.BETA_AIDC == 0.25
    assert authority.RHO_VALID == 0.10
    assert authority.TIME_LOCAL_GRID_LP_COUNT == 96
    assert authority.CONTROL_DIMENSION == 60
    assert authority.PHASE_CURRENT_DIMENSION == 383
    assert authority.ACTIVE_FOR_PRODUCTION_PLANNING is True


def test_phase_current_epigraph_is_explicit_and_lp_safe() -> None:
    source = inspect.getsource(authority.add_phase_current_epigraph)
    assert "lb=0.0" in source and "ub=1.0" in source
    assert "i_hat >= affine_current_pu" in source
    assert "line_objective >= i_hat" in source
    assert authority.physical_phase_current_pu(-0.25) == 0.0
    assert authority.physical_phase_current_pu(0.75) == 0.75


def test_refreeze_manifest_records_each_authority_artifact_sha() -> None:
    manifest = _load("V16_3_REFREEZE_MANIFEST.json")
    expected = {
        "V16_3_SCIENTIFIC_AUTHORITY.json",
        "V16_3_IMPLEMENTATION_BINDING.json",
        "V16_3_D1_AC_ANCHOR_AUTHORITY.json",
        "V16_3_COMMON_FROZEN_TAP_AUTHORITY.json",
        "V16_3_AC_ANCHORED_VOLTAGE_AUTHORITY.json",
        "V16_3_AC_ANCHORED_PHASE_CURRENT_AUTHORITY.json",
        "V16_3_TRUST_REGION_AUTHORITY.json",
        "V16_3_BETA025_CASESTUDY_PENETRATION_AUTHORITY.json",
        "V16_3_DUAL_FRESH_AC_VALIDATION_CONTRACT.json",
    }
    assert set(manifest["authority_artifact_sha256"]) == expected
    for name, expected_sha in manifest["authority_artifact_sha256"].items():
        assert _sha(ARTIFACTS / name) == expected_sha
    assert manifest["all_sections_1_through_14_pass"] is True


def test_implementation_binding_preserves_decomposition_and_thermal_separation() -> None:
    binding = _load("V16_3_IMPLEMENTATION_BINDING.json")
    assert binding["production_active"] is True
    assert binding["phase_current_rows"] == {
        "epigraph": "I_hat_pu >= I_aff_pu",
        "nonnegative": "I_hat_pu >= 0",
        "hard": "I_hat_pu <= 1",
        "line_objective": "lambda >= I_hat_pu",
        "integer_or_binary_variables_added": 0,
    }
    assert binding["decomposition"]["time_local_grid_LP_count"] == 96
    assert binding["decomposition"]["Pi_optimality_cuts"] == "PRESERVED"
    assert binding["decomposition"]["Farkas_feasibility_cuts"] == "PRESERVED"
    assert len(binding["separate_thermal_families"]) == 4


def test_apr15_certificate_is_regression_only_and_dual_ac_passes() -> None:
    contract = _load("V16_3_DUAL_FRESH_AC_VALIDATION_CONTRACT.json")
    regression = contract["Apr15_regression"]
    assert regression["schedule_sha256"] == APR15_SCHEDULE_SHA256
    assert regression["schedule_redesigned_or_resolved"] is False
    assert regression["terminal_service_parity_residual"] == 0.0
    assert regression["MESS_terminal_SOC_residual"] == 0.0
    assert regression["trust_region_respected_all_96_slots"] is True
    assert regression["primary"]["convergence_count"] == 96
    assert regression["secondary"]["convergence_count"] == 96
    assert regression["voltage_violations"] == 0
    assert regression["phase_current_violations"] == 0
    assert regression["transformer_kva_violations"] == 0


def test_activation_and_firewall_counters_are_exact() -> None:
    scientific = _load("V16_3_SCIENTIFIC_AUTHORITY.json")
    assert scientific["evidence_checkpoint_sha"] == EVIDENCE_CHECKPOINT_SHA
    assert scientific["classification"] == "V163_REFREEZE_PASS_AUTHORITY_ACTIVE"
    assert scientific["next_decision"] == "READY_FOR_FINAL_B0_B1_B2_B3_AND_DECOMPOSITION_RUN"
    assert scientific["activation_counters"] == ACTIVATION_COUNTERS
    assert ACTIVATION_COUNTERS["scientific_authority_changes"] == 1
    assert ACTIVATION_COUNTERS["production_V16_3_activations"] == 1
    for key, value in ACTIVATION_COUNTERS.items():
        if key not in {"scientific_authority_changes", "production_V16_3_activations"}:
            assert value == 0

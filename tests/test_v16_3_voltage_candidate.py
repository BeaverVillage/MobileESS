import json
from pathlib import Path

import pytest

from dayahead.authority import sha256_file
from dayahead.v16_3_voltage_candidate import (
    AcAnchoredAffineVoltageSlice,
    AffineVoltageGridLPFactory,
    FrozenD1ControlState,
    make_96_affine_factories,
)


ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "dayahead" / "artifacts" / "v16_3_candidate"
SOURCE = Path(r"C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\tmp\c12_exact_sources_repo_cleanup\c12_exact_sources\v2038_parent\Conversation3_Exact_AC_Remediation_Sweep_From_Conversation1_V2038\reference")
NATIVE_SHA = "cc7c2f153ca1e57f9fb5cad8b3c3e1ecbcb20c5db59ca4d65539411a50525969"


def _slice(time_index: int = 0, anchor: float = 1.0) -> AcAnchoredAffineVoltageSlice:
    return AcAnchoredAffineVoltageSlice(
        time_index=time_index,
        node_names=("n.1",),
        control_names=("aidc_load_kw[AIDC01]", "mess_q_kvar[IDC01]"),
        anchor_v_squared=(anchor,),
        sensitivity_by_control={"aidc_load_kw[AIDC01]": (-1e-4,), "mess_q_kvar[IDC01]": (2e-4,)},
        anchor_control={"aidc_load_kw[AIDC01]": 100.0, "mess_q_kvar[IDC01]": 0.0},
        regulator_taps={"reg1a": 1.025},
        capacitor_states={"c83": (1,)},
    )


def test_affine_candidate_is_deterministic_and_contains_no_discrete_control() -> None:
    first = _slice()
    second = _slice()
    assert first.fingerprint() == second.fingerprint()
    assert set(first.variable_types.values()) == {"CONTINUOUS_MASTER_INPUT"}
    master = {"aidc_load_kw[AIDC01]": 110.0, "mess_q_kvar[IDC01]": 5.0}
    assert first.evaluate(master)["n.1"] == pytest.approx(1.0)
    rows = first.master_dependent_rows()
    assert len(rows) == 2
    for row in rows:
        shifted = dict(master, **{"aidc_load_kw[AIDC01]": 110.001})
        derivative = (row.rhs(shifted) - row.rhs(master)) / 0.001
        assert derivative == pytest.approx(row.master_coefficients["aidc_load_kw[AIDC01]"], abs=1e-10)


def test_time_axis_and_common_exogenous_control_contract() -> None:
    taps = tuple({name: 1.0 for name in ("reg1a", "reg2a", "reg3a", "reg3c", "reg4a", "reg4b", "reg4c")} for _ in range(96))
    caps = tuple({name: (1,) for name in ("c83", "c88a", "c90b", "c92c")} for _ in range(96))
    control = FrozenD1ControlState("2025-04-17", taps, caps)
    assert len(control.fingerprint()) == 64
    factories = make_96_affine_factories(tuple(_slice(index) for index in range(96)))
    assert len(factories) == 96
    assert all(row.integer_variable_count == row.binary_variable_count == 0 for row in factories)
    assert all(row.opendss_call_count == 0 for row in factories)


def test_pi_and_farkas_interfaces_remain_valid() -> None:
    pytest.importorskip("gurobipy")
    feasible = AffineVoltageGridLPFactory(_slice()).solve({"aidc_load_kw[AIDC01]": 100.0, "mess_q_kvar[IDC01]": 0.0})
    assert feasible.feasible
    assert feasible.optimality_cut is not None
    assert feasible.optimality_cut.evaluate({"aidc_load_kw[AIDC01]": 101.0, "mess_q_kvar[IDC01]": 0.0}) <= 1e-9
    infeasible = AffineVoltageGridLPFactory(_slice(anchor=0.80)).solve({"aidc_load_kw[AIDC01]": 100.0, "mess_q_kvar[IDC01]": 0.0})
    assert not infeasible.feasible
    assert infeasible.farkas_by_row
    assert infeasible.feasibility_cut is not None


def test_native_sha_and_legacy_sidecar_firewall() -> None:
    assert sha256_file(SOURCE / "opendss_assets" / "IEEE123Master.dss") == NATIVE_SHA
    runner = (ROOT / "dayahead" / "run_v16_3_voltage_candidate.py").read_text(encoding="utf-8").lower()
    assert '"v13/' not in runner and '"v13\\' not in runner
    assert "sidecar.json" not in runner
    assert "common-control" not in runner
    assert "emergency control" not in runner
    assert "post-hoc tap" not in runner


def test_candidate_artifacts_when_materialized() -> None:
    review_path = ARTIFACTS / "V16_3_PLANNING_MODEL_CANDIDATE_REVIEW.json"
    if not review_path.exists(): pytest.skip("candidate runner has not materialized artifacts yet")
    review = json.loads(review_path.read_text(encoding="utf-8"))
    anchor = json.loads((ARTIFACTS / "V16_3_D1_AC_ANCHOR_CONTRACT_CANDIDATE.json").read_text(encoding="utf-8"))
    sensitivity = json.loads((ARTIFACTS / "V16_3_AC_ANCHORED_VOLTAGE_SENSITIVITY_CONTRACT_CANDIDATE.json").read_text(encoding="utf-8"))
    assert anchor["anchor_B0_B1_B2_B3_identical"] is True
    assert anchor["anchor_case_fingerprints"]["B0"] == anchor["anchor_case_fingerprints"]["B1"] == anchor["anchor_case_fingerprints"]["B2"] == anchor["anchor_case_fingerprints"]["B3"]
    assert sensitivity["affine"] is True
    assert sensitivity["nonlinear_terms"] == sensitivity["integer_or_binary_control_variables"] == 0
    assert sensitivity["time_local_slice_count"] == 96
    assert sensitivity["thermal_model_replaced"] is False
    for key in (
        "scientific_authority_changes", "production_V16_3_activations", "native_ieee123_changes",
        "native_regulator_setting_changes", "tap_cooptimization_variables_added",
        "OpenDSS_calls_inside_Benders", "legacy_v13_control_sidecar_loads", "AIDC_raw_data_changes",
        "beta_production_changes", "alpha_grid_changes", "native_feeder_rating_changes", "u080_changes",
        "voltage_limit_changes", "kappa_changes", "PUE_changes", "PF_changes",
        "may_scientific_loader_access_count", "june_scientific_loader_access_count",
        "G12_final_calls", "G13_calls", "G14_calls", "C12_calls",
    ):
        assert review[key] == 0
    assert review["beta_candidate_recommended"] is None

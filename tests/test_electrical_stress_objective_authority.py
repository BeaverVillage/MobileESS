from pathlib import Path

import pytest

from pfr.methods import ElectricalStressMethod, ExperimentAuthority, MethodFactory
from pfr.retained_h54 import (
    RetainedH54JointPlanner,
    _FORMULATION_DEFAULTS,
    _RuntimeZeroFixedRackEnvironment,
)
from pfr.runtime import (
    CausalExperimentFrame,
    MESS_CANONICAL_STAGING,
    MESS_IDS,
    MutableMethodState,
    RuntimeContractError,
    _build_slow_plan,
)


REPO = Path(__file__).resolve().parents[1]


def test_runtime_reference_grid_cannot_read_pilot_fixed_rack_baseline() -> None:
    class PilotEnvironment:
        marker = "retained"

        def current_fixed(self, _issue, _rack):
            raise AssertionError("pilot timestamp lookup must not occur")

    environment = _RuntimeZeroFixedRackEnvironment(PilotEnvironment())
    assert environment.current_fixed("2025-01-04", "IDC01_LP01") == (0.0, 0.0)
    assert environment.marker == "retained"


def test_retained_h54_planner_uses_only_frozen_paper_facing_hierarchy() -> None:
    source = (REPO / "science" / "main.py").read_text(encoding="utf-8")
    assert 'm.setObjectiveN(stress_worst,0,priority=3' in source
    assert 'm.setObjectiveN(obj_exposure,1,priority=2' in source
    assert 'm.setObjectiveN(obj_actuation,2,priority=1' in source
    assert 'price_used_by_optimizer":False' in source
    assert "N_modality" not in source
    for field in (
        "predicted_voltage_stress_max",
        "predicted_line_stress_max",
        "predicted_transformer_stress_max",
        "predicted_worst_stress_type",
        "predicted_worst_element_id",
        "predicted_worst_phase",
    ):
        assert f'"{field}"' in source


def test_runtime_executes_joint_plan_setpoints_without_price_dispatch() -> None:
    source = (REPO / "pfr" / "runtime.py").read_text(encoding="utf-8")
    nominal_start = source.index("def _nominal_mess_dispatch(")
    nominal_end = source.index("def _nominal_control(", nominal_start)
    nominal_dispatch = source[nominal_start:nominal_end]
    assert "current_price" not in nominal_dispatch
    assert "horizon_price" not in nominal_dispatch
    assert "coarse_charging_kw" in nominal_dispatch
    assert "coarse_discharging_kw" in nominal_dispatch


def test_legacy_route_score_cannot_masquerade_as_scientific_objective() -> None:
    source = (REPO / "pfr" / "runtime.py").read_text(encoding="utf-8")
    assert '"scientific_decision_authority": False' in source
    assert '"replacement_required": "ELECTRICAL_STRESS_OBJECTIVE_V1_H54_JOINT_PLANNER"' in source


def test_retained_h54_model_uses_capability_mask_not_separate_objectives() -> None:
    source = (REPO / "science" / "main.py").read_text(encoding="utf-8")
    assert "capability_mask=None" in source
    assert 'if not _cap["spatial_compute"]' in source
    assert 'if not _cap["temporal_compute"]' in source
    assert 'if not _cap["mess_mobility"]' in source
    assert 'if not _cap["mess_dispatch"]' in source


def test_runtime_enables_exact_sparse_cuts_and_causal_rolling_start() -> None:
    assert _FORMULATION_DEFAULTS[
        "MOBILEESS_POST15_SKIP_REDUNDANT_DENSE_B4_CUTS"
    ] == "1"
    assert _FORMULATION_DEFAULTS["MOBILEESS_OPT_HORIZON_STEPS"] == "54"
    assert _FORMULATION_DEFAULTS["MOBILEESS_R25V_CAUSAL_ROLLING_MIPSTART"] == "1"
    assert _FORMULATION_DEFAULTS["MOBILEESS_R26_MULTIRES_MOBILITY"] == "1"
    assert _FORMULATION_DEFAULTS[
        "MOBILEESS_R26_SINGLE_RELOCATION_TRUST_REGION"
    ] == "1"
    assert _FORMULATION_DEFAULTS["MOBILEESS_GUROBI_PRIMARY_STRESS_MIPGAP"] == "0.03"
    assert _FORMULATION_DEFAULTS["MOBILEESS_GUROBI_EXPOSURE_MIPGAP"] == "0.03"
    assert _FORMULATION_DEFAULTS["MOBILEESS_GUROBI_TIMELIMIT"] == "300"
    adapter = (REPO / "pfr" / "retained_h54.py").read_text(encoding="utf-8")
    science = (REPO / "science" / "main.py").read_text(encoding="utf-8")
    assert "rolling_warmstart=self._rolling_warmstarts.get(method_key)" in adapter
    assert 'solution["rolling_warmstart_payload"]' in adapter
    assert '"source":"causal no-job/no-debt all-STAY incumbent"' in science
    assert '_r14_quality={"pass":False,"reason":"NO_INCUMBENT"' in science
    assert '"all_grid_SOC_dispatch_workload_stress_steps_retained":True' in science
    assert 'float(_model_gap)<=float(_current_gap_target)+1e-12' in science
    assert "elif int(issue)==113 and not _runtime_adapter_mode" in science
    assert "if _runtime_adapter_mode or int(issue)>113" in science
    assert '"maximum_new_relocations_per_mess":1' in science
    assert "_current_multiobj_pass>=2" in science


def test_legacy_no_demand_stay_decision_is_only_miqcp_domain_screening() -> None:
    authority = ExperimentAuthority(*(format(index, "064x") for index in range(1, 8)))
    config = MethodFactory(authority).create_electrical_stress(
        ElectricalStressMethod.B07
    )
    state = MutableMethodState(
        issue=0,
        pre_state_sha256="a" * 64,
        mess_energy_kwh={mid: 760.0 for mid in MESS_IDS},
        mess_location=dict(MESS_CANONICAL_STAGING),
    )
    planner = object.__new__(RetainedH54JointPlanner)
    planner.legacy_causal_screening = True
    homes, reason = planner._legacy_fixed_location_screen(state, config)
    assert homes == dict(MESS_CANONICAL_STAGING)
    assert reason == "LEGACY_CAUSAL_NO_ACTIVE_DESTINATION_ALL_CANONICAL_STAY"

    state.mess_location["MESS01"] = "IDC01"
    homes, reason = planner._legacy_fixed_location_screen(state, config)
    assert homes is None
    assert reason == "ACTIVE_WORKLOAD_OR_AWAY_MESS_REQUIRES_ROUTE_DOMAIN"


def test_online_runtime_uses_persistent_bounded_milp_and_keeps_full_oracle_offline() -> None:
    source = (REPO / "pfr" / "tools" / "run_pfr_matrix.py").read_text(
        encoding="utf-8"
    )
    assert "PersistentBoundedMilpPlanner" in source
    assert 'default="online-bounded"' in source
    assert 'choices=("online-bounded", "full-miqcp-oracle")' in source
    assert "Full H54 MIQCP is an offline sampled-state oracle" in source
    assert '"PFR_EXPERIMENTAL_LEGACY_CAUSAL_SCREENING", "0"' in source
    contract = (REPO / "pfr" / "contracts" / "ELECTRICAL_STRESS_OBJECTIVE_V1.json").read_text(
        encoding="utf-8"
    )
    assert "disabled by default" in contract
    assert "MIP-start and branching guidance" in contract


def test_hierarchical_move_blocked_mpc_preserves_science_and_exact_recourse() -> None:
    source = (REPO / "pfr" / "persistent_bounded_milp.py").read_text(
        encoding="utf-8"
    )
    contract = (
        REPO
        / "pfr"
        / "contracts"
        / "HIERARCHICAL_MOVE_BLOCKED_MIXED_INTEGER_MPC_V1.json"
    ).read_text(encoding="utf-8")
    assert "OBJECTIVE_AUTHORITY" in source
    assert "self.debt[(mid, self.h)] == 0.0" in source
    assert "route departure reserve" not in source  # encoded as dep_reserve rows
    assert "self.dep_reserve" in source
    assert 'model_role="slow_master"' in source
    assert 'model_role="exact_recourse"' in source
    assert "self._add_initial_norm_cuts()" in source
    assert "self._add_exact_norm_constraints()" in source
    assert "slow_master_skipped_exact_forced_domain" in source
    assert "maximum_exact_norm_residual" in source
    assert "future_actual_used" in source
    assert "price_used_by_optimizer" in source
    assert 'PFR_ONLINE_MILP_WALL_BUDGET_SECONDS", "30.0"' in source
    assert 'self.numeric_focus = 0 if model_role == "slow_master" else 2' in source
    assert "self.model.Params.NumericFocus = self.numeric_focus" in source
    assert "PFR_GUROBI_NUMERIC_FOCUS" not in source
    assert "PFR_GUROBI_CROSSOVER" not in source
    assert "PFR_GUROBI_MULTIOBJ_PRE" not in source
    assert "PFR_SEQUENTIAL" not in source
    assert "condensed" not in source.lower()
    assert "persistent bounded MILP" in contract
    assert "persistent exact continuous convex QCP" in contract
    assert "Full H54 MIQCP" in contract
    assert "sampled-state offline oracle only" in contract
    assert "condensed QCP diagnostic" in contract
    assert "watchdog_is_not_speed_evidence" in contract
    assert "no paired speed improvement is removed" in contract

    runner_source = (REPO / "pfr" / "tools" / "run_pfr_matrix.py").read_text(
        encoding="utf-8"
    )
    assert "online_solver_contract_sha256" in runner_source
    assert "HIERARCHICAL_MOVE_BLOCKED_MIXED_INTEGER_MPC_V1.json" in runner_source


def test_new_stress_campaign_fails_closed_without_retained_h54_planner() -> None:
    authority = ExperimentAuthority(*(format(index, "064x") for index in range(1, 8)))
    config = MethodFactory(authority).create_electrical_stress(
        ElectricalStressMethod.B00
    )
    state = MutableMethodState(
        issue=100,
        pre_state_sha256="a" * 64,
        mess_energy_kwh={mid: 760.0 for mid in MESS_IDS},
        mess_location=dict(MESS_CANONICAL_STAGING),
    )
    frame = CausalExperimentFrame(
        issue=100,
        current_price_aud_per_mwh=0.0,
        horizon_price_median_aud_per_mwh=0.0,
        q50_background_p_kw=0.0,
        q50_background_q_kvar=0.0,
        arrivals=(),
        exogenous_sha256="b" * 64,
    )
    with pytest.raises(RuntimeContractError, match="retained H54 joint planner"):
        _build_slow_plan(state, config, frame, None, 54)

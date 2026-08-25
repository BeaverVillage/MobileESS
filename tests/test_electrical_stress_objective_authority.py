from pathlib import Path

import pytest

from pfr.methods import ElectricalStressMethod, ExperimentAuthority, MethodFactory
from pfr.retained_h54 import _RuntimeZeroFixedRackEnvironment
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

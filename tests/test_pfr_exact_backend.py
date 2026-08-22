from pfr.tools.run_pfr_matrix import ExactOpenDssBackend


class FakeExact:
    def __init__(self):
        self.states = []

    def solve_step(self, paths, issue, state):
        self.states.append(dict(state))
        robust = "background_p_kw" in state
        passed = not robust
        return {
            "voltage_violation_count": 1 if robust else 0,
            "line_violation_count": 0,
            "transformer_kva_violation_count": 0,
            "transformer_current_violation_count": 0,
            "root_sign_pass": True,
            "hard_constraint_pass": passed,
            "voltage_min_pu": 0.94 if robust else 0.98,
            "voltage_max_pu": 1.02,
            "line_max_loading_pu": 0.5,
            "transformer_max_kva_loading_pu": 0.5,
            "transformer_max_current_loading_pu": 0.5,
            "root_import_p_kw": 100.0,
            "native_grid_control_authority": "TEST_COMMON_CONTROL",
            "native_capacitor_states": {"c83": [0]},
        }


def test_robust_grid_forecast_is_diagnostic_not_realized_h0_commit_gate() -> None:
    backend = ExactOpenDssBackend(FakeExact(), {})
    robust = ((1.0, 1.0, 1.0),)

    commit = backend.verify_fresh(
        issue=0,
        facility_p_kw=(0.0,),
        facility_q_kvar=(0.0,),
        mess_location=("STA09",),
        mess_p_kw=(0.0,),
        mess_q_kvar=(0.0,),
        mess_in_transit=(False,),
        robust_background_p_kw=robust,
        robust_background_q_kvar=robust,
        robust_pv_available_kw=robust,
    )

    assert commit.exact.passed is True
    assert commit.exact.minimum_voltage_pu == 0.98
    assert commit.raw_metrics["robust_grid_hard_constraint_pass"] is False
    assert commit.raw_metrics["robust_grid_role"] == (
        "CAUSAL_PLAN_VALIDITY_DIAGNOSTIC_NOT_H0_COMMIT_GATE"
    )


def test_native_transition_is_selected_once_then_fixed_for_verification() -> None:
    exact = FakeExact()
    backend = ExactOpenDssBackend(exact, {})
    common = dict(
        issue=4,
        facility_p_kw=(0.0,),
        facility_q_kvar=(0.0,),
        mess_location=("STA09",),
        mess_p_kw=(0.0,),
        mess_q_kvar=(0.0,),
        mess_in_transit=(False,),
    )

    decision = backend.select_native_control(
        **common,
        previous_capacitor_states={"c83": (1,)},
        locked_capacitors=(),
    )
    backend.verify_fresh(
        **common,
        robust_background_p_kw=(),
        robust_background_q_kvar=(),
        robust_pv_available_kw=(),
        native_capacitor_states=decision.states,
    )

    assert decision.states == {"c83": (0,)}
    assert exact.states[0]["native_grid_control_mode"] == "EVALUATE_TRANSITION"
    assert exact.states[1]["native_grid_control_mode"] == "FIXED_STATE_VERIFICATION"
    assert exact.states[1]["native_capacitor_initial_states"] == {"c83": [0]}

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
        previous_regulator_taps={},
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


class FeederWideOvervoltageExact:
    """Local C83 transition misses a remote phase overvoltage."""

    def __init__(self) -> None:
        self.states = []

    def solve_step(self, paths, issue, state):
        frozen = state.get("native_grid_control_mode") == "FIXED_STATE_VERIFICATION"
        capacitor_states = {
            key: list(value)
            for key, value in state.get(
                "native_capacitor_initial_states",
                {"c83": [0], "c88a": [1]},
            ).items()
        }
        if not frozen:
            # Local monitors switch C83 only; C88a leaves a remote phase high.
            capacitor_states = {"c83": [0], "c88a": [1]}
        safe = capacitor_states == {"c83": [0], "c88a": [0]}
        self.states.append(dict(state))
        return {
            "voltage_violation_count": 0 if safe else 1,
            "line_violation_count": 0,
            "transformer_kva_violation_count": 0,
            "transformer_current_violation_count": 0,
            "root_sign_pass": True,
            "hard_constraint_pass": safe,
            "voltage_min_pu": 0.98,
            "voltage_max_pu": 1.045 if safe else 1.0505,
            "line_max_loading_pu": 0.6,
            "transformer_max_kva_loading_pu": 0.5,
            "transformer_max_current_loading_pu": 0.55,
            "root_import_p_kw": 100.0,
            "native_grid_control_authority": "TEST_COMMON_CONTROL",
            "native_capacitor_states": capacitor_states,
        }


def test_native_control_coordinates_existing_assets_against_global_envelope() -> None:
    exact = FeederWideOvervoltageExact()
    backend = ExactOpenDssBackend(exact, {})

    decision = backend.select_native_control(
        issue=209,
        facility_p_kw=(0.0,),
        facility_q_kvar=(0.0,),
        mess_location=("STA09",),
        mess_p_kw=(0.0,),
        mess_q_kvar=(0.0,),
        mess_in_transit=(False,),
        previous_capacitor_states={"c83": (0,), "c88a": (1,)},
        previous_regulator_taps={},
        locked_capacitors=(),
    )

    assert decision.states == {"c83": (0,), "c88a": (0,)}
    assert decision.raw_metrics["global_guard_search_triggered"] is True
    assert decision.raw_metrics["selection_hard_constraint_pass"] is True
    assert decision.raw_metrics["global_guard_candidates_evaluated"] == 4


def test_native_global_guard_respects_chronological_dwell_lock() -> None:
    exact = FeederWideOvervoltageExact()
    backend = ExactOpenDssBackend(exact, {})

    decision = backend.select_native_control(
        issue=209,
        facility_p_kw=(0.0,),
        facility_q_kvar=(0.0,),
        mess_location=("STA09",),
        mess_p_kw=(0.0,),
        mess_q_kvar=(0.0,),
        mess_in_transit=(False,),
        previous_capacitor_states={"c83": (0,), "c88a": (1,)},
        previous_regulator_taps={},
        locked_capacitors=("c88a",),
    )

    assert decision.states["c88a"] == (1,)
    assert decision.raw_metrics["selection_hard_constraint_pass"] is False


class RegulatorStateCoherenceExact:
    """A fixed capacitor candidate is safe only with the local transition tap."""

    def solve_step(self, paths, issue, state):
        del paths, issue
        frozen = state.get("native_grid_control_mode") == "FIXED_STATE_VERIFICATION"
        tap = int(
            state.get("native_regulator_initial_tap_numbers", {}).get(
                "creg4a", 5
            )
        )
        if not frozen:
            tap = 5
        safe = frozen and tap == 4
        return {
            "voltage_violation_count": 0 if safe else 1,
            "line_violation_count": 0,
            "transformer_kva_violation_count": 0,
            "transformer_current_violation_count": 0,
            "root_sign_pass": True,
            "hard_constraint_pass": safe,
            "voltage_min_pu": 0.98,
            "voltage_max_pu": 1.049 if safe else 1.051,
            "line_max_loading_pu": 0.6,
            "transformer_max_kva_loading_pu": 0.5,
            "transformer_max_current_loading_pu": 0.55,
            "root_import_p_kw": 100.0,
            "native_grid_control_authority": "TEST_COMMON_CONTROL",
            "native_capacitor_states": {"c83": [1]},
            "native_regulator_tap_numbers": {"creg4a": tap},
        }


def test_native_global_guard_preserves_and_coordinates_regulator_state() -> None:
    backend = ExactOpenDssBackend(RegulatorStateCoherenceExact(), {})

    decision = backend.select_native_control(
        issue=786,
        facility_p_kw=(0.0,),
        facility_q_kvar=(0.0,),
        mess_location=("STA09",),
        mess_p_kw=(0.0,),
        mess_q_kvar=(0.0,),
        mess_in_transit=(False,),
        previous_capacitor_states={"c83": (1,)},
        previous_regulator_taps={"creg4a": 5},
        locked_capacitors=(),
    )

    assert decision.states == {"c83": (1,)}
    assert decision.regulator_taps == {"creg4a": 4}
    assert decision.raw_metrics["selection_hard_constraint_pass"] is True
    assert any(
        row["regulator_taps"] == {"creg4a": 4}
        for row in decision.raw_metrics["global_guard_candidate_evidence"]
    )


class CoupledCapacitorRegulatorExact:
    """The initially worse capacitor state is feasible after two tap moves."""

    def solve_step(self, paths, issue, state):
        del paths, issue
        frozen = state.get("native_grid_control_mode") == "FIXED_STATE_VERIFICATION"
        capacitor = int(
            state.get("native_capacitor_initial_states", {}).get("c83", [0])[0]
        )
        tap = int(
            state.get("native_regulator_initial_tap_numbers", {}).get(
                "creg1a", 5
            )
        )
        if not frozen:
            capacitor, tap = 0, 5
        safe = frozen and capacitor == 1 and tap == 3
        if capacitor == 0:
            transformer = 1.01
            vmax = 1.04
        else:
            transformer = 0.96
            vmax = 1.04 + 0.006 * (tap - 3)
        return {
            "voltage_violation_count": 0 if vmax <= 1.05 else 1,
            "line_violation_count": 0,
            "transformer_kva_violation_count": 0,
            "transformer_current_violation_count": 0 if transformer <= 1.0 else 1,
            "root_sign_pass": True,
            "hard_constraint_pass": safe,
            "voltage_min_pu": 0.98,
            "voltage_max_pu": vmax,
            "line_max_loading_pu": 0.6,
            "transformer_max_kva_loading_pu": transformer,
            "transformer_max_current_loading_pu": transformer,
            "root_import_p_kw": 100.0,
            "native_grid_control_authority": "TEST_COMMON_CONTROL",
            "native_capacitor_states": {"c83": [capacitor]},
            "native_regulator_tap_numbers": {"creg1a": tap},
        }


def test_native_global_guard_searches_capacitor_and_regulator_jointly() -> None:
    backend = ExactOpenDssBackend(CoupledCapacitorRegulatorExact(), {})

    decision = backend.select_native_control(
        issue=1057,
        facility_p_kw=(0.0,),
        facility_q_kvar=(0.0,),
        mess_location=("STA09",),
        mess_p_kw=(0.0,),
        mess_q_kvar=(0.0,),
        mess_in_transit=(False,),
        previous_capacitor_states={"c83": (0,)},
        previous_regulator_taps={"creg1a": 5},
        locked_capacitors=(),
    )

    assert decision.states == {"c83": (1,)}
    assert decision.regulator_taps == {"creg1a": 3}
    assert decision.raw_metrics["selection_hard_constraint_pass"] is True
    assert decision.raw_metrics["global_guard_joint_discrete_search"] == {
        "algorithm": (
            "FRESH_EXACT_DUAL_ANCHOR_GLOBAL_ONLINE_"
            "CAPACITOR_REGULATOR_BEAM_SEARCH"
        ),
        "search_profile": "ONLINE",
        "tap_anchors": [
            "LOCAL_TRANSITION",
            "CHRONOLOGICAL_PRE_TRANSITION",
        ],
        "beam_width": 4,
        "beam_width_per_capacitor_state": None,
        "frontier_policy": "SCALAR_FEASIBILITY_BEAM",
        "frontier_width_per_capacitor_state": None,
        "voltage_tradeoff_bin_pu": None,
        "maximum_tap_depth": 16,
        "single_tap_change_per_search_edge": True,
        "integer_trust_region_radius": None,
        "maximum_relinearizations": None,
    }


class CascadedRegulatorTradeoffExact:
    """A safe cascaded state requires preserving a temporary low-voltage bridge."""

    def solve_step(self, paths, issue, state):
        del paths, issue
        frozen = state.get("native_grid_control_mode") == "FIXED_STATE_VERIFICATION"
        taps = state.get(
            "native_regulator_initial_tap_numbers",
            {"creg1a": 0, "creg4a": 0},
        )
        upstream = int(taps.get("creg1a", 0))
        downstream = int(taps.get("creg4a", 0))
        if not frozen:
            upstream = downstream = 0
        vmin = 0.96 + 0.01 * upstream + 0.01 * downstream
        transformer = 1.02 + 0.01 * upstream + 0.001 * downstream
        safe = vmin >= 0.95 and transformer <= 1.0
        return {
            "voltage_violation_count": 0 if vmin >= 0.95 else 1,
            "line_violation_count": 0,
            "transformer_kva_violation_count": 0,
            "transformer_current_violation_count": 0 if transformer <= 1.0 else 1,
            "root_sign_pass": True,
            "hard_constraint_pass": safe,
            "voltage_min_pu": vmin,
            "voltage_max_pu": 1.04,
            "line_max_loading_pu": 0.6,
            "transformer_max_kva_loading_pu": transformer,
            "transformer_max_current_loading_pu": transformer,
            "root_import_p_kw": 100.0,
            "native_grid_control_authority": "TEST_COMMON_CONTROL",
            "native_capacitor_states": {"c83": [0]},
            "native_regulator_tap_numbers": {
                "creg1a": upstream,
                "creg4a": downstream,
            },
        }


def test_deep_native_trust_region_solves_cascaded_voltage_thermal_tradeoff() -> None:
    backend = ExactOpenDssBackend(CascadedRegulatorTradeoffExact(), {})

    decision = backend.select_native_control_deep(
        issue=1330,
        facility_p_kw=(0.0,),
        facility_q_kvar=(0.0,),
        mess_location=("STA09",),
        mess_p_kw=(0.0,),
        mess_q_kvar=(0.0,),
        mess_in_transit=(False,),
        previous_capacitor_states={"c83": (0,)},
        previous_regulator_taps={"creg1a": 0, "creg4a": 0},
        locked_capacitors=(),
    )

    assert decision.raw_metrics["selection_hard_constraint_pass"] is True
    assert decision.regulator_taps["creg1a"] < 0
    assert decision.regulator_taps["creg4a"] > 0
    assert len(decision.raw_metrics["global_guard_candidate_evidence"]) <= 20
    assert decision.raw_metrics["global_guard_candidates_evaluated"] <= 50
    assert decision.raw_metrics["global_guard_joint_discrete_search"][
        "frontier_policy"
    ] == "FINITE_DIFFERENCE_INTEGER_TRUST_REGION"


class PreviousTapAnchorExact:
    """A multi-tap local transition is unsafe; the prior tap anchor is safe."""

    def solve_step(self, paths, issue, state):
        del paths, issue
        frozen = state.get("native_grid_control_mode") == "FIXED_STATE_VERIFICATION"
        capacitor = int(
            state.get("native_capacitor_initial_states", {}).get("c83", [0])[0]
        )
        tap = int(
            state.get("native_regulator_initial_tap_numbers", {}).get(
                "creg1a", 0
            )
        )
        if not frozen:
            capacitor, tap = 0, 9
        safe = frozen and capacitor == 1 and tap == 0
        transformer = 0.99 if safe else 1.02
        return {
            "voltage_violation_count": 0,
            "line_violation_count": 0,
            "transformer_kva_violation_count": 0,
            "transformer_current_violation_count": 0 if safe else 1,
            "root_sign_pass": True,
            "hard_constraint_pass": safe,
            "voltage_min_pu": 0.98,
            "voltage_max_pu": 1.04,
            "line_max_loading_pu": 0.6,
            "transformer_max_kva_loading_pu": transformer,
            "transformer_max_current_loading_pu": transformer,
            "root_import_p_kw": 100.0,
            "native_grid_control_authority": "TEST_COMMON_CONTROL",
            "native_capacitor_states": {"c83": [capacitor]},
            "native_regulator_tap_numbers": {"creg1a": tap},
        }


def test_native_global_guard_includes_chronological_previous_tap_anchor() -> None:
    backend = ExactOpenDssBackend(PreviousTapAnchorExact(), {})

    decision = backend.select_native_control(
        issue=1058,
        facility_p_kw=(0.0,),
        facility_q_kvar=(0.0,),
        mess_location=("STA09",),
        mess_p_kw=(0.0,),
        mess_q_kvar=(0.0,),
        mess_in_transit=(False,),
        previous_capacitor_states={"c83": (0,)},
        previous_regulator_taps={"creg1a": 0},
        locked_capacitors=(),
    )

    assert decision.states == {"c83": (1,)}
    assert decision.regulator_taps == {"creg1a": 0}
    assert decision.raw_metrics["selection_hard_constraint_pass"] is True

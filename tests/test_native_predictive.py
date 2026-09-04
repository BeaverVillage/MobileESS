import pytest

from pfr.native_oracle import OracleNativeState, find_positive_trajectory
from pfr.native_predictive import (
    PredictivePathScore,
    intermediate_capacitor_states,
    normalized_hard_violation,
)
from pfr.runtime import CausalExperimentFrame, RuntimeContractError


def _metrics(*, passed: bool, transformer: float = 0.8):
    return {
        "hard_constraint_pass": passed,
        "voltage_min_pu": 0.98,
        "voltage_max_pu": 1.02,
        "line_max_loading_pu": 0.7,
        "transformer_max_loading_pu": transformer,
    }


def test_predictive_score_prioritizes_violation_steps_then_severity() -> None:
    safe = _metrics(passed=True)
    overload = _metrics(passed=False, transformer=1.01)

    score = PredictivePathScore.from_metrics((safe, overload, overload))

    assert normalized_hard_violation(overload) > 0.0
    assert score.violation_steps == 2
    assert score.maximum_violation > 0.0
    assert score.cumulative_violation == 2.0 * score.maximum_violation


def test_intermediate_capacitor_states_enumerates_transition_subsets() -> None:
    candidates = intermediate_capacitor_states(
        {"c83": (1,), "c88a": (1,), "c90": (0,)},
        {"c83": (0,), "c88a": (0,), "c90": (0,)},
        locked=("c90",),
    )

    assert len(candidates) == 4
    assert {tuple(row[name] for name in sorted(row)) for row in candidates} == {
        ((0,), (0,), (0,)),
        ((0,), (1,), (0,)),
        ((1,), (0,), (0,)),
        ((1,), (1,), (0,)),
    }


def test_offline_oracle_finds_positive_path_and_labels_miss_non_certifying() -> None:
    initial = OracleNativeState.create(
        capacitor_states={"c83": (0,)},
        capacitor_dwell_remaining={"c83": 0},
        regulator_taps={"creg1a": 0},
    )
    prepared = OracleNativeState.create(
        capacitor_states={"c83": (1,)},
        capacitor_dwell_remaining={"c83": 6},
        regulator_taps={"creg1a": 0},
    )

    positive = find_positive_trajectory(
        initial=initial,
        steps=1,
        successors=lambda step, state: (prepared,),
        safe=lambda step, state: state == initial or state == prepared,
        maximum_frontier_states=4,
    )
    miss = find_positive_trajectory(
        initial=initial,
        steps=1,
        successors=lambda step, state: (prepared,),
        safe=lambda step, state: state == initial,
        maximum_frontier_states=4,
    )

    assert positive.status == "POSITIVE_SAFE_TRAJECTORY_FOUND"
    assert positive.path == (initial, prepared)
    assert miss.status == "NO_PATH_FOUND_WITHIN_BOUND"
    assert miss.negative_result_is_infeasibility_certificate is False


def test_causal_frame_requires_complete_twelve_step_native_forecast() -> None:
    profile = tuple((0.0, 0.0, 0.0) for _ in range(131))
    short_forecast = (profile,) * 11
    frame = CausalExperimentFrame(
        9708,
        10.0,
        10.0,
        1000.0,
        100.0,
        (),
        "f" * 64,
        native_forecast_background_p_kw=short_forecast,
        native_forecast_background_q_kvar=short_forecast,
        native_forecast_pv_available_kw=short_forecast,
    )

    with pytest.raises(RuntimeContractError, match="12x131x3"):
        frame.validate()

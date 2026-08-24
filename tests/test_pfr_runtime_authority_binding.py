from types import SimpleNamespace

import pytest

from pfr.mobility_execution import MobilityExecutionRealization
from pfr.runtime import (
    CausalExperimentFrame,
    MESS_IDS,
    MobilityRouteForecast,
    MutableMethodState,
    RuntimeContractError,
    _mobility_energy_profile,
    _optimize_mess_routes,
    _pareto_routes,
    _start_planned_routes,
)
from pfr.slow_fast import SlowDiscretePlan


def _route(rank: int, eta: float, energy: float) -> MobilityRouteForecast:
    return MobilityRouteForecast(
        source_service_id="STA09",
        destination_service_id="IDC01",
        od_index=1,
        rank=rank,
        q50_eta_seconds=eta,
        safe_eta_seconds=eta,
        q50_energy_kwh=energy,
        safe_energy_kwh=energy,
    )


def test_duration_energy_pareto_prunes_dominated_k3_route() -> None:
    routes = (_route(1, 600.0, 20.0), _route(2, 900.0, 30.0), _route(3, 500.0, 35.0))

    kept = _pareto_routes(routes, safe=True)

    assert [route.rank for route in kept] == [1, 3]


def test_physics_profile_conserves_selected_safe_energy() -> None:
    route = _route(1, 600.0, 24.0)

    profile = _mobility_energy_profile(route, safe=True)

    assert len(profile) == 2
    assert all(value >= 0.0 for value in profile)
    assert abs(sum(profile) - 24.0) < 1e-9


def test_physics_profile_weights_partial_final_step() -> None:
    route = _route(1, 650.0, 26.0)

    profile = _mobility_energy_profile(route, safe=True)

    assert profile == (12.0, 12.0, 2.0)


class _ExecutionAuthority:
    fingerprint = "e" * 64

    def __init__(self) -> None:
        self.calls = []

    def realize(self, *, issue: int, route: MobilityRouteForecast):
        self.calls.append((issue, route.od_index, route.rank))
        return MobilityExecutionRealization(
            issue=issue,
            date="2025-01-01",
            depart_slot5=issue,
            od_index=route.od_index,
            rank=route.rank,
            eta_seconds=650.0,
            energy_kwh=13.0,
            source_authority="TEST_SUMO_EXECUTION_ONLY",
            source_day_sha256="f" * 64,
        )


def test_route_commit_uses_post_decision_sumo_eta_and_energy() -> None:
    locations = {
        "MESS01": "STA09",
        "MESS02": "IDC12",
        "MESS03": "STA07",
        "MESS04": "STA11",
    }
    destinations = dict(locations)
    destinations["MESS03"] = "IDC01"
    state = MutableMethodState(
        issue=6,
        pre_state_sha256="a" * 64,
        mess_energy_kwh={mid: 760.0 for mid in MESS_IDS},
        mess_location=locations,
        active_plan=SlowDiscretePlan(
            plan_id="plan",
            valid_from_issue=6,
            mess_destination=destinations,
            mess_native_route_rank={mid: 1 for mid in MESS_IDS},
            job_idc_placement={},
            checkpoint_migration={},
            gpu_gang_allocation={},
            job_start_issue={},
            coarse_charging_kw={mid: (0.0,) for mid in MESS_IDS},
        ),
    )
    route = MobilityRouteForecast(
        source_service_id="STA07",
        destination_service_id="IDC01",
        od_index=471,
        rank=1,
        q50_eta_seconds=600.0,
        safe_eta_seconds=900.0,
        q50_energy_kwh=24.0,
        safe_energy_kwh=36.0,
    )
    frame = CausalExperimentFrame(
        issue=6,
        current_price_aud_per_mwh=0.0,
        horizon_price_median_aud_per_mwh=0.0,
        q50_background_p_kw=0.0,
        q50_background_q_kvar=0.0,
        arrivals=(),
        exogenous_sha256="b" * 64,
        mobility_routes=(route,),
    )
    authority = _ExecutionAuthority()

    events = _start_planned_routes(
        state,
        SimpleNamespace(energy_flexibility="MESS", joint_uncertainty=True),
        frame,
        authority,
        10,
    )

    assert authority.calls == [(6, 471, 1)]
    assert state.mess_route_energy_profile_kwh["MESS03"] == (6.0, 6.0, 1.0)
    assert events[0]["planned_mobility_energy_kwh"] == 24.0
    assert events[0]["reserved_safe_mobility_energy_kwh"] == 36.0
    assert events[0]["planning_mobility_energy_kwh_used"] == 36.0
    assert events[0]["sumo_realized_eta_seconds"] == 650.0
    assert events[0]["realized_mobility_energy_route_total_kwh"] == 13.0
    assert events[0]["q50_eta_prediction_error_seconds"] == 50.0
    assert events[0]["q50_eta_absolute_error_seconds"] == 50.0
    assert events[0]["planning_eta_prediction_error_seconds"] == -250.0
    assert events[0]["safe_eta_reserve_margin_seconds"] == 250.0
    assert events[0]["safe_eta_realization_covered"] is True
    assert events[0]["q50_energy_prediction_error_kwh"] == -11.0
    assert events[0]["q50_energy_absolute_error_kwh"] == 11.0
    assert events[0]["planning_energy_prediction_error_kwh"] == -23.0
    assert events[0]["safe_energy_reserve_margin_kwh"] == 23.0
    assert events[0]["safe_energy_realization_covered"] is True
    assert events[0]["execution_transit_steps"] == 3
    assert events[0]["actual_used_by_optimizer"] is False


def test_planning_blocks_route_that_cannot_finish_before_episode_boundary() -> None:
    locations = {
        "MESS01": "STA09",
        "MESS02": "IDC12",
        "MESS03": "IDC01",
        "MESS04": "STA11",
    }
    state = MutableMethodState(
        issue=286,
        pre_state_sha256="a" * 64,
        mess_energy_kwh={mid: 760.0 for mid in MESS_IDS},
        mess_location=locations,
    )
    route = MobilityRouteForecast(
        source_service_id="IDC01",
        destination_service_id="STA07",
        od_index=10,
        rank=1,
        q50_eta_seconds=900.0,
        safe_eta_seconds=920.0,
        q50_energy_kwh=20.0,
        safe_energy_kwh=21.0,
    )
    frame = CausalExperimentFrame(
        issue=286,
        current_price_aud_per_mwh=0.0,
        horizon_price_median_aud_per_mwh=0.0,
        q50_background_p_kw=0.0,
        q50_background_q_kvar=0.0,
        arrivals=(),
        exogenous_sha256="b" * 64,
        mobility_routes=(route,),
    )

    destinations, _ = _optimize_mess_routes(
        state,
        SimpleNamespace(energy_flexibility="MESS", joint_uncertainty=True),
        frame,
        2,
    )

    assert destinations["MESS03"] == "IDC01"
    assert state.last_slow_miqp_certificate[
        "episode_boundary_blocked_route_count"
    ] == 1
    assert state.last_slow_miqp_certificate[
        "episode_boundary_eta_authority"
    ] == "SAFE_ETA"


def test_execution_fails_closed_when_sumo_actual_crosses_episode_boundary() -> None:
    locations = {
        "MESS01": "STA09",
        "MESS02": "IDC12",
        "MESS03": "STA07",
        "MESS04": "STA11",
    }
    destinations = dict(locations)
    destinations["MESS03"] = "IDC01"
    state = MutableMethodState(
        issue=6,
        pre_state_sha256="a" * 64,
        mess_energy_kwh={mid: 760.0 for mid in MESS_IDS},
        mess_location=locations,
        active_plan=SlowDiscretePlan(
            plan_id="plan",
            valid_from_issue=6,
            mess_destination=destinations,
            mess_native_route_rank={mid: 1 for mid in MESS_IDS},
            job_idc_placement={},
            checkpoint_migration={},
            gpu_gang_allocation={},
            job_start_issue={},
            coarse_charging_kw={mid: (0.0,) for mid in MESS_IDS},
        ),
    )
    route = MobilityRouteForecast(
        source_service_id="STA07",
        destination_service_id="IDC01",
        od_index=471,
        rank=1,
        q50_eta_seconds=600.0,
        safe_eta_seconds=900.0,
        q50_energy_kwh=24.0,
        safe_energy_kwh=36.0,
    )
    frame = CausalExperimentFrame(
        issue=6,
        current_price_aud_per_mwh=0.0,
        horizon_price_median_aud_per_mwh=0.0,
        q50_background_p_kw=0.0,
        q50_background_q_kvar=0.0,
        arrivals=(),
        exogenous_sha256="b" * 64,
        mobility_routes=(route,),
    )
    authority = _ExecutionAuthority()

    with pytest.raises(RuntimeContractError, match="crosses the independent"):
        _start_planned_routes(
            state,
            SimpleNamespace(energy_flexibility="MESS", joint_uncertainty=True),
            frame,
            authority,
            2,
        )

    assert authority.calls == [(6, 471, 1)]
    assert state.mess_in_transit["MESS03"] is False
    assert state.mess_location["MESS03"] == "STA07"

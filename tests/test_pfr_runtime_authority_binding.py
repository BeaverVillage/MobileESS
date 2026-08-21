from pfr.runtime import MobilityRouteForecast, _mobility_energy_profile, _pareto_routes


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
        profile_template_id=0,
        profile_horizon_steps=2,
    )


def test_duration_energy_pareto_prunes_dominated_k3_route() -> None:
    routes = (_route(1, 600.0, 20.0), _route(2, 900.0, 30.0), _route(3, 500.0, 35.0))

    kept = _pareto_routes(routes, safe=True)

    assert [route.rank for route in kept] == [1, 3]


def test_e4_profile_conserves_selected_safe_energy() -> None:
    cumulative = tuple(index / 128.0 for index in range(129))
    route = _route(1, 600.0, 24.0)

    profile = _mobility_energy_profile(route, {0: cumulative}, safe=True)

    assert len(profile) == 2
    assert all(value >= 0.0 for value in profile)
    assert abs(sum(profile) - 24.0) < 1e-9

from pfr.compact_h54 import _MobilityTemplate, _ordered_mobility_candidates


def _route(offset: int | None, destination: str, rank: int = 1) -> _MobilityTemplate:
    return _MobilityTemplate(
        departure_offset=offset,
        destination_service_id=destination,
        route_rank=rank,
        route_slot=None if offset is None else offset,
        transit_steps=0 if offset is None else 3,
        energy_kwh=0.0 if offset is None else 10.0,
        source="STA07",
        generation_reason="TEST",
    )


def test_small_prefix_contains_actionable_destination_diversity() -> None:
    stay = _route(None, "STA07")
    late_best = _route(42, "IDC01")
    early_first = _route(2, "IDC01")
    early_second_destination = _route(1, "IDC07")
    early_duplicate_destination = _route(3, "IDC01", rank=2)

    ordered = _ordered_mobility_candidates(
        mandatory=[stay],
        ranked=[
            (late_best, 0.70),
            (early_first, 0.80),
            (early_duplicate_destination, 0.81),
            (early_second_destination, 0.82),
        ],
        commitment_window_steps=6,
    )

    assert ordered[:4] == [
        stay,
        early_first,
        early_second_destination,
        late_best,
    ]


def test_previous_plan_and_stay_remain_mandatory() -> None:
    stay = _route(None, "STA07")
    previous = _route(12, "IDC03")
    early = _route(0, "IDC07")

    ordered = _ordered_mobility_candidates(
        mandatory=[stay, previous],
        ranked=[(early, 0.5), (previous, 0.6)],
        commitment_window_steps=6,
    )

    assert ordered[:3] == [stay, previous, early]
    assert ordered.count(previous) == 1


def test_actionable_prefix_round_robins_destinations_before_route_depth() -> None:
    stay = _route(None, "STA07")
    idc01_first = _route(1, "IDC01", rank=1)
    idc01_second = _route(2, "IDC01", rank=2)
    idc01_third = _route(3, "IDC01", rank=3)
    idc02 = _route(1, "IDC02")
    sta05 = _route(1, "STA05")

    ordered = _ordered_mobility_candidates(
        mandatory=[stay],
        ranked=[
            (idc01_first, 0.50),
            (idc01_second, 0.51),
            (idc01_third, 0.52),
            (idc02, 0.60),
            (sta05, 0.70),
        ],
        commitment_window_steps=6,
    )

    assert ordered.index(sta05) < ordered.index(idc01_second)
    assert ordered.index(sta05) < ordered.index(idc01_third)

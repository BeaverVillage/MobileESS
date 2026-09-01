from datetime import date, datetime, timedelta

import pytest

from dayahead.input_contract import (
    FIXED_AEST,
    ForecastVintage,
    InputContractError,
    average_5_to_15,
    issuance_cutoff,
    operating_axis,
    pwc_30_to_15,
    require_causal_timestamp,
    select_latest_complete_vintage,
    sum_energy_5_to_15,
)


def test_exact_96_slot_fixed_aest_axis_and_cutoff() -> None:
    axis = operating_axis(date(2025, 11, 3))
    assert len(axis) == 96
    assert axis[0].isoformat() == "2025-11-03T00:00:00+10:00"
    assert axis[-1].isoformat() == "2025-11-03T23:45:00+10:00"
    assert issuance_cutoff(date(2025, 11, 3)).isoformat() == "2025-11-02T18:00:00+10:00"


def test_resolution_mappings_preserve_energy() -> None:
    half_hour_kw = tuple(float(index) for index in range(48))
    quarter_hour_kw = pwc_30_to_15(half_hour_kw)
    assert len(quarter_hour_kw) == 96
    assert sum(half_hour_kw) * 0.5 == pytest.approx(sum(quarter_hour_kw) * 0.25)

    five_minute_kw = tuple(float(index % 7) for index in range(288))
    quarter_hour_actual = average_5_to_15(five_minute_kw)
    assert sum(five_minute_kw) / 12 == pytest.approx(sum(quarter_hour_actual) / 4)

    energy = tuple((-1.0 if index == 2 else 2.0) for index in range(12))
    assert sum(sum_energy_5_to_15(energy)) == pytest.approx(sum(energy))


def test_cutoff_rejects_future_actual_and_naive_timestamps() -> None:
    day = date(2025, 11, 3)
    with pytest.raises(InputContractError):
        require_causal_timestamp(datetime(2025, 11, 2, 18, 1, tzinfo=FIXED_AEST), day)
    with pytest.raises(InputContractError):
        require_causal_timestamp(datetime(2025, 11, 2, 17, 0), day)


def test_latest_complete_product_vintage_is_selected_without_slot_mixing() -> None:
    day = date(2025, 11, 3)
    axis = operating_axis(day)
    older = ForecastVintage("DEMAND", issuance_cutoff(day) - timedelta(hours=2), axis, "old")
    latest = ForecastVintage("DEMAND", issuance_cutoff(day) - timedelta(minutes=1), axis, "latest")
    incomplete = ForecastVintage("DEMAND", issuance_cutoff(day), axis[:-1], "incomplete")
    assert select_latest_complete_vintage((older, latest, incomplete), day, "DEMAND").vintage_id == "latest"

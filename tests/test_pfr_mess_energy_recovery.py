import pytest

from pfr.runtime import MESS_IDS, _nominal_mess_dispatch


def dispatch(*, energy, transit=(), enabled=True, price=100.0, median=100.0):
    return _nominal_mess_dispatch(
        energy_kwh={mid: float(energy) for mid in MESS_IDS},
        in_transit={mid: mid in transit for mid in MESS_IDS},
        energy_enabled=enabled,
        current_price_aud_per_mwh=price,
        horizon_price_median_aud_per_mwh=median,
    )


def test_low_price_precharges_toward_physical_capacity_within_refresh_window():
    charge, discharge = dispatch(energy=760.0, price=90.0)

    assert set(charge.values()) == {550.0}
    assert set(discharge.values()) == {0.0}


def test_neutral_price_recovers_canonical_daily_energy_within_refresh_window():
    charge, discharge = dispatch(energy=700.0)

    assert all(value == pytest.approx(60.0 / (0.95 * 0.5)) for value in charge.values())
    assert set(discharge.values()) == {0.0}


def test_high_price_discharge_cannot_cross_protected_floor():
    charge, discharge = dispatch(energy=441.0, price=110.0)

    assert set(charge.values()) == {0.0}
    assert all(value == pytest.approx(1.0 * 0.95 / (5.0 / 60.0)) for value in discharge.values())

    _, at_floor = dispatch(energy=440.0, price=110.0)
    assert set(at_floor.values()) == {0.0}


def test_disabled_or_in_transit_storage_has_no_nominal_dispatch():
    disabled_charge, disabled_discharge = dispatch(energy=600.0, enabled=False, price=90.0)
    transit_charge, transit_discharge = dispatch(energy=600.0, transit=MESS_IDS, price=90.0)

    assert set(disabled_charge.values()) == set(disabled_discharge.values()) == {0.0}
    assert set(transit_charge.values()) == set(transit_discharge.values()) == {0.0}

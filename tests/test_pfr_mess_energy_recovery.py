import pytest
from types import SimpleNamespace

from pfr.runtime import MESS_IDS, _GurobiSensitivityProjector, _nominal_mess_dispatch
from pfr.safety import ExactAcResult
from pfr.slow_fast import FastControl, FastLayerState


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


class CoupledPqVerifier:
    mess_in_transit = (False, False, False, False)

    def verify_fresh(self, *, control, state, slow_plan):
        del state, slow_plan
        net_p = sum(
            control.mess_discharge_kw[mid] - control.mess_charge_kw[mid]
            for mid in MESS_IDS
        )
        active_fraction = (net_p + 200.0) / 2400.0
        q_fraction = sum(control.mess_q_kvar.values()) / (4.0 * 700.0)
        vmin = 0.96 + 0.01 * active_fraction + 0.02 * q_fraction
        vmax = 1.04 + 0.02 * active_fraction + 0.08 * q_fraction
        line = 1.12 - 0.20 * active_fraction
        passed = 0.95 <= vmin <= vmax <= 1.05 and line <= 1.0
        return ExactAcResult(
            passed,
            "PASS" if passed else "VIOLATION",
            True,
            True,
            vmin,
            vmax,
            line,
            0.8,
            0 if passed else 1,
        )


def test_projector_combines_active_relief_with_location_sensitive_q():
    nominal = FastControl(
        {mid: 50.0 for mid in MESS_IDS},
        {mid: 0.0 for mid in MESS_IDS},
        {mid: 0.0 for mid in MESS_IDS},
        {},
        {},
    )
    state = FastLayerState(0, {mid: 760.0 / 1080.0 for mid in MESS_IDS}, {})
    projector = _GurobiSensitivityProjector(CoupledPqVerifier(), allow_mess=True)

    candidate = projector.project(
        nominal=nominal,
        state=state,
        slow_plan=SimpleNamespace(fingerprint="fixed-plan"),
    )
    exact = projector.verifier.verify_fresh(
        control=candidate.control,
        state=state,
        slow_plan=SimpleNamespace(fingerprint="fixed-plan"),
    )

    assert exact.passed
    assert sum(candidate.control.mess_q_kvar.values()) < 0.0
    assert any(
        row.get("solver", {}).get("status")
        == "FRESH_OPENDSS_PASSING_ACTIVE_COORDINATE_Q_SEARCH"
        for row in projector.trace
    )

import numpy as np

from dayahead.thermal.models.constant_pue import constant_pue
from dayahead.thermal.models.dynamic_state import DynamicThermalModel, causal_state
from dayahead.thermal.models.quasistatic import QuasiStaticModel
from dayahead.thermal.normalize import reference_pue_normalize


def test_c0_exactly_1p30() -> None:
    it = np.array([1.0, 100.0, 1000.0])
    assert np.array_equal(constant_pue(it), 1.30 * it)


def test_models_nonnegative_monotonic_and_causal() -> None:
    it = np.array([500.0, 600.0, 700.0, 800.0])
    tw = np.full(4, 15.0)
    rh = np.full(4, 50.0)
    c1 = QuasiStaticModel((0.0, 2.0, 0.1, 0.0, 0.1, 0.1, 0.0), 10.0)
    p1 = c1.predict_cooling_kw(it, tw, rh)
    assert np.all(p1 >= 0) and np.all(np.diff(p1) >= 0)
    c2 = DynamicThermalModel((0, 2, .1, .1, 0, .1, 1, .1), .9, 1.0)
    p2, _ = c2.predict_cooling_kw(it, tw, rh)
    assert np.all(p2 >= 0) and 0 < c2.rho < 1 and np.isfinite(c2.tau_minutes)
    changed = causal_state(np.array([1.0, 999.0, 3.0]), .9)
    base = causal_state(np.array([1.0, 2.0, 3.0]), .9)
    assert changed[1] == base[1]  # current/future input cannot affect theta(t)


def test_reference_pue_energy_identity_no_double_count() -> None:
    it = np.array([100.0, 200.0, 300.0])
    overhead = np.array([10.0, 80.0, 30.0])
    pue, pcc, audit = reference_pue_normalize(it, overhead)
    assert np.all(pue >= 1)
    assert abs(np.sum(pcc - it) / np.sum(it) - 0.30) < 1e-12
    assert audit["double_pue_count"] == 0
    assert audit["extra_1p30_multiplier_count"] == 0

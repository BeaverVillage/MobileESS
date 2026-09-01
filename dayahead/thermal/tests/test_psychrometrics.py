import numpy as np

from dayahead.thermal.psychrometrics import (
    dewpoint_from_relative_humidity,
    relative_humidity_from_dewpoint,
    wet_bulb_temperature_c,
)


def test_psychrometric_physical_bounds() -> None:
    t = np.array([-10.0, 5.0, 20.0, 35.0])
    rh = np.array([20.0, 50.0, 80.0, 100.0])
    td = dewpoint_from_relative_humidity(t, rh)
    tw = wet_bulb_temperature_c(t, rh, np.array([80000, 90000, 101325, 105000]))
    assert np.all((rh >= 0) & (rh <= 100))
    assert np.all(td <= t + 0.05)
    assert np.all(tw >= td - 0.05)
    assert np.all(tw <= t + 0.05)
    assert np.allclose(relative_humidity_from_dewpoint(t, td), rh, atol=0.2)

from pathlib import Path
from unittest.mock import patch
import pytest
import math
from v44_recovery_r049 import weather
from v44_recovery_r049 import operations as op


def test_altimeter_conversion_standard_pressure_and_elevation_direction():
    assert weather.station_pressure_hpa(1018.,132.28)==pytest.approx(1002.4410849095201,abs=1e-10)
    assert weather.station_pressure_hpa(1018.,0)==pytest.approx(1018.3,abs=1e-9)
    assert weather.station_pressure_hpa(1018.,500)<weather.station_pressure_hpa(1018.,132.28)


@pytest.mark.parametrize('a,z',[(math.nan,132.28),(1018.,math.nan),(0,132.28),(1018.,-100),(1018.,9999)])
def test_invalid_pressure_or_elevation_is_rejected(a,z):
    with pytest.raises(ValueError):weather.station_pressure_hpa(a,z)


def test_original_psychrometric_result_is_physical():
    p=weather.psychrometrics();rh=float(p.relative_humidity_from_dewpoint(13.,11.))
    wet=float(p.wet_bulb_temperature_c(13.,rh,weather.station_pressure_hpa(1018.,132.28)*100))
    assert 11.<=wet<=13. and wet==pytest.approx(11.856969099303287,abs=1e-12)


def test_existing_asof_age_and_future_read_guards_remain():
    from v43_actual.vendor.current_ac_admission import CausalSeries
    series=CausalSeries([dict(observed_seconds=0.,available_seconds=0.,values={'t_wb_c':10.,'rh_pct':80.})],name='weather')
    assert series.max_staleness_seconds==7200
    with pytest.raises(ValueError):series.at(7201,observed_now=7201)
    with pytest.raises(ValueError):series.at(1,observed_now=0)


def test_unrelated_day_returns_the_original_observation_object():
    marker=object()
    with patch.object(weather,'original_loader',return_value=lambda **kwargs:marker):
        assert weather.loader()(begin=0,end=1,bundle=Path('DAY_20250524')) is marker


def test_scoped_request_authority_is_mandatory():
    with patch.object(op,'authority'),patch.object(op,'record',return_value={'path':'required'}),pytest.raises(PermissionError):op.authorize_case({'day':'2025-05-23','arm':'B0'})

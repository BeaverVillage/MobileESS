from copy import deepcopy
import math
import pytest
from v44_recovery_r003.weather import admit,loader
from v43_actual.vendor.current_ac_admission import CausalSeries


def row(t,wb=12.,rh=40.):
    return dict(observed_seconds=t,available_seconds=t,values=dict(t_wb_c=wb,rh_pct=rh))


def test_incomplete_hour_uses_original_past_hold_without_interpolation():
    raw=[row(0),row(3600,math.nan,35.),row(7200,14.,36.)];before=deepcopy(raw)
    valid,rejected=admit(raw);series=CausalSeries(valid,name='weather')
    assert series.at(6300,observed_now=6300)['values']==raw[0]['values']
    assert series.at(6300,observed_now=6300)['observation_age_seconds']==6300
    assert rejected[0]['invalid_fields']==['t_wb_c']
    assert raw[0]==before[0] and math.isnan(raw[1]['values']['t_wb_c'])
    assert series.max_staleness_seconds==7200


def test_original_too_stale_and_future_query_guards_stay_active():
    valid,_=admit([row(0),row(3600,math.nan),row(10800)])
    series=CausalSeries(valid,name='weather')
    with pytest.raises(ValueError,match='TOO_STALE'):series.at(8100,observed_now=8100)
    with pytest.raises(ValueError,match='FUTURE'):series.at(900,observed_now=0)


def test_no_valid_weather_and_nonfinite_clock_fail_closed():
    with pytest.raises(ValueError,match='NO_COMPLETE'):admit([row(0,math.nan)])
    with pytest.raises(ValueError,match='CLOCK'):admit([row(math.nan)])


def test_finite_rows_unchanged_and_conflicting_duplicates_still_fail():
    raw=[row(0),row(3600)];valid,rejected=admit(raw)
    assert valid==raw and not rejected
    assert CausalSeries(valid,name='weather').receipt_sha==CausalSeries(raw,name='weather').receipt_sha
    with pytest.raises(ValueError,match='CONFLICTING'):CausalSeries(admit([row(0),row(0,13.)])[0],name='weather')


def test_may02_actual_case_weather_all_120_queries_and_may01_unchanged(tmp_path):
    from pathlib import Path
    from v44.daily import day_inputs
    from v44.config import axis
    from v44.common import read
    import v43_actual.observations as original
    for day in ('2025-05-01','2025-05-02','2025-05-07'):
        a=axis(day);kwargs=dict(begin=a['issue_seconds'],end=a['end_seconds'],bundle=Path(day_inputs(day)['actual_bundle']))
        path=tmp_path/(day+'.json');obs=loader(path)(**kwargs)
        for t in range(120):
            when=a['issue_seconds']+t*900;r=obs.at(when,observed_now=when)['weather']
            assert r['observed_seconds']<=when and r['available_seconds']<=when
            assert r['observation_age_seconds']<=7200
            assert all(math.isfinite(v) for v in r['values'].values())
        audit=read(path)
        if day=='2025-05-01':
            assert obs.sha==original.load_observations(**kwargs).sha
            assert not audit['rejected_rows']
        else:assert len(audit['rejected_rows'])==1

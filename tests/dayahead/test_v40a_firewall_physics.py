from dataclasses import replace
import pytest
from dayahead.v40a import firewall
from dayahead.v40a.recourse import validate_physics
from dayahead.v33m.mess_mobility_milp import MessElectricalAuthority
from dayahead.v33m.mess_trajectory import MessTrajectory,MessTrajectorySlot
from dayahead.v40a.invariants import route_sha


def stationary():
    a=MessElectricalAuthority.from_repository()
    return MessTrajectory(tuple(MessTrajectorySlot('MESS01',t,'CONNECTED','STA01',None,None,(),None,
                   0,0,0,0,0,None,0,0,0,0,a.initial_energy_kwh,a.initial_energy_kwh/a.capacity_kwh) for t in range(96)))


@pytest.mark.parametrize('path',['cache/fresh/OPENDSS_SUMMARY.json','data/noaa_actual_weather.parquet','days/2025-05-01/results.json'])
def test_planning_firewall_blocks_actual_fresh_future(path):
    firewall.activate('2025-04-01')
    try:
        with pytest.raises(PermissionError):firewall.check_read(path)
    finally:firewall.deactivate()


def test_planning_firewall_allows_causal_day_forecasts():
    firewall.activate('2025-04-01')
    try:firewall.check_read('2025-04-01/aemo_forecast.json')
    finally:firewall.deactivate()


def test_fresh_reads_possible_after_loop():
    firewall.deactivate();firewall.check_read('fresh/OPENDSS_SUMMARY.json')


def test_stationary_physics_and_mobility_identity():
    t=stationary();assert validate_physics(t)['status']=='PASS'
    modified=MessTrajectory(tuple(replace(r,q_kvar=1) for r in t.slots))
    assert route_sha(t.slots)==route_sha(modified.slots)


def test_energy_imbalance_is_rejected():
    t=stationary();bad=MessTrajectory((replace(t.slots[0],p_kw=1),*t.slots[1:]))
    assert validate_physics(bad)['status']=='FAIL'


def test_route_change_changes_signature():
    t=stationary();bad=MessTrajectory((replace(t.slots[0],service_id='STA02'),*t.slots[1:]))
    assert route_sha(t.slots)!=route_sha(bad.slots)

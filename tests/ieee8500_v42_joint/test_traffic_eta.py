"""Pinned source proxy tests; no Native, AC, Actual or artifact writers."""
import copy
import math
import pytest
from ieee8500_v42_joint.traffic_eta import load_sources,make_rows,check_route,SLOTS,EXPECTED_INITIAL

@pytest.fixture(scope='module')
def sources():return load_sources()

def test_full_original_route_product_and_six_initial_identities(sources):
    assert len(sources['routes'])==96*24*24
    assert sources['fleet']['initial_locations']==EXPECTED_INITIAL
    assert len(sources['services'])==len(set(sources['services'].values()))==24

def test_complete_432_rows_have_original_connection_energy_and_scope(sources):
    rows=make_rows(sources)
    assert len(rows)==len({(r['departure_slot'],r['vehicle_id'],r['destination_STA']) for r in rows})==432
    assert {r['departure_slot'] for r in rows}==set(SLOTS)
    for r in rows:
        assert r['new_PCC_physical_access']=='UNVERIFIED' and not r['full_dynamic_dispatch_or_Actual_SUMO_PASS']
        assert r['station_simultaneous_vehicle_capacity']==1 and r['single_abstract_move_SOC_PASS']
        if r['initial_traffic_service']!=r['destination_STA']:
            assert r['source_ready_offset_slots']==math.ceil((r['source_safe_ETA_seconds']+600)/900)
            assert r['effective_ready_slot']==r['departure_slot']+r['source_ready_offset_slots']
        elif r['departure_slot']==0:
            assert r['source_ready_offset_slots']==0 and r['effective_ready_slot']==1
            assert not r['reachable_from_initial_before_sample_slot']
        assert abs(r['after_single_move_SOC_kwh']+r['source_safe_energy_kwh']-1140)<1e-9

@pytest.mark.parametrize('field,value',[
    ('road_destination_node','TN_99'),('route_distance_km',9999.),('connection_ready_slots_15min',0),
    ('energy_safe_kwh',9999.),('route_graph_sha','0'*64)])
def test_route_auditor_rejects_identity_units_readytime_energy_or_source_drift(sources,field,value):
    r=copy.deepcopy(sources['routes'][(0,'STA01','STA02')]);r[field]=value
    with pytest.raises(AssertionError):check_route(r,sources)

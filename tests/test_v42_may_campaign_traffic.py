from copy import deepcopy
from datetime import datetime, timedelta, timezone
import numpy as np
import pytest
from v42_may_campaign.traffic import (forecast_logical_sha, validate_forecast,
    validate_routes, original_physics)


@pytest.fixture
def traffic_case():
    midnight=datetime(2025,5,1,tzinfo=timezone(timedelta(hours=10)))
    links=[f'L{i:03}' for i in range(509)]
    q={key:np.repeat((np.arange(288,dtype=np.float32)+base)[:,None],509,axis=1)
       for key,base in [('Q10_sec',300),('Q50_sec',400),('Q90_sec',500)]}
    meta=dict(forecast_day='2025-05-01',issue_time=(midnight-timedelta(hours=6)).isoformat(),
        max_input_timestamp=(midnight-timedelta(hours=6,minutes=5)).isoformat(),
        target_timestamps=[(midnight+timedelta(minutes=5*t)).isoformat() for t in range(288)],
        link_ids=links,model_id='ORIGINAL',model_sha='a'*64,data_sha='b'*64,
        graph_sha='c'*64,normalization_sha='d'*64,causality_pass=True,future_actual_read_count=0)
    meta['bundle_sha']=forecast_logical_sha(meta,q)
    physics,physics_sha=original_physics(); rows=[]
    for t in range(96):
        for s in ('A','B'):
            for d in ('A','B'):
                stay=s==d; eta=[0.,0.,0.] if stay else [float(q[key][3*t,0]) for key in ('Q10_sec','Q50_sec','Q90_sec')]
                row=dict(departure_slot_15=t,origin_service_id=s,destination_service_id=d,
                    route_link_ids=[] if stay else ['L000'],route_graph_sha=meta['graph_sha'],
                    traffic_forecast_sha=meta['bundle_sha'],physics_contract_sha=physics_sha,
                    route_distance_km=0. if stay else 1.,cumulative_ascent_m=0. if stay else 1.,
                    cumulative_descent_m=0.,route_q10_eta_sec=eta[0],route_q50_eta_sec=eta[1],route_q90_eta_sec=eta[2],
                    route_safe_eta_sec=0. if stay else eta[1]+50.,travel_slots_15min=0 if stay else 1,
                    connection_ready_slots_15min=0 if stay else 2,energy_nominal_kwh=0.,energy_safe_kwh=0.)
                if not stay:
                    energy=[physics.energy_kwh(row,e) for e in eta]
                    row.update(energy_nominal_kwh=energy[1],energy_safe_kwh=max(energy))
                rows.append(row)
    return meta,q,dict(service_ids=['A','B'],departure_slots=list(range(96)),routes=rows),physics,physics_sha


def verify_routes(case):
    meta,q,table,physics,physics_sha=case
    return validate_routes(table,meta,q,physics=physics,physics_sha=physics_sha,expected_services=2)


def test_original_288_forecast_to_96_departures_without_interpolation(traffic_case):
    meta,q,table,*rest=traffic_case
    forecast=validate_forecast('2025-05-01',meta,q)
    arcs,receipt=verify_routes(traffic_case)
    assert forecast['route_slot_to_forecast_step']==list(range(0,288,3))
    assert forecast['route_slot_to_timestamp'][1]=='2025-05-01T00:15:00+10:00'
    assert receipt['PASS'] and len(arcs)==188
    assert receipt['exclusions']=={'same_site_represented_by_stay':192,'outside_inherited_RouteArc_time_contract':4}
    assert receipt['original_physics_energy_exact'] and receipt['interpolation_calls']==0
    assert arcs['A:B:1'][:5]==('A','B',1,2,3)


def test_calibrated_safe_eta_is_not_replaced_by_q90(traffic_case):
    row=traffic_case[2]['routes'][1]
    assert row['route_q50_eta_sec'] < row['route_safe_eta_sec'] < row['route_q90_eta_sec']
    assert verify_routes(traffic_case)[1]['PASS']


@pytest.mark.parametrize('mutation,label',[('bytes','ORIGINAL_LOGICAL_BUNDLE_SHA'),
    ('five_minute_axis','ORIGINAL_288_FIVE_MINUTE_AXIS'),('timezone','FIXED_AEST_CAUSAL_ISSUE'),
    ('future','SAME_DAY_NO_FUTURE_READ'),('post_issue','FIXED_AEST_CAUSAL_ISSUE'),
    ('quantile','ORIGINAL_QUANTILE_SHAPE_UNITS_AND_ORDER')])
def test_forecast_mutations_rejected(traffic_case,mutation,label):
    meta,q,*rest=traffic_case
    if mutation=='bytes': q['Q50_sec'][0,0]+=.1
    elif mutation=='five_minute_axis': meta['target_timestamps'][1]=meta['target_timestamps'][0]
    elif mutation=='timezone': meta['issue_time']='2025-04-30T08:00:00+00:00'
    elif mutation=='future': meta['future_actual_read_count']=1
    elif mutation=='post_issue': meta['max_input_timestamp']='2025-04-30T19:00:00+10:00'
    elif mutation=='quantile': q['Q10_sec'][0,0]=1000
    with pytest.raises(ValueError,match=label):validate_forecast('2025-05-01',meta,q)


@pytest.mark.parametrize('mutation,label',[('missing','COMPLETE_ORIGINAL_ROUTE_PRODUCT'),
    ('duplicate','NO_MISSING_OR_DUPLICATE_ROUTE_KEYS'),('logical','ROW_LOGICAL_FORECAST_AND_GRAPH_SHA'),
    ('snapshot','EXACT_DEPARTURE_EPOCH_LINK_SNAPSHOT_SUM'),('connection','ORIGINAL_SAFE_TRAVEL_AND_600_SECOND_CONNECTION'),
    ('energy','ORIGINAL_PHYSICS_ENERGY_EXACT'),('path','ORIGINAL_PATH_LINK_ID_AXIS')])
def test_every_original_route_field_and_physical_mapping_is_checked(traffic_case,mutation,label):
    rows=traffic_case[2]['routes']; row=rows[1]
    if mutation=='missing':rows.pop()
    elif mutation=='duplicate':rows[-1]=deepcopy(rows[0])
    elif mutation=='logical':row['traffic_forecast_sha']='e'*64
    elif mutation=='snapshot':row['route_q50_eta_sec']+=1.
    elif mutation=='connection':row['connection_ready_slots_15min']=1
    elif mutation=='energy':row['energy_safe_kwh']+=.01
    elif mutation=='path':row['route_link_ids']=['created_missing_path']
    with pytest.raises(ValueError,match=label):verify_routes(traffic_case)

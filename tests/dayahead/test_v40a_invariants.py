from copy import deepcopy
import math
import pytest
from dayahead.v40a.invariants import *


def job(uid='a',start=100,duration=10,site='AIDC01',gpu=4):
    return dict(job_uid=uid,start_slot=start,end_slot=start+duration,AIDC_site=site,
                post_H_site=site if start+duration>120 else None,requested_GPU=gpu,
                safe_duration_slots=duration,state_at_issue='PENDING',qos='standby',
                migration_selected=False,migration_destination=None,Rack_label='R1')


def test_terminal_new_occupancy_fails():
    a=job();b=job(start=115)
    assert terminal_audit([a],[b])['status']=='FAIL'


def test_terminal_new_site_fails():
    assert terminal_audit([job(duration=30)],[job(duration=30,site='AIDC02')])['POST_H_SITE_STATE_CHANGED_JOBS']==1


def test_legal_baseline_tail_preserved():
    a=job(duration=30)
    assert terminal_audit([a],[a])['status']=='PASS'


def test_gpu_tail_increments_cannot_cancel():
    a=[job('a',100,30),job('b',100,30)]
    b=[job('a',110,30),job('b',90,30)]
    assert terminal_audit(a,b)['REPAIR_INDUCED_INCREMENTAL_POST_MIDNIGHT_GPU_H']==10


def test_terminal_site_field_cannot_hide_site_change():
    a=job(duration=30);b={**a,'AIDC_site':'AIDC02'}
    with pytest.raises(ValueError,match='TERMINAL_SITE'):terminal_audit([a],[b])


def test_full_interval_symmetric_cost_counts_site():
    a=job();assert occupancy_deviation(a,job(start=103))==24
    assert occupancy_deviation(a,job(site='AIDC02'))==80


@pytest.mark.parametrize('new,hard,expected',[(.5,True,True),(.6,True,False),(.5,False,False),(math.nan,True,False)])
def test_monotone(new,hard,expected):assert monotone(.5,new,hard,1e-6)==expected


def test_old_b3_not_accepted():
    with pytest.raises(ValueError,match='OLD_SEQUENTIAL'):validate_joint({'method':'SEQUENTIAL'})


def test_joint_hash_binds_both_replays():
    d=joint_decision([job()],[],{'inputs':'a'*64})
    assert validate_joint(d)==d['FINAL_JOINT_DECISION_SHA']
    d['authority']['inputs']='b'*64
    with pytest.raises(ValueError,match='HASH_MISMATCH'):validate_joint(d)


def test_interaction_values_observable():
    assert interaction_metrics(dict(B0=1,B1=.9,B2=.8,B3=.65))['Interaction']==pytest.approx(-.05)


def test_uid_loss_fails():
    with pytest.raises(ValueError,match='UNIVERSE'):terminal_audit([job()],[])


def test_numpy_arrays_hash_as_values():
    import numpy as np
    assert digest(np.array([[1.,2.],[3.,4.]]))==digest([[1.,2.],[3.,4.]])


def test_safe_seconds_and_frozen_wan_evidence_cannot_change():
    a={**job(),'safe_duration_seconds':9000,'accepted_A0_assignment_and_WAN':{'fixed_WAN_path_id':'p1'}}
    b=deepcopy(a);b['accepted_A0_assignment_and_WAN']['fixed_WAN_path_id']='p2'
    assert terminal_audit([a],[b])['status']=='FAIL'
    b=deepcopy(a);b['safe_duration_seconds']=1
    assert terminal_audit([a],[b])['status']=='FAIL'

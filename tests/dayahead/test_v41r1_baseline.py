from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace
import inspect
import pytest
from dayahead.v37.aidc_materializer import Job
from dayahead.v41r1.migration_baseline import materialize


def capacity(rack_size=4):
    racks=[SimpleNamespace(rack_pool_id='A_R1',historical_gpu_capacity=rack_size),
           SimpleNamespace(rack_pool_id='A_R2',historical_gpu_capacity=rack_size)]
    return SimpleNamespace(aidc_ids=('A',),site_capacity={'A':4},rack_pools=racks,
        eligible_racks=lambda site,g:[r for r in racks if r.historical_gpu_capacity>=g])


def row(uid,start,duration,gpu=4,*,state='PENDING',qos='normal',rack='A_R1',site='A'):
    return dict(job_uid=uid,start_slot=start,end_slot=start+duration,safe_duration_slots=duration,
        safe_duration_seconds=duration*900.,requested_GPU=gpu,state_at_issue=state,qos=qos,
        AIDC_site=site,Rack_label=rack,initial_Rack_label=rack,migration_selected=False)


def schedule(rows,cap=None):
    jobs=[Job(r['job_uid'],r['state_at_issue'],'',False,r['qos'],'gpu','2025-04-30T00:00:00Z',
        1,r['requested_GPU'],r['safe_duration_slots']) for r in rows]
    return materialize(rows,jobs,cap or capacity())


def test_delay_propagates_nonpreemptively_at_same_site_with_full_gpu():
    rows=[row('running',0,2,state='RUNNING'),row('a',1,3),row('b',3,2)]
    before=deepcopy(rows);out,audit=schedule(rows)
    assert rows==before
    assert [(r['start_slot'],r['end_slot']) for r in out]==[(0,2),(2,5),(5,7)]
    assert audit['changed_start_jobs']==2 and audit['GPU_feasibility']==audit['rack_feasibility']=='PASS'
    assert all(r['AIDC_site']=='A' and r['requested_GPU']==4 for r in out)
    assert all(not r['migration_selected'] for r in out)


def test_later_release_does_not_reserve_capacity_ahead_of_eligible_job():
    out,_=schedule([row('later_high',2,3,qos='high'),row('early_normal',0,4)])
    assert [r['start_slot'] for r in out]==[4,0]


def test_same_event_uses_existing_qos_submit_uid_priority():
    out,_=schedule([row('running',0,2,state='RUNNING'),row('a_standby',1,1,qos='standby'),row('z_normal',1,1)])
    assert [r['start_slot'] for r in out]==[0,3,2]


def test_rack_fragmentation_cannot_split_a_gang_even_when_site_has_room():
    out,audit=schedule([row('r1',0,3,1,state='RUNNING',rack='A_R1'),
        row('r2',0,6,1,state='RUNNING',rack='A_R2'),row('whole',1,2,2)],capacity(2))
    assert out[-1]['start_slot']==3 and out[-1]['end_slot']==5 and out[-1]['Rack_label']=='A_R1'
    assert audit['queue_waits'][0]['blocking_job_ids']==['r1','r2']


def test_no_advance_or_change_when_reference_is_feasible():
    rows=[row('a',25,2),row('b',29,1)]
    out,audit=schedule(rows)
    assert out==rows and audit['changed_start_jobs']==0


def test_unassigned_postday_admission_is_preserved_without_new_site():
    rows=[row('later',125,300,site='UNASSIGNED',rack=None)]
    out,audit=schedule(rows)
    assert out==rows and audit['admission_changes']==0


def test_frozen_unadmitted_overlap_is_full_backlog_without_new_admission():
    rows=[row('missing',0,30,site='UNASSIGNED',rack=None)]
    out,audit=schedule(rows)
    assert out==rows and audit['admission_changes']==0 and audit['occupancy_events']==[]
    assert audit['rows'][0]['unadmitted_backlog_GPUh']==30
    assert audit['rows'][0]['unadmitted_Q90_interval_overlaps_Day_D']


def test_unknown_site_for_new_day_overlap_is_not_silently_invented():
    with pytest.raises(ValueError,match='SITE_AUTHORITY'):
        schedule([row('missing',0,30,site='UNKNOWN',rack=None)])


def test_running_conflict_cannot_be_repaired_by_pending_queue():
    with pytest.raises(ValueError,match='IMMUTABLE_RUNNING'):
        schedule([row('r1',0,5,3,state='RUNNING'),row('r2',0,5,2,state='RUNNING')])


def test_baseline_firewall_has_no_grid_actual_or_optimizer_inputs():
    assert tuple(inspect.signature(materialize).parameters)==('jobs','scheduling','capacity')
    rows=[row('a',24,1)];first,a=schedule(rows)
    perturbed=deepcopy(rows);perturbed[0].update(actual_runtime=1e9,rho_max=-1,voltage=100,tail_probability=.99)
    other,b=schedule(perturbed)
    assert [(r['start_slot'],r['end_slot'],r['AIDC_site']) for r in first]==[(r['start_slot'],r['end_slot'],r['AIDC_site']) for r in other]
    assert a==b and a['grid_reads']==a['Actual_reads']==a['optimizer_calls']==0

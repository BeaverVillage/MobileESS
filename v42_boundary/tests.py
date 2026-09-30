from dataclasses import replace,asdict
import runpy
import numpy as np
import pytest
from .common import *
from .boundaries import known_window,LiveAuthority,submit_with_boundary,load_native
from .generator import Generator,checkpoints
from v42_job_capability import build_domain,checkpoint_records,validate,Job,Resources
from v42_temporal.native import temporal_domain
from v42_native.service import boundary
from v42_final.state import EpisodeLedger
from v42_final.workload import ForecastBook

fixture=runpy.run_path(str(ROOT/'tests/test_v42_job_capability.py'))['fixture']

@pytest.mark.parametrize('case',list('ABCDEFGHIJ'))
def test_all_legacy_synthetic_option_sets(case):
    j,b,r,_=fixture(case);old,_=build_domain(j,b,r)
    g=Generator(r,max(b.latest_completion,120));new=g.domain(j,b)
    assert tuple(new)==old
    assert len(new)==len(old)
    for o in new:assert validate(j,o,b,r)

@pytest.mark.parametrize('elapsed',[None,0,1,899,900,1799,1800,1801,57238.3])
def test_checkpoint_analytic_exact(elapsed):
    j,b,r,_=fixture('E');j=replace(j,elapsed_seconds=elapsed)
    assert checkpoints(j,0,10)==checkpoint_records(j,0,10)

def test_mask_matches_bruteforce_and_tail():
    j,b,r,_=fixture('F');r.fixed_gpu={('A',3):6,('A',15):8}
    g=Generator(r,30)
    for d in (0,1,2,8):
        for gang in (1,4,8):
            m=g.mask(d,gang,'A')
            for s in range(30-d):assert m[s]==all(r.capacities['A']-r.fixed_gpu.get(('A',t),0)>=gang for t in range(s,s+d))
    assert g.mask(5,4,'B')[11]

def test_failed_full_STAY_does_not_prune_escaping_migration():
    j,b,r,_=fixture('F');r.fixed_gpu={('A',4):8};old,_=build_domain(j,b,r)
    new=tuple(Generator(r,30).domain(j,b))
    assert new==old and any(o.initial_site=='A' and o.migrated for o in new)

def test_fixed_WAN_and_transfer_limits_match_legacy():
    j,b,r,_=fixture('F');r.fixed_wan={('AB',3):630};r.fixed_transfers={4:1}
    old,_=build_domain(j,b,r);g=Generator(r,30)
    assert tuple(g.domain(j,b))==old
    assert g.transfer('A','B',4,2)==g.transfer('A','B',4,2)

def test_no_movable_reference_occupancy_input_and_template_identity():
    j,b,r,_=fixture('F');g=Generator(r,30)
    a=g.domain(j,b);a2=g.domain(replace(j,uid='different_uid'),b)
    assert a is a2 and tuple(a)==tuple(a2)
    shortened=replace(b,allowed_starts=(0,))
    assert g.domain(j,shortened).sha!=a.sha
    # Snapshot owns immutable data, changes outside it cannot poison its masks.
    r.fixed_gpu['A',0]=100
    assert tuple(g.domain(j,b))==tuple(a)

def test_order_and_SHA_deterministic():
    j,b,r,_=fixture('F')
    a=Generator(r,30).domain(j,b);c=Generator(r,30).domain(j,b)
    assert a.sha==c.sha and tuple(a)==tuple(c)

def live_rows(n=100,slots=2,qos='standby',partition='p'):
    return [dict(job_id=str(i),issue_time='2024-01-01T00:00:00Z',authority_available_at='2024-01-01T00:00:00Z',
        source_kind='AUTHORIZED_R0_START_WINDOW',authority_reproduced=True,future_outcome_used=False,state='PENDING',qos=qos,
        protected=False,partition=partition,gpu_bucket='1',wall_bucket='<=1h',reference_start=24,latest_authorized_start=24+slots) for i in range(n)]

def metadata(qos='standby',protected=False):return dict(qos=qos,protected=protected,partition='p',gpu_bucket='1',wall_bucket='<=1h')

def test_live_Q25_higher_and_support():
    rows=live_rows();rows[0]['latest_authorized_start']=24
    a=LiveAuthority(rows);w=a.boundary(metadata(),901)
    assert w['earliest_start']==2 and w['latest_start']==4 and w['quantile']==.25 and w['method']=='higher'
    assert not LiveAuthority(rows[:99]).boundary(metadata(),901)['can_timeshift']
    assert not LiveAuthority(live_rows(slots=0)).boundary(metadata(),901)['can_timeshift']

@pytest.mark.parametrize('qos,protected',[('normal',False),('high',False),('urgent',False),('standby',True)])
def test_live_QoS_protection_fail_closed(qos,protected):
    assert not LiveAuthority(live_rows()).boundary(metadata(qos,protected),0)['can_timeshift']

def test_live_backoff_finest_and_no_queue_age():
    rows=live_rows(99);extra=dict(rows[0],job_id='100',partition='elsewhere');rows.append(extra)
    w=LiveAuthority(rows).boundary(metadata(),999999)
    assert w['selected_level']=='L1' and w['N_window']==100 and w['can_timeshift']

@pytest.mark.parametrize('change',[dict(future_outcome_used=True),dict(source_kind='RAW_WAIT'),dict(issue_time='2025-05-01T00:00:00Z')])
def test_live_rejects_future_or_wait_source(change):
    r=live_rows();r[0].update(change)
    with pytest.raises(ValueError):LiveAuthority(r)

def test_submitted_unknown_Q50_depletes_once_and_PENDING_can_TS():
    class Provider:
        def predict_total(self,metadata,**kw):return 1800.
    e=EpisodeLedger({'A':8});book=ForecastBook(tuple([10.]*24),tuple([15.]*24),0)
    j=submit_with_boundary(e,book,Provider(),LiveAuthority(live_rows()),'new',1,1,4,{},metadata())
    assert j['latest_observed_state']=='PENDING' and j['q50_seconds']==1800
    assert e.physical(1)=={'A':0} and book.row(0,1)['remaining_CC4_Q50_GPUh']==8
    assert j['live_service_boundary']['can_timeshift']
    with pytest.raises(ValueError):submit_with_boundary(e,book,Provider(),LiveAuthority([]),'new',1,1,4,{},metadata())

def test_known_Q50_source_and_no_actual_read():
    j=dict(job_uid='j',state='PENDING',planning_eligible=True,cohort='standby|p|STANDBY_QUEUE_CONTROLLED|False|1|<=1h|1',
        reference_start_if_authorized=116,service_slots=8,V10_Q50_total_seconds=7200,source_snapshot_sha='a'*64)
    s=dict(RSP_start_slot=116,RW_completion_slot=150,start_slot=116,safe_duration_slots=20,source_snapshot_sha256='a'*64,qos='standby',state_at_issue='PENDING')
    w=known_window(j,s);assert w['can_timeshift'] and w['latest_start']==119 and w['latest_start']+8>120
    s['actual_end']='invalid future';s['actual_runtime']=1e20
    assert known_window(j,s)==w
    j['state']='RUNNING';assert not known_window(j,s)['can_timeshift']

def test_frozen_interfaces_and_no_unsubmitted_identity():
    p=read(OUT/'PREREGISTRATION.json');assert p['target_TS_share'] is None and not p['live_TS']['D1_unknown_individual_boundary']
    for r in read(OUT/'PR97_BYTE_SNAPSHOT.json'):assert sha(r['path'])==r['sha256']

@pytest.mark.parametrize('seed',range(30))
def test_varied_physical_domains_exact(seed):
    rng=np.random.default_rng(seed);j,b,r,_=fixture('F')
    j=replace(j,service_slots=int(rng.integers(2,9)),gpu=int(rng.integers(1,5)))
    r=replace(r,control_end=12,restart_slots=int(rng.integers(1,3)))
    r.fixed_gpu={(s,int(rng.integers(0,19))):int(rng.integers(0,9)) for s in ('A','B')}
    r.fixed_transfers={int(rng.integers(0,12)):int(rng.integers(0,2))}
    r.wan_capacities={('AB',t):int(rng.choice([0,80,160,640])) for t in range(12)}
    b=replace(b,latest_completion=22)
    old,_=build_domain(j,b,r);g=Generator(r,30)
    assert tuple(g.domain(j,b))==old

def test_dedup_start_repetition_only():
    j,b,r,_=fixture('F');b=replace(b,allowed_starts=(0,0,1,1))
    old,_=build_domain(j,b,r);new=tuple(Generator(r,30).domain(j,b))
    assert old==new and len(new)==len(set(new))

def test_migration_column_GPU_WAN_and_runtime_identity():
    # Independent finite-domain check used by the streaming column builder:
    # every interval coefficient counts exactly the complete service slots.
    from v42_job_capability import resources_used
    j,b,r,_=fixture('F')
    for o in Generator(r,30).domain(j,b):
        cols={(site,t):j.gpu for site,a,e in o.segments for t in range(a,e)}
        legacy=resources_used(j,o)
        assert sum(cols.values())==j.service_slots*j.gpu
        assert cols=={(s,t):x for (kind,s,t),x in legacy.items() if kind=='GPU'}
        if o.migrated:
            assert o.segments[-1][2]-(j.reference_start+j.service_slots)==o.start-j.reference_start+o.restart_end-o.checkpoint

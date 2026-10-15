"""Research assumptions are separate from source permissions and QoS."""
from copy import deepcopy

import pytest

from v42_integration.experimental_qos import participation_for
from v42_integration.m_engine import file_record
from v42_integration.policy import digest
from v42_integration.research_presite_contract import (
    ResearchPresiteProvider, make_spec, source_authority)


def member(*, yes=True, skip=0):
    return next(str(i) for i in range(skip, skip+1000)
                if participation_for(str(i))['membership']['FLEX30'] is yes)


def fixture(tmp_path, *, scenario='R1', **kwargs):
    path = tmp_path/'NAMED_FIXTURE_SOURCE.json'; path.write_text('NAMED_NUMERIC_FIXTURE_ONLY')
    record = file_record(path)
    wan = dict(bytes_per_gpu=800., maximum_active_transfers=1,
        paths=[dict(source='A', destination='B', links=['AB'])],
        link_capacity_bytes_15min=dict(AB=[9000.]*20))
    spec = make_spec(scenario=scenario, source_records=[record], native_wan_sha=digest(wan), shared_sites=['A','B'], **kwargs)
    p = ResearchPresiteProvider(spec, native_wan=wan)
    m = dict(uid=member(), submit_seconds=10., gpu=2, compatible_sites=['A','B'],
        reference_site='A', state='PENDING', origin_unknown=True, accumulated_compute_seconds=0.,
        t50_seconds=200., qos='UNCONFIRMED', protected=None, batch_eligible=None,
        can_prestart_place=False)
    row = dict(job_uid=m['uid'],submit_seconds=10.,GPU_gang=2,compatible_sites=['A','B'])
    p.register_observed(m,source_authority(row,record,now=900),now=900)
    qos = dict(allowed_starts_seconds=[900.,1800.,2700.,3600.],latest_start_seconds=3600.,budget_seconds=2700.)
    return p,m,row,record,qos


def test_flex30_ready_assumption_does_not_rewrite_raw_default_or_qos(tmp_path):
    p,m,row,_,qos = fixture(tmp_path)
    before = deepcopy((m,row,qos))
    r = p.propose(m,'B',900.,day_begin=0,qos_receipt=qos)
    assert r['status']=='READY' and r['provenance_class']=='ASSUMED'
    assert r['ready_at_seconds']==900. and r['WAN_segments']==[]
    assert r['customer_permission_claim'] is False and r['measured_WAN_claim'] is False
    assert (m,row,qos)==before and m['can_prestart_place'] is False


@pytest.mark.parametrize('fact,value',[('can_prestart_place',False),('data_access_forbidden',True),
    ('protected',True),('batch_eligible',False),('qos','urgent'),('forbidden_destinations',['B'])])
def test_explicit_source_prohibitions_override_research(tmp_path,fact,value):
    p,m,row,record,qos=fixture(tmp_path)
    row[fact]=value
    p=ResearchPresiteProvider(p.spec,native_wan=p.wan)
    p.register_observed(m,source_authority(row,record,now=900),now=900)
    r=p.propose(m,'B',900.,day_begin=0,qos_receipt=qos)
    assert r['status']=='REJECTED' and not r['eligible']


def test_nonparticipant_not_blanket_ready_and_running_forbidden(tmp_path):
    p,m,row,record,qos=fixture(tmp_path)
    m['uid']=row['job_uid']=member(yes=False)
    p.register_observed(m,source_authority(row,record,now=900),now=900)
    assert p.propose(m,'B',900.,day_begin=0,qos_receipt=qos)['reason']=='OUTSIDE_EXISTING_FLEX30_RESEARCH_BATCH_CONTRACT'
    m['state']='RUNNING'
    assert p.propose(m,'B',900.,day_begin=0,qos_receipt=qos)['reason']=='ONLY_ACTUALLY_ARRIVED_UNKNOWN_PENDING'


def test_r2_rounding_payload_time_and_unchanged_qos(tmp_path):
    p,m,_,_,qos=fixture(tmp_path,scenario='R2',payload_multiplier=4.,bandwidth_fraction=.25,preparation_seconds=1.)
    r=p.propose(m,'B',900.,day_begin=0,qos_receipt=qos)
    assert r['payload_bytes']==6400. and r['bandwidth_bytes_per_second']==2.5
    assert r['transfer_seconds']==2700. and r['ready_at_seconds']==4500.
    assert r['status']=='REJECTED' and r['reason']=='ORIGINAL_QOS_HAS_NO_PREPARATION_DELAY_AUTHORITY'
    assert not p.transfers


def test_r2_atomic_concurrency_no_restart_and_ready_only_after_transfer(tmp_path):
    p,m,row,record,qos=fixture(tmp_path,scenario='R2',preparation_seconds=0.)
    r=p.propose(m,'B',900.,day_begin=0,qos_receipt=qos)
    assert r['status']=='PREPARATION_REQUIRED' and r['ready_at_seconds']==1800.
    ok,reason=p.commit_transfer(r,current_metadata=m,now=900.)
    assert ok and reason is None and p.transfer_history[0]['GPU_started'] is False
    m2=deepcopy(m);m2['uid']=member(skip=int(m['uid'])+1);row2=deepcopy(row);row2['job_uid']=m2['uid']
    p.register_observed(m2,source_authority(row2,record,now=900),now=900)
    r2=p.propose(m2,'B',900.,day_begin=0,qos_receipt=qos)
    assert r2['reason']=='RESEARCH_WAN_MAXIMUM_ACTIVE_TRANSFERS'
    with pytest.raises(ValueError,match='RESTART'):
        p.commit_transfer(r,current_metadata=m,now=900.)
    assert p.propose(m,'B',1800.,day_begin=0,qos_receipt=qos)['status']=='READY'
    assert p.propose(m,'B',4500.,day_begin=0,qos_receipt=qos)['reason']=='ORIGINAL_QOS_HAS_NO_PREPARATION_DELAY_AUTHORITY'


def test_hard_deadline_and_compatibility_preserved(tmp_path):
    p,m,_,_,qos=fixture(tmp_path,scenario='R2',preparation_seconds=0.)
    m['completion_deadline_seconds']=1900.
    assert p.propose(m,'B',900.,day_begin=0,qos_receipt=qos)['reason']=='SOURCE_PUBLIC_Q50_COMPLETION_DEADLINE'
    assert p.propose(m,'C',900.,day_begin=0,qos_receipt=qos)['reason']=='SOURCE_COMPATIBLE_AND_RESEARCH_ACCESS_DESTINATION_REQUIRED'


def test_future_or_mutated_authority_and_contract_rejected(tmp_path):
    p,m,row,record,_=fixture(tmp_path)
    with pytest.raises(ValueError,match='PREFIX'):
        source_authority(row,record,now=0.)
    a=source_authority(row,record,now=900.);a['public']['facts']['can_prestart_place']=True
    with pytest.raises(ValueError,match='AUTHORITY'):
        p.register_observed(m,a,now=900.)
    p.spec['ready_delay_slots']=99
    with pytest.raises(ValueError,match='MUTATED'):
        p.export()


def test_r2_parameter_ranges_change_science_and_prepare_not_source(tmp_path):
    p,_,_,_,_=fixture(tmp_path,scenario='R2',payload_multiplier=.25,bandwidth_fraction=1.,preparation_seconds=0.)
    q,_,_,_,_=fixture(tmp_path,scenario='R2',payload_multiplier=4.,bandwidth_fraction=.25,preparation_seconds=900.)
    assert p.science_sha!=q.science_sha
    assert p.spec['source_records']==q.spec['source_records']
    assert p.spec['additional_QoS_delay_granted_seconds']==q.spec['additional_QoS_delay_granted_seconds']==0


def test_registered_source_authority_sealed_at_every_candidate(tmp_path):
    p,m,_,_,qos=fixture(tmp_path)
    p.observed[m['uid']]['public']['facts']['can_prestart_place']=True
    with pytest.raises(ValueError,match='AUTHORITY_MUTATED'):
        p.propose(m,'B',900.,day_begin=0,qos_receipt=qos)

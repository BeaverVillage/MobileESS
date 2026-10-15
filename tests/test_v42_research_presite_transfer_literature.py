"""Named public fixtures only: per-job payload never adds delay authority."""
from copy import deepcopy
from pathlib import Path

import pytest

from v42_integration.experimental_qos import participation_for
from v42_integration.m_engine import file_record
from v42_integration.policy import digest
from v42_integration.research_presite_contract import ResearchPresiteProvider, make_spec, source_authority
from v42_integration.research_presite_transfer_literature import (
    LiteratureTransferProvider, PAYLOAD_MB, make_literature_spec, provider_decision_equivalence)

ROOT = Path(__file__).resolve().parents[1]
FACTS = ROOT/'docs/v42_unified_aidc_mess_research_20261014/RELEASE_RECOVERY_20261015/RC03/LITERATURE/LITERATURE_FACTS.json'


def member(*, yes=True, skip=0):
    return next(str(i) for i in range(skip, skip+1000)
                if participation_for(str(i))['membership']['FLEX30'] is yes)


def fixture(tmp_path, *, payload=100, bandwidth=1., prepare=0, gpu=2, facts=None):
    path = tmp_path/'NAMED_PUBLIC_FIXTURE_SOURCE.json'
    path.write_text('NAMED_PUBLIC_NUMERIC_FIXTURE_NOT_ACTUAL')
    record = file_record(path)
    wan = dict(bytes_per_gpu=80_000_000_000., maximum_active_transfers=1,
        paths=[dict(source='A', destination='B', links=['AB'])],
        link_capacity_bytes_15min=dict(AB=[900_000_000.]*20))
    spec = make_literature_spec(payload_MB=payload, bandwidth_fraction=bandwidth,
        preparation_seconds=prepare, literature_fact_record=file_record(FACTS),
        source_records=[record], native_wan_sha=digest(wan), shared_sites=['A','B'])
    p = LiteratureTransferProvider(spec, native_wan=wan)
    m = dict(uid=member(), submit_seconds=10., gpu=gpu, compatible_sites=['A','B'],
        reference_site='A', state='PENDING', origin_unknown=True, accumulated_compute_seconds=0.,
        t50_seconds=200., qos='UNCONFIRMED', protected=None, batch_eligible=None,
        can_prestart_place=False)
    row = dict(job_uid=m['uid'],submit_seconds=10.,GPU_gang=gpu,compatible_sites=['A','B'])
    row.update(facts or {})
    p.register_observed(m,source_authority(row,record,now=900),now=900)
    qos = dict(allowed_starts_seconds=[1800.,2700.,3600.,4500.],latest_start_seconds=4500.,budget_seconds=3600.)
    return p,m,row,record,qos


def test_static_original_decisions_differ_only_in_payload_expression():
    r=provider_decision_equivalence()
    assert r['status']=='PASS_SINGLE_PAYLOAD_EXPRESSION_DIFFERENCE'
    assert r['runtime_source_execution'] is False


@pytest.mark.parametrize('payload',PAYLOAD_MB)
def test_absolute_payload_gpu_independent_and_original_proxy_unchanged(tmp_path,payload):
    a,ma,_,_,qa=fixture(tmp_path,payload=payload,gpu=1)
    b,mb,_,_,qb=fixture(tmp_path,payload=payload,gpu=16)
    ra=a.propose(ma,'B',900.,day_begin=0,qos_receipt=qa)
    rb=b.propose(mb,'B',900.,day_begin=0,qos_receipt=qb)
    assert ra['payload_bytes']==rb['payload_bytes']==payload*1_000_000
    assert ra['transfer_seconds']==rb['transfer_seconds']==900.
    assert a.wan['bytes_per_gpu']==b.wan['bytes_per_gpu']==80_000_000_000.
    assert a.spec['Kestrel_task_type_mapping'] is None


def test_all_twenty_specs_are_separate_and_not_measured(tmp_path):
    shas=set()
    for payload in PAYLOAD_MB:
        for bandwidth in (.25,1.):
            for prepare in (0,900):
                p,_,_,_,_=fixture(tmp_path,payload=payload,bandwidth=bandwidth,prepare=prepare)
                shas.add(p.science_sha)
                assert p.spec['additional_QoS_delay_granted_seconds']==0
                assert p.spec['actual_input_payload_measured'] is False
                assert p.spec['actual_WAN_measured'] is False
    assert len(shas)==20


@pytest.mark.parametrize('payload',PAYLOAD_MB)
def test_strict_zero_qos_rejects_every_literature_payload(tmp_path,payload):
    p,m,row,_,_=fixture(tmp_path,payload=payload)
    qos=dict(allowed_starts_seconds=[],latest_start_seconds=900.,budget_seconds=0.)
    before=deepcopy((m,row,qos,p.wan))
    r=p.propose(m,'B',900.,day_begin=0,qos_receipt=qos)
    assert r['reason']=='ORIGINAL_QOS_HAS_NO_PREPARATION_DELAY_AUTHORITY'
    assert r['status']=='REJECTED' and not p.transfers
    assert (m,row,qos,p.wan)==before and m['can_prestart_place'] is False


@pytest.mark.parametrize('facts',[{'can_prestart_place':False},{'protected':True},
    {'qos':'urgent'},{'batch_eligible':False},{'data_access_forbidden':True},
    {'authorized_destinations':['A']},{'forbidden_destinations':['B']}])
def test_existing_source_exclusions_preserved(tmp_path,facts):
    p,m,_,_,qos=fixture(tmp_path,facts=facts)
    r=p.propose(m,'B',900.,day_begin=0,qos_receipt=qos)
    assert r['status']=='REJECTED' and not r['eligible']


def test_original_membership_state_and_causal_source_checks_preserved(tmp_path):
    p,m,row,record,qos=fixture(tmp_path)
    m['uid']=row['job_uid']=member(yes=False)
    p.register_observed(m,source_authority(row,record,now=900),now=900)
    assert p.propose(m,'B',900.,day_begin=0,qos_receipt=qos)['reason'].startswith('OUTSIDE_EXISTING_FLEX30')
    m['state']='RUNNING'
    assert p.propose(m,'B',900.,day_begin=0,qos_receipt=qos)['reason']=='ONLY_ACTUALLY_ARRIVED_UNKNOWN_PENDING'
    with pytest.raises(ValueError,match='SOURCE_PREFIX'):
        source_authority(row,record,now=0.)


def test_rounding_link_and_maxactive_capacity_and_source_windows(tmp_path):
    p,m,row,record,qos=fixture(tmp_path,payload=650,bandwidth=.25,prepare=900)
    r=p.propose(m,'B',900.,day_begin=0,qos_receipt=qos)
    assert r['transfer_seconds']==2700. and r['ready_at_seconds']==4500.
    assert r['transfer_seconds']>=r['payload_bytes']/r['bandwidth_bytes_per_second']
    assert r['WAN_path']==['AB'] and r['status']=='PREPARATION_REQUIRED'
    assert p.commit_transfer(r,current_metadata=m,now=900.)==(True,None)
    other=deepcopy(m);other['uid']=member(skip=int(m['uid'])+1)
    otherrow=deepcopy(row);otherrow['job_uid']=other['uid']
    p.register_observed(other,source_authority(otherrow,record,now=900),now=900)
    assert p.propose(other,'B',900.,day_begin=0,qos_receipt=qos)['reason']=='RESEARCH_WAN_MAXIMUM_ACTIVE_TRANSFERS'
    m['hard_latest_start_seconds']=4400.
    assert p.propose(m,'B',4500.,day_begin=0,qos_receipt=qos)['reason']=='SOURCE_LATEST_START_WINDOW'
    del m['hard_latest_start_seconds'];m['completion_deadline_seconds']=4600.
    assert p.propose(m,'B',4500.,day_begin=0,qos_receipt=qos)['reason']=='SOURCE_PUBLIC_Q50_COMPLETION_DEADLINE'


def test_original_and_new_numeric_decisions_equal_for_matched_payload(tmp_path):
    p,m,row,record,qos=fixture(tmp_path,payload=100)
    # A named synthetic WAN only: original payload equals the per-job example.
    wan=deepcopy(p.wan);wan['bytes_per_gpu']=50_000_000.
    old=ResearchPresiteProvider(make_spec(scenario='R2',source_records=[record],
        native_wan_sha=digest(wan),shared_sites=['A','B'],bandwidth_fraction=1.,preparation_seconds=0),native_wan=wan)
    old.register_observed(m,source_authority(row,record,now=900),now=900)
    a=old.propose(m,'B',900.,day_begin=0,qos_receipt=qos)
    b=p.propose(m,'B',900.,day_begin=0,qos_receipt=qos)
    for r in (a,b):
        r.pop('science_sha');r.pop('proposal_sha')
    assert a==b


def test_frozen_contract_authority_source_and_bad_values_rejected(tmp_path):
    p,m,_,record,qos=fixture(tmp_path)
    original_spec=deepcopy(p.spec)
    p.observed[m['uid']]['public']['facts']['can_prestart_place']=True
    with pytest.raises(ValueError,match='AUTHORITY_MUTATED'):
        p.propose(m,'B',900.,day_begin=0,qos_receipt=qos)
    p,m,_,_,qos=fixture(tmp_path)
    p.spec['absolute_payload_bytes_per_job']=1
    with pytest.raises(ValueError,match='MUTATED'):
        p.propose(m,'B',900.,day_begin=0,qos_receipt=qos)
    record_path=Path(record['path']);record_path.write_text('DRIFT')
    with pytest.raises(ValueError,match='SOURCE_BYTES_DRIFT'):
        LiteratureTransferProvider(original_spec,native_wan=p.wan)


@pytest.mark.parametrize('payload',[0,80,100.,True,651])
def test_no_new_sizes_or_gpu_proxy_implicitly_accepted(tmp_path,payload):
    with pytest.raises(ValueError,match='PAYLOAD_MB'):
        fixture(tmp_path,payload=payload)

"""Named Native0 counterexamples, not real AC/Actual96 certification."""
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pytest

from test_v43_actual_port import example, stats
from v43_actual.vendor.actual import JobRequest,run_actual
from v43_actual.vendor.policy import digest,ReservationLedger
from v43_actual.vendor.qos import CausalReferenceScheduler,QoSWindowProvider
from v43_corrective.reference import CorrectedReferenceScheduler
from v43_corrective.participation import ArrivalParticipation,change_authority
from v43_corrective.policy import CorrectivePolicy
from v43_corrective.controller import CorrectiveController
from v42_capacity.actual import Environment


def request(uid,submit=0.,site=None,compatible=('A','B'),q50=900.,**meta):
    m=dict(origin_unknown=True,protected=False,qos='normal',batch_eligible=True,
        representation_starts_seconds=tuple(float(t) for t in range(0,100801,900)))
    m.update(meta)
    return JobRequest(uid,submit,1,compatible,q50,site,m)


def metadata(uid='U'):
    return dict(uid=uid,submit_seconds=0.,origin_unknown=True,is_observed=True,state='PENDING',
        protected=False,qos='normal',gpu=1,compatible_sites=['A','B'],source_site='A',reference_site='A')


def participant_uid():
    for i in range(100):
        uid='NAMED_PARTICIPANT_'+str(i)
        if ArrivalParticipation().observe(metadata(uid),0.)['participant']:return uid
    raise AssertionError('NAMED_HASH_FIXTURE_NOT_FOUND')


def test_future_known_2200_does_not_block_unknown_0900_on_another_site():
    old=CausalReferenceScheduler({'A':1,'B':1},reference_sha='NAMED_REF')
    old.reservations['A']=[(22*3600.,23*3600.,1)]
    old.last_pending_start_seconds=22*3600.
    job=request('U',9*3600.,site='B')
    assert old.submit(job,event_seconds=9*3600.)['reference_start_seconds']==22*3600.
    new=CorrectedReferenceScheduler({'A':1,'B':1},reference_sha='NAMED_REF',
        reservations={'A':[(22*3600.,23*3600.,1)]},last_pending_start_seconds=22*3600.)
    assert new.submit(job,event_seconds=9*3600.)['reference_start_seconds']==9*3600.
    assert new.reservations['A']==[(22*3600.,23*3600.,1)]


def test_fifo_processing_allows_concurrent_different_site_and_preserves_same_site_booking():
    ref=CorrectedReferenceScheduler({'A':1,'B':1},reference_sha='NAMED_REF',reservations={'A':[(0.,1800.,1)]})
    rows=ref.submit_batch([request('Z',site='B'),request('A',site='A')],event_seconds=0.)
    assert [r['uid'] for r in rows]==['A','Z']
    assert [r['reference_start_seconds'] for r in rows]==[1800.,0.]
    assert ref.reservations['A'][0]==(0.,1800.,1)


def test_reference_deadline_is_not_extended_and_future_uid_cannot_enter():
    ref=CorrectedReferenceScheduler({'A':1},reference_sha='NAMED_REF',reservations={'A':[(0.,3600.,1)]})
    row=ref.submit(request('U',site='A',compatible=('A',),completion_deadline_seconds=1800.),event_seconds=0.)
    assert row['reference_feasible'] is False and ref.reservations['A']==[(0.,3600.,1)]
    with pytest.raises(ValueError,match='NOT_YET_SUBMITTED'):
        ref.submit(request('FUTURE',900.,compatible=('A',)),event_seconds=0.)


def test_arrival_hash_is_identical_across_arm_policy_and_reference_site():
    uid=participant_uid();m=metadata(uid);book=ArrivalParticipation();r=book.observe(m,0.)
    assert r['participant'] and not r['Source_verified']
    m['reference_site']='B'
    assert book.observe(m,900.)==r
    assert ArrivalParticipation().observe(m,0.)['hash_hex']==r['hash_hex']
    assert r['future_uid_population_reads']==0 and not r['intentional_timeshift_permission']


@pytest.mark.parametrize('field,value',[('protected',True),('qos','urgent'),('source_pre_site_forbidden',True)])
def test_ineligible_source_jobs_never_receive_r1_permission(field,value):
    m=metadata(participant_uid());m[field]=value
    assert not ArrivalParticipation().observe(m,0.)['participant']


def test_r1_destination_ban_and_running_hold_remain_binding():
    m=metadata(participant_uid());m['r1_flex30']=ArrivalParticipation().observe(m,0.)
    assert change_authority(m,'B',0.) is None
    m['source_forbidden_destinations']=['B']
    assert change_authority(m,'B',0.)=='SOURCE_DESTINATION_FORBIDDEN'
    m['state']='RUNNING'
    assert change_authority(m,'B',0.)=='R1_OBSERVED_PENDING_UNKNOWN_REQUIRED'


@pytest.mark.parametrize('field',['future_unknown_uids','actual_runtime_seconds','future_completion','completion_time'])
def test_private_future_data_fails_before_hash_or_reference_mutation(field):
    m=metadata();m[field]=123;book=ArrivalParticipation()
    with pytest.raises(ValueError,match='PRIVATE_REALIZATION'):book.observe(m,0.)
    assert not book.receipts


class NamedOracle:
    issue=0.
    now=None
    sites=('A','B')
    def __init__(self):
        self.calls=0;self.history=[]
        self.observations=SimpleNamespace(at=lambda *a,**k:dict(weather=dict(values={})))
        self.model=SimpleNamespace(recompute=lambda gpu,*a:dict(PCC_P_kw=np.array(gpu),PCC_Q_kvar=np.array(gpu)*0.))
    def observe(self,now,history):self.now=now;self.history=history
    def guard(self,*args):self.calls+=1;return None


def policy(variant='C1'):
    old,m,r,ledger=example();oracle=NamedOracle()
    p=CorrectivePolicy(old.reference,old.packet,variant=variant,oracle=oracle,
        bindings=old.bindings,expected_bindings=old.bindings,evidence_scope='NAMED_CORRECTIVE_FIXTURE')
    m.update(protected=False,qos='normal',source_site='A',uid=participant_uid())
    m['r1_flex30']=ArrivalParticipation().observe(m,0.)
    p.observe(0.,{'A':0,'B':0},{m['uid']:m});oracle.now=0.
    return p,m,r,ledger


def test_basic_impossible_alternative_possible_is_not_compared_to_impossible_score():
    p,m,r,l=policy();l.reserve('KNOWN',[dict(resource='gpu:A',begin=0.,end=900.,quantity=8)])
    d=p.select(m,r,0.,l)
    assert d['action']=='PREPLACE' and d['site']=='B'
    assert m['uid'] not in l.reservations  # selection is not execution


def test_all_alternatives_impossible_queue_and_c0_has_no_presite():
    for variant in ['C0','C1']:
        p,m,r,l=policy(variant)
        for s in ['A','B']:l.reserve(s,[dict(resource='gpu:'+s,begin=0.,end=900.,quantity=8)])
        assert p.select(m,r,0.,l)['action']=='QUEUE'
    p,m,r,l=policy('C0');l.reserve('A',[dict(resource='gpu:A',begin=0.,end=900.,quantity=8)])
    assert p.select(m,r,0.,l)['action']=='QUEUE'


def test_actual_ac_rejection_and_deadline_remain_hard():
    p,m,r,l=policy();p.oracle.guard=lambda *a:'NAMED_PHYSICAL_AC_REJECT'
    assert p.select(m,r,0.,l)['action']=='QUEUE'
    p,m,r,l=policy();m['completion_deadline_seconds']=1.
    assert p.select(m,r,0.,l)['action']=='QUEUE'


def test_real_affine_hard_gate_cannot_be_disabled_by_unverified_claim():
    p,m,r,l=policy();old,_,_,_=example()
    with pytest.raises(ValueError,match='CORRECTION_PROOF_REQUIRED'):
        CorrectivePolicy(old.reference,old.packet,variant='C1',oracle=p.oracle,
            bindings=old.bindings,expected_bindings=old.bindings,evidence_scope='NAMED_CORRECTIVE_FIXTURE',
            correction_proof=dict(root_cause_verified=True))


def event_run(variant,*,running_unknown=False,overrun=True):
    p,_,_,_=policy(variant);q=QoSWindowProvider(stats(),case_sha=p.bindings['case_sha'],provider_sha=digest('PROVIDER'))
    ref=CorrectedReferenceScheduler({'A':1,'B':1},reference_sha='NAMED_REF')
    uid=participant_uid()
    earlier=request('R',site='A',q50=900.,protected=True,origin_unknown=running_unknown)
    later=request(uid,1800.,site='A',q50=900.)
    p.observe(0.,{'A':0,'B':0},{})
    return run_actual({'A':1,'B':1},[earlier,later],Environment({'R':2700. if overrun else 900.,uid:300.}),
        arm='B1',qos_window_provider=q,frozen_policy=p,reference=ref,begin=0.,end=4500.,
        controller_class=CorrectiveController,expected_bindings=p.bindings),uid


@pytest.mark.parametrize('running_unknown',[False,True])
def test_observed_overrun_presite_really_starts_without_eviction(running_unknown):
    out,uid=event_run('C1',running_unknown=running_unknown)
    u=next(r for r in out['queue_ledger'] if r['job_uid']==uid)
    assert u['admitted_time']==1800. and u['site']=='B' and u['policy_action']=='PREPLACE'
    assert any(e['event']=='OVERRUN_OBSERVED' and e['uid']=='R' for e in out['job_event_ledger'])
    assert out['receipt']['capacity_violations']==out['receipt']['future_completion_controller_reads']==0
    assert out['receipt']['actual_compute_GPUh']>0 and out['receipt']['anonymous_physical_GPU']==0


def test_c0_c1_same_participants_c0_waits_and_actual_completion_releases_gpu():
    a,uid=event_run('C0');b,_=event_run('C1')
    get=lambda x:next(r for r in x['queue_ledger'] if r['job_uid']==uid)
    assert get(a)['admitted_time']==2700. and get(b)['admitted_time']==1800.
    rows=lambda x:[(e['uid'],e['participant'],e['receipt_sha']) for e in x['job_event_ledger'] if e['event']=='R1_PARTICIPATION_OBSERVED']
    assert rows(a)==rows(b)
    assert any(e['uid']=='R' and e['event']=='GPU_RELEASE_CONTROL' for e in a['job_event_ledger'])


def test_no_overrun_has_no_false_overrun_event():
    out,uid=event_run('C0',overrun=False)
    assert not any(e['event']=='OVERRUN_OBSERVED' for e in out['job_event_ledger'])


def test_failed_atomic_replacement_preserves_every_existing_reservation():
    l=ReservationLedger({'A':1,'B':1})
    l.reserve('U',[dict(resource='gpu:A',begin=0.,end=900.,quantity=1)])
    l.reserve('OTHER',[dict(resource='gpu:B',begin=0.,end=900.,quantity=1)])
    before=deepcopy(l.reservations)
    assert not l.reserve('U',[dict(resource='gpu:B',begin=0.,end=900.,quantity=1)],replace=True)[0]
    assert l.reservations==before


def test_future_known_command_remains_frozen_while_other_site_unknown_starts():
    p,_,_,_=policy('C0');q=QoSWindowProvider(stats(),case_sha=p.bindings['case_sha'],provider_sha=digest('PROVIDER'))
    ref=CorrectedReferenceScheduler({'A':1,'B':1},reference_sha='NAMED_REF',
        reservations={'A':[(3600.,4500.,1)]},last_pending_start_seconds=3600.)
    ref.assigned['K']=dict(uid='K',reference_site='A',reference_start_seconds=3600.,
        nominal_release_seconds=4500.,reference_sha=ref.reference_sha)
    commands={'K':dict(site='A',start_seconds=3600.,protected_segments=[dict(resource='gpu:A',begin=3600.,end=4500.,quantity=1)])}
    original=deepcopy(commands)
    out=run_actual({'A':1,'B':1},[request('K',site='A',origin_unknown=False,reference_start_seconds=3600.),
        request('U',900.,site='B',compatible=('B',))],Environment({'K':300.,'U':300.}),arm='B1',
        qos_window_provider=q,frozen_policy=p,reference=ref,known_schedule=commands,begin=0.,end=5400.,
        controller_class=CorrectiveController,expected_bindings=p.bindings)
    rows={r['job_uid']:r for r in out['queue_ledger']}
    assert rows['U']['admitted_time']==900. and rows['K']['admitted_time']==3600.
    assert rows['K']['site']=='A' and commands==original


def test_same_clock_identical_state_does_not_recheck_a_started_uid():
    p,_,_,_=policy('C0');q=QoSWindowProvider(stats(),case_sha=p.bindings['case_sha'],provider_sha=digest('PROVIDER'))
    c=CorrectiveController({'A':1,'B':1},arm='B1',qos_window_provider=q,frozen_policy=p,
        reference=CorrectedReferenceScheduler({'A':1,'B':1},reference_sha='NAMED_REF'))
    c.submit(request('U',site='A'),0.)
    assert c.admit(0.)==['U'];calls=p.oracle.calls
    assert c.admit(0.)==[] and p.oracle.calls==calls


def test_unknown_submission_depletes_cc4_once_despite_repeated_wait_ticks():
    from v42_final.workload import ForecastBook
    p,_,_,_=policy('C0');q=QoSWindowProvider(stats(),case_sha=p.bindings['case_sha'],provider_sha=digest('PROVIDER'))
    c=CorrectiveController({'A':1,'B':1},arm='B1',qos_window_provider=q,frozen_policy=p,
        reference=CorrectedReferenceScheduler({'A':1,'B':1},reference_sha='NAMED_REF'),
        forecast=ForecastBook(tuple([1.]*24),tuple([2.]*24),0.))
    c.submit(request('U',site='A',completion_deadline_seconds=1.),0.)
    c.admit(0.);c.admit(900.)
    assert len(c.cc4_ledger)==1 and c.cc4_ledger[0]['depletion_count']==1
    assert c.audit['U']['admitted_time'] is None

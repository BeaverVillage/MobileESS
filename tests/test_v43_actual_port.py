"""Independent signed-row, authority and event-boundary counterexamples."""
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pytest

from v43_actual.vendor.actual import JobRequest, run_actual
from v43_actual.vendor.current_ac_admission import CausalSeries
from v43_actual.vendor.policy import digest, ReservationLedger
from v43_actual.vendor.qos import TrainingStatistics, ObservedJob, QoSWindowProvider
from v43_actual.vendor.sensitivity_policy import OriginalGridPacket
from v43_actual.vendor.trajectory_tracking import TrackingReference
from v43_actual.vendor.unified_contract import BINDING_FIELDS
from v43_actual.presite import PendingPresitePolicy, change_authority
from v43_actual.windows import OriginalKnownWindows
from v42_capacity.actual import Environment


def stats():
    return TrainingStatistics(0.,digest('NAMED_TRAIN_SOURCE'),(),(),0,{},False,'NAMED_FIXTURE_ONLY')


def example(variant='C1', *, consent=False, future_voltage=False, current_ac=None):
    sites=('A','B'); names=('aidc_load_kw[A]','aidc_load_kw[B]')
    bindings={k:digest('NAMED_V43:'+k) for k in BINDING_FIELDS}
    sha=digest('NAMED_GRID_RESPONSE');bindings['response_sha']=sha
    coefs=[]
    for t in range(96):
        coefs.append(SimpleNamespace(slot=t,control_names=names,branch_names=('line.fixture::a',),
            coefficient_sha256=sha,anchor=np.zeros(2),voltage_constant=np.ones(1),
            voltage_matrix=np.array([[0.],[.2 if future_voltage and t==95 else 0.]]),
            current_constant=np.array([.4]),current_matrix=np.array([[.1],[-.1]]),
            flow_p_constant=np.zeros(1),flow_q_constant=np.zeros(1),
            flow_p_matrix=np.zeros((1,2)),flow_q_matrix=np.zeros((1,2)),
            branch_limits=np.ones(1),transformer_ratings=(None,)))
    z=np.zeros((96,2))
    aidc=dict(aidc_anchor=bindings['aidc_anchor'],AIDC_P_by_site={s:[0.]*96 for s in sites},
        AIDC_Q_by_site={s:[0.]*96 for s in sites})
    mess=dict(P_by_site={},Q_by_site={});mess['plan_sha']=digest(mess);bindings['mess_anchor']=mess['plan_sha']
    packet=OriginalGridPacket(coefs,{(s,t):SimpleNamespace(slope=1.) for s in sites for t in range(96)},
        1.,{'A':8,'B':8},aidc,mess,
        SimpleNamespace(voltage_lower_squared=.95**2,voltage_upper_squared=1.05**2),bindings,
        known_gpu=z,mess_validation=dict(plan_sha=mess['plan_sha'],frozen_execution_validated=True))
    ref=TrackingReference(z,z,z,z,z,sites=sites,begin=0.,commands={},identity={})
    policy=PendingPresitePolicy(ref,packet,variant=variant,
        current_ac_guard=current_ac or (lambda *args:None),bindings=bindings,expected_bindings=bindings,
        evidence_scope='NAMED_V43_COUNTEREXAMPLE')
    m=dict(uid='OBSERVED_NAMED_UID',origin_unknown=True,is_observed=True,state='PENDING',
        submit_seconds=0.,t50_seconds=86400. if future_voltage else 900.,gpu=1,
        reference_site='A',compatible_sites=['A','B'],can_prestart_place=consent,
        additional_start_delay_seconds=0.)
    if consent:
        a=dict(scope='SOURCE_VERIFIED_UID_DESTINATION_PRESTART',uid=m['uid'],destinations=['B'],
            source_sha=digest('NAMED_SOURCE_CONSENT'),observed_at_seconds=0.)
        a['authority_sha']=digest(a);m['source_presite_authority']=a
        m['source_data_ready']={'B':dict(uid=m['uid'],source_sha=digest('NAMED_READY_RECEIPT'),
            observed_at_seconds=0.,ready_at_seconds=0.,requires_new_transfer=False)}
    policy.observe(0.,{'A':0,'B':0},{m['uid']:m})
    receipt=dict(reference_start_seconds=0.,budget_seconds=0.,latest_start_seconds=0.,allowed_starts_seconds=(0.,))
    return policy,m,receipt,ReservationLedger({'A':8,'B':8})


def test_c0_c1_share_basic_without_source_consent():
    for variant in ('C0','C1'):
        p,m,r,ledger=example(variant)
        before=deepcopy(m)
        d=p.select(m,r,0.,ledger,reserve=False)
        assert d['site']=='A' and d['action']=='START' and m==before
        assert not ledger.reservations


def test_initial_study_permission_never_grants_source_change():
    p,m,r,ledger=example()
    m.update(initial_research_placement=True,initial_research_authority={'approved':True})
    assert p.select(m,r,0.,ledger,reserve=False)['site']=='A'


def test_verified_observed_ready_pending_can_choose_signed_better_site():
    p,m,r,ledger=example(consent=True)
    d=p.select(m,r,0.,ledger)
    assert d['site']=='B' and d['action']=='PREPLACE'
    assert d['tracking']['checked_grid_slots']==96 and d['online_global_optimizer_calls']==0


@pytest.mark.parametrize('field,value',[('observed_at_seconds',900.),('ready_at_seconds',900.),('requires_new_transfer',True)])
def test_future_or_unperformed_data_transfer_is_not_ready(field,value):
    p,m,r,ledger=example(consent=True)
    m['source_data_ready']['B'][field]=value
    assert p.select(m,r,0.,ledger,reserve=False)['site']=='A'


def test_last_slot_voltage_hard_rejects_current_better_destination():
    p,m,r,ledger=example(consent=True,future_voltage=True)
    d=p.select(m,r,0.,ledger,reserve=False)
    assert d['site']=='A'
    assert any(x['site']=='B' and 'VOLTAGE' in x['reason'] for x in d['rejected_candidates'])


def test_current_ac_guard_rejection_is_binding():
    guard=lambda m,segs,now,use:'CURRENT_AC_NOT_CERTIFIED' if segs[0]['resource']=='gpu:B' else None
    p,m,r,ledger=example(consent=True,current_ac=guard)
    assert p.select(m,r,0.,ledger,reserve=False)['site']=='A'


def test_running_or_known_cannot_enter_pending_selector():
    p,m,r,ledger=example(consent=True)
    m['state']='RUNNING'
    assert p.select(m,r,0.,ledger,reserve=False)['action']=='QUEUE'
    m['origin_unknown']=False
    with pytest.raises(ValueError,match='KNOWN_NEVER'):
        p.select(m,r,0.,ledger)


@pytest.mark.parametrize('field',['actual_runtime_seconds','future_completion','future_job_uid','completion_time'])
def test_private_future_aliases_fail_before_scoring(field):
    p,m,r,ledger=example()
    m[field]=1
    with pytest.raises(ValueError,match='PRIVATE_REALIZATION'):
        p.select(m,r,0.,ledger)


def test_original_known_windows_survive_unsupported_empirical_metadata():
    q=OriginalKnownWindows(stats(),case_sha=digest('CASE'),provider_sha=digest('PROVIDER'),issue_seconds=9000.,
        windows=[dict(job_id='K',reference_start=0,latest_start=7,allowed_starts=[0,3,7])])
    j=ObservedJob(uid='K',submit_seconds=0.,event_seconds=9000.,reference_start_seconds=9000.,
        t50_seconds=900.,gpu=1,origin_unknown=False,provider_sha=q.provider_sha,reference_sha=digest('REF'))
    receipt=q.issue(j)
    assert receipt.allowed_starts_seconds==(9000.,11700.,15300.)
    assert receipt.budget_seconds==6300 and receipt.policy_id=='PR189_ORIGINAL_KNOWN_WINDOWS'
    assert q.issue(replace(j,event_seconds=9900.)) is receipt


def test_unmodeled_running_continuation_grants_no_new_pending_window():
    q=OriginalKnownWindows(stats(),case_sha=digest('CASE'),provider_sha=digest('PROVIDER'),issue_seconds=9000.,
        windows=[],external_running=['EXTERNAL'])
    j=ObservedJob(uid='EXTERNAL',submit_seconds=0.,event_seconds=9000.,reference_start_seconds=9000.,
        t50_seconds=0.,gpu=1,origin_unknown=False,provider_sha=q.provider_sha,reference_sha=digest('REF'))
    with pytest.raises(ValueError,match='CANNOT_CREATE_PENDING'):
        q.issue(j)
    assert q.issue(replace(j,state='RUNNING')).budget_seconds==0


def test_asof_observations_disallow_future_update_and_interpolation():
    series=CausalSeries([dict(observed_seconds=0.,available_seconds=0.,values={'x':1.}),
        dict(observed_seconds=900.,available_seconds=1200.,values={'x':2.})],name='NAMED')
    assert series.at(900.,observed_now=900.)['values']['x']==1.
    with pytest.raises(ValueError,match='FUTURE_OBSERVATION'):
        series.at(1200.,observed_now=900.)


def test_observed_overrun_retains_whole_gang_until_private_completion():
    q=QoSWindowProvider(stats(),case_sha=digest('CASE'),provider_sha=digest('PROVIDER'))
    meta=dict(origin_unknown=False,state='RUNNING',elapsed_compute_seconds=900.,
        representation_starts_seconds=tuple(range(0,4500,900)))
    running=JobRequest('R',0.,1,('A',),100.,'A',meta)
    waiting=JobRequest('U',900.,1,('A',),100.,None,dict(origin_unknown=True,
        representation_starts_seconds=tuple(range(900,4500,900))))
    out=run_actual({'A':1},[waiting],Environment({'R':2600.,'U':300.},{'R':2600.}),
        arm='B0',qos_window_provider=q,running=[(running,'A',0.)],begin=900.,end=3600.)
    row=next(x for x in out['queue_ledger'] if x['job_uid']=='U')
    assert row['admitted_time']==2700. and out['receipt']['capacity_violations']==0
    assert out['receipt']['future_duration_controller_reads']==0

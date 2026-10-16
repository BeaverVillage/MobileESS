from copy import deepcopy
from types import SimpleNamespace
import random

import numpy as np

from test_v43_corrective import policy,request,participant_uid,NamedOracle,stats
from v43_actual.vendor.reservation_state import ContractReservationLedger
from v43_actual.vendor.aidc_sensitivity_runtime import SignedSensitivityPolicy
from v43_corrective.controller import CorrectiveReservations,CorrectiveController
from v43_corrective.reference import CorrectedReferenceScheduler
from v43_actual.vendor.actual import run_actual
from v43_actual.vendor.qos import QoSWindowProvider
from v43_actual.vendor.policy import digest
from v42_capacity.actual import Environment


def test_interval_sweep_matches_original_union_with_exclusion_and_overrun():
    rng=random.Random(232)
    owner=SimpleNamespace(known_schedule={},metadata={})
    fast=CorrectiveReservations(owner,capacities={'A':8,'B':8})
    old=ContractReservationLedger(owner,capacities={'A':8,'B':8})
    for state in range(25):
        rows={};plans={}
        for i in range(16):
            a=rng.randrange(6)*900.;b=a+rng.randrange(1,5)*900.
            s=dict(resource='gpu:'+rng.choice(['A','B']),begin=a,end=b,quantity=rng.randrange(1,5))
            rows[str(i)]=dict(status=rng.choice(['ACTIVE','RELEASED']),segments=[s])
            if i%3==0:plans[str(i)]=[dict(s,end=b+900)]
        for ledger in (old,fast):ledger.reservations=deepcopy(rows);ledger.known_plans=deepcopy(plans)
        fast.revision+=1
        for j in range(25):
            a=rng.randrange(6)*900.;candidate=[dict(resource='gpu:'+rng.choice(['A','B']),begin=a,
                end=a+rng.randrange(1,5)*900.,quantity=rng.randrange(1,5))]
            exclude=rng.choice([None,*rows])
            assert fast._fits(candidate,exclude=exclude)==old._fits(candidate,exclude=exclude)


def test_cached_public_future_matches_original_before_and_after_state_change():
    p,m,_,_=policy();m['reference_start_seconds']=0.;owner=SimpleNamespace(known_schedule={},metadata=p.metadata)
    ledger=CorrectiveReservations(owner,capacities={'A':8,'B':8})
    for i in range(4):
        row=dict(m,uid='PUBLIC_'+str(i),reference_start_seconds=i*900.,t50_seconds=1800.,
            state='PENDING' if i%2 else 'RUNNING',current_site='A',accumulated_compute_seconds=100.)
        p.metadata[row['uid']]=row
    for tick in (0.,900.,1800.):
        p.observe(tick,{'A':2,'B':0},p.metadata)
        for exclude in p.metadata:
            want=SignedSensitivityPolicy._public_future(p,ledger,exclude)
            got=p._public_future(ledger,exclude)
            for a,b in zip(want,got):np.testing.assert_allclose(a,b,rtol=0,atol=1e-12)
        ledger.reserve('BOOK'+str(tick),[dict(resource='gpu:B',begin=tick,end=tick+900.,quantity=1)])


def pending_overrun_canary():
    p,_,_,_=policy();q=QoSWindowProvider(stats(),case_sha=p.bindings['case_sha'],provider_sha=digest('PROVIDER'))
    uid=participant_uid()
    rows=[request('A_HOLD',site='A',q50=900.,protected=True,origin_unknown=False),
        request('B_HOLD',site='B',compatible=('B',),q50=900.,protected=True),
        request(uid,1800.,site='A',q50=900.)]
    out=run_actual({'A':1,'B':1},rows,Environment({'A_HOLD':4500.,'B_HOLD':2700.,uid:300.}),arm='B1',
        qos_window_provider=q,frozen_policy=p,reference=CorrectedReferenceScheduler({'A':1,'B':1},reference_sha='FIXTURE'),
        begin=0.,end=5400.,controller_class=CorrectiveController,expected_bindings=p.bindings)
    job=next(r for r in out['queue_ledger'] if r['job_uid']==uid)
    attempts=[r for r in p.audit if r['uid']==uid]
    assert attempts[0]['decision']['action']=='QUEUE'
    assert job['admitted_time']==2700. and job['site']=='B' and job['policy_action']=='PREPLACE'
    assert any(r['decision']['action']=='PREPLACE' for r in attempts)
    assert any(r['event']=='OVERRUN_OBSERVED' and r['uid']=='A_HOLD' for r in out['job_event_ledger'])
    assert out['migration_receipts']==[]
    return dict(scope='NAMED_EVENT_FIXTURE_NOT_REAL_GRID_CERTIFICATION',uid=uid,attempts=attempts,
        actual_job=job,events=out['job_event_ledger'],receipt=out['receipt'])


def test_pending_overrun_is_reconsidered_then_presite_starts():
    pending_overrun_canary()

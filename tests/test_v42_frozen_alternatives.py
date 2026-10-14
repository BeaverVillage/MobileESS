"""Independent rank, protected reservations, and same-row execution tests."""
from copy import deepcopy
from types import SimpleNamespace
import numpy as np
import pytest

from v42_integration.policy import ReservationLedger
from v42_integration.reservation_state import ContractReservationLedger,union_job_segments
from v42_integration.anonymous_allocation import spatial_frames
from test_v42_known_unknown_contract import frozen,participant
from test_v42_experimental_control import metadata,policy


def test_FIRST_FEASIBLE_FROZEN_FALLBACK_SELECTED(monkeypatch):
    provider,p=frozen();job,receipt=participant(provider);m=metadata(provider,job,receipt)
    ledger=ReservationLedger({'A':8,'B':8})
    for s in ('A','B'):ledger.reserve('prior_'+s,[dict(resource='gpu:'+s,begin=0,end=900,quantity=8)])
    ledger.reserve('future_Known',[dict(resource='gpu:B',begin=1800,end=3600,quantity=8)])
    p.set_current_resources(0,{'A':0,'B':0})
    decision=p.select(m,receipt,0,ledger)
    assert decision['start_seconds']==900 and decision['site']=='B'
    ledger.release('prior_A',900);ledger.release('prior_B',900)
    ledger.retain_running('overrun','B',900,1800,8)
    fixed=deepcopy(ledger.reservations['future_Known']);before=p.packet.evaluation_calls
    monkeypatch.setattr(p.packet,'evaluate',lambda *a,**k:(_ for _ in ()).throw(AssertionError('Actual grid objective score')))
    fallback=p.revalidate_command(m,receipt,900,ledger,decision,{'A':0,'B':8},failure_reason='GPU_CAPACITY')
    assert fallback['site']=='A' and fallback['start_seconds']==900
    assert fallback['rule_id']==decision['rule_id'] and fallback['frozen_alternative_rank']>decision['frozen_alternative_rank']
    assert fallback['reservation_replaced_atomically'] and ledger.reservations['future_Known']==fixed
    assert p.packet.evaluation_calls==before and m['additional_start_delay_seconds']==900


def test_KNOWN_HARD_RESERVATION_PROTECTED():
    owner=SimpleNamespace(known_schedule={'K':dict(site='B',protected_segments=[dict(resource='gpu:B',begin=900,end=2700,quantity=8)])},metadata={})
    ledger=ContractReservationLedger(owner,capacities={'A':8,'B':8})
    assert ledger.feasible([dict(resource='gpu:B',begin=0,end=1800,quantity=1)])=='NO_CAPACITY'
    assert ledger.known_plans['K']==owner.known_schedule['K']['protected_segments']
    assert ledger.snapshot()['anonymous_Q50_physical_reservations']==0


def test_RUNNING_OVERRUN_CAPACITY_PROTECTED():
    owner=SimpleNamespace(known_schedule={},metadata={'R':{'state':'RUNNING'}})
    ledger=ContractReservationLedger(owner,capacities={'A':8,'B':8})
    ledger.reserve('R',[dict(resource='gpu:A',begin=0,end=9000,quantity=8)])
    ledger.retain_running('R','A',0,900,8)
    assert ledger.feasible([dict(resource='gpu:A',begin=0,end=900,quantity=1)])=='NO_CAPACITY'
    # A future nominal forecast is soft; the actual overrun is checked again
    # before admission at that future clock, with no eviction.
    assert ledger.feasible([dict(resource='gpu:A',begin=900,end=1800,quantity=1)]) is None
    ledger.retain_running('R','A',900,1800,8)
    assert ledger.feasible([dict(resource='gpu:A',begin=900,end=1800,quantity=1)])=='NO_CAPACITY'
    assert ledger.reservations['R']['status']=='ACTIVE'


def test_NO_FUTURE_HARD_CAPACITY_VIOLATION():
    ledger=ReservationLedger({'A':8,'B':8})
    ledger.reserve('committed',[dict(resource='gpu:A',begin=900,end=2700,quantity=8)])
    snapshot=deepcopy(ledger.reservations)
    assert ledger.reserve('new',[dict(resource='gpu:A',begin=1800,end=3600,quantity=1)])[0] is False
    assert ledger.reservations==snapshot


def test_Q50_SERVICE_AND_Q90_EXTRA_MASS_CONSERVATION():
    provider,p=frozen(service_reallocation=True)
    assert p.document['service_reallocation'] and len(p.document['anonymous_service_frames'])>1
    for frame in p.document['anonymous_service_frames'].values():
        assert frame['certificate']['Q50_CDF_and_mass_unchanged']
        if frame['frame_id']=='BASE':continue
        delta=np.zeros((96,2))
        for t,s,value in frame['sparse_site_GPU_delta']:delta[t,['A','B'].index(s)]=value
        np.testing.assert_allclose(delta.sum(axis=1),0.,atol=1e-12)
    assert all(m['conservation_PASS'] for t in p.expanded_document()['templates'] for r in t['ordered_actions'] for m in r['q90_mass_conservation'])


def test_same_UID_known_and_observed_holds_are_not_counted_twice():
    segments=[dict(resource='gpu:A',begin=0,end=1800,quantity=4),dict(resource='gpu:A',begin=900,end=2700,quantity=4)]
    assert union_job_segments(segments)==[dict(resource='gpu:A',begin=0,end=2700,quantity=4,scope='physical')]


def test_independent_all_sites_and_delays_match_frozen_P1_scores():
    condition=dict(state='PENDING',qos='normal',gpu=1,reference_site='A',compatible_sites=['A','B'],
        runtime_lower_seconds=0.,runtime_upper_seconds=900.,time_slots=[0])
    provider,p=frozen(conditions=[condition]);t=p.expanded_document()['templates'][0]
    original=policy(provider)
    scores=t['scenario_comparisons']
    assert {(r['site'],r['delay_seconds']) for r in scores}=={(s,d) for s in ('A','B') for d in (0,900,1800)}
    # Independent scalar source equation: flow rows are zero in this named toy,
    # so the signed 16-face anchor correction equals the literal current row.
    from v42_integration.q90_recourse import evaluate_q90_recourse
    independent=[]
    for row in scores:
        worst=0.;exposure=0.;risk=[]
        for service in row['runtime_endpoints_seconds']:
            peaks=[];delta=np.zeros((96,2))
            for slot,c in enumerate(p.packet.coefficients):
                control=p.packet.controls[slot].copy()
                a,b=slot*900,(slot+1)*900
                ref=max(0.,min(b,service)-max(a,0.))/900
                after=max(0.,min(b,row['delay_seconds']+service)-max(a,row['delay_seconds']))/900
                control[0]-=ref;control[0 if row['site']=='A' else 1]+=after
                delta[slot,0]-=ref;delta[slot,0 if row['site']=='A' else 1]+=after
                peaks.append(max(0.,float((c.current_constant+c.current_matrix.T@control)[0])))
            worst=max(worst,max(peaks))
            exposure=max(exposure,sum(peaks)*.25)
            recourse=evaluate_q90_recourse(p.packet,original.nominal,original.q90,original.cdf_lower,original.cdf_upper,
                candidate_gpu_delta=delta,remaining_slot=0,source_authority=original.recourse_authority)
            risk.append(recourse)
        assert row['q50_primary_score']==pytest.approx(worst,abs=1e-12)
        if row['hard_feasible']:
            independent.append((worst,(max(len(r['CDF_timing_violations']) for r in risk),
                max(r['CDF_lower_max_deficit_GPUh'] for r in risk),max(r['risk_total_unfinished_GPUh'] for r in risk),
                max(r['queue_area_GPUh_hours'] for r in risk),exposure,
                max(r['original_grid_score']['peak_score'] for r in risk),row['delay_seconds'],
                row['action'] not in ('START_NOW','STAY'),False,row['site'],'BASE'),(row['site'],row['delay_seconds'])))
    assert t['ordered_actions'][0]['q50_primary_score']==min(r['q50_primary_score'] for r in scores)
    independent.sort(key=lambda r:r[0]);expected=[]
    while independent:
        first=independent[0][0]
        n=next((i for i,r in enumerate(independent) if r[0]-first>1e-9),len(independent))
        peers,independent=independent[:n],independent[n:]
        expected.extend(r[2] for r in sorted(peers,key=lambda r:r[1]))
    assert [(r['site'],r['delay_seconds']) for r in t['ordered_actions']]==expected

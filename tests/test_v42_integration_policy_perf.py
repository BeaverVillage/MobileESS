"""Policy cache/index boundaries: immutable API, exact rows and reservations."""
from copy import deepcopy

import pytest

from v42_integration.policy import compile_policy,FrozenControlPolicy,ReservationLedger


def fixture():
    bindings={key:key for key in ('science_sha','qos_sha','case_sha','aidc_anchor','mess_anchor')}
    envelope=[dict(site=site,slot_start=t,slot_end=t+900,gpu_capacity=4,
                   source_variable='anonymous:'+site+':'+str(t),carryout_end=3600)
              for t in (-900,0,900,1800,2700) for site in ('A','B')]
    effects={(r['site'],r['slot_start']):(float(r['slot_start']/900)*(1 if r['site']=='A' else -1),.125)
             for r in envelope}
    return compile_policy(envelope,bindings,effects)


def request(policy):
    meta=dict(uid='observed',submit_seconds=0,state='PENDING',is_observed=True,
        qos='normal',protected=False,t50_seconds=1200,gpu=2,compatible_sites=['A','B'])
    receipt=dict(uid='observed',case_sha=policy.bindings['case_sha'],allowed_starts_seconds=[0,900],
        reference_start_seconds=0,budget_seconds=900)
    return meta,receipt


def test_index_matches_original_order_at_negative_fractional_and_half_open_boundaries():
    policy=fixture();document=policy.document
    for time in (-901,-900,-1,0,.5,899.9,900,1800,3599,3600):
        expected=[r for r in document['rules'] if r['slot_start']<=time<r['slot_end']]
        assert policy.rules_at(time)==expected
    assert policy.envelope_for_interval('A',850,1850)==[
        r for r in document['envelope'] if r['site']=='A' and r['slot_start']<1850 and r['slot_end']>850]


def test_public_document_bindings_and_rule_copies_cannot_mutate_execution_or_sha():
    policy=fixture();meta,receipt=request(policy)
    expected=policy.candidates(meta,receipt,0);sha=policy.sha
    doc=policy.document;doc['bindings']['case_sha']='changed'
    doc['rules'][2]['signed_grid_effect_vector'][0]=1e100
    assert doc['envelope'][2]['signed_grid_effect_vector'][0]!=1e100
    policy.bindings['case_sha']='changed'
    rows=policy.rules_at(0);rows[0]['gpu_capacity']=0
    rows[0]['signed_grid_effect_vector'][0]=1e100
    assert policy.candidates(meta,receipt,0)==expected and policy.sha==sha
    assert policy.document['rules'][2]['signed_grid_effect_vector'][0]!=1e100


def test_effect_cache_preserves_signed_multislot_exact_sum_and_mutable_return_independence():
    policy=fixture()
    # Original left-to-right sum: A starts with0, then .5GPU-slot on vector1.
    assert policy._effect('A',0,1350,2)==[1.,.375]
    first=policy._effect('A',0,1350,2);first[0]=999
    assert policy._effect('A',0,1350,2)==[1.,.375]
    assert policy._effect('B',0,1350,2)==[-1.,.375]
    assert policy._effect('A',2700,4000,2) is None


def test_candidate_vector_mutation_does_not_poison_later_query_or_reservation():
    policy=fixture();meta,receipt=request(policy)
    candidates,status=policy.candidates(meta,receipt,0)
    reference=deepcopy(candidates)
    candidates[0]['signed_grid_effect_vector'][0]=1e100
    candidates[0]['segments'][0]['quantity']=999
    assert policy.candidates(meta,receipt,0)==(reference,status)
    a=policy.select(meta,receipt,0,ReservationLedger({'A':4,'B':4}),reserve=False)
    b=policy.select(meta,receipt,0,ReservationLedger({'A':4,'B':4}),reserve=True)
    assert a==b and a['action'] in {'START','DELAY'}


def test_shared_budget_and_atomic_whole_interval_capacity_still_reject_candidates():
    policy=fixture();meta,receipt=request(policy)
    meta['cumulative_migration_interruption_seconds']=900
    choices,_=policy.candidates(meta,receipt,0)
    assert all(c['start_seconds']==0 for c in choices)
    ledger=ReservationLedger({'A':4,'B':4})
    for site in ('A','B'):
        assert ledger.reserve('full:'+site,[dict(resource='gpu:'+site,begin=0,end=3600,quantity=4)])[0]
    decision=policy.select(meta,receipt,0,ledger)
    assert decision['action']=='QUEUE' and all(r['reason']=='NO_CAPACITY' for r in decision['rejected_candidates'])


def test_reload_is_identical_and_stale_binding_or_running_start_immutable(tmp_path):
    policy=fixture();meta,receipt=request(policy)
    path=tmp_path/'POLICY.json';policy.save(path)
    reload=FrozenControlPolicy.load(path,bindings=policy.bindings)
    assert reload.document==policy.document and reload.candidates(meta,receipt,0)==policy.candidates(meta,receipt,0)
    with pytest.raises(ValueError,match='ANCHOR_MISMATCH'):
        reload.require_bindings(dict(policy.bindings,mess_anchor='stale'))
    meta['state']='RUNNING'
    assert reload.candidates(meta,receipt,0)==([], 'RUNNING_START_IMMUTABLE')


def test_wide_interval_index_does_not_expand_dense_time_grid_and_cache_is_bounded():
    bindings={key:key for key in ('science_sha','qos_sha','case_sha','aidc_anchor','mess_anchor')}
    policy=compile_policy([dict(site='A',slot_start=0,slot_end=9000000,gpu_capacity=4,source_variable='wide')],
        bindings,{('A',0):(1.,-2.)})
    assert len(policy.rules_at(4500000.5))==1 and not policy.rules_at(9000000)
    for i in range(300):policy._effect('A',i,1000+i,1)
    assert len(policy._FrozenControlPolicy__effect_cache)==256
    assert policy._effect('A',0,1000,1)==[1000/900.,-2000/900.]

from dataclasses import replace
from fractions import Fraction
import numpy as np
import pytest
from test_v42_a_stage_phase1 import block_fixture
from v42_a_stage_phase1.producer import native_block
from v42_a_stage_domain_v2.domain import physical_domain
from v42_a_stage_early.candidate import validate,expanded_graph,point_for_option
from v42_a_stage_early.policy import trigger,stagnated
from v42_a_stage_early.budget import Budget
from v42_a_stage_early.native import BudgetStop
from v42_job_capability import Option

@pytest.mark.parametrize('N',(1,2,3))
@pytest.mark.parametrize('migration',(False,True))
def test_concrete_native_physical_exact_coupling_replay(N,migration):
    data,g,axes=block_fixture(N);snap,B,_,units=native_block(data,'c',g,axes)
    cache=dict(snapshot=snap,B=B,units=units,graph=g)
    uid='j0';job=data[1][uid];domain=physical_domain(job,data[2][uid],data[3])
    if migration:
        start,source,cp,physical,dest,gpu,taus=domain.blocks[0];tau=taus[0]
        tx=domain.cache.transfer(source,dest,gpu,tau);end=tx.restart+job.service_slots-(cp-start)
        option=Option(start,source,((source,start,cp),(dest,tx.restart,end)),cp,physical,dest,tau,tx.end,tx.restart,tx.wan)
    else:
        start,site=domain.stays[0];option=Option(start,site,((site,start,start+job.service_slots),))
    pi=np.asarray([((i*17)%11-5)/8 for i in range(len(axes))])
    result=validate(cache,job,data[2][uid],data[3],domain,data[4][uid],data[0],{k:i for i,k in enumerate(axes)},pi,N,0,option,'c')
    assert result['native_local_replay']['PASS'] and result['exact_coupling_PASS']
    assert result['independent_price_PASS'] and result['physical_membership_PASS']
    if not migration:
        with pytest.raises(ValueError,match='MEMBERSHIP'):
            validate(cache,job,data[2][uid],data[3],domain,data[4][uid],data[0],{k:i for i,k in enumerate(axes)},pi,N,0,replace(option,start=-1),'c')

def test_original_coupling_mutation_fails_independently():
    data,g,axes=block_fixture(2);snap,B,_,units=native_block(data,'c',g,axes)
    job=data[1]['j0'];domain=physical_domain(job,data[2]['j0'],data[3]);start,site=domain.stays[0]
    option=Option(start,site,((site,start,start+4),));point=point_for_option(dict(snapshot=snap,units=units,graph=g),job,data[3],option,2)
    j=int(np.flatnonzero(point)[0]);bad=B.copy().tolil();bad[0,j]+=1;bad=bad.tocsr()
    with pytest.raises(ValueError,match='COUPLING'):
        validate(dict(snapshot=snap,B=bad,units=units,graph=g),job,data[2]['j0'],data[3],domain,data[4]['j0'],data[0],{k:i for i,k in enumerate(axes)},np.ones(len(axes)),2,0,option,'c')

def test_early_16_or_24_and_stagnation_rules_are_fixed():
    assert not trigger(15,23)
    assert trigger(16,1) and trigger(0,24)
    assert stagnated([.009,.0,-.001],1)
    assert not stagnated([.009,.0,-.001],0)
    assert not stagnated([.02,.0,0.],1)

def test_single_wall_native_budget_and_parallel_reservations(monkeypatch):
    import v42_a_stage_early.budget as module
    monkeypatch.setattr(module,'perf_counter',lambda:100.)
    budget=Budget(started=0);budget.charge(200)
    assert budget.accounted()==200 and budget.reservation(4)==175
    budget.charge(700)
    with pytest.raises(BudgetStop):budget.remaining()

def test_stay_activation_preserves_every_existing_native_primitive():
    data,g,axes=block_fixture(2);domain=physical_domain(data[1]['j0'],data[2]['j0'],data[3])
    start,site=domain.stays[0];o=Option(start,site,((site,start,start+4),))
    expanded=expanded_graph(g,o,data[1]['j0'],domain,False)
    for n in g.events:assert set(g.events[n])<=set(expanded.events[n])
    for n in g.states:assert set(g.states[n])<=set(expanded.states[n])
    assert all(expanded.physical[k]==v for k,v in g.physical.items())

def test_raw_backstop_rejects_other_date_integer_or_wrong_model(monkeypatch):
    from types import SimpleNamespace
    from v42_a_stage_early import execution
    model=SimpleNamespace(NumIntVars=0)
    token=execution._scope.set((model,'2025-05-19','PHASE_I',lambda:100))
    try:
        execution.guard(model,'2025-05-19')
        with pytest.raises(PermissionError):execution.guard(model,'2025-05-17')
        with pytest.raises(PermissionError):execution.guard(SimpleNamespace(NumIntVars=0),'2025-05-19')
        model.NumIntVars=1
        with pytest.raises(PermissionError):execution.guard(model,'2025-05-19')
        with pytest.raises(PermissionError):execution.authorize('2025-05-19','ACTUAL')
    finally:execution._scope.reset(token)

def test_numerical_phi_increase_with_prior_inclusion_is_not_forced_stop():
    from test_v42_a_stage_phase1 import snapshot
    from v42_a_stage_phase1.core import elastic_master
    from v42_a_stage_early.progress import capture,inclusion_witness
    first=snapshot([(1,1)]);before=elastic_master(first,(0,1))
    descriptor=dict(units=[dict(id='j',v=dict(y={('A',0):('v',0)}))])
    raw=dict(X=np.asarray([1.,0.,0.,1.]))
    prior=capture(first,descriptor,before,raw)
    new=snapshot([(1,1),(1,0)]);after=elastic_master(new,(0,1))
    expanded=dict(units=[dict(id='j',v=dict(y={('A',0):('v',0),('B',0):('v',1)}))])
    witness,point=inclusion_witness(prior,new,expanded,after,0)
    assert witness['PASS'] and witness['mapped_Phi']==witness['previous_Phi']
    assert np.array_equal(raw['X'],[1.,0.,0.,1.])
    assert point[1]==0 and witness['separate_projection']

def test_prior_point_witness_rejects_nonincluded_row_or_weight():
    from test_v42_a_stage_phase1 import snapshot
    from v42_a_stage_phase1.core import elastic_master
    from v42_a_stage_early.progress import capture,inclusion_witness
    first=snapshot([(1,1)]);before=elastic_master(first,(0,1))
    descriptor=dict(units=[dict(id='j',v=dict(y={('A',0):('v',0)}))])
    prior=capture(first,descriptor,before,dict(X=np.asarray([1.,0.,0.,1.])))
    changed=replace(first,rhs=np.asarray([2.,0.]));after=elastic_master(changed,(0,1),weights_by_row={r:w for r,w in zip(before.artificial_rows,before.weights)})
    witness,_=inclusion_witness(prior,changed,descriptor,after,0)
    assert not witness['PASS']
    prior['weights']=tuple(w*2 for w in prior['weights'])
    with pytest.raises(ValueError,match='WEIGHT'):inclusion_witness(prior,changed,descriptor,after,0)

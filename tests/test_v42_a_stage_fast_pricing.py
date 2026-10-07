"""Exact native primitive/block pricing tests; no optimizer calls."""
from dataclasses import replace
from fractions import Fraction
from types import SimpleNamespace
import json

import numpy as np
import pytest
import scipy.sparse as sp

from v42_a_stage_domain_v2.lexstage import LinearSnapshot,Objective
from v42_a_stage_domain_v2.fast_pricing import (NativeExtension,NativeLocalBlock,
    verify_primal,verify_dual,verify_farkas,price_native_extension,
    verify_local_pricing,verify_local_farkas,local_pricing_snapshot,select_batch,require_milp_pricing_gate,
    score_active_pools,verify_active_pool_scores,parse_baseline_log,_migration_prefix)


def snapshot(matrix,rhs,senses,coefficients,lower=None,upper=None):
    matrix=sp.csr_matrix(np.asarray(matrix,dtype=float));n=matrix.shape[1]
    return LinearSnapshot(matrix,np.zeros(n) if lower is None else np.asarray(lower,dtype=float),
        np.ones(n) if upper is None else np.asarray(upper,dtype=float),np.asarray(senses),
        np.asarray(rhs,dtype=float),np.full(n,'C'),
        (Objective('rho',tuple((i,value) for i,value in enumerate(coefficients) if value)),)).require()


def test_exact_dual_keeps_original_bound_multipliers_and_does_not_ignore_tiny_residual():
    model=snapshot([[1]],[0],['>'],[-1],upper=[2])
    cert=verify_dual(model,[0],'rho',[2])
    assert cert['PASS'] and cert['lower_bound']=='-2' and cert['exact_LP_optimum']
    assert not cert['LP_PRICING_CLOSED']
    model=snapshot([[1]],[0],['>'],[0],upper=[np.inf])
    assert not verify_dual(model,[Fraction(1,10**30)],'rho')['PASS']
    assert not verify_dual(model,[-1],'rho')['PASS']


def test_farkas_prices_original_native_primitive_that_breaks_restricted_certificate():
    active=snapshot([[1]],[2],['='],[0])
    full=snapshot([[1,1]],[2],['='],[0,0])
    bridge=NativeExtension(active,full,(0,),(0,),((1,'new_finish_direction'),))
    receipt=price_native_extension(bridge,[-1],mode='feasibility')
    assert receipt['active_certificate']['PASS']
    assert not receipt['extension_certificate']['PASS']
    assert receipt['negative_native_primitives'][0]['price']=='-1'
    assert receipt['candidate_blocks']==['new_finish_direction']
    assert not receipt['LP_PRICING_CLOSED']
    # A new column with too little bound capacity does NOT break the full ray.
    short=replace(full,upper=np.array([1,.5]))
    receipt=price_native_extension(replace(bridge,extended=short),[-1],mode='feasibility')
    assert receipt['finite_extension_infeasible']
    assert receipt['extension_certificate']['contradiction_margin']=='1/2'
    assert not receipt['extension_certificate']['SCIENTIFIC_DOMAIN_INFEASIBLE']


def test_exact_farkas_signs_and_infinite_bound_fail_closed():
    model=snapshot([[1]],[2],['>'],[0])
    assert verify_farkas(model,[-1])['PASS']
    assert not verify_farkas(model,[1])['PASS']
    assert not verify_farkas(replace(model,upper=np.array([np.inf])),[-1])['PASS']


def test_finite_native_lp_extension_is_certified_but_never_full_scientific_closure():
    active=snapshot([[1]],[1],['>'],[1],upper=[2])
    full=snapshot([[1,0],[0,1]],[1,0],['>','>'],[1,2],upper=[2,1])
    bridge=NativeExtension(active,full,(0,),(0,),((1,'new_state'),))
    cert=price_native_extension(bridge,[1],mode='optimality',point=[1])
    assert cert['finite_extension_LP_closed']
    assert cert['extension_certificate']['lower_bound']=='1'
    assert not cert['LP_PRICING_CLOSED']
    with pytest.raises(PermissionError,match='MILP_BLOCKED'):
        require_milp_pricing_gate(cert)


def test_added_local_row_zero_dual_alone_does_not_prove_primal_lift():
    active=snapshot([[1]],[1],['>'],[1],upper=[2])
    full=snapshot([[1,0],[1,-1]],[1,0],['>','='],[1,0],upper=[2,2])
    cert=price_native_extension(NativeExtension(active,full,(0,),(0,),((1,'local_state'),)),
        [1],mode='optimality',point=[1])
    assert cert['extension_certificate']['PASS']
    assert not cert['extension_certificate']['primal']['PASS']
    assert not cert['finite_extension_LP_closed']


@pytest.mark.parametrize('mutation',['matrix','rhs','objective','bounds','mapping','uncovered'])
def test_native_extension_rejects_shared_science_or_primitive_coverage_drift(mutation):
    active=snapshot([[1]],[1],['>'],[1])
    full=snapshot([[1,0]],[1],['>'],[1,0])
    bridge=NativeExtension(active,full,(0,),(0,),((1,'x'),))
    if mutation=='matrix':bridge=replace(bridge,extended=replace(full,matrix=sp.csr_matrix([[2.,0.]])))
    elif mutation=='rhs':bridge=replace(bridge,extended=replace(full,rhs=np.array([2.])))
    elif mutation=='objective':bridge=replace(bridge,extended=replace(full,objectives=(Objective('rho',((0,2),)),)))
    elif mutation=='bounds':bridge=replace(bridge,extended=replace(full,upper=np.array([2.,1.])))
    elif mutation=='mapping':bridge=replace(bridge,column_map=(1,))
    else:bridge=replace(bridge,column_blocks=())
    with pytest.raises(ValueError):bridge.verify()


def test_full_original_local_flow_oracle_includes_fractional_finish_counterexample():
    # ORIGINAL one-start, one-finish, r0 balances and total service=1.
    # Columns: y0,y1,y2,f1,f2,f3,r0[0],r0[1],r0[2].
    rows=[[1,1,1,0,0,0,0,0,0],[0,0,0,1,1,1,0,0,0],
        [-1,0,0,0,0,0,1,0,0],[0,-1,0,1,0,0,-1,1,0],
        [0,0,-1,0,1,0,0,-1,1],[0,0,0,0,0,1,0,0,-1],
        [0,0,0,0,0,0,1,1,1]]
    local=snapshot(rows,[1,1,0,0,0,0,1],['=']*7,[0,1,0,1,0,1,0,0,0])
    fractional=[Fraction(1,2),0,Fraction(1,2),0,1,0,Fraction(1,2),Fraction(1,2),0]
    assert verify_primal(local,fractional)['PASS']
    # Every deterministic duration-one physical STAY costs1. The ORIGINAL
    # flow's fractional finish at2 costs0 and is absent from their convex hull.
    for start in range(3):
        point=[0]*9;point[start]=1;point[3+start]=1;point[6+start]=1
        assert verify_primal(local,point)['PASS']
        assert sum(Fraction(c)*p for c,p in zip([0,1,0,1,0,1,0,0,0],point))==1
    block=NativeLocalBlock('mixed',local,sp.csr_matrix((1,9)),(0,),'rho')
    receipt=verify_local_pricing(block,[0],[0]*7,fractional)
    assert receipt['certificate']['exact_LP_optimum']
    assert receipt['certificate']['lower_bound']=='0'
    assert receipt['fractional_finish_directions_included']
    assert not receipt['LP_PRICING_CLOSED']


def test_native_local_pricing_uses_actual_coupling_objective_and_bounds():
    local=snapshot([[1,1]],[1],['='],[0,0])
    block=NativeLocalBlock('c',local,sp.csr_matrix([[2.,0.]]),(0,),'rho')
    derived=local_pricing_snapshot(block,[1])
    assert derived.objective('native_local_pricing').coefficients()=={0:Fraction(-2)}
    receipt=verify_local_pricing(block,[1],[-2],[1,0])
    assert receipt['certificate']['exact_LP_optimum']
    assert receipt['certificate']['lower_bound']=='-2'
    farkas=verify_local_farkas(block,[-1],[-2],[1,0])
    assert farkas['certificate']['exact_LP_optimum']
    assert farkas['certificate']['lower_bound']=='-2'
    assert not farkas['SCIENTIFIC_DOMAIN_INFEASIBLE']


def test_batch_orders_exact_prices_and_retains_unselected_small_negatives():
    scores=[dict(candidate_id='b',class_id='c',price='-1'),
        dict(candidate_id='a',class_id='c',price='-1'),
        dict(candidate_id='tiny',class_id='c',price='-1/1000000000000000000000')]
    result=select_batch(scores,batch_size=1,negative_threshold=Fraction(-1,1000))
    assert result['selected'][0]['candidate_id']=='a'
    assert result['skipped_small_negative']==1 and not result['LP_PRICING_CLOSED']


def adapter_fixture():
    from v42_job_capability import Job,ServiceBoundary,Resources
    from v42_a_stage_domain_v2.domain import physical_domain
    from v42_a_stage_domain_v2.active import StayPool,MigrationPool,_intervals
    job=Job('j','PENDING',0,0,4,'A',2,2,initial_sites=('A','B'),duration_authority='SYNTHETIC')
    bound=ServiceBoundary('SYNTHETIC',True,True,(4,5),10)
    resources=Resources({'A':8,'B':8},{'A':(4,),'B':(4,)},{},{},12,4,{},{},{})
    domain=physical_domain(job,bound,resources);active=frozenset({(4,'A')})
    pool=StayPool('c','j',1,job,domain,active,_intervals(set(domain.stays)-active),False)
    row_keys={};values=[];weights=[]
    for site in ('A','B'):
        for slot in range(10):
            row_keys['GPU',(site,slot)]=len(values)
            values.append([-2. if site=='A' and slot in (4,5) else 0.])
            weights.append(-1. if site=='A' and slot in (0,1) else 0.)
        for slot in range(24,120):
            row_keys['Runtime',(site,slot)]=len(values);values.append([0.]);weights.append(0.)
    norm=len(values);values.append([1.]);weights.append(0.)
    native=snapshot(values,[0.]*norm+[1.],['=']*len(values),[0])
    native=replace(native,objectives=tuple(Objective(name,()) for name in
        ('rho','migration_count','shift_magnitude','prestart_relocation')))
    raw={'risk_nominal_completion_issue_slot':6,'reference_end':6}
    data=({'runtime_reserve_gamma':1.,'runtime_survival_kernel':[.5]},
          {'j':job},{'j':bound},resources,{'j':raw},{},{},{'classes':{'c':['j']}})
    backend=SimpleNamespace(current=native,row_keys=row_keys,data=data,domains={'j':domain},
        descriptor={'units':[dict(class_key='c',optional=False,stay_count=True,v={'y':{('A',4):('v',0)}})]},
        ledger={'stay_pools':{'c':pool},'migration_pools':{'c':MigrationPool('c',domain,frozenset())}},
        policy={'batch':{'initial':2,'minimum':1,'maximum':4},'max_pricing_iterations':4})
    build=SimpleNamespace(model=SimpleNamespace(getAttr=lambda name:weights))
    return backend,build


def test_production_adapter_uses_histogram_native_identity_and_fails_closed_after_full_path_scan():
    backend,build=adapter_fixture()
    pricing=score_active_pools(backend,build,'OPTIMALITY',0)
    assert pricing['candidates_activated']==2
    assert pricing['certificate']['exhaustive_inactive_STAY_scanned']
    assert pricing['certificate']['exhaustive_migration_scanned']
    assert pricing['certificate']['actual_histogram_column_identities']=={'c':True}
    assert not pricing['LP_PRICING_CLOSED']
    pricing['mode']='OPTIMALITY'  # Runner wrapper adds its public uppercase mode.
    assert verify_active_pool_scores(backend,build,pricing,'OPTIMALITY')['PASS']
    pricing['selected_scores'][0]['price']='-999'
    assert not verify_active_pool_scores(backend,build,pricing,'OPTIMALITY')['PASS']


def test_last_iteration_never_activates_an_unsolved_final_batch():
    backend,build=adapter_fixture()
    pricing=score_active_pools(backend,build,'OPTIMALITY',3)
    assert pricing['trace']['improving_candidates']>0
    assert pricing['trace']['last_iteration_activation_prohibited']
    assert pricing['candidates_activated']==0 and pricing['selections']=={}


def test_independent_activation_replay_rejects_normalization_metadata_tampering():
    backend,build=adapter_fixture()
    pricing=score_active_pools(backend,build,'OPTIMALITY',0)
    pricing['selected_scores'][0]['normalization_rows']=()
    verification=verify_active_pool_scores(backend,build,pricing,'OPTIMALITY')
    assert not verification['PASS']
    assert 'ORIGINAL_NATIVE_NORMALIZATION_REPLAY_MISMATCH' in verification['errors']


def test_baseline_log_parser_preserves_distinct_native_clocks_and_timeout_meaning():
    text='''Optimize a model with 4417827 rows, 4316192 columns and 49651657 nonzeros (Min)
Presolved: 2958547 rows, 3718260 columns, 16895324 nonzeros
Root relaxation presolved: 2930311 rows, 3709978 columns, 16393728 nonzeros
Ordering time: 140.09s
 Factor NZ  : 1.562e+09 (roughly 15.0 GB of memory)
 52 7.30210831e-01 7.30174548e-01 1.51e-07 8.44e-13 5.60e-12 3463s
Barrier performed 52 iterations in 3605.14 seconds (4586.45 work units)
Root relaxation: time limit, 0 iterations, 3520.71 seconds (4393.98 work units)
Explored 1 nodes (0 simplex iterations) in 3606.64 seconds (4588.84 work units)
'''
    receipt=parse_baseline_log(text,{'native_seconds':3606.6459999084473,'status':9,'objective':None})
    assert receipt['classification']=='COMPLETE_STAY_ALL_ACTIVE_ROOT_TIMEOUT'
    assert receipt['ordering_seconds']==140.09
    assert receipt['factor_nnz_rounded_from_log']==1562000000
    assert receipt['barrier_summary_seconds']==3605.14
    assert receipt['root_relaxation_summary_seconds']==3520.71
    assert receipt['native_Runtime_seconds']==3606.6459999084473
    assert not receipt['infeasible'] and not receipt['scientific_domain_fail']
    assert receipt['barrier_log_iterations'][-1]['iteration']==52

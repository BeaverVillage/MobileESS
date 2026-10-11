"""Exact affine range extension: LP/integer projection and mutation rejection."""
import copy
from fractions import Fraction
import json

import numpy as np
import pytest
from scipy import sparse
from scipy.optimize import linprog

from v42_ultracompact.response import ReformulationResult,reformulate_responses,state_sha
from v42_ultracompact.response_verify import verify_response_reformulation


def model(rows=None,names=None,senses=None,rhs=None):
    if rows is None:
        rows=[[1.,2.,-1.,0.,0.],[1.,2.,-1.,0.,0.],
            [0.,1.,1.,2.,0.],[0.,1.,1.,2.,0.],[1.,1.,0.,0.,-1.]]
        names=['voltage_lower[0,0]','voltage_upper[0,0]',
            'voltage_lower[1,0]','voltage_upper[1,0]','physical_test']
        senses=['>','<','>','<','<'];rhs=[-.5,2.75,-1.,3.,0.]
    A=sparse.csr_matrix(np.asarray(rows,dtype=float));n=A.shape[1]
    d=dict(names=np.asarray([f'physical_{j}' for j in range(n)]),
        types=np.asarray(['B']+['C']*(n-1)),lower=np.asarray([0.]+[-2.]*(n-2)+[0.]),
        upper=np.asarray([1.]+[2.]*(n-2)+[10.]),objective=np.asarray([0.]*(n-1)+[1.]),
        constant=np.asarray(0.),row_names=np.asarray(names),sense=np.asarray(senses),rhs=np.asarray(rhs))
    return A,d


def solve(A,d,objective=None,fixed_binary=None):
    less=d['sense']=='<';more=d['sense']=='>';equal=d['sense']=='='
    ub=sparse.vstack((A[less],-A[more]),format='csr')
    bounds=list(zip(d['lower'],d['upper']))
    if fixed_binary is not None:bounds[0]=(fixed_binary,fixed_binary)
    return linprog(d['objective'] if objective is None else objective,
        A_ub=ub,b_ub=np.concatenate((d['rhs'][less],-d['rhs'][more])),
        A_eq=A[equal] if equal.any() else None,b_eq=d['rhs'][equal] if equal.any() else None,
        bounds=bounds,method='highs')


def feasible(A,d,x):
    value=A@x;eps=1e-8
    assert np.all(x>=d['lower']-eps) and np.all(x<=d['upper']+eps)
    assert np.all(value[d['sense']=='<']<=d['rhs'][d['sense']=='<']+eps)
    assert np.all(value[d['sense']=='>']>=d['rhs'][d['sense']=='>']-eps)
    assert np.all(np.abs(value[d['sense']=='=']-d['rhs'][d['sense']=='='])<=eps)


def test_projection_equivalence_for_distinct_lp_objectives_and_binary_fixings():
    A,d=model();result=reformulate_responses(A,d)
    assert result.proof['PASS'] and result.proof['original_variable_projection_equivalent']
    assert result.A.shape==(3,7) and result.proof['nnz_reduction']==4
    assert result.proof['original_auxiliaries_deleted']==0
    objectives=[d['objective'],np.asarray([1.,-.75,.25,-.5,0.]),np.asarray([-1.,.5,-.125,.75,0.])]
    for fixed in (None,0,1):
        for objective in objectives:
            old=solve(A,d,objective,fixed)
            new=solve(result.A,result.d,np.concatenate((objective,[0.,0.])),fixed)
            assert old.success==new.success
            if old.success:
                assert new.fun==pytest.approx(old.fun,abs=1e-8)
                feasible(result.A,result.d,result.forward(old.x))
                restored=result.inverse(new.x);feasible(A,d,restored)
                assert np.array_equal(restored,new.x[:A.shape[1]])


def test_actual_stored_rhs_and_duplicate_expressions_across_node_ids():
    lower=np.nextafter(.9025,-np.inf);upper=np.nextafter(1.1025,np.inf)
    A,d=model(rows=[[1.,2.,3.],[1.,2.,3.],[1.,2.,3.]],
        names=['voltage_lower[2,8]','voltage_lower[2,9]','voltage_upper[2,17]'],
        senses=['>','>','<'],rhs=[lower,np.nextafter(lower,np.inf),upper])
    result=reformulate_responses(A,d)
    assert len(result.plans)==1 and result.A.shape==(1,4)
    assert Fraction(float(result.d['lower'][-1]))==Fraction(float(d['rhs'][1]))
    assert Fraction(float(result.d['upper'][-1]))==Fraction(float(d['rhs'][2]))
    assert result.d['rhs'][-1]==0
    assert result.proof['nnz_reduction']==5


def test_nonzero_subnormal_is_preserved_exactly():
    tiny=np.nextafter(0.,1.)
    A,d=model(rows=[[1.,-2.,tiny],[1.,-2.,tiny]],
        names=['voltage_lower[0,0]','voltage_upper[0,0]'],senses=['>','<'],rhs=[-3.,3.])
    result=reformulate_responses(A,d)
    assert result.A.nnz==4
    assert Fraction(float(result.A[0,2]))==-Fraction(float(tiny))
    assert result.proof['coefficient_zeroing_thresholds_used']==0


@pytest.mark.parametrize('kind',['ONE_ULP_COEFFICIENT','DISTINCT_SLOT','UNPAIRED','FILL_WORSE'])
def test_unhelpful_or_nonidentical_sharing_is_not_selected(kind):
    width=2 if kind=='FILL_WORSE' else 3
    vector=list(map(float,range(1,width+1)))
    rows=[vector,vector.copy()];names=['voltage_lower[0,0]','voltage_upper[0,0]']
    senses=['>','<']
    if kind=='ONE_ULP_COEFFICIENT':rows[1][0]=np.nextafter(1.,np.inf)
    elif kind=='DISTINCT_SLOT':names[1]='voltage_upper[1,0]'
    elif kind=='UNPAIRED':names[1]='line_thermal_face[0,0,0]'
    A,d=model(rows=rows,names=names,senses=senses,rhs=[-3.,3.])
    result=reformulate_responses(A,d)
    assert not result.plans and not result.proof['structural_improvement']
    assert result.A is A and np.array_equal(result.d['names'],d['names'])


@pytest.mark.parametrize('mutation',['INWARD_LB','INWARD_UB','OUTWARD_UB','ORIGINAL_OBJECTIVE',
    'NEW_OBJECTIVE','NEW_INTEGER_TYPE','ORIGINAL_INTEGER_TYPE','ORIGINAL_BOUND','RETAINED_ROW',
    'NEW_EQUALITY_COEFFICIENT','NEW_EQUALITY_RHS','ORIGINAL_REMOVED_RHS','ORIGINAL_REMOVED_LHS',
    'PLAN_SLOT','REPEATED_DELETION','AXIS'])
def test_independent_verifier_rejects_mutations(mutation):
    A,d=model();result=copy.deepcopy(reformulate_responses(A,d));e=result.d
    if mutation=='INWARD_LB':e['lower'][-1]=np.nextafter(e['lower'][-1],np.inf)
    elif mutation=='INWARD_UB':e['upper'][-1]=np.nextafter(e['upper'][-1],-np.inf)
    elif mutation=='OUTWARD_UB':e['upper'][-1]=np.nextafter(e['upper'][-1],np.inf)
    elif mutation=='ORIGINAL_OBJECTIVE':e['objective'][0]=1.
    elif mutation=='NEW_OBJECTIVE':e['objective'][-1]=1.
    elif mutation=='NEW_INTEGER_TYPE':e['types'][-1]='B'
    elif mutation=='ORIGINAL_INTEGER_TYPE':e['types'][0]='C'
    elif mutation=='ORIGINAL_BOUND':e['upper'][0]=2.
    elif mutation=='RETAINED_ROW':result.A.data[0]=np.nextafter(result.A.data[0],np.inf)
    elif mutation=='NEW_EQUALITY_COEFFICIENT':result.A.data[-1]=np.nextafter(1.,np.inf)
    elif mutation=='NEW_EQUALITY_RHS':e['rhs'][-1]=np.nextafter(0.,1.)
    elif mutation=='ORIGINAL_REMOVED_RHS':result.original_data['rhs'][0]=np.nextafter(-.5,-np.inf)
    elif mutation=='ORIGINAL_REMOVED_LHS':result.original.data[0]=np.nextafter(1.,np.inf)
    elif mutation=='PLAN_SLOT':result.plans[0]['slot']=9
    elif mutation=='REPEATED_DELETION':result.plans[1]['rows']=result.plans[0]['rows'].copy()
    elif mutation=='AXIS':result.row_ids[-1]=0
    with pytest.raises(ValueError):verify_response_reformulation(result)


def test_sha_binds_transport_and_domains_but_not_cosmetic_proof_labels():
    result=reformulate_responses(*model());before=state_sha(result)
    result.proof['scientific_source_SHAs']={'example':'abc'}
    assert state_sha(result)==before
    result.plans[0]['lower_row']=result.plans[0]['upper_row']
    assert state_sha(result)!=before


def test_point_axes_and_skipping_fresh_independent_proof_are_rejected():
    A,d=model();result=reformulate_responses(A,d)
    with pytest.raises(ValueError):result.forward(np.zeros(A.shape[1]+1))
    with pytest.raises(ValueError):result.inverse(np.zeros(result.A.shape[1]-1))
    with pytest.raises(ValueError):reformulate_responses(A,d,independent_replay=False)


def test_saved_dense_stage_replays_and_preserves_both_transport_maps(tmp_path):
    result=reformulate_responses(*model())
    before=state_sha(result)
    for prefix,A,d in [('C3A',result.original,result.original_data),('DENSE',result.A,result.d)]:
        sparse.save_npz(tmp_path/(prefix+'_A.npz'),A)
        np.savez_compressed(tmp_path/(prefix+'_DATA.npz'),**d)
    np.savez_compressed(tmp_path/'AXES.npz',rows=result.row_ids,columns=result.col_ids)
    (tmp_path/'PLANS.json').write_text(json.dumps(result.plans),encoding='utf-8')
    (tmp_path/'PROOF.json').write_text(json.dumps(result.proof),encoding='utf-8')
    with np.load(tmp_path/'C3A_DATA.npz',allow_pickle=False) as z:
        original_data={k:z[k].copy() for k in z.files}
    with np.load(tmp_path/'DENSE_DATA.npz',allow_pickle=False) as z:
        selected_data={k:z[k].copy() for k in z.files}
    with np.load(tmp_path/'AXES.npz',allow_pickle=False) as z:
        row_ids,col_ids=z['rows'].copy(),z['columns'].copy()
    restored=ReformulationResult(sparse.load_npz(tmp_path/'C3A_A.npz'),original_data,
        sparse.load_npz(tmp_path/'DENSE_A.npz'),selected_data,row_ids,col_ids,
        json.loads((tmp_path/'PLANS.json').read_text(encoding='utf-8')),
        json.loads((tmp_path/'PROOF.json').read_text(encoding='utf-8')))
    assert verify_response_reformulation(restored)['PASS'] and state_sha(restored)==before
    point=np.asarray([.375,.25,-.125,.5,2.])
    assert np.array_equal(restored.forward(point),result.forward(point))
    assert np.array_equal(restored.inverse(restored.forward(point)),point)

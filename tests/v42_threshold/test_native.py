import gurobipy as gp
import numpy as np
import pytest
from v42_threshold.common import *
from v42_threshold.routes import path_validation

@pytest.fixture(scope='module')
def native():
    env=gp.Env(empty=True);env.setParam('OutputFlag',0);env.start();m=threshold_model(env)
    yield m
    m.dispose();env.dispose()

def test_threshold_only_matrix_delta(native):
    env=gp.Env(empty=True);env.setParam('OutputFlag',0);env.start();base=gp.read(str(LOCAL/'F3.mps'),env=env)
    A=base.getA();B=native.getA()[:-1]
    assert np.array_equal(A.data,B.data) and np.array_equal(A.indices,B.indices) and np.array_equal(A.indptr,B.indptr)
    assert native.getAttr('RHS')[:-1]==base.getAttr('RHS') and native.getAttr('Sense')[:-1]==base.getAttr('Sense')
    assert native.getAttr('LB')==base.getAttr('LB') and native.getAttr('UB')==base.getAttr('UB')
    assert native.getAttr('VarName')==base.getAttr('VarName')
    base.dispose();env.dispose()

def test_single_threshold_row_and_constant_objective(native):
    A=native.getA();i=native.getAttr('VarName').index('rho_max')
    assert A[-1].nnz==1 and A[-1].indices[0]==i and A[-1].data[0]==1
    assert native.getConstrs()[-1].RHS==T and native.getConstrs()[-1].Sense=='<'
    assert np.count_nonzero(native.getAttr('Obj'))==0 and native.ObjCon==0

def test_exact_B3_domains_and_no_route_deletion(native):
    assert native.NumVars==316743 and native.NumBinVars==85744
    assert np.array_equal(np.asarray(native.getAttr('VType'))=='B',domains())
    assert np.array_equal(native.getAttr('VarName'),axis()['names'])
    assert native.NumConstrs==954561 and native.NumNZs==8282351

def test_initial_and_terminal_SOC_retained(native):
    a=axis();rhs=native.getAttr('RHS');senses=native.getAttr('Sense')
    initial=np.flatnonzero(a['rownames']=='initial_SOC')
    assert len(initial)==len(a['terminal_rows'])==4
    assert all(rhs[int(i)]==760 and senses[int(i)]=='=' for i in a['terminal_rows'])
    broken=full_start().copy();i=list(a['names']).index('SOC[MESS01,96]');broken[i]+=1
    assert not matrix_validation(native,broken,include_threshold=False)['PASS']

def test_original_complete_start_is_preserved_but_threshold_infeasible(native):
    v=full_start();assert matrix_validation(native,v,include_threshold=False)['PASS']
    assert not matrix_validation(native,v)['PASS']
    assert v[list(axis()['names']).index('rho_max')]==ORIGINAL_UB>T

def test_broken_flow_and_PCS_detected(native):
    v=full_start().copy();names=list(axis()['names']);i=next(i for i,n in enumerate(names) if n.startswith('arc[') and v[i]==1);v[i]=0
    assert not matrix_validation(native,v,include_threshold=False)['PASS']
    v=full_start().copy();n=next(str(n) for n in names if str(n).startswith('Pdis['));suffix=n[5:]
    v[names.index(n)]=300;v[names.index('Pch['+suffix)]=0;v[names.index('Q['+suffix)]=400
    assert not matrix_validation(native,v,include_threshold=False)['PASS']

def test_candidates_are_legal_and_count_preregistered():
    p=read(OUT/'PREREGISTRATION.json');c=read(OUT/'ROUTE_WITNESS_CANDIDATES.json')
    assert p['candidate_count']==c['candidate_count']==2
    _,_,_,_,initial,_,_=inputs()
    for candidate in c['candidates']:
        for u,chosen in candidate['routes'].items():assert path_validation(arcs(),initial[u],chosen)['PASS']

def test_scientific_grid_voltage_and_physics_preserved():
    a=read(OUT/'B3_THRESHOLD_MATRIX_IDENTITY.json');p=read(OUT/'PREREGISTRATION.json')
    assert a['full96_grid_retained'] and a['PCS16_retained'] and a['robust_voltage']==[.955,1.045]
    assert a['removed_rows']==a['route_pruning']==0 and a['new_rows']==1
    assert p['B1_optimize_calls']==p['B2_optimize_calls']==0 and not any(p[k] for k in ['production','P2','downstream','new_cuts'])

def test_independent_full_matrix_physical_and_grid_validator(native):
    from v42_threshold.validate import validate_point
    result,_=validate_point(native,axis()['names'],full_start())
    assert result['B3_feasible_PASS'] and result['physical']['full96'] and result['grid']['full96']
    assert result['original_M1_UB_eligible'] and not result['threshold_certificate_PASS']
    assert result['grid']['no_Actual_PQ_repair'] and result['grid']['robust_grid']['voltage_band']==[.955,1.045]

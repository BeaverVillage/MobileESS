"""Exact outer intervals and honest unknowns, without a model/optimizer."""
from dataclasses import replace
from fractions import Fraction as F
from types import SimpleNamespace

import numpy as np
import pytest
from scipy import sparse

from test_v42_physical_prescreen import domain
from v42_native.contracts import ContractError,digest
from v42_native.grid_prescreen import build_grid_prescreen,verify_grid_original_rows,GRID_FAMILIES,_domain_sha
from v42_m1_hybrid.blocks import matrix_sha


def fixture():
    physical=domain(H=2)
    controls=('aidc_load_kw[IDC]','mess_p_kw[A]','mess_q_kvar[A]',
        'mess_p_kw[B]','mess_q_kvar[B]')
    coefficients=[SimpleNamespace(slot=t,coefficient_sha256=str(t)*64,control_names=controls)
        for t in range(2)]
    grid=build_grid_prescreen(physical,coefficients,[[1.25,0.,0.,0.,0.]]*2)
    names=[];lower=[];upper=[]
    def column(name,lo,hi):
        names.append(name);lower.append(lo);upper.append(hi);return len(names)-1
    for t in range(2):
        for family,lo,hi in [('Pch',0,300),('Pdis',0,300),('Q',-400,400)]:
            column(f'{family}[MESS01,A,{t}]',lo,hi)
    for t in range(2):
        for site in ('A','B'):
            for family in ('injection_P','injection_Q'):column(f'{family}[{site},{t}]',-np.inf,np.inf)
    rho=column('rho_max',0,1)
    y=column('response_line_P[0,0]',-np.inf,np.inf)
    z=column('response_line_Q[0,0]',-np.inf,np.inf)
    lookup={name:j for j,name in enumerate(names)};rows=[];labels=[];senses=[];rhs=[]
    def row(label,sense,right,terms):
        rows.append(terms);labels.append(label);senses.append(sense);rhs.append(right)
    for t in range(2):
        for site in ('A','B'):
            for family in ('injection_P','injection_Q'):
                j=lookup[f'{family}[{site},{t}]'];terms={j:1.}
                if site=='A':
                    for raw,weight in ([('Q',-1.)] if family=='injection_Q' else [('Pch',1.),('Pdis',-1.)]):
                        terms[lookup[f'{raw}[MESS01,A,{t}]']]=weight
                row(family+'_binding','=',0.,terms)
    ip=lookup['injection_P[A,0]'];iq=lookup['injection_Q[A,0]']
    row('response_line_P_binding[0,0]','=',.375,{y:1.,ip:-2.,iq:.5})
    row('response_line_Q_binding[0,0]','=',-.125,{z:1.,y:-3.,ip:1.})
    row('voltage_lower[0,0]','>',-300.,{ip:1.})
    row('voltage_upper[0,0]','<',300.,{ip:1.})
    row('line_thermal_face[0,0,0]','<',10000.,{y:1.,z:1.,rho:-1.})
    row('transformer_kVA[0,0,0]','<',10000.,{z:1.})
    row('NormalAmps[0,0]','<',10000.,{z:1.})
    row('transformer_current[0,0]','<',10000.,{z:1.})
    matrix=np.zeros((len(rows),len(names)))
    for i,terms in enumerate(rows):
        for j,w in terms.items():matrix[i,j]=w
    data=dict(names=np.asarray(names),types=np.full(len(names),'C'),lower=np.asarray(lower,float),
        upper=np.asarray(upper,float),objective=np.eye(1,len(names),rho).ravel(),constant=np.asarray(0.),
        row_names=np.asarray(labels),sense=np.asarray(senses),rhs=np.asarray(rhs,float))
    return grid,sparse.csr_matrix(matrix),data


def test_all_six_families_current_stored_response_dag_and_lp_outer_boxes():
    grid,A,d=fixture();before=A.copy();domains={k:v.copy() for k,v in d.items()}
    receipt=grid.receipt();proof=verify_grid_original_rows(grid,A,d)
    assert receipt['PASS'] and receipt['actual_original_row_bridge_required']
    assert proof['PASS'] and not proof['entire_model_infeasible']
    assert proof['original_matrix_sha']==matrix_sha(A) and proof['original_domain_sha']==_domain_sha(d)
    assert proof['stored_affine_equalities_cached']==2
    assert all(proof['per_family'][f]['rows_exactly_measured']==1 for f in GRID_FAMILIES)
    assert proof['coefficient_zeroing_thresholds_used']==proof['Native_optimize_calls']==0
    assert (A!=before).nnz==0 and all(np.array_equal(d[k],domains[k]) for k in d)
    # Boxes include the fractional aggregate origin controls and every other
    # reachable site, independently of any particular path/Forecast point.
    source=next(b for b in grid.boxes if b[:2]==('A',0))
    assert source[3:]==(F(-300),F(300),F(-400),F(400))
    unavailable=next(b for b in grid.boxes if b[:2]==('B',0))
    assert unavailable[2:]==((),F(0),F(0),F(0),F(0))


@pytest.mark.parametrize('sense,rhs',[('<',-301.),('>',301.)])
def test_strict_outer_minimum_only_proves_entire_model_infeasible(sense,rhs):
    grid,A,d=fixture();i=list(d['row_names']).index('voltage_upper[0,0]')
    d['sense'][i]=sense;d['rhs'][i]=rhs
    proof=verify_grid_original_rows(grid,A,d)
    assert proof['entire_model_infeasible'] and len(proof['infeasibility_witnesses'])==1
    witness=proof['infeasibility_witnesses'][0]
    assert F(witness['strict_positive_margin_exact'])==1
    assert proof['route_or_column_or_row_deletions']==0


def test_unknown_unbounded_response_is_not_mistaken_for_infeasibility():
    grid,A,d=fixture();i=list(d['row_names']).index('response_line_P_binding[0,0]')
    # A nonunit definition is deliberately unsupported; none of its consumers
    # can produce an infeasibility statement from a guessed helper value.
    dense=A.toarray();j=list(d['names']).index('response_line_P[0,0]');dense[i,j]=2.
    proof=verify_grid_original_rows(grid,sparse.csr_matrix(dense),d)
    assert not proof['entire_model_infeasible']
    assert proof['per_family']['line_thermal_face']['not_measured_unknown_expression']==1
    assert proof['unmeasured_variable_reasons']


def test_positive_exact_subnormal_product_underflow_is_an_infeasibility_witness():
    grid,A,d=fixture();tiny=np.nextafter(0.,1.)
    extra=sparse.csr_matrix(([tiny],([0],[0])),shape=(1,1))
    A=sparse.vstack((sparse.hstack((A,sparse.csr_matrix((A.shape[0],1)))),
        sparse.hstack((sparse.csr_matrix((1,A.shape[1])),extra))),format='csr')
    for key,tail in [('names',['fixed_literal']),('types',['C']),('lower',[.25]),('upper',[.25]),('objective',[0.])]:
        d[key]=np.concatenate((d[key],tail))
    for key,tail in [('row_names',['NormalAmps[1,0]']),('sense',['<']),('rhs',[0.])]:
        d[key]=np.concatenate((d[key],tail))
    assert float(F(float(tiny))/4)==0.
    proof=verify_grid_original_rows(grid,A,d)
    assert proof['entire_model_infeasible']
    assert F(proof['infeasibility_witnesses'][0]['strict_positive_margin_exact'])==F(float(tiny))/4


@pytest.mark.parametrize('attack',['RAW_BOUND','INJECTION_WEIGHT','INJECTION_RHS','RHO_BOUND','BOX','MASK'])
def test_input_and_actual_original_binding_mutations_reject(attack):
    grid,A,d=fixture()
    if attack=='RAW_BOUND':d['upper'][0]=np.nextafter(300.,np.inf)
    elif attack=='INJECTION_WEIGHT':
        A=A.copy();A.data[0]=np.nextafter(A.data[0],np.inf)
    elif attack=='INJECTION_RHS':d['rhs'][0]=np.nextafter(0.,1.)
    elif attack=='RHO_BOUND':d['upper'][list(d['names']).index('rho_max')]=.99
    elif attack=='BOX':
        boxes=list(grid.boxes);b=list(boxes[0]);b[4]-=1;boxes[0]=tuple(b)
        grid=replace(grid,boxes=tuple(boxes));grid=replace(grid,state_sha=digest(grid.scientific_state()))
    else:
        physical=grid.physical;unit=physical.units[0]
        physical=replace(physical,units=(replace(unit,retained=unit.retained[1:]),))
        physical=replace(physical,state_sha=digest(physical.scientific_state()))
        grid=replace(grid,physical=physical);grid=replace(grid,state_sha=digest(grid.scientific_state()))
    with pytest.raises(ContractError):verify_grid_original_rows(grid,A,d)


def test_nonzero_mess_placeholder_cannot_be_used_as_prescreen_point():
    grid,A,d=fixture();physical=grid.physical
    coefs=[SimpleNamespace(slot=t,coefficient_sha256='c'*64,control_names=grid.inputs[t][2]) for t in range(2)]
    with pytest.raises(ContractError,match='NOT_AN_OPTIMIZATION_POINT'):
        build_grid_prescreen(physical,coefs,[[1.,.001,0.,0.,0.]]*2)

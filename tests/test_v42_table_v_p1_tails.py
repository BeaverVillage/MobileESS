from dataclasses import replace
from fractions import Fraction
import numpy as np
import scipy.sparse as sp
import pytest
from v42_a_stage_domain_v2.lexstage import LinearSnapshot,Objective
from v42_a_stage_phase1.core import primal_replay
from v42_integration.table_v_p1_tails import project,lift,verify


def fixture():
    s=LinearSnapshot(sp.csr_matrix([[-1.,1.],[1.,0.]]),np.array([0.,0.]),np.array([3.,np.inf]),
        np.array(['>','<']),np.array([2.,3.]),np.array(['B','C']),
        (Objective('rho',((0,Fraction(1)),),Fraction(0)),)).require()
    d=dict(units=[],known={},risk={},controls=[[('v',0)]],globals={'scientific_x':0,'CC4_dplus[0,0]':1},
        levels=[('rho',('v',0)),('P2_deviation',('v',1))])
    return s,d


def test_neutral_tail_projection_and_canonical_lift_replay_all_original_rows():
    s,d=fixture();new,desc,proof,rr,cc=project(s,d)
    assert new.matrix.shape==(1,1) and new.vtypes[0]=='B' and proof['removed_columns']==1
    assert desc['controls']==[[('v',0)]] and desc['levels']==[('rho',('v',0))]
    assert proof['independent_verification']['all_original_discrete_variables_retained']
    for x in (0.,1.,3.):
        point=lift(s,np.array([x]),proof)
        assert point[0]==x and point[1]==x+2. and primal_replay(s,point)['PASS']
    bad=lift(s,np.array([4.]),proof)
    assert bad[0]==4. and not primal_replay(s,bad)['PASS']


@pytest.mark.parametrize('kind',['nonzero_cost','finite_upper','binary_tail','protected','extra_support','wrong_sense'])
def test_projection_does_not_remove_a_non_neutral_or_protected_original_constraint(kind):
    s,d=fixture();protected=()
    if kind=='nonzero_cost':s=replace(s,objectives=(Objective('rho',((0,Fraction(1)),(1,Fraction(1))),Fraction(0)),))
    if kind=='finite_upper':s=replace(s,upper=np.array([3.,9.]))
    if kind=='binary_tail':s=replace(s,vtypes=np.array(['B','B']))
    if kind=='protected':protected=(0,)
    if kind=='extra_support':s=replace(s,matrix=sp.csr_matrix([[-1.,1.],[1.,1.]]))
    if kind=='wrong_sense':s=replace(s,senses=np.array(['=','<']))
    new,desc,proof,_,_=project(s,d,protected_rows=protected)
    assert proof['removed_columns']==0 and new.fingerprint()==s.fingerprint()


def test_tail_in_scientific_control_is_rejected_instead_of_deleting_control():
    s,d=fixture();d['controls']=[[('v',1)]]
    with pytest.raises(ValueError,match='SCIENTIFIC_CONTROL'):project(s,d)


def test_verifier_rejects_coefficient_domain_objective_tamper():
    s,d=fixture();new,_,proof,_,_=project(s,d)
    with pytest.raises(ValueError,match='MATRIX_BYTES'):verify(s,replace(new,matrix=sp.csr_matrix([[2.]])),proof)
    with pytest.raises(ValueError,match='DOMAIN_CHANGED'):verify(s,replace(new,vtypes=np.array(['C'])),proof)
    with pytest.raises(ValueError,match='OBJECTIVE_CHANGED'):
        verify(s,replace(new,objectives=(Objective('rho',((0,Fraction(2)),),Fraction(0)),)),proof)


def test_canonical_tail_uses_outward_rounding_without_changing_retained_coordinates():
    s,d=fixture();s=replace(s,matrix=sp.csr_matrix([[-0.1,0.3],[1.,0.]]),rhs=np.array([0.2,3.]))
    new,_,proof,_,_=project(s,d);x=np.array([0.7]);point=lift(s,x,proof)
    exact=Fraction(float(s.matrix[0,0]))*Fraction(point[0])+Fraction(float(s.matrix[0,1]))*Fraction(point[1])
    assert exact>=Fraction(float(s.rhs[0])) and point[0].tobytes()==x[0].tobytes()

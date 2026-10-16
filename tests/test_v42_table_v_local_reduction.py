from dataclasses import replace
from copy import deepcopy
from fractions import Fraction as F
import numpy as np
import scipy.sparse as sp
import pytest
from v42_a_stage_domain_v2.lexstage import LinearSnapshot,Objective
from v42_integration.table_v_local_reduction import reduce_block,lift_point,NonBinary64Projection
from v42_integration.table_v_local_reduction_verify import verify


def case(A,rhs,senses,lower=None,upper=None,terms=()):
    A=sp.csr_matrix(A,dtype=float);n=A.shape[1]
    return LinearSnapshot(A,np.zeros(n) if lower is None else np.array(lower,float),
        np.ones(n) if upper is None else np.array(upper,float),np.array(senses),np.array(rhs,float),
        np.full(n,'C'),(Objective('local_price',terms,F(0)),)).require()


def fixture():
    s=case([[1,-1,0,0],[0,0,1,0],[1,1,1,0],[2,2,0,0],[0,0,0,1]],
        [0,0,2,4,0],['=','=','<','<','>'],terms=((0,F(1,2)),(1,F(1,2)),(2,F(3)),(3,F(2))))
    B=sp.csr_matrix([[1,2,3,0],[0,0,7,1]],dtype=float)
    return s,B


def test_complete_polytope_alias_zero_redundancy_and_coupling_are_independently_proved():
    s,B=fixture();before=s.fingerprint();r=reduce_block(s,B);proof=verify(s,B,r)
    assert proof['PASS'] and proof['complete_domain_coverage'] and not proof['finite_column_pool_used']
    assert r['snapshot'].matrix.shape==(2,2)
    assert np.array_equal(r['mapping'],[0,0,-1,1])
    assert np.array_equal(r['B'].toarray(),[[3,0],[0,1]])
    assert s.fingerprint()==before
    for a in [F(0),F(1,2),F(1)]:
        for b in [F(0),F(1,4),F(1)]:
            point=lift_point(r,np.array([a,b],dtype=object))
            assert list(point)==[a,a,F(0),b]
            assert sum(c*point[j] for j,c in s.objectives[0].coefficients().items())==a+2*b


def test_alias_box_intersection_preserves_original_boxes():
    s=case([[1,-1]],[0],['='],lower=[0,.25],upper=[1,.75]);B=sp.csr_matrix((0,2))
    r=reduce_block(s,B);assert verify(s,B,r)['PASS']
    assert np.array_equal(r['snapshot'].lower,[.25]) and np.array_equal(r['snapshot'].upper,[.75])


def test_nonrepresentable_binary64_coupling_sum_is_rejected_without_rounding():
    s=case([[1,-1]],[0],['=']);B=sp.csr_matrix([[.1,.2]])
    with pytest.raises(NonBinary64Projection):reduce_block(s,B)


def test_approximate_equal_coefficients_are_not_an_exact_alias():
    s=case([[1,-(1+2**-40)]],[0],['=']);B=sp.eye(2,format='csr')
    r=reduce_block(s,B);assert verify(s,B,r)['PASS']
    assert r['snapshot'].matrix.shape[1]==2


@pytest.mark.parametrize('sense,expected_columns',[('>',2),('<',0),('=',0)])
def test_zero_implication_requires_the_correct_inequality_direction(sense,expected_columns):
    s=case([[1,1]],[0],[sense]);B=sp.eye(2,format='csr')
    r=reduce_block(s,B);assert verify(s,B,r)['PASS']
    assert r['snapshot'].matrix.shape[1]==expected_columns


def test_free_singleton_equality_is_exact_zero_but_free_sum_is_not():
    s=case([[1,0],[0,1]],[0,0],['=','>'],lower=[-np.inf,-np.inf],upper=[np.inf,np.inf])
    B=sp.eye(2,format='csr');r=reduce_block(s,B);assert verify(s,B,r)['PASS']
    assert np.array_equal(r['mapping'],[-1,0])
    s=case([[1,1]],[0],['='],lower=[-np.inf,-np.inf],upper=[np.inf,np.inf]);r=reduce_block(s,B)
    assert r['snapshot'].matrix.shape[1]==2 and verify(s,B,r)['PASS']


def test_independent_replay_rejects_deleted_implication_and_altered_coupling():
    s,B=fixture();r=reduce_block(s,B)
    wrong=deepcopy(r);wrong['proof']['inference_steps']=[x for x in wrong['proof']['inference_steps'] if x['kind']!='ROW_ALIAS']
    with pytest.raises(ValueError,match='MAPPING'):verify(s,B,wrong)
    wrong=deepcopy(r);wrong['B'].data[0]+=1
    with pytest.raises(ValueError,match='COUPLING'):verify(s,B,wrong)


def test_independent_replay_rejects_removed_active_row_and_forged_target_rhs():
    s,B=fixture();r=reduce_block(s,B)
    wrong=deepcopy(r);wrong['row_targets'][2]=-1
    with pytest.raises(ValueError,match='TAUTOLOGY'):verify(s,B,wrong)
    wrong=deepcopy(r);rhs=wrong['snapshot'].rhs.copy();rhs[0]+=1
    wrong['snapshot']=replace(wrong['snapshot'],rhs=rhs);wrong['proof']['target_snapshot_sha']=wrong['snapshot'].fingerprint()
    with pytest.raises(ValueError,match='ROW_LIFT'):verify(s,B,wrong)


def test_primitive_expressions_are_mapped_without_inventing_a_trajectory():
    s,B=fixture();unit=dict(uid='real',v=dict(y={0:('v',0),1:('v',2)},sum={0:('e',0.,np.array([0,1]),np.array([.5,.5]))}))
    r=reduce_block(s,B,[unit]);u=r['units'][0]
    assert u['v']['y']=={0:('v',0),1:('c',0.)} and u['v']['sum'][0]==('v',0)
    assert verify(s,B,r)['PASS']


def test_original_integer_domain_is_never_compressed():
    s,B=fixture();s=replace(s,vtypes=np.array(['B','C','C','C']))
    with pytest.raises(ValueError,match='CONTINUOUS'):reduce_block(s,B)

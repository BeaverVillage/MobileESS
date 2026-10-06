from fractions import Fraction as F
import numpy as np
import pytest
from scipy import sparse
from v42_m_stage_root.conservative_authority import numerical_zero_sign,free_rc_consistency,split_gates
from v42_m_stage_root.numerical_certificate import canonicalize,independent_csc
from v42_bap.state import Tree,ColumnRegistry,BinaryProjection,NodeResult

@pytest.mark.parametrize('sense,pi',[('<',4e-11),('>',-4e-11)])
def test_authorized_numerical_sign_boundary(sense,pi):
    p,t=numerical_zero_sign([pi],[sense]);assert p[0]==0 and t['canonicalized_Pi_count']==1

def test_sign_above_fixed_threshold_is_rejected():
    with pytest.raises(ValueError,match='EXCEEDS'):numerical_zero_sign([2e-8],['<'])

def test_free_rc_consistency_does_not_fabricate_exact_support():
    r=free_rc_consistency(np.array([5e-10]),np.array([-np.inf]),np.array([np.inf]))
    assert r['numerical_consistency_PASS'] and r['exact_support_proof_still_required']
    with pytest.raises(ValueError,match='EXCEEDS'):free_rc_consistency(np.array([2e-8]),np.array([-np.inf]),np.array([np.inf]))

def gates(p,d,**kw):
    defaults=dict(exact_signs=True,exact_columns=True,exact_bounds=True,independent_identity=True,corrected_formula=True,rational_verification=True)
    defaults.update(kw);return split_gates(p,d,**defaults)

def test_weak_duality_not_strong_identity_authorizes_conservative_bound():
    g=gates(F(1),F(1)-F(174154,10**13))
    assert not g['OPTIMAL_DUAL_IDENTITY'] and g['EXACT_DUAL_AUTHORITY_FOR_BAP']

def test_dual_above_primal_or_missing_exact_proof_rejected():
    assert not gates(F(1),F(1)+F(1,10**15))['EXACT_DUAL_AUTHORITY_FOR_BAP']
    assert not gates(F(1),F(0),exact_columns=False)['EXACT_DUAL_AUTHORITY_FOR_BAP']

def test_all_column_rc_recomputed_without_individual_zeroing():
    A=sparse.csr_matrix([[1.,-1.],[1.,0.],[0.,1.]])
    v=dict(pi=np.array([1e-10,4e-11,1.+2e-10]),objective=np.array([0.,1.]),sense=np.array(['=','<','=']),rhs=np.array([0.,2.,1.]),lower=np.array([-np.inf,0.]),upper=np.array([np.inf,np.inf]),constant=np.array(0.))
    pi,q,_,proof=canonicalize(A,v,[(0,0)],[2],True)
    qi,_,d,_=independent_csc(A,v,pi)
    assert all(q.get(j,F(0))==r for j,r in qi.items()) and d==F(1) and qi[0]==0 and qi[1]>=0
    v['objective'][1]=-.006
    with pytest.raises(ValueError,match='EXCEEDS'):canonicalize(A,v,[(0,0)],[2],True)

def test_early_branching_preserves_inherited_global_lb_without_closure():
    r=ColumnRegistry();k=r.add(0,(0.,),(0.,),0.,0)
    tree=Tree(r,(k,),tolerance=1e-8,allow_early_branching=True)
    def solve(n,r):return NodeResult('PRICING_OPEN',(k,),rmp_objective=1.,certified_lower_bound=.5,pricing_closed=False,points=((.5,),),certificate=dict(PASS=True,node_id=0))
    assert tree.step(solve,(BinaryProjection('original_binary',0,0,'x',((0,1.),)),),None)=='BRANCHED'
    assert tree.global_lb==.5 and len(tree.open_ids)==2
    assert {tree.nodes[i].decisions[-1].value for i in tree.open_ids}=={0,1}

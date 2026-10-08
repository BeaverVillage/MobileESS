from copy import deepcopy
from fractions import Fraction
from types import SimpleNamespace
from dataclasses import dataclass
import numpy as np
import pytest
from scipy import sparse
from v42_m1_research.check_lb import check_dual_certificate, check_rational_dual_certificate, check_retained_relaxation, check_route_conflicts_against_graph, check_integer_count_cover
from v42_m1_research.lb import prepare, variable_slot, diagnose_fractional, repair_affine_equality_duals, prepare_count_disjunction, latest_validated_ub


def data(A, *, names=None, rows=None, sense=None, rhs=None, lower=None, upper=None, types=None, objective=None):
    m,n=A.shape
    return dict(names=np.asarray(names or [f'x[{j}]' for j in range(n)]),
        row_names=np.asarray(rows or ['flow']*m),
        sense=np.asarray(sense or ['>']*m),rhs=np.asarray(rhs or [1.]*m,dtype=float),
        lower=np.asarray(lower or [0.]*n,dtype=float),upper=np.asarray(upper or [10.]*n,dtype=float),
        types=np.asarray(types or ['C']*n),objective=np.asarray(objective or [1.]*n,dtype=float),constant=np.asarray(0.))


def test_any_signed_multiplier_certifies_exact_bound_without_optimality():
    A=sparse.csr_matrix([[1.,1.]])
    d=data(A,rhs=[3.],objective=[1.,2.])
    r=check_dual_certificate(A,d,[1.])
    assert r['exact_bound']=='3' and r['independently_certified_LB']==3
    assert not r['native_objective_used'] and not r['optimality_claimed']


def test_dual_residual_box_correction_cannot_be_ignored():
    A=sparse.csr_matrix([[1.,1.]])
    d=data(A,rhs=[3.],objective=[1.,2.],upper=[4.,5.])
    r=check_dual_certificate(A,d,[2.])
    assert r['weighted_rhs_exact']=='6' and r['box_correction_exact']=='-4'
    assert r['independently_certified_LB']==2.


@pytest.mark.parametrize('sense,dual',[('<',1.),('>',-1.)])
def test_invalid_row_multiplier_sign_rejected(sense,dual):
    A=sparse.csr_matrix([[1.]])
    with pytest.raises(ValueError,match='ROW_SIGN'):
        check_dual_certificate(A,data(A,sense=[sense]),[dual])


def test_exact_dyadic_cancellation_and_outward_rounding():
    A=sparse.csr_matrix([[.1],[.3]])
    d=data(A,sense=['=','='],rhs=[.1,.3],objective=[.7],lower=[1.],upper=[1.])
    r=check_dual_certificate(A,d,[.2,-.4])
    assert Fraction(r['exact_bound'])==Fraction(.7)
    assert Fraction(r['independently_certified_LB'])<=Fraction(r['exact_bound'])


def test_unsupported_objective_column_is_box_minimized():
    A=sparse.csr_matrix([[1.,0.]])
    d=data(A,rhs=[2.],objective=[1.,-3.],upper=[5.,4.])
    assert check_dual_certificate(A,d,[1.])['exact_bound']=='-10'


def test_nonfinite_original_box_rejected():
    A=sparse.csr_matrix([[1.]])
    with pytest.raises(ValueError,match='FINITE'):
        check_dual_certificate(A,data(A,upper=[np.inf]),[1.])


def test_exact_affine_equality_repair_cancels_two_layer_auxiliary_residuals():
    # p=2*x, q=3*p, min(q), q>=1. Raw multipliers on the two
    # unrestricted equalities have numerical errors; repair makes both
    # auxiliary reduced costs exactlyzero without changing the >= multiplier.
    A=sparse.csr_matrix([[-2.,1.,0.],[0.,-3.,1.],[0.,0.,1.]])
    d=data(A,names=['Pdis[MESS01,A,66]','injection_P[A,66]','response_line_P[66,9]'],
        rows=['injection_P_binding','response_line_P_binding','line_thermal_face'],
        sense=['=','=','>'],rhs=[0.,0.,1.],objective=[0.,0.,1.],upper=[2.,4.,12.])
    dual=np.array([.00001,.00002,1.])
    raw=check_dual_certificate(A,d,dual)
    rational,receipt=repair_affine_equality_duals(A,d,dual)
    result=check_rational_dual_certificate(A,d,rational)
    assert result['exact_bound']=='1'
    assert result['independently_certified_LB']>=raw['independently_certified_LB']
    assert receipt['auxiliary_residuals_cancelled_exactly']==2
    assert rational['2']=='1'


def test_rational_wrong_sign_rejected_without_float_rounding():
    A=sparse.csr_matrix([[1.]])
    with pytest.raises(ValueError,match='ROW_SIGN'):
        check_rational_dual_certificate(A,data(A,sense=['<']),{'0':'1/100000000000000000000000000000000000000000000000000000000'})


def test_original_integer_types_and_every_physics_row_retained():
    A=sparse.csr_matrix([[1.,0.],[0.,1.],[1.,1.]])
    d=data(A,rows=['flow','energy_balance','line_thermal_face'],types=['B','C'],sense=['<','<','<'],rhs=[1.,1.,2.])
    rows=np.array([0,1],dtype=np.int64)
    e=dict(d,**{k:d[k][rows] for k in ('rhs','sense','row_names')})
    report=check_retained_relaxation(A,d,A[rows],e,rows)
    assert report['PASS'] and not report['new_strong_cut']
    e['types']=np.array(['C','C'])
    with pytest.raises(ValueError,match='DOMAIN_DRIFT'):
        check_retained_relaxation(A,d,A[rows],e,rows)


def test_drop_soc_row_is_not_allowed_even_if_witness_passes():
    A=sparse.csr_matrix([[1.],[1.]])
    d=data(A,rows=['energy_balance','line_thermal_face'])
    rows=np.array([1],dtype=np.int64)
    e=dict(d,**{k:d[k][rows] for k in ('rhs','sense','row_names')})
    with pytest.raises(ValueError,match='PHYSICS_ROW_DROPPED'):
        check_retained_relaxation(A,d,A[rows],e,rows)


def test_retained_coefficient_mutation_rejected():
    A=sparse.csr_matrix([[1.]])
    d=data(A)
    with pytest.raises(ValueError,match='COEFFICIENT_DRIFT'):
        check_retained_relaxation(A,d,sparse.csr_matrix([[1.000001]]),d,np.array([0],dtype=np.int64))


def test_joint_relaxation_uses_native_incidence_not_generic_row_names():
    A=sparse.csr_matrix([[1.,0.,0.],[0.,1.,-1.],[1.,0.,-1.],[0.,1.,0.]])
    d=data(A,names=['response_line_P[66,9]','response_line_Q[95,10]','rho_max'],
        rows=['line_thermal_face','line_thermal_face','line_thermal_face','energy_balance'],
        sense=['<','<','<','='],rhs=[2.,2.,2.,0.],objective=[0.,0.,1.],upper=[10.,10.,1.])
    case=SimpleNamespace(A=A,d=d,point=np.zeros(3),case_sha='sameMay01')
    result=prepare(case)
    assert {x['slot'] for x in result.requirements['selected_original_grid_rows']}=={66,95}
    assert result.inclusion['PASS'] and result.d['upper'][2]==1.
    assert result.requirements['target_rho_is_not_imposed_as_original_domain_bound']


@pytest.mark.parametrize('name,t',[('node_activity[MESS01,IDC02,95]',95),('response_line_P[66,19]',66),('injection_Q[STA01,78]',78),('route_flow[MESS01,1234]',None)])
def test_slot_mapping(name,t):
    assert variable_slot(name)==t


def test_complete_graph_route_conflict_checked_independently():
    A=sparse.csr_matrix([[1.,0.],[0.,1.]])
    d=data(A,names=['node_activity[MESS01,A,66]','node_activity[MESS01,B,70]'],types=['B','B'])
    graph=(['A','B'],{'MESS01':'A'},[('A',66,'A',67,None),('A',67,'A',70,None)],None,None)
    arcs=[list(a[:4]) for a in graph[2]]
    cut=dict(unit='MESS01',columns=[0,1],arcs=arcs)
    assert check_route_conflicts_against_graph(A,d,[cut],graph)['PASS']
    changed=deepcopy(cut);changed['arcs']=[]
    with pytest.raises(ValueError,match='COMPLETE_ORIGINAL'):
        check_route_conflicts_against_graph(A,d,[changed],graph)


def test_reachable_pair_cannot_be_claimed_conflicting():
    A=sparse.csr_matrix([[1.,0.],[0.,1.]])
    d=data(A,names=['node_activity[MESS01,A,66]','node_activity[MESS01,B,70]'],types=['B','B'])
    graph=(['A','B'],{'MESS01':'A'},[('A',66,'B',70,None)],None,None)
    with pytest.raises(ValueError,match='ACTUALLY_REACHABLE'):
        check_route_conflicts_against_graph(A,d,[dict(unit='MESS01',columns=[0,1],arcs=[list(graph[2][0][:4])])],graph)


def test_four_fleet_substitution_cannot_be_removed_by_single_unit_conflict():
    A=sparse.csr_matrix([[1.,0.],[0.,1.]])
    d=data(A,names=['node_activity[MESS01,A,66]','node_activity[MESS02,B,70]'],types=['B','B'])
    graph=(['A','B'],{'MESS01':'A','MESS02':'B'},[],None,None)
    with pytest.raises(ValueError,match='DIFFERENT_FLEET'):
        check_route_conflicts_against_graph(A,d,[dict(unit='MESS01',columns=[0,1],arcs=[])],graph)


def test_fractional_count_is_not_reported_as_bound_success():
    A=sparse.csr_matrix([[1.,0.],[0.,1.]])
    d=data(A,names=['node_activity[MESS01,A,66]','charge_mode[MESS01,95]'],types=['B','B'])
    report=diagnose_fractional(d,[.5,.25])
    assert report['fractional_binary_total']==2
    assert report['reduction_in_fractional_count_is_not_bound_improvement']


def count_case():
    units=[f'MESS0{i}' for i in range(1,5)]
    names=[f'node_activity[{u},{site},{t}]' for site,t in [('A',66),('B',90)] for u in units]
    A=sparse.eye(8,format='csr')
    d=data(A,names=names,types=['B']*8,upper=[1.]*8,sense=['<']*8)
    return SimpleNamespace(A=A,d=d,graph=(['A','B'],dict.fromkeys(units,'A'),[],None,None),case_sha='SameMay01')


def test_four_fleet_two_time_cover_is_complete_and_removes_fractional_count():
    case=count_case()
    leaves,report=prepare_count_disjunction(case,np.array([.2,.2,.2,.2,.4,.4,.4,.5]))
    assert report['PASS'] and report['every_original_integer_plan_covered']
    assert report['root_point_violates_both_integer_halfspaces']
    assert leaves[0].d['rhs'][-1]+1==leaves[1].d['rhs'][-1]
    assert leaves[0].A.shape==(9,8)
    # Exhaustive tiny-domain check verifies unioncoverage for all2^8 plans.
    import itertools
    for bits in itertools.product([0.,1.],repeat=8):
        count=sum(bits)
        assert count<=leaves[0].d['rhs'][-1] or count>=leaves[1].d['rhs'][-1]


def test_four_fleet_cover_missing_leaf_rejected():
    case=count_case()
    leaves,report=prepare_count_disjunction(case,np.array([.2]*8))
    with pytest.raises(ValueError,match='INCOMPLETE_LEAF'):
        check_integer_count_cover(case.A,case.d,leaves[:1],report['original_binary_columns'],int(leaves[0].d['rhs'][-1]),units=case.graph[1])


def test_four_fleet_cover_gap_in_halfspaces_rejected():
    case=count_case()
    leaves,report=prepare_count_disjunction(case,np.array([.2]*8))
    leaves[1].d['rhs'][-1]+=1
    with pytest.raises(ValueError,match='HOLE'):
        check_integer_count_cover(case.A,case.d,leaves,report['original_binary_columns'],int(leaves[0].d['rhs'][-1]),units=case.graph[1])


def test_count_cover_modified_original_grid_coefficient_rejected():
    case=count_case()
    leaves,report=prepare_count_disjunction(case,np.array([.2]*8))
    leaves[0].A=leaves[0].A.copy();leaves[0].A.data[0]+=1e-10
    with pytest.raises(ValueError,match='ORIGINAL_COEFFICIENT'):
        check_integer_count_cover(case.A,case.d,leaves,report['original_binary_columns'],int(leaves[0].d['rhs'][-1]),units=case.graph[1])


def test_integral_joint_count_does_not_trigger_single_binary_fallback():
    case=count_case()
    leaves,report=prepare_count_disjunction(case,np.array([0.,1.,0.,1.,1.,0.,1.,0.]))
    assert leaves==[] and report['status']=='NOT_PROVEN'


def test_global_count_bound_uses_min_all_exact_leaf_proofs_not_high_child_bound(monkeypatch):
    import v42_m1_research.lb as lb
    case=count_case()
    class FakeModel:
        def __init__(self,leaf):self.leaf=leaf
        def getAttr(self,name):
            assert name=='Pi'
            y=np.zeros(self.leaf.A.shape[0])
            if self.leaf.d['sense'][-1]=='>':y[-1]=1.
            return y
        def dispose(self):pass
    class FakeLedger:
        def optimize(self,model,**kwargs):
            return dict(Native_Runtime=0.,optimize_wall_seconds=0.,native_solver_bound_diagnostic=1000.)
    monkeypatch.setattr(lb,'build_model',lambda leaf,**kwargs:(FakeModel(leaf),{}))
    report,artifacts=lb.run_count_disjunction(case,FakeLedger(),np.array([.2]*8),np.zeros(8),repair=False)
    assert [r['independently_certified_leaf_LB'] for r in report['leaves']]==[0.,2.]
    assert report['independently_certified_global_LB']==0.
    assert report['no_native_BestBd_promoted']


@dataclass
class WitnessCase:
    d:dict
    point:object
    case_sha:str='FrozenMay01'


def test_latest_ub_forwarding_revalidates_and_preserves_scientific_case(monkeypatch,tmp_path):
    import v42_m1_research.check_ub as checker
    case=WitnessCase(dict(objective=np.array([1.]),constant=np.array(0.)),np.array([.628]))
    path=tmp_path/'FINAL_VALID_UB_POINT.npz';np.savez_compressed(path,point=np.array([.60]))
    calls=[]
    def validate(c,x):
        calls.append((c.case_sha,x.copy()))
        return dict(PASS=True,case_sha=c.case_sha,objective=.60,point_sha256=checker.vector_sha(x))
    monkeypatch.setattr(checker,'validate_candidate',validate)
    local,receipt=latest_validated_ub(case,path)
    assert len(calls)==1 and local.case_sha==case.case_sha and local.d is case.d
    assert case.point[0]==.628 and local.point[0]==.60
    assert receipt['required_global_LB_for_half_percent']==.597
    assert receipt['native_optimize_calls']==0 and receipt['source_sha256']


def test_latest_ub_forwarding_rejects_failed_full_replay(monkeypatch,tmp_path):
    import v42_m1_research.check_ub as checker
    case=WitnessCase(dict(objective=np.array([1.]),constant=np.array(0.)),np.array([.628]))
    path=tmp_path/'FINAL_VALID_UB_POINT.npz';np.savez_compressed(path,point=np.array([.59]))
    monkeypatch.setattr(checker,'validate_candidate',lambda c,x:dict(PASS=False,case_sha=c.case_sha))
    with pytest.raises(ValueError,match='ORIGINAL_REPLAY_FAILED'):
        latest_validated_ub(case,path)

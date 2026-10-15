"""Scientific regression: no seed is fabricated and relaxation proof is universal."""
from dataclasses import replace
from fractions import Fraction
from types import SimpleNamespace
import numpy as np
import pytest
from scipy import sparse
from test_v42_table_v_k48 import source_fixture, bound_result
from test_v42_integration_m import fixture, validator
from test_v42_table_v_mess_adaptive import Budget
from v42_integration import m_engine
from v42_integration.table_v_k48 import prepare_k16, verify_packet, summarize_current_k48
from v42_integration.pcc_definitions import satisfy_definitions, hard_rows
from v42_a_stage_domain_v2.lexstage import LinearSnapshot, Objective
from v42_a_stage_phase1.core import elastic_master


def test_seedless_K16_has_no_start_or_UB_but_valid_global_relaxation(tmp_path):
    case,_=source_fixture()
    packet,proof=prepare_k16(case,None,tmp_path/'K16')
    assert proof['PASS'] and proof['original_domain_projection_included']
    assert proof['current_FULL_UB'] is None
    assert packet['start'] is packet['full_start'] is None
    assert not (tmp_path/'K16/JOINT_START.npz').exists()
    summary=summarize_current_k48(packet,proof,[bound_result(packet['source'],16,.4)])
    assert summary['Global_LB']==.4 and summary['Global_LB_valid']
    assert summary['relative_global_gap'] is None and not summary['global_gap_certified']
    packet['start']=np.zeros(len(packet['columns']))
    with pytest.raises(ValueError,match='CANNOT_CLAIM_MIP_START'):verify_packet(case,packet)


def test_seedless_joint_contains_STAY_and_MOVE_without_a_start(tmp_path):
    case,point=fixture(tmp_path)
    bank=m_engine.IncumbentBank(case)
    graph=bank.graph
    moves=graph.paths(point(True))
    pools=m_engine.pin_pools(case,None,bank,{u:[moves[u]] for u in graph.origins})
    A,d,lift,start,proof=m_engine.direct_joint(case,None,pools)
    assert start is None and not proof['MIP_Start_present']
    assert proof['restricted_to_FULL_inclusion'] and proof['no_MOVE_forcing']
    assert all(graph.complete(u) in pools[u] and moves[u] in pools[u] for u in graph.origins)


def test_first_integer_capture_is_replayed_before_becoming_UB(tmp_path):
    case,point=fixture(tmp_path)
    graph=m_engine.PathGraph(case);moves=graph.paths(point(True))
    case.candidate_pools={u:[moves[u]] for u in graph.origins}
    budget=Budget(145)
    def solve(c,b,packet,folder,seconds):
        assert packet[3] is None
        b.parent.consumed+=seconds
        return dict(executed=True,Native_Runtime=seconds),[dict(point=point(True))]
    case.joint_solver=solve
    result,chosen=m_engine.optimize_mess(case,None,[],budget)
    assert result['FULL_validated'] and np.array_equal(chosen,point(True))
    assert not result['admission_order'][-1]['invoked']


def test_seedless_native_readback_leaves_every_Start_undefined(tmp_path,monkeypatch):
    import gurobipy as gp
    def forbidden(*args,**kwargs):raise AssertionError('NATIVE0_OPTIMIZE_FORBIDDEN')
    monkeypatch.setattr(gp.Model,'optimize',forbidden)
    case,_=fixture(tmp_path);bank=m_engine.IncumbentBank(case)
    packet=m_engine.direct_joint(case,None,m_engine.pin_pools(case,None,bank))
    result,captures=m_engine._native_joint(case,Budget(),packet,tmp_path/'READBACK',0.,native0=True)
    assert result['Native_optimize_calls']==0 and captures==[]
    assert result['start_processing']['classification']=='NO_MIP_START'
    assert not result['start_processing']['MIP_Start_present']


def test_PCC_identity_stays_hard_while_grid_rows_remain_elastic():
    s=LinearSnapshot(sparse.csr_matrix([[1.,-2.],[1.,0.]]),np.array([-np.inf,0.]),
        np.array([np.inf,3.]),np.array(['=','<']),np.array([10.,11.]),np.array(['C','C']),
        (Objective('rho',((0,Fraction(1)),)),)).require()
    defs=[dict(row=0,pivot=0)]
    x=satisfy_definitions(s,np.array([0.,2.]),defs)
    assert x[0]==14.
    state=dict(compact=s,grows=(0,1),hard_pcc_definitions=defs)
    hard=hard_rows(state);master=elastic_master(s,tuple(i for i in state['grows'] if i not in hard))
    assert 0 not in master.artificial_rows and 1 in master.artificial_rows
    assert (master.snapshot.matrix.getrow(0).toarray()[0,:2]==[1.,-2.]).all()


def test_tiny_projected_K_coefficient_is_preserved_by_exact_row_scaling(tmp_path,monkeypatch):
    import gurobipy as gp
    from v42_integration.a_engine import digest
    from v42_m1_hybrid.blocks import matrix_sha
    case,_=source_fixture()
    case.original_A[4,6]=-2.**-42
    case.identity['original_matrix_sha']=matrix_sha(case.original_A);case.case_sha=digest(case.identity)
    packet,proof=prepare_k16(case,None,tmp_path/'K16_SCALED')
    assert proof['positive_dyadic_native_row_scaling_exact']
    assert all(cut['native_row_scale']>1 for cut in packet['cuts'])
    def forbidden(*args,**kwargs):raise AssertionError('NATIVE0_OPTIMIZE_FORBIDDEN')
    monkeypatch.setattr(gp.Model,'optimize',forbidden)
    model=gp.Model();model.Params.OutputFlag=0
    try:
        d=packet['d'];x=model.addMVar(packet['A'].shape[1],lb=d['lower'],ub=d['upper'],vtype=d['types'])
        model.addMConstr(packet['A'],x,d['sense'],d['rhs']);model.update()
        assert matrix_sha(model.getA().tocsr())==matrix_sha(packet['A'])
    finally:model.dispose()
    packet['cuts'][0]['native_row_scale']*=2
    with pytest.raises(ValueError,match='ROW_SCALE_DRIFT'):verify_packet(case,packet)

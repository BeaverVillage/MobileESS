"""Lightweight stage adapter gates, no Gurobi optimize."""
from fractions import Fraction as F
from types import SimpleNamespace as NS
from pathlib import Path
from copy import deepcopy
import json
import numpy as np
from scipy import sparse
from scipy.optimize import linprog
import pytest
from v42_trajectory_hull.adapter import CGAdapter, strict_admission, exact_price,checkpoint,validate_checkpoint
from v42_trajectory_hull.budget import ContinuedBudget,write
from v42_trajectory_hull.scaling import row_scaling,restore_dual
from v42_trajectory_hull.certificate import node_bound_details
from v42_trajectory_hull.legacy_mechanics import next_smoothing_weight


def small_case():
    # Full96 fixed SOC states plus a binary dispatch trajectory; both complete
    # integer trajectories survive. Original grid: rho+z >= 1.
    cols=np.arange(97);A=sparse.hstack((sparse.csr_matrix((96,1)),sparse.eye(96)),format='csr')
    d=dict(lower=np.concatenate(([0.],np.ones(96))),upper=np.ones(97),
        types=np.concatenate((['B'],np.full(96,'C'))),objective=np.zeros(97),rhs=np.ones(96),
        sense=np.full(96,'='),constant=np.array(0.),names=np.array(['charge_mode[MESS01,0]']+[f'SOC[MESS01,{t}]' for t in range(96)]),row_names=np.array([f'SOC_fixture[{t}]' for t in range(96)]))
    b=NS(unit='MESS01',A=A,d=d,original_columns=cols,original_rows=np.arange(1,97))
    grid=sparse.csr_matrix(([1.,1.],([0,0],[0,97])),shape=(1,98))
    whole=sparse.vstack((grid,sparse.hstack((A,sparse.csr_matrix((96,1))))),format='csr')
    case=NS(A=whole,d=d,point=np.concatenate(([0.],np.ones(96),[1.])),case_sha='fixture')
    decomp=NS(units={'MESS01':b},coupling_rows=np.array([0]),nonunit_block=NS(original_rows=np.array([],dtype=int)))
    return case,decomp,b


def test_legacy_add_current_true_rc_then_reoptimize(tmp_path):
    case,decomp,b=small_case();out=tmp_path/'adapter';out.mkdir()
    adapter=CGAdapter(case,decomp,np.array([0]),{'MESS01':[]},out)
    adapter.bind_true_prices(NS(exact_objectives={'MESS01':{0:F(-1)}}),{'MESS01':'0'})
    adapter.current_round=1;x=np.ones(97);path=out/'raw.npz';np.savez(path,point=x,original_columns=b.original_columns)
    old=linprog([1.,0.],A_ub=[[-1.,0.]],b_ub=[-1.],A_eq=[[0.,1.]],b_eq=[1.],bounds=[(0,1),(0,1)])
    receipt=adapter.admit(0,path);assert receipt['added'] and F(receipt['exact_true_RC'])==-1
    # Reuse admitted original-row projection in the tiny restricted master.
    proj=adapter.blocks[0].column(x)[0][0]
    new=linprog([1.,0.,0.],A_ub=[[-1.,0.,-proj]],b_ub=[-1.],A_eq=[[0.,1.,1.]],b_eq=[1.],bounds=[(0,1)]*3)
    assert old.success and new.success and old.fun==1 and new.fun==0
    assert not adapter.admit(0,path)['added']
    adapter.blocks[0].true_price={'0':'1'}
    assert not adapter.admit(0,path)['added']


def test_column_axis_and_fractional_integer_rejected():
    _,_,b=small_case();x=np.ones(97)
    with pytest.raises(ValueError,match='AXIS'):strict_admission(b,x,b.original_columns[::-1])
    x[0]=.5;assert not strict_admission(b,x,b.original_columns)['PASS']
    assert exact_price(np.array([.1]),{'0':'1/3'})==F(float(.1))/3


def test_checkpoint_preserves_identity_axes_and_budget(tmp_path):
    case,decomp,b=small_case();out=tmp_path/'cp';out.mkdir();adapter=CGAdapter(case,decomp,np.array([0]),{'MESS01':[]},out)
    adapter.current_round=1;adapter.smooth(np.array([1.]),np.array([0.]));dual=out/'dual.npz';np.savez(dual,Pi_original=np.array([1.,0.]))
    identity={'case_sha':'fixture','matrix_sha':'same'};budget=NS(calls=[{'Runtime':12.}],used=12.)
    checkpoint(adapter,budget,out/'cp.json',identity,dual)
    assert validate_checkpoint(out/'cp.json',identity,decomp)['measured_native_seconds']==12.
    with pytest.raises(ValueError,match='CASE'):validate_checkpoint(out/'cp.json',dict(identity,matrix_sha='wrong'),decomp)
    cp=json.loads((out/'cp.json').read_text());cp['measured_native_seconds']=0;write(out/'cp.json',cp)
    with pytest.raises(ValueError,match='NATIVE'):validate_checkpoint(out/'cp.json',identity,decomp)


def test_native_resume_does_not_reset_budget_or_replay_inflight(tmp_path):
    old=tmp_path/'old.json';write(old,dict(calls=[dict(Runtime=136.165)],measured_native_seconds=136.165,inflight=None))
    out=tmp_path/'continued';b=ContinuedBudget(out,old);assert b.used==136.165 and b.remaining==300
    restored=ContinuedBudget(out,old,resume=True);assert restored.used==b.used
    state=json.loads((out/'LEDGER.json').read_text());state['inflight']={'label':'unresolved'};write(out/'LEDGER.json',state)
    with pytest.raises(ValueError,match='NO_AUTOMATIC_REPLAY'):ContinuedBudget(out,old,resume=True)


def test_power_two_recovery_and_discovery_only_stabilization(tmp_path):
    A=sparse.csr_matrix([[1e-18,1e-7]]);rhs=np.array([1.]);scaled,b,e=row_scaling(A,rhs)
    assert np.array_equal(np.ldexp(scaled.data,-np.repeat(e,np.diff(A.indptr))),A.data)
    assert np.array_equal(np.ldexp(b,-e),rhs)
    assert np.array_equal(restore_dual(np.array([2.]),e),np.ldexp([2.],e))
    case,decomp,_=small_case();out=tmp_path/'smooth';out.mkdir();adapter=CGAdapter(case,decomp,np.array([0]),{'MESS01':[]},out)
    adapter.current_round=1;adapter.smooth_pi=np.array([0.]);adapter.smooth_conv=np.array([0.]);adapter.last_true_pi=np.array([0.])
    true=np.array([1.]);discovery,_=adapter.smooth(true,np.array([0.]));assert discovery[0]==.3 and true[0]==1
    assert next_smoothing_weight(.3,1.)==.15


def test_saved_may01_same_unit_cross_dual_regressions():
    # Required real saved regression, read-only, no solver or model creation.
    from v42_trajectory_hull.case import read
    from v42_m1_hybrid.blocks import build_blocks,matrix_sha
    from v42_may_campaign.m_model import _domain_sha
    root=Path(__file__).resolve().parents[2];spec=read(root/'docs/v42_m_stage_trajectory_hull/MAY01_SPEC.json');folder=Path(spec['arrays'])
    A=sparse.load_npz(folder/'C3A_A.npz');d=dict(np.load(folder/'C3A_DATA.npz',allow_pickle=False))
    assert matrix_sha(A)==spec['selected_matrix_sha'] and _domain_sha(d)==spec['selected_domain_sha']
    decomp=build_blocks(NS(A=A,d=d,case_sha=spec['case_sha']))
    packet=read(root/'runtime/v42_trajectory_hull/master_single_trial01/NEW_PRICE_CERTIFICATE_PACKET.json')
    a=packet['units']['MESS01'];assert a['tree']['r1']['proof']['dual']==a['tree']['r00']['proof']['dual']
    detail=node_bound_details(decomp.units['MESS01'],a['exact_price'],{'60875':0,'58180':1},a['tree']['r1']['proof'])
    assert abs(float(F(detail['bound']))-(-1.529717979855327))<1e-14
    assert F(detail['bound'])>F(a['exact_price_lower_bound'])+17
    b=packet['units']['MESS03'];detail=node_bound_details(decomp.units['MESS03'],b['exact_price'],{},b['tree']['r0']['proof'])
    assert abs(float(F(detail['bound']))-(-1.5297179798572176))<1e-14
    assert F(detail['bound'])>F(b['exact_price_lower_bound'])+17

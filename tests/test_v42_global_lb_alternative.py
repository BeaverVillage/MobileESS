"""Corruption gates and exhaustive integer route/mode continuous-support fixtures."""
from fractions import Fraction as F
from itertools import product
import json

import numpy as np
import pytest
from scipy import sparse
from scipy.optimize import linprog

from tools.global_lb_alternative.math import (directed, exact_dual, normalize, weight_packet, stabilized_step,
    rounding_error, transport_cut, binding, combine)
from tools.global_lb_alternative.native import NativeBudget


def test_exact_duality_all_senses_and_nonzero_reduced_cost():
    # min x+2y+7; x>=1, y<=3, x+y=3; box x:[0,4], y:[0,3].
    A=sparse.csr_matrix([[1.,0.],[0.,1.],[1.,1.]])
    c=np.array([1.,2.]);b=np.array([1.,3.,3.]);s=np.array(['>','<','='])
    lower=np.array([0.,0.]);upper=np.array([4.,3.])
    q,detail=exact_dual(A,c,b,s,lower,upper,np.array([.25,-.125,1.]),7.)
    # Independent explicit corner calculation for residual [.75-.0? c-A'pi].
    pi=[F(1,4),F(-1,8),F(1)]
    residual=[F(1)-pi[0]-pi[2],F(2)-pi[1]-pi[2]]
    corners=[sum(a*F(x) for a,x in zip(residual,p)) for p in product((0,4),(0,3))]
    assert q==F(7)+sum(v*F(x) for v,x in zip(pi,b))+min(corners)
    assert q<=10  # actual optimum10 at x3,y0
    assert F(detail['box_term'])==min(corners)


@pytest.mark.parametrize('bad',[[-1.,0.,0.],[0.,1.,0.]])
def test_wrong_dual_sign_rejected(bad):
    with pytest.raises(ValueError,match='WRONG_DUAL_SIGN'):
        exact_dual(sparse.eye(3,format='csr'),np.ones(3),np.ones(3),np.array(['>','<','=']),np.zeros(3),np.ones(3),np.array(bad+[0.] if len(bad)==2 else bad))


def test_no_fabricated_envelope():
    with pytest.raises(ValueError,match='UNPROVEN_FINITE_BOX'):
        exact_dual(sparse.eye(1,format='csr'),np.ones(1),np.ones(1),['<'],np.zeros(1),np.array([np.inf]),np.array([-1.]))


def test_outward_rounding_negative_and_positive():
    for q in (F(1,3),F(-1,3),F(10**50,3)):
        assert F(directed(q))<=q<=F(directed(q,True))
    exact={0:F(1,3),1:F(-2,7)};native=np.array([float(exact[0]),float(exact[1])])
    lower=np.array([-3.,-2.]);upper=np.array([2.,4.])
    corrections=[sum((exact[j]-F(float(native[j])))*F(x) for j,x in enumerate(p)) for p in product((-3,2),(-2,4))]
    assert rounding_error(exact,native,lower,upper)==min(corrections)
    assert rounding_error(exact,native,lower,upper,True)==max(corrections)


def test_exact_simplex_and_stabilization_trust_region():
    w=normalize({0:F(1),1:F(2)})
    for i in range(8):
        proposed,mu=stabilized_step(w,{0:100.,1:-100.,2:50.},{3:F(.01)},{3:-1e6},i)
        assert sum(proposed.values())==1 and all(v>=0 for v in proposed.values())
        assert np.linalg.norm([float(proposed.get(k,0)-w.get(k,0)) for k in range(3)])<=.15+1e-14
        assert all(0<=v<=100 for v in mu.values())
    with pytest.raises(ValueError,match='SIMPLEX'):weight_packet({0:F(1,2)}, {})
    with pytest.raises(ValueError,match='MULTIPLIER'):weight_packet({0:F(1)}, {3:F(-1)})


class AliasFixture:
    def row(self,rhs,constant,terms):
        # Full x0=1+2*z0, x1=-z0+z1. Exact affine alias transport.
        return rhs-terms[0],constant+terms[0],{0:2*terms[0]-terms[1],1:terms[1]}


def test_compact_cut_transport_never_excludes_full_points():
    terms={0:F(1,3),1:F(2,7)};rhs=F(2)
    cut=transport_cut(terms,rhs,AliasFixture(),np.array([-1.,-2.]),np.array([2.,3.]))
    for z0,z1 in product((F(-1),F(0),F(2)),(F(-2),F(0),F(3))):
        original=terms[0]*(1+2*z0)+terms[1]*(-z0+z1)
        if original<=rhs:
            assert sum(F(v)*[z0,z1][int(j)] for j,v in cut['native_terms'].items())<=F(cut['native_rhs'])
    assert F(cut['native_rhs'])>=F(cut['compact_rhs'])+F(cut['coefficient_error_upper'])


def _fixture_support(path,mode):
    """Four-slot original-style physical rows, continuous powers/SOC, fixed binary route/mode.

    The route travels A->B with ETA2, energy.25 at departure1, blocking
    service at1/2, or stays A. Initial/terminal SOC1, min0/max2, Pmax1.
    Each integer route and all16 mode patterns are enumerated. linprog solves
    the remaining entire continuous polytope, rather than sampling powers.
    """
    n=8+5  # Pch4, Pdis4, SOC5
    c=np.r_[-np.ones(8),np.zeros(5)]
    eq=[];rhs=[]
    for t in range(4):
        r=np.zeros(n);r[8+t]=-1;r[8+t+1]=1;r[t]=-1;r[4+t]=1
        eq.append(r);rhs.append(-.25 if path=='MOVE' and t==1 else 0.)
    r=np.zeros(n);r[8]=1;eq.append(r);rhs.append(1.)
    r=np.zeros(n);r[12]=1;eq.append(r);rhs.append(1.)
    limits=[]
    for t in range(4):
        connected=not(path=='MOVE' and t in (1,2))
        limits.append((0.,float(connected and mode[t]==1)))
    for t in range(4):
        connected=not(path=='MOVE' and t in (1,2))
        limits.append((0.,float(connected and mode[t]==0)))
    limits += [(0.,2.)]*5
    return linprog(c,A_eq=eq,b_eq=rhs,bounds=limits,method='highs')


def test_exhaustive_multiperiod_route_soc_support_fixture():
    feasible=[];rejected=[]
    for path,mode in product(('STAY','MOVE'),product((0,1),repeat=4)):
        result=_fixture_support(path,mode)
        if result.success:
            feasible.append((path,mode,-result.fun))
            # Universal multi-time support U4 follows from unit path + mode,
            # while energy endpoints and travel loss are still active in each LP.
            assert -result.fun<=4+1e-9
        else:
            assert result.status==2;rejected.append((path,mode))
    assert len(feasible)+len(rejected)==32 and feasible and rejected
    assert max(v for _,_,v in feasible)==pytest.approx(4.)
    assert max(v for p,_,v in feasible if p=='MOVE')==pytest.approx(1.75)
    # Exact feasible LP point: half STAY, half ETA2 MOVE. Travel debits.125
    # at1. Fractional mode.5 permits simultaneous Pch/Pdis at occupied sites.
    # At3 reduce discharge by.125 to recover the original terminal SOC1.
    occupancy=[[F(1),F(0)],[F(1,2),F(0)],[F(1,2),F(0)],[F(1,2),F(1,2)]]
    charge=[[F(1,2),F(0)],[F(1,2),F(0)],[F(1,2),F(0)],[F(1,2),F(1,2)]]
    discharge=[[F(1,2),F(0)],[F(1,2),F(0)],[F(1,2),F(0)],[F(1,2),F(3,8)]]
    soc=F(1);gross=F(0)
    for t in range(4):
        for s in range(2):
            assert 0<=charge[t][s]<=min(F(1,2),occupancy[t][s])
            assert 0<=discharge[t][s]<=min(F(1,2),occupancy[t][s])
        soc+=sum(charge[t])-sum(discharge[t])-(F(1,8) if t==1 else F(0))
        assert 0<=soc<=2
        gross+=sum(charge[t])+sum(discharge[t])
    assert soc==1 and gross==F(39,8)>4


def test_stage_and_ub_registry_fail_closed():
    a=binding('B2',*['a'*64]*6);other=dict(a,stage='M1',anchor_sha='b'*64)
    record=dict(PASS=True,algorithm='K48 Baseline',binding=a,exact_LB='1/2',
                scope='GLOBAL_LOWER_BOUND',global_domain_inclusion_verified=True)
    ub=dict(PASS=True,binding=a,exact_UB='3/4')
    assert combine([record],a,ub)['LB']==.5
    with pytest.raises(ValueError,match='FOREIGN'):combine([dict(record,binding=other)],a,ub)
    with pytest.raises(ValueError,match='ABOVE_UB'):combine([dict(record,exact_LB='1')],a,ub)
    with pytest.raises(ValueError,match='CURRENT_FULL'):combine([record],a,dict(ub,PASS=False))
    assert combine([record,dict(PASS=False,exact_LB='99')],a,ub)['LB']==.5
    with pytest.raises(ValueError,match='RESTRICTED_OR_UNREGISTERED'):
        combine([dict(record,scope='ROUTE_FIXED_RESTRICTED_BOUND')],a,ub)


def test_measured_prefix_not_reset_and_inflight_quarantine(tmp_path):
    p=tmp_path/'NATIVE_RUNTIME_BUDGET_LEDGER.json'
    value=dict(budget_proven=True,STOP=False,inflight=None,prefix_records=[],calls=[],original_ceiling=1800.,prefix_Native_Runtime=1790.)
    p.write_text(json.dumps(value));budget=NativeBudget(tmp_path)
    assert budget.remaining('A')==10
    with pytest.raises(ValueError,match='RESERVE'):budget.begin('A','unit',29.)
    budget.begin('A','unit',8.)
    with pytest.raises(ValueError,match='NOT_ADMITTED'):budget.remaining('B')
    budget.finish(8.1)
    assert budget.remaining('A')==pytest.approx(1.9)
    assert json.loads(p.read_text())['effective_cumulative_Native_Runtime']==1798.1


def test_unknown_runtime_and_prefix_drift_fail_closed(tmp_path):
    import hashlib
    source=tmp_path/'prefix.json';source.write_text('preserved')
    packet=dict(budget_proven=True,STOP=False,inflight=None,
        prefix_records=[dict(path=str(source),sha256=hashlib.sha256(source.read_bytes()).hexdigest())],
        calls=[],original_ceiling=1800.,prefix_Native_Runtime=1003.501)
    ledger=tmp_path/'NATIVE_RUNTIME_BUDGET_LEDGER.json';ledger.write_text(json.dumps(packet))
    budget=NativeBudget(tmp_path);budget.begin('A','unit',29.)
    budget.finish(None,'runtime_unavailable')
    assert json.loads(ledger.read_text())['STOP'] is True
    assert json.loads(ledger.read_text())['research_Native_Runtime'] is None
    with pytest.raises(ValueError,match='NOT_ADMITTED'):budget.remaining('A')
    ledger.write_text(json.dumps(packet));source.write_text('changed')
    with pytest.raises(ValueError,match='HISTORICAL_LEDGER_DRIFT'):budget.remaining('B')


def test_weight_family_and_invalid_stage_sha_rejected():
    from tools.global_lb_alternative.math import objective
    with pytest.raises(ValueError,match='WRONG_DUAL_ROW_FAMILY'):
        objective({0:dict(thermal=False,constant='0',terms={})},{0:F(1)},{})
    with pytest.raises(ValueError,match='INCOMPLETE_STAGE_BINDING'):
        binding('M2',*['z'*64]*6)

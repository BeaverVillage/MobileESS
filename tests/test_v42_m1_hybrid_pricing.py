"""Zero-Native tests for exact decomposition/prices and certificate scope."""
from copy import deepcopy
from fractions import Fraction
from types import SimpleNamespace
import numpy as np
import pytest
from scipy import sparse
from v42_m1_hybrid.blocks import build_blocks, verify_decomposition
from v42_m1_hybrid.pricing import make_prices, validate_local_column
from v42_m1_hybrid.bound import (assemble_full_dual, certify_global,
    local_exact_price_bound, compare_dw_lagrangian)


def case():
    A = sparse.csr_matrix([[1,0,0,0,0,0], [0,1,0,0,0,0],
        [0,0,1,0,0,0], [0,0,0,1,0,0], [0,0,0,0,1,-1],
        [1,1,1,1,-1,0], [1,1,0,0,0,0], [0,0,0,0,0,0]],dtype=float)
    d = dict(names=np.array([f'node_activity[MESS0{k+1},A,0]' for k in range(4)]
                              +['injection_P[A,0]','rho_max']),
        row_names=np.array(['flow']*4+['line_thermal_face','injection_P_binding','fleet','zero']),
        rhs=np.array([.25]*4+[0,0,2,0],dtype=float),
        sense=np.array(['>']*4+['<','=','<','<']),
        lower=np.zeros(6), upper=np.array([1]*4+[4,4],dtype=float),
        types=np.array(['B']*4+['C','C']),objective=np.array([0]*5+[1.],dtype=float),
        constant=np.asarray(.125))
    return SimpleNamespace(A=A,d=d,case_sha='same-frozen-case')


def prices_case():
    c=case();b=build_blocks(c)
    y={'0':'1','1':'1','2':'1','3':'1','4':'-1','5':'-1'}
    return c,b,make_prices(c,b,y)


def test_complete_original_row_column_nonzero_partition():
    c=case();b=build_blocks(c)
    assert list(b.units)==['MESS01','MESS02','MESS03','MESS04']
    assert b.coupling_rows.tolist()==[5,6]
    assert b.nonunit_block.original_rows.tolist()==[4,7]
    assert b.nonunit_columns.tolist()==[4,5]
    assert b.inclusion['all_original_nonzeros_retained']
    assert not b.inclusion['new_cut']
    assert b.inclusion['full_96_slot_domain_preserved']
    assert sum(z.A.nnz for z in b.units.values())+b.nonunit_block.A.nnz+c.A[b.coupling_rows].nnz==c.A.nnz


@pytest.mark.parametrize('field',['lower','upper','types','objective','rhs','sense','row_names','names'])
def test_local_literal_domain_metadata_mutation_rejected(field):
    c=case();b=build_blocks(c);z=b.units['MESS01'];z.d[field]=z.d[field].copy()
    if z.d[field].dtype.kind in 'fiu':z.d[field][0]+=1
    else:z.d[field][0]='X'
    with pytest.raises(ValueError,match='DRIFT'):
        verify_decomposition(c,b)


def test_coefficient_sparsification_rejected():
    c=case();b=build_blocks(c);b.units['MESS01'].A.data[0]=0.
    with pytest.raises(ValueError,match='CSR_COEFFICIENT_DRIFT'):
        verify_decomposition(c,b)


def test_missing_coupling_or_nonunit_row_rejected():
    c=case();b=build_blocks(c);b.coupling_rows=b.coupling_rows[:1]
    with pytest.raises(ValueError,match='PARTITION_INCOMPLETE'):
        verify_decomposition(c,b)
    b=build_blocks(c);b.nonunit_block.original_rows=b.nonunit_block.original_rows[:1]
    with pytest.raises(ValueError,match='PARTITION_INCOMPLETE'):
        verify_decomposition(c,b)


def test_all_four_units_required():
    c=case();c.d['names'][3]='unowned'
    with pytest.raises(ValueError,match='FOUR_ORIGINAL'):
        build_blocks(c)


def test_multirow_prices_signed_lagrangian_exact_sum_original_constant_once():
    c,b,p=prices_case()
    assert all(p.exact_objectives[u]=={0:Fraction(1)} for u in b.units)
    assert p.coupling_dual=={'0':'-1'}
    cert=certify_global(c,b,p.coupling_dual,p.seed_unit_duals,p.seed_nonunit_dual)
    assert cert['exact_bound']=='9/8'
    exact=Fraction(float(c.d['constant']))+Fraction(p.coupling_constant_exact)
    exact+=Fraction(local_exact_price_bound(b.nonunit_block,p.nonunit_exact_objective,p.seed_nonunit_dual)['exact_bound'])
    exact+=sum((Fraction(local_exact_price_bound(z,p.exact_objectives[u],p.seed_unit_duals[u])['exact_bound'])
                for u,z in b.units.items()),Fraction(0))
    assert exact==Fraction(cert['exact_bound'])
    assert p.full_objective_residual=={}
    assert not cert['structural_integer_block_improvement_proven']


def test_nonunit_dual_or_residual_box_omission_cannot_inflate_bound():
    c,b,p=prices_case()
    cert=certify_global(c,b,p.coupling_dual,p.seed_unit_duals,{})
    assert Fraction(cert['exact_bound'])<=Fraction(9,8)
    assert cert['box_correction_exact']=='-4'
    assert cert['exact_bound']=='-23/8'


def test_missing_unit_dual_rejected():
    c,b,p=prices_case();ys=dict(p.seed_unit_duals);ys.pop('MESS04')
    with pytest.raises(ValueError,match='ALL_FOUR'):
        assemble_full_dual(c,b,p.coupling_dual,ys,p.seed_nonunit_dual)


@pytest.mark.parametrize('row,value',[('0','-1'),('4','1'),('6','1')])
def test_bad_original_signed_price_dual_rejected(row,value):
    c=case();b=build_blocks(c)
    with pytest.raises(ValueError,match='INVALID_LAGRANGIAN_DUAL_SIGN'):
        make_prices(c,b,{row:value})


def test_native_binary64_price_rounding_is_not_the_certificate():
    c=case();b=build_blocks(c);p=make_prices(c,b,{'5':'-1/3'})
    assert p.exact_objectives['MESS01'][0]==Fraction(1,3)
    assert Fraction(float(p.unit_objectives['MESS01'][0]))!=Fraction(1,3)
    cert=certify_global(c,b,p.coupling_dual,p.seed_unit_duals,p.seed_nonunit_dual)
    assert not cert['rounded_pricing_objective_used']
    assert Fraction(cert['exact_bound'])==Fraction(1,8)-Fraction(4,3)


def test_restricted_master_value_never_becomes_global_bound_or_ub():
    r=compare_dw_lagrangian(rmp_objective=100.,pricing_closed=False)
    assert not r['restricted_master_is_global_LB']
    assert not r['restricted_master_is_global_UB']
    assert r['independently_certified_global_LB'] is None
    assert r['integer_block_strengthening']=='NOT_PROVEN'


def test_soft_integer_column_rejected_even_inside_scientific_tolerance():
    c=case();b=build_blocks(c)
    result=validate_local_column(c,b.units['MESS01'],np.array([1.-1e-10]))
    assert result['local_C3A']['PASS']
    assert not result['PASS']
    assert not result['local_C3A']['exact_binary_0_1']
    assert result['rounding']==0 and result['repairs']==0 and not result['global_UB']


def test_literal_column_requires_original_full_and_physical_replay(monkeypatch):
    from v42_m1_research import check_ub
    c=case();b=build_blocks(c);c.point=np.array([1,1,1,1,4,4.],dtype=float)
    c.original_A=c.A;c.original_d=c.d;c.lift=lambda x:x.copy()
    monkeypatch.setattr(check_ub,'physical_replay',lambda c,x:dict(PASS=True,native_optimize_calls=0))
    r=validate_local_column(c,b.units['MESS01'],np.array([1.]))
    assert r['PASS'] and r['original_FULL_local_rows']['PASS']
    assert not r['global_UB'] and not r['grid_coupling_replayed']
    assert r['original_FULL_unit_integer_gate']['exact_binary_0_1']


def test_lifted_original_soft_arc_pattern_rejected_without_repair(monkeypatch):
    c=case();b=build_blocks(c);c.point=np.array([1,1,1,1,4,4.],dtype=float)
    c.original_A=c.A;c.original_d=deepcopy(c.d)
    c.original_d['names'][0]='arc[MESS01,0]'
    def lift(x):
        x=x.copy();x[0]=1.-1e-10;return x
    c.lift=lift
    r=validate_local_column(c,b.units['MESS01'],np.array([1.]))
    assert not r['PASS']
    assert r['reason']=='LIFTED_ORIGINAL_UNIT_INTEGER_PATTERN_NOT_LITERAL'
    assert r['repairs']==0


def test_native_optimize_is_absent_from_build_and_math_source():
    import inspect
    from v42_m1_hybrid.pricing import build_pricing_model
    assert '.optimize(' not in inspect.getsource(build_pricing_model)
    assert '.optimize(' not in inspect.getsource(make_prices)
    assert '.optimize(' not in inspect.getsource(certify_global)


@pytest.mark.parametrize('kind',['MILP','LP'])
def test_builder_keeps_full_matrix_domain_threads_tolerances_without_optimize(monkeypatch,kind):
    import sys
    from v42_m1_hybrid.pricing import build_pricing_model
    class Model:
        def __init__(self,*args,**kwargs):
            self.Params=SimpleNamespace();self.calls=[];self.NumConstrs=0;self.NumVars=0
            self.NumNZs=0;self.NumBinVars=0
        def addMVar(self,n,**kw):
            self.domain=kw;self.NumVars=n
            self.NumBinVars=int(np.sum(np.asarray(kw['vtype'])=='B'))
            return SimpleNamespace()
        def addMConstr(self,A,v,sense,rhs):
            self.rows=(A.copy(),sense.copy(),rhs.copy())
            self.NumConstrs=A.shape[0];self.NumNZs=A.nnz
        def update(self):pass
        def dispose(self):pass
        def optimize(self,*a,**k):raise AssertionError('NATIVE_FORBIDDEN')
    monkeypatch.setitem(sys.modules,'gurobipy',SimpleNamespace(Model=Model,GRB=SimpleNamespace(MINIMIZE=1)))
    c,b,p=prices_case();block=b.units['MESS01']
    model,v,r=build_pricing_model(block,p.unit_objectives['MESS01'],kind,point=np.array([1.]))
    assert np.array_equal(model.rows[0].data,block.A.data)
    assert np.array_equal(model.domain['lb'],block.d['lower'])
    assert np.array_equal(model.domain['ub'],block.d['upper'])
    assert np.array_equal(model.domain['vtype'],block.d['types'] if kind=='MILP' else ['C'])
    assert model.Params.Threads==1 and model.Params.IntFeasTol==1e-8
    assert model.Params.FeasibilityTol==1e-8 and model.Params.MIPGap==.005
    assert not hasattr(model.Params,'MemLimit') and not hasattr(model.Params,'SoftMemLimit')
    assert not hasattr(model.Params,'Presolve') and r['native_optimize_calls']==0

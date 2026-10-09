from fractions import Fraction
from types import SimpleNamespace

import gurobipy as gp
import numpy as np
import pytest
from scipy import sparse

from v42_autonomous_b2 import dw_native


def test_power_of_two_rows_keep_every_binary64_coefficient_and_rhs():
    matrix=sparse.csr_matrix([[1.,-5e-15],[2.,0.],[1e-25,4.]])
    rhs=np.array([1.,2.,-3.])
    original,scaled,scaled_rhs,exponents,receipt=dw_native.scale_rows(matrix,rhs)
    assert exponents[1]==0 and exponents[0]>0 and exponents[2]>exponents[0]
    restored=scaled.copy()
    restored.data=np.ldexp(restored.data,-np.repeat(exponents,np.diff(restored.indptr)))
    assert (restored-original).nnz==0
    assert np.array_equal(np.ldexp(scaled_rhs,-exponents),rhs)
    assert np.array_equal(matrix.data,original.data)
    assert receipt['tiny_nonzero_coefficients_preserved']==2
    assert receipt['coefficients_dropped_or_clipped']==0
    assert receipt['original_FULL_model_rescaled'] is False


def test_exact_dual_pullback_preserves_original_lagrangian_expression():
    matrix=sparse.csr_matrix([[1.,-5e-15],[1e-25,4.]])
    rhs=np.array([1.,-3.]);point=np.array([.5,.75])
    _,scaled,scaled_rhs,exponents,_=dw_native.scale_rows(matrix,rhs)
    native_pi=np.array([-.125,.25])
    pi=dw_native.pullback_pi(native_pi,exponents)
    for i in range(2):
        assert Fraction(float(pi[i]))==Fraction(float(native_pi[i]))*(2**int(exponents[i]))
        assert Fraction(float(scaled_rhs[i]))==Fraction(float(rhs[i]))*(2**int(exponents[i]))
        for j in range(2):
            assert Fraction(float(scaled[i,j]))==Fraction(float(matrix[i,j]))*(2**int(exponents[i]))
    assert np.array_equal(np.ldexp(pi,-exponents),native_pi)


def test_unrepresentable_scaling_or_pi_is_rejected():
    with pytest.raises(ValueError,match='NOT_EXACTLY_REVERSIBLE'):
        dw_native.scale_rows(sparse.csr_matrix([[1e-300,1e300]]),np.array([1.]))
    with pytest.raises(ValueError,match='PI_PULLBACK_NOT_EXACTLY_REVERSIBLE'):
        dw_native.pullback_pi(np.array([1e300]),np.array([100],dtype=np.int32))


@pytest.fixture
def model():
    model=dw_native.ExactRowModel('V42_DW_CONSTRUCTION_ONLY_TEST')
    model.Params.OutputFlag=0
    try:yield model
    finally:model.dispose()


def construct(model):
    variables=model.addMVar(2,lb=np.zeros(2),ub=np.ones(2),vtype='C',obj=np.array([0.,1.]))
    matrix=sparse.csr_matrix([[1.,-5e-15],[1e-25,4.]])
    rhs=np.array([1.,2.]);sense=np.array(['<','='])
    rows=model.addMConstr(matrix,variables,sense,rhs);model.update()
    return matrix,rhs,variables,rows


def test_actual_native_construction_preserves_tiny_entries_without_optimize(model):
    matrix,rhs,_,_=construct(model)
    assert (model.getA()-matrix).nnz==0
    assert np.array_equal(model.getAttr('RHS'),rhs)
    assert model._model.getA().nnz==matrix.nnz
    assert model._model.Status==gp.GRB.LOADED


@pytest.mark.parametrize('kind',['coefficient','RHS','sense','objective','constant','bound','type'])
def test_actual_native_non_tiny_drift_is_never_hidden_by_transport(model,kind):
    _,_,variables,rows=construct(model)
    native=model._model
    if kind=='coefficient':native.chgCoeff(rows._rows[0].item(),variables[0].item(),3.)
    elif kind=='RHS':rows._rows[0].RHS=3.
    elif kind=='sense':rows._rows[0].Sense='>'
    elif kind=='objective':variables[0].Obj=2.
    elif kind=='constant':native.ObjCon=2.
    elif kind=='bound':variables[0].UB=2.
    elif kind=='type':variables[0].VType='B'
    native.update()
    with pytest.raises(ValueError,match='DW_.*DRIFT'):
        model.getAttr('RHS') if kind=='RHS' else model.getA()


def test_scoped_builder_retains_original_code_and_drift_guard():
    from v42_m1_hybrid import dw
    original=dw.build_master
    builder=dw_native.scoped_builder(original,lambda p:p,lambda *a:None)
    assert builder.original_builder.__code__ is original.__code__
    assert 'DW_NATIVE_MATRIX_DRIFT' in original.__code__.co_consts
    assert builder.original_builder.__globals__['matrix_replay'] is dw.matrix_replay
    assert builder.original_builder.__globals__['verify_decomposition'] is dw.verify_decomposition


def test_original_builder_guard_rejects_omission_and_scoped_builder_passes(tmp_path):
    from v42_m1_hybrid import dw
    from v42_m1_hybrid.blocks import build_blocks
    matrix=np.zeros((7,6))
    for i in range(6):matrix[i,i]=1.
    matrix[6,4]=1.;matrix[6,5]=-1.
    data=dict(names=np.array([f'route_flow[M{i},0]' for i in range(1,5)]+['Pch[M1,0,0]','rho_max']),
        lower=np.zeros(6),upper=np.array([1.,1.,1.,1.,1.,10.]),
        types=np.array(['B','B','B','B','C','C']),objective=np.array([0.,0.,0.,0.,0.,1.]),
        rhs=np.array([0.,0.,0.,0.,0.,10.,0.]),sense=np.array(['>','>','>','>','>','<','<']),
        row_names=np.array([str(i) for i in range(7)]),constant=np.array(.5))
    case=SimpleNamespace(A=sparse.csr_matrix(matrix),d=data,
        point=np.array([1.,1.,1.,1.,1e-18,4.]),case_sha='current_case')
    decomp=build_blocks(case)
    with pytest.raises(ValueError,match='DW_NATIVE_MATRIX_DRIFT'):
        dw.build_master(case,decomp,{},tmp_path/'original')
    def output(path):path.mkdir(parents=True,exist_ok=True);return path
    builder=dw_native.scoped_builder(dw.build_master,output,lambda *args:None)
    model,_,_,receipt,_=builder(case,decomp,{},tmp_path/'scoped')
    try:
        assert receipt['PASS'] is True
        assert model._receipt['tiny_nonzero_coefficients_preserved']==1
        assert model.ObjCon==.5 and model.Status==gp.GRB.LOADED
    finally:model.dispose()


def test_pi_wrapper_forwards_native_gurobi_unavailable_error():
    class Unavailable:
        @property
        def Pi(self):raise gp.GurobiError(10005,'Pi unavailable')
    with pytest.raises(gp.GurobiError):
        dw_native.OriginalRows(Unavailable(),np.array([2],dtype=np.int32)).Pi


def test_infinite_source_bounds_remain_unbounded_without_accepting_finite_drift(model):
    variables=model.addMVar(2,lb=np.array([-np.inf,0.]),ub=np.array([np.inf,1.]),
                            vtype='C',obj=np.array([0.,1.]))
    matrix=sparse.csr_matrix([[1.,-5e-15]])
    model.addMConstr(matrix,variables,np.array(['<']),np.array([1.]));model.update()
    assert (model.getA()-matrix).nnz==0
    variables[0].UB=100.;model.update()
    with pytest.raises(ValueError,match='DOMAIN_OR_OBJECTIVE_DRIFT:UB'):
        model.getA()

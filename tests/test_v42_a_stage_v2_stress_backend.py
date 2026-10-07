"""Tiny native BUILD-only adapter checks; Model.optimize is never invoked."""
from fractions import Fraction
import numpy as np
import scipy.sparse as sp
import gurobipy as gp
import pytest
from v42_a_stage_domain_v2.stress_backend import snapshot_of,materialize,row_replay,expressions
from v42_a_stage_domain_v2.lexstage import LinearSnapshot,Objective
from v42_a_stage_domain_v2.execution import guard_model_optimize


def fixture_snapshot():
    return LinearSnapshot(sp.csr_matrix([[1.,0.]]),np.array([0.,-np.inf]),np.array([1.,np.inf]),
        np.array(['<']),np.array([1.]),np.array(['I','C']),
        tuple(Objective(name,((0,1),)) for name in ('rho','migration_count','shift_magnitude','prestart_relocation'))).require()


def test_snapshot_roundtrip_preserves_native_rows_bounds_types_objectives():
    model=gp.Model('SYNTHETIC_BUILD_ONLY');model.Params.OutputFlag=0
    try:
        y=model.addVar(lb=0,ub=3,vtype='I');rho=model.addVar(lb=0,ub=1)
        model.addConstr(y+2*rho<=3)
        objectives=[('rho',rho),('migration_count',y),('shift_magnitude',2*y),('prestart_relocation',0)]
        snapshot=snapshot_of(model,objectives)
        rebuilt,levels=materialize(snapshot,'2025-05-17')
        try:
            captured=snapshot_of(rebuilt,levels)
            assert snapshot.fingerprint()==captured.fingerprint()
            assert rebuilt._v42_a_stage_day=='2025-05-17'
            with pytest.raises(PermissionError,match='STRESS_DATE_OPTIMIZATION_NOT_AUTHORIZED'):
                guard_model_optimize(rebuilt)
        finally:rebuilt.dispose()
    finally:model.dispose()


def test_replay_rejects_nan_in_unreferenced_unbounded_continuous_column():
    with pytest.raises(ValueError,match='FINITE_ORIGINAL_COLUMN_AXIS_POINT_REQUIRED'):
        row_replay(fixture_snapshot(),np.array([1.,np.nan]))


@pytest.mark.parametrize('bad',[np.inf,-np.inf])
def test_replay_rejects_infinite_column(bad):
    with pytest.raises(ValueError,match='FINITE_ORIGINAL_COLUMN_AXIS_POINT_REQUIRED'):
        row_replay(fixture_snapshot(),np.array([1.,bad]))


def test_replay_checks_raw_point_shape_before_arithmetic():
    with pytest.raises(ValueError,match='FINITE_ORIGINAL_COLUMN_AXIS_POINT_REQUIRED'):
        row_replay(fixture_snapshot(),np.array([1.]))


def test_expression_materialization_rejects_nonbinary64_constant():
    model=gp.Model('SYNTHETIC_BUILD_ONLY');model.Params.OutputFlag=0
    try:
        variable=model.addVar();model.update()
        snapshot=fixture_snapshot()
        snapshot=LinearSnapshot(snapshot.matrix,snapshot.lower,snapshot.upper,snapshot.senses,
            snapshot.rhs,snapshot.vtypes,(Objective('rho',(),Fraction(1,3)),))
        with pytest.raises(ValueError,match='NONEXACT_NATIVE_OBJECTIVE_CONSTANT'):
            expressions(snapshot,[variable])
    finally:model.dispose()


def test_materialize_handles_exact_native_infinite_bounds_without_solve():
    snapshot=fixture_snapshot();model,_=materialize(snapshot,'2025-05-19')
    try:
        assert np.isneginf(model.getAttr('LB')[1])
        assert np.isposinf(model.getAttr('UB')[1])
    finally:model.dispose()


def test_replay_preserves_raw_point_and_checks_integrality():
    point=np.array([.5,0.]);copy=point.copy()
    assert not row_replay(fixture_snapshot(),point)['PASS']
    assert np.array_equal(point,copy)
    assert row_replay(fixture_snapshot(),np.array([1.,0.]))['PASS']


def test_integer_certificate_binds_current_native_objective_bound_and_replay():
    from types import SimpleNamespace
    from v42_a_stage_domain_v2.stress_backend import Backend
    backend=Backend();backend.current=fixture_snapshot()
    backend.model=SimpleNamespace(Status=gp.GRB.TIME_LIMIT,SolCount=1,ObjVal=1.,ObjBound=.5,
        ObjCon=0.,getAttr=lambda attr:[1.,0.])
    backend.last_verification=dict(PASS=True,source_matrix_sha256=backend.current.fingerprint())
    assert backend.integer_certificate('shift_magnitude',1.,.5)['PASS']
    assert not backend.integer_certificate('shift_magnitude',1.,.6)['PASS']
    backend.model.getAttr=lambda attr:[0.,1.]
    assert not backend.integer_certificate('shift_magnitude',1.,.5)['PASS']


def test_integer_certificate_rejects_numerical_native_status_and_stale_matrix():
    from types import SimpleNamespace
    from v42_a_stage_domain_v2.stress_backend import Backend
    backend=Backend();backend.current=fixture_snapshot()
    backend.model=SimpleNamespace(Status=gp.GRB.NUMERIC,SolCount=1,ObjVal=1.,ObjBound=.5,
        ObjCon=0.,getAttr=lambda attr:[1.,0.])
    backend.last_verification=dict(PASS=True,source_matrix_sha256=backend.current.fingerprint())
    assert not backend.integer_certificate('shift_magnitude',1.,.5)['PASS']
    backend.model.Status=gp.GRB.OPTIMAL
    backend.last_verification['source_matrix_sha256']='0'*64
    assert not backend.integer_certificate('shift_magnitude',1.,.5)['PASS']


"""Exact reversible Native construction for the original restricted master.

Gurobi omits matrix coefficients smaller than 1e-13 at construction.  The
original CSR-dot-trajectory lambda columns can contain such nonzero values.
Scale only affected RMP rows by positive powers of two, retain the original
builder and its exact matrix guard, and transport Native Pi back to original
rows before the independent original-domain checker sees it.
"""
from types import SimpleNamespace
import math

import gurobipy as gp
import numpy as np
from scipy import sparse

from v42_may_campaign_native90.a_routing import rebound


SAFE_MINIMUM = math.ldexp(1., -40)
DROP_THRESHOLD = 1e-13


def _same_matrix(actual, expected):
    if actual.shape != expected.shape:
        return False
    difference = actual - expected
    difference.eliminate_zeros()
    return difference.nnz == 0


def scale_rows(matrix, rhs):
    """Return an exactly invertible binary64 row representation, never a cut."""
    original = sparse.csr_matrix(matrix, copy=True)
    original.sum_duplicates(); original.eliminate_zeros(); original.sort_indices()
    rhs = np.asarray(rhs, dtype=np.float64)
    if rhs.shape != (original.shape[0],) or not np.isfinite(rhs).all():
        raise ValueError('DW_ROW_SCALING_RHS_REQUIRED')
    if not np.isfinite(original.data).all():
        raise ValueError('DW_ROW_SCALING_FINITE_MATRIX_REQUIRED')
    exponents = np.zeros(original.shape[0], dtype=np.int32)
    tiny = np.flatnonzero(np.abs(original.data) < DROP_THRESHOLD)
    if len(tiny):
        rows = np.searchsorted(original.indptr, tiny, side='right') - 1
        values = np.abs(original.data[tiny])
        # frexp gives x=m*2**e, .5<=m<1.  This integer choice places every
        # affected nonzero at >=2**-40, comfortably above Native omission.
        needed = -39 - np.frexp(values)[1]
        np.maximum.at(exponents, rows, needed)
    entry_exponents = np.repeat(exponents, np.diff(original.indptr))
    with np.errstate(over='ignore', under='ignore', invalid='ignore'):
        data = np.ldexp(original.data, entry_exponents)
        scaled_rhs = np.ldexp(rhs, exponents)
    if (not np.isfinite(data).all() or not np.isfinite(scaled_rhs).all()
            or not np.array_equal(np.ldexp(data, -entry_exponents), original.data)
            or not np.array_equal(np.ldexp(scaled_rhs, -exponents), rhs)
            or np.any((data != 0) & (np.abs(data) < DROP_THRESHOLD))):
        raise ValueError('DW_ROW_SCALING_NOT_EXACTLY_REVERSIBLE')
    scaled = sparse.csr_matrix((data, original.indices.copy(), original.indptr.copy()),
                              shape=original.shape)
    receipt = dict(schema='V42_B2_RMP_EXACT_POWER_OF_TWO_ROWS_V25',
        PASS=True, Native_optimize_calls=0, original_rows=original.shape[0],
        original_columns=original.shape[1], original_nnz=original.nnz,
        scaled_rows=int(np.count_nonzero(exponents)),
        tiny_nonzero_coefficients_preserved=len(tiny),
        maximum_row_scale_exponent=int(exponents.max(initial=0)),
        maximum_absolute_scaled_coefficient=float(np.max(np.abs(data), initial=0)),
        minimum_absolute_original_coefficient=float(np.min(np.abs(original.data)))
            if original.nnz else None,
        matrix_and_RHS_exactly_reversible=True, row_senses_unchanged=True,
        variable_domain_and_objective_unchanged=True,
        original_FULL_model_rescaled=False, coefficients_dropped_or_clipped=0,
        dual_pullback='original_Pi = Native_Pi * 2**row_exponent',
        restricted_master_objective_is_Global_LB=False)
    return original, scaled, scaled_rhs, exponents, receipt


def pullback_pi(pi, exponents):
    pi = np.asarray(pi, dtype=np.float64)
    exponents = np.asarray(exponents, dtype=np.int32)
    if pi.shape != exponents.shape or not np.isfinite(pi).all():
        raise ValueError('DW_NATIVE_PI_FINITE_AXIS_REQUIRED')
    with np.errstate(over='ignore', under='ignore', invalid='ignore'):
        original = np.ldexp(pi, exponents)
        inverse = np.ldexp(original, -exponents)
    if not np.isfinite(original).all() or not np.array_equal(inverse, pi):
        raise ValueError('DW_NATIVE_PI_PULLBACK_NOT_EXACTLY_REVERSIBLE')
    return original


class OriginalRows:
    def __init__(self, rows, exponents):
        self._rows, self._exponents = rows, exponents

    @property
    def Pi(self):
        return pullback_pi(self._rows.Pi, self._exponents)

    def __getattr__(self, name):
        return getattr(self._rows, name)


class ExactRowModel:
    """Expose original RMP axes while the Native model stores scaled rows."""
    def __init__(self, name, *, factory=gp.Model):
        object.__setattr__(self, '_model', factory(name))
        object.__setattr__(self, '_expected', None)

    def __getattr__(self, name):
        return getattr(self._model, name)

    def __setattr__(self, name, value):
        if name.startswith('_'):
            object.__setattr__(self, name, value)
        else:
            setattr(self._model, name, value)
            if name == 'ObjCon':
                object.__setattr__(self, '_objective_constant', float(value))

    def addMVar(self, n, **kwargs):
        object.__setattr__(self, '_domain', {k:np.asarray(v).copy() if k in ('lb','ub','obj') else v
                                          for k,v in kwargs.items()})
        return self._model.addMVar(n, **kwargs)

    def addMConstr(self, matrix, variables, sense, rhs):
        if self._expected is not None:
            raise ValueError('DW_ONE_MATRIX_CONSTRUCTION_REQUIRED')
        original, scaled, scaled_rhs, exponents, receipt = scale_rows(matrix, rhs)
        object.__setattr__(self, '_expected', original)
        object.__setattr__(self, '_scaled', scaled)
        object.__setattr__(self, '_rhs', np.asarray(rhs, dtype=np.float64).copy())
        object.__setattr__(self, '_scaled_rhs', scaled_rhs)
        object.__setattr__(self, '_sense', np.asarray(sense).copy())
        object.__setattr__(self, '_exponents', exponents)
        object.__setattr__(self, '_receipt', receipt)
        rows = self._model.addMConstr(scaled, variables, sense, scaled_rhs)
        return OriginalRows(rows, exponents)

    def getA(self):
        actual = self._model.getA().tocsr()
        if not _same_matrix(actual, self._scaled):
            raise ValueError('DW_SCALED_NATIVE_MATRIX_DRIFT')
        original = actual.copy()
        original.data = np.ldexp(original.data,
            -np.repeat(self._exponents, np.diff(original.indptr)))
        if not _same_matrix(original, self._expected):
            raise ValueError('DW_UNSCALED_NATIVE_MATRIX_DRIFT')
        if not np.array_equal(np.asarray(self._model.getAttr('Sense')), self._sense):
            raise ValueError('DW_NATIVE_ROW_SENSE_DRIFT')
        for name, key in (('LB','lb'), ('UB','ub'), ('Obj','obj')):
            actual=np.asarray(self._model.getAttr(name))
            expected=np.asarray(self._domain[key])
            # Native represents either signed infinity spelling as an
            # unbounded variable. Only already-unbounded inputs may match it.
            matches=actual==expected
            if name in ('LB','UB'):
                matches |= (np.isposinf(expected)&(actual>=gp.GRB.INFINITY))
                matches |= (np.isneginf(expected)&(actual<=-gp.GRB.INFINITY))
            if not np.all(matches):
                raise ValueError('DW_NATIVE_VARIABLE_DOMAIN_OR_OBJECTIVE_DRIFT:'+name)
        if float(self._model.ObjCon)!=getattr(self,'_objective_constant',0.):
            raise ValueError('DW_NATIVE_OBJECTIVE_CONSTANT_DRIFT')
        if any(t != 'C' for t in self._model.getAttr('VType')):
            raise ValueError('DW_NATIVE_CONTINUOUS_RMP_DOMAIN_DRIFT')
        return original

    def getAttr(self, name, *args):
        if name != 'RHS':
            return self._model.getAttr(name, *args)
        actual = np.asarray(self._model.getAttr('RHS', *args))
        if not np.array_equal(actual, self._scaled_rhs):
            raise ValueError('DW_SCALED_NATIVE_RHS_DRIFT')
        original = np.ldexp(actual, -self._exponents)
        if not np.array_equal(original, self._rhs):
            raise ValueError('DW_UNSCALED_NATIVE_RHS_DRIFT')
        return original


def scoped_builder(original, output_directory, write):
    """Retain the original builder, local replay, catalog and exact guard."""
    namespace = dict(original.__globals__, gp=SimpleNamespace(Model=ExactRowModel),
                     output_directory=output_directory, write=write)
    checked = rebound(original, namespace)

    def build(case, decomp, columns, output):
        result = checked(case, decomp, columns, output)
        model = result[0]
        write(output_directory(output)/'RMP_NATIVE_ROW_SCALING.json', model._receipt)
        return result

    build.original_builder = checked
    return build

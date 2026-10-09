"""C3A original MILP construction, with unified policy and no research defaults."""
from contextlib import ExitStack
from time import perf_counter
import numpy as np
from scipy import sparse
import gurobipy as gp
from .audit import ROOT, REPORTS, M_HEAD, write
from .replay import pinned, forbid_native
from .storage import sha
from .policy import Policy


def build_frozen_c3a(*, stage='M1', env=None):
    """Frozen May01 development model. Other A1 anchors must be regenerated.

    The default is Gurobi's native MILP implementation over certified C3A.
    No branching, Benders or failed experiment's solver settings are applied.
    """
    if stage != 'M1':
        raise ValueError('FROZEN_C3A_ONLY_BINDS_ORIGINAL_M1_INPUT')
    out = ROOT/'docs/v42_m1_ultracompact_exact_20261006'
    authority = pinned(out/'ULTRACOMPACT_CURRENT_AUTHORITY_M1.json', M_HEAD)
    if sha(out/'C3A_A.npz') != authority['selected_matrix_SHA256'] or sha(out/'C3A_DATA.npz') != authority['selected_data_SHA256']:
        raise ValueError('C3A_SCIENTIFIC_AUTHORITY_DRIFT')
    A = sparse.load_npz(out/'C3A_A.npz')
    with np.load(out/'C3A_DATA.npz') as z:
        d = {k:z[k].copy() for k in z.files}
    model = gp.Model('V42_PR162_C3A_FROZEN_ORIGINAL_M1', env=env)
    try:
        model.Params.OutputFlag = 0
        variables = model.addMVar(A.shape[1], lb=d['lower'], ub=d['upper'], vtype=d['types'], obj=d['objective'])
        variables.VarName = d['names'].tolist()
        model.ObjCon = float(d['constant'])
        constraints = model.addMConstr(A, variables, d['sense'], d['rhs'])
        constraints.ConstrName = d['row_names'].tolist()
        for key, value in Policy().parameters(stage).items():
            setattr(model.Params, key, value)
        model.update()
        model._v42_unified_input = 'ORIGINAL_PR162_C3A_MAY01_1499_JOBS'
        return model, A, d, authority
    except BaseException:
        model.dispose()
        raise


def build_only():
    start = perf_counter()
    with ExitStack() as stack:
        forbid_native(stack)
        model, A, d, authority = build_frozen_c3a()
        try:
            from v42_integrated.matrix import arrays
            B, current = arrays(model)
            delta = B-A; delta.eliminate_zeros()
            identity = delta.nnz == 0 and all(np.array_equal(d[k],current[k]) for k in d)
            parameters = {k:getattr(model.Params,k) for k in Policy().parameters('M1')}
            result = dict(PASS=bool(identity), rows=model.NumConstrs, columns=model.NumVars,
                          binary=model.NumBinVars, nonzeros=model.NumNZs, parameters=parameters,
                          objective_RHS_axes_bounds_types_coefficients_exact=True,
                          scientific_authority=authority, native_optimize_calls=0,
                          build_and_identity_seconds=perf_counter()-start,
                          failed_experimental_solver_default=False,
                          finite_memory_limits=False, M1_ACCEPTED=False,
                          other_P1_only_anchor_requires_fresh_model_and_equivalence_proofs=True)
        finally:
            model.dispose()
    write(REPORTS/'NATIVE_BUILD_ONLY.json', result)
    if not identity:
        raise ValueError('NATIVE_C3A_MATRIX_IDENTITY_DRIFT')
    return result

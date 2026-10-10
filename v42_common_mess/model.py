"""Clone all current C3A rows, objective, types and continuous bounds."""
from time import perf_counter
import numpy as np
from .storage import write


def build(case, output, *, lower=None, upper=None, continuous=False,
          start=None, spec=None, numeric_parameters=None):
    import gurobipy as gp
    began = perf_counter()
    lower = case.d['lower'].copy() if lower is None else np.asarray(lower, dtype=float)
    upper = case.d['upper'].copy() if upper is None else np.asarray(upper, dtype=float)
    if np.any(lower < case.d['lower']) or np.any(upper > case.d['upper']) or np.any(lower > upper):
        raise ValueError('COMMON_M_RESTRICTION_OUTSIDE_ORIGINAL_DOMAIN')
    types = np.full(len(case.d['types']), 'C') if continuous else case.d['types'].copy()
    model = gp.Model('V42_COMMON_MESS_PRIMAL_ANYTIME_U4_V1')
    try:
        parameters = dict(Threads=1, FeasibilityTol=1e-8, OptimalityTol=1e-8,
            IntFeasTol=1e-8, MIPGap=.005, Method=1 if continuous else 2, MIPFocus=1)
        parameters.update(numeric_parameters or {})
        parameters['Threads'] = 1
        for name, value in parameters.items():
            setattr(model.Params, name, value)
        variables = model.addMVar(case.A.shape[1], lb=lower, ub=upper,
            vtype=types, obj=case.d['objective'])
        variables.VarName = case.d['names'].tolist()
        model.ObjCon = float(case.d['constant'])
        rows = model.addMConstr(case.A, variables, case.d['sense'], case.d['rhs'])
        rows.ConstrName = case.d['row_names'].tolist()
        if spec is not None:
            free = spec['free_binary_columns']
            coefficients = np.where(start[free] == 1., -1., 1.)
            model.addConstr(coefficients @ variables[free] <=
                spec['hamming_radius'] - float(np.count_nonzero(start[free])),
                name='COMMON_M_RESTRICTED_HAMMING_NEVER_GLOBAL_CUT')
        if start is not None:
            discrete = np.flatnonzero(case.d['types'] != 'C')
            if not np.all(start[discrete] == np.rint(start[discrete])):
                raise ValueError('COMMON_M_LITERAL_INTEGER_START_REQUIRED')
            variables.Start = start
        model.update()
        difference = model.getA()[:case.A.shape[0]] - case.A
        difference.eliminate_zeros()
        continuous_columns = case.d['types'] == 'C'
        checks = dict(original_source_rows_exact=difference.nnz == 0,
            original_RHS_exact=np.array_equal(np.asarray(model.getAttr('RHS'))[:case.A.shape[0]], case.d['rhs']),
            original_senses_exact=np.array_equal(np.asarray(model.getAttr('Sense'))[:case.A.shape[0]], case.d['sense']),
            original_objective_exact=np.array_equal(np.asarray(model.getAttr('Obj')), case.d['objective'])
                and model.ObjCon == float(case.d['constant']),
            types_exact=np.array_equal(np.asarray(model.getAttr('VType')), types),
            restricted_bounds_exact=np.array_equal(np.asarray(model.getAttr('LB')), lower)
                and np.array_equal(np.asarray(model.getAttr('UB')), upper),
            original_continuous_bounds_exact=spec is None or (
                np.array_equal(lower[continuous_columns], case.d['lower'][continuous_columns])
                and np.array_equal(upper[continuous_columns], case.d['upper'][continuous_columns])))
        if not all(checks.values()):
            raise ValueError('COMMON_M_ORIGINAL_MODEL_IDENTITY_DRIFT')
        identity = dict(PASS=True, case_sha=case.case_sha, checks=checks,
            original_rows=case.A.shape[0], original_columns=case.A.shape[1],
            original_integer_count=int(np.count_nonzero(case.d['types'] != 'C')),
            original_full_integer_count=int(np.count_nonzero(case.original_d['types'] != 'C')),
            continuous_initialization_only=continuous, objective='minimize rho_max',
            model_rows=model.NumConstrs, build_wall_seconds=perf_counter() - began,
            numeric_parameters=parameters, original_model_identity=case.identity,
            equality_defined_helper_rows=int(sum(str(name).split('[', 1)[0].endswith('_binding')
                for name in case.original_d['row_names'])),
            mip_start_helper_equalities_checked_by_original_FULL_replay=start is not None,
            helper_count_not_hardcoded=True, spec=spec)
        write(output / 'MODEL_IDENTITY.json', identity)
        return model, variables, identity
    except BaseException:
        model.dispose()
        raise

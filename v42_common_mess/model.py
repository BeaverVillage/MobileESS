"""Clone all current C3A rows, objective, types and continuous bounds."""
from time import perf_counter
import numpy as np
from .storage import write
from . import VERSION


def memory_observation():
    """Persist actual process RSS/private/peak and system admission counters."""
    import psutil
    process = psutil.Process()
    info = process.memory_info()
    result = dict(RSS_bytes=info.rss, private_bytes=getattr(info, 'private', info.rss),
        peak_RSS_bytes=getattr(info, 'peak_wset', info.rss),
        peak_private_commit_bytes=getattr(info, 'peak_pagefile', getattr(info, 'private', info.rss)),
        RAM_available=psutil.virtual_memory().available)
    if __import__('os').name == 'nt':
        from v42_svr11.resources import snapshot
        result.update(snapshot())
    return result


def build(case, output, *, lower=None, upper=None, continuous=False,
          start=None, spec=None, numeric_parameters=None):
    import gurobipy as gp
    began = perf_counter()
    memory_before = memory_observation()
    lower = case.d['lower'] if lower is None else np.asarray(lower, dtype=float)
    upper = case.d['upper'] if upper is None else np.asarray(upper, dtype=float)
    if np.any(lower < case.d['lower']) or np.any(upper > case.d['upper']) or np.any(lower > upper):
        raise ValueError('COMMON_M_RESTRICTION_OUTSIDE_ORIGINAL_DOMAIN')
    types = np.full(len(case.d['types']), 'C') if continuous else case.d['types']
    unrestricted = not continuous and spec is None and (
        np.array_equal(lower, case.d['lower']) and np.array_equal(upper, case.d['upper']))
    model = gp.Model(VERSION)
    try:
        parameters = dict(Threads=1, FeasibilityTol=1e-8, OptimalityTol=1e-8,
            IntFeasTol=1e-8, MIPGap=.005, Method=1 if continuous else 2, MIPFocus=1)
        parameters.update(numeric_parameters or {})
        parameters['Threads'] = 1
        parameters['LogFile'] = str(output / 'NATIVE_GUROBI.log')
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
            start = np.asarray(start, dtype=np.float64)
            if start.shape != (case.A.shape[1],) or not np.isfinite(start).all():
                raise ValueError('COMMON_M_FINITE_SAME_DOMAIN_START_REQUIRED')
            discrete = np.flatnonzero(case.d['types'] != 'C')
            if not np.all(start[discrete] == np.rint(start[discrete])):
                raise ValueError('COMMON_M_LITERAL_INTEGER_START_REQUIRED')
            variables.Start = start
        model.update()
        # One temporary native CSR is sufficient. Subtracting two large sparse
        # matrices duplicated both coefficients and index storage at each build.
        native_matrix = model.getA().tocsr()
        source_nnz = int(native_matrix.indptr[case.A.shape[0]])
        matrix_exact = (np.array_equal(native_matrix.indptr[:case.A.shape[0]+1], case.A.indptr)
            and np.array_equal(native_matrix.indices[:source_nnz], case.A.indices)
            and np.array_equal(native_matrix.data[:source_nnz], case.A.data))
        del native_matrix
        continuous_columns = case.d['types'] == 'C'
        checks = dict(original_source_rows_exact=matrix_exact,
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
        unrestricted_checks = dict(all_original_bounds_exact=(
                np.array_equal(lower, case.d['lower']) and np.array_equal(upper, case.d['upper'])),
            all_original_integer_types_exact=np.array_equal(types, case.d['types']),
            all_original_rows_and_no_additional_cuts=model.NumConstrs == case.A.shape[0],
            no_neighborhood_or_hamming_constraint=spec is None,
            original_minimization=model.ModelSense == gp.GRB.MINIMIZE)
        if unrestricted and not all(unrestricted_checks.values()):
            raise ValueError('COMMON_M_UNRESTRICTED_ORIGINAL_MODEL_IDENTITY_DRIFT')
        memory_after = memory_observation()
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
            helper_count_not_hardcoded=True, spec=spec,
            unrestricted_original_C3A_MILP=unrestricted,
            unrestricted_checks=unrestricted_checks,
            memory_before=memory_before, memory_after=memory_after,
            measured_build_RSS_growth_bytes=max(0, memory_after['RSS_bytes']-memory_before['RSS_bytes']),
            measured_build_private_growth_bytes=max(0, memory_after['private_bytes']-memory_before['private_bytes']))
        write(output / 'MODEL_IDENTITY.json', identity)
        return model, variables, identity
    except BaseException:
        model.dispose()
        raise

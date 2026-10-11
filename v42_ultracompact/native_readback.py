"""Read actual native parameters after all overrides, without optimization."""
from pathlib import Path
import math


PRECISION = dict(FeasibilityTol=1e-9, OptimalityTol=1e-9, IntFeasTol=1e-8,
                 NumericFocus=3, ScaleFlag=2)
ROOT_PARAMETERS = dict(Method=2, Threads=1, Crossover=2, NodeMethod=1,
                       MIPFocus=3, DegenMoves=0, PreCrush=1, MIPGap=.03,
                       MIPGapAbs=0., NodefileStart=.5, **PRECISION)


def snapshot(model):
    """Persist supported parameters, including defaults, rather than requests."""
    values = {}
    for name in dir(model.Params):
        if name and name[0].isupper():
            value = getattr(model.Params, name)
            if isinstance(value, (int, float, str)):
                values[name] = value
    return dict(actual_parameters=values, ModelSense=int(model.ModelSense),
                rows=int(model.NumConstrs), columns=int(model.NumVars),
                integer_count=int(model.NumIntVars), nonzeros=int(model.NumNZs),
                optimize_calls=0, presolve_calls=0)


def verify_root_readback(receipt):
    """Reject overrides of the prescribed Root settings before Native entry."""
    actual = receipt['actual_parameters']
    for name, value in ROOT_PARAMETERS.items():
        if actual.get(name) != value:
            raise ValueError('DENSE_ROOT_PARAMETER_READBACK_DRIFT:' + name)
    from gurobipy import GRB
    if actual.get('SolutionLimit') != GRB.MAXINT or receipt['ModelSense'] != GRB.MINIMIZE:
        raise ValueError('DENSE_ROOT_OBJECTIVE_OR_SOLUTION_LIMIT_DRIFT')
    limit = actual.get('TimeLimit')
    if not isinstance(limit, (int, float)) or not math.isfinite(limit) or not 0 < limit <= 600:
        raise ValueError('DENSE_ROOT_NATIVE_CAP_INVALID')
    directory = Path(actual.get('NodefileDir', ''))
    if directory.drive.upper() != 'D:' or not directory.is_dir():
        raise ValueError('DENSE_ROOT_NODEFILE_DIRECTORY_INVALID')
    return dict(PASS=True, actual_parameters_checked=True, actual_TimeLimit=limit,
                recorded_supported_parameters=len(actual), Native_optimize_calls=0)

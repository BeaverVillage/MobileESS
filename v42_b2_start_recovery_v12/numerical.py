"""Reuse the validated precision parameters without changing scientific replay."""
from v42_a_stage_domain_v2.solver_policy import apply_policy as original_apply

PRECISION = dict(FeasibilityTol=1e-9, OptimalityTol=1e-9, NumericFocus=3, ScaleFlag=2)
DAYS = frozenset(f'2025-05-{n:02d}' for n in range(1, 32))
A_COMPONENTS = frozenset(('PHASE_I', 'ORIGINAL_P1', 'INTEGER_CONTROL'))


def precision_enabled(day, component, arm='B1'):
    return day in DAYS and (arm == 'B2' or arm == 'B1' and component in A_COMPONENTS)


def set_precision(model, *, day, component, arm='B1'):
    if day not in DAYS or arm not in ('B1', 'B2'):
        raise PermissionError('V12_PRECISION_REQUIRES_EXACT_MAY_ARM_DATE')
    effective = {}
    if precision_enabled(day, component, arm):
        for name, value in PRECISION.items():
            model.setParam(name, value)
            effective[name] = getattr(model.Params, name)
        if arm == 'B1' and component == 'PHASE_I':
            # The unchanged 29.7-billion-scale May25 equality is rejected after
            # presolve postsolve reconstruction, even at 1e-9. Solve the exact
            # original Phase I rows; the same Method=2 and replay remain intact.
            model.setParam('Presolve', 0)
            effective['Presolve'] = model.Params.Presolve
    return effective


def apply_precision(model, policy, gp, *, day, component):
    effective = original_apply(model, policy, gp)
    effective.update(set_precision(model, day=day, component=component))
    return effective

"""Improve May11 LP arithmetic; retain the original model and acceptance tests."""
from v42_a_stage_domain_v2.solver_policy import apply_policy as original_apply
from .policy import PRECISION


def apply_precision(model, policy, gp, *, day, component):
    effective = original_apply(model, policy, gp)
    if day == '2025-05-11' and component in ('PHASE_I', 'ORIGINAL_P1'):
        for name, value in PRECISION.items():
            model.setParam(name, value)
            effective[name] = getattr(model.Params, name)
    return effective

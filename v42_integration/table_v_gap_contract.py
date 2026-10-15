"""Acceptance targets only; no solver, model, or historical evidence imports."""
import math


AIDC_GLOBAL_GAP_TARGET = .005
MESS_GLOBAL_GAP_TARGET = .03


def restricted_joint_diagnostic(result, *, stopping_target=.005):
    """The restricted Joint gap is diagnostic and never a Global Gap."""
    native = result.get('native_call') or {}
    objective, bound = native.get('current_pool_ObjVal'), native.get('restricted_ObjBound_diagnostic')
    finite = lambda value: type(value) in (int, float) and math.isfinite(value)
    gap = (max(0., (objective-bound) / max(abs(objective), 1e-10))
           if finite(objective) and finite(bound) else None)
    return dict(restricted_joint_ObjVal=objective, restricted_joint_ObjBound=bound,
        restricted_joint_relative_gap=gap, restricted_joint_gap_target=stopping_target,
        restricted_joint_gap_is_global=False)

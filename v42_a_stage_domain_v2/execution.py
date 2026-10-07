"""Task authorization boundary, independent of Gurobi and domain generation.

The four diagnostic dates are permanently blocked in this formulation-review
revision. There is deliberately no environment variable, CLI flag, or fixture
override that can authorize a production date. Synthetic tests use synthetic
identities; they may not borrow a blocked production date.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import date, datetime
from collections.abc import Mapping


STRESS_DATES = frozenset(('2025-05-10', '2025-05-12', '2025-05-17', '2025-05-19'))
BLOCK_REASON = 'STRESS_DATE_OPTIMIZATION_NOT_AUTHORIZED'
BLOCKED_ACTIONS = frozenset(('OPTIMIZE', 'P1', 'P2', 'FEASIBILITY_LP',
    'FEASIBILITY_MIP', 'A1', 'A2', 'PLANNING_FREEZE', 'ACTUAL', 'FRESH_AC'))
_native_day = ContextVar('v42_a_stage_authorized_native_day', default=None)


def normalize_day(value):
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str):
        # Native timestamps use the date in their scientific source timezone.
        # Reject malformed dates rather than interpreting a system timezone.
        result = value[:10]
        try:
            if date.fromisoformat(result).isoformat() == result:
                return result
        except ValueError:
            pass
    raise PermissionError('A_STAGE_PRODUCTION_DAY_REQUIRED')


def day_from_authority(value):
    """Read only explicit date metadata; never inspect scientific future data."""
    if isinstance(value, (date, datetime, str)):
        return normalize_day(value)
    if isinstance(value, Mapping):
        days = []
        for key in ('day', 'date', 'planning_day', 'target_day'):
            if key in value and value[key] is not None:
                days.append(normalize_day(value[key]))
        for key in ('bundle', 'identity', 'payload', 'request', 'plan'):
            if isinstance(value.get(key), Mapping):
                found = day_from_authority(value[key])
                if found is not None:
                    days.append(found)
        if len(set(days)) > 1:
            # A conflict may never hide a stress date behind another date.
            if set(days) & STRESS_DATES:
                raise PermissionError(BLOCK_REASON)
            raise PermissionError('A_STAGE_PRODUCTION_DAY_CONFLICT')
        return days[0] if days else None
    request = getattr(value, 'request', None)
    if isinstance(request, Mapping):
        return day_from_authority(request)
    return None


def require_action_authorized(authority, action='OPTIMIZE', *, require_day=True):
    """Fail before model creation, optimization, freeze, or physical execution."""
    day = day_from_authority(authority)
    if day is None:
        day = _native_day.get()
    if day is None and require_day:
        raise PermissionError('A_STAGE_PRODUCTION_DAY_REQUIRED')
    if day in STRESS_DATES:
        raise PermissionError(BLOCK_REASON)
    return day


@contextmanager
def native_execution_scope(authority, action='OPTIMIZE'):
    day = require_action_authorized(authority, action)
    token = _native_day.set(day)
    try:
        yield day
    finally:
        _native_day.reset(token)


def tag_model_for_day(model, authority, *, require_day=True):
    """Static model construction is permitted; tag without authorizing a solve."""
    day = day_from_authority(authority)
    if day is None and require_day:
        raise PermissionError('A_STAGE_PRODUCTION_DAY_REQUIRED')
    if day is not None:
        original_day=getattr(model,'_v42_a_stage_day',None)
        if original_day is not None and original_day!=day:
            if original_day in STRESS_DATES or day in STRESS_DATES:
                raise PermissionError(BLOCK_REASON)
            raise PermissionError('A_STAGE_PRODUCTION_DAY_CONFLICT')
        model._v42_a_stage_day = day
    return model


def guard_model_optimize(model):
    # Tagged native models are always guarded, including direct optimize calls.
    day = getattr(model, '_v42_a_stage_day', None)
    context_day = _native_day.get()
    if day in STRESS_DATES or context_day in STRESS_DATES:
        raise PermissionError(BLOCK_REASON)
    if day is not None and context_day is not None and day != context_day:
        raise PermissionError('A_STAGE_PRODUCTION_DAY_CONFLICT')


def guarded_optimize(model, authority, *args, **kwargs):
    guard_model_optimize(model)
    require_action_authorized(authority)
    tag_model_for_day(model, authority)
    guard_model_optimize(model)
    return model.optimize(*args, **kwargs)


def install_gurobi_backstop(gp):
    """Preserve the native class; guard optimize/copy/relax without solving.

    copy() and relax() return different native models. Date tags are explicitly
    propagated so feasibility LPs and copied MIPs cannot lose the boundary.
    This installer is idempotent and does not change settings or coefficients.
    """
    model_class = gp.Model
    if getattr(model_class, '_v42_stress_guard_installed', False):
        return
    original_optimize = model_class.optimize

    def optimize(self, *args, **kwargs):
        guard_model_optimize(self)
        return original_optimize(self, *args, **kwargs)

    model_class.optimize = optimize
    for method in ('copy', 'relax', 'presolve', 'fixed'):
        original = getattr(model_class, method, None)
        if original is None:
            continue

        def derived(self, *args, _original=original, _method=method, **kwargs):
            if _method == 'presolve':
                guard_model_optimize(self)
            result = _original(self, *args, **kwargs)
            day = getattr(self, '_v42_a_stage_day', None)
            if day is not None:
                result._v42_a_stage_day = day
            return result

        setattr(model_class, method, derived)
    model_class._v42_stress_guard_installed = True


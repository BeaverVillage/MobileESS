"""Narrow task authority: one exact planned May10 PRESTART model at a time."""
from contextvars import ContextVar
from contextlib import contextmanager
import math
from v42_pr134_b1.common import read
from .isolation import OUT
_scope=ContextVar('may10_prestart_rescue_model',default=None)


def current():return _scope.get()


def authorize(day,action):
    if current() is None or day!='2025-05-10' or action not in ('OPTIMIZE','FEASIBILITY_LP','FEASIBILITY_MIP'):
        raise PermissionError('ONLY_PLANNED_MAY10_PRESTART_NATIVE_AUTHORIZED')
    return day


def guard(model,day):
    scope=current()
    if scope is None or scope[0] is not model or day!='2025-05-10':
        raise PermissionError('EXACT_MAY10_PRESTART_MODEL_SCOPE_REQUIRED')
    from .native import verify_sources
    verify_sources()
    actual=read(OUT/'NATIVE'/scope[1]/'ACTUAL_MODEL_VERIFICATION.json')
    if not actual['PASS'] or (model.NumVars,model.NumConstrs,model.NumNZs)!=(actual['cols'],actual['rows'],actual['nnz']):
        raise PermissionError('EXACT_VERIFIED_MAY10_PRESTART_NATIVE_MODEL_REQUIRED')
    if model.Params.Threads!=1 or not math.isinf(model.Params.MemLimit) or not math.isinf(model.Params.SoftMemLimit):
        raise PermissionError('THREADS_ONE_AND_NO_MEMORY_LIMIT_REQUIRED')
    scope[2]()


@contextmanager
def native_scope(model,name,budget_check):
    token=_scope.set((model,name,budget_check))
    try:
        guard(model,getattr(model,'_v42_a_stage_day',None));yield
    finally:_scope.reset(token)

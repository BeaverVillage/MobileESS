"""Source-frozen May12-only permit; no P2 or downstream execution."""
from contextvars import ContextVar
from contextlib import contextmanager
from .policy import ROOT,OUT,STATIC,DAY
from v42_pr134_b1.common import read,record,sha
_scope=ContextVar('may12_rescue_native_scope',default=None)
def current():return _scope.get()
def active_freeze():
    pointer=OUT/'ACTIVE_SOURCE_FREEZE.json'
    if not pointer.exists():return OUT/'SOURCE_FREEZE.json'
    r=read(pointer)['receipt']
    if record(r['path'])!=r:raise PermissionError('MAY12_ACTIVE_SOURCE_POINTER_DRIFT')
    return r['path']
def verify():
    f=read(active_freeze())
    if f.get('schema')!='MAY12_P1_ONLY_EXACT_RESCUE_V1' or not f.get('PASS'):raise PermissionError('MAY12_FROZEN_SOURCE_REQUIRED')
    for p,h in f['execution_sources'].items():
        if sha(p)!=h:raise PermissionError('MAY12_EXECUTED_SOURCE_DRIFT:'+p)
    if record(f['plan']['path'])!=f['plan']:raise PermissionError('MAY12_IMMUTABLE_PLAN_DRIFT')
    return f
def authorize(day,action):
    s=current()
    if not s or day!=DAY or action not in ('OPTIMIZE','P1','FEASIBILITY_LP','FEASIBILITY_MIP'):raise PermissionError('MAY12_P1_ONLY_SCOPE_REQUIRED')
    return DAY
def guard(model,day):
    s=current()
    if not s or s[0] is not model or day!=DAY:raise PermissionError('MAY12_EXACT_NATIVE_MODEL_REQUIRED')
    if model.Params.Threads!=1 or model.Params.MemLimit<1e100 or model.Params.SoftMemLimit<1e100:
        raise PermissionError('MAY12_THREADS_ONE_UNLIMITED_MEMORY_REQUIRED')
    if s[1] not in ('ORIGINAL_P1','LOCAL_PRICING','INTEGER_CONTROL'):raise PermissionError('MAY12_P2_DOWNSTREAM_FORBIDDEN')
    if not read(OUT/'PHASE1_ZERO_CERTIFICATE.json')['PASS']:raise PermissionError('MAY12_REAL_ZERO_BEFORE_P1')
    if s[1]=='INTEGER_CONTROL' and not read(OUT/'COMPLETE_PRICING_CLOSURE.json')['PASS']:raise PermissionError('FULL_PRICING_CLOSURE_BEFORE_INTEGER')
    if s[1]!='INTEGER_CONTROL' and model.NumIntVars:raise PermissionError('LP_COMPONENT_MUST_BE_CONTINUOUS')
    s[2]()
@contextmanager
def native_scope(model,component,budget_check):
    verify();t=_scope.set((model,component,budget_check))
    try:guard(model,getattr(model,'_v42_a_stage_day',None));yield
    finally:_scope.reset(t)

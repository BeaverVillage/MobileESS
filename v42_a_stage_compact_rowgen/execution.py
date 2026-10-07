"""Source-bound stage permits; historical permits and scientific guards remain."""
from contextvars import ContextVar
from contextlib import contextmanager
from v42_pr134_b1.common import read,record,sha
from .policy import OUT,DAY,POLICY
_scope=ContextVar('overnight_compact_exact_stage',default=None)
def current():return _scope.get()
def verify():
    freeze=read(OUT/'SOURCE_FREEZE.json')
    if freeze.get('PASS') is not True or freeze.get('schema')!='A_PRACTICAL_EXACT_OVERNIGHT_V1':raise PermissionError('OVERNIGHT_SOURCE_BOUND_PERMIT_REQUIRED')
    if read(OUT/'POLICY.json')!=POLICY:raise PermissionError('OVERNIGHT_POLICY_DRIFT')
    for p,d in freeze['execution_sources'].items():
        if sha(p)!=d:raise PermissionError('OVERNIGHT_EXECUTION_SOURCE_DRIFT:'+p)
    for r in freeze['gate_receipts']:
        if record(r['path'])!=r or read(r['path']).get('PASS') is not True:raise PermissionError('OVERNIGHT_GATE_DRIFT')
    return freeze
def authorize(day,action):
    if day!=DAY or action not in ('OPTIMIZE','FEASIBILITY_LP'):raise PermissionError('OVERNIGHT_CURRENT_STAGE_LP_ONLY')
    return day
def guard(model,day):
    s=current()
    if s is None or s[0] is not model or day!=DAY or model.NumIntVars or s[1] not in ('PHASE_I','LOCAL_PRICING'):raise PermissionError('OVERNIGHT_EXACT_LP_SCOPE_REQUIRED')
    s[2]()
@contextmanager
def native_scope(model,component,budget_check):
    verify();t=_scope.set((model,component,budget_check))
    try:guard(model,DAY);yield
    finally:_scope.reset(t)

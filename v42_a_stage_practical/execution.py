from contextvars import ContextVar
from contextlib import contextmanager
from v42_pr134_b1.common import read,record,sha
from .policy import OUT,DAY,POLICY
_scope=ContextVar('practical_rowcol_native_stage',default=None)
def current():return _scope.get()
def verify():
    f=read(OUT/'PRACTICAL_SOURCE_FREEZE.json')
    if f.get('PASS') is not True or f.get('schema')!=POLICY['schema']:raise PermissionError('PRACTICAL_STAGE_SOURCE_PERMIT_REQUIRED')
    for p,h in f['execution_sources'].items():
        if sha(p)!=h:raise PermissionError('PRACTICAL_STAGE_SOURCE_DRIFT:'+p)
    for r in f['gate_receipts']:
        if record(r['path'])!=r or read(r['path']).get('PASS') is not True:raise PermissionError('PRACTICAL_STAGE_GATE_DRIFT')
    return f
def authorize(day,action):
    if day!=DAY or action not in ('OPTIMIZE','P1','FEASIBILITY_LP'):raise PermissionError('PRACTICAL_CURRENT_STAGE_LP_ONLY')
    return day
def guard(model,day):
    s=current()
    if s is None or s[0] is not model or day!=DAY or model.NumIntVars or s[1] not in ('PHASE_I','LOCAL_PRICING','ORIGINAL_P1'):raise PermissionError('PRACTICAL_EXACT_LP_SCOPE_REQUIRED')
    if s[1]=='ORIGINAL_P1':
        z=read(OUT/'FROZEN64_RESULT.json')
        if not z.get('certified_zero'):
            z=read(OUT/'ADAPTIVE_PHASE1_RESULT.json')
        if not z.get('certified_zero') or not read(z['closure_certificate']['path'])['zero']['PASS']:raise PermissionError('P1_CERTIFIED_ZERO_AND_ORIGINAL_REPLAY_REQUIRED')
    s[2]()
@contextmanager
def native_scope(model,component,budget_check):
    verify();t=_scope.set((model,component,budget_check))
    try:guard(model,DAY);yield
    finally:_scope.reset(t)

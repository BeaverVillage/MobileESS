from contextvars import ContextVar
from contextlib import contextmanager
from v42_pr134_b1.common import read,record,sha
from .policy import OUT,DAY,POLICY
_scope=ContextVar('practical_lex_refine_native',default=None)
def current():return _scope.get()
def verify():
    f=read(OUT/'LEX_REFINE_SOURCE_FREEZE.json')
    if f.get('PASS') is not True or f.get('schema')!=POLICY['schema']:raise PermissionError('INTEGER_SOURCE_PERMIT_REQUIRED')
    for p,h in f['execution_sources'].items():
        if sha(p)!=h:raise PermissionError('INTEGER_SOURCE_DRIFT:'+p)
    for r in f['gate_receipts']:
        if record(r['path'])!=r or read(r['path']).get('PASS') is not True:raise PermissionError('INTEGER_GATE_DRIFT')
    return f
def authorize(day,action):
    if day!=DAY or action not in ('OPTIMIZE','P1','P2','FEASIBILITY_LP','FEASIBILITY_MIP'):raise PermissionError('INTEGER_CURRENT_DAY_ONLY')
    return day
def guard(model,day):
    s=current()
    if s is None or s[0] is not model or day!=DAY or s[1] not in ('INTEGER_CONTROL','NODE_LP','LOCAL_PRICING','P2'):raise PermissionError('INTEGER_EXACT_MODEL_SCOPE_REQUIRED')
    r=read(OUT/'P1_RESULT.json')
    if not r['P1_LP_closure'] or r['valid_LB'] is None:raise PermissionError('FULL_DOMAIN_P1_LP_CLOSURE_REQUIRED_BEFORE_INTEGER')
    if s[1] in ('NODE_LP','LOCAL_PRICING') and model.NumIntVars:raise PermissionError('NODE_LP_MUST_BE_CONTINUOUS')
    if s[1]=='P2' and not read(OUT/'INTEGER_RESULT.json').get('P1_accepted'):raise PermissionError('P2_REQUIRES_FULL_DOMAIN_P1_ACCEPTANCE')
    s[2]()
@contextmanager
def native_scope(model,component,budget_check):
    verify();t=_scope.set((model,component,budget_check))
    try:guard(model,DAY);yield
    finally:_scope.reset(t)

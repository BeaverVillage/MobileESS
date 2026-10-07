"""Only the three requested canaries, after actual May19 A1 acceptance."""
from contextvars import ContextVar
from contextlib import contextmanager
from v42_pr134_b1.common import read,record,sha
from .policy import OUT,OVERNIGHT,DAYS,POLICY
_scope=ContextVar('practical_requested_canary',default=None)
def current():return _scope.get()
def verify():
    f=read(OUT/'CANARY_SOURCE_FREEZE.json')
    if f.get('PASS') is not True or f.get('schema')!=POLICY['schema']:raise PermissionError('CONDITIONAL_CANARY_SOURCE_PERMIT_REQUIRED')
    for p,h in f['execution_sources'].items():
        if sha(p)!=h:raise PermissionError('CANARY_SOURCE_DRIFT:'+p)
    for r in f['gate_receipts']:
        if record(r['path'])!=r or read(r['path']).get('PASS') is not True:raise PermissionError('CANARY_GATE_DRIFT')
    if not read(OVERNIGHT/'P2_CASE_RESULT.json').get('A1_accepted'):raise PermissionError('MAY19_A1_ACCEPTANCE_REQUIRED')
    return f
def authorize(day,action):
    s=current()
    if day not in DAYS or s is None or day!=s[3] or action not in ('OPTIMIZE','P1','P2','FEASIBILITY_LP','FEASIBILITY_MIP'):raise PermissionError('REQUESTED_CANARY_NATIVE_ACTION_ONLY')
    return day
def guard(model,day):
    s=current()
    if s is None or s[0] is not model or day!=s[3] or day not in DAYS:raise PermissionError('CANARY_EXACT_MODEL_SCOPE_REQUIRED')
    folder=OUT/day
    if not read(folder/'INITIAL_VERIFICATION.json').get('PASS'):raise PermissionError('CANARY_STATIC_INPUT_AND_PROJECTION_GATES_REQUIRED')
    if s[1] in ('PHASE_I','ORIGINAL_P1','LOCAL_PRICING','NODE_LP') and model.NumIntVars:raise PermissionError('CANARY_LP_COMPONENT_MUST_BE_CONTINUOUS')
    if s[1] in ('ORIGINAL_P1','INTEGER_CONTROL','P2') and not read(folder/'PHASE_I_ZERO_CERTIFICATE.json').get('PASS'):raise PermissionError('CANARY_ORIGINAL_MODEL_REQUIRES_CERTIFIED_ZERO')
    if s[1]=='INTEGER_CONTROL' and not read(folder/'P1_RESULT.json').get('P1_LP_closure'):raise PermissionError('CANARY_FULL_P1_LP_CLOSURE_REQUIRED')
    if s[1]=='P2' and not read(folder/'INTEGER_RESULT.json').get('P1_accepted'):raise PermissionError('CANARY_P2_REQUIRES_FULL_DOMAIN_P1_ACCEPTANCE')
    s[2]()
@contextmanager
def native_scope(model,component,budget_check):
    verify();day=getattr(model,'_v42_a_stage_day',None)
    if component not in ('PHASE_I','ORIGINAL_P1','INTEGER_CONTROL','NODE_LP','LOCAL_PRICING','P2'):raise PermissionError('UNREQUESTED_CANARY_COMPONENT')
    t=_scope.set((model,component,budget_check,day))
    try:guard(model,day);yield
    finally:_scope.reset(t)

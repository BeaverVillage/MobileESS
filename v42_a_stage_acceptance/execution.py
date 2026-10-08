from contextvars import ContextVar
from contextlib import contextmanager
from v42_pr134_b1.common import read,record,sha
from .policy import OUT,OLD,DAYS,POLICY
_scope=ContextVar('a_stage_acceptance_native',default=None)
def current():return _scope.get()
def active_freeze():
    pointer=OUT/'ACTIVE_SOURCE_FREEZE.json'
    if pointer.exists():
        r=read(pointer)['receipt']
        if record(r['path'])!=r:raise PermissionError('CURRENT_SOURCE_EPOCH_POINTER_DRIFT')
        return r['path']
    return OUT/'CONTINUATION_SOURCE_FREEZE.json'
def verify():
    f=read(active_freeze())
    if not f.get('PASS') or f['schema']!=POLICY['schema']:raise PermissionError('CONTINUATION_SOURCE_FREEZE_REQUIRED')
    for p,h in f['execution_sources'].items():
        if sha(p)!=h:raise PermissionError('CONTINUATION_SOURCE_DRIFT:'+p)
    if record(OUT/'CONTINUATION_BUDGET.json')!=f['budget']:raise PermissionError('IMMUTABLE_NEW_BUDGET_DRIFT')
    return f
def authorize(day,action):
    s=current()
    if s is None or day not in DAYS or day!=s[3] or action not in ('OPTIMIZE','P1','P2','FEASIBILITY_LP','FEASIBILITY_MIP'):
        raise PermissionError('CURRENT_REQUESTED_A_STAGE_NATIVE_ONLY')
    return day
def guard(model,day):
    s=current()
    if s is None or s[0] is not model or day!=s[3] or day not in DAYS:raise PermissionError('CONTINUATION_EXACT_MODEL_SCOPE_REQUIRED')
    folder=OUT/day
    if day==DAYS[0]:
        if s[1]!='P2' or not read(folder/'SHIFT_GLOBAL_GAP_ACCEPTANCE.json')['PASS']:
            raise PermissionError('MAY19_SHIFT_ACCEPTANCE_BEFORE_PRESTART_ONLY')
    else:
        if not read(OUT/DAYS[0]/'A1_RESULT.json').get('A1_accepted'):raise PermissionError('ACTUAL_MAY19_A1_ACCEPTANCE_REQUIRED')
        for prior in DAYS[1:DAYS.index(day)]:
            if not (OUT/prior/'RESULT.json').exists():raise PermissionError('FOURDAY_REQUESTED_ORDER_REQUIRED')
        if not read(folder/'INITIAL_VERIFICATION.json')['PASS']:raise PermissionError('DAY_SPECIFIC_INPUT_BUILD_REQUIRED')
        if s[1] in ('ORIGINAL_P1','INTEGER_CONTROL','P2') and not read(folder/'PHASE_I_ZERO_CERTIFICATE.json')['PASS']:
            raise PermissionError('CERTIFIED_ZERO_BEFORE_ORIGINAL_MODEL_REQUIRED')
        if s[1]=='INTEGER_CONTROL' and not read(folder/'P1_RESULT.json')['P1_LP_closure']:
            raise PermissionError('FULL_DOMAIN_COLUMN_AND_ROW_CLOSURE_REQUIRED')
        if s[1]=='P2' and not read(folder/'INTEGER_RESULT.json')['P1_accepted']:
            raise PermissionError('GLOBAL_P1_ACCEPTANCE_BEFORE_P2_REQUIRED')
    if s[1] in ('PHASE_I','ORIGINAL_P1','LOCAL_PRICING','NODE_LP') and model.NumIntVars:
        raise PermissionError('ORIGINAL_LP_CONTINUOUS_REQUIRED')
    if model.Params.Threads!=1:raise PermissionError('THREADS_ONE_REQUIRED')
    s[2]()
@contextmanager
def native_scope(model,component,budget_check):
    verify();day=getattr(model,'_v42_a_stage_day',None)
    if component not in ('PHASE_I','ORIGINAL_P1','INTEGER_CONTROL','LOCAL_PRICING','NODE_LP','P2'):
        raise PermissionError('UNREQUESTED_CONTINUATION_COMPONENT')
    t=_scope.set((model,component,budget_check,day))
    try:guard(model,day);yield
    finally:_scope.reset(t)

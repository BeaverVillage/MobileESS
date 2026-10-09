from v42_b2_start_recovery_v13.m_stage import prepare as original_prepare
from .common import atomic
from .execution import current
from .policy import MODEL_FIELDS

def prepare(request,progress=None):
    from time import perf_counter,process_time
    started=perf_counter();cpu=process_time();native_before=len(request['_budget'].calls)
    case=original_prepare(request,progress)
    atomic(case.output/'ORIGINAL_MODEL_BUILD_TIMING.json',dict(wall_seconds=perf_counter()-started,
        CPU_seconds=process_time()-cpu,Native_calls=len(request['_budget'].calls)-native_before,
        scope='ORIGINAL_MODEL_AND_STATIONARY_BACKGROUND_PROBE; BEFORE_V19_INITIALIZATION'))
    expected=current()['manifest']['model_identity'].get(request['day'])
    actual={k:case.identity[k] for k in MODEL_FIELDS}
    if expected is not None and expected!=actual:raise ValueError('ORIGINAL_FULL_MODEL_SHA_DRIFT')
    atomic(case.output/'V19_MODEL_IDENTITY_VERIFICATION.json',dict(PASS=True,expected=expected,actual=actual,
        prior_same_day_model_available=expected is not None,original_model_transport=case.identity['transport']))
    if case.point is None:
        from .initialization import initialize
        case.point=initialize(case,request['_budget'],progress)
    return case

def exhausted_seed(case,budget,progress):
    """F5 already ran inside initialize; never launch another old 900s seed."""
    from .common import read
    failure=read(case.output/'INITIALIZATION_FAILURE.json')
    return None,dict(failure,status='TIME_LIMIT_NO_VALID_INCUMBENT',
        reason='V19_F1_F5_EXHAUSTED_WITHOUT_ORIGINAL_FULL_VALID_POINT',
        automatic_retry=False,Native_Runtime=budget.used())

def run(request,budget,progress=None):
    """Preserve the old case.point handoff and every downstream algorithm byte."""
    from v42_b2_seed_recovery_v18.m_stage import run as admitted_run
    from v42_may_campaign_native90.a_routing import rebound
    return rebound(admitted_run,dict(admitted_run.__globals__,prepare=prepare,
        seed_integer=exhausted_seed))(request,budget,progress)

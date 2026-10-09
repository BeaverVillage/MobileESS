from v42_b2_start_recovery_v13.m_stage import prepare as original_prepare
from .common import atomic
from .execution import current
from .policy import MODEL_FIELDS

def prepare(request,progress=None):
    case=original_prepare(request,progress)
    expected=current()['manifest']['model_identity'][request['day']]
    actual={k:case.identity[k] for k in MODEL_FIELDS}
    if expected!=actual:raise ValueError('ORIGINAL_FULL_MODEL_SHA_DRIFT')
    atomic(case.output/'V18_MODEL_IDENTITY_VERIFICATION.json',dict(PASS=True,expected=expected,actual=actual))
    if case.point is None:
        from .initialization import initialize
        case.point=initialize(case,request['_budget'],progress)
    return case

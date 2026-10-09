from v42_may_campaign_native90 import m_stage as original
from v42_b2_start_recovery_v13.m_stage import prepare as original_prepare
from v42_may_campaign_native90.a_routing import rebound
from .seed_policy import seed_integer
from .common import atomic
from .policy import MODEL_FIELDS
from .execution import current


def prepare(request, progress=None):
    case = original_prepare(request, progress)
    context = current()
    expected = context['manifest'].get('model_identity', {}).get(request['day'], {}) if context else {}
    actual = {k:case.identity[k] for k in MODEL_FIELDS}
    if expected and expected != actual:
        raise ValueError('V17_RESTART_ORIGINAL_MODEL_SHA_DRIFT')
    atomic(case.output/'V17_MODEL_IDENTITY_VERIFICATION.json',dict(PASS=True,
        case_sha=case.case_sha,expected=expected,actual=actual,new_source_SHA=request.get('implementation_SHA'),
        original_FULL_physics_and_integer_domain_unchanged=True))
    return case


def run(request, budget, progress=None):
    return rebound(original.run,dict(original.run.__globals__,prepare=prepare,
        _seed_integer=seed_integer))(request,budget,progress)

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
        raise ValueError('V18_RESTART_ORIGINAL_MODEL_SHA_DRIFT')
    atomic(case.output/'V18_MODEL_IDENTITY_VERIFICATION.json',dict(PASS=True,
        case_sha=case.case_sha,expected=expected,actual=actual,new_source_SHA=request.get('implementation_SHA'),
        original_FULL_physics_and_integer_domain_unchanged=True))
    if case.point is None:
        from .initialization import initialize
        case.point=initialize(case,request['_budget'],progress)
    return case


def run(request, budget, progress=None):
    from contextlib import ExitStack
    from unittest.mock import patch
    from v42_m1_hybrid import bound,verify
    from v42_m1_research import lb
    from .certificate_box import check
    # Source bytes and exact evaluator stay frozen. Only proved certificate-box
    # inputs compose the old checker's existing lower/upper API.
    with ExitStack() as stack:
        for module in (original,bound,verify,lb):
            stack.enter_context(patch.object(module,'check_rational_dual_certificate',check))
        return rebound(original.run,dict(original.run.__globals__,prepare=prepare,
            _seed_integer=seed_integer))(request,budget,progress)

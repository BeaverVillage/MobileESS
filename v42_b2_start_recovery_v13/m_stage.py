"""Use the original M algorithm with only the versioned case-construction port."""
from v42_may_campaign_native90 import m_stage as original
from v42_may_campaign_native90.a_routing import rebound


def prepare(request, progress=None):
    from v42_b2_build_authority_v13 import build_case
    return rebound(original.prepare, dict(original.prepare.__globals__, build_case=build_case))(request, progress)


def run(request, budget, progress=None):
    return rebound(original.run, dict(original.run.__globals__, prepare=prepare))(request, budget, progress)

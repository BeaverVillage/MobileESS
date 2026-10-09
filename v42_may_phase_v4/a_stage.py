"""Opt-in routing for the original A-stage with stable Phase I normalization."""
from v42_may_campaign_native90 import a_stage as original
from v42_may_campaign_native90.a_routing import rebound, group
from .phase import VERSION, routed_group


def run(request, budget, progress=None):
    if request.get('phase_weights_version') != VERSION:
        raise PermissionError('SEPARATELY_ADMITTED_PHASE_VERSION_REQUIRED')

    def route(module, names, **routing):
        if module.__name__ == 'v42_a_stage_canary.phase':
            return routed_group(module, names, **routing)
        return group(module, names, **routing)

    delegate = rebound(original.run, dict(original.run.__globals__, group=route))
    return delegate(request, budget, progress)

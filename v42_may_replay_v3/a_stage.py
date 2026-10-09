"""Opt-in A-stage adapter; original builder, phase, physics and budget unchanged.

This version requires a separately admitted source boundary. It never changes
the frozen native90 manifest or installs itself into a live Worker.
"""
from pathlib import Path
from v42_may_campaign_native90 import a_stage as original
from v42_may_campaign_native90.a_routing import rebound
from v42_pr134_b1.common import atomic
from .replay import ReplayNative, VERSION


def classify_result(result, failure):
    if failure and result.get('classification') == 'IMPLEMENTATION_FAILURE' and (
            not result.get('accepted') and not result.get('PASS')):
        result = dict(result, classification='NUMERICAL_FAILURE',
            numerical_replay=failure, diagnostic_version=VERSION,
            scientific_infeasibility_proven=False)
    return result


def run(request, budget, progress=None):
    if request.get('replay_diagnostics_version') != VERSION:
        raise PermissionError('SEPARATELY_ADMITTED_REPLAY_VERSION_REQUIRED')
    delegates = []

    def native(*args, **kwargs):
        delegate = ReplayNative(original._native(*args, **kwargs))
        delegates.append(delegate)
        return delegate

    routed = rebound(original.run, dict(original.run.__globals__, _native=native))
    result = routed(request, budget, progress)
    failure = delegates[0].failure if delegates else None
    result = classify_result(result, failure)
    if failure:
        atomic(Path(request['output'])/'A_RESULT.json', result)
    return result

"""An explicit new campaign permit; all historical authorization stays intact."""
from contextvars import ContextVar
from contextlib import contextmanager
from pathlib import Path
from .common import verify_manifest, sha, worker_slot

_active = ContextVar('v42_may_campaign_permit', default=None)
_model = ContextVar('v42_may_campaign_native_model', default=None)
COMPONENTS = frozenset(('P1', 'ORIGINAL_P1', 'PHASE_I', 'INTEGER_CONTROL', 'NODE_LP',
    'LOCAL_PRICING', 'FEASIBILITY_LP', 'FEASIBILITY_MIP', 'LP_DUAL', 'UB', 'PRICING', 'RMP'))


def current():
    return _active.get()


@contextmanager
def worker_scope(request):
    slot = worker_slot(request)
    manifest_path = Path(request['manifest'])
    manifest = verify_manifest(manifest_path)
    root = Path(request['root']).resolve()
    key = request['arm'] + '/' + request['day']
    if (request['run_id'] != manifest['run_id'] or key not in manifest['input_folders']
            or manifest_path.resolve() != root / 'CAMPAIGN_MANIFEST.json'
            or request.get('manifest_SHA') != sha(manifest_path)
            or Path(request['input_folder']).resolve() != Path(manifest['input_folders'][key]).resolve()):
        raise PermissionError('WORKER_MANIFEST_DATE_ARM_IDENTITY')
    expected = dict(Threads=1, P2_calls=0, wall_budget_seconds=5400,
                    native_budget_seconds=5400,
                    target_gap=.005 if request['arm'] == 'B1' else .03)
    if any(request.get(name) != value for name, value in expected.items()):
        raise PermissionError('WORKER_MANIFEST_POLICY_IDENTITY')
    token = _active.set(dict(request=dict(request), manifest=manifest,
                            manifest_sha=request['manifest_SHA'], worker_slot=slot))
    try:
        yield
    finally:
        _active.reset(token)


def authorize(day, action):
    context = current()
    if context is None:
        raise PermissionError('CAMPAIGN_SCOPE_REQUIRED')
    if day is None or day != context['request']['day']:
        raise PermissionError('CAMPAIGN_DATE_CONFLICT')
    if action in ('P2', 'A2', 'M2'):
        raise PermissionError('CAMPAIGN_P1_ONLY')
    if action not in COMPONENTS | {'OPTIMIZE', 'A1', 'PLANNING_FREEZE', 'ACTUAL', 'FRESH_AC'}:
        raise PermissionError('CAMPAIGN_ACTION_NOT_REGISTERED:' + action)
    if action == 'A1' and context['request']['arm'] != 'B1':
        raise PermissionError('B2_AIDC_OPTIMIZATION_FORBIDDEN')
    return day


def guard(model):
    context = current()
    scope = _model.get()
    if context is None or scope is None or scope['model'] is not model:
        raise PermissionError('CAMPAIGN_NATIVE_MODEL_SCOPE_REQUIRED')
    if scope['component'] not in COMPONENTS:
        raise PermissionError('CAMPAIGN_P2_FORBIDDEN')
    day = getattr(model, '_v42_a_stage_day', context['request']['day'])
    authorize(day, scope['component'])
    if int(model.Params.Threads) != 1:
        raise PermissionError('CAMPAIGN_THREADS_ONE_REQUIRED')
    if context['request']['arm'] == 'B2' and scope.get('track') == 'A':
        raise PermissionError('B2_AIDC_OPTIMIZATION_FORBIDDEN')
    if context.get('worker_slot') is not None:
        # Recheck actual processes before each Native entry. This also rejects
        # an external historical worker launched after our initial admission.
        from .worker import assert_no_other_native_worker
        assert_no_other_native_worker(context['request'])


@contextmanager
def native_scope(model, component='P1', track=None):
    context = current()
    if context is None:
        raise PermissionError('CAMPAIGN_SCOPE_REQUIRED')
    authorize(context['request']['day'], component)
    token = _model.set(dict(model=model, component=component, track=track))
    try:
        yield
    finally:
        _model.reset(token)

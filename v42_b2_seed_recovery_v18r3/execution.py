from contextlib import contextmanager
from pathlib import Path
import psutil
from .common import worker_slot, read, same_process
from .policy import verify_request
from v42_may_campaign import execution as legacy
from v42_may_campaign_native90.execution import COMPONENTS, authorize, native_scope, current


def assert_peers(request):
    seen_days, slots = {request['day']}, {worker_slot(request)}
    for proc in psutil.process_iter(['pid','name']):
        if proc.pid == psutil.Process().pid or (proc.info['name'] or '').lower() not in ('python.exe','pythonw.exe'):
            continue
        try:
            args = proc.cmdline(); module = args[args.index('-m')+1] if '-m' in args else ''
            if module == 'v42_b2_seed_recovery_v18r3.worker':
                peer = read(args[-1]); verify_request(peer)
                if peer['manifest_SHA'] != request['manifest_SHA'] or peer['day'] in seen_days or worker_slot(peer) in slots:
                    raise PermissionError('V18R3_CONFLICTING_WORKER')
                seen_days.add(peer['day']); slots.add(worker_slot(peer))
            elif module.endswith('.worker') and (module.startswith(('v42_may','v42_b2_start','v42_b2_seed_recovery','v42_m1_','v42_a_stage'))):
                raise PermissionError('V18R3_OLD_SCIENTIFIC_WORKER_STILL_RUNNING')
        except psutil.Error:
            continue
    if len(slots) > 3:
        raise PermissionError('V18R3_MAX_THREE_WORKERS')


def guard(model):
    context, scope = current(), legacy._model.get()
    if context is None or scope is None or scope['model'] is not model or scope['component'] not in COMPONENTS:
        raise PermissionError('V18R3_NATIVE_MODEL_SCOPE_REQUIRED')
    authorize(context['request']['day'],scope['component'])
    if model.Params.Threads != 1 or scope.get('track') == 'A':
        raise PermissionError('V18R3_B2_P1_THREADS_ONE_ONLY')
    assert_peers(context['request'])


@contextmanager
def worker_scope(request):
    manifest = verify_request(request); assert_peers(request)
    token = legacy._active.set(dict(request=dict(request),manifest=manifest,
        manifest_sha=request['manifest_SHA'],worker_slot=worker_slot(request)))
    before = legacy.guard; legacy.guard = guard
    try:
        yield manifest
    finally:
        legacy.guard = before; legacy._active.reset(token)

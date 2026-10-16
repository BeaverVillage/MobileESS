"""Process-local authority under the coordinator's real external OS lease."""
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
import os
from .common import verify,read,NotReady
from .locks import alive,EXTERNAL_LOCKS

_active=ContextVar('V44_CASE_LEASE',default=None)


@contextmanager
def case_scope(request,lease,worker):
    if not alive(lease) or not alive(worker):raise NotReady('V44_LIVE_COORDINATOR_AND_CASE_PROCESS_REQUIRED')
    token=_active.set(dict(request=request,lease=lease,worker=worker))
    try:yield
    finally:_active.reset(token)


def assert_current():
    c=_active.get()
    if c is None or c['worker']['pid']!=os.getpid() or not alive(c['lease']):raise NotReady('V44_LIVE_CASE_LEASE_REQUIRED')
    from .prepare import require_execution_permit
    from .common import DOC
    permit=c['request'].get('execution_permit')
    if not permit:raise PermissionError('V44_EXPLICIT_EXECUTION_PERMIT_REQUIRED')
    verify([permit])
    if read(permit['path']).get('mode')=='V44_MAY01_B2_SVR11_PILOT_V1':
        from .pilot import validate_permit
        validate_permit(permit['path'],c['request'])
    else:require_execution_permit(permit['path'],read(DOC/'PREEXECUTION_CERTIFICATION.json'))
    verify(c['request']['sources']);return c


@contextmanager
def shared_lease_scope(path):
    c=assert_current()
    if Path(path).resolve() not in [p.resolve() for p in EXTERNAL_LOCKS]:raise PermissionError('UNKNOWN_LEGACY_RESOURCE_LOCK')
    if set(c['lease']['external_locks'])!={str(p) for p in EXTERNAL_LOCKS}:raise PermissionError('COMPLETE_LEGACY_LOCK_LEASE_REQUIRED')
    yield


@contextmanager
def native_stage(request):
    from v42_may_campaign import execution as legacy
    from v42_may_campaign_native90 import execution as inherited
    from v42_may_campaign_native90 import budget
    c=assert_current();old=(legacy.guard,inherited.guard,budget.guard);original=inherited.guard
    token=legacy._active.set(dict(request=request,manifest=dict(schema='V44_DATED_STAGE'),
        worker_slot=None,V44_worker_slot=c['worker']['worker_slot'],manifest_sha=request['source_sha']))
    def guard(model):assert_current();original(model)
    legacy.guard=inherited.guard=budget.guard=guard
    try:yield
    finally:
        legacy.guard,inherited.guard,budget.guard=old
        legacy._active.reset(token)

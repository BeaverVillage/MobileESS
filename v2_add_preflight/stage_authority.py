"""Separate V2_add approval/OS lease over unchanged source Native guards.

This module never creates an approval or starts a campaign on import.
Native0 preparation does not enter this production authority.
"""
from contextlib import contextmanager,ExitStack
from contextvars import ContextVar
from pathlib import Path
from unittest.mock import patch
import os
import psutil
from .stage_common import OUT,RUN,SOURCE,read,record
from .stage_resources import campaign_scope

_active=ContextVar('V2_ADD_LIVE_CASE_AUTHORITY',default=None)
_lease=ContextVar('V2_ADD_OWNED_OS_LEASE',default=None)
_source_records=ContextVar('V2_ADD_WRITE_LOCKED_SOURCE_RECORDS',default=None)


def require_approval(path):
    final=OUT/'FINAL_MAY01_PRESTART_GO_NO_GO.json'
    if not final.exists() or read(final).get('status')!='READY_FOR_MAY01_CAMPAIGN_APPROVAL':
        raise PermissionError('PRESTART_BLOCKED_WITH_EVIDENCE')
    permit=read(path)
    certificate=read(final)
    from v42_native.contracts import digest
    if (permit.get('explicit_human_campaign_approval') is not True
            or permit.get('prestart_certificate_sha')!=record(final)['sha256']
            or permit.get('experiment_id')!='V2_add' or permit.get('days')!=['2025-05-01']
            or not certificate.get('execution_identity')
            or permit.get('execution_identity_sha')!=digest(certificate['execution_identity'])
            or permit.get('human_instruction')!=certificate['execution_identity']['human_instruction']):
        raise PermissionError('MATCHING_FUTURE_HUMAN_MAY01_APPROVAL_REQUIRED')
    instruction=permit['human_instruction']
    if record(instruction['path'])!=instruction:raise PermissionError('HUMAN_INSTRUCTION_FILE_DRIFT')
    from .stage_pause import verify
    verify(certificate['execution_identity']['iteration2_pause'])
    return permit


def current():
    context=_active.get()
    if context is None:raise PermissionError('V2_ADD_LIVE_APPROVED_CASE_SCOPE_REQUIRED')
    p=psutil.Process()
    if context['worker']['pid']!=os.getpid() or context['worker']['process_created']!=p.create_time():
        raise PermissionError('V2_ADD_WORKER_IDENTITY_DRIFT')
    if record(context['approval']['path'])!=context['approval']:raise PermissionError('V2_ADD_APPROVAL_FILE_DRIFT')
    for expected in context['request']['sources']:
        protected=_source_records.get()
        if (protected(expected['path']) if protected else record(expected['path']))!=expected:
            raise PermissionError('V2_ADD_IMMUTABLE_SOURCE_DRIFT')
    return context


@contextmanager
def diagnostic_lease(root,approval):
    """Explicit short numerical canary, never an official campaign permit."""
    from .stage_pause import verify as verify_pause
    from .stage_campaign import source_files
    from .stage_immutable_io import ImmutableRecords
    from .prestart_execution import owned_lock,atomic
    from .stage_gurobi_io import scope as gurobi_io
    from .stage_budget import scope as budget_scope
    from v44.locks import EXTERNAL_LOCKS,exclusive_lock,process_identity
    from v42_native.contracts import digest
    permit=read(approval);root=Path(root).resolve()
    if (not root.is_relative_to((RUN/'isolated_numerical_canary').resolve())
            or permit.get('role')!='ISOLATED_NUMERICAL_CANARY'
            or permit.get('explicit_human_canary_authorization') is not True
            or permit.get('official_campaign_result') is not False
            or permit.get('source_sha')!=digest(SOURCE)
            or permit.get('Native_seconds_per_account')!=30.
            or permit.get('source_files')!=source_files()):
        raise PermissionError('EXPLICIT_SEPARATE_SHORT_CANARY_AUTHORITY_REQUIRED')
    instruction=permit['human_instruction']
    if record(instruction['path'])!=instruction:raise PermissionError('CANARY_HUMAN_INSTRUCTION_DRIFT')
    verify_pause(permit['iteration2_pause'])
    with ExitStack() as stack:
        stack.enter_context(owned_lock(root))
        for path in EXTERNAL_LOCKS:stack.enter_context(exclusive_lock(path))
        protected=ImmutableRecords(row['path'] for row in permit['source_files'])
        source_token=_source_records.set(protected.wrap(record))
        def release_sources():
            profile=protected.report();protected.close();_source_records.reset(source_token)
            atomic(root/'IMMUTABLE_SOURCE_IO_PROFILE.json',profile)
        stack.callback(release_sources)
        stack.enter_context(gurobi_io());stack.enter_context(budget_scope())
        # Numerical diagnostics use the same telemetry-only memory policy;
        # the separate lease/output/30-second accounts confer no official
        # campaign authorization and do not alter Native0 protections.
        stack.enter_context(campaign_scope())
        lease=dict(**process_identity(),external_locks=[str(p) for p in EXTERNAL_LOCKS],root=str(root),
            approval=record(approval),worker_slot=1,role='ISOLATED_NUMERICAL_CANARY')
        token=_lease.set(lease)
        try:yield lease
        finally:_lease.reset(token)


@contextmanager
def campaign_lease(root,approval):
    require_approval(approval)
    from .prestart_execution import owned_lock
    from v44.locks import EXTERNAL_LOCKS,exclusive_lock,process_identity
    root=Path(root)
    if not root.resolve().is_relative_to((RUN/'official_stage_campaign').resolve()):
        raise PermissionError('OWN_V2_ADD_OFFICIAL_STAGE_RUNTIME_REQUIRED')
    root.mkdir(parents=True,exist_ok=True)
    with ExitStack() as stack:
        stack.enter_context(owned_lock(root))
        # Actual inherited byte-range locks remain authoritative. There is no
        # RAM admission threshold and no forced termination of a peer.
        for path in EXTERNAL_LOCKS:stack.enter_context(exclusive_lock(path))
        from .stage_campaign import source_files
        from .stage_immutable_io import ImmutableRecords
        from .prestart_execution import atomic
        identity=read(OUT/'FINAL_MAY01_PRESTART_GO_NO_GO.json')['execution_identity']
        if source_files()!=identity['source_files']:raise PermissionError('APPROVED_SOURCE_SET_DRIFT')
        for expected in [identity['hardware'],*identity['inputs'].values()]:
            if record(expected['path'])!=expected:raise PermissionError('APPROVED_HARDWARE_OR_INPUT_DRIFT')
        protected=ImmutableRecords(row['path'] for row in identity['source_files'])
        source_token=_source_records.set(protected.wrap(record))
        def release_sources():
            profile=protected.report();protected.close();_source_records.reset(source_token)
            atomic(root/'IMMUTABLE_SOURCE_IO_PROFILE.json',profile)
        stack.callback(release_sources)
        from .stage_timing import telemetry
        stack.enter_context(telemetry(root))
        from .stage_gurobi_io import scope as gurobi_io
        from .stage_budget import scope as budget_scope
        from .stage_case_cache import scope as case_cache_scope
        with gurobi_io(),campaign_scope(),budget_scope(),case_cache_scope():
            lease=dict(**process_identity(),external_locks=[str(p) for p in EXTERNAL_LOCKS],root=str(root.resolve()),
                approval=record(approval),worker_slot=1)
            token=_lease.set(lease)
            try:yield lease
            finally:_lease.reset(token)


@contextmanager
def stage_scope(request,lease):
    from v44 import execution
    from v42_may_campaign_native90 import budget
    if request['day']!='2025-05-01' or request['arm'] not in ('B0','B1','B2','B3'):
        raise ValueError('V2_ADD_MAY01_AXIS_REQUIRED')
    p=psutil.Process()
    if lease is not _lease.get():raise PermissionError('ACTUALLY_HELD_OS_LEASE_REQUIRED')
    if lease['pid']!=p.pid or lease['process_created']!=p.create_time():raise PermissionError('OWN_LIVE_OS_LEASE_REQUIRED')
    root=Path(lease['root']).resolve()
    if not Path(request['output']).resolve().is_relative_to(root):raise PermissionError('OWN_OFFICIAL_OUTPUT_ROOT_REQUIRED')
    context=dict(request=request,lease=lease,worker=lease,approval=lease['approval'])
    old_path=budget.d_path
    def path(value):
        candidate=Path(value).resolve()
        return candidate if candidate.is_relative_to(root) else old_path(value)
    token=_active.set(context)
    try:
        with ExitStack() as stack:
            stack.enter_context(patch.object(execution,'assert_current',current))
            stack.enter_context(patch.object(budget,'d_path',path))
            if request['stage'] in ('M1','M2'):
                from .stage_threads import scope as threads
                stack.enter_context(threads(request))
            # The original stage scope, authorization checks, Native Runtime
            # accounting and source thread guards are still used.
            with execution.native_stage(request):yield current()
    finally:_active.reset(token)

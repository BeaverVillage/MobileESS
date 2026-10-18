"""One safe revision transition after the current worker naturally exits."""
from pathlib import Path
import time
from v44.common import read,record,verify,atomic,now
from v44.locks import alive,exclusive_lock,process_identity

REASON='R029_VALIDATED_REPAIRS_SAFE_HANDOVER'


def boundary(guard,*,lease,workers):
    if workers or alive(lease):return False
    if any(alive(guard[k]) for k in ('protected_worker','protected_coordinator')):return False
    if guard.get('superseded_handover') and alive(guard['superseded_handover']):return False
    p=Path(guard['protected_case_root'])/'RESULT.json'
    return p.exists() and read(p).get('status') in ('COMPLETE','FAILED','BLOCKED','BLOCKED_DEPENDENCY','USER_STOPPED')


def require_boundary():
    from .operations import OPS,CAMPAIGN,workers
    guard=read(OPS/'R029_HANDOVER_GUARD.json');lease=read(CAMPAIGN/'COORDINATOR_LEASE.json')
    if alive(lease):
        import psutil
        if 'v44_recovery_r029.operations' in psutil.Process(lease['pid']).cmdline():return guard
    if not boundary(guard,lease=lease,workers=workers()):raise PermissionError('R029_PROTECTED_WORKER_BOUNDARY_REQUIRED')
    return guard


def activate(lease):
    from .operations import OPS,PERMIT
    p=OPS/'CURRENT_HANDOFF.json';v=read(p)
    if v.get('active_revision')=='v44_recovery_r029':return
    atomic(OPS/'R029_PRE_ACTIVATION_HANDOFF_PRESERVED.json',v)
    guard=read(OPS/'R029_HANDOVER_GUARD.json')
    v.update(UTC=now(),active_revision='v44_recovery_r029',algorithm_revision='v44_recovery_r029',
        source_root='D:/v44_may01_07_prepare_20261016',adapter_source_root=str(Path(__file__).resolve().parents[1]),
        permit=record(PERMIT),entry='python -m v44_recovery_r029.operations --handover',
        active_operational_entry='v44_recovery_r029.operations',active_operational_permit=None,
        pending_revision=None,pending_permit=None,pending_validation=None,
        windows_task='MobileESS_V44_Campaign004_Recovery_R029',protected_case=guard['protected_case_root'],
        dispatch_hold_reason=None,collector=str(OPS/'collect_watchdog_r029.py'),
        active_source_auditor=str(OPS/'audit_active_revision_r029.py'),
        latest_user_instruction='Fix all errors; diagnose and fix May02 B3 P1; reuse validated Planning where possible.',
        next='Diagnosed new attempts only; preserve PASS/Raw/Native. May06 fixed-integer Planning repair then Actual/Fresh; May02 fresh A2 with certified P1 acceleration.')
    atomic(p,v)


def release_repairs(ops,permit):
    require_boundary()
    for pending in sorted((ops/'R029_PENDING_REPAIR_RELEASES').glob('*.json')):
        release=read(pending)
        verify([release['repair_validation'],release['failed_queue_receipt'],release['execution_permit'],release['failed_result']])
        if release['execution_permit']!=record(permit):raise ValueError('R029_PENDING_RELEASE_WRONG_PERMIT')
        target=ops/'R026F1_REPAIR_RELEASES'/pending.name
        if target.exists():raise FileExistsError('R029_REPAIR_RELEASE_ALREADY_EXISTS')
        atomic(target,release)


def run():
    from .operations import OPS,CAMPAIGN,PERMIT,validate,workers,watchdog
    validate();guard=read(OPS/'R029_HANDOVER_GUARD.json')
    with exclusive_lock(OPS/'R029_HANDOVER.lock'):
        stop=OPS/'STOP_AUTONOMY.json'
        if stop.exists() and read(stop).get('reason')!=REASON:
            value=read(stop)
            permitted=(value.get('reason')=='R028_VALIDATED_REPAIRS_SAFE_HANDOVER'
                and value.get('user_stop') is False and guard.get('superseded_handover_stop')==record(stop))
            if not permitted:
                atomic(OPS/'R029_HANDOVER_USER_STOP.json',dict(UTC=now(),stop=value));return
            verify([guard['authorization']])
            if not read(guard['authorization']['path']).get('supersedes_pending_r028'):
                raise PermissionError('R029_SUPERSEDING_HANDOVER_AUTHORIZATION_REQUIRED')
            atomic(OPS/'R029_SUPERSEDED_R028_STOP_PRESERVED.json',value)
            atomic(stop,dict(UTC=now(),reason=REASON,user_stop=False,current_worker_must_finish=True,
                authorization=guard['authorization'],supersedes='R028_PENDING_HANDOVER_ONLY'))
        if not stop.exists():atomic(stop,dict(UTC=now(),reason=REASON,user_stop=False,
            current_worker_must_finish=True,authorization=record(OPS/'R029_USER_AUTHORIZATION.json')))
        while True:
            if not stop.exists() or read(stop).get('reason')!=REASON:return
            lease=read(CAMPAIGN/'COORDINATOR_LEASE.json');active=workers()
            atomic(OPS/'R029_HANDOVER_HEARTBEAT.json',dict(UTC=now(),**process_identity(),
                protected_case=guard['protected_case_root'],coordinator=lease,workers=active,
                worker_interrupted=False,waiting_for_natural_terminal=True))
            if boundary(guard,lease=lease,workers=active):break
            time.sleep(15.)
        validate();require_boundary()
        # The old coordinator reads the shared queue on every poll. Publish
        # new-permit releases only after its natural exit, never during it.
        release_repairs(OPS,PERMIT)
        stop.rename(OPS/'R029_HANDOVER_STOP_PRESERVED.json')
        atomic(OPS/'R029_HANDOVER_APPLIED.json',dict(UTC=now(),permit=record(PERMIT),
            protected_worker_interrupted=False,old_sources_modified=False))
    watchdog()

"""Wait for the entire May02 B3 case; then enable faster May03+ A stages."""
import time
from pathlib import Path
from v44.common import read,atomic,record,verify,now
from v44.locks import exclusive_lock,alive,process_identity

REASON='R020_PHASE_I_REBUILD_PERFORMANCE_SAFE_HANDOVER_AFTER_MAY02_B3'


def boundary(guard,*,lease,workers):
    target=Path(guard['protected_case_root'])
    if workers or alive(lease):return False
    for name in ('protected_worker','protected_coordinator'):
        if alive(guard[name]):return False
    path=target/'RESULT.json'
    if not path.exists():return False
    value=read(path)
    return value.get('status') in ('COMPLETE','FAILED','BLOCKED_DEPENDENCY')


def require_boundary():
    from .operations import OPS,CAMPAIGN,workers
    guard=read(OPS/'R020_HANDOVER_GUARD.json')
    lease=read(CAMPAIGN/'COORDINATOR_LEASE.json')
    if alive(lease):
        import psutil
        if 'v44_recovery_r020.operations' in psutil.Process(lease['pid']).cmdline():
            return guard
    if not boundary(guard,lease=lease,workers=workers()):
        raise PermissionError('R020_PROTECTED_B3_ENTIRE_CASE_NOT_FINISHED')
    return guard


def activate(lease):
    from .operations import OPS,PERMIT
    guard=read(OPS/'R020_HANDOVER_GUARD.json')
    path=OPS/'CURRENT_HANDOFF.json';value=read(path)
    if value.get('active_revision')=='v44_recovery_r020':return
    atomic(OPS/'R020_PRE_ACTIVATION_HANDOFF_PRESERVED.json',value)
    value.update(UTC=now(),active_revision='v44_recovery_r020',permit=record(PERMIT),
        entry='python -m v44_recovery_r020.operations --handover',
        windows_task='MobileESS_V44_Campaign004_Recovery_R020',
        pending_revision=None,pending_permit=None,pending_validation=None,
        next_performance_revision='v44_recovery_r020',performance_revision_state='R020_ACTIVE_MAY03_ONWARD_AFTER_MAY02_B3',
        active_operational_entry='v44_recovery_r020.operations',active_operational_permit=None,
        protected_case=guard['protected_case_root'],protected_case_finished_receipt=record(Path(guard['protected_case_root'])/'RESULT.json'),
        r020_coordinator=lease,r020_improved_arms=['B0','B1','B3'],dispatch_hold_reason=None,
        next='Apply faster exact Phase I rebuilds to remaining cases from May03 onward; continue existing sequential queue.')
    atomic(path,value)


def run():
    from .operations import CAMPAIGN,OPS,PERMIT,validate,workers,watchdog
    permit=validate();guard=read(OPS/'R020_HANDOVER_GUARD.json')
    verify([permit['autonomous_recovery_overlay']['handover_guard']])
    with exclusive_lock(OPS/'R020_HANDOVER.lock'):
        while True:
            stop=OPS/'STOP_AUTONOMY.json';value=read(stop) if stop.exists() else {}
            if value and value.get('reason')!=REASON:
                atomic(OPS/'R020_HANDOVER_USER_STOP.json',dict(UTC=now(),stop=value));return
            lease=read(CAMPAIGN/'COORDINATOR_LEASE.json');active=workers()
            atomic(OPS/'R020_HANDOVER_HEARTBEAT.json',dict(UTC=now(),**process_identity(),
                protected_case=guard['protected_case_root'],protected_coordinator=lease,
                coordinator_alive=alive(lease),workers=active,
                policy='WAIT_ENTIRE_ACTUAL_AND_INDEPENDENT_FRESH_AND_NATURAL_WORKER_COORDINATOR_EXIT'))
            if not value and alive(lease):
                import psutil
                if 'v44_recovery_r020.operations' in psutil.Process(lease['pid']).cmdline():break
            if boundary(guard,lease=lease,workers=active):break
            time.sleep(15.)
        validate()
        stop=OPS/'STOP_AUTONOMY.json'
        if stop.exists():
            if read(stop).get('reason')!=REASON:return
            require_boundary()
            archive=OPS/'R020_HANDOVER_STOP_PRESERVED.json'
            if archive.exists():raise FileExistsError('R020_HANDOVER_STOP_ALREADY_PRESERVED')
            stop.rename(archive)
        atomic(OPS/'R020_HANDOVER_APPLIED.json',dict(UTC=now(),permit=record(PERMIT),
            protected_worker_interrupted=False,protected_case=guard['protected_case_root'],
            Native_optimization_repeated=False,improved_arms=['B0','B1','B3']))
    watchdog()

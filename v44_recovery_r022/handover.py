"""Wait for the entire May02 B3 case; then enable faster May03+ A stages."""
import time
from pathlib import Path
from v44.common import read,atomic,record,verify,now
from v44.locks import exclusive_lock,alive,process_identity

REASON='R022_MAY02_B3_FRESH_A2_ROWGEN_RESTART'


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
    guard=read(OPS/'R022_HANDOVER_GUARD.json')
    lease=read(CAMPAIGN/'COORDINATOR_LEASE.json')
    if alive(lease):
        import psutil
        if 'v44_recovery_r022.operations' in psutil.Process(lease['pid']).cmdline():
            return guard
    if not boundary(guard,lease=lease,workers=workers()):
        raise PermissionError('R022_PROTECTED_B3_ENTIRE_CASE_NOT_FINISHED')
    return guard


def activate(lease):
    from .operations import OPS,PERMIT
    guard=read(OPS/'R022_HANDOVER_GUARD.json')
    path=OPS/'CURRENT_HANDOFF.json';value=read(path)
    if value.get('active_revision')=='v44_recovery_r022':return
    atomic(OPS/'R022_PRE_ACTIVATION_HANDOFF_PRESERVED.json',value)
    value.update(UTC=now(),active_revision='v44_recovery_r022',permit=record(PERMIT),
        adapter_source_root=str(Path(__file__).resolve().parents[1]),
        entry='python -m v44_recovery_r022.operations --handover',
        windows_task='MobileESS_V44_Campaign004_Recovery_R022',
        pending_revision=None,pending_permit=None,pending_validation=None,
        next_performance_revision='v44_recovery_r022',performance_revision_state='R022_ACTIVE_MAY03_ONWARD_AFTER_MAY02_B3',
        active_operational_entry='v44_recovery_r022.operations',active_operational_permit=None,
        protected_case=guard['protected_case_root'],protected_case_finished_receipt=record(Path(guard['protected_case_root'])/'RESULT.json'),
        r022_coordinator=lease,r022_improved_arms=['B0','B1','B3'],dispatch_hold_reason=None,
        active_regressions=read(OPS/'R022_CHANGE_AND_VALIDATION.json')['regressions'],
        collector=str(OPS/'collect_watchdog_r022.py'),active_source_auditor=str(OPS/'audit_active_revision_r022.py'),
        next='Priority May02 B3 fresh A2 from completed M1 with zero new A2 Native clock and numerical stability; then continue future B1/B3 A2 performance queue.')
    atomic(path,value)


def run():
    from .operations import CAMPAIGN,OPS,PERMIT,validate,workers,watchdog
    permit=validate();guard=read(OPS/'R022_HANDOVER_GUARD.json')
    verify([permit['autonomous_recovery_overlay']['handover_guard']])
    with exclusive_lock(OPS/'R022_HANDOVER.lock'):
        while True:
            stop=OPS/'STOP_AUTONOMY.json';value=read(stop) if stop.exists() else {}
            if value and value.get('reason')!=REASON:
                atomic(OPS/'R022_HANDOVER_USER_STOP.json',dict(UTC=now(),stop=value));return
            lease=read(CAMPAIGN/'COORDINATOR_LEASE.json');active=workers()
            atomic(OPS/'R022_HANDOVER_HEARTBEAT.json',dict(UTC=now(),**process_identity(),
                protected_case=guard['protected_case_root'],protected_coordinator=lease,
                coordinator_alive=alive(lease),workers=active,
                policy='WAIT_ENTIRE_ACTUAL_AND_INDEPENDENT_FRESH_AND_NATURAL_WORKER_COORDINATOR_EXIT'))
            if not value and alive(lease):
                import psutil
                if 'v44_recovery_r022.operations' in psutil.Process(lease['pid']).cmdline():break
            if boundary(guard,lease=lease,workers=active):break
            time.sleep(15.)
        validate()
        stop=OPS/'STOP_AUTONOMY.json'
        if stop.exists():
            if read(stop).get('reason')!=REASON:return
            require_boundary()
            archive=OPS/'R022_HANDOVER_STOP_PRESERVED.json'
            if archive.exists():raise FileExistsError('R022_HANDOVER_STOP_ALREADY_PRESERVED')
            stop.rename(archive)
        atomic(OPS/'R022_HANDOVER_APPLIED.json',dict(UTC=now(),permit=record(PERMIT),
            protected_worker_interrupted=False,protected_case=guard['protected_case_root'],
            Native_optimization_repeated=False,improved_arms=['B0','B1','B3']))
    watchdog()

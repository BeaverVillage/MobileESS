"""Wait for the entire May02 B3 case; then enable faster May03+ A stages."""
import time
from pathlib import Path
from v44.common import read,atomic,record,verify,now
from v44.locks import exclusive_lock,alive,process_identity

REASON='R026F1_NEXT_DAY_ASSEMBLY_SAFE_HANDOVER'


def boundary(guard,*,lease,workers):
    target=Path(guard['protected_case_root'])
    if workers or alive(lease):return False
    for name in ('protected_worker','protected_coordinator'):
        if alive(guard[name]):return False
    path=target/'RESULT.json'
    if not path.exists():return False
    value=read(path)
    return value.get('status') in ('COMPLETE','FAILED','BLOCKED_DEPENDENCY','USER_STOPPED')


def require_boundary():
    from .operations import OPS,CAMPAIGN,workers
    guard=read(OPS/'R026F1_HANDOVER_GUARD.json')
    lease=read(CAMPAIGN/'COORDINATOR_LEASE.json')
    if alive(lease):
        import psutil
        if 'v44_recovery_r026f1.operations' in psutil.Process(lease['pid']).cmdline():
            return guard
    if not boundary(guard,lease=lease,workers=workers()):
        raise PermissionError('R026F1_PROTECTED_B3_ENTIRE_CASE_NOT_FINISHED')
    return guard


def activate(lease):
    from .operations import OPS,PERMIT
    guard=read(OPS/'R026F1_HANDOVER_GUARD.json')
    path=OPS/'CURRENT_HANDOFF.json';value=read(path)
    if value.get('active_revision')=='v44_recovery_r026f1':return
    atomic(OPS/'R026F1_PRE_ACTIVATION_HANDOFF_PRESERVED.json',value)
    value.update(UTC=now(),active_revision='v44_recovery_r026f1',permit=record(PERMIT),
        adapter_source_root=str(Path(__file__).resolve().parents[1]),
        entry='python -m v44_recovery_r026f1.operations --handover',
        windows_task='MobileESS_V44_Campaign004_Recovery_R026F1',
        pending_revision=None,pending_permit=None,pending_validation=None,
        next_performance_revision='v44_recovery_r026f1',performance_revision_state='R026F1_R023_A2_VOLTAGE_RECOVERY_PHASE1500_ACTIVE',
        active_operational_entry='v44_recovery_r026f1.operations',active_operational_permit=None,
        algorithm_revision='v44_recovery_r026f1',unconditional_future_B1_B3=True,pilot_PASS_required=False,
        protected_case=guard['protected_case_root'],protected_case_finished_receipt=record(Path(guard['protected_case_root'])/'RESULT.json'),
        r026f1_coordinator=lease,r026f1_improved_arms=['B0','B1','B3'],dispatch_hold_reason=None,
        active_regressions=read(OPS/'R026F1_CHANGE_AND_VALIDATION.json')['regressions'],
        collector=str(OPS/'collect_watchdog_r026f1.py'),active_source_auditor=str(OPS/'audit_active_revision_r026f1.py'),
        next='Every subsequent unstarted B1 A1 and B3 A2 uses r026f1 fast sparse assembly and r022 row generation unconditionally; current A2 outcome does not gate rollout.')
    atomic(path,value)


def run():
    from .operations import CAMPAIGN,OPS,PERMIT,validate,workers,watchdog
    permit=validate();guard=read(OPS/'R026F1_HANDOVER_GUARD.json')
    verify([permit['autonomous_recovery_overlay']['handover_guard']])
    with exclusive_lock(OPS/'R026F1_HANDOVER.lock'):
        while True:
            stop=OPS/'STOP_AUTONOMY.json';value=read(stop) if stop.exists() else {}
            lease=read(CAMPAIGN/'COORDINATOR_LEASE.json');active=workers()
            if value and value.get('reason')!=REASON:
                from .failure_continue import technical_hold,defer
                authorization=OPS/'R026F1_USER_AUTHORIZATION.json'
                authorized_resume=False
                if authorization.exists() and guard.get('superseded_user_stop')==record(stop):
                    verify([guard['authorization']]);a=read(authorization)
                    authorized_resume=(a.get('explicit_resume_May02_B3_A2_Native0') is True
                        and a.get('supersedes_previous_user_stop') is True)
                if authorized_resume:
                    if not boundary(guard,lease=lease,workers=active):time.sleep(15.);continue
                    archive=OPS/'R026F1_PREVIOUS_USER_STOP_PRESERVED.json'
                    if archive.exists():raise FileExistsError('R026F1_USER_STOP_ALREADY_PRESERVED')
                    stop.rename(archive)
                    value=dict(UTC=now(),reason=REASON,user_stop=False,authorization=record(authorization))
                    atomic(stop,value)
                elif technical_hold(value,guard):
                    if not boundary(guard,lease=lease,workers=active):time.sleep(15.);continue
                    preserved=OPS/'R026F1_CURRENT_CASE_TECHNICAL_STOP_PRESERVED.json'
                    if preserved.exists():raise FileExistsError('R026F1_TECHNICAL_STOP_ALREADY_PRESERVED')
                    stop.rename(preserved)
                    defer(OPS,guard['protected_case_root'],read(Path(guard['protected_case_root'])/'RESULT.json'))
                    value=dict(UTC=now(),reason=REASON,user_stop=False,technical_error_isolated=True)
                    atomic(stop,value)
                else:
                    atomic(OPS/'R026F1_HANDOVER_USER_STOP.json',dict(UTC=now(),stop=value));return
            atomic(OPS/'R026F1_HANDOVER_HEARTBEAT.json',dict(UTC=now(),**process_identity(),
                protected_case=guard['protected_case_root'],protected_coordinator=lease,
                coordinator_alive=alive(lease),workers=active,
                policy='WAIT_ENTIRE_ACTUAL_AND_INDEPENDENT_FRESH_AND_NATURAL_WORKER_COORDINATOR_EXIT'))
            if not value and alive(lease):
                import psutil
                if 'v44_recovery_r026f1.operations' in psutil.Process(lease['pid']).cmdline():break
            if boundary(guard,lease=lease,workers=active):
                result=read(Path(guard['protected_case_root'])/'RESULT.json')
                if not result.get('PASS') and result.get('status')!='USER_STOPPED':
                    from .failure_continue import defer
                    defer(OPS,guard['protected_case_root'],result)
                break
            time.sleep(15.)
        validate()
        stop=OPS/'STOP_AUTONOMY.json'
        if stop.exists():
            if read(stop).get('reason')!=REASON:return
            require_boundary()
            archive=OPS/'R026F1_HANDOVER_STOP_PRESERVED.json'
            if archive.exists():raise FileExistsError('R026F1_HANDOVER_STOP_ALREADY_PRESERVED')
            stop.rename(archive)
        atomic(OPS/'R026F1_HANDOVER_APPLIED.json',dict(UTC=now(),permit=record(PERMIT),
            protected_worker_interrupted=False,protected_case=guard['protected_case_root'],
            Native_optimization_repeated=False,improved_arms=['B0','B1','B3']))
    watchdog()

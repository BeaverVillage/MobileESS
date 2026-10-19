"""Wait for the entire May02 B3 case; then enable faster May03+ A stages."""
import time
from pathlib import Path
from v44.common import read,atomic,record,verify,now
from v44.locks import exclusive_lock,alive,process_identity

REASON='R025B_USER_REQUESTED_PHASE1000_CURRENT_A2_CONTINUATION'


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
    guard=read(OPS/'R025B_HANDOVER_GUARD.json')
    lease=read(CAMPAIGN/'COORDINATOR_LEASE.json')
    if alive(lease):
        import psutil
        if 'v44_recovery_r025b.operations' in psutil.Process(lease['pid']).cmdline():
            return guard
    if not boundary(guard,lease=lease,workers=workers()):
        raise PermissionError('R025B_PROTECTED_B3_ENTIRE_CASE_NOT_FINISHED')
    return guard


def activate(lease):
    from .operations import OPS,PERMIT
    guard=read(OPS/'R025B_HANDOVER_GUARD.json')
    path=OPS/'CURRENT_HANDOFF.json';value=read(path)
    if value.get('active_revision')=='v44_recovery_r025b':return
    atomic(OPS/'R025B_PRE_ACTIVATION_HANDOFF_PRESERVED.json',value)
    value.update(UTC=now(),active_revision='v44_recovery_r025b',permit=record(PERMIT),
        adapter_source_root=str(Path(__file__).resolve().parents[1]),
        entry='python -m v44_recovery_r025b.operations --handover',
        windows_task='MobileESS_V44_Campaign004_Recovery_R025B',
        pending_revision=None,pending_permit=None,pending_validation=None,
        next_performance_revision='v44_recovery_r025b',performance_revision_state='R025B_ACTIVE_NATIVE60_PHASE1000_VERIFIED_UB_CURRENT_NATIVE_CONTINUATION',
        active_operational_entry='v44_recovery_r025b.operations',active_operational_permit=None,
        algorithm_revision='v44_recovery_r025b',development_revision=None,effective_from_day='2025-05-02',
        pending_deployment_receipt_file=str(OPS/'R025B_HANDOVER_APPLIED.json'),unconditional_future_B1_B3=True,pilot_PASS_required=False,
        protected_case=guard['protected_case_root'],protected_case_finished_receipt=record(Path(guard['protected_case_root'])/'RESULT.json'),
        r025b_coordinator=lease,r025b_improved_arms=['B0','B1','B3'],dispatch_hold_reason=None,
        active_regressions=read(OPS/'R025B_CHANGE_AND_VALIDATION.json')['regressions'],
        collector=str(OPS/'collect_watchdog_r025b.py'),active_source_auditor=str(OPS/'audit_active_revision_r025b.py'),
        latest_user_instruction='All B1/B3 A1/A2 Native3600, Phase I cutoff1000, original integer search then verified UB freeze; current A2 inherits Native414.457 without reset.',
        next='May02 B3 attempt009 A2 resumes saved active rows, support, prior primal and measured Native414.457; Phase I cumulative1000 and total3600. All future B1/B3 A stages unconditional; UB-only cache gate compatible.')
    atomic(path,value)


def run():
    from .operations import CAMPAIGN,OPS,PERMIT,validate,workers,watchdog
    permit=validate();guard=read(OPS/'R025B_HANDOVER_GUARD.json')
    verify([permit['autonomous_recovery_overlay']['handover_guard']])
    with exclusive_lock(OPS/'R025B_HANDOVER.lock'):
        while True:
            stop=OPS/'STOP_AUTONOMY.json';value=read(stop) if stop.exists() else {}
            lease=read(CAMPAIGN/'COORDINATOR_LEASE.json');active=workers()
            if value and value.get('reason')!=REASON:
                from .failure_continue import technical_hold,defer
                if technical_hold(value,guard):
                    if not boundary(guard,lease=lease,workers=active):time.sleep(15.);continue
                    preserved=OPS/'R025B_CURRENT_CASE_TECHNICAL_STOP_PRESERVED.json'
                    if preserved.exists():raise FileExistsError('R025B_TECHNICAL_STOP_ALREADY_PRESERVED')
                    stop.rename(preserved)
                    defer(OPS,guard['protected_case_root'],read(Path(guard['protected_case_root'])/'RESULT.json'))
                    value=dict(UTC=now(),reason=REASON,user_stop=False,technical_error_isolated=True)
                    atomic(stop,value)
                else:
                    atomic(OPS/'R025B_HANDOVER_USER_STOP.json',dict(UTC=now(),stop=value));return
            atomic(OPS/'R025B_HANDOVER_HEARTBEAT.json',dict(UTC=now(),**process_identity(),
                protected_case=guard['protected_case_root'],protected_coordinator=lease,
                coordinator_alive=alive(lease),workers=active,
                policy='WAIT_ENTIRE_ACTUAL_AND_INDEPENDENT_FRESH_AND_NATURAL_WORKER_COORDINATOR_EXIT'))
            if not value and alive(lease):
                import psutil
                if 'v44_recovery_r025b.operations' in psutil.Process(lease['pid']).cmdline():break
            if boundary(guard,lease=lease,workers=active):
                result=read(Path(guard['protected_case_root'])/'RESULT.json')
                if not result.get('PASS') and result.get('classification')!='USER_REQUESTED_ALGORITHM_REVISION_STOP':
                    from .failure_continue import defer
                    from .operations import phase1000_priority
                    if not phase1000_priority(Path(guard['protected_case_root'])):defer(OPS,guard['protected_case_root'],result)
                break
            time.sleep(15.)
        validate()
        stop=OPS/'STOP_AUTONOMY.json'
        if stop.exists():
            if read(stop).get('reason')!=REASON:return
            require_boundary()
            archive=OPS/'R025B_HANDOVER_STOP_PRESERVED.json'
            if archive.exists():raise FileExistsError('R025B_HANDOVER_STOP_ALREADY_PRESERVED')
            stop.rename(archive)
        atomic(OPS/'R025B_HANDOVER_APPLIED.json',dict(UTC=now(),permit=record(PERMIT),
            protected_worker_interrupted=False,user_authorized=True,protected_case=guard['protected_case_root'],
            prior_Native_clock_reset=False,improved_arms=['B1','B3']))
    watchdog()

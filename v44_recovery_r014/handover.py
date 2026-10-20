"""Apply the new immutable revision only after the protected worker finishes."""
from pathlib import Path
import time
from v44.common import read,atomic,record,now
from v44.locks import exclusive_lock,alive,process_identity


def run():
    from .operations import CAMPAIGN,OPS,PERMIT,validate,workers,watchdog
    validate()
    with exclusive_lock(OPS/'R014_HANDOVER.lock'):
        while True:
            stop=OPS/'STOP_AUTONOMY.json'
            value=read(stop) if stop.exists() else {}
            if value and value.get('reason')!='R014_PERFORMANCE_VALIDATION_SAFE_HANDOVER_AFTER_HEALTHY_WORKER':
                atomic(OPS/'R014_HANDOVER_USER_STOP.json',dict(UTC=now(),stop=value))
                return
            lease=read(CAMPAIGN/'COORDINATOR_LEASE.json')
            existing=alive(lease);active=workers()
            atomic(OPS/'R014_HANDOVER_HEARTBEAT.json',dict(UTC=now(),**process_identity(),
                protected_coordinator=lease,coordinator_alive=existing,workers=active,
                policy='WAIT_NATURAL_WORKER_AND_COORDINATOR_EXIT_NO_HOTPATCH_NO_TERMINATION'))
            if not existing and not active:break
            # Already completed handover after a login/restart: maintain only
            # the ordinary single supervisor lock, without waiting forever.
            if not value and existing:
                import psutil
                command=' '.join(psutil.Process(lease['pid']).cmdline())
                if 'v44_recovery_r014.operations' in command:break
            time.sleep(15.)
        validate()
        stop=OPS/'STOP_AUTONOMY.json'
        if stop.exists():
            value=read(stop)
            if value.get('reason')!='R014_PERFORMANCE_VALIDATION_SAFE_HANDOVER_AFTER_HEALTHY_WORKER':return
            archive=OPS/'R014_HANDOVER_STOP_PRESERVED.json'
            if archive.exists():raise FileExistsError('HANDOVER_STOP_ARCHIVE_ALREADY_EXISTS')
            stop.rename(archive)
        atomic(OPS/'R014_HANDOVER_APPLIED.json',dict(UTC=now(),permit=record(PERMIT),
            protected_worker_interrupted=False,previous_coordinator_exit_confirmed=not existing,
            next_priority='NEXT_READY_CASE_PER_SAME_DATE_B0_B1_B3_QUEUE_NO_HEALTHY_RESTART',
            Native_optimization_repeated=False))
    watchdog()

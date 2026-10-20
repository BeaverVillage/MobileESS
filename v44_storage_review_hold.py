"""Finish the requested case, clean exact duplicates, and wait without dispatch."""
from pathlib import Path
import sys,time
import v44_recovery_r029
from v44_recovery_r036 import operations as op
from v44.common import read,record,verify,atomic,now
from v44.locks import exclusive_lock,process_identity

REASON='USER_WAIT_AFTER_MAY02_B3_STORAGE_REVIEW'
AUTH=op.OPS/'USER_STORAGE_REVIEW_AUTHORIZATION.json'

def held():
    path=op.OPS/'STOP_AUTONOMY.json'
    return path.exists() and read(path).get('reason')==REASON and read(path).get('user_dispatch_pause') is True

def step():
    if not held():return 'OTHER_CONTROL_PRESERVED'
    if not op.ready() or not (op.CLEANUP_CASE/'RESULT.json').exists():return 'WAITING_FOR_MAY02_B3_AND_FRESH'
    result=read(op.CLEANUP_CASE/'RESULT.json')
    if type(result.get('PASS')) is not bool:return 'WAITING_FOR_TERMINAL_CASE_RESULT'
    # This function only removes exact redundant physical copies; no scheduler.
    done=op.previous.cleanup_after_case()
    if not held():return 'OTHER_CONTROL_PRESERVED'
    atomic(op.OPS/'USER_STORAGE_REVIEW_CLEANUP_COMPLETE.json',dict(UTC=now(),PASS=True,
        cleanup=record(op.OPS/'R035_EXISTING_RAW_CLEANUP.json'),case_result=record(op.CLEANUP_CASE/'RESULT.json'),
        next_date_started=False,waiting_for_explicit_user_resume=True))
    return 'CLEANED_WAITING_FOR_EXPLICIT_USER_RESUME'

def run():
    value=read(AUTH);verify(value['sources']+[value['revision_authorization']]);op.validate()
    with exclusive_lock(op.OPS/'USER_STORAGE_REVIEW.lock'):
        op.storage_maintenance.start(op)
        while held():
            def heartbeat(phase):
                row=dict(UTC=now(),**process_identity(),phase=phase,active_workers=[p['pid'] for p in op.base.workers()],
                    active_worker_untouched=True,mode='CLEANUP_ONLY_NO_SCHEDULER',next_date_started=False,
                    user_dispatch_pause=True,resume_requires_explicit_user_instruction=True)
                atomic(op.OPS/'USER_STORAGE_REVIEW_HEARTBEAT.json',row)
                # Existing source auditor requires a live pending helper identity.
                atomic(op.OPS/'R036_HANDOVER_HEARTBEAT.json',row)
            heartbeat('WAITING_OR_CLEANING_WITH_USER_DISPATCH_HOLD')
            phase=step();heartbeat(phase)
            time.sleep(15)

if __name__=='__main__':run()

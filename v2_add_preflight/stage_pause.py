"""Verify the authorized prior campaign hold from actual frozen receipts."""
import psutil
from .stage_common import read,record

def verify(receipt):
    if record(receipt['path'])!=receipt:raise PermissionError('V44_PAUSE_RECEIPT_DRIFT')
    pause=read(receipt['path'])
    if not (pause.get('PASS') is True and pause.get('all_OS_locks_verified_released') is True
            and pause.get('no_next_stage_dispatched') is True and pause.get('scheduled_task_disabled') is True
            and pause.get('worker_killed') is False and pause.get('Supervisor_terminated') is False):
        raise PermissionError('V44_VERIFIED_STAGE_BOUNDARY_HOLD_REQUIRED')
    for key in ('stage_frozen','coordinator_normal_finally_exit','persistent_hold'):
        item=pause[key]
        if record(item['path'])!=item:raise PermissionError('V44_PAUSE_ARTIFACT_DRIFT:'+key)
    stage=read(pause['stage_frozen']['path'])
    if stage.get('Native_inflight') is not None or stage.get('Native_budget_reset') is not False:
        raise PermissionError('V44_RECONCILED_FROZEN_CLOCK_REQUIRED')
    if record(stage['ledger']['path'])!=stage['ledger']:raise PermissionError('V44_FROZEN_LEDGER_DRIFT')
    for key in ('worker','supervisor'):
        identity=stage[key]
        try:
            process=psutil.Process(identity['pid'])
            if abs(process.create_time()-identity['process_created'])<.001 and process.is_running():
                raise PermissionError('V44_PRIOR_OWNER_STILL_LIVE:'+key)
        except psutil.NoSuchProcess:pass
    return pause

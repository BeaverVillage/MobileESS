"""Official orphan reconciliation with immutable evidence and no fake Runtime."""
import argparse
import json
import os
from pathlib import Path
import platform
import shutil
import sys
from time import time

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from v42_integration.m_engine import file_record
from v42_integration.table_v_interruption import restart_bounds,archived_runtime_summary
from v42_integration.table_v_native_journal import atomic_json


def recover(output,events_path):
    import psutil
    from v42_integration.table_v_control import stop_request
    from v42_integration.release_production_budget import reconcile_interrupted_ledger
    root=Path(output).resolve();ledger=root/'PLANNING_NATIVE_LEDGER.json'
    document=json.loads(ledger.read_text(encoding='utf8'));call=document.get('inflight')
    events=json.loads(Path(events_path).read_text(encoding='utf-8-sig'))
    if not call:raise ValueError('ACTUAL_UNRECONCILED_NATIVE_CALL_REQUIRED')
    pid=call['pid'];boot=psutil.boot_time()
    log=root/'B1/A1/DW/PHASE_I/S1/SOURCE18R_FAST/NATIVE_GUROBI.log'
    interval=restart_bounds(call,events,boot_epoch=boot,pid_alive=psutil.pid_exists(pid),
        log_text=log.read_text(encoding='utf8'))
    # These are exactly named single files, never a recursive cleanup.
    locks=[Path('D:/V42_UNIFIED_HEAVY_WORKER.lock').resolve(),Path('D:/V42_2_MAY01_CAMPAIGN.lock').resolve()]
    expected={}
    for path in locks:
        owner=json.loads(path.read_text(encoding='utf8'))
        if owner.get('pid')!=pid or not owner.get('nonce'):raise ValueError('ORPHAN_LOCK_OWNER_DRIFT')
        expected[str(path)]=file_record(path)
    if expected[str(locks[0])]!=call['worker_lock_record']:
        raise ValueError('EXACT_INFLIGHT_HEAVY_LOCK_BYTES_REQUIRED')
    folder=root/'HOST_RESTART_RECOVERY';folder.mkdir(exist_ok=False)
    original_rows=[file_record(p) for p in sorted(root.rglob('*')) if p.is_file() and folder not in p.parents]
    atomic_json(folder/'ORIGINAL_ATTEMPT_FILE_MANIFEST.json',dict(files=original_rows))
    original=folder/'ORIGINAL_UNRECONCILED_LEDGER.json';shutil.copyfile(ledger,original)
    native_log=folder/'ORIGINAL_NATIVE_GUROBI.log';shutil.copyfile(log,native_log)
    event_file=folder/'WINDOWS_RESTART_EVENTS.json';atomic_json(event_file,events)
    for path in locks:shutil.copyfile(path,folder/path.name)
    stop=stop_request(root,reason='OS_UPDATE_RESTART_ORPHAN_RECOVERY_NO_LIVE_NATIVE_PID')
    receipt=dict(schema='TABLE_V_PROVEN_HOST_RESTART_RECEIPT_V1',host=platform.node(),
        observed_epoch_seconds=time(),observed_new_boot_epoch_seconds=boot,original_pid=pid,
        original_pid_alive=False,original_ledger=file_record(original),native_log=file_record(native_log),
        events=file_record(event_file),native_runtime_interval_seconds=interval,
        lock_originals=expected,stop_request=stop,FULL_PASS=False,Actual_Fresh_PASS=False,
        exact_Native_Runtime_recovered=False,Native_Runtime_fabricated=False)
    receipt_path=folder/'RESTART_RECEIPT.json';atomic_json(receipt_path,receipt)
    # Official accounting appends NULL Runtime and a conservative charge. The
    # pristine pre-recovery ledger, log, locks and file inventory stay intact.
    updated=reconcile_interrupted_ledger(ledger,evidence=file_record(receipt_path),
        charge_seconds=interval['upper'],host_restart_receipt=file_record(receipt_path))
    summary=archived_runtime_summary(updated)
    for path in locks:
        if psutil.pid_exists(pid) or file_record(path)!=expected[str(path)]:
            raise ValueError('LOCK_CHANGED_OR_OWNER_BECAME_LIVE_DO_NOT_REMOVE')
        path.unlink()
    outcome=dict(status='HOST_RESTART_INTERRUPTED_NOT_CERTIFIED',failed_stage='A1',
        native_accounting=summary,recovery_receipt=file_record(receipt_path),
        physical_PASS_claimed=False,FULL_PASS=False,Actual_Fresh_PASS=False,
        completed_planning_stages=[],identical_inplace_resume_forbidden=True)
    target=root/'B1/ARM_OUTCOME.json'
    if target.exists():raise FileExistsError('EXISTING_OUTCOME_MUST_NOT_OVERWRITE')
    atomic_json(target,outcome)
    atomic_json(folder/'RECOVERY_COMPLETE.json',dict(PASS=True,ledger=file_record(ledger),
        native_accounting=summary,orphan_locks_preserved_and_released=True,attempt_sealed=True))
    return summary


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    p.add_argument('--windows-events',type=Path,required=True);args=p.parse_args()
    print(json.dumps(recover(args.output,args.windows_events),ensure_ascii=False))

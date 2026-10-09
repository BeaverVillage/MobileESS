"""Start admitted Windows tasks at the terminal date boundary; no Worker stop."""
from pathlib import Path
import shutil,json
import psutil
from v42_pr134_b1.common import ROOT,read,atomic,now,same_process,record
from v42_may_recovery_v5.policy import verify_policy
from v42_may_recovery_v5.windows import register_campaign_tasks,run_task,reuse_registered_task
from .preflight import RUN,DOC


def main():
    manifest=verify_policy(RUN)
    if same_process(read(RUN/'COORDINATOR_HOST.json').get('process',{})):
        raise PermissionError('V2_COORDINATOR_MUST_BE_TERMINAL')
    if same_process(read(RUN/'COORDINATOR_V5_HOST.json').get('process',{})) if (RUN/'COORDINATOR_V5_HOST.json').exists() else False:
        raise PermissionError('V5_COORDINATOR_ALREADY_RUNNING')
    registration=register_campaign_tasks(RUN,manifest)
    for role,name in manifest['tasks'].items():reuse_registered_task(RUN,role,name,python=manifest['Python'])
    # Only replace this run's read-only monitor. Old Solver/result/ledger and
    # existing scheduler definitions stay intact. Keep its process receipts.
    old=read(RUN/'MONITOR_PROCESS.json')
    monitor=psutil.Process(old['PID']) if same_process(old) else None
    if monitor is not None:
        command=old['command']
        if not ('v42_may_campaign_native90.host' in command and 'monitor' in command and str(RUN) in command):
            raise PermissionError('ONLY_EXACT_V2_READ_ONLY_MONITOR_REPLACEMENT_ALLOWED')
        atomic(RUN/'MONITOR_REPLACEMENT_V5.json',dict(old=old,old_monitor_only=True,
            Solver_stops=0,UTC=now(),new_task=manifest['tasks']['monitor']))
        for name in ('MONITOR_PROCESS.json','MONITOR_SERVER.json'):
            target=RUN/(Path(name).stem+'_V2_BEFORE_CONTINUATION.json')
            if target.exists():raise PermissionError('MONITOR_ORIGINAL_RECEIPT_ALREADY_PRESERVED')
            shutil.copyfile(RUN/name,target)
        monitor.terminate();monitor.wait(timeout=15)
    started={role:run_task(manifest['tasks'][role]) for role in ('monitor','coordinator','watchdog')}
    atomic(DOC/'OS_ACTIVATION_DISPATCH.json',dict(PASS=True,UTC=now(),tasks=registration,started=started,
        actual_worker_observation='NOT_YET_OBSERVED',Native_calls_by_dispatch_tool=0,Solver_stops=0,
        original_HOLD_retained=True,existing_scheduler_definitions_changed=False))
    print(json.dumps(dict(PASS=True,Windows_tasks_dispatched=list(started),Native_calls_by_dispatch_tool=0)))


if __name__=='__main__':main()

"""Launch new ordinary-user tasks; retain the held old task definitions."""
import json,shutil,psutil
from v42_pr134_b1.common import read,atomic,now,same_process,record
from v42_may_build_v6.policy import verify_policy
from v42_may_build_v6.windows import register_campaign_tasks,reuse_registered_task,run_task
from .preflight import RUN,DOC


def main():
    manifest=verify_policy(RUN)
    if same_process(read(RUN/'COORDINATOR_V5_HOST.json')['process']):raise PermissionError('V5_COORDINATOR_STILL_LIVE')
    registration=register_campaign_tasks(RUN,manifest)
    for role,name in manifest['tasks'].items():reuse_registered_task(RUN,role,name,python=manifest['Python'])
    old=read(RUN/'MONITOR_PROCESS.json')
    if same_process(old):
        if not ('v42_may_recovery_v5.host' in old['command'] and 'monitor' in old['command'] and str(RUN) in old['command']):
            raise PermissionError('ONLY_OWN_V5_READ_ONLY_MONITOR_REPLACEMENT')
        for name in ('MONITOR_PROCESS.json','MONITOR_SERVER.json'):
            path=RUN/(name[:-5]+'_V5_BEFORE_BUILD_V6.json')
            if path.exists():raise PermissionError('MONITOR_RECEIPT_ALREADY_PRESERVED')
            shutil.copyfile(RUN/name,path)
        p=psutil.Process(old['PID']);p.terminate();p.wait(15)
        atomic(DOC/'MONITOR_REPLACEMENT.json',dict(old_process=old,Solver_stops=0,UTC=now()))
    started={role:run_task(manifest['tasks'][role]) for role in ('monitor','coordinator','watchdog')}
    atomic(DOC/'OS_ACTIVATION_DISPATCH.json',dict(PASS=True,UTC=now(),registration=registration,
        started=started,Native_calls_by_dispatch=0,existing_scheduler_definitions_changed=False,
        actual_new_worker='NOT_YET_OBSERVED',LOGOFF_PERSISTENCE='NOT_PROVEN'))
    print(json.dumps(dict(PASS=True,dispatched=list(started))),flush=True)


if __name__=='__main__':main()

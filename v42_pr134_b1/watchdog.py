"""OS hourly supervisor: observe healthy solves, recover dead infrastructure."""
import sys
from .common import *
from .coordinator import counts

def run(root):
    root=Path(root);freeze=read(root/'B1_PRODUCTION_FREEZE_MANIFEST.json');verify_freeze(freeze)
    cp=read(root/'CHECKPOINT.json');hb=read(root/'B1_HEARTBEAT.json') if (root/'B1_HEARTBEAT.json').exists() else {}
    active=read(root/'ACTIVE.json') if (root/'ACTIVE.json').exists() else {}
    coor=same_process(hb.get('process',{}));worker=same_process(active.get('worker',{}));totals=counts(cp);actions=[]
    age=max(0,datetime.now(timezone.utc).timestamp()-datetime.fromisoformat(hb['timestamp_UTC']).timestamp()) if hb.get('timestamp_UTC') else None
    if cp['state']=='COMPLETE':
        from .finalize import publish
        publish(root,freeze,cp)
    elif not coor:
        path=root/'COORDINATOR_RESTART_COUNT.json';restarts=read(path).get('count',0) if path.exists() else 0
        if restarts<2:
            atomic(path,dict(count=restarts+1,UTC=now(),reason='IDENTITY_VERIFIED_COORDINATOR_DEAD',live_worker_adoption_required=worker))
            subprocess.run(['schtasks.exe','/Run','/TN',freeze['task_name']],check=True,capture_output=True)
            actions.append('RESTART_DEAD_COORDINATOR_THROUGH_SCHEDULER_WITH_LIVE_WORKER_ADOPTION')
        else:actions.append('BOUNDED_COORDINATOR_RETRIES_EXHAUSTED_EXACT_INFRA_REPAIR_REQUIRED')
    # A live stale heartbeat is recorded and investigated; neither stale solver
    # telemetry nor high memory authorizes killing or changing a healthy solve.
    monitor=read(root/'MONITOR_PROCESS.json') if (root/'MONITOR_PROCESS.json').exists() else {}
    if not same_process(monitor):
        subprocess.run(['schtasks.exe','/Run','/TN',freeze['monitor_task']],check=True,capture_output=True);actions.append('RESTART_DEAD_READ_ONLY_MONITOR')
    sha_failures=[]
    for key,entry in cp['stages'].items():
        if entry.get('status')!='PASS':continue
        if sha(entry['receipt'])!=entry['sha256'] or not valid_receipt(read(entry['receipt']),identity(freeze,*key.split('/')),root):sha_failures.append(key)
    progress={}
    if active.get('request'):
        request=read(active['request']);p=Path(request['progress'])
        if p.is_file():progress=read(p)
    errors=read(root/'ERROR_REPAIR_LEDGER.json') if (root/'ERROR_REPAIR_LEDGER.json').exists() else []
    value=dict(UTC=now(),run_id=freeze['run_id'],counts=totals,current_date=active.get('day'),stage=active.get('stage'),coordinator_alive=coor,worker_alive=worker,
        heartbeat_age=age,elapsed_native_seconds=progress.get('cumulative_native_runtime'),solver_phase=progress.get('phase'),
        healthy_solve_settings_changed=False,memory_guard=False,completed_identity_failures=sha_failures,
        actions=actions,last_error=errors[-1] if errors else read(root/'COORDINATOR_ERROR.json') if (root/'COORDINATOR_ERROR.json').exists() else None,
        repaired_errors=[e for e in errors if e.get('resolution')=='RESOLVED'],new_failure_receipts=len(errors),
        reuse_count=sum(r.get('reused',False) for r in cp['dates'].values()),rerun_count=sum(r.get('attempts',0)>0 for r in cp['dates'].values()))
    atomic(root/'MAY_B1_HOURLY_STATUS.json',value)
    (root/'MAY_B1_HOURLY_STATUS.md').write_text(f'''# May B1 독립 매시간 점검

{value['UTC']} · {value['run_id']}

PASS {totals['PASS']}/31 · TIMEOUT {totals['TIMEOUT']}/31 · FAIL {totals['FAIL']}/31 · pending {totals['pending']}

현재 {active.get('day')} / {active.get('stage')} · coordinator alive {coor} · worker alive {worker} · heartbeat age {age}

조치: {actions}

메모리·CPU 정보는 관찰용이며 중단·감속·solver 설정 변경에 사용하지 않는다.
''',encoding='utf8')
    return value

if __name__=='__main__':run(sys.argv[1])

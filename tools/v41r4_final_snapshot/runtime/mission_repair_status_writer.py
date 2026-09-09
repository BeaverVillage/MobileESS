from mission_health import *
from fast_prepare import record
state=read(RUN/'campaign_progress.json');p=psutil.Process(state['supervisor_pid'])
assert 'mission_supervisor.py' in ' '.join(p.cmdline())
stack=LOG/f'supervisor_{p.pid}_stale_stack.txt'
assert stack.exists() and 'PermissionError' in stack.read_text(encoding='utf-8')
p.suspend()
try:
    current=read(RUN/'campaign_progress.json');assert current==state
    active=[]
    for r in state['active']:
        receipt=RUN/'audit'/r['day']/f"PHASE_{r['phase']}.json"
        if receipt.exists() and read(receipt)['status']=='PASS':continue
        c=psutil.Process(r['worker_pid']);assert r['day'] in c.cmdline() and r['phase'] in c.cmdline();active.append(r)
    assert len(active)==4
    evidence=OUT/f'STATUS_WRITER_FAILURE_{p.pid}.json'
    write(evidence,dict(state=state,stack=record(stack),pending_snapshot=record(RUN/'campaign_progress.json.tmp')))
    write(OUT/'SUPERVISOR_TAKEOVER_BEFORE_STATUS_REPAIR.json',read(OUT/'SUPERVISOR_TAKEOVER.json'))
    write(OUT/'SUPERVISOR_TAKEOVER.json',dict(**{k:v for k,v in state.items() if k!='active'},active=active))
    write(OUT/'STATUS_WRITER_REPAIR.json',dict(status='PASS',at=time.time(),root_cause='Unhandled PermissionError during atomic status replacement; ThreadPoolExecutor.__exit__ joined live workers instead of refreshing status',
        evidence=record(evidence),fix='Unique pending paths; retry transient PermissionError; retain controller loop after OSError',
        source=[record(ROOT/'mission_health.py'),record(ROOT/'mission_supervisor.py')],
        preserved_worker_pids=[r['worker_pid'] for r in active],science_worker_restarts=0,scientific_method_changes=0))
    p.terminate();p.wait(15)
    assert all(psutil.pid_exists(r['worker_pid']) for r in active)
except BaseException:
    if p.is_running():p.resume()
    raise
print('STATUS_CONTROLLER_REPAIRED_WORKERS_PRESERVED')

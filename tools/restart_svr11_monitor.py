"""Restart only the independently sealed read-only HTTP monitor."""
from pathlib import Path
import sys,psutil,time,json,urllib.request
SOURCE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(SOURCE))
from v42_pr134_b1.common import read,atomic,now
from v42_svr11.authority import verify
from v42_svr11.processes import live,workers
from svr11_monitor_ui import verify_ui,safeguard

root=Path(sys.argv[1]).resolve();m=verify(root/'CAMPAIGN_MANIFEST.json');verify_ui(root)
supervisor=read(root/'SUPERVISOR_PROCESS.json');assert live(supervisor)
before=workers(root,m['execution_SHA']);old=read(root/'MONITOR_PROCESS.json')
assert live(old) and old['source_SHA']==m['execution_SHA']
assert old['command'][4:]==[str(SOURCE/'tools/svr11_monitor_ui.py'),'serve',str(root)]
process=psutil.Process(old['PID']);assert process.create_time()==old['create_time']
process.terminate();process.wait(10)
safeguard(root,monitor_only=True)
for attempt in range(30):
    try:
        with urllib.request.urlopen('http://127.0.0.1:8796/api/state',timeout=2) as response:state=json.load(response)
        assert state['source_SHA']==m['execution_SHA'] and Path(state['root']).resolve()==root
        break
    except (OSError,AssertionError):
        if attempt==29:raise
        time.sleep(.2)
assert live(supervisor);monitor=read(root/'MONITOR_PROCESS.json');assert live(monitor)
receipt=dict(PASS=True,UTC=now(),source_SHA=m['execution_SHA'],
    old_monitor=old,new_monitor=monitor,supervisor_unchanged=supervisor,
    prior_workers=before,current_workers=workers(root,m['execution_SHA']),
    scientific_workers_or_supervisor_terminated=0,monitor_HTTP=200,
    displayed_errors=state['errors'])
atomic(root/'MONITOR_RESTART_RECEIPT.json',receipt)
print(json.dumps(dict(PASS=True,monitor_PID=monitor['PID'],errors=state['errors'],scientific_processes_terminated=0)))

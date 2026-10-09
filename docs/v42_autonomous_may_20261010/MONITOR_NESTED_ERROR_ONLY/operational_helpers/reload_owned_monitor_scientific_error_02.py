from pathlib import Path
import json,hashlib,psutil,subprocess,time,urllib.request
from datetime import datetime,timezone
from v42_autonomous.recovery import assert_lease
R=Path(r"D:\v42_may_restart_20261010_02");A=R/"autonomous";CODE=Path(r"D:\MobileESS_v42_autonomous")
def read(p):return json.loads(Path(p).read_bytes())
def record(p):
 b=p.read_bytes();return dict(path=str(p),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def identity(pid):
 p=psutil.Process(pid);return dict(PID=p.pid,created=p.create_time(),command=p.cmdline(),cwd=p.cwd())
def seal(name,doc):
 p=A/name;assert not p.exists();p.write_text(json.dumps(doc,indent=2)+"\n",encoding="utf-8");return record(p)
lease=read(R/"REPAIR_LEASE.json");assert_lease(R,lease['token'])
server=read(R/"AUTONOMOUS_MONITOR_SERVER.json");expected=server['process'];actual=identity(expected['PID'])
assert actual['command']==expected['command'] and abs(actual['created']-expected['created'])<.001
assert Path(actual['cwd']).resolve()==CODE and actual['command'][0].lower().endswith('pythonw.exe')
assert actual['command'][1:]==['-B','-X','utf8','-m','v42_autonomous_monitor.host',str(R),'--port','8794']
connections=psutil.Process(actual['PID']).net_connections(kind='inet');assert any(v.status=='LISTEN' and v.laddr.port==8794 and v.laddr.ip=='127.0.0.1' for v in connections)
cp=read(R/"SUPERVISOR_STATE.json");workers={};already_exited={}
for k,v in cp['workers'].items():
 try:workers[k]=identity(v['PID'])
 except psutil.NoSuchProcess:already_exited[k]=dict(checkpoint_worker=v,OS_process_absent=True,not_terminated_by_this_script=True)
results={k:record(Path(v['result'])) for k,v in cp['dates'].items() if k in ['B2/2025-05-01','B2/2025-05-02','B2/2025-05-03']}
with urllib.request.urlopen('http://127.0.0.1:8794/api/status',timeout=5) as f:before=json.load(f)
b=seal('MONITOR_SCIENTIFIC_ERROR_RELOAD_BEFORE.json',dict(UTC=datetime.now(timezone.utc).isoformat(),actual_monitor=actual,workers=workers,results=results,first3=[dict(day=v['day'],status=v['B2']['status'],error=v['B2']['error']) for v in before['rows'][:3]],monitor_code=record(CODE/'v42_autonomous_monitor/monitor.py'),lease_token=lease['token']))
# Only this exactly owned read-only host is replaced. Scientific workers are untouched.
old=psutil.Process(actual['PID']);old.terminate();old.wait(timeout=10)
stdout=(A/'monitor_scientific_error_stdout.log').open('ab');stderr=(A/'monitor_scientific_error_stderr.log').open('ab')
new=subprocess.Popen(actual['command'],cwd=CODE,stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr,creationflags=subprocess.CREATE_NO_WINDOW)
stdout.close();stderr.close()
for i in range(60):
 try:
  current=read(R/'AUTONOMOUS_MONITOR_SERVER.json');n=identity(current['process']['PID'])
  assert n['PID']==new.pid and n['command']==actual['command'] and Path(n['cwd']).resolve()==CODE
  with urllib.request.urlopen('http://127.0.0.1:8794/api/status',timeout=2) as f:after=json.load(f)
  expected_error='PermissionError: RMP_PRESOLVE_ORIGINAL_BUDGET_OR_SCOPE_CLOSURE_DRIFT'
  assert all(v['B2']['error']==expected_error for v in after['rows'][:3])
  break
 except (OSError,AssertionError):time.sleep(.5)
else:raise RuntimeError('OWNED_MONITOR_RELOAD_HTTP_VERIFICATION_REQUIRED')
worker_obs={}
for k,v in workers.items():
 try:
  current_worker=identity(v['PID']);assert current_worker==v;worker_obs[k]=dict(same_exact_identity=True,actual=current_worker)
 except psutil.NoSuchProcess:
  worker_obs[k]=dict(natural_exit_observed=True,process_was_not_terminated_by_this_script=True)
assert all(record(Path(v['path']))==v for v in results.values())
r=seal('MONITOR_SCIENTIFIC_ERROR_RELOAD_VERIFICATION.json',dict(PASS=True,UTC=datetime.now(timezone.utc).isoformat(),before=b,actual_monitor=n,first3=[dict(day=v['day'],status=v['B2']['status'],error=v['B2']['error']) for v in after['rows'][:3]],worker_observations=worker_obs,pre_reload_already_exited=already_exited,original_first3_results_unchanged=True,scientific_worker_terminate_calls=0,supervisor_terminate_calls=0,Native_optimize_calls=0,model_constructions=0,monitor_code=record(CODE/'v42_autonomous_monitor/monitor.py'),URL='http://127.0.0.1:8794/',no_GUI_render_verification_claimed=True))
print(json.dumps(dict(PASS=True,receipt=r,new_monitor_PID=new.pid,workers_untouched=True)),flush=True)

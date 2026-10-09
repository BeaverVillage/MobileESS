from pathlib import Path
from datetime import datetime,timezone
import json,hashlib,psutil,subprocess,time
from v42_autonomous.recovery import assert_lease
R=Path(r"D:\v42_may_restart_20261010_02");A=R/'autonomous';CODE=Path(r"D:\MobileESS_v42_autonomous")
def read(p):return json.loads(p.read_bytes())
def ident(pid):
 p=psutil.Process(pid);return dict(PID=p.pid,created=p.create_time(),command=p.cmdline(),cwd=p.cwd())
def rec(p):
 b=p.read_bytes();return dict(path=str(p),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def seal(name,d):
 p=A/name;assert not p.exists();p.write_text(json.dumps(d,indent=2)+"\n",encoding='utf-8');return rec(p)
lease=read(R/'REPAIR_LEASE.json');assert lease['token']=='ec09026701ab4e6db5b1ed35c06cbe42';assert_lease(R,lease['token'])
expected=read(R/'SUPERVISOR_PROCESS.json');old=ident(expected['PID']);assert old['PID']==107856 and abs(old['created']-expected['created'])<.001 and old['command']==expected['command']
assert Path(old['cwd']).resolve()==CODE and old['command'][1:]==['-B','-X','utf8','-m','v42_autonomous.supervisor',str(R)]
cp=read(R/'SUPERVISOR_STATE.json');workers={};ledgers={};ledger_paths={}
for key,w in cp['workers'].items():
 actual=ident(w['PID']);assert actual['command']==w['command'] and abs(actual['created']-w['created'])<.001 and Path(actual['cwd']).resolve()==Path(r"D:\v42run32")
 req=read(Path(w['request']));assert req['implementation_SHA']=='9c159a8c64e6a7494aecf41266c0289e16cd65f6ee9eddf3de9f113593156ba9'
 workers[key]=actual;p=Path(w['request']).parent/'NATIVE_RUNTIME_LEDGER.json';raw=p.read_bytes();d=json.loads(raw);ledgers[key]=d;ledger_paths[key]=p
 capture=A/('CONTROLLER_IO_RELOAD_'+key.replace('/','_')+'_NATIVE_BEFORE.json');assert not capture.exists();capture.write_bytes(raw)
assert len(workers)==3 and set(workers)=={'B2/2025-05-01','B2/2025-05-02','B2/2025-05-03'}
files={x:rec(CODE/x) for x in ['v42_autonomous/recovery.py','v42_autonomous/supervisor.py']}
b=seal('CONTROLLER_HEARTBEAT_IO_RELOAD_BEFORE.json',dict(UTC=datetime.now(timezone.utc).isoformat(),supervisor=old,workers=workers,measured_Native={k:v['measured_Native_Runtime'] for k,v in ledgers.items()},Native_call_counts={k:len(v['calls']) for k,v in ledgers.items()},control_files=files,prior_supervisor_error=rec(R/'SUPERVISOR_ERROR.json'),lease_token=lease['token']))
# Terminate only the verified controller; all scientific child workers remain alive.
proc=psutil.Process(old['PID']);assert ident(old['PID'])==old;proc.terminate();proc.wait(timeout=10)
out=(A/'controller_heartbeat_io_stdout.log').open('ab');err=(A/'controller_heartbeat_io_stderr.log').open('ab')
new=subprocess.Popen(old['command'],cwd=CODE,stdin=subprocess.DEVNULL,stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW);out.close();err.close()
launch=seal('CONTROLLER_HEARTBEAT_IO_RELOAD_LAUNCH.json',dict(UTC=datetime.now(timezone.utc).isoformat(),PID=new.pid,command=old['command'],before=b,started_process_not_yet_admitted=True))
for i in range(100):
 try:
  current=read(R/'SUPERVISOR_PROCESS.json');actual=ident(current['PID'])
  assert actual['PID']==new.pid and actual['created']>old['created'] and actual['command']==old['command'] and Path(actual['cwd']).resolve()==CODE
  after=read(R/'SUPERVISOR_STATE.json');heartbeat=read(R/'SUPERVISOR_HEARTBEAT.json')
  assert heartbeat['process']['PID']==new.pid and after['state']=='B2_RUNNING'
  for key,w in workers.items():
   assert ident(w['PID'])==w and after['workers'][key]['PID']==w['PID']
   now=read(ledger_paths[key]);prior=ledgers[key]
   assert now['calls'][:len(prior['calls'])]==prior['calls'] and now['measured_Native_Runtime']>=prior['measured_Native_Runtime'] and now['P2_calls']==0 and now['Native_ceiling_seconds']==5400
  break
 except (OSError,AssertionError,psutil.NoSuchProcess):time.sleep(.25)
else:raise RuntimeError('NEW_CONTROLLER_ADOPTION_PROOF_REQUIRED')
assert all(rec(CODE/x)==v for x,v in files.items())
p=seal('CONTROLLER_HEARTBEAT_IO_RELOAD_VERIFICATION.json',dict(PASS=True,UTC=datetime.now(timezone.utc).isoformat(),before=b,launch=launch,actual_supervisor=actual,actual_workers={k:ident(v['PID']) for k,v in workers.items()},same_worker_PID_create_command_cwd=True,all3_current_workers_adopted=True,all3_original_Native_call_prefixes_preserved=True,Native_after={k:read(ledger_paths[k])['measured_Native_Runtime'] for k in workers},control_files=files,old_error_evidence_unchanged=rec(R/'SUPERVISOR_ERROR.json')==read(A/'CONTROLLER_HEARTBEAT_IO_RELOAD_BEFORE.json')['prior_supervisor_error'],scientific_worker_terminate_calls=0,Native_optimize_calls=0,model_constructions=0,new_supervisor_P2_calls=0,final_scientific_PASS_not_claimed=True))
print(json.dumps(dict(PASS=True,receipt=p,new_supervisor_PID=new.pid,workers_untouched=True)),flush=True)

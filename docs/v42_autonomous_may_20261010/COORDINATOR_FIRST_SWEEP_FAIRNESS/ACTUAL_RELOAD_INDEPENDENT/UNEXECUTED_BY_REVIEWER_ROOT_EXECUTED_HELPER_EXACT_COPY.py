from pathlib import Path
from datetime import datetime,timezone
import json,hashlib,psutil,subprocess,time,sys,argparse
sys.path.insert(0,"D:/MobileESS_v42_autonomous")
from v42_autonomous.recovery import assert_lease
from v42_b2_seed_recovery_v19.common import exclusive_lock,LockBusy
import errno
R=Path(r"D:\v42_may_restart_20261010_02");A=R/'autonomous';CODE=Path(r"D:\MobileESS_v42_autonomous")
def read(p):return json.loads(p.read_bytes())
def ident(pid):
 p=psutil.Process(pid);return dict(PID=p.pid,created=p.create_time(),command=p.cmdline(),cwd=p.cwd())
def rec(p):
 b=p.read_bytes();return dict(path=str(p),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def seal(name,d):
 p=A/name;assert not p.exists();p.write_text(json.dumps(d,indent=2)+"\n",encoding='utf-8');return rec(p)
parser=argparse.ArgumentParser();parser.add_argument('--lease-token',required=True);args=parser.parse_args()
lease=read(R/'REPAIR_LEASE.json');assert lease['token']==args.lease_token;assert_lease(R,lease['token'])
expected=read(R/'SUPERVISOR_PROCESS.json');old=ident(expected['PID']);assert old['PID']==107788 and old['created']==expected['created'] and old['command']==expected['command']
assert Path(old['cwd']).resolve()==CODE and old['command'][1:]==['-B','-X','utf8','-m','v42_autonomous.supervisor',str(R)]
heartbeat_before=read(R/'SUPERVISOR_HEARTBEAT.json')
assert all(heartbeat_before['process'][field]==old[field] for field in ('PID','created','command'))
stamp=datetime.fromisoformat(heartbeat_before['timestamp_UTC']);assert stamp.tzinfo is not None
heartbeat_age=(datetime.now(timezone.utc)-stamp).total_seconds();assert 0<=heartbeat_age<=60
lock_path=R/'AUTONOMOUS_SUPERVISOR.lock';assert lock_path.is_file()
try:
 with exclusive_lock(lock_path):
  raise AssertionError('EXISTING_LIVE_SUPERVISOR_OS_LOCK_REQUIRED')
except LockBusy as refusal:
 assert type(refusal) is LockBusy and str(refusal)=='LIVE_OS_LOCK:'+str(lock_path)
 assert isinstance(refusal.__cause__,OSError) and refusal.__cause__.errno in (errno.EACCES,errno.EAGAIN,errno.EDEADLK)
 mutex_refusal=dict(type=type(refusal).__name__,error=repr(refusal),cause=repr(refusal.__cause__),errno=refusal.__cause__.errno)
cp=read(R/'SUPERVISOR_STATE.json');workers={};ledgers={};ledger_paths={};requests={}
for key,w in cp['workers'].items():
 actual=ident(w['PID']);assert actual['command']==w['command'] and actual['created']==w['created'] and Path(actual['cwd']).resolve()==Path(r"D:\v42run35")
 req=read(Path(w['request']));assert req['implementation_SHA']=='a8cb6983fdda381987116936c9a402330111223547abaa64b51408f807ad6a14'
 workers[key]=actual;requests[key]=rec(Path(w['request']));p=Path(w['request']).parent/'NATIVE_RUNTIME_LEDGER.json';raw=p.read_bytes();d=json.loads(raw);ledgers[key]=d;ledger_paths[key]=p
 capture=A/('CONTROLLER_FAIRNESS_RELOAD_'+key.replace('/','_')+'_NATIVE_BEFORE.json');assert not capture.exists();capture.write_bytes(raw)
assert len(workers)==3 and set(workers)=={'B2/2025-05-01','B2/2025-05-02','B2/2025-05-03'}
prior_error_path=R/'SUPERVISOR_ERROR.json';error_raw=prior_error_path.read_bytes();saved_error=A/'CONTROLLER_RETRY_FAIRNESS_PRIOR_SUPERVISOR_ERROR.json';assert not saved_error.exists();saved_error.write_bytes(error_raw)
files={x:rec(CODE/x) for x in ['v42_autonomous/recovery.py','v42_autonomous/supervisor.py']}
b=seal('CONTROLLER_RETRY_FAIRNESS_RELOAD_BEFORE.json',dict(UTC=datetime.now(timezone.utc).isoformat(),supervisor=old,owned_recent_heartbeat=heartbeat_before,heartbeat_age_seconds=heartbeat_age,typed_live_OS_mutex_refusal=mutex_refusal,workers=workers,requests=requests,prior_error_raw_copy=rec(saved_error),measured_Native={k:v['measured_Native_Runtime'] for k,v in ledgers.items()},Native_call_counts={k:len(v['calls']) for k,v in ledgers.items()},control_files=files,prior_supervisor_error=rec(R/'SUPERVISOR_ERROR.json'),lease_token=lease['token']))
# Terminate only the verified controller; all scientific child workers remain alive.
proc=psutil.Process(old['PID']);assert ident(old['PID'])==old;proc.terminate();proc.wait(timeout=10)
out=(A/'controller_retry_fairness_stdout.log').open('ab');err=(A/'controller_retry_fairness_stderr.log').open('ab')
new=subprocess.Popen(old['command'],cwd=CODE,stdin=subprocess.DEVNULL,stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW);out.close();err.close()
launch=seal('CONTROLLER_RETRY_FAIRNESS_RELOAD_LAUNCH.json',dict(UTC=datetime.now(timezone.utc).isoformat(),PID=new.pid,command=old['command'],before=b,started_process_not_yet_admitted=True))
for i in range(100):
 try:
  current=read(R/'SUPERVISOR_PROCESS.json');actual=ident(current['PID'])
  assert actual['PID']==new.pid and actual['created']>old['created'] and actual['command']==old['command'] and Path(actual['cwd']).resolve()==CODE
  after=read(R/'SUPERVISOR_STATE.json');heartbeat=read(R/'SUPERVISOR_HEARTBEAT.json')
  assert heartbeat['process']['PID']==new.pid and after['state']=='B2_RUNNING'
  for key,w in workers.items():
   assert ident(w['PID'])==w and after['workers'][key]['PID']==w['PID']
   assert rec(Path(requests[key]['path']))==requests[key]
   now=read(ledger_paths[key]);prior=ledgers[key]
   assert now['calls'][:len(prior['calls'])]==prior['calls'] and now['measured_Native_Runtime']>=prior['measured_Native_Runtime'] and now['P2_calls']==0 and now['Native_ceiling_seconds']==5400
  break
 except (OSError,AssertionError,psutil.NoSuchProcess):time.sleep(.25)
else:raise RuntimeError('NEW_CONTROLLER_ADOPTION_PROOF_REQUIRED')
assert all(rec(CODE/x)==v for x,v in files.items())
assert rec(R/'SUPERVISOR_ERROR.json')==read(A/'CONTROLLER_RETRY_FAIRNESS_RELOAD_BEFORE.json')['prior_supervisor_error']
p=seal('CONTROLLER_RETRY_FAIRNESS_RELOAD_VERIFICATION.json',dict(PASS=True,UTC=datetime.now(timezone.utc).isoformat(),before=b,launch=launch,actual_supervisor=actual,actual_workers={k:ident(v['PID']) for k,v in workers.items()},same_worker_PID_create_command_cwd=True,all3_current_workers_adopted=True,all3_original_Native_call_prefixes_preserved=True,Native_after={k:read(ledger_paths[k])['measured_Native_Runtime'] for k in workers},control_files=files,exact_request_records_preserved=requests,old_error_evidence_unchanged=rec(R/'SUPERVISOR_ERROR.json')==read(A/'CONTROLLER_RETRY_FAIRNESS_RELOAD_BEFORE.json')['prior_supervisor_error'],scientific_worker_terminate_calls=0,Native_optimize_calls=0,model_constructions=0,new_supervisor_P2_calls=0,final_scientific_PASS_not_claimed=True))
print(json.dumps(dict(PASS=True,receipt=p,new_supervisor_PID=new.pid,workers_untouched=True)),flush=True)

"""Continue approved B3 after the new full chronological B2 Actual PASS."""
import os, sys, time, json, hashlib, subprocess, traceback, uuid
from pathlib import Path
H=Path(__file__).absolute().parent
F=H.parent/'IEEE8500_QSAFE_V2_LEGACY_SHELL_20260913'
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def save(name,value):
 p=H/name;p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_name(p.name+'.'+uuid.uuid4().hex+'.tmp')
 tmp.write_text(json.dumps(value,indent=2),encoding='utf-8')
 for attempt in range(101):
  try:os.replace(tmp,p);return
  except PermissionError:
   if attempt==100:raise
   time.sleep(.05)
def run(script,*args):
 label=script[:-3]+('_'+'_'.join(args) if args else '')
 log_path=H/(label+'_'+str(time.time_ns())+'.log')
 with log_path.open('x',encoding='utf-8') as log:
  p=subprocess.Popen([sys.executable,'-X','utf8','-B',script,*args],cwd=H,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
  save('SUPERVISOR_STATUS.json',dict(status='RUNNING',stage=label,worker_pid=p.pid,pid=os.getpid(),updated_unix=time.time(),log=str(log_path),B2_actual_namespace=str(F)))
  code=p.wait()
 assert code==0,(script,args,code)
def main():
 assert not(H/'B3_CONTINUATION_STARTED.json').exists(),'ALREADY_STARTED'
 done=read(F/'B2_ACTUAL_COMPLETE.json');assert done['status']=='PASS'
 assert sha(done['result']['path'])==done['result']['sha256']
 result=read(done['result']['path'])
 assert result['AC_feasible'] and result['independent_replay_PASS'] and result['ROBUST_Q_ONLY_UNRESOLVED_slots']==0
 assert read(F/'B2/CONTINUOUS_VERIFICATION.json')['status']=='PASS'
 for r in read(H/'INHERITED_SOURCE_FREEZE.json')['files']:assert sha(r['path'])==r['sha256'],r['path']
 save('B3_CONTINUATION_STARTED.json',dict(pid=os.getpid(),unix=time.time(),B2_PASS=done,B3_sequence=['B1_A0_REUSE','M1','A1_CONTINUOUS_14400S','MF','ACTUAL_SHELL_QSAFE'],fleet=6,solver_threads=4))
 run('mess_worker.py','B3_M1')
 run('a1_supervisor.py')
 run('mf_worker.py')
 run('b3_actual_shell.py')
 run('finalize_campaign_shell.py')
 save('SUPERVISOR_STATUS.json',dict(status='COMPLETE',updated_unix=time.time(),pid=os.getpid()))
if __name__=='__main__':
 try:main()
 except BaseException as e:
  save('B3_CONTINUATION_FAILURE.json',dict(error=repr(e),traceback=traceback.format_exc()))
  save('SUPERVISOR_STATUS.json',dict(status='FAILED',error=repr(e),updated_unix=time.time()))
  raise

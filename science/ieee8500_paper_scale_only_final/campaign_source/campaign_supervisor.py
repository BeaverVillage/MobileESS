import os,sys,time,json,subprocess,traceback
from pathlib import Path
H=Path(__file__).absolute().parent
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def save(n,v):
 p=H/n;q=p.with_suffix('.tmp');q.write_text(json.dumps(v,indent=2),encoding='utf-8');os.replace(q,p)
def run(script,*args):
 label=script[:-3]+('_'+'_'.join(args) if args else '')
 log_path=H/(label+'.log')
 if log_path.exists():log_path=H/(label+'_'+str(time.time_ns())+'.log')
 with log_path.open('x',encoding='utf-8') as log:
  p=subprocess.Popen([sys.executable,'-X','utf8','-B',script,*args],cwd=H,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
  save('SUPERVISOR_STATUS.json',dict(status='RUNNING',stage=label,worker_pid=p.pid,pid=os.getpid(),updated_unix=time.time(),log=str(log_path)))
  code=p.wait()
 assert code==0,(script,args,code)
def main():
 if '--resume' in sys.argv[1:]:
  assert (H/'CAMPAIGN_STARTED.json').exists()
  assert read(H/'recovery_stall/NUMERICAL_REPAIR_PROOF.json')['status']=='PASS'
  save('CAMPAIGN_RESUMED_'+str(time.time_ns())+'.json',dict(pid=os.getpid(),unix=time.time(),fleet=6))
  run('mess_worker.py','B2','--resume')
 else:
  assert not(H/'CAMPAIGN_STARTED.json').exists()
  save('CAMPAIGN_STARTED.json',dict(pid=os.getpid(),unix=time.time(),fleet=6))
  run('mess_worker.py','B2')
 while not(H/'PIPELINE_READY.json').exists():time.sleep(1)
 run('actual_worker.py','B2')
 run('mess_worker.py','B3_M1')
 run('a1_supervisor.py')
 run('mf_worker.py')
 run('actual_worker.py','B3')
 run('finalize_campaign.py')
 save('SUPERVISOR_STATUS.json',dict(status='COMPLETE',updated_unix=time.time(),pid=os.getpid()))
if __name__=='__main__':
 try:main()
 except BaseException as e:save('SUPERVISOR_FAILURE.json',dict(error=repr(e),traceback=traceback.format_exc()));save('SUPERVISOR_STATUS.json',dict(status='FAILED',error=repr(e),updated_unix=time.time()));raise

"""Single-day serial policy supervisor. No Actual entry point."""
import os,sys,time,json,subprocess,traceback,hashlib
from pathlib import Path
H=Path(__file__).absolute().parent
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def save(p,v):
 p=Path(p);q=p.with_suffix('.writing');q.write_text(json.dumps(v,indent=2),encoding='utf-8');os.replace(q,p)
def main():
 import psutil
 assert str(H).isascii(),'Launch this supervisor through the existing D:/ChatGPT/Mobile ESS 2 ASCII alias; Gurobi native file I/O cannot use the Unicode path.'
 resume='--resume' in sys.argv
 if resume:
  previous=read(H/'SUPERVISOR_STATUS.json')
  assert previous['status']=='FAILED' or (previous['status']=='PAUSED_USER' and read(H/'SEED_CORRECTION_RESTART_AUTHORIZATION.json')['status']=='APPROVED_CONDITIONAL_PROOF_PASS')
  save(H/f'SUPERVISOR_RESUMED_{time.time_ns()}.json',dict(pid=os.getpid(),started_unix=time.time(),workers=1,threads=4,date='2025-05-01',Actual=False))
 else:
  assert not(H/'SUPERVISOR_STARTED.json').exists()
  save(H/'SUPERVISOR_STARTED.json',dict(pid=os.getpid(),started_unix=time.time(),workers=1,threads=4,date='2025-05-01',Actual=False))
  preparation=int(sys.argv[1]);p=psutil.Process(preparation)
  assert any('IEEE8500_LEGAL_MIXED_M1_FULL_MAY01_20260916/prepare_electrical.py' in a for a in p.cmdline())
  while p.is_running():
   save(H/'SUPERVISOR_STATUS.json',dict(status='RUNNING',stage='ELECTRICAL_PREPARATION',worker_pid=preparation,supervisor_pid=os.getpid(),updated_unix=time.time()))
   time.sleep(10)
 assert (H/'COEFFICIENT_GENERATION.json').exists() and read(H/'COEFFICIENT_GENERATION.json')['status']=='PASS',read(H/'STATUS.json')
 for role in ('B1','B2','B3_M1','B3_A1','B3_MF'):
  if (H/('B3' if role=='B3_MF' else role)/'COMPLETE.json').exists():continue
  env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',TEMP=str(H/'tmp'),TMP=str(H/'tmp'))
  log_path=H/(role+'_production.log')
  if log_path.exists():log_path=H/(role+'_production_'+str(time.time_ns())+'.log')
  with log_path.open('x',encoding='utf-8') as log:
   child=subprocess.Popen([sys.executable,'-X','utf8','-B','-u',str(H/'production_worker.py'),role],cwd=H,env=env,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
   save(H/'SUPERVISOR_STATUS.json',dict(status='RUNNING',stage=role,worker_pid=child.pid,supervisor_pid=os.getpid(),updated_unix=time.time(),log=str(log_path),workers=1,threads=4))
   code=child.wait()
  assert code==0,(role,code)
 subprocess.run([sys.executable,'-B',str(H/'report_full.py')],cwd=H,check=True,creationflags=subprocess.CREATE_NO_WINDOW)
 save(H/'SUPERVISOR_STATUS.json',dict(status='COMPLETE',stage='DA_AND_FRESH_COMPLETE_ACTUAL_NOT_RUN',supervisor_pid=os.getpid(),updated_unix=time.time()))
if __name__=='__main__':
 try:main()
 except BaseException as e:save(H/'SUPERVISOR_STATUS.json',dict(status='FAILED',error=repr(e),traceback=traceback.format_exc(),updated_unix=time.time()));raise

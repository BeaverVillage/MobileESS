from pathlib import Path
import os,sys,time,json,subprocess,hashlib,traceback,ctypes,msvcrt
import psutil
ROOT=Path(__file__).parent
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def save(p,v):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(v,indent=2),encoding='utf-8')
 # Windows readers can briefly deny delete sharing during an atomic replacement.
 # Preserve the previous valid JSON and retry publication without restarting work.
 for attempt in range(100):
  try:
   os.replace(tmp,p)
   return
  except PermissionError:
   if attempt==99:raise
   time.sleep(min(0.05*(attempt+1),0.5))
def in_job(pid):
 k=ctypes.WinDLL('kernel32',use_last_error=True);k.OpenProcess.argtypes=[ctypes.c_uint32,ctypes.c_int,ctypes.c_uint32];k.OpenProcess.restype=ctypes.c_void_p;k.IsProcessInJob.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.POINTER(ctypes.c_int)];k.CloseHandle.argtypes=[ctypes.c_void_p]
 h=k.OpenProcess(0x1000,False,pid);r=ctypes.c_int();assert h;k.IsProcessInJob(h,None,ctypes.byref(r));k.CloseHandle(h);return bool(r.value)
def pin():
 files=list(ROOT.glob('*.py'))+list((ROOT/'original_source').rglob('*.py'))+[ROOT/'PATCH_MANIFEST.json',ROOT/'AUTHORITY_VERIFIED.json']
 save(ROOT/'RUN_CODE_SHA.json',{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files})
def verify():
 for p,h in read(ROOT/'RUN_CODE_SHA.json').items():assert hashlib.sha256(Path(p).read_bytes()).hexdigest()==h,('RUN_CODE_CHANGED',p)
class AdoptedWorker:
 def __init__(self,proc,status):
  self.proc=proc;self.status=status
 def poll(self):
  if self.proc.is_running():return None
  result=read(self.status)
  return 0 if result.get('status')=='COMPLETE' else 1
def adopt_workers(phases,days):
 active={}
 for proc in psutil.process_iter(['pid','cmdline','create_time']):
  cmd=proc.info['cmdline'] or []
  matches=[i for i,arg in enumerate(cmd) if os.path.normcase(os.path.abspath(arg))==os.path.normcase(str(ROOT/'worker.py'))]
  if not matches:continue
  i=matches[0];day,phase=cmd[i+1:i+3]
  if phase=='M1_WORKER':continue  # Owned by its still-running B3 parent.
  assert day in days and phase in phases,('UNRECOGNIZED_LIVE_WORKER',cmd)
  assert day not in active,('DUPLICATE_LIVE_DATE',day)
  status=ROOT/'days'/day/'status'/f'{phase}.json';receipt=read(status)
  assert receipt['pid']==proc.pid and abs(receipt['started_at']-proc.create_time())<15,('WORKER_IDENTITY_MISMATCH',cmd)
  assert not in_job(proc.pid)
  logp=ROOT/'days'/day/'logs'/f'{phase}.log'
  active[day]=dict(proc=AdoptedWorker(proc,status),log=None,log_path=str(logp),phase=phase,started_at=receipt['started_at'],pid=proc.pid,adopted=True,process_created_at=proc.create_time())
 return active
def main():
 os.environ['GIT_OPTIONAL_LOCKS']='0'
 os.environ['PATH']=str(Path(read(ROOT/'RUNTIME_EXECUTABLES.json')['git_executable']).parent)+os.pathsep+os.environ.get('PATH','')
 sys.stdin=open(os.devnull);sys.stdout=open(ROOT/'supervisor.log','a',encoding='utf-8',buffering=1);sys.stderr=sys.stdout
 assert not in_job(os.getpid()),'SUPERVISOR_ATTACHED_TO_JOB'
 save(ROOT/'DETACHED_PROOF.json',dict(pid=os.getpid(),parent=psutil.Process().parent().name(),in_windows_job=False,stdio='worker-owned disk log',created=time.time()))
 assert read(ROOT/'AUTHORITY_VERIFIED.json')['status']=='PASS';verify()
 phases=['A1','B3','CLOSURE','ACTUAL','REPORT'];days=[f'2025-05-{i:02}' for i in range(1,32)];active=adopt_workers(phases,days);errors=[];started=time.time();last_pairs=-1
 manifest=read(ROOT/'EXPERIMENT_MANIFEST.json');manifest.update(status='RUNNING',NO_CC4_NEW_RUN=True);save(ROOT/'EXPERIMENT_MANIFEST.json',manifest)
 def next_phase(day):
  for phase in phases:
   p=ROOT/'days'/day/'status'/f'{phase}.json'
   if not p.exists() or read(p)['status']!='COMPLETE':return phase
  return None
 try:
  while True:
   verify()
   held=read(ROOT/'HELD_DATES.json') if (ROOT/'HELD_DATES.json').exists() else {}
   for d,row in list(active.items()):
    code=row['proc'].poll()
    if code is not None:
     if row['log'] is not None:row['log'].close()
     del active[d]
     if code:errors.append(dict(day=d,phase=row['phase'],exit_code=code,log=row['log_path']))
   completed=[d for d in days if next_phase(d) is None]
   if len(completed)!=last_pairs:
    subprocess.run([sys.executable,'-B',str(ROOT/'report.py'),'aggregate'],cwd=ROOT,check=True);last_pairs=len(completed)
   failed={r['day'] for r in errors}
   if not errors:
    for d in days:
     if len(active)>=4:break
     if d in active or d in completed or d in failed or d in held:continue
     phase=next_phase(d);case=ROOT/'days'/d;case.mkdir(parents=True,exist_ok=True);logp=case/'logs'/f'{phase}.log';logp.parent.mkdir(exist_ok=True)
     log=logp.open('a',encoding='utf-8');child_env=os.environ.copy();child_env.pop('PYTHONPATH',None)
     for key in ['V41_FO_RECOVERY_PLAN','B3_2R_DAY','B3_2R_FAST_WIRING']:child_env.pop(key,None)
     for key in ['OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS']:child_env[key]='4'
     p=subprocess.Popen([sys.executable,'-B','-u',str(ROOT/'worker.py'),d,phase],cwd=case,env=child_env,stdin=subprocess.DEVNULL,stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW)
     assert not in_job(p.pid)
     active[d]=dict(proc=p,log=log,log_path=str(logp),phase=phase,started_at=time.time(),pid=p.pid)
   state=dict(status='FAILED_REQUIRES_REPAIR' if errors else 'COMPLETE' if len(completed)==31 else 'RUNNING',supervisor_pid=os.getpid(),updated_at=time.time(),started_at=started,completed=completed,errors=errors,active={d:{k:v for k,v in r.items() if k not in ('proc','log')} for d,r in active.items()},workers=4,threads_per_worker=4,ram_available_gib=psutil.virtual_memory().available/2**30,cpu_percent=psutil.cpu_percent(),budget=[900,180,120,120])
   state['held_dates']=held
   if held and not errors:state['status']='RUNNING_WITH_HOLD' if active else 'WAITING_ON_HELD_DATE'
   save(ROOT/'CAMPAIGN_STATUS.json',state)
   if len(completed)==31:
    subprocess.run([sys.executable,'-B',str(ROOT/'report.py'),'aggregate'],cwd=ROOT,check=True);manifest.update(status='COMPLETE');save(ROOT/'EXPERIMENT_MANIFEST.json',manifest);break
   if errors and not active:break
   time.sleep(5)
 except BaseException as e:
  save(ROOT/'SUPERVISOR_FAILURE.json',dict(error=repr(e),traceback=traceback.format_exc()));raise
if __name__=='__main__':
 if '--pin' in sys.argv:pin()
 else:main()

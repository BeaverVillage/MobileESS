"""Serial IEEE8500 affected-stage queue; isolated from IEEE123 parallel runtime."""
from pathlib import Path
import os,sys,time,json,subprocess,traceback,hashlib,csv
import psutil
from runtime_io import atomic_json, exclusive_supervisor
ROOT=Path(__file__).absolute().parent;P=ROOT/'production';LOG=P/'logs';LOG.mkdir(exist_ok=True)
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def save(p,v):
 atomic_json(p,v)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def publish(status,stage,pid=None,began=None,error=None,log=None):
 workers=[]
 if pid:
  try:
   parent=psutil.Process(pid)
   for x in [parent,*parent.children(recursive=True)]:workers.append(dict(pid=x.pid,CPU_seconds=sum(x.cpu_times()[:2]),RSS_GiB=x.memory_info().rss/2**30))
  except psutil.Error:pass
 try:save(P/'MONITOR_STATUS.json',dict(status=status,stage=stage,worker_pid=pid,supervisor_pid=os.getpid(),stage_started_unix=began,updated_unix=time.time(),threads=4,error=error,process_tree=workers,log=str(log) if log else None))
 except PermissionError as exc:
  with (LOG/'STATUS_WRITE_RETRIES.log').open('a',encoding='utf-8') as f:f.write(f'{time.time()} {exc!r}\n')
def stop_gate():
 if (P/'SEMANTIC_ALIGNMENT_STOP.json').exists():raise RuntimeError('SCIENTIFIC_STOP_SURROGATE_EXACT_RANKING_INVERSION')
def stage(role,complete):
 stop_gate()
 if complete.exists():assert read(complete)['status']=='PASS';return
 existing=[]
 for process in psutil.process_iter(['pid','cmdline']):
  cmd=process.info['cmdline'] or []
  if any(str(P/'aligned_worker.py').lower()==str(x).lower() for x in cmd) and cmd[-1]==role:existing.append(process)
 assert len(existing)<=1
 began=time.time();handle=None;log=LOG/f'{role}_{time.time_ns()}.log';adopted=bool(existing)
 if adopted:proc=existing[0];pid=proc.pid
 else:
  handle=log.open('w',encoding='utf-8');proc=subprocess.Popen([sys.executable,'-B','-u',str(P/'aligned_worker.py'),role],cwd=P,stdout=handle,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0));pid=proc.pid
 save(P/(role+'_STAGE_SOURCE.json'),dict(role=role,adopted_existing_worker=adopted,start=time.time(),files=[dict(path=str(f),sha256=sha(f)) for f in [P/'aligned_worker.py',P/'aligned_mess.py',P/'bootstrap.py']]))
 while proc.is_running() if adopted else proc.poll() is None:
  publish('RUNNING',role,pid,began,log=log);time.sleep(3)
 if handle:handle.close()
 stop_gate()
 if (not adopted and proc.returncode) or not complete.exists():raise RuntimeError(f'{role}_FAILED_OR_INCOMPLETE; log={log if not adopted else P/(role+"_ALIGNED_FAILURE.json")}')
 assert read(complete)['status']=='PASS'
def subprocess_stage(name,script,complete):
 if complete.exists():return
 stop_gate();began=time.time();log=LOG/f'{name}_{time.time_ns()}.log'
 with log.open('w',encoding='utf-8') as f:
  p=subprocess.Popen([sys.executable,'-B','-u',str(script)],cwd=P,stdout=f,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
  while p.poll() is None:publish('RUNNING',name,p.pid,began,log=log);time.sleep(3)
 if p.returncode or not complete.exists():raise RuntimeError(f'{name}_FAILED_OR_INCOMPLETE; log={log}')
def main():
 assert read(P/'PRODUCTION_AUTHORIZATION.json')['authorized'];assert read(P/'scale_audit/PHYSICAL_SCALE_AUDIT.json')['status']=='PASS'
 assert psutil.cpu_count()>=16 and psutil.virtual_memory().available>=6*2**30
 save(P/'CONCURRENT_RESOURCE_CHECK.json',dict(IEEE123_concurrent_days=3,IEEE123_threads_per_day=4,IEEE8500_threads=4,total_planned_threads=16,logical_CPUs=psutil.cpu_count(),available_RAM_GiB=psutil.virtual_memory().available/2**30,at=time.time()))
 assert read(P/'B0_REUSE_VERIFIED.json')['status']=='PASS'
 for role,proof in [('B1','B1/COMPLETE.json'),('B2','B2/COMPLETE.json'),('B3_M1','B3_M1/COMPLETE.json'),('B3_A1','B3_A1/COMPLETE.json'),('B3_MF','B3_MF/COMPLETE.json')]:stage(role,P/proof)
 subprocess_stage('REPORT',P/'aligned_planning_gate.py',P/'ALIGNED_PLANNING_GATE.json')
 assert read(P/'ALIGNED_PLANNING_GATE.json')['status']=='PASS'
 subprocess_stage('Actual',P/'aligned_actual.py',P/'Actual/CAMPAIGN_COMPLETE.json')
 subprocess_stage('EXPORT',P/'aligned_export.py',P/'FINAL_EXPORT_COMPLETE.json')
 publish('COMPLETE','EXPORT')
if __name__=='__main__':
 supervisor_lock=exclusive_supervisor(ROOT/'SUPERVISOR.lock')
 try:main()
 except Exception as e:
  current=read(P/'MONITOR_STATUS.json') if (P/'MONITOR_STATUS.json').exists() else {}
  save(P/'SUPERVISOR_FAILURE.json',dict(error=repr(e),traceback=traceback.format_exc(),at=time.time()))
  publish('STOP' if (P/'SEMANTIC_ALIGNMENT_STOP.json').exists() else 'FAILED',current.get('stage','START'),error=repr(e));raise

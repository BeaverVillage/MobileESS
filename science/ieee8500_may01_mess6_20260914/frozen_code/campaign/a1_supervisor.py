from campaign_supervisor import H,read,save
import sys,time,subprocess,traceback,hashlib
def sha(p):
 with open(p,'rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def main():
 assert not(H/'SEARCH_CLOCK.json').exists()
 with (H/'a1_worker.log').open('w',encoding='utf-8') as log:
  child=subprocess.Popen([sys.executable,'-X','utf8','-B','a1_worker.py'],cwd=H,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
  save('A1_WORKER_PROCESS.json',dict(pid=child.pid,started_unix=time.time()))
  while not(H/'SEARCH_CLOCK.json').exists():
   if child.poll() is not None:raise RuntimeError('A1_EXIT_BEFORE_SEARCH:'+str(child.returncode))
   time.sleep(.1)
  clock=read(H/'SEARCH_CLOCK.json');assert clock['total_seconds']==14400 and clock['clock_pause_allowed'] is False
  while child.poll() is None and time.perf_counter()<clock['deadline_monotonic']:time.sleep(min(.05,max(0,clock['deadline_monotonic']-time.perf_counter())))
  killed=child.poll() is None
  requested=time.perf_counter()
  if killed:child.kill()
  code=child.wait()
  if requested<clock['deadline_monotonic']:raise RuntimeError('A1_EARLY_EXIT:'+str(code))
 save('DEADLINE_ENFORCEMENT.json',dict(status='STOPPED',budget_seconds=14400,clock=clock,killed_at_deadline=killed,kill_request_lateness_seconds=max(0,requested-clock['deadline_monotonic']),process_exit_unix=time.time(),exit_code=code))
 chosen=read(H/'DEADLINE_INCUMBENT.json');assert chosen['status']=='INDEPENDENTLY_VALIDATED' and max(chosen['accepted_elapsed'],chosen['published_elapsed'])<=14400
 for key in ['jobs','power','exact_AC']:
  r=chosen[key];assert sha(r['path'])==r['sha256']
 save('FOUR_HOUR_A1_INCUMBENT.json',chosen)
if __name__=='__main__':
 try:main()
 except BaseException as e:save('A1_SUPERVISOR_FAILURE.json',dict(error=repr(e),traceback=traceback.format_exc()));raise

"""Full May: three concurrent days, one sequential policy worker/day, four threads/worker."""
from pathlib import Path
import os,sys,time,json,hashlib,subprocess,csv,traceback
import psutil
from runtime_io import atomic_json, exclusive_supervisor
OUT=Path(__file__).absolute().parent;VIEW=OUT/'monitor_view/frozen_artifacts/v41r4_may/loop_wall_v4'
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,v):
 atomic_json(p,v)
def folder(c):return OUT/('replays_1round' if c['round']=='1R' else 'replays')/c['day']/c['policy']
authority=read(OUT/'MONTHLY_INPUT_AUTHORITY.json');cases=authority['cases'];by_id={c['case_id']:c for c in cases};start=time.time();controller_sha=sha(OUT/'actual_controller.py');running={};failure=False;receipts=set()
units={c['case_id']:dict(day=c['day'],policy=c['policy'] if c['round']=='COMMON' else 'B3_'+c['round'],status='WAITING',phase='actual',worker_pid=None,error='') for c in cases}
def valid(c):
 f=folder(c)/'COMPLETE.json'
 if not f.exists():return False
 try:r=read(f)
 except (ValueError,PermissionError):return False
 assert r['controller_SHA']==controller_sha and r['Planning_Fresh_preserved'] and r['Planning_optimizer_calls']==0
 if r.get('decision_sha256'):assert r['decision_sha256']==c['decision_sha256']
 else:
  old=next(x for x in read(OUT/'INPUT_AUTHORITY.json')['cases'] if (x['day'],x['policy'])==(c['day'],c['policy']))
  assert old['decision_sha256']==c['decision_sha256'] and old['common_inputs']==c['common_inputs']
 return True
def external():
 result=[];legacy_parent=False;own={v['p'].pid for v in running.values()}
 for p in psutil.process_iter(['pid','cmdline']):
  cmd=p.info['cmdline'] or []
  if any(str(OUT/'campaign.py').lower()==str(a).lower() for a in cmd):legacy_parent=True
  if p.pid in own:continue
  for i,a in enumerate(cmd):
   if str(OUT/'run_case.py').lower()!=str(a).lower():continue
   day,policy=cmd[i+1:i+3]
   variant='1R' if '--round1' in cmd else '2R' if policy=='B3' else 'COMMON'
   key=cmd[cmd.index('--case-id')+1] if '--case-id' in cmd else f'{day}_{policy}_{variant}'
   assert key in by_id;result.append(dict(pid=p.pid,key=key,day=day))
 return result,legacy_parent
def telemetry(pid,c,log=None):
 out=dict(pid=pid,day=c['day'],policy=units[c['case_id']]['policy'],threads=4,CPU_seconds=0,RSS_GiB=0,slots_complete=0)
 try:
  p=psutil.Process(pid);out.update(CPU_seconds=sum(p.cpu_times()[:2]),RSS_GiB=p.memory_info().rss/2**30,process_state=p.status())
 except psutil.NoSuchProcess:out['process_state']='finished'
 progress=folder(c)/'PROGRESS.json'
 if progress.exists():
  try:out.update(slots_complete=read(progress).get('slots_complete',0))
  except (ValueError,PermissionError):pass
 if log and log.exists():out['log_tail']=' | '.join(log.read_text(encoding='utf-8',errors='replace').splitlines()[-2:])
 return out
def publish(status,ext):
 active=[]
 for key,v in running.items():active.append(telemetry(v['p'].pid,by_id[key],v['log']))
 for e in ext:active.append(telemetry(e['pid'],by_id[e['key']]))
 assert len({x['day'] for x in active})==len(active)<=3,'THREE_DISTINCT_DAY_WORKERS_REQUIRED'
 for c in cases:
  key=c['case_id']
  if valid(c):
   units[key].update(status='COMPLETE',phase='complete',worker_pid=None)
   if key not in receipts:
    r=read(folder(c)/'COMPLETE.json');label=units[key]['policy']
    save(VIEW/c['day']/label/'actual/ACTUAL_RECEIPT.json',dict(status='COMPLETE'))
    save(VIEW/'audit'/c['day']/f'{label}_ACCEPTANCE.json',dict(Fresh='FROZEN',Actual_physical_outcome='PASS' if r['AC_PASS'] else 'WITH_VIOLATIONS',Actual_summary=r['summary']));receipts.add(key)
 for x in active:
  key=next(c['case_id'] for c in cases if c['day']==x['day'] and units[c['case_id']]['policy']==x['policy'])
  units[key].update(status='RUNNING',phase=f"actual {x['slots_complete']}/96",worker_pid=x['pid'])
 tm=dict(pid=os.getpid(),CPU_seconds=sum(x['CPU_seconds'] for x in active),RSS_GiB=sum(x['RSS_GiB'] for x in active),elapsed_seconds=time.time()-start,day='3 days parallel',policy='4 threads each',process_state=status,log_tail=' | '.join(f"{x['day']} {x['policy']} {x['slots_complete']}/96 PID {x['pid']}" for x in active))
 v=dict(status=status,pid=os.getpid(),supervisor_pid=os.getpid(),updated_at=time.time(),scope='FULL MAY 2025; THREE CONCURRENT DAYS; FOUR THREADS EACH',days=31,day_workers=3,threads_per_day=4,total_IEEE123_threads=12,reserved_IEEE8500_threads=4,distinct_replays=155,round_policy_rows=248,units=units,active=active,telemetry=tm)
 save(OUT/'MONTHLY_CAMPAIGN_STATUS.json',v);save(VIEW/'campaign_state.json',dict(units=units));save(VIEW/'campaign_progress.json',v)
def finalize():
 rows=[]
 for c in cases:
  r=read(folder(c)/'COMPLETE.json')
  for rnd in (['1R','2R'] if c['round']=='COMMON' else [c['round']]):rows.append(dict(r,round=rnd,day=c['day'],policy=c['policy'],case_id=c['case_id']))
 assert len(rows)==248
 cols=['day','round','policy','case_id','old_Actual_rho','new_Actual_rho','Q_interventions','P_interventions','max_abs_delta_P_DA','max_abs_corrective_delta_P','energy_recovery_kwh','AC_PASS','runtime_seconds']
 with (OUT/'MONTHLY_ACTUAL_COMPARISON.csv').open('w',newline='',encoding='utf-8-sig') as f:
  w=csv.DictWriter(f,fieldnames=cols,extrasaction='ignore');w.writeheader();w.writerows(rows)
 assert all(sha(p)==h for p,h in authority['protected_files'].items())
 aggregate={rnd:{pol:dict(mean=sum(r['new_Actual_rho'] for r in rows if r['round']==rnd and r['policy']==pol)/31,max=max(r['new_Actual_rho'] for r in rows if r['round']==rnd and r['policy']==pol),AC_PASS_days=sum(r['AC_PASS'] for r in rows if r['round']==rnd and r['policy']==pol)) for pol in ('B0','B1','B2','B3')} for rnd in ('1R','2R')}
 save(OUT/'MONTHLY_FINAL_RESULT.json',dict(status='COMPLETE',all_AC_PASS=all(r['AC_PASS'] for r in rows),cases=rows,aggregates=aggregate,original_authorities_preserved=True,controller_SHA=controller_sha,concurrent_days=3,threads_each=4))
def main():
 global failure
 scope=read(OUT/'ACTIVE_SCOPE.json');assert scope['scope']=='FULL_MAY_3DAY_PARALLEL' and scope['threads']==4 and scope['concurrent_days']==3
 assert psutil.cpu_count()>=16
 for path,h in authority['protected_files'].items():assert sha(path)==h,('FROZEN_DRIFT',path)
 save(OUT/'PARALLEL_RESOURCE_CHECK.json',dict(logical_CPUs=psutil.cpu_count(),RAM_available_GiB=psutil.virtual_memory().available/2**30,IEEE123_day_workers=3,threads_per_worker=4,IEEE123_total_threads=12,IEEE8500_reserved_threads=4,total_planned_threads=16,CPU_oversubscription=False,at=time.time()))
 while True:
  assert read(OUT/'ACTIVE_SCOPE.json')['scope']=='FULL_MAY_3DAY_PARALLEL'
  assert sha(OUT/'actual_controller.py')==controller_sha
  for key,v in list(running.items()):
   if v['p'].poll() is None:continue
   v['handle'].close();del running[key]
   if v['p'].returncode or not valid(by_id[key]):
    units[key].update(status='FAILED',worker_pid=None,error=str(v['log']));failure=True
  ext,legacy=external()
  if all(valid(c) for c in cases) and not running and not ext:finalize();publish('COMPLETE',[]);return 0
  occupied={by_id[k]['day'] for k in running}|{e['day'] for e in ext}
  reserved=max(len(ext),1 if legacy else 0)
  free=3-len(running)-reserved
  if not failure:
   for day in authority['days']:
    if free<=0:break
    if day in occupied:continue
    c=next((c for c in cases if c['day']==day and not valid(c)),None)
    if c is None:continue
    if psutil.virtual_memory().available<3*2**30:break
    key=c['case_id'];log=OUT/'logs'/f'parallel_{key}_{time.time_ns()}.log';log.parent.mkdir(exist_ok=True);handle=log.open('w',encoding='utf-8')
    cwd=OUT/'runtime'/key;cwd.mkdir(parents=True,exist_ok=True)
    env=dict(os.environ,OMP_NUM_THREADS='4',OPENBLAS_NUM_THREADS='4',MKL_NUM_THREADS='4',NUMEXPR_NUM_THREADS='4')
    proc=subprocess.Popen([sys.executable,'-B','-u',str(OUT/'run_case.py'),c['day'],c['policy'],'--case-id',key],cwd=cwd,env=env,stdout=handle,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    running[key]=dict(p=proc,log=log,handle=handle);occupied.add(day);free-=1
  try:publish('FAILED_DRAINING_ACTIVE' if failure else 'RUNNING',ext)
  except PermissionError as error:
   # A temporarily locked monitor file must not abandon the execution queue.
   with (OUT/'STATUS_WRITE_RETRIES.log').open('a',encoding='utf-8') as f:f.write(f'{time.time()} {error!r}\n')
  if failure and not running and not ext:return 1
  time.sleep(3)
if __name__=='__main__':
 supervisor_lock=exclusive_supervisor(OUT/'MONTHLY_SUPERVISOR.lock')
 try:sys.exit(main())
 except Exception as e:save(OUT/'MONTHLY_PARALLEL_FAILURE.json',dict(error=repr(e),traceback=traceback.format_exc()));raise

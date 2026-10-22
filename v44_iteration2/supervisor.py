"""Persistent single owner: B2 drain -> all31 serial Planning -> rolling Actual7."""
from pathlib import Path
from contextlib import contextmanager
import os,sys,time,subprocess,traceback,psutil
from . import config as c
from .io import read,optional,record,verify,atomic,now
from . import authority,resources
from .safety import alive,b2_state,ready_receipt,try_os_locks
from .contracts import actual_barrier,full_a,full_m

STATE=c.ROOT/'STATE.json'

def initial():
 return dict(experiment='V44_iteration2',phase='WAIT_B2',jobs=[dict(day=d,arm='B3',status='QUEUED',stages={}) for d in c.DAYS],workers=[],MESS_units=list(c.FLEET),max_Actual_workers=7)

def publish(state):
 state.update(UTC=now(),supervisor=dict(pid=os.getpid(),process_created=psutil.Process().create_time()),commit_sha=authority.validate()['commit_sha'])
 atomic(STATE,state)

@contextmanager
def single_owner():
 path=c.OPS/'SUPERVISOR.lock';path.parent.mkdir(parents=True,exist_ok=True)
 if not path.exists():path.write_bytes(b'0')
 with try_os_locks([path]):yield

def orphans():
 found=[]
 for identity in optional(STATE).get('workers',[]):
  if alive(identity):found.append(identity)
 for path in c.ROOT.glob('2025-05-*/B3/attempt*/START.json'):
  identity=optional(path)
  if alive(identity):found.append(dict(pid=identity['pid'],process_created=identity['process_created'],root=str(path.parent)))
 # Cover the few milliseconds between Popen and the first state/START write.
 for p in psutil.process_iter(['pid','cmdline','create_time']):
  try:
   args=p.info['cmdline'] or []
   if '--worker' in args and any(str(c.OPS).casefold() in str(a).casefold() for a in args):found.append(dict(pid=p.pid,process_created=p.info['create_time'],root='ENTRY_OR_EXISTING_WORKER'))
  except (psutil.Error,TypeError):pass
 return list({(x['pid'],x['process_created']):x for x in found}.values())

def completed(folder,stage,day):
 """Recover a completed core after a controller/public-receipt interruption."""
 from .worker import public_result
 from .history import checked_completed
 folder=Path(folder);core=folder/c.CORE_STAGE[stage];request=read(core/'request.json')
 checked_completed(core/'COMPLETED_STAGE_CHECKPOINT.json',request)
 result=read(core/'RESULT.json')
 (full_m if stage.startswith('M') else full_a)(result,day)
 public=folder/'RESULT.json'
 if public.exists():
  value=read(public)
  if value.get('PASS') and not value.get('error') and value.get('checkpoint'):
   verify([value['core_result'],value['checkpoint']]);return record(public)
 # Preserve any previous failure. This is a completed-stage replay, not a solve.
 output=folder/'RECOVERED_COMPLETED_RESULT.json'
 if not output.exists():
  value=public_result(read(folder/'request.json'),result,core/'RESULT.json',time.monotonic())
  value.update(checkpoint=record(core/'COMPLETED_STAGE_CHECKPOINT.json'),completed_stage_reused=True,new_resume_Native_calls=0)
  value.update(original_public_result=record(public) if public.exists() else None,original_source_sha=request['source_sha'])
  atomic(output,value)
 return record(output)

def launch(request):
 reservation=c.OPS/'attempt_reservations'/request['day']/(Path(request['case_root']).name+'.json')
 if reservation.exists() or Path(request['case_root']).exists():raise PermissionError('ATTEMPT_ALREADY_RESERVED_OR_CREATED')
 atomic(reservation,dict(day=request['day'],stage=request['iteration_stage'],case_root=request['case_root'],source_sha=request['source_sha'],UTC=now()))
 pointer=c.OPS/'requests'/Path(request['case_root']).parent.parent.name/(Path(request['case_root']).name+'.json')
 atomic(pointer,request);logs=c.OPS/'logs';logs.mkdir(parents=True,exist_ok=True)
 stem=request['day']+'_'+request['iteration_stage']+'_'+Path(request['case_root']).name
 env=dict(os.environ,PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',NUMEXPR_NUM_THREADS='1')
 with (logs/(stem+'.out.log')).open('ab') as out,(logs/(stem+'.err.log')).open('ab') as err:
  p=subprocess.Popen([sys.executable,'-B','-X','utf8','-u','-m','v44_iteration2','--worker',str(pointer)],cwd=c.REPO,env=env,stdout=out,stderr=err,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
 return p,dict(pid=p.pid,process_created=psutil.Process(p.pid).create_time(),day=request['day'],stage=request['iteration_stage'],root=request['case_root'],request=record(pointer))

def wait_resources(state,phase,**kwargs):
 while True:
  resource=resources.admission(c.ROOT,phase=phase,**kwargs);state['resources']=resource
  if resource['admit']:return
  state['phase']='RESOURCE_WAIT_'+phase;publish(state);time.sleep(15)

def stage_resume(folder,stage,day,parent):
 """Only an interrupted same-stage attempt may spend its remaining account."""
 from .resume import admit
 from v44.campaign import stage_request
 core=Path(folder)/c.CORE_STAGE[stage]
 old=read(core/'request.json');admit(core,dict(old))
 if old['iteration_stage']!=stage or old['fixed_parent_receipt']!=parent:raise PermissionError('RESUME_FIXED_PARENT_DRIFT')
 return core

def freeze(job):
 stages=job['stages'];m=read(stages['M4']['result']['path']);a=read(stages['A4']['result']['path'])
 mr=m['core_result'];ar=a['core_result'];mp=full_m(read(mr['path']),job['day']);full_a(read(ar['path']),job['day'])
 aidc=read(ar['path'])['AIDC_reference'];ref=read(aidc['path'])
 evidence=[s['result'] for s in stages.values()]+[mr,ar,aidc,ref['identity']['physical']]+[read(s['result']['path'])['checkpoint'] for s in stages.values()]
 verify(evidence);path=c.ROOT/job['day']/'B3/M4_FREEZE.json'
 value=dict(PASS=True,day=job['day'],arm='B3',experiment='V44_iteration2',MESS_units=list(c.FLEET),equipment_version=c.EQUIPMENT,
  M4_core=mr,A4_core=ar,A4_reference=aidc,M4_case_sha=mp['case_sha'],M4_plan_sha=mp['plan_sha'],evidence=evidence,
  actual_voltage_band=[.95,1.05],M4_voltage_band=[.95,1.05],commit_sha=authority.validate()['commit_sha'])
 if path.exists():
  if read(path)!=value:raise ValueError('FROZEN_M4_DRIFT')
 else:atomic(path,value)
 job.update(status='PLANNING_PASS',M4_freeze=record(path))

def planning(state,lease):
 from .requests import make
 catalogue={x['day']:x for x in read(c.DOC/'BASELINE_CATALOG.json')['days']}
 for job in state['jobs']:
  if job['status'] in ('PLANNING_FAILED','PLANNING_BLOCKED'):continue
  day=job['day'];row=catalogue[day]
  parent=next(r for r in row['evidence'] if Path(r['path'])==Path(row['A2'])/'RESULT.json')
  job['reused_original_stages']=dict(A1=row['A1'],M1=row['M1'],A2=row['A2'],evidence=row['evidence'],new_Native_calls=0)
  for stage in c.STAGES:
   item=job['stages'].get(stage)
   if item:
    folder=Path(item['root'])
    try:
     reference=completed(folder,stage,day);value=read(reference['path'])
     item.update(status='PASS',PASS=True,result=reference);parent=value['core_result'];publish(state);continue
    except (OSError,ValueError,KeyError,PermissionError) as error:
     if item.get('status')=='PASS':
      job.update(status='PLANNING_BLOCKED',error='COMPLETED_STAGE_EVIDENCE_DRIFT:'+repr(error));publish(state);break
     # A recorded scientific failure is terminal for this date. A crash with
     # no public terminal receipt may resume only a reconciled exact account.
     if item.get('status') in ('FAILED','ENTRY_FAILED'):
      job.update(status='PLANNING_FAILED',error=item.get('error',repr(error)));break
     try:resume=stage_resume(folder,stage,day,parent)
     except Exception as reason:
      job.update(status='PLANNING_BLOCKED',error=repr(reason));item.update(status='BLOCKED',error=repr(reason));publish(state);break
   else:resume=None
   wait_resources(state,'PLANNING');state['phase']='PLANNING_SERIAL';atomic(c.ROOT/'PHASE.json',dict(lane='MAIN',UTC=now()))
   request=make(day,stage,lease,parent=parent,resume=resume)
   p,identity=launch(request);item=dict(status='RUNNING',PASS=False,root=request['case_root'],request=identity['request'],identity=identity)
   job['stages'][stage]=item;job['status']='PLANNING_RUNNING';state['workers']=[identity];publish(state)
   while p.poll() is None:
    item['progress']=optional(Path(request['case_root'])/c.CORE_STAGE[stage]/'progress.json');publish(state);time.sleep(5)
   state['workers']=[];path=Path(request['case_root'])/'RESULT.json';result=optional(path)
   item.update(process_exit=p.returncode,status='PASS' if p.returncode==0 and result.get('PASS') else 'FAILED',PASS=p.returncode==0 and result.get('PASS') is True,result=record(path) if path.exists() else None,error=result.get('error'))
   if not item['PASS']:
    job.update(status='PLANNING_FAILED',error=result.get('error','STAGE_NOT_FULL_OR_PROCESS_EXIT'));publish(state);break
   try:
    item['result']=completed(Path(request['case_root']),stage,day);parent=read(item['result']['path'])['core_result']
   except Exception as error:
    item.update(status='FAILED',PASS=False,error=repr(error));job.update(status='PLANNING_FAILED',error=repr(error));publish(state);break
   publish(state)
  else:freeze(job);publish(state)
 if not actual_barrier(state['jobs']):
  state.update(phase='PLANNING_FAILED_ACTUAL_HELD',workers=[],Actual_started=False);publish(state);return False
 freezes=[j['M4_freeze'] for j in state['jobs']];verify(freezes)
 value=dict(PASS=True,UTC=now(),freezes=freezes,days=list(c.DAYS),Actual_started_before_barrier=False,commit_sha=authority.validate()['commit_sha'])
 path=c.OPS/'ALL_31_M4_FROZEN.json'
 if path.exists():
  previous=read(path)
  if previous['freezes']!=freezes:raise ValueError('ALL_31_FROZEN_PLAN_DRIFT')
 else:atomic(path,value)
 return True

def actual(state,lease):
 if not actual_barrier(state['jobs']):raise PermissionError('ALL_31_M4_REQUIRED_BEFORE_ANY_ACTUAL_DISPATCH')
 barrier=read(c.OPS/'ALL_31_M4_FROZEN.json');verify(barrier['freezes'])
 if not barrier['PASS'] or barrier['freezes']!=[j['M4_freeze'] for j in state['jobs']]:raise PermissionError('EXACT_31_FROZEN_PLAN_BARRIER_REQUIRED')
 from .requests import make
 from v44_recovery_r038.cpu import reserve_pool
 placement=read(c.DOC/'CPU_PLACEMENT.json');running={};queue=[]
 for job in state['jobs']:
  item=job.get('actual')
  if item and item.get('status')=='RUNNING':
   path=Path(item['root'])/'RESULT.json';value=optional(path)
   if value.get('independent_audit'):
    verify([value['independent_audit']]);audit=read(value['independent_audit']['path'])
    verify([audit['raw'],audit['actual'],audit['Actual_current_AC']])
    item.update(status='PASS' if value.get('PASS') and audit.get('PASS') else 'FAILED',result=record(path))
  if item and item.get('status') in ('PASS','FAILED'):
   if item.get('result'):verify([item['result']])
   continue
  # A restarted Actual always creates an independent engine from source and
  # leaves its old native control queue and partial files untouched.
  queue.append(job)
 stats=state.setdefault('Actual_memory',dict(peak_process_tree_bytes=0,pilot_complete=False))
 atomic(c.ROOT/'PHASE.json',dict(lane='ACTUAL_PARALLEL',UTC=now(),max_workers=7,barrier=record(c.OPS/'ALL_31_M4_FROZEN.json')))
 with reserve_pool(placement,c.OPS,lease):
  while queue or running:
   for slot,(p,job,identity) in list(running.items()):
    size=resources.rss(identity);stats['peak_process_tree_bytes']=max(stats['peak_process_tree_bytes'],size)
    job['actual']['peak_process_tree_bytes']=max(job['actual'].get('peak_process_tree_bytes',0),size)
    if p.poll() is None:
     job['actual']['progress']=optional(Path(identity['root'])/'progress.json');continue
    path=Path(identity['root'])/'RESULT.json';value=optional(path)
    job['actual'].update(status='PASS' if p.returncode==0 and value.get('PASS') else 'FAILED',result=record(path) if path.exists() else None,process_exit=p.returncode,error=value.get('error'))
    if value.get('independent_audit'):
     audit=read(value['independent_audit']['path']);stats['pilot_complete']=audit.get('Actual120_input_and_output_axis_checked',False)
    del running[slot]
   for slot in range(1,8):
    if not queue or slot in running:continue
    resource=resources.admission(c.ROOT,phase='ACTUAL',running=len(running),peak=stats['peak_process_tree_bytes'],pilot_complete=stats['pilot_complete']);state['resources']=resource
    if not resource['admit']:break
    job=queue.pop(0);request=make(job['day'],'ACTUAL',lease,freeze=job['M4_freeze'],slot=slot)
    p,identity=launch(request);job['actual']=dict(status='RUNNING',root=request['case_root'],identity=identity);running[slot]=(p,job,identity)
   state.update(phase='ACTUAL_PARALLEL' if running else 'RESOURCE_WAIT_ACTUAL',workers=[v[2] for v in running.values()],Actual_started=True);publish(state);time.sleep(5)
 state.update(phase='REPORTING',workers=[]);publish(state)
 from .report import report
 report(state);state.update(phase='COMPLETE',PASS=all(j.get('actual',{}).get('status')=='PASS' for j in state['jobs']));publish(state);atomic(c.ROOT/'FINAL_RESULT.json',state)

def run():
 c.OPS.mkdir(parents=True,exist_ok=True)
 if (c.OPS/'USER_STOP.json').exists():return
 authority.validate()
 with single_owner():
  while True:
   state=optional(STATE) or initial()
   if state.get('phase')=='COMPLETE':publish(state);return
   active=orphans()
   if active:
    state.update(phase='WAIT_EXISTING_OWN_WORKERS',workers=active);publish(state);time.sleep(30);continue
   b2,pointer=b2_state()
   if b2.get('phase')!='COMPLETE':
    state.update(phase='WAIT_B2',B2=dict(phase=b2.get('phase'),state_path=str(pointer),jobs=[dict(day=j['day'],status=j['status']) for j in b2.get('jobs',[])]),workers=[]);publish(state);time.sleep(30);continue
   if state.get('phase')=='PLANNING_FAILED_ACTUAL_HELD':publish(state);time.sleep(30);continue
   gate=ready_receipt();state['B2_release_gate']=gate
   if not gate['ready']:state['phase']='WAIT_B2_RESOURCES';publish(state);time.sleep(30);continue
   try:
    from .bootstrap import base,equipment
    from .adapters import bindings
    from .archives import Store
    from .storage import install
    from v44.locks import coordinator
    store=Store()
    try:
     with bindings(),install(),store.read_scope(),coordinator(c.ROOT) as lease,equipment.scope():
      state['lease']=lease
      if planning(state,lease):actual(state,lease)
    finally:store.close()
   except BaseException as error:
    state.update(phase='SUPERVISOR_ERROR',error=repr(error),traceback=traceback.format_exc());publish(state);atomic(c.OPS/'ERROR.json',dict(UTC=now(),error=repr(error),traceback=traceback.format_exc()))
    # No silent restart of a failed Native account. A quiet heartbeat diagnoses
    # and seals a repair; completed stages and partial ledgers remain intact.
    return
   if state.get('phase')=='COMPLETE':return

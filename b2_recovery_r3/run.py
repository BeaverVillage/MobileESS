"""Reuse completed May23 M1, execute new Actual/Fresh, continue queued B2 dates."""
from pathlib import Path
from contextlib import ExitStack
from unittest.mock import patch
from types import FunctionType
import argparse,os,sys,time,subprocess,traceback
import psutil
sys.path.insert(0,'D:/v44_b2_iofix_r2_20261022')
import run as previous
from v44.common import read,record,verify,atomic,digest,now
from v44.locks import coordinator,exclusive_lock,alive,process_identity,worker_slot,EXTERNAL_LOCKS
from v44.execution import case_scope
from v44_recovery_r049 import weather as recovered
from v44_recovery_r029 import weather
from v44 import worker as science

CODE=Path(__file__).resolve().parent
REPO=CODE.parent
ROOT=previous.ROOT
HOME=ROOT/'CONTROLLERS/B2_WEATHER_R3_20261022'
AUTH=HOME/'AUTHORIZATION.json'
STATE=HOME/'STATE.json'
DAYS=previous.DAYS
PARENT=ROOT/'2025-05-23/B2/attempt002/M1'

def sources():
 return [record(p) for p in sorted(CODE.glob('*.py'))]+[record(REPO/'docs/B2_weather_recovery_r3.md'),record(REPO/'scripts/launch_b2_weather_r3.ps1')]

def authority(request=None):
 a=read(AUTH);previous.authority();verify(a['sources']+[a['prior_authority'],a['diagnosis'],a['validation']])
 if a['sources']!=sources():raise PermissionError('SEALED_B2_WEATHER_R3_SOURCE_REQUIRED')
 if request:
  day=request['day'];root=Path(request['case_root'])
  if day not in DAYS or request['arm']!='B2' or Path(request['campaign_root'])!=ROOT or root.parent!=ROOT/day/'B2':raise PermissionError('ONLY_AUTHORIZED_B2_MAY22_31')
  if request['weather_recovery_authorization']!=record(AUTH):raise PermissionError('EXPLICIT_B2_WEATHER_R3_AUTHORITY_REQUIRED')
  verify(request['sources'])
 return a

def boundary(request):
 authority(request);lease=request['lease']
 if alive(read(previous.STATE).get('lease')):raise PermissionError('PRIOR_COORDINATOR_MUST_BE_DEAD')
 if not alive(lease) or lease!=read(ROOT/'COORDINATOR_LEASE.json') or set(lease['external_locks'])!={str(p) for p in EXTERNAL_LOCKS}:raise PermissionError('LIVE_COORDINATOR_ALL_SIX_LOCKS_REQUIRED')
 return dict(protected_case_root=str(previous.old.ROOT),new_campaign_lease=lease)

def reuse_m1(parent,request):
 from v44.checkpoints import checked,assert_dead
 parent=Path(parent);assert_dead(parent);old=read(parent/'request.json')
 checked(parent/'COMPLETED_STAGE_CHECKPOINT.json',old,'COMPLETED')
 m=read(parent/'RESULT.json')
 if (old['day'],old['arm'],old['stage'])!=(request['day'],'B2','M1'):raise PermissionError('EXACT_DATED_M1_ONLY')
 if not (m['FULL_feasible'] and m['upper']['FULL_validated'] and m['allow_downstream'] and m['M_stage_execution_PASS']) or m.get('implementation_errors'):raise PermissionError('COMPLETED_FULL_M1_REQUIRED')
 model_root=parent
 if old.get('resume_parent'):
  model_root=Path(old['resume_parent']);restore=read(parent/'BINARY_RESTORE_RECEIPT.json')
  checked(model_root/'BINARY_STAGE_CHECKPOINT.json',old,'M_BINARY')
  if not restore['PASS'] or restore['Native_clock_reset'] or restore['checkpoint']!=record(model_root/'BINARY_STAGE_CHECKPOINT.json') or restore['case_sha']!=m['case_sha']:raise PermissionError('EXACT_RESTORED_M1_MODEL_REQUIRED')
 binding=read(model_root/'EQUIPMENT825_MODEL_BINDING.json');verify([binding['compiled_thermal']])
 if not binding['PASS'] or binding['source_sha']!=old['source_sha'] or binding['equipment_version']!=previous.old.equipment.VERSION or not binding['normalized_current_and_kVA_constraints_use_825']:raise PermissionError('EXACT_825_MODEL_REQUIRED')
 for n in ('K48_NATIVE_LEDGER.json','JOINT_NATIVE_LEDGER.json','RECONCILIATION.json'):
  if read(parent/n).get('inflight') is not None:raise PermissionError('UNRECONCILED_NATIVE_INFLIGHT')
 atomic(Path(request['case_root'])/'REUSED_COMPLETED_M1.json',dict(PASS=True,original_result=record(parent/'RESULT.json'),checkpoint=record(parent/'COMPLETED_STAGE_CHECKPOINT.json'),
  parent_sources=old['sources'],parent_source_sha=old['source_sha'],K48_Native_seconds=m['K48_Native_seconds'],Joint_Native_seconds=m['Joint_Native_seconds'],
  new_M1_Native_calls=0,Native_clock_reset=False,plan_sha=m['MESS_plan']['plan_sha']))
 return m

def audited(root,result,m1,mroot):
 # Preserve the original B2 conjunction and arithmetic. Only select its exact
 # reused M1 files and the new controller's authority/commit.
 old=previous.old.followup.audit
 def path(p):
  p=Path(p)
  return Path(mroot)/p.relative_to(root/'M1') if p.is_relative_to(root/'M1') else p
 fn=FunctionType(old.__code__,dict(old.__globals__,read=lambda p:read(path(p)),record=lambda p:record(path(p)),AUTH=AUTH),old.__name__)
 return fn(root,result,m1)

def case(request):
 from v44.campaign import stage_request
 root=Path(request['case_root']);root.mkdir(parents=True,exist_ok=False)
 who=dict(**process_identity(),day=request['day'],arm='B2',worker_slot=1)
 atomic(root/'START.json',dict(who,UTC=now(),sources=request['sources'],source_sha=request['source_sha']))
 atomic(root/'request.json',request)
 result=dict(PASS=False,status='FAILED',day=request['day'],arm='B2',equipment_version=previous.old.equipment.VERSION)
 def progress(stage):atomic(root/'progress.json',dict(who,UTC=now(),stage=stage,status='RUNNING'))
 with worker_slot(request['day'],'B2',1,root=ROOT,lease=request['lease']),case_scope(request,request['lease'],who),previous.old.equipment.scope():
  try:
   folder=ROOT/'references'/request['day'];progress('REFERENCE_R0_Q50');aidc=science.reference(request['day'],folder)
   parent=request.get('reuse_completed_M1')
   if parent:
    progress('REUSE_COMPLETED_M1_NO_NEW_NATIVE');m1=reuse_m1(parent,request);mroot=Path(parent)
   else:
    progress('M1');mroot=root/'M1';m1=science.m_stage(stage_request(request,'M1'),aidc)
   if not m1['allow_downstream']:raise RuntimeError(m1['status'])
   progress('ACTUAL120_AND_INDEPENDENT_FRESH');atomic(root/'ACTUAL_START.json',dict(who,UTC=now()))
   r=stage_request(request,'ACTUAL');r['MESS_result']=str(mroot/'RESULT.json')
   result.update(science.actual(r,folder,m1['MESS_plan']));atomic(root/'ORIGINAL_DRIVER_RESULT.json',result)
   # A driver exception must retain its original cause. Missing Fresh output is
   # not a physical FAIL and must not obscure the observation-loading failure.
   if result.get('error'):raise RuntimeError('ORIGINAL_ACTUAL_DRIVER_ERROR:'+result['error'])
   audit=audited(root,result,m1,mroot)
   result.update(PASS=audit['PASS'],status='COMPLETE' if audit['PASS'] else 'FAILED',
    independent_audit=record(root/'INDEPENDENT_FINAL_AUDIT.json'),hardware_revision=previous.old.equipment.VERSION,
    commit_sha=read(AUTH)['commit_sha'],reused_M1=bool(parent),M1_result=record(mroot/'RESULT.json'))
   progress(result['status'])
  except BaseException as e:result.update(PASS=False,status='FAILED',error=repr(e),traceback=traceback.format_exc())
  finally:result['finished_UTC']=now();atomic(root/'RESULT.json',result)
 return result

def worker(path):
 r=read(path);boundary(r)
 from v44_recovery_r038 import operations as inherited
 from v44_recovery_r039 import latency
 from v44_recovery_r029 import handover,conditional_campaign,integer_repair
 from v43_arms import reference
 base=previous.old.followup.base
 with base.bindings(),previous.iofix.install(),patch.object(weather,'loader',recovered.loader), \
  patch.object(handover,'require_boundary',lambda:boundary(r)),patch.object(reference,'project',base.project), \
  patch.object(integer_repair,'compile_run',base.live_compiler(integer_repair.compile_run)), \
  inherited.previous.install(),latency.install(lambda:boundary(r)),patch.object(conditional_campaign,'run_case',case):
  return inherited.base.worker(r)

def publish(state):
 state.update(UTC=now(),controller_home=str(HOME),state_path=str(STATE))
 atomic(STATE,state);atomic(ROOT/'IO_RECOVERY_STATUS.json',state);previous.old.publish_active(state)

def new_request(day,lease):
 pointer=ROOT/'requests'/f'{day}_B2.json'
 if pointer.exists():r=read(pointer)
 else:
  with previous.bindings():r=previous.old.followup.new_request(day,lease)
 for key in ('io_resume_M1_parent','resume_parent','resume_of','io_recovery_authority','sequence825_authorization'):r.pop(key,None)
 attempts=sorted((ROOT/day/'B2').glob('attempt[0-9][0-9][0-9]'))
 number=int(attempts[-1].name[-3:])+1 if attempts else 1
 r.update(case_root=str(ROOT/day/'B2'/f'attempt{number:03d}'),lease=lease,weather_recovery_authorization=record(AUTH))
 r['sources']=list({x['path']:x for x in r['sources']+sources()+[record(AUTH),record(recovered.SUPPLEMENT)]}.values());r['source_sha']=digest(r['sources'])
 if day=='2025-05-23':r['reuse_completed_M1']=str(PARENT)
 authority(r);return r

def run():
 authority();HOME.mkdir(parents=True,exist_ok=True)
 with exclusive_lock(HOME/'RUN.lock'):
  state=read(STATE) if STATE.exists() else read(previous.STATE)
  if alive(state.get('lease')):raise PermissionError('EXISTING_B2_OWNER_STILL_LIVE')
  for j in state['jobs']:
   if j.get('case_root') and alive(read(Path(j['case_root'])/'START.json')):raise PermissionError('SCIENTIFIC_WORKER_STILL_LIVE')
  if state.get('phase')=='COMPLETE':return
  preserved=read(AUTH)['preserved'];verify(preserved)
  with coordinator(ROOT) as lease:
   state.update(**process_identity(),lease=lease,phase='B2_WEATHER_R3_SERIAL_FULL_CASES',commit_sha=read(AUTH)['commit_sha']);publish(state)
   for job in state['jobs']:
    if job['status']=='PASS':continue
    # Existing failed scientific attempts are never silently recomputed. The
    # diagnosed May23 exception is the only admitted prior failed case.
    if job['status']=='FAILED' and job['day']!='2025-05-23':raise RuntimeError('UNDIAGNOSED_FAILED_DATE:'+job['day'])
    if job['status']=='RUNNING':raise RuntimeError('INTERRUPTED_WORKER_REQUIRES_CHECKPOINT_DIAGNOSIS:'+job['day'])
    r=new_request(job['day'],lease);path=HOME/'requests'/f"{job['day']}_B2.json";atomic(path,r)
    atomic(ROOT/'PHASE.json',dict(lane='B2',UTC=now(),max_workers=1))
    logs=HOME/'logs';logs.mkdir(exist_ok=True)
    env=dict(os.environ,PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',NUMEXPR_NUM_THREADS='1')
    with (logs/f"{job['day']}.out.log").open('ab') as out,(logs/f"{job['day']}.err.log").open('ab') as err:
     p=subprocess.Popen([sys.executable,'-B','-X','utf8','-u','-m','b2_recovery_r3.run','--case',str(path)],cwd=REPO,env=env,stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW)
    if job.get('result'):job['superseded_result']=job['result']
    job.update(status='RUNNING',pid=p.pid,case_root=r['case_root'],progress=None);job.pop('result',None);publish(state)
    while p.poll() is None:
     pp=Path(r['case_root'])/'progress.json';job['progress']=read(pp) if pp.exists() else None;publish(state);time.sleep(5)
    result=Path(r['case_root'])/'RESULT.json';value=read(result) if result.exists() else {}
    job.update(status='PASS' if p.returncode==0 and value.get('PASS') else 'FAILED',process_exit=p.returncode,result=record(result) if result.exists() else None);publish(state)
    verify(preserved)
    if p.returncode!=0 or not value or value.get('error'):raise RuntimeError('NEW_TECHNICAL_FAILURE_REQUIRES_DIAGNOSIS:'+job['day'])
   state.update(phase='COMPLETE',pending_retries=[],resume_pending=False,PASS=all(j['status']=='PASS' for j in state['jobs']));publish(state);atomic(HOME/'FINAL_RESULT.json',state)

def authorize(commit):
 if AUTH.exists():raise FileExistsError('IMMUTABLE_AUTHORITY_EXISTS')
 if read(HOME/'VALIDATION.json').get('PASS') is not True:raise PermissionError('PASSING_PREFLIGHT_REQUIRED')
 previous.authority();preserved=[]
 for job in read(previous.STATE)['jobs']:
  if not job.get('case_root'):continue
  root=Path(job['case_root'])
  for p in root.rglob('*.json'):
   if p.name in ('RESULT.json','ORIGINAL_DRIVER_RESULT.json','COMPLETED_STAGE_CHECKPOINT.json','K48_NATIVE_LEDGER.json','JOINT_NATIVE_LEDGER.json','RECONCILIATION.json'):preserved.append(record(p))
 atomic(AUTH,dict(UTC=now(),commit_sha=commit,sources=sources(),prior_authority=record(previous.AUTH),diagnosis=record(HOME/'DIAGNOSIS.json'),validation=record(HOME/'VALIDATION.json'),
  preserved=preserved,explicit_user_instruction='응 계속 작업하는데 지금 B2 실패있거든? 오류 해결해서 재개해.',scope='B2 May22-31 only; keep May22 PASS; reuse completed May23 M1; only Actual/Fresh replay May23; continue queued May24-31.',
  weather_policy='Existing verified same-time r049 supplement; original7200s max age; no interpolation or source mutation',physics_or_optimizer_changed=False))

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--run',action='store_true');p.add_argument('--case',type=Path);p.add_argument('--authorize');a=p.parse_args()
 try:
  if a.authorize:authorize(a.authorize)
  elif a.case:worker(a.case)
  elif a.run:run()
  else:p.error('explicit mode required')
 except BaseException as e:
  atomic(HOME/'ERROR.json',dict(UTC=now(),error=repr(e),traceback=traceback.format_exc()));raise

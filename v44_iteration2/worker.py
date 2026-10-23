"""One process, one date/stage, one immutable attempt and Native account."""
from pathlib import Path
from contextlib import ExitStack
from unittest.mock import patch
from types import FunctionType
import time,traceback,os
from . import config as c
from .io import read,record,verify,atomic,digest,now
from . import authority,adapters,storage
from .archives import Store
from .contracts import full_m,full_a
from .safety import alive,b2_state

def boundary(request):
 authority.validate(request);lease=request['lease']
 if not alive(lease) or lease!=read(c.ROOT/'COORDINATOR_LEASE.json'):raise PermissionError('LIVE_NEW_COORDINATOR_REQUIRED')
 if set(lease['external_locks'])!={str(p) for p in c.LOCKS}:raise PermissionError('ALL_ORIGINAL_OS_LOCKS_REQUIRED')
 release=read(c.OPS/'B2_RELEASE_PRESERVATION.json')
 if not release['ready'] or not release['OS_locks_verified_released']:raise PermissionError('B2_COMPLETE_RELEASE_REQUIRED')
 b2,_=b2_state()
 if b2.get('phase')!='COMPLETE' or alive(b2.get('lease',{})):raise PermissionError('B2_WAS_RESTARTED')
 return dict(protected_case_root=str(c.B2_ROOT),new_campaign_lease=lease)

def public_result(request,core,path,started):
 kind=request['iteration_stage'];day=request['day']
 if kind.startswith('M'):
  from .voltage_audit import verify_result
  full_m(core,day);voltage_proof=verify_result(core,kind)
 else:full_a(core,day)
 plan=core.get('MESS_plan',{})
 receipt=dict(PASS=True,day=day,arm='B3',stage=kind,core_stage=core['stage'],core_result=record(path),
  case_sha=core.get('case_sha',core.get('freeze',{}).get('sha256')),plan_sha=plan.get('plan_sha'),
  AIDC_reference=core.get('AIDC_reference'),Native_seconds=core.get('Native_seconds'),Native_calls=core.get('Native_calls',core.get('native_calls')),
  K48_Native_seconds=core.get('K48_Native_seconds'),Joint_Native_seconds=core.get('Joint_Native_seconds'),
  LB=core.get('Global_LB',core.get('LB')),UB=core.get('Global_UB',core.get('UB')),
  Gap=core.get('Global_Gap',core.get('certified_gap')),global_gap_certified=core.get('global_gap_certified'),
  original_FULL_PASS=True,voltage_band=list(c.band(kind)) if kind.startswith('M') else None,
  fixed_parent_stage=request['fixed_parent_stage'],fixed_parent=request['fixed_parent_receipt'],
  new_AIDC_FULL_optimization=kind.startswith('A'),B1_A1_reuse_path_used=False,
  equipment_version=c.EQUIPMENT,commit_sha=authority.validate()['commit_sha'],wall_seconds=time.monotonic()-started,finished_UTC=now())
 if kind.startswith('M'):receipt['actual_voltage_proof']=voltage_proof
 return receipt

def planning_case(request):
 from .bootstrap import equipment
 from v44 import worker,campaign
 from v44.daily import load_aidc
 from v44.execution import case_scope
 from v44.locks import worker_slot,process_identity
 stage=request['iteration_stage'];root=Path(request['case_root']);root.mkdir(parents=True,exist_ok=False)
 who=dict(**process_identity(),day=request['day'],arm='B3',worker_slot=1)
 atomic(root/'START.json',dict(who,UTC=now(),request=request))
 atomic(root/'progress.json',dict(who,UTC=now(),stage=stage,status='RUNNING'))
 started=time.monotonic();result=dict(PASS=False,day=request['day'],arm='B3',stage=stage)
 with worker_slot(request['day'],'B3',1,root=c.ROOT,lease=request['lease']),case_scope(request,request['lease'],who):
  try:
   r=campaign.stage_request(request,c.CORE_STAGE[stage]);r['iteration_stage']=stage
   resume_parent=request.get('stage_resume_parent')
   atomic(root/'request.json',request)
   if stage.startswith('M'):
    parent=read(request['fixed_parent_core']);verify([request['fixed_parent_receipt']])
    folder=Path(parent['AIDC_reference']['path']).parent;payload,_=load_aidc(folder,request['day'])
    r['Threads']=4
    if resume_parent:
     from .resume import m_request
     admission=m_request(resume_parent,r);atomic(root/'RESUME_ADMISSION.json',admission)
    core=adapters.execute_m(r,payload)
   else:
    parent=read(request['fixed_parent_core']);full_m(parent,request['day']);r['Threads']=1
    catalog=next(v for v in read(c.DOC/'BASELINE_CATALOG.json')['days'] if v['day']==request['day'])
    r.update(physical_domain_request=catalog['physical_domain_request'],physical_cache_case_proof=catalog['physical_cache_case_proof'],M1_result=request['fixed_parent_receipt'])
    r['fixed_parent_stage']=request['fixed_parent_stage'];r['fixed_parent_core']=request['fixed_parent_core'];r['fixed_parent_receipt']=request['fixed_parent_receipt']
    with adapters.new_a_scope(r),equipment.scope(),ExitStack() as stack:
     if resume_parent:
      from .resume import a_scope
      admission=stack.enter_context(a_scope(resume_parent,r));atomic(root/'RESUME_ADMISSION.json',admission)
     core=worker.a_stage(r,m1=parent)
   corepath=Path(r['root'])/'RESULT.json';result=public_result(request,core,corepath,started)
   from v44.checkpoints import checked
   with equipment.scope():
    checked(Path(r['root'])/'COMPLETED_STAGE_CHECKPOINT.json',read(Path(r['root'])/'request.json'),'COMPLETED')
   result['checkpoint']=record(Path(r['root'])/'COMPLETED_STAGE_CHECKPOINT.json')
  except BaseException as error:result.update(PASS=False,error=repr(error),traceback=traceback.format_exc(),finished_UTC=now())
  finally:atomic(root/'RESULT.json',result)
 return result

def actual_case(request):
 from .bootstrap import equipment
 from v44 import worker,campaign
 from v44.execution import case_scope
 from v44.locks import process_identity
 from v44_recovery_r038.cpu import actual_slot
 from v42_may_campaign_native90.preflight import native_zero
 from .audit import validate_actual
 barrier=read(c.OPS/'ALL_31_M4_FROZEN.json');verify(barrier['freezes'])
 if len(barrier['freezes'])!=31 or not barrier['PASS']:raise PermissionError('ALL_31_DAY_ACTUAL_BARRIER_REQUIRED')
 freeze=read(request['M4_freeze']['path']);verify(freeze['evidence'])
 if freeze['day']!=request['day'] or request['M4_freeze'] not in barrier['freezes']:raise ValueError('M4_DAY_OR_BARRIER_DRIFT')
 root=Path(request['case_root']);root.mkdir(parents=True,exist_ok=False)
 who=dict(**process_identity(),day=request['day'],arm='B3',worker_slot=1)
 atomic(root/'START.json',dict(who,UTC=now(),request=request));atomic(root/'ACTUAL_START.json',dict(who,UTC=now()))
 atomic(root/'progress.json',dict(who,UTC=now(),stage='ACTUAL_FRESH',status='RUNNING'))
 result=dict(PASS=False,day=request['day'],arm='B3',stage='ACTUAL')
 plan=full_m(read(freeze['M4_core']['path']),request['day'])
 placement=read(c.DOC/'CPU_PLACEMENT.json')
 with actual_slot(request,c.OPS,placement),case_scope(request,request['lease'],who),equipment.scope(),native_zero() as denied:
  try:
   r=campaign.stage_request(request,'ACTUAL');r['MESS_result']=freeze['M4_core']['path']
   result.update(worker.actual(r,Path(freeze['A4_reference']['path']).parent,plan))
   atomic(root/'ORIGINAL_DRIVER_RESULT.json',result)
   audit=validate_actual(root,request,freeze,result)
   result.update(PASS=bool(audit['PASS'] and not denied),independent_audit=record(root/'INDEPENDENT_FINAL_AUDIT.json'),new_Planning_optimization_calls_in_Actual=len(denied),commit_sha=authority.validate()['commit_sha'])
  except BaseException as error:result.update(PASS=False,error=repr(error),traceback=traceback.format_exc())
  finally:result.update(finished_UTC=now());atomic(root/'RESULT.json',result)
 return result

def scientific_case(request):
 if request['iteration_stage']=='ACTUAL':return actual_case(request)
 # The original r031 case wrapper installs this only after r029 compiled its
 # selective A2 worker. Preserve that same placement for new A3/A4.
 if request['iteration_stage'].startswith('A'):
  from v44_recovery_r031 import p1_expansion
  with p1_expansion.install():return planning_case(request)
 return planning_case(request)

def run(path):
 from .bootstrap import base
 from v44_recovery_r038 import operations as inherited
 from v44_recovery_r039 import latency
 from v44_recovery_r029 import handover,conditional_campaign,integer_repair,cpu_placement,weather
 from v44_recovery_r049 import weather as recovered_weather
 from v43_arms import reference
 request=read(path);boundary(request);store=Store()
 try:
  with adapters.bindings(),store.read_scope(),storage.install(),ExitStack() as stack:
   from .numerical import scope as numerical_scope
   stack.enter_context(base.numerical.scope());stack.enter_context(numerical_scope())
   stack.enter_context(patch.object(weather,'loader',recovered_weather.loader))
   stack.enter_context(patch.object(handover,'require_boundary',lambda:boundary(request)))
   stack.enter_context(patch.object(reference,'project',base.project))
   stack.enter_context(patch.object(integer_repair,'compile_run',base.live_compiler(integer_repair.compile_run)))
   stack.enter_context(inherited.previous.install());stack.enter_context(latency.install(lambda:boundary(request)))
   stack.enter_context(patch.object(conditional_campaign,'run_case',scientific_case))
   if request['iteration_stage']=='ACTUAL':
    from v44_recovery_r038.cpu import compute_scope
    plan=read(c.DOC/'CPU_PLACEMENT.json')
    stack.enter_context(patch.object(cpu_placement,'compute_cpu_scope',lambda n,receipt=None:compute_scope(request,n,receipt,plan)))
   return inherited.base.worker(request)
 finally:store.close()

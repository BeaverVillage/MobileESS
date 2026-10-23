"""Stage/parent/provenance adapters over the unchanged r043 scientific engines.

Public A3/A4 use the fixed-MESS A2 engine and NEW Solver searches; public
M2/M3/M4 use the M2 engine. Public labels are included in each M Case SHA.
No upstream FULL certificate, incumbent, bound or clock crosses Cases.
"""
from pathlib import Path
from contextlib import contextmanager,ExitStack
from contextvars import ContextVar
from unittest.mock import patch
from copy import deepcopy
import inspect,textwrap,linecache
import numpy as np
from . import config as c
from .io import read,record,verify,atomic,digest,now
from .contracts import full_m
ACTIVE=ContextVar('V44_ITERATION2_STAGE',default=None)

@contextmanager
def bindings():
 from .bootstrap import base
 from v44 import daily,inputs,public_inputs,checkpoints
 from v44 import svr12
 from v44_week2.operations import period
 from v44_recovery_r029 import a2_cache
 from v44_recovery_r035 import operations as raw35
 from v44_recovery_r036 import operations as raw36
 from v44_recovery_r037 import operations as raw37
 with base.bindings(),period(c.DAYS),ExitStack() as stack:
  from .history import verify_historical
  # Accepted parents retain their original controller receipts. Only exact
  # archived source bytes may resolve a historical receipt; data stays strict.
  stack.enter_context(patch.object(daily,'verify',verify_historical))
  stack.enter_context(patch.object(checkpoints,'verify',verify_historical))
  for module in (daily,inputs,public_inputs,a2_cache):stack.enter_context(patch.object(module,'DOC',c.DOC))
  for module in (inputs,public_inputs):stack.enter_context(patch.object(module,'DAYS',c.DAYS))
  native_runtime=c.ROOT/'NATIVE_RUNTIME'
  stack.enter_context(patch.object(svr12,'RUNTIME',native_runtime))
  # All live raw Current/Fresh audit and lossless chunk storage must belong to
  # this experiment, including globals captured by the inherited storage scopes.
  audit=native_runtime/'v43_planning_svr12_actual_v1/AC_AUDIT/svr11_revision01'
  for module in (raw35,raw36,raw37):stack.enter_context(patch.object(module,'RAW_ROOT',audit))
  yield

@contextmanager
def voltage(stage):
 from v42_native import voltage as v
 from v42_integrated import contract
 before=dict(v._MAPPING);lower,upper=c.band(stage)
 selected=v.Voltage('V44_ITERATION2_'+stage,lower,upper,lower**2,upper**2)
 original_authority=contract.physical_authority
 @contextmanager
 def physical_authority():
  # The inherited equipment context resets every Planning band. Apply the
  # requested M band AFTER that reset, before the original model is built.
  with original_authority() as receipt:
   if stage!='M4':v._MAPPING[v.Stage.M1]=selected;v._MAPPING[v.Stage.M2]=selected
   yield receipt
 # M4 retains the exact existing policy object, including its authority name.
 if stage=='M4':
  if (v.voltage_for(v.Stage.M2).lower_pu,v.voltage_for(v.Stage.M2).upper_pu)!=(.95,1.05):raise PermissionError('M4_ORIGINAL_POLICY_DRIFT')
 else:v._MAPPING[v.Stage.M2]=selected
 try:
  if v.voltage_for(v.Stage.ACTUAL)!=before[v.Stage.ACTUAL]:raise PermissionError('ACTUAL_AUTHORITY_LEAK')
  with patch.object(contract,'physical_authority',physical_authority):yield
 finally:v._MAPPING.clear();v._MAPPING.update(before)

def routed_build():
 from .bootstrap import CORE_RUNTIME
 from v44_recovery_r029.voltage_policy import require_handoff
 source=textwrap.dedent(inspect.getsource(CORE_RUNTIME))
 old="        require_a2(i,request['day'])"
 if source.count(old)!=1:raise ValueError('M_RUNTIME_PARENT_BOUNDARY_DRIFT')
 source=source.replace(old,"        _iteration2_require_handoff(i,request['day'])")
 ns=dict(CORE_RUNTIME.__globals__,_iteration2_require_handoff=require_handoff)
 name=__file__+'.runtime.generated';linecache.cache[name]=(len(source),None,source.splitlines(True),name)
 exec(compile(source,name,'exec'),ns);original=ns['build']
 def build(payload,request,progress=None):
  case=original(payload,request,progress)
  stage=request['iteration_stage']
  case.identity=dict(case.identity,experiment='V44_iteration2',iteration_stage=stage,
   fixed_parent_stage=c.PARENT[stage],equipment_version=c.EQUIPMENT,voltage_band=list(c.band(stage)))
  case.case_sha=digest(case.identity)
  atomic(case.output/'SCIENTIFIC_CASE_IDENTITY.json',dict(case_sha=case.case_sha,**case.identity))
  return case
 return build

def require_fixed_parent(result,day):
 context=ACTIVE.get()
 if not context or context['iteration_stage'] not in ('A3','A4'):raise PermissionError('ONLY_EXPLICIT_NEW_AIDC_STAGES')
 expected=c.PARENT[context['iteration_stage']]
 if context['fixed_parent_stage']!=expected or record(context['fixed_parent_core'])!=context['fixed_parent_receipt']:raise PermissionError('EXACT_PRECEDING_M_STAGE_REQUIRED')
 stored=read(context['fixed_parent_core'])
 if stored!=result:raise ValueError('FIXED_PARENT_RESULT_DRIFT')
 return deepcopy(full_m(result,day))

def domain_ownership(request,fresh_data,case_proof):
 """Generalize only accepted-A1 producer ownership, retaining the verifier tail."""
 context=ACTIVE.get()
 if not context or context['iteration_stage'] not in ('A3','A4'):raise PermissionError('A3_A4_FULL_DOMAIN_ONLY')
 proof=read(case_proof);verify(proof['sources']+[proof['result'],proof['cache']]+list(proof['inputs'].values()))
 if proof['schema']!='V44_ACCEPTED_A1_PHYSICAL_CACHE':raise ValueError('ORIGINAL_DOMAIN_PROOF_SCHEMA')
 parent_file=Path(proof['result']['path']);parent=read(parent_file);day=request['day']
 if any(parent.get(k)!=value for k,value in dict(day=day,arm='B1',stage='A1',PASS=True,FULL_feasible=True,independent_Global_LB_validated=True).items()) or not 0<=parent.get('certified_gap',1)<=.005:raise ValueError('ORIGINAL_DATED_A1_DOMAIN_CERTIFICATE')
 source=Path(request['_current_date_physical_cache']);output=Path(request['output']);inputs=Path(request['input_folder'])
 if source!=Path(parent.get('accepted_cache_output',str(parent_file.parent/'OUTPUT'))):raise ValueError('EXACT_DOMAIN_CACHE_SOURCE')
 if output!=Path(context['output']) or output.parent.name!='A2' or not output.resolve().is_relative_to(c.ROOT.resolve()):raise ValueError('ONLY_NEW_A3_A4_OUTPUT')
 cache=source/'STATIC/DOMAIN'/day/'PHYSICAL_DOMAIN_CACHE.json'
 if record(cache)!=proof['cache'] or request['_physical_cache_identity']!=proof['cache']:raise ValueError('DOMAIN_CACHE_SHA_DRIFT')
 manifest=c.DOC/'SEVEN_DAY_INPUT_MANIFEST.json';dated=next(r for r in read(manifest)['days'] if r['day']==day)
 for name,key in [('NATIVE_INPUT.json','native'),('WINDOWS.json','windows')]:
  actual=record(inputs/name)
  if any(actual[k]!=proof['inputs'][name][k] or actual[k]!=dated['files'][key][k] for k in ('bytes','sha256')):raise ValueError('DOMAIN_INPUT_ROSTER_DRIFT')
 prepared=read(source/'A_PREPARE_RECEIPT.json');domain=read(cache)
 if fresh_data[0]['day']!=day or not prepared['PASS'] or request['_expected_model_verification']!=prepared['verification'] or request['_expected_complete_domain_hashes']!=domain['complete_domain_hashes']:raise ValueError('FULL_JOB_DOMAIN_BINDING_DRIFT')
 return Path(request['campaign_root']),source,output,inputs,day,Path(case_proof),manifest,inputs/'NATIVE_INPUT.json'

@contextmanager
def new_a_scope(request):
 from v44 import a2
 from v44_recovery_r029 import a2_cache
 token=ACTIVE.set(request)
 try:
  with patch.object(a2,'require_m1',require_fixed_parent),patch.object(a2_cache,'ownership',domain_ownership):yield
 finally:ACTIVE.reset(token)

def routed_restore(original):
 """Restore Planning with the same original coefficients as its fresh builder."""
 source=textwrap.dedent(inspect.getsource(original))
 old="    from v42_svr11.model import load_coefficients\n    coefficients=load_coefficients(read(payload['bundle']['electrical_certificate']['path']),request['day'])"
 new="    from v42_pr134_b1.native import original_coefficients_for_day\n    import v42_may01.prepare as original_planning\n    from v42_temporal.native import load_power\n    certificate,_,_,_=load_power(payload['bundle'])\n    coefficients=original_coefficients_for_day(original_planning,certificate,request['day'])"
 if source.count(old)!=1:raise ValueError('PLANNING_RESTORE_COEFFICIENT_SOURCE_BOUNDARY_DRIFT')
 source=source.replace(old,new)
 source=source.replace("read(payload['bundle']['electrical_certificate']['path'])['output']['path']", "read(payload['bundle']['electrical_certificate']['path'])['outputs']['planning_coefficients']['path']")
 source=source.replace("case._v43_coefficient_metadata={k:z[k].copy() for k in ('node_names','branch_names','transformer_ratings')}","case._v43_coefficient_metadata={k:z[k].copy() for k in ('node_names','branch_names')}\n        case._v43_coefficient_metadata['transformer_ratings']=np.asarray(coefficients[0].transformer_ratings)")
 ns=dict(original.__globals__);name=__file__+'.restore.generated'
 linecache.cache[name]=(len(source),None,source.splitlines(True),name)
 exec(compile(source,name,'exec'),ns);return ns['restore']

def execute_m(request,payload):
 from .bootstrap import CORE_M,equipment
 from v44 import runtime,q250_m4_v2 as q,m_restore
 from v44_recovery_r029.thread_policy import build_scope
 from v44_recovery_r029.cpu_placement import compute_cpu_scope
 from .voltage_audit import check_rows,check_plan
 from v44.checkpoints import seal_stage
 ids=set();out=Path(request['output']);built={};original_bind=q.bind_case;original_restore=routed_restore(m_restore.restore)
 def bind(case,req):
  case=original_bind(case,req)
  check_rows(case,request['iteration_stage']);built['case']=case
  return case
 def restore(*args,**kwargs):
  case=original_restore(*args,**kwargs)
  check_rows(case,request['iteration_stage']);built['case']=case
  return case
 with patch.object(runtime,'build',routed_build()),patch.object(q,'bind_case',bind),patch.object(m_restore,'restore',restore),voltage(request['iteration_stage']),equipment.scope(),q.m_threads(request) as params,q.q_domain(),build_scope(ids),compute_cpu_scope(4) as cpu:
  result=CORE_M(request,payload)
  # Original failure cannot be replaced by a previous plan or a diagnostic PASS.
  full_m(result,request['day'])
  if 'case' not in built:raise ValueError('ITERATION2_VOLTAGE_MATRIX_NOT_AUDITED')
  check_plan(built['case'],payload,result['MESS_plan'],request['iteration_stage'])
  result.update(iteration2_voltage_rows=record(out/'ITERATION2_FULL_VOLTAGE_ROWS.json'),
   iteration2_voltage_plan=record(out/'ITERATION2_PLAN_VOLTAGE.json'))
  atomic(out/'RESULT.json',result)
  seal_stage(out,read(out/'request.json'),result)
  atomic(out/'ITERATION2_POLICY.json',dict(PASS=True,UTC=now(),public_stage=request['iteration_stage'],core_stage='M2',
   voltage_band=list(c.band(request['iteration_stage'])),parameters=params,cpu=cpu,equipment=c.EQUIPMENT,
   fallback_plan_used=False,source_algorithm_changed=False,coefficient_worker_thread_ids=sorted(ids)))
  return result

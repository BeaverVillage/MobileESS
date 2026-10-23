"""Native-zero regressions of sequencing, stage ownership and physical gates."""
import unittest,tempfile,json,zipfile,threading,hashlib,copy,time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from contextlib import contextmanager
from v44_iteration2 import config as c
from v44_iteration2.io import atomic,read,record,digest
from v44_iteration2 import contracts,archives,adapters,authority,requests,resources

def mresult(day='2025-05-01'):
 p=dict(case_sha='new-m-case',P_sign='POSITIVE_GRID_INJECTION_Pdis_MINUS_Pch',time_axis=list(range(96)),P_kW={u:[0.]*96 for u in c.FLEET})
 p['plan_sha']=digest(p)
 return dict(day=day,arm='B3',stage='M2',FULL_feasible=True,upper=dict(FULL_validated=True),M_stage_execution_PASS=True,allow_downstream=True,case_sha=p['case_sha'],MESS_plan=p)

class Contracts(unittest.TestCase):
 def test_ready_subset_barrier_requires_all31_terminal_and_exact_freezes(self):
  rows=[dict(day=d,status='PLANNING_FAILED',stages={}) for d in c.DAYS]
  rows[2].update(status='PLANNING_PASS',M4_freeze={'path':'exact'},stages=dict(M4=dict(PASS=True)))
  b=dict(PASS=True,all_31_Planning_terminal=True,days=list(c.DAYS),ready_days=[rows[2]['day']],freezes=[rows[2]['M4_freeze']])
  self.assertTrue(contracts.ready_barrier(b,rows));self.assertEqual(contracts.actual_ready(rows),[rows[2]])
  rows[-1]['status']='QUEUED';self.assertFalse(contracts.ready_barrier(b,rows));rows[-1]['status']='PLANNING_FAILED'
  self.assertFalse(contracts.ready_barrier(dict(b,freezes=[]),rows))
 def test_four_unit_contract_and_no_old_A_optimum(self):
  result=mresult();contracts.full_m(result,'2025-05-01');bad=copy.deepcopy(result);bad['MESS_plan']['P_kW']['MESS05']=[0.]*96;bad['MESS_plan']['plan_sha']=digest({k:v for k,v in bad['MESS_plan'].items() if k!='plan_sha'})
  with self.assertRaises(ValueError):contracts.full_m(bad,'2025-05-01')
  a=dict(day='2025-05-01',arm='B3',PASS=True,FULL_feasible=True,independent_Global_LB_validated=True,certified_gap=.001,Native_seconds=0)
  with self.assertRaisesRegex(ValueError,'SOLVER_CALLS'):contracts.full_a(a,'2025-05-01')
  a['Native_seconds']=10;contracts.full_a(a,'2025-05-01');a['old_point_bound_clock_loaded']=True
  with self.assertRaises(ValueError):contracts.full_a(a,'2025-05-01')

 def test_all31_barrier_not_partial_or_duplicate(self):
  rows=[dict(day=d,status='PLANNING_PASS',M4_freeze={'path':'verified'},stages=dict(M4=dict(PASS=True))) for d in c.DAYS]
  self.assertTrue(contracts.actual_barrier(rows));self.assertFalse(contracts.actual_barrier(rows[:-1]));rows[-1]['day']=rows[0]['day'];self.assertFalse(contracts.actual_barrier(rows))

 def test_zero_workers_is_not_B2_completion(self):
  jobs=[dict(day=f'2025-05-{n:02d}',arm='B2',status='PASS',result={'path':'receipt'}) for n in range(22,32)]
  s=dict(phase='RUNNING',jobs=jobs);self.assertFalse(contracts.b2_terminal(s,[],[]));s['phase']='COMPLETE';self.assertTrue(contracts.b2_terminal(s,[],[]))
  for key,value in [('pending_retries',['May23']),('resume_pending',True)]:
   self.assertFalse(contracts.b2_terminal(dict(s,**{key:value}),[],[]))
  self.assertFalse(contracts.b2_terminal(s,[dict(pid=1)],[]));self.assertFalse(contracts.b2_terminal(s,[],['ledger']))

 def test_fresh_requires_all120_and_checks_terminal_kVA_voltage_current(self):
  from v44_iteration2.bootstrap import equipment
  from final_audit import physical
  p=dict(all_original_and_added_axes_checked=True,nodes=[dict(voltage_pu=1.)],currents=[dict(element='line.x',current_A=9.,NormalAmps=10.,loading_pu=.9)],transformers=[dict(element='transformer.mess_idc01',kVA=742.5,rating_kVA=825.,loading_pu=.9)])
  raw=dict(physical_steps=[dict(slot=i,PASS=True,converged=True,full_physical=copy.deepcopy(p),time_control=dict(PASS=True),SVR_devices=dict(hardware_PASS=True)) for i in range(120)],Source_Initial_State_independent=True,Planning_tap_queue_transfer=0,Native_TIME_queue_processed=True,midnight_continuity=dict(PASS=True))
  self.assertTrue(physical(raw)['PASS'])
  raw['physical_steps'][0]['full_physical']['nodes'][0]['voltage_pu']=1.06;self.assertFalse(physical(raw)['PASS']);raw['physical_steps'][0]['full_physical']['nodes'][0]['voltage_pu']=1.
  raw['physical_steps'][119]['full_physical']['transformers'][0].update(kVA=830.,loading_pu=830/825);self.assertFalse(physical(raw)['PASS'])
  with self.assertRaises(ValueError):physical(dict(raw,physical_steps=raw['physical_steps'][24:]))

 def test_actual_up_to7_without_pilot_or_RAM_gate_with_disk_guard(self):
  G=2**30
  with patch.object(resources.psutil,'virtual_memory',return_value=SimpleNamespace(total=32*G,available=30*G)),patch.object(resources.shutil,'disk_usage',return_value=SimpleNamespace(free=40*G)):
   self.assertTrue(resources.admission('D:/',phase='ACTUAL')['admit']);self.assertTrue(resources.admission('D:/',phase='ACTUAL',running=1)['admit'])
   self.assertFalse(resources.admission('D:/',phase='ACTUAL',running=7,pilot_complete=True)['admit']);self.assertTrue(resources.admission('D:/',phase='ACTUAL',running=6,pilot_complete=True)['admit'])
  with patch.object(resources.psutil,'virtual_memory',return_value=SimpleNamespace(total=32*G,available=7*G)),patch.object(resources.shutil,'disk_usage',return_value=SimpleNamespace(free=40*G)):
   self.assertTrue(resources.admission('D:/',phase='ACTUAL',pilot_complete=True)['admit'])
   self.assertFalse(resources.admission('D:/',phase='PLANNING')['admit'])
  with patch.object(resources.psutil,'virtual_memory',return_value=SimpleNamespace(total=32*G,available=30*G)),patch.object(resources.shutil,'disk_usage',return_value=SimpleNamespace(free=G)):
   self.assertFalse(resources.admission('D:/',phase='ACTUAL')['admit'])

class ArchiveIO(unittest.TestCase):
 def test_new_dated_index_and_equipment_member_are_read_without_extraction(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);old=root/'old';eq=root/'equipment';camp=old/'campaign006_may15_21';camp.mkdir(parents=True);day='2025-05-15';logical=camp/day/'B3/attempt001/RESULT.json';extra=eq/'campaign'/day/'B2/attempt001/RESULT.json';raw=b'{"PASS":true}';archive=root/'daily.zip'
   items=[dict(path=day+'/B3/attempt001/RESULT.json',bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest()),dict(path='equipment_versions/test.json',logical_path=str(extra),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())]
   manifest=dict(day=day,source=str(camp/day),campaign=str(camp),source_roots=[str(camp/day),str(eq/'campaign'/day)],files=items)
   with zipfile.ZipFile(archive,'w') as z:
    for item in items:z.writestr(item['path'],raw)
    z.writestr('_ARCHIVE_MANIFEST.json',json.dumps(manifest))
   atomic(camp/'ARCHIVED_RESULTS_20250515_24.json',dict(days=[dict(day=day,source=str(camp/day),archive=str(archive))]))
   with patch.object(c,'OLD',old),patch.object(c,'B2_ROOT',eq/'new'):
    store=archives.Store()
    try:
     self.assertEqual(store.read(logical),dict(PASS=True));self.assertEqual(store.read(extra),dict(PASS=True));self.assertFalse(logical.exists());self.assertFalse(extra.exists())
    finally:store.close()

 def test_verified_read_alias_protects_original_writes_and_detects_tamper(self):
  with tempfile.TemporaryDirectory(dir=c.ROOT) as folder:
   root=Path(folder);old=root/'old';logical=old/'2025-05-01/B3/attempt001/RESULT.json';raw=b'{"PASS":true}\n';member='2025-05-01/B3/attempt001/RESULT.json';zpath=root/'source.zip'
   with zipfile.ZipFile(zpath,'w') as z:z.writestr(member,raw)
   z=zipfile.ZipFile(zpath);store=archives.Store.__new__(archives.Store);store._lock=threading.RLock();store.zips={'day':z};store.entries={archives.key(logical):(dict(source=str(old/'2025-05-01')),z,dict(path=member,bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest()))}
   try:
    with patch.object(c,'ROOT',root/'new'),patch.object(c,'campaign',lambda d:old):
     (root/'new').mkdir()
     with store.read_scope():
      self.assertTrue(logical.is_file());self.assertEqual(json.loads(logical.read_text()),dict(PASS=True))
      with self.assertRaises(PermissionError):logical.write_text('false')
     self.assertFalse(logical.exists());target=store.materialize(logical);target.write_bytes(b'changed')
     with self.assertRaisesRegex(ValueError,'VIEW_DRIFT'):store.materialize(logical)
   finally:store.close()

class StageRouting(unittest.TestCase):
 def test_every_inherited_raw_audit_root_is_owned_and_restored(self):
  from v44_iteration2.bootstrap import base
  from v44 import svr12
  from v44_recovery_r035 import operations as r35
  from v44_recovery_r036 import operations as r36
  from v44_recovery_r037 import operations as r37
  before=[svr12.RUNTIME,r35.RAW_ROOT,r36.RAW_ROOT,r37.RAW_ROOT]
  with adapters.bindings():
   for path in [svr12.RUNTIME,r35.RAW_ROOT,r36.RAW_ROOT,r37.RAW_ROOT]:self.assertTrue(path.is_relative_to(c.ROOT))
  self.assertEqual(before,[svr12.RUNTIME,r35.RAW_ROOT,r36.RAW_ROOT,r37.RAW_ROOT])
 def test_stage_local_voltage_and_original_M4_actual_policy_restoration(self):
  from v44_iteration2.bootstrap import base
  from v42_native import voltage as v
  before=dict(v._MAPPING)
  for stage,band in [('M2',(.955,1.045)),('M3',(.955,1.045)),('M4',(.95,1.05))]:
   with adapters.voltage(stage):
    policy=v.voltage_for(v.Stage.M2);self.assertEqual((policy.lower_pu,policy.upper_pu),band);self.assertEqual(v.voltage_for(v.Stage.ACTUAL),before[v.Stage.ACTUAL])
   self.assertEqual(v._MAPPING,before)

 def test_M_case_uses_honest_A2_parent_and_distinct_public_SHA_without_Native(self):
  from v44_iteration2.bootstrap import CORE_RUNTIME
  with tempfile.TemporaryDirectory(dir=c.ROOT) as folder,adapters.bindings():
   parent=dict(day='2025-05-01',arm='B3',stage='A2',PASS=True,FULL_feasible=True,P2_calls=0,certified_gap=.001,independent_Global_LB_validated=True,finished_UTC='finished',aidc_anchor='newA')
   payload=dict(identity=parent,bundle=dict(day='2025-05-01'))
   def fake(payload,request,progress=None):return SimpleNamespace(identity=dict(aidc_anchor='newA'),output=Path(folder),mess_stage_budget_seconds=900.)
   hashes=[]
   with patch.dict(CORE_RUNTIME.__globals__,_build=fake):
    for stage in ('M2','M3','M4'):
     result=adapters.routed_build()(payload,dict(day='2025-05-01',arm='B3',stage='M2',iteration_stage=stage))
     hashes.append(result.case_sha);self.assertEqual(result.identity['voltage_band'],list(c.band(stage)))
   self.assertEqual(len(set(hashes)),3)

 def test_A3_fixed_parent_accepts_only_exact_new_M2(self):
  with tempfile.TemporaryDirectory(dir=c.ROOT) as folder:
   p=Path(folder)/'M2.json';m=mresult();atomic(p,m);request=dict(iteration_stage='A3',fixed_parent_stage='M2',fixed_parent_core=str(p),fixed_parent_receipt=record(p))
   with adapters.new_a_scope(request):
    self.assertEqual(adapters.require_fixed_parent(m,'2025-05-01')['plan_sha'],m['MESS_plan']['plan_sha'])
    with self.assertRaises(ValueError):adapters.require_fixed_parent(dict(m,case_sha='wrong'),'2025-05-01')

 def test_new_A_domain_ownership_retains_original_complete_job_proofs(self):
  row=read(c.DOC/'BASELINE_CATALOG.json')['days'][-1]
  with tempfile.TemporaryDirectory(dir=c.ROOT) as folder:
   output=Path(folder)/'A2/OUTPUT';request=dict(row['physical_domain_request'],output=str(output));context=dict(iteration_stage='A4',output=str(output))
   with adapters.new_a_scope(context):
    answer=adapters.domain_ownership(request,[dict(day=row['day'])],row['physical_cache_case_proof']['path'])
   self.assertEqual(answer[2],output);self.assertEqual(answer[4],row['day'])
   with adapters.new_a_scope(context):
    with self.assertRaises(ValueError):adapters.domain_ownership(request,[dict(day='2025-05-01')],row['physical_cache_case_proof']['path'])

 def test_actual_worker_entry_uses_current_canonical_sources_and_same_time_weather(self):
  # Exercise all installed original worker-entry scopes; replace only the
  # scientific case body with observation/policy checks (no model or DSS).
  from v44_iteration2 import worker
  from v44_iteration2.bootstrap import base
  from v44_recovery_r029 import conditional_campaign
  reference=c.DOC/'USER_REQUEST.txt';real_record=requests.record
  seen=[]
  def probe(request):
   from v43_actual.observations import load_observations
   from v44.daily import day_inputs
   from v44_recovery_r029 import phase_stability
   self.assertTrue(issubclass(phase_stability.StableNative,base.numerical.UnpresolvedNative))
   if request['iteration_stage']=='A3':
    from v44 import worker as original_worker
    self.assertEqual(original_worker.a_stage.__module__,'v44_recovery_r031.p1_expansion')
   begin=request['axis']['issue_seconds'];bundle=Path(day_inputs(request['day'])['actual_bundle']);obs=load_observations(begin=begin,end=begin+120*900,bundle=bundle)
   for t in range(121):obs.at(begin+900*t,observed_now=begin+900*t)
   seen.append(True);return dict(PASS=True,Native_calls=0)
  for stage in ('ACTUAL','A3','M2'):
   with adapters.bindings(),patch.object(requests,'validate',lambda q:None),patch.object(requests,'record',side_effect=lambda p:real_record(reference) if Path(p)==c.OPS/'AUTHORIZATION.json' else real_record(p)):
    q=requests.make('2025-05-23',stage,dict(pid=1),freeze=dict(path='test'),slot=1,parent=real_record(reference))
   for r in q['sources']:self.assertEqual(Path(r['path']).resolve(),Path(r['path']))
   with tempfile.TemporaryDirectory(dir=c.ROOT) as folder:
    q['case_root']=str(Path(folder)/'ENTRY_ONLY');p=Path(folder)/'request.json';atomic(p,q)
    with patch.object(worker,'boundary',lambda q:dict(protected_case_root='D:/protected')),patch.object(worker,'actual_case',probe),patch.object(worker,'planning_case',probe):
     result=worker.run(p)
   self.assertTrue(result['PASS'])
  self.assertEqual(seen,[True,True,True])

class CheckpointRepair(unittest.TestCase):
 def test_recovered_parent_accepts_only_explicitly_pinned_previous_authority(self):
  with tempfile.TemporaryDirectory(dir=c.ROOT) as folder:
   root=Path(folder);core=root/'2025-05-01/B3/attempt001/M2/RESULT.json';atomic(core,{})
   old=root/'old_authority.json';atomic(old,dict(version='previous'));previous=record(old)
   auth=root/'OPS/AUTHORIZATION.json';atomic(auth,dict(compatible_previous_authorizations=[previous]))
   atomic(core.parent/'request.json',dict(day='2025-05-01',arm='B3',iteration_stage='M2',equipment_version=c.EQUIPMENT,iteration2_authorization=previous))
   atomic(core.parent.parent/'RESULT.json',dict(PASS=True,core_result=record(core),stage='M2'))
   request=dict(iteration_stage='A3',day='2025-05-01',fixed_parent_receipt=record(core),fixed_parent_core=str(core),fixed_parent_stage='M2',iteration2_authorization=record(auth))
   with patch.object(c,'ROOT',root),patch.object(c,'OPS',auth.parent),patch('v44_iteration2.voltage_audit.verify_result',return_value={}):
    authority.parent_authority(request)
    atomic(core.parent.parent/'RESULT.json',dict(PASS=True,core_result=record(core),stage='M2',error='old checkpoint failure'))
    with self.assertRaises(PermissionError):authority.parent_authority(request)
    atomic(core.parent.parent/'RECOVERED_COMPLETED_RESULT.json',dict(PASS=True,core_result=record(core),stage='M2'))
    authority.parent_authority(request)
    atomic(auth,dict(compatible_previous_authorizations=[]))
    with self.assertRaises(PermissionError):authority.parent_authority(request)

 def test_error_public_receipt_is_recovered_without_checkpoint_key_error(self):
  from v44_iteration2 import supervisor as s,worker,history
  with tempfile.TemporaryDirectory(dir=c.ROOT) as folder:
   root=Path(folder);core=root/'M2';core.mkdir()
   atomic(core/'request.json',dict(source_sha='original-source'));atomic(root/'request.json',{})
   atomic(core/'RESULT.json',mresult());atomic(core/'COMPLETED_STAGE_CHECKPOINT.json',{})
   atomic(root/'RESULT.json',dict(PASS=True,error='old hardware scope failure'))
   before=(root/'RESULT.json').read_bytes()
   with patch.object(history,'checked_completed',return_value={}),patch('v44_iteration2.voltage_audit.verify_result',return_value={}),patch.object(worker,'public_result',return_value=dict(PASS=True,core_result=record(core/'RESULT.json'))):
    receipt=s.completed(root,'M2','2025-05-01')
   recovered=read(receipt['path']);self.assertEqual(recovered['new_resume_Native_calls'],0)
   self.assertIn('checkpoint',recovered);self.assertEqual((root/'RESULT.json').read_bytes(),before)

 def test_completed_checkpoint_keeps_825_hardware_outside_execution_scope(self):
  from v44_iteration2.bootstrap import equipment
  from v44_iteration2.history import checked_completed
  from v44 import checkpoints,svr12
  with tempfile.TemporaryDirectory(dir=c.ROOT) as folder:
   root=Path(folder);result=root/'RESULT.json';atomic(result,dict(PASS=True))
   request=dict(day='2025-05-01',arm='B3',stage='M2',source_sha='test',case_root=str(root),sources=[])
   before=svr12.HARDWARE
   with equipment.scope():
    saved=checkpoints.envelope(request,'COMPLETED',[record(result)])
    self.assertEqual(saved['hardware']['path'],record(c.PROFILE/'equipment/HARDWARE.json')['path'])
   self.assertEqual(svr12.HARDWARE,before)
   path=root/'COMPLETED_STAGE_CHECKPOINT.json';atomic(path,saved)
   self.assertEqual(checked_completed(path,request)['key'],saved['key'])
   self.assertEqual(svr12.HARDWARE,before)
   result.write_text('{}')
   with self.assertRaises(ValueError):checked_completed(path,request)

 def test_historical_source_receipts_require_exact_saved_bytes(self):
  from v44_iteration2.history import verify_historical
  with tempfile.TemporaryDirectory(dir=c.ROOT) as folder:
   root=Path(folder);old=root/'old.py';old.write_text('old');receipt=record(old)
   snapshot=root/'snapshot.py';snapshot.write_bytes(old.read_bytes())
   manifest=root/'REPAIR_test/HISTORICAL_SOURCES.json'
   atomic(manifest,dict(files=[dict(original=receipt,snapshot=record(snapshot))]))
   atomic(root/'AUTHORIZATION.json',dict(historical_source_manifests=[record(manifest)]))
   old.write_text('new')
   with patch.object(c,'OPS',root):
    verify_historical([receipt]);snapshot.write_text('changed')
    with self.assertRaises(ValueError):verify_historical([receipt])

 def test_worker_failure_after_public_result_cannot_leave_PASS_true(self):
  from v44_iteration2 import worker
  from v44_iteration2.bootstrap import equipment
  from v44 import worker as original,campaign,daily,execution,locks,checkpoints,svr12
  from contextlib import nullcontext
  with tempfile.TemporaryDirectory(dir=c.ROOT) as folder:
   root=Path(folder);parent=root/'parent.json';atomic(parent,dict(AIDC_reference=dict(path=str(root/'AIDC_REFERENCE.json'))))
   case=root/'attempt';request=dict(day='2025-05-01',iteration_stage='M2',case_root=str(case),lease={},fixed_parent_core=str(parent),fixed_parent_receipt=record(parent))
   def stage_request(*args):
    core=case/'M2';core.mkdir();atomic(core/'request.json',{})
    return dict(root=str(core))
   def checked(*args):
    self.assertEqual(svr12.HARDWARE,c.PROFILE/'equipment')
    raise ValueError('synthetic checkpoint verification failure')
   with patch.object(locks,'worker_slot',lambda *a,**kw:nullcontext()),patch.object(locks,'process_identity',lambda:dict(pid=1,process_created=1)),patch.object(execution,'case_scope',lambda *a:nullcontext()),patch.object(campaign,'stage_request',side_effect=stage_request),patch.object(daily,'load_aidc',return_value=({},None)),patch.object(adapters,'execute_m',return_value={}),patch.object(worker,'public_result',return_value=dict(PASS=True)),patch.object(checkpoints,'checked',side_effect=checked):
    result=worker.planning_case(request)
   self.assertFalse(result['PASS']);self.assertIn('synthetic checkpoint',result['error']);self.assertNotIn('checkpoint',result)

class SupervisorOrdering(unittest.TestCase):
 def exercise(self,root,fail=None,explode=False):
  from v44_iteration2 import supervisor as s
  real_read=s.read;calls=[];counts={};state=s.initial();catalogue=[]
  for day in c.DAYS:
   p=root/'original'/day/'A2/RESULT.json';atomic(p,{})
   catalogue.append(dict(day=day,A1='oldA1',M1='oldM1',A2=str(p.parent),evidence=[record(p)]))
  def make(day,stage,lease,**kw):
   if explode and (day,stage)==fail:raise RuntimeError('synthetic request failure')
   counts[day]=counts.get(day,0)+1
   return dict(day=day,iteration_stage=stage,case_root=str(root/day/'B3'/f'attempt{counts[day]:03d}'))
  def launch(q):
   calls.append((q['day'],q['iteration_stage']));p=Path(q['case_root']);p.mkdir(parents=True)
   passed=(q['day'],q['iteration_stage'])!=fail;atomic(p/'CORE.json',{})
   atomic(p/'RESULT.json',dict(PASS=passed,core_result=record(p/'CORE.json'),error=None if passed else 'synthetic FULL rejection'))
   atomic(p/'request.json',q)
   return SimpleNamespace(poll=lambda:0,returncode=0),dict(pid=1,process_created=1,root=str(p),request=record(p/'request.json'))
  def seal(job):
   p=root/job['day']/'M4_FREEZE.json';atomic(p,{})
   job.update(status='PLANNING_PASS',M4_freeze=record(p))
  def selected(p):return dict(days=catalogue) if Path(p)==c.DOC/'BASELINE_CATALOG.json' else real_read(p)
  with patch.object(c,'ROOT',root),patch.object(c,'OPS',root/'OPS'),patch.object(authority,'validate',lambda request=None:dict(commit_sha='test')),patch.object(s,'read',selected),patch.object(requests,'make',make),patch.object(s,'launch',launch),patch.object(s,'completed',lambda folder,stage,day:record(Path(folder)/'RESULT.json')),patch.object(s,'freeze',seal),patch.object(s,'publish',lambda state:None),patch.object(s,'wait_resources',lambda *a,**kw:None):
   passed=s.planning(state,{})
   if passed:
    before=len(calls);self.assertTrue(s.planning(state,{}));self.assertEqual(len(calls),before,'completed stages must not solve again')
  return state,calls,passed

 def test_serial31_all_new_stages_and_resume_without_repeated_solves(self):
  with tempfile.TemporaryDirectory(dir=c.ROOT) as folder:
   state,calls,passed=self.exercise(Path(folder))
   self.assertTrue(passed);self.assertEqual(calls,[(d,s) for d in c.DAYS for s in c.STAGES]);self.assertTrue(contracts.actual_barrier(state['jobs']))

 def test_one_failed_stage_continues_through31_then_actual_only_ready_dates(self):
  with tempfile.TemporaryDirectory(dir=c.ROOT) as folder:
   state,calls,passed=self.exercise(Path(folder),('2025-05-02','A3'))
   self.assertTrue(passed);self.assertIn(('2025-05-31','M4'),calls);self.assertNotIn(('2025-05-02','M3'),calls)
   barrier=read(Path(folder)/'OPS/ALL_31_PLANNING_FINISHED.json')
   self.assertEqual(len(barrier['freezes']),30);self.assertNotIn('2025-05-02',barrier['ready_days'])
   self.assertEqual(len(contracts.actual_ready(state['jobs'])),30)

 def test_actual_entry_rejects_any_missing_M4_before_launch(self):
  from v44_iteration2 import supervisor as s
  with patch.object(s,'launch') as launch:
   with self.assertRaises(PermissionError):s.actual(s.initial(),{})
   launch.assert_not_called()

 def test_request_exception_skips_date_and_still_reaches_may31(self):
  with tempfile.TemporaryDirectory(dir=c.ROOT) as folder:
   state,calls,passed=self.exercise(Path(folder),('2025-05-02','A3'),explode=True)
   self.assertTrue(passed);self.assertIn(('2025-05-31','M4'),calls)
   self.assertEqual(state['jobs'][1]['status'],'PLANNING_FAILED')

 def test_actual_dispatches_seven_and_only_ready_dates_after_all_planning(self):
  from contextlib import nullcontext
  from v44_iteration2 import supervisor as s
  from v44_iteration2.report import report
  from v44_recovery_r038 import cpu
  with tempfile.TemporaryDirectory(dir=c.ROOT) as folder:
   root=Path(folder);ops=root/'OPS';doc=root/'DOC';atomic(doc/'CPU_PLACEMENT.json',{})
   jobs=[dict(day=d,status='PLANNING_FAILED',stages={}) for d in c.DAYS]
   for j in jobs[:8]:
    p=root/(j['day']+'.json');atomic(p,{})
    j.update(status='PLANNING_PASS',M4_freeze=record(p),stages=dict(M4=dict(PASS=True)))
   ready=contracts.actual_ready(jobs)
   atomic(ops/'ALL_31_PLANNING_FINISHED.json',dict(PASS=True,all_31_Planning_terminal=True,days=list(c.DAYS),ready_days=[j['day'] for j in ready],freezes=[j['M4_freeze'] for j in ready]))
   launched=[];counts=[];state=dict(jobs=jobs)
   def make(day,stage,lease,**kw):return dict(day=day,case_root=str(root/day),slot=kw['slot'])
   def launch(q):
    launched.append(q);p=Path(q['case_root']);atomic(p/'RESULT.json',dict(PASS=True))
    return SimpleNamespace(poll=lambda:0,returncode=0),dict(pid=0,process_created=0,root=str(p))
   with patch.object(c,'ROOT',root),patch.object(c,'OPS',ops),patch.object(c,'DOC',doc),patch.object(requests,'make',make),patch.object(s,'launch',launch),patch.object(s,'publish',lambda v:counts.append(len(v.get('workers',[])))),patch.object(s.time,'sleep',lambda n:None),patch.object(cpu,'reserve_pool',lambda *a:nullcontext()),patch('v44_iteration2.report.report',lambda v:None),patch.object(resources,'admission',lambda *a,**kw:dict(admit=kw['running']<7)):
    s.actual(state,{})
   self.assertEqual([q['day'] for q in launched],[j['day'] for j in ready]);self.assertEqual(max(counts),7)
   self.assertEqual(state['Actual_ready_count'],8);self.assertTrue(state['Actual_subset_PASS'])

if __name__=='__main__':unittest.main()

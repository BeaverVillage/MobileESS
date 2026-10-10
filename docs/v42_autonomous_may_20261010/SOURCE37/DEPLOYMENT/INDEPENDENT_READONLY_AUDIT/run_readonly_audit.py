from pathlib import Path
from datetime import datetime,timezone
import ast,hashlib,json,time,psutil
ROOT=Path('D:/v42_may_restart_20261010_02');REPO=Path('D:/MobileESS_v42_autonomous');OUT=Path(__file__).resolve().parent
SOURCE37='ba88d19a1e0d0abbbf343ee55deec49753b8e68d6a31c37c1ee9a8cf288c4a82'
SOURCE36='4f1a5980ae897ce1dcfc1ca0fc35836d2a17eddcf3e15df5d587de9f9bd0bf39'
BASE=Path('D:/v42_source36_actual_transition_independent_audit_20261010_01/events/OWNED_CONTROL_ONLY_SUPERVISOR_RELOAD_CONTINUITY_70a5a5f3/OWNED_SUPERVISOR_RELOAD_READONLY_ACCEPTANCE_RECEIPT.json')
def raw(p):
 for attempt in range(100):
  try:return Path(p).read_bytes()
  except PermissionError:
   if attempt==99:raise
   time.sleep(.001)
def record(p):
 p=Path(p).resolve();b=raw(p);return dict(path=str(p),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def save_bytes(name,b):
 p=OUT/name;p.parent.mkdir(parents=True,exist_ok=True);assert not p.exists();p.write_bytes(b);return record(p)
def saved(p):
 p=Path(p).resolve();b=raw(p);h=hashlib.sha256(b).hexdigest();q=OUT/'artifacts'/(h+p.suffix)
 if not q.exists():save_bytes(q.relative_to(OUT),b)
 return json.loads(b.decode('utf-8-sig')),dict(path=str(p),bytes=len(b),sha256=h,saved_copy=str(q))
def same(a,b):return {k:a[k] for k in ('path','bytes','sha256')}=={k:b[k] for k in ('path','bytes','sha256')}
def ident(pid):
 p=psutil.Process(pid);return dict(PID=p.pid,created=p.create_time(),command=p.cmdline(),cwd=p.cwd())
def frozen_state():
 d={}
 for version in ('35','36','37'):
  receipt=ROOT/('autonomous/V'+version+'_SPARSE_IMMUTABLE_FREEZE.json');f,ref=saved(receipt)
  declared={x['path']:x for x in f['source_files']};assert len(declared)==1111
  assert all(record(p)==entry for p,entry in declared.items())
  d[version]=dict(receipt=ref,files=declared)
 return d
def old_docs_state():
 result={}
 for version in ('35','36'):
  p=REPO/('docs/v42_autonomous_may_20261010/SOURCE'+version)
  for inventory in sorted(p.rglob('*INVENTORY*.json')):result[str(inventory)]=record(inventory)
  top=p/'SHA_INVENTORY.json';doc=json.loads(raw(top));assert doc['PASS'] is True
  for name,expected in doc['files'].items():
   actual=record(p/name);assert actual['sha256']==expected['sha256'] and actual['bytes']==expected['bytes']
 return result
ast.parse(Path(__file__).read_text(encoding='utf-8-sig'))
assert all(not any(ord(c)<32 for c in n.value) for n in ast.walk(ast.parse(Path(__file__).read_text(encoding='utf-8-sig'))) if isinstance(n,ast.Constant) and isinstance(n.value,str))
start=datetime.now(timezone.utc).isoformat();frozen_before=frozen_state();docs_before=old_docs_state()
baseline,baseline_ref=saved(BASE);assert baseline_ref['sha256']=='ce0734a69da99d00993b88bf9a4d1cc091e60b3f858d50d0871a429b2d31f7af'
deployment,dref=saved(ROOT/'autonomous/V37_ZERO_START_RETRY_DEPLOYMENT.json')
prepared,pref=saved(ROOT/'autonomous/V37_ZERO_START_RETRY_PREPARATION.json')
validation,vref=saved(ROOT/'autonomous/V37_VERIFIED_REPAIR_VALIDATION.json')
manifest,mref=saved(ROOT/'B2_V37_ZERO_START_DEPLOYMENT_MANIFEST.json')
registry,rref=saved(ROOT/'AUTONOMOUS_MANIFEST.json')
lease,lref=saved(ROOT/'REPAIR_LEASE.json')
cp,cpref=saved(ROOT/'SUPERVISOR_STATE.json')
queue,qref=saved(ROOT/'RECOVERY_QUEUE.json')
sup,sref=saved(ROOT/'SUPERVISOR_PROCESS.json');heartbeat,href=saved(ROOT/'SUPERVISOR_HEARTBEAT.json')
monitor,monref=saved(ROOT/'AUTONOMOUS_MONITOR_SERVER.json')
assert deployment['PASS'] and prepared['PASS'] and validation['PASS']
assert mref['sha256']=='8837dc2cd0487dd4401d29893f6746ca6faa9d2e95bb3ca111b3e24194a111d1'
assert vref['sha256']=='0d9ddc227fc3a3f0101fe59865ea137dbaf0173306cf1034123776e6e61adcde'
assert pref['sha256']=='6e8d1fc3e74ee7e566a3a86e9b87046acb70b3cc32f3e15e8d0f4520143a1cd7'
assert same(deployment['deployment'],mref) and same(prepared['deployment'],mref)
assert same(deployment['validation'],vref) and same(prepared['validation'],vref)
assert Path(registry['B2_code_root']).resolve()==Path('D:/v42run37')
assert Path(registry['B2_deployment_manifest']).resolve()==ROOT/'B2_V37_ZERO_START_DEPLOYMENT_MANIFEST.json'
assert registry['B2_source_SHA']==manifest['execution_SHA']==SOURCE37
assert registry['B2_source_commit']==manifest['source_commit']=='300acbeb7a53da184d996bc352a8527cfb3549f5'
assert len(manifest['builder_original_sources'])==1007 and len(manifest['execution_sources'])==99
m36,_=saved(ROOT/'B2_V36_ZERO_START_DEPLOYMENT_MANIFEST.json')
assert manifest['builder_original_sources']==m36['builder_original_sources']
assert [n for n in manifest['execution_sources'] if manifest['execution_sources'][n]!=m36['execution_sources'][n]]==['v42_autonomous_b2/worker.py']
assert all(record(Path('D:/v42run37')/n)['sha256']==h for n,h in {**manifest['builder_original_sources'],**manifest['execution_sources']}.items())
assert manifest['prior_attempts']=={} and manifest['historical_bound_point_reuse'] is False and manifest['restart_from_zero'] is True
requests={}
assert set(prepared['requests_by_day_and_slot'])=={'2025-05-10'}
for slot,expected in prepared['requests_by_day_and_slot']['2025-05-10'].items():
 request,ref=saved(expected['path']);assert same(ref,expected)
 assert request['attempt_id']=='repair_b2_v37_01_s'+slot and request['worker_slot']==int(slot) and request['day']=='2025-05-10'
 assert request['implementation_SHA']==SOURCE37 and request['manifest_SHA']==mref['sha256']
 assert request['restart_from_zero'] is True and request['previous_attempts']==[] and request['reset_authorization']==manifest['reset_authorization']
 assert request['native_budget_seconds']==5400 and request['wall_budget_seconds'] is None and request['Threads']==1 and request['P2_calls']==0 and request['target_gap']==.03
 assert not Path(request['output']).exists() and not Path(request['result']).exists() and not Path(ref['path']).parent.joinpath('NATIVE_RUNTIME_LEDGER.json').exists()
 requests[slot]=dict(receipt=ref,document=request,no_output_or_result_or_native_ledger=True)
assert set(requests)=={'1','2','3'}
rows=[x for x in queue['entries'] if x.get('repair_source_SHA')==SOURCE37]
assert len(rows)==1
row=rows[0];assert row['queue_id']=='cb3c3b7e32b0455c883aefb16051c340' and row['date']=='2025-05-10' and row['verification_status']=='READY_VERIFIED_REPAIR'
assert row['initial_native_runtime']==0 and row['remaining_native_seconds']==row['native_budget_seconds']==5400 and row['retry_priority']==100
assert row['new_worker_PID'] is None and row['retry_attempt_id'] is None
assert row['retry_request_receipts_by_slot']==prepared['requests_by_day_and_slot']['2025-05-10']
assert row['restart_from_zero'] is True and row['previous_checkpoint_reuse'] is False and row['previous_native_budget_carry'] is False and row['old_attempts_and_accounting_preserved'] is True
assert same(row['validation_receipt'],vref)
old_result,old_result_ref=saved(row['original_result_receipt']['path']);old_ledger,old_ledger_ref=saved(row['original_ledger_receipt']['path'])
assert same(old_result_ref,row['original_result_receipt']) and same(old_ledger_ref,row['original_ledger_receipt'])
assert old_result['PASS'] is False and old_result['Native_Runtime']==row['historical_native_runtime']==row['original_native_runtime']==old_ledger['measured_Native_Runtime']==584.6879997253418
assert old_result_ref['sha256']=='d3d6d86dd02dd97e59f575d44ca0dbb2961f81b852f9200f6fede8a353462454'
assert old_ledger_ref['sha256']=='9cb0737392f5cab196bc115d58349aa203b24b8e89cbab5bb52af3d9fa923588'
assert len(old_ledger['calls'])==6 and old_ledger['P2_calls']==0
current={};expected_keys={'B2/2025-05-01','B2/2025-05-02','B2/2025-05-03'}
assert set(cp['workers'])==expected_keys
for key,w in cp['workers'].items():
 prior=baseline['current_workers'][key];actual=ident(w['PID']);assert actual==prior['OS']
 assert actual['created']==w['created'] and actual['command']==w['command']
 assert Path(actual['command'][-1]).resolve()==Path(w['request']).resolve() and Path(actual['cwd']).resolve()==Path('D:/v42run36')
 request,reqref=saved(w['request']);assert same(reqref,prior['request']) and request['implementation_SHA']==SOURCE36
 ledger_path=Path(w['request']).parent/'NATIVE_RUNTIME_LEDGER.json';ledger,lref_worker=saved(ledger_path)
 prior_ledger,prior_lref=saved(prior['current_Native']['path']);assert same(prior_lref,prior['current_Native'])
 assert ledger['calls'][:len(prior_ledger['calls'])]==prior_ledger['calls']
 assert ledger['measured_Native_Runtime']>=prior_ledger['measured_Native_Runtime'] and ledger['P2_calls']==0 and ledger['Native_ceiling_seconds']==5400
 current[key]=dict(OS=actual,request=reqref,current_ledger=lref_worker,prefix_baseline=prior_lref,current_completed_calls=len(ledger['calls']),current_completed_Native_Runtime=ledger['measured_Native_Runtime'],inflight=ledger['inflight'],earlier_completed_prefix_preserved=True)
actual_sup=ident(sup['PID']);assert actual_sup==baseline['current_supervisor'] and actual_sup['PID']==80264
assert all(heartbeat['process'][k]==actual_sup[k] for k in ('PID','created','command'))
age=(datetime.now(timezone.utc)-datetime.fromisoformat(heartbeat['timestamp_UTC'])).total_seconds();assert 0<=age<=60
actual_monitor=ident(monitor['process']['PID']);assert actual_monitor['PID']==105976
assert all(actual_monitor[k]==monitor['process'][k] for k in ('PID','created','command'))
monitors=[]
for p in psutil.process_iter(['pid','name']):
 if (p.info['name'] or '').lower() not in ('python.exe','pythonw.exe'):continue
 try:
  cmd=p.cmdline()
  if '-m' in cmd and cmd[cmd.index('-m')+1]=='v42_autonomous_monitor.host' and str(ROOT) in cmd:monitors.append(p.pid)
 except (psutil.NoSuchProcess,psutil.AccessDenied):pass
assert monitors==[105976]
assert lease['state']=='RELEASED' and lease['token']=='c4c7547609954eefaa5ad213269fb2ca' and lease['automatic_time_expiry'] is False and lease['release_reason']=='EXPLICIT_REPAIR_END'
previous_deploy,_=saved(ROOT/'autonomous/V36_ZERO_START_RETRY_DEPLOYMENT.json')
old_qids={x['queue_id'] for x in previous_deploy['queues']};old_rows=[x for x in queue['entries'] if x['queue_id'] in old_qids]
assert len(old_rows)==9
assert len([x for x in old_rows if x['verification_status']=='READY_VERIFIED_REPAIR'])==6
assert len([x for x in old_rows if x['verification_status']=='NATIVE_PROGRESS_VERIFIED'])==3
assert all(x['repair_source_SHA']==SOURCE36 for x in old_rows)
prior_prepared,_=saved(ROOT/'autonomous/V36_ZERO_START_RETRY_PREPARATION.json')
for day,slots in prior_prepared['requests_by_day_and_slot'].items():
 for slot,ref in slots.items():assert same(record(ref['path']),ref)
frozen_after=frozen_state();docs_after=old_docs_state()
assert frozen_before==frozen_after and docs_before==docs_after
assert record(ROOT/'B2_V37_ZERO_START_DEPLOYMENT_MANIFEST.json')['sha256']==mref['sha256']
assert record(row['original_result_receipt']['path'])['sha256']==old_result_ref['sha256'] and record(row['original_ledger_receipt']['path'])['sha256']==old_ledger_ref['sha256']
receipt=dict(schema='V42_SOURCE37_ACTUAL_MAY10_DEPLOYMENT_INDEPENDENT_READONLY_AUDIT_V1',PASS=True,UTC=datetime.now(timezone.utc).isoformat(),audit_start_UTC=start,audit_end_UTC=datetime.now(timezone.utc).isoformat(),scientific_day_or_performance_PASS_claimed=False,execution_SHA=SOURCE37,execution_source_count=99,original_source_count=1007,unique_science_source_count=1106,sparse_source_count_each=1111,changed_execution_vs_Source36=['v42_autonomous_b2/worker.py'],future_registry=rref,manifest=mref,validation=vref,preparation=pref,deployment=dref,actual_deployment_timestamp=deployment['UTC'],requests=requests,new_queue_id=row['queue_id'],new_queue_status=row['verification_status'],new_queue_initial_Native=0,new_queue_native_ceiling_seconds=5400,new_queue_retry_priority=100,new_queue_worker_not_started=True,old_failed_May10_result=old_result_ref,old_failed_May10_ledger=old_ledger_ref,old_failed_May10_native_runtime=584.6879997253418,old_completed_Native_calls=6,current_workers=current,supervisor=dict(OS=actual_sup,metadata=sref,heartbeat=href,heartbeat_age_seconds=age),monitor=dict(OS=actual_monitor,metadata=monref,sole_matching_PID=monitors),released_lease=lref,actual_lease_released_UTC=lease['released_UTC'],prior_source36_queue_ids=sorted(old_qids),prior_Source36_three_running_and_six_READY_preserved=True,prior_Source36_all27_request_SHA_preserved=True,old_documentation_inventories=docs_before,old_documentation_declared_top_inventory_files_verified=True,immutable_before=frozen_before,immutable_after=frozen_after,all_frozen_source_and_old_inventory_start_end_identical=True,current_checkpoint=cpref,current_queue_snapshot=qref,prefix_baseline_receipt=baseline_ref,prefix_boundary='Earlier independently sealed owned80264 reload observation at '+baseline['UTC']+' compared to current post-Source37 snapshot; not an invented simultaneous prepare-before cursor.',Native_optimize_calls=0,real_Native_model_constructions=0,modelattempts=[],nativeattempts=[],production_queue_process_worker_lease_Git_actions=0,limitations=['Audit reads existing producer admission receipts and saved files only; it does not repeat scientific factories, cases, checkers or Native solves.','Source37 May10 is READY and has no scientific output or Native ledger; no solve or finalPASS observed.','Current Source36 ledgers legitimately progress; completed call prefixes from the earlier independent observation remain exact.','Source36 firstRMP downstream numerical/certification performance remains a separate active observation.'])
final=save_bytes('SOURCE37_DEPLOYMENT_INDEPENDENT_READONLY_AUDIT.json',(json.dumps(receipt,ensure_ascii=False,indent=2)+chr(10)).encode('utf-8'))
print(json.dumps(dict(PASS=True,receipt=final,workers={k:v['OS']['PID'] for k,v in current.items()},queue=row['queue_id'],Native_initial=0,actual_deployment_UTC=deployment['UTC'],released_UTC=lease['released_UTC'])))

"""Read-only deployment audit; every mutable JSON snapshot uses one byte read."""
from pathlib import Path
import collections, datetime, hashlib, json, math, subprocess, urllib.request
import psutil

AUDIT=Path(r'D:\v42_source30_deployment_audit_20261010_01')
ROOT=Path(r'D:\v42_may_restart_20261010_02')
CODE=Path(r'D:\v42run30')
SOURCE='f6ed2fee8b50208e64a2b0abffc65b7485eb717e4af4c1b29f82cea19a4de788'
COMMIT='bb9052225b440e4d70cd0441fb0c8dc8c6708e47'
FOLDERS=('v42_b2_seed_recovery_v19','v42_b2_seed_recovery_v18r3',
 'v42_b2_seed_recovery_v18r2','v42_b2_seed_recovery_v18',
 'v42_b2_start_recovery_v13','v42_b2_build_authority_v13','v42_autonomous_b2')
RAW=AUDIT/'post_raw_03'; RAW.mkdir(exist_ok=False)
records=[]; issues=[]; checks={}

def sha(data):return hashlib.sha256(data).hexdigest()
def digest(value):return sha(json.dumps(value,sort_keys=True,separators=(',',':')).encode())
def check(name,value):
 checks[name]=bool(value)
 if not value:issues.append(name)
 return bool(value)
def saved(path,name):
 data=Path(path).read_bytes()
 target=RAW/name
 with target.open('xb') as f:f.write(data)
 receipt=dict(source_path=str(path),snapshot_path=str(target),bytes=len(data),
   sha256=sha(data),source_read_count=1,snapshot_bytes_exact=True)
 records.append(receipt)
 return json.loads(data),receipt
def seal_match(receipt,name):
 value,actual=saved(receipt['path'],name)
 check('sealed_receipt_'+name,actual['sha256']==receipt['sha256'] and actual['bytes']==receipt['bytes'])
 return value,actual
def process(pid):
 p=psutil.Process(pid)
 with p.oneshot():
  return dict(PID=p.pid,created=p.create_time(),command=p.cmdline(),cwd=p.cwd(),exe=p.exe(),
    status=p.status(),priority=p.nice(),CPU_seconds=sum(p.cpu_times()[:2]),RSS_bytes=p.memory_info().rss)
def same_process(a,b):return all(a[k]==b[k] for k in ('PID','created','command','cwd','exe'))

baseline=json.loads((AUDIT/'SOURCE30_DEPLOYMENT_BASELINE.json').read_bytes())
before=json.loads((AUDIT/'baseline_raw/RECOVERY_QUEUE.json').read_bytes())
corrected=json.loads((AUDIT/'SOURCE30_DEPLOYMENT_BASELINE_QUEUE_SUMMARY.json').read_bytes())
cp,cp_receipt=saved(ROOT/'SUPERVISOR_STATE.json','SUPERVISOR_STATE.json')
supervisor_record,_=saved(ROOT/'SUPERVISOR_PROCESS.json','SUPERVISOR_PROCESS.json')
queue,queue_receipt=saved(ROOT/'RECOVERY_QUEUE.json','RECOVERY_QUEUE.json')
autonomous,autonomous_receipt=saved(ROOT/'AUTONOMOUS_MANIFEST.json','AUTONOMOUS_MANIFEST.json')
heartbeat,heartbeat_receipt=saved(ROOT/'SUPERVISOR_HEARTBEAT.json','SUPERVISOR_HEARTBEAT.json')

# Capture workers immediately, before static file hashing.
workers=[]
for old in baseline['workers']:
 key=old['key']; day=key.split('/')[1]; current=cp['workers'].get(key)
 try:proc=process(old['actual_process']['PID'])
 except psutil.NoSuchProcess:proc=None
 result=None; result_receipt=None
 if proc is None:
  result,result_receipt=saved(old['request']['result'],day+'_Source27_TERMINAL_RESULT.json')
  check(day+'_old_worker_natural_terminal_after_deployment',result['PASS'] is False
   and result['identity']['attempt_id']==old['request']['attempt_id']
   and result['finished_UTC']>'2026-10-09T21:07:00.352988+00:00'
   and result['status']=='TIME_LIMIT_FEASIBLE_NOT_CERTIFIED')
  if current is not None:
   successor=process(current['PID'])
   check(day+'_legitimate_source30_successor_after_old_terminal',current['source_SHA']==SOURCE
    and successor['created']>datetime.datetime.fromisoformat(result['finished_UTC']).timestamp()
    and successor['command']==current['command'] and successor['cwd']==str(CODE))
 else:
  check(day+'_worker_checkpoint_identity_unchanged',current==old['worker_checkpoint'])
  check(day+'_actual_process_identity_unchanged',same_process(old['actual_process'],proc))
 request,req_receipt=saved(old['request_receipt']['source_path'],day+'_request.json')
 ledger,ledger_receipt=saved(old['ledger_receipt']['source_path'],day+'_NATIVE_RUNTIME_LEDGER.json')
 progress,progress_receipt=saved(old['progress_receipt']['source_path'],day+'_progress.json')
 old_ledger=json.loads(Path(old['ledger_receipt']['snapshot_path']).read_bytes())
 count=len(old_ledger['calls']); calls=ledger['calls']
 check(day+'_request_bytes_unchanged',req_receipt['sha256']==old['request_receipt']['sha256'])
 check(day+'_completed_native_calls_exact_prefix',calls[:count]==old_ledger['calls'])
 check(day+'_non_native_cost_receipts_exact_prefix',ledger['costs'][:len(old_ledger['costs'])]==old_ledger['costs'])
 check(day+'_measured_native_monotonic',ledger['measured_Native_Runtime']>=old_ledger['measured_Native_Runtime'])
 native_sum=sum(call['Native_Runtime'] for call in calls)
 check(day+'_measured_native_matches_exact_current_calls',native_sum==ledger['measured_Native_Runtime'])
 check(day+'_no_budget_reset_or_historical_carry',ledger['Native_ceiling_seconds']==5400
       and ledger['inclusive_T0']==old_ledger['inclusive_T0'] and ledger['prior_attempt'] is None
       and ledger['date_runtime_reset'] is False and ledger['historical_costs_reused'] is False)
 check(day+'_source27_current_progress_and_request',request==old['request']
       and progress['attempt_id']==request['attempt_id'] and progress['worker']['PID']==old['actual_process']['PID']
       and (proc is None or (proc['cwd']==r'D:\v42run27' and proc['priority']==old['actual_process']['priority'])))
 if result is not None:
  check(day+'_terminal_exact_measured_ledger_cost',result['Native_Runtime']==ledger['measured_Native_Runtime']
   and ledger['inflight'] is None and ledger['measured_Native_Runtime']>=5400)
 workers.append(dict(key=key,actual_process=proc,worker_checkpoint=current,request_receipt=req_receipt,
  terminal_result_receipt=result_receipt,terminal_worker_status=result.get('status') if result else None,
  terminal_finished_UTC=result.get('finished_UTC') if result else None,
  ledger_receipt=ledger_receipt,progress_receipt=progress_receipt,
  completed_calls_before=count,completed_calls_after=len(calls),
  measured_Native_Runtime_before=old_ledger['measured_Native_Runtime'],
  measured_Native_Runtime_after=ledger['measured_Native_Runtime'],
  inflight=ledger['inflight'],progress_Native_Runtime=progress['Native_Runtime'],
  UB=progress.get('UB'),global_LB=progress.get('global_LB'),gap=progress.get('gap')))
supervisor=process(supervisor_record['PID'])
check('coordinator87676_actual_identity_unchanged',supervisor['PID']==87676
 and same_process(baseline['supervisor'],supervisor)
 and supervisor_record['created']==supervisor['created'] and supervisor_record['command']==supervisor['command'])

deployment,deployment_receipt=saved(ROOT/'autonomous/V30_ZERO_START_RETRY_DEPLOYMENT.json','V30_ZERO_START_RETRY_DEPLOYMENT.json')
manifest,manifest_receipt=seal_match(deployment['deployment'],'B2_V30_ZERO_START_DEPLOYMENT_MANIFEST.json')
validation,validation_receipt=seal_match(deployment['validation'],'V30_VERIFIED_REPAIR_VALIDATION.json')
preparation,preparation_receipt=saved(ROOT/'autonomous/V30_ZERO_START_RETRY_PREPARATION.json','V30_ZERO_START_RETRY_PREPARATION.json')
freeze,freeze_receipt=seal_match(validation['sparse_freeze'],'V30_SPARSE_IMMUTABLE_FREEZE.json')
authorization,authorization_receipt=seal_match(manifest['reset_authorization'],'USER_ZERO_START_RETRY_AUTHORIZATION.json')
check('deployment_preparation_validation_true',deployment['PASS'] is True and preparation['PASS'] is True
 and validation['PASS'] is True and freeze['PASS'] is True)
check('deployment_and_preparation_same_source_receipts',deployment['deployment']==preparation['deployment']
 and deployment['validation']==preparation['validation'])
check('actual_native_denied_27_admissions_recorded',preparation['all_27_sealed_request_native_denied_admissions_PASS'] is True
 and preparation['all_27_current_source_cache_and_RMP_factory_admissions_PASS'] is True
 and preparation['Native_optimize_calls']==0 and preparation['model_constructions']==0)
check('source30_commit_and_source_binding',manifest['source_commit']==COMMIT and manifest['execution_SHA']==SOURCE
 and validation['repair_source_SHA']==SOURCE and validation['repair_commit_SHA']==COMMIT
 and freeze['commit']==COMMIT and Path(freeze['code_root'])==CODE)
git_head=subprocess.check_output(['git','-C',str(CODE),'rev-parse','HEAD'],text=True).strip()
check('actual_checkout_HEAD',git_head==COMMIT)
source_actual=[]
for receipt in freeze['source_files']:
 p=Path(receipt['path']); data=p.read_bytes(); actual=dict(path=str(p),sha256=sha(data),bytes=len(data))
 source_actual.append(actual)
 if actual!=receipt:issues.append('frozen_source_drift:'+str(p))
check('all_1110_frozen_source_bytes_exact',source_actual==freeze['source_files'] and len(source_actual)==1110)
actual_map={Path(x['path']).relative_to(CODE).as_posix():x['sha256'] for x in source_actual}
execution=manifest['execution_sources']; originals=manifest['builder_original_sources']
actual_execution_names={p.relative_to(CODE).as_posix() for folder in FOLDERS
 for p in (CODE/folder).iterdir() if p.is_file() and p.suffix in ('.py','.html')}
check('exact_execution_set98_and_digest',len(execution)==98 and set(execution)==actual_execution_names
 and all(actual_map[k]==v for k,v in execution.items()) and digest(execution)==SOURCE)
check('original1007_bytes_exact',len(originals)==1007 and all(actual_map[k]==v for k,v in originals.items()))
old_manifest,_=saved(baseline['workers'][0]['request']['manifest'],'B2_V27_ORIGINAL_WORKER_MANIFEST.json')
check('original_science_map_unchanged_from_running27',old_manifest['builder_original_sources']==originals)
assets=validation['sparse_required_additional_assets']
check('required_five_assets_exact',len(assets)==5 and all(x in source_actual for x in assets))
check('execution_original_assets_exact_union',set(actual_map)==set(execution)|set(originals)|
 {Path(x['path']).relative_to(CODE).as_posix() for x in assets})
check('future_pointer_only_source30',autonomous['B2_code_root']==str(CODE)
 and autonomous['B2_source_SHA']==SOURCE and autonomous['B2_source_commit']==COMMIT
 and autonomous['B2_manifest']==dict(path=str(ROOT/'B2_V30_ZERO_START_DEPLOYMENT_MANIFEST.json'),
  sha256=manifest_receipt['sha256'],bytes=manifest_receipt['bytes']))

requests=[]
for day,slots in preparation['requests_by_day_and_slot'].items():
 check(day+'_exact_three_slots',set(slots)=={'1','2','3'})
 for slot,receipt in slots.items():
  req,actual=seal_match(receipt,day+'_s'+slot+'_source30_request.json')
  attempt=ROOT/'dates/B2'/day/'attempts'/req['attempt_id']
  check(day+'_s'+slot+'_fresh0_sealed_source30_request',req['root']==str(ROOT) and req['arm']=='B2'
   and req['day']==day and req['worker_slot']==int(slot) and req['native_budget_seconds']==5400
   and req['restart_from_zero'] is True and req['previous_attempts']==[]
   and req['reset_authorization']==manifest['reset_authorization']
   and req['implementation_SHA']==SOURCE and req['deployment_SHA']==SOURCE
   and req['manifest']==str(ROOT/'B2_V30_ZERO_START_DEPLOYMENT_MANIFEST.json')
   and req['manifest_SHA']==manifest_receipt['sha256'] and req['output']==str(attempt/'output')
   and Path(receipt['path'])==attempt/'request.json' and req['wall_budget_seconds'] is None
   and req['target_gap']==.03 and req['P2_calls']==0 and req['Threads']==1)
  active=next((worker for worker in cp['workers'].values() if worker['request']==receipt['path']),None)
  if active is None:
   check(day+'_s'+slot+'_unstarted_no_ledger_output_result',set(x.name for x in attempt.iterdir())=={'request.json'})
  else:
   check(day+'_s'+slot+'_naturally_started_current_source30',active['source_SHA']==SOURCE and active['source_commit']==COMMIT)
  requests.append(dict(day=day,slot=int(slot),request_receipt=actual,attempt_id=req['attempt_id'],current_active_worker=active))
check('27_actual_fresh_requests',len(requests)==27 and len(preparation['requests_by_day_and_slot'])==9)

old_by={e['queue_id']:e for e in before['entries']}; new_by={e['queue_id']:e for e in queue['entries']}
old_ready={e['queue_id']:e for e in before['entries'] if e['verification_status']=='READY_VERIFIED_REPAIR'}
added=[e for e in queue['entries'] if e['queue_id'] not in old_by]
check('exact_old27_plus_new9_queue_lineage',set(old_by)<=set(new_by) and len(added)==9 and len(queue['entries'])==36)
check('exact_new9_source30_ready_or_legitimate_dispatch',all(e['verification_status'] in ('READY_VERIFIED_REPAIR','WORKER_ENTERED','NATIVE_PROGRESS_VERIFIED') and e['repair_source_SHA']==SOURCE
 and e['repair_commit_SHA']==COMMIT and e['repair_code_root']==str(CODE) for e in added))
check('new9_dates_and_priority',sorted(e['date'] for e in added)==sorted(preparation['requests_by_day_and_slot'])
 and all(e['retry_priority']==(1000 if e['date'] in ('2025-05-01','2025-05-02','2025-05-03') else 100) for e in added))
allowed={'verification_status','superseded_UTC','original_prepared_repair_and_failure_evidence_preserved',
 'superseded_by_queue_id','superseded_reason'}
changes=[]
for qid,old in old_by.items():
 new=new_by[qid]; changed={k for k in set(old)|set(new) if old.get(k)!=new.get(k)}
 changes.append(dict(queue_id=qid,old_status=old['verification_status'],new_status=new['verification_status'],changed_keys=sorted(changed)))
 if qid in old_ready:
  successor=new_by[new['superseded_by_queue_id']]
  check(qid+'_only_unstarted28_superseded',old['repair_source_SHA']==corrected['ready_entries_before'][0]['repair_source_SHA']
   and old['retry_attempt_id'] is None and old['new_worker_PID'] is None and changed<=allowed
   and new['verification_status']=='SUPERSEDED_UNSTARTED_READY'
   and successor['supersedes_queue_id']==qid and successor['date']==old['date']
   and successor['repair_source_SHA']==SOURCE and new['original_prepared_repair_and_failure_evidence_preserved'] is True)
 else:
  # Native progress rows can update measured diagnostics naturally. Their dispatch/source/history identity must stay fixed.
  immutable=('retry_attempt_id','new_worker_PID','repair_source_SHA','repair_commit_SHA',
   'original_result_receipt','original_ledger_receipt','retry_request_receipts_by_slot','retry_request_receipt')
  check(qid+'_other_queue_identity_and_historical_evidence_preserved',all(old.get(k)==new.get(k) for k in immutable))
  if old['verification_status']!=new['verification_status']:
   key='B2/'+old['date']; observed=next(w for w in workers if w['key']==key)
   check(qid+'_only_natural_old_worker_terminal_status_transition',old['verification_status']=='NATIVE_PROGRESS_VERIFIED'
    and new['verification_status']=='RECOVERY_FAILED' and observed['terminal_result_receipt'] is not None)
check('only_old_source28_ready9_replaced',len(old_ready)==9 and all(e['supersedes_queue_id'] in old_ready for e in added))
for e in added:
 check(e['queue_id']+'_queue_fresh0_receipts_match',e['validation_receipt']==deployment['validation']
  and e['retry_request_receipts_by_slot']==preparation['requests_by_day_and_slot'][e['date']]
  and e['restart_from_zero'] is True and e['initial_native_runtime']==0
  and e['native_budget_seconds']==5400 and e['remaining_native_seconds']==5400
  and e['previous_checkpoint_reuse'] is False and e['previous_native_budget_carry'] is False
  and e['old_attempts_and_accounting_preserved'] is True and e['reset_authorization']==manifest['reset_authorization'])

try:
 with urllib.request.urlopen('http://127.0.0.1:8794/',timeout=10) as response:
  http_body=response.read(); http=dict(status=response.status,bytes=len(http_body),sha256=sha(http_body))
 check('HTTP8794_healthy',http['status']==200)
except Exception as error:
 http=dict(error=repr(error));check('HTTP8794_healthy',False)

receipt=dict(schema='SOURCE30_DEPLOYMENT_INDEPENDENT_READ_ONLY_EXECUTION_AUDIT_V1',
 UTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),PASS=not issues,
 root=str(ROOT),code_root=str(CODE),source_SHA=SOURCE,science_commit=COMMIT,actual_git_HEAD=git_head,
 checks=checks,issues=issues,workers=workers,supervisor=supervisor,HTTP8794=http,
 source_file_count=len(source_actual),execution_source_count=len(execution),original_source_count=len(originals),
 required_assets_count=len(assets),source_file_actual_receipts=source_actual,
 baseline_receipt=dict(path=str(AUDIT/'SOURCE30_DEPLOYMENT_BASELINE.json'),sha256=sha((AUDIT/'SOURCE30_DEPLOYMENT_BASELINE.json').read_bytes())),
 baseline_queue_schema_correction_receipt=dict(path=str(AUDIT/'SOURCE30_DEPLOYMENT_BASELINE_QUEUE_SUMMARY.json'),
 sha256=sha((AUDIT/'SOURCE30_DEPLOYMENT_BASELINE_QUEUE_SUMMARY.json').read_bytes())),
 raw_single_read_receipts=records,prepared_requests=requests,old_queue_changes=changes,
 new_queue_summary=[{k:e.get(k) for k in ('queue_id','date','verification_status','retry_priority','repair_source_SHA','supersedes_queue_id')} for e in added],
 actual_queue_status_counts=dict(collections.Counter(e['verification_status'] for e in queue['entries'])),
 deployment_time_status_from_sealed_deployer='9 READY at21:07:00UTC; later natural Source27 terminal/Source30 dispatch distinguished in actual snapshots',
 partial_initial_audit_snapshot_preserved=str(AUDIT/'post_raw'),
 production_mutations=0,Native_models_or_solves=0,
 admission_evidence_scope='Sealed27 request bytes and source/policy identities independently checked; Native-denied admission outcomes are sealed preparer evidence, not rerun by this execution audit.',
 scientific_independent_review_owner='authority_audit',final_day_PASS_claimed=False)
target=AUDIT/'SOURCE30_DEPLOYMENT_INDEPENDENT_READ_ONLY_EXECUTION_AUDIT.json'
data=(json.dumps(receipt,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode('utf8')
with target.open('xb') as f:f.write(data)
print(json.dumps(dict(PASS=receipt['PASS'],issues=issues,path=str(target),sha256=sha(data),bytes=len(data),checks=len(checks),
 workers=[dict(day=w['key'],PID=w['actual_process']['PID'] if w['actual_process'] else None,terminal_status=w['terminal_worker_status'],Native_before=w['measured_Native_Runtime_before'],Native_after=w['measured_Native_Runtime_after'],calls_before=w['completed_calls_before'],calls_after=w['completed_calls_after']) for w in workers],
 supervisor_PID=supervisor['PID'],queue_counts=receipt['actual_queue_status_counts']),ensure_ascii=False,indent=2))

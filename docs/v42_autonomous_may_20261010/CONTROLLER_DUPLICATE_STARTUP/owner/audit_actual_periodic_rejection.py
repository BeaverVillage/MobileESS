"""Read-only actual periodic startup rejection and live worker prefix audit."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,urllib.request
import psutil
R=Path(r'D:\v42_may_restart_20261010_02');O=Path(__file__).parent;REPO=Path(r'D:\MobileESS_v42_autonomous')
rawdir=O/'actual_periodic_raw';rawdir.mkdir(exist_ok=False)
rows=[];cache={}
def rec(p,b=None):
 p=Path(p);b=p.read_bytes() if b is None else b
 return dict(path=str(p),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def cap(p):
 p=Path(p)
 if p not in cache:
  b=p.read_bytes();q=rawdir/(f'{len(rows):03d}_'+p.name)
  with q.open('xb') as f:f.write(b)
  row=dict(source=rec(p,b),snapshot=rec(q,b),source_read_count=1);rows.append(row);cache[p]=(b,row)
 return cache[p]
def doc(p):return json.loads(cap(p)[0].decode('utf-8-sig'))
def ident(pid):
 p=psutil.Process(pid);return dict(PID=p.pid,created=p.create_time(),command=p.cmdline(),cwd=p.cwd())
baseline=doc(Path(r'D:\v42_control_heartbeat_io_repair_20261010_01')/'CONTROLLER_HEARTBEAT_IO_RELOAD_INDEPENDENT_ACTUAL_AUDIT_02.json')
event_path=R/'autonomous/startup_rejections/20261009T223320448514_df070a15592346f9b4f2b2dea7531cc4.json';event=doc(event_path)
task=doc(O/'ACTUAL_PERIODIC_REJECTION_TASK_READ_ONLY_OBSERVATION.json')
assert event['existing_owner']==baseline['actual_supervisor']
assert event['duplicate_process']['PID']==98264 and event['existing_owner']['PID']==107788
assert event['SUPERVISOR_ERROR_not_written'] and event['CP_worker_Native_files_not_written'] and not event['lock_removed_or_lease_broken']
assert event['reason']=='DUPLICATE_STARTUP_REJECTED_EXISTING_OWNED_LIVE_SUPERVISOR' and 0<=event['matching_heartbeat_age_seconds']<=60
assert task['LastTaskResult']==0 and task['LastRunTime'].startswith('2026-10-09T22:33:20')
assert ident(107788)==baseline['actual_supervisor']
current_cp=doc(R/'SUPERVISOR_STATE.json');proc=doc(R/'SUPERVISOR_PROCESS.json')
assert proc['PID']==107788 and proc['created']==baseline['actual_supervisor']['created']
assert set(current_cp['workers'])=={x['key'] for x in baseline['same_three_workers']}
workers=[]
for old in baseline['same_three_workers']:
 key=old['key'];w=current_cp['workers'][key];actual=ident(w['PID']);assert actual==old['actual']
 req=Path(w['request']);assert cap(req)[1]['source']==old['request']['source'];request=doc(req)
 assert request['implementation_SHA']==baseline['immutable_Source32_SHA'] and request['previous_attempts']==[]
 prior=doc(old['ledger']['snapshot']['path']);ledger_path=req.parent/'NATIVE_RUNTIME_LEDGER.json';ledger=doc(ledger_path)
 assert ledger['calls'][:len(prior['calls'])]==prior['calls'] and ledger['measured_Native_Runtime']>=prior['measured_Native_Runtime']
 assert ledger['Native_ceiling_seconds']==5400 and ledger['P2_calls']==0
 workers.append(dict(key=key,identity=actual,request=cap(req)[1],ledger=cap(ledger_path)[1],Native_before=prior['measured_Native_Runtime'],Native_after=ledger['measured_Native_Runtime'],calls_before=len(prior['calls']),calls_after=len(ledger['calls']),ledger_UTC=ledger['UTC'],CP_status=current_cp['dates'][key]['status']))
current_error=doc(R/'SUPERVISOR_ERROR.json');prior_error=doc(O/'ORIGINAL_SUPERVISOR_ERROR_RAW_FULL.json')
assert cap(R/'SUPERVISOR_ERROR.json')[1]['source']['sha256']==cap(O/'ORIGINAL_SUPERVISOR_ERROR_RAW_FULL.json')[1]['source']['sha256']
assert datetime.fromisoformat(current_error['UTC'])<datetime.fromisoformat(event['UTC'])
owner=doc(O/'FULL_NATIVE_DENIED_TEST_RECEIPT.json')
control={k:rec(v['path']) for k,v in owner['source_files_end'].items()};assert control==owner['source_files_end']
with urllib.request.urlopen('http://127.0.0.1:8794/api/status',timeout=20) as f:status=f.status;raw=f.read()
api=json.loads(raw);assert status==200 and api['supervisor_alive'] and {x['PID'] for x in api['workers']}=={x['identity']['PID'] for x in workers}
api_path=rawdir/'HTTP8794_API_STATUS_RAW.json'
with api_path.open('xb') as f:f.write(raw)
report=dict(PASS=True,UTC=datetime.now(timezone.utc).isoformat(),schema='V42_ACTUAL_OS_PERIODIC_DUPLICATE_STARTUP_REJECTION_INDEPENDENT_READ_ONLY_AUDIT',
 actual_event=cap(event_path)[1],actual_event_data=event,actual_OS_task=cap(O/'ACTUAL_PERIODIC_REJECTION_TASK_READ_ONLY_OBSERVATION.json')[1],owner_supervisor_unchanged=ident(107788),workers=workers,all_completed_Native_prefixes_preserved=True,
 public_error_bytes_unchanged_from_pre_full_test_observation=True,public_error=cap(R/'SUPERVISOR_ERROR.json')[1],public_error_UTC=current_error['UTC'],control_source4=control,
 actual_HTTP8794=dict(status=status,snapshot=rec(api_path,raw),snapshot_UTC=api['snapshot_UTC']),raw_single_read_records=rows,
 future_startup_candidate_applied_by_existing_OS_task=True,active_owner_loop_not_restarted=True,supervisor_reload_required=False,
 Native_optimize_calls_by_auditor=0,real_Native_model_constructions_by_auditor=0,process_actions_by_auditor=0,production_source_queue_manifest_changes_by_auditor=0,
 scientific_final_PASS_claimed=False,independent142_review_status='PENDING_AT_THIS_OBSERVATION',
 limitations='OS task naturally loaded edited future startup code. Reviewer did not launch the task or restart any production process. Duplicate event code declares Native/model0; audit did not independently instrument that task process. Actual Native ledger values belong to unchanged scientific workers. Operational files/API were observed sequentially at their stated timestamps.')
p=O/'ACTUAL_PERIODIC_DUPLICATE_STARTUP_READ_ONLY_AUDIT.json'
with p.open('x',encoding='utf-8') as f:json.dump(report,f,ensure_ascii=False,indent=2);f.write('\n')
print(json.dumps(dict(PASS=True,receipt=rec(p),workers=[dict(key=w['key'],PID=w['identity']['PID'],Native=w['Native_after'],calls=w['calls_after']) for w in workers])))

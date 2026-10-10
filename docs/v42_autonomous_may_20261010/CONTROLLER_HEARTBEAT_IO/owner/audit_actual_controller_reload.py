"""Independent read-only process/ledger audit. Writes only external evidence."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib, json, subprocess, urllib.request
import psutil

R=Path(r'D:\v42_may_restart_20261010_02')
REPO=Path(r'D:\MobileESS_v42_autonomous')
SCI=Path(r'D:\v42run32')
OUT=Path(__file__).parent
RAW=OUT/'post_reload_raw'
RAW.mkdir(exist_ok=False)
records=[];cache={};checks=[]
def record(p,raw=None):
    p=Path(p).resolve();raw=p.read_bytes() if raw is None else raw
    return dict(path=str(p),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
def capture(p):
    p=Path(p).resolve()
    if p not in cache:
        raw=p.read_bytes();dest=RAW/(f'{len(records):03d}_'+p.name)
        with dest.open('xb') as f:f.write(raw)
        rec=dict(source=record(p,raw),snapshot=record(dest,raw),source_read_count=1)
        records.append(rec);cache[p]=(raw,rec)
    return cache[p]
def doc(p):return json.loads(capture(p)[0].decode('utf-8-sig'))
def need(v,label):
    assert v,label
    checks.append(dict(PASS=True,name=label))
def ident(pid):
    p=psutil.Process(pid)
    return dict(PID=p.pid,created=p.create_time(),command=p.cmdline(),cwd=p.cwd())

before=doc(R/'autonomous/CONTROLLER_HEARTBEAT_IO_RELOAD_BEFORE.json')
reload=doc(R/'autonomous/CONTROLLER_HEARTBEAT_IO_RELOAD_VERIFICATION.json')
launch=doc(R/'autonomous/CONTROLLER_HEARTBEAT_IO_RELOAD_LAUNCH.json')
need(capture(R/'autonomous/CONTROLLER_HEARTBEAT_IO_RELOAD_VERIFICATION.json')[1]['source']['sha256']=='4089d87fa419c8e76f33be11fcaad95553824defc8659668216dff30a4a29276','Root actual reload receipt exact disclosed SHA')
need(reload['PASS'] is True and reload['before']==capture(R/'autonomous/CONTROLLER_HEARTBEAT_IO_RELOAD_BEFORE.json')[1]['source'],'Root reload before SHA exact')
need(reload['launch']==capture(R/'autonomous/CONTROLLER_HEARTBEAT_IO_RELOAD_LAUNCH.json')[1]['source'],'Root launch receipt SHA exact')
need(before['supervisor']['PID']==107856 and reload['actual_supervisor']['PID']==107788 and launch['PID']==107788,'only disclosed supervisor replacement 107856 to 107788')
old_pid=before['supervisor']['PID']
old_alive=psutil.pid_exists(old_pid)
old_ident=ident(old_pid) if old_alive else None
need(not old_alive or old_ident['created']!=before['supervisor']['created'],'old exact supervisor process is absent (PID reuse distinguished)')
process=doc(R/'SUPERVISOR_PROCESS.json');cp=doc(R/'SUPERVISOR_STATE.json');hb=doc(R/'SUPERVISOR_HEARTBEAT.json');queue=doc(R/'RECOVERY_QUEUE.json')
actual_sup=ident(process['PID'])
need(actual_sup==reload['actual_supervisor'],'actual supervisor PID/create/command/cwd matches reload')
need(process['PID']==actual_sup['PID'] and process['created']==actual_sup['created'] and process['command']==actual_sup['command'],'current supervisor process record matches actual OS identity')
need(hb['process']['PID']==actual_sup['PID'] and hb['process']['created']==actual_sup['created'],'live heartbeat belongs to new supervisor')
need(cp['state']=='B2_RUNNING','coordinator continues B2_RUNNING')
need(set(cp['workers'])==set(before['workers'])=={'B2/2025-05-01','B2/2025-05-02','B2/2025-05-03'},'same three workers adopted without added or removed keys')
owner=doc(OUT/'FULL_NATIVE_DENIED_TEST_RECEIPT_02.json')
indep=doc(Path(r'D:\v42_controller_io_independent_review_20261010_01')/'INDEPENDENT_CONTROLLER_IO_NATIVE_DENIED_REVIEW_RECEIPT.json')
need(owner['PASS'] is True and owner['tests']==125 and owner['source_start_end_identical'],'owner final125 source-stable PASS')
need(indep['PASS'] is True and indep['tests_passed']==125 and indep['source_start_end_identical'] and indep['test_start_end_identical'],'independent125 source and test-stable PASS')
controls={}
for rel,expected in owner['source_files_end'].items():
    actual=record(REPO/rel);controls[rel]=actual
    need(actual==expected==indep['control_source_file_records_end'][rel],'current control source/test byte SHA '+rel)
    committed=subprocess.check_output(['git','show','81a62242:'+rel],cwd=REPO)
    need(hashlib.sha256(committed).hexdigest()==actual['sha256'],'committed81a62242 control bytes '+rel)
manifest=doc(R/'B2_V32_ZERO_START_DEPLOYMENT_MANIFEST.json')
SOURCE='9c159a8c64e6a7494aecf41266c0289e16cd65f6ee9eddf3de9f113593156ba9'
need(manifest['execution_SHA']==SOURCE and len(manifest['execution_sources'])==98 and len(manifest['builder_original_sources'])==1007,'immutable Source32 manifest98 and original1007 identity')
need(subprocess.check_output(['git','rev-parse','HEAD'],cwd=SCI,text=True).strip()==manifest['source_commit'],'immutable D32 actual commit')
scientific_files={}
for rel,sha in {**manifest['builder_original_sources'],**manifest['execution_sources']}.items():
    rec=record(SCI/rel);scientific_files[rel]=rec
    need(rec['sha256']==sha,'immutable D32 declared science byte SHA '+rel)
freeze=doc(R/'autonomous/V32_SPARSE_IMMUTABLE_FREEZE.json')
need(freeze['unique_file_count']==1110,'D32 complete sparse1110 freeze')
for expected in freeze['source_files']:
    need(record(expected['path'])==expected,'immutable D32 frozen byte SHA '+Path(expected['path']).relative_to(SCI).as_posix())
workers=[]
by_id={row['queue_id']:row for row in queue['entries']}
for key,expected in before['workers'].items():
    w=cp['workers'][key];actual=ident(w['PID']);request_path=Path(w['request']);request=doc(request_path)
    need(actual==expected==reload['actual_workers'][key],'same actual worker PID/create/command/cwd '+key)
    need(actual['command'][-1]==str(request_path) and Path(actual['cwd']).resolve()==SCI,'exact worker module and owned request path '+key)
    need(request['implementation_SHA']==SOURCE and request['deployment_SHA']==SOURCE and request['manifest_SHA']==capture(R/'B2_V32_ZERO_START_DEPLOYMENT_MANIFEST.json')[1]['source']['sha256'],'same source32 sealed worker request '+key)
    need(w['source_SHA']==SOURCE and w['source_commit']==manifest['source_commit'],'CP adopted scientific identity '+key)
    q=by_id[w['recovery_queue_id']]
    need(q['worker']==w and q['new_worker_PID']==actual['PID'] and q['retry_attempt_id']==request['attempt_id'],'queue dispatch identity matches CP worker '+key)
    receipt=q['retry_request_receipts_by_slot'][str(request['worker_slot'])]
    need(capture(request_path)[1]['source']==receipt,'exact dispatched sealed request SHA '+key)
    need(request['previous_attempts']==[] and request['restart_from_zero'] is True and request['native_budget_seconds']==5400,'current retry fresh0 no historical carry '+key)
    prior=doc(R/'autonomous'/('CONTROLLER_IO_RELOAD_'+key.replace('/','_')+'_NATIVE_BEFORE.json'))
    lp=request_path.parent/'NATIVE_RUNTIME_LEDGER.json';current=doc(lp)
    need(current['calls'][:len(prior['calls'])]==prior['calls'],'entire completed original Native-call prefix preserved '+key)
    need(current['measured_Native_Runtime']>=prior['measured_Native_Runtime'] and current['Native_ceiling_seconds']==5400 and current['P2_calls']==0,'Native runtime nondecreasing same cap/P2 '+key)
    row=cp['dates'][key]
    need(row['current_attempt']==request['attempt_id'] and row['request']==str(request_path) and row['status']=='RUNNING','current date is actual running new attempt '+key)
    need(bool(row.get('first_attempt_terminal')) and bool(row.get('attempt_history')),'historical first-attempt evidence retained '+key)
    workers.append(dict(key=key,actual=actual,request=capture(request_path)[1],ledger=capture(lp)[1],ledger_UTC=current['UTC'],before_Native=prior['measured_Native_Runtime'],after_Native=current['measured_Native_Runtime'],before_calls=len(prior['calls']),after_calls=len(current['calls']),inflight=current['inflight'],last_completed_call=current['calls'][-1],date_status=row['status'],current_attempt=row['current_attempt']))
error=doc(R/'SUPERVISOR_ERROR.json')
need(capture(R/'SUPERVISOR_ERROR.json')[1]['source']==before['prior_supervisor_error'],'original saved supervisor error byte SHA unchanged')
lease=doc(R/'REPAIR_LEASE.json')
need(lease['token']==before['lease_token'] and lease['state']=='RELEASED' and lease['release_reason']=='EXPLICIT_REPAIR_END' and lease['automatic_time_expiry'] is False,'exact reload manual lease explicitly released')
need(datetime.fromisoformat(lease['released_UTC'])>datetime.fromisoformat(reload['UTC']),'lease released after successful actual reload proof')
api_url='http://127.0.0.1:8794/api/status'
with urllib.request.urlopen(api_url,timeout=20) as response:
    status=response.status;api_raw=response.read()
api=json.loads(api_raw);api_dest=RAW/'HTTP8794_API_STATUS_RAW.json'
with api_dest.open('xb') as f:f.write(api_raw)
need(status==200 and api['read_only'] is True and api['supervisor_alive'] is True and api['live_worker_count']==3,'actual HTTP8794 read-only API healthy supervisor and three live workers')
need({w['PID'] for w in api['workers']}=={w['actual']['PID'] for w in workers},'HTTP8794 reports same three actual workers')
task=doc(OUT/'READ_ONLY_SCHEDULED_TASK_OBSERVATION.json');events=doc(OUT/'READ_ONLY_TASK_EVENT_HISTORY_OBSERVATION.json')
report=dict(schema='V42_CONTROLLER_OWNED_HEARTBEAT_IO_RELOAD_INDEPENDENT_READ_ONLY_EXECUTION_AUDIT',PASS=True,UTC=datetime.now(timezone.utc).isoformat(),root=str(R),audit_scope='Independent execution audit after Root coordinator-only reload; no process actions or production changes by reviewer',checks=checks,
    actual_supervisor=actual_sup,prior_supervisor=before['supervisor'],old_exact_supervisor_absent=True,same_three_workers=workers,current_four_control_file_records=controls,control_commit='81a62242',immutable_Source32_SHA=SOURCE,immutable_Source32_declared_source_files=scientific_files,
    root_reload_receipt=capture(R/'autonomous/CONTROLLER_HEARTBEAT_IO_RELOAD_VERIFICATION.json')[1]['source'],owner_final125=capture(OUT/'FULL_NATIVE_DENIED_TEST_RECEIPT_02.json')[1]['source'],independent_final125=capture(Path(r'D:\v42_controller_io_independent_review_20261010_01')/'INDEPENDENT_CONTROLLER_IO_NATIVE_DENIED_REVIEW_RECEIPT.json')[1]['source'],original_error_unchanged=capture(R/'SUPERVISOR_ERROR.json')[1],released_reload_lease=capture(R/'REPAIR_LEASE.json')[1],
    actual_HTTP8794=dict(url=api_url,status=status,snapshot=record(api_dest,api_raw),snapshot_UTC=api['snapshot_UTC'],state=api['state'],worker_PIDs=[w['PID'] for w in api['workers']],live_worker_count=api['live_worker_count']),
    task_settings_observation=capture(OUT/'READ_ONLY_SCHEDULED_TASK_OBSERVATION.json')[1]['source'],task_event_history_observation=capture(OUT/'READ_ONLY_TASK_EVENT_HISTORY_OBSERVATION.json')[1]['source'],task_repetition_intervals=[x['RepetitionInterval'] for x in task['Triggers']],task_RestartCount=task['RestartCount'],task_operational_event_log_enabled=events['IsEnabled'],
    historical_recovery_cause='Prior heartbeat PermissionError13 and later exact coordinator identities were observed. Five-minute trigger is compatible with recovery timing; disabled Operational log provides no event proof. Atomic replacement is plausible, not proven.',
    observation_error_state=cp.get('worker_observation_errors',{}),historical_error_not_erased=True,raw_single_read_snapshots=records,Native_optimize_calls=0,real_Native_model_constructions=0,process_actions=0,queue_manifest_source_immutable_changes=0,git_mutations=0,final_date_PASS_claimed=False,
    limitations='Mutable operational files and API were captured sequentially at stated timestamps; this is not an atomic campaign-wide snapshot. Final scientific PASS and performance are pending. Repo science edits after test completion are outside this audit; immutable D32 worker source is verified.')
target=OUT/'CONTROLLER_HEARTBEAT_IO_RELOAD_INDEPENDENT_ACTUAL_AUDIT.json'
with target.open('x',encoding='utf-8') as f:json.dump(report,f,ensure_ascii=False,indent=2);f.write('\n')
print(json.dumps(dict(PASS=True,receipt=record(target),checks=len(checks),supervisor=actual_sup['PID'],workers=[dict(key=w['key'],PID=w['actual']['PID'],Native=w['after_Native'],calls=w['after_calls']) for w in workers]),ensure_ascii=False))

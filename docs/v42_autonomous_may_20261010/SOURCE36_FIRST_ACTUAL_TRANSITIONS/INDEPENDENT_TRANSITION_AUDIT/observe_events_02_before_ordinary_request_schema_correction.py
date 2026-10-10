"""One bounded read-only observation; empty checks do not create PASS events."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib, json, math, re, traceback, uuid
import psutil
R=Path('D:/v42_may_restart_20261010_02');O=Path(__file__).resolve().parent
S35='a8cb6983fdda381987116936c9a402330111223547abaa64b51408f807ad6a14'
S36='4f1a5980ae897ce1dcfc1ca0fc35836d2a17eddcf3e15df5d587de9f9bd0bf39'
def read(p):return json.loads(Path(p).read_bytes())
def rec(p):
    p=Path(p);h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return dict(path=str(p.resolve()),bytes=p.stat().st_size,sha256=h.hexdigest())
def save(p,obj):
    assert not p.exists();p.write_text(json.dumps(obj,indent=2)+'\n',encoding='utf8');return rec(p)
def ident(pid):
    p=psutil.Process(pid);return dict(PID=p.pid,created=p.create_time(),command=p.cmdline(),cwd=p.cwd())
def exact(r):
    now=rec(r['path']);assert now['bytes']==r['bytes'] and now['sha256']==r['sha256'];return now
def rawcopy(path,folder,name):
    dest=folder/name;assert not dest.exists();dest.write_bytes(Path(path).read_bytes());return rec(dest)
baseline=read(O/'SOURCE36_TRANSITION_INITIAL_BASELINE_RECEIPT.json')
state_path=O/'OBSERVED_EVENT_STATE.json'
state=read(state_path) if state_path.exists() else dict(terminal35={},birth36={},terminal36={},RMP_pre={},RMP_complete={},errors={})
events=[]
def folder(kind,tag):
    p=O/'events'/(kind+'_'+re.sub(r'[^A-Za-z0-9_.-]','_',tag)+'_'+uuid.uuid4().hex[:8]);p.mkdir(parents=True);return p
def common(p):
    cp=read(R/'SUPERVISOR_STATE.json');sup=ident(82852)
    assert sup==baseline['supervisor'] and not psutil.pid_exists(107788)
    meta=read(R/'SUPERVISOR_PROCESS.json');assert all(meta[k]==sup[k] for k in ('PID','created','command'))
    hb=read(R/'SUPERVISOR_HEARTBEAT.json');assert all(hb['process'][k]==sup[k] for k in ('PID','created','command'))
    age=(datetime.now(timezone.utc)-datetime.fromisoformat(hb['timestamp_UTC'])).total_seconds();assert 0<=age<=60
    refs=dict(checkpoint=rawcopy(R/'SUPERVISOR_STATE.json',p,'CHECKPOINT_RAW.json'),
        queue=rawcopy(R/'RECOVERY_QUEUE.json',p,'QUEUE_RAW.json'),heartbeat=rawcopy(R/'SUPERVISOR_HEARTBEAT.json',p,'SUPERVISOR_HEARTBEAT_RAW.json'),
        metadata=rawcopy(R/'SUPERVISOR_PROCESS.json',p,'SUPERVISOR_PROCESS_RAW.json'))
    return dict(supervisor=sup,heartbeat_age_seconds=age,checkpoint_state=cp['state'],retry_streak=cp.get('first_sweep_retry_streak',{}),refs=refs)
def event(p,kind,data):
    d=dict(schema='V42_SOURCE36_ACTUAL_TRANSITION_OBSERVED_EVENT',kind=kind,UTC=datetime.now(timezone.utc).isoformat(),
        event_integrity_verified=True,transition_event_observed=True,
        Native_optimize_calls=0,real_Native_model_constructions=0,modelattempts=[],nativeattempts=[],
        science_or_Case_or_matrix_imports=0,helper_admission_or_test_executions=0,
        production_source_runtime_queue_lease_process_Git_changes=0,
        scientific_final_PASS_or_Source36_performance_claimed=False,**data)
    r=save(p/'EVENT_RECEIPT.json',d);events.append(dict(kind=kind,receipt=r));return r
def terminal(request_path,expected_source,kind,old=None):
    req=read(request_path);path=Path(req['result'])
    if not path.exists():return None
    p=folder(kind,req['attempt_id']);raw=path.read_bytes();result=json.loads(raw)
    assert result['source_SHA']==req['implementation_SHA']==expected_source
    assert all(result['identity'][k]==req[k] for k in ('run_id','arm','day','attempt_id','algorithm_version'))
    assert isinstance(result['PASS'],bool) and result['finished_UTC']
    dest=p/'RESULT_EXACT_RAW.json';dest.write_bytes(raw)
    refs=dict(result=rec(dest),request=rawcopy(request_path,p,'REQUEST_EXACT_RAW.json'))
    ledger_path=Path(request_path).parent/'NATIVE_RUNTIME_LEDGER.json';ledger=None
    if ledger_path.exists():
        refs['ledger']=rawcopy(ledger_path,p,'TERMINAL_NATIVE_ENTIRE_RAW.json');ledger=read(refs['ledger']['path'])
        assert ledger['Native_ceiling_seconds']==5400 and ledger['P2_calls']==0
        if old:
            prior=read(old['ledger_copy']['path']);assert ledger['calls'][:len(prior['calls'])]==prior['calls']
        if 'ledger' in result:exact(result['ledger'])
    for name,artifact_path in [('progress',req['progress']),('error',req['error']),('heartbeat',Path(request_path).parent/'HEARTBEAT.json')]:
        if Path(artifact_path).exists():refs[name]=rawcopy(artifact_path,p,name.upper()+'_RAW.json')
    pid=result['worker']['PID'];alive=psutil.pid_exists(pid)
    r=event(p,kind,dict(observation=common(p),identity=result['identity'],source=expected_source,
        actual_worker_result_PASS=result['PASS'],actual_worker_status=result['status'],result_source=rec(path),
        worker_process_alive_at_observation=alive,worker=result['worker'],known_Native_Runtime=result.get('Native_Runtime'),
        cumulative_Native_unknown=result.get('actual_cumulative_Native_Runtime')=='UNKNOWN',
        original5400_cap_preserved=ledger is not None,measured_Native=ledger.get('measured_Native_Runtime') if ledger else None,
        completed_Native_calls=len(ledger['calls']) if ledger else None,raw_refs=refs,
        original_full_GlobalGap_Actual_Fresh_independent_final_audit_pending=True))
    return r
try:
    cp=read(R/'SUPERVISOR_STATE.json')
    assert ident(82852)==baseline['supervisor']
    for key,old in baseline['workers'].items():
        if key not in state['terminal35']:
            r=terminal(old['request_original']['path'],S35,'SOURCE35_TERMINAL',old)
            if r:state['terminal35'][key]=r
    current36={}
    for key,w in cp.get('workers',{}).items():
        req=read(w['request'])
        if req.get('implementation_SHA')!=S36:continue
        current36[req['attempt_id']]=dict(key=key,worker=w,request=req)
        if req['attempt_id'] in state['birth36']:continue
        ledger_path=Path(w['request']).parent/'NATIVE_RUNTIME_LEDGER.json'
        if not ledger_path.exists():continue
        p=folder('SOURCE36_BIRTH',req['attempt_id']);process=ident(w['PID'])
        assert all(process[k]==w[k] for k in ('PID','created','command')) and Path(process['cwd']).resolve()==Path('D:/v42run36')
        assert req['previous_attempts']==[] and req['native_budget_seconds']==5400 and req['Threads']==1 and req['P2_calls']==0
        assert req['wall_budget_seconds'] is None and req['target_gap']==.03
        request_rec=rec(w['request'])
        declared=next((v['original'] for v in baseline['Source36_fresh_request_records27'].values() if Path(v['original']['path']).resolve()==Path(w['request']).resolve()),None)
        if declared:assert exact(declared)==request_rec
        refs=dict(request=rawcopy(w['request'],p,'REQUEST_EXACT_RAW.json'),ledger=rawcopy(ledger_path,p,'FIRST_OBSERVED_NATIVE_ENTIRE_RAW.json'))
        ledger=read(refs['ledger']['path']);assert ledger['Native_ceiling_seconds']==5400 and ledger['P2_calls']==0 and ledger['prior_attempt'] is None
        assert ledger['historical_costs_reused'] is False
        zero=ledger['measured_Native_Runtime']==0 and ledger['calls']==[] and ledger.get('inflight') is None
        frozen=read(R/'autonomous/V36_SPARSE_IMMUTABLE_FREEZE.json')['source_files'];assert len(frozen)==1111
        verified=[exact(r) for r in frozen];refs['frozen1111']=save(p/'FROZEN36_CURRENT_ALL1111_RECORDS.json',verified)
        state['birth36'][req['attempt_id']]=event(p,'SOURCE36_FRESH_BIRTH',dict(observation=common(p),process=process,
            current_request=request_rec,identity={k:req[k] for k in ('run_id','arm','day','worker_slot','attempt_id')},
            same_sealed27_repair_request=declared is not None,first_sweep_ordinary_request=declared is None,
            previous_attempts=[],native_budget_seconds=5400,Native0_observed=zero,
            measured_Native_at_first_observation=ledger['measured_Native_Runtime'],remaining_Native_at_first_observation=5400-ledger['measured_Native_Runtime'],
            prior_attempt=None,historical_costs_reused=False,original_manifest99_source=S36,
            all1111_frozen_current_source_files_verified=True,raw_refs=refs,
            limitation='Actual zero observed only when zero flag true; requested fresh5400 alone is not an observed zero ledger.'))
    for attempt,birth in state['birth36'].items():
        d=read(birth['path']);request_path=d['current_request']['path'];req=read(request_path)
        if attempt not in state['terminal36']:
            r=terminal(request_path,S36,'SOURCE36_TERMINAL')
            if r:state['terminal36'][attempt]=r
        output=Path(req['output'])
        if not output.exists():continue
        receipts=sorted(output.rglob('RMP_PRESOLVE0_COMPUTATIONAL_ENTRY.json'))
        if not receipts:continue
        entry_path=receipts[0];entry=read(entry_path)
        assert entry['source']['execution_SHA']==S36
        stage=entry.get('status')
        destmap=state['RMP_complete'] if stage in ('COMPLETED','FAILED') else state['RMP_pre']
        if attempt in destmap:continue
        p=folder('SOURCE36_FIRST_RMP_'+str(stage),attempt)
        refs=dict(entry=rawcopy(entry_path,p,'RMP_ENTRY_ENTIRE_RAW.json'),ledger=rawcopy(Path(request_path).parent/'NATIVE_RUNTIME_LEDGER.json',p,'CURRENT_NATIVE_ENTIRE_RAW.json'))
        scale=entry_path.parent/'RMP_NATIVE_ROW_SCALING.json'
        if scale.exists():refs['row_scaling']=rawcopy(scale,p,'RMP_ROW_SCALING_ENTIRE_RAW.json')
        ledger=read(refs['ledger']['path'])
        destmap[attempt]=event(p,'SOURCE36_FIRST_RMP_'+str(stage),dict(observation=common(p),attempt=attempt,
            request=rec(request_path),source=S36,entry_source=rec(entry_path),raw_refs=refs,
            computational_Method=entry.get('exact_selected_computational_Method'),actual_parameters=entry.get('actual_parameters'),
            warm_start=entry.get('current_attempt_warm_start'),Native_call_completed=entry.get('Native_call_completed'),
            completed_original_Native_call=entry.get('completed_original_Native_call'),entry_error=entry.get('error'),
            current_ledger_inflight=ledger.get('inflight'),completed_RMP_calls=[c for c in ledger['calls'] if c.get('track')=='RMP'],
            requires_scientific_result_review=True,
            limitation='PreNative receipt is admission only. COMPLETED is accounting completion, not solver OPTIMAL/finitePi/GlobalLB/finalPASS. FAILED may follow actual Native entry.'))
except BaseException as error:
    signature=repr(error)
    if signature not in state['errors']:
        p=folder('READONLY_OBSERVATION_ERROR','error')
        r=save(p/'OBSERVATION_ERROR_RECEIPT.json',dict(PASS=False,UTC=datetime.now(timezone.utc).isoformat(),
            error=signature,traceback=traceback.format_exc(),Native_optimize_calls=0,real_Native_model_constructions=0,
            production_source_runtime_queue_lease_process_Git_changes=0,scope='Read-only observation failure; no fake empty or successful event.'))
        state['errors'][signature]=r;events.append(dict(kind='READONLY_OBSERVATION_ERROR',receipt=r))
if events:
    state_path.write_text(json.dumps(state,indent=2)+'\n',encoding='utf8')
    print(json.dumps(dict(observed_events=events),indent=2))
else:print('NO_NEW_TRANSITION_TERMINAL_BIRTH_RMP_OR_ERROR_EVENT')

"""Read-only existing receipts, raw source hashes, OS and HTTP observation."""
from pathlib import Path
from datetime import datetime, timezone
from fractions import Fraction
import hashlib, json, math, traceback, urllib.request
import psutil

R=Path('D:/v42_may_restart_20261010_02'); A=R/'autonomous'
C=Path('D:/MobileESS_v42_autonomous'); O=Path(__file__).resolve().parent
SCI35='a8cb6983fdda381987116936c9a402330111223547abaa64b51408f807ad6a14'
SCI36='4f1a5980ae897ce1dcfc1ca0fc35836d2a17eddcf3e15df5d587de9f9bd0bf39'
def read(p):return json.loads(Path(p).read_bytes())
def rec(p):
    p=Path(p); h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return dict(path=str(p.resolve()),bytes=p.stat().st_size,sha256=h.hexdigest())
def save_raw(p,name):
    dest=O/name; assert not dest.exists(); dest.write_bytes(Path(p).read_bytes()); return rec(dest)
def save(name,obj):
    dest=O/name; assert not dest.exists(); dest.write_text(json.dumps(obj,indent=2)+'\n',encoding='utf8');return rec(dest)
def exact(record):
    now=rec(record['path']);assert now['sha256']==record['sha256'] and now['bytes']==record['bytes'];return now
def identity(pid):
    p=psutil.Process(pid);return dict(PID=p.pid,created=p.create_time(),command=p.cmdline(),cwd=p.cwd())
def byte_records(mapping,base=None):
    records={}
    for name,expected in mapping.items():
        p=Path(name) if base is None else base/name; record=rec(p)
        assert record['sha256']==expected,(str(p),'source drift')
        records[name]=record
    return records

result=dict(schema='V42_FIRST_SWEEP_FAIRNESS_ACTUAL_RELOAD_INDEPENDENT_READONLY_AUDIT',PASS=False,
    started_UTC=datetime.now(timezone.utc).isoformat(),Native_optimize_calls=0,
    real_Native_model_constructions=0,modelattempts=[],nativeattempts=[],
    science_or_Case_or_matrix_imports=0,helper_executions=0,tests_or_admissions_executed=0,
    production_source_control_queue_lease_process_Git_changes=0,
    actual_fairness_dispatch_actions_claimed=False,actual_Source36_performance_or_final_scientific_PASS_claimed=False)
try:
    producer=A/'CONTROLLER_RETRY_FAIRNESS_RELOAD_VERIFICATION.json'
    assert rec(producer)['sha256']=='b9a97ecf2fc87bb7912f91f809db9fe5cba7afb015690c94ad07ec28ba581041'
    proof=read(producer);assert proof['PASS'] is True
    before=read(exact(proof['before'])['path']);launch=read(exact(proof['launch'])['path'])
    helper=A/'reload_owned_supervisor_retry_fairness.py'
    assert rec(helper)['sha256']=='d63598af0bb842b681db5b3e5a0354020dcf48917699122748b14b8cc2180f87'
    refs=dict(producer=save_raw(producer,'PRODUCER_VERIFICATION_EXACT_COPY.json'),
        before=save_raw(proof['before']['path'],'PRODUCER_BEFORE_EXACT_COPY.json'),
        launch=save_raw(proof['launch']['path'],'PRODUCER_LAUNCH_EXACT_COPY.json'),
        helper=save_raw(helper,'UNEXECUTED_BY_REVIEWER_ROOT_EXECUTED_HELPER_EXACT_COPY.py'))
    assert before['supervisor']['PID']==107788 and not psutil.pid_exists(107788)
    assert before['typed_live_OS_mutex_refusal']['type']=='LockBusy' and before['typed_live_OS_mutex_refusal']['errno']==13
    assert 0<=before['heartbeat_age_seconds']<=60
    supervisor=identity(82852);assert supervisor==proof['actual_supervisor']
    metadata=read(R/'SUPERVISOR_PROCESS.json')
    assert all(metadata[k]==supervisor[k] for k in ('PID','created','command'))
    assert launch['PID']==82852 and launch['command']==supervisor['command']
    assert supervisor['command'][1:]==['-B','-X','utf8','-m','v42_autonomous.supervisor',str(R)]
    assert Path(supervisor['cwd']).resolve()==C
    owned=[]
    for p in psutil.process_iter(['pid','cmdline']):
        cmd=p.info['cmdline'] or []
        if cmd[1:]==supervisor['command'][1:]:owned.append(identity(p.pid))
    assert owned==[supervisor],owned
    heartbeat_raw=(R/'SUPERVISOR_HEARTBEAT.json').read_bytes();heartbeat=json.loads(heartbeat_raw)
    for k in ('PID','created','command'):assert heartbeat['process'][k]==supervisor[k]
    stamp=datetime.fromisoformat(heartbeat['timestamp_UTC']);assert stamp.tzinfo is not None
    age=(datetime.now(timezone.utc)-stamp).total_seconds();assert 0<=age<=60 and heartbeat['state']=='B2_RUNNING'
    refs['heartbeat']=save_raw(R/'SUPERVISOR_HEARTBEAT.json','CURRENT_HEARTBEAT_RAW.json')
    refs['supervisor_metadata']=save_raw(R/'SUPERVISOR_PROCESS.json','CURRENT_SUPERVISOR_PROCESS_RAW.json')
    cp=read(R/'SUPERVISOR_STATE.json');refs['checkpoint']=save_raw(R/'SUPERVISOR_STATE.json','CURRENT_CHECKPOINT_RAW.json')
    assert cp['state']=='B2_RUNNING' and cp['parallel_workers']==3 and cp['first_sweeps_completed']=={}
    streak=cp.get('first_sweep_retry_streak',{})
    for arm,value in streak.items():assert arm in ('B2','B3') and type(value) is int and 0<=value<=({'B2':2,'B3':1}[arm])
    assert set(cp['workers'])==set(before['workers'])=={'B2/2025-05-01','B2/2025-05-02','B2/2025-05-03'}
    workers={}
    for key,expected in before['workers'].items():
        process=identity(expected['PID']);assert process==expected==proof['actual_workers'][key]
        current=cp['workers'][key]
        assert all(current[k]==process[k] for k in ('PID','created','command'))
        request_rec=exact(before['requests'][key]);assert request_rec==proof['exact_request_records_preserved'][key]
        assert Path(current['request']).resolve()==Path(request_rec['path']).resolve()
        request=read(request_rec['path']);assert request['implementation_SHA']==SCI35 and request['previous_attempts']==[] and request['native_budget_seconds']==5400
        assert request['arm']=='B2' and key=='B2/'+request['day'] and Path(process['cwd']).resolve()==Path('D:/v42run35')
        name='CONTROLLER_FAIRNESS_RELOAD_'+key.replace('/','_')+'_NATIVE_BEFORE.json'
        baseline_path=A/name;baseline=read(baseline_path)
        assert len(baseline['calls'])==before['Native_call_counts'][key] and baseline['measured_Native_Runtime']==before['measured_Native'][key]
        refs[key+'_baseline']=save_raw(baseline_path,key.replace('/','_')+'_BASELINE_NATIVE_RAW.json')
        ledger_path=Path(request_rec['path']).parent/'NATIVE_RUNTIME_LEDGER.json';raw=ledger_path.read_bytes();ledger=json.loads(raw)
        dest=O/(key.replace('/','_')+'_CURRENT_NATIVE_RAW.json');assert not dest.exists();dest.write_bytes(raw);refs[key+'_current']=rec(dest)
        assert ledger['calls'][:len(baseline['calls'])]==baseline['calls']
        assert ledger['measured_Native_Runtime']>=proof['Native_after'][key]>=baseline['measured_Native_Runtime']
        assert ledger['P2_calls']==0 and ledger['Native_ceiling_seconds']==5400
        workers[key]=dict(process=process,request=request_rec,attempt=request['attempt_id'],source=SCI35,
            baseline_completed_calls=len(baseline['calls']),current_completed_calls=len(ledger['calls']),
            measured_Native_Runtime=ledger['measured_Native_Runtime'],prefix_preserved=True,inflight=ledger.get('inflight'))
    error_record=exact(before['prior_supervisor_error']);prior_record=exact(before['prior_error_raw_copy'])
    assert error_record['sha256']==prior_record['sha256'] and proof['old_error_evidence_unchanged'] is True
    assert Path(error_record['path']).read_bytes()==Path(prior_record['path']).read_bytes()
    refs['error_current']=save_raw(error_record['path'],'CURRENT_PUBLIC_SUPERVISOR_ERROR_RAW.json')
    refs['error_preserved']=save_raw(prior_record['path'],'ROOT_PRIOR_SUPERVISOR_ERROR_EXACT_COPY.json')
    controls={k:exact(v) for k,v in proof['control_files'].items()};assert controls==before['control_files']
    assert controls['v42_autonomous/supervisor.py']['sha256']=='cce72776da0e8f31d834f63fc9530e9894eb77a5164c694b7a9a937a2de1c77a'
    manifest=read(R/'B2_V36_ZERO_START_DEPLOYMENT_MANIFEST.json')
    source_before=dict(original=byte_records(manifest['builder_original_sources'],C),execution=byte_records(manifest['execution_sources'],C))
    assert len(source_before['original'])==1007 and len(source_before['execution'])==99
    frozen={}
    for version in ('35','36'):
        freeze=read(A/('V'+version+'_SPARSE_IMMUTABLE_FREEZE.json'));assert len(freeze['source_files'])==1111
        frozen[version]=[exact(item) for item in freeze['source_files']]
    refs['source_records']=save('SCIENCE_ORIGINAL1007_EXECUTION99_AND_FROZEN35_36_EACH1111_RECORDS.json',dict(current_repo=source_before,frozen=frozen))
    qraw=(R/'RECOVERY_QUEUE.json').read_bytes();queue=json.loads(qraw)
    qdest=O/'CURRENT_RECOVERY_QUEUE_RAW.json';assert not qdest.exists();qdest.write_bytes(qraw);refs['queue']=rec(qdest)
    ready=[row for row in queue['entries'] if row['verification_status']=='READY_VERIFIED_REPAIR']
    original_queue=read(Path('D:/v42_source36_deployment_independent_audit_20261010_01/RECOVERY_QUEUE_SNAPSHOT.json'))
    old_ready=[row for row in original_queue['entries'] if row['verification_status']=='READY_VERIFIED_REPAIR']
    assert len(ready)==len(old_ready)==9 and ready==old_ready
    assert {row['date'] for row in ready}=={f'2025-05-{i:02d}' for i in range(1,10)}
    assert all(row['repair_source_SHA']==SCI36 and row['new_worker_PID'] is None for row in ready)
    leasepath=R/'repair_leases/705bf36e5f9a489bb9b0121ce2844fca.json'
    lease=read(leasepath);assert lease['token']==before['lease_token']=='705bf36e5f9a489bb9b0121ce2844fca'
    assert lease['state']=='RELEASED' and lease['released_UTC']=='2026-10-10T00:54:59.422107+00:00' and lease['owner'] is None
    refs['historical_lease']=save_raw(leasepath,'ROOT_RELOAD_HISTORICAL_RELEASED_LEASE_EXACT_COPY.json')
    refs['current_global_lease']=save_raw(R/'REPAIR_LEASE.json','CURRENT_GLOBAL_LEASE_OBSERVATION_RAW.json')
    with urllib.request.urlopen('http://127.0.0.1:8794/api/status',timeout=5) as response:
        assert response.status==200;api_raw=response.read()
    api=json.loads(api_raw);dest=O/'CURRENT_API_STATUS_RAW.json';assert not dest.exists();dest.write_bytes(api_raw);refs['API']=rec(dest)
    assert api['supervisor_alive'] is True and api['live_worker_count']==3
    rows=api['rows'][:3];assert {row['day'] for row in rows}=={'2025-05-01','2025-05-02','2025-05-03'}
    bounds=[]
    for row in rows:
        key='B2/'+row['day'];b2=row['B2'];bound=b2['bounds']
        assert b2['source_SHA']==SCI35 and b2['current_attempt']==workers[key]['attempt'] and b2['error'] is None
        assert bound['status']=='CERTIFIED' and bound['scope']=='ORIGINAL_FULL_GLOBAL'
        U=Fraction(bound['evidence']['UB']['exact']);L=Fraction(bound['evidence']['LB']['exact'])
        assert U>0 and 0<L<=U and math.isclose(bound['gap'],float((U-L)/abs(U)),rel_tol=0,abs_tol=1e-15)
        for e in bound['evidence'].values():
            if isinstance(e,dict) and 'path' in e and 'sha256' in e:assert rec(e['path'])['sha256']==e['sha256']
        bounds.append(dict(day=row['day'],UB=bound['UB'],LB=bound['LB'],gap=bound['gap'],status=bound['status'],exact_gap=str((U-L)/abs(U)),existing_display_evidence_only=True))
    source_after=dict(original=byte_records(manifest['builder_original_sources'],C),execution=byte_records(manifest['execution_sources'],C))
    assert source_before==source_after and all(exact(item)==item for records in frozen.values() for item in records)
    assert all(exact(v)==v for v in controls.values()) and identity(82852)==supervisor
    snapshot=save('CURRENT_OS_READONLY_SNAPSHOT.json',dict(UTC=datetime.now(timezone.utc).isoformat(),supervisor=supervisor,sole_owned_controller_processes=owned,old107788_absent=True,workers=workers,heartbeat_age_seconds=age,checkpoint_state=cp['state'],checkpoint_retry_streak=streak,first_sweeps_completed=cp['first_sweeps_completed']))
    result.update(PASS=True,producer=rec(producer),helper=rec(helper),raw_refs=refs,OS_snapshot=snapshot,
        actual_supervisor=supervisor,old107788_absent=True,sole_owned82852=True,recent_matching_heartbeat_age_seconds=age,
        state='B2_RUNNING',loaded_command_and_current_source_file_binding=controls,
        loaded_code_not_memory_inspected=True,worker_observations=workers,all3_current_PID_create_command_cwd_request_and_completed_Native_prefixes_preserved=True,
        old_public_supervisor_error_byte_identical=error_record,current_nine_Source36_READY_records_unchanged=ready,
        current_checkpoint_retry_streak=streak,actual_fairness_dispatch_not_yet_observed=True,
        historical_reload_lease_released=lease,original1007_execution99_source_start_end_identical=True,
        frozen35_and36_each1111_exact_start_end=True,current_API_rows=bounds,
        limitations=['PID/command/cwd/current source SHA and Root launch binding verified; process memory bytecode not inspected.',
            'All current slots remain occupied by unchanged Source35 workers; no new fairness retry/ordinary dispatch observed.',
            'Current API certificate evidence and exact scalar gap checked; no Case/matrix reconstruction or new independent full checker replay.',
            'No Source36 Native performance, improved GlobalLB, GlobalGap<=.03, or original FULL/Actual/Fresh final PASS claimed.'])
except BaseException as error:result.update(error=repr(error),traceback=traceback.format_exc())
result['finished_UTC']=datetime.now(timezone.utc).isoformat()
receipt=save('FIRST_SWEEP_FAIRNESS_ACTUAL_RELOAD_INDEPENDENT_READONLY_AUDIT.json',result)
print(json.dumps(dict(PASS=result['PASS'],receipt=receipt,error=result.get('error')),indent=2))
raise SystemExit(0 if result['PASS'] else 1)

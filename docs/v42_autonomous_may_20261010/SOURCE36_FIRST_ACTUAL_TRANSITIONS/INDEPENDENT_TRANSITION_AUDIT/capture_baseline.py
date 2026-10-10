"""Existing byte evidence and OS observation only; no science imports."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib, json, psutil
R=Path('D:/v42_may_restart_20261010_02'); C=Path('D:/MobileESS_v42_autonomous')
O=Path(__file__).resolve().parent
S35='a8cb6983fdda381987116936c9a402330111223547abaa64b51408f807ad6a14'
S36='4f1a5980ae897ce1dcfc1ca0fc35836d2a17eddcf3e15df5d587de9f9bd0bf39'
def rec(p):
    p=Path(p);h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return dict(path=str(p.resolve()),bytes=p.stat().st_size,sha256=h.hexdigest())
def read(p):return json.loads(Path(p).read_bytes())
def rawcopy(p,name):
    dest=O/name;assert not dest.exists();dest.write_bytes(Path(p).read_bytes());return rec(dest)
def save(name,d):
    dest=O/name;assert not dest.exists();dest.write_text(json.dumps(d,indent=2)+'\n',encoding='utf8');return rec(dest)
def ident(pid):
    p=psutil.Process(pid);return dict(PID=p.pid,created=p.create_time(),command=p.cmdline(),cwd=p.cwd())
def exact(r):
    now=rec(r['path']);assert now['sha256']==r['sha256'] and now['bytes']==r['bytes'];return now
cpraw=(R/'SUPERVISOR_STATE.json').read_bytes();cp=json.loads(cpraw)
refs=dict(checkpoint=save('BASELINE_CHECKPOINT_RAW.json',cp),queue=rawcopy(R/'RECOVERY_QUEUE.json','BASELINE_RECOVERY_QUEUE_RAW.json'),
    supervisor_metadata=rawcopy(R/'SUPERVISOR_PROCESS.json','BASELINE_SUPERVISOR_PROCESS_RAW.json'),
    heartbeat=rawcopy(R/'SUPERVISOR_HEARTBEAT.json','BASELINE_SUPERVISOR_HEARTBEAT_RAW.json'),
    public_error=rawcopy(R/'SUPERVISOR_ERROR.json','BASELINE_PUBLIC_SUPERVISOR_ERROR_RAW.json'))
sup=ident(82852);assert sup['command'][1:]==['-B','-X','utf8','-m','v42_autonomous.supervisor',str(R)] and Path(sup['cwd']).resolve()==C
meta=read(R/'SUPERVISOR_PROCESS.json');assert all(meta[k]==sup[k] for k in ('PID','created','command'))
assert cp['state']=='B2_RUNNING' and set(cp['workers'])=={'B2/2025-05-01','B2/2025-05-02','B2/2025-05-03'}
workers={}
for key,w in cp['workers'].items():
    live=ident(w['PID']);assert all(live[k]==w[k] for k in ('PID','created','command')) and Path(live['cwd']).resolve()==Path('D:/v42run35')
    req=read(w['request']);assert req['implementation_SHA']==S35 and req['native_budget_seconds']==5400 and req['previous_attempts']==[]
    tag=key.replace('/','_');request=rawcopy(w['request'],tag+'_SOURCE35_REQUEST_RAW.json')
    ledger_path=Path(w['request']).parent/'NATIVE_RUNTIME_LEDGER.json';raw=ledger_path.read_bytes();ledger=json.loads(raw)
    dest=O/(tag+'_SOURCE35_BASELINE_NATIVE_RAW.json');assert not dest.exists();dest.write_bytes(raw)
    assert ledger['P2_calls']==0 and ledger['Native_ceiling_seconds']==5400 and not Path(req['result']).exists()
    workers[key]=dict(process=live,worker=w,request_original=rec(w['request']),request_copy=request,
        ledger_original=str(ledger_path),ledger_copy=rec(dest),completed_calls=len(ledger['calls']),
        measured_Native_Runtime=ledger['measured_Native_Runtime'],inflight=ledger.get('inflight'),
        result_path=req['result'],output=req['output'],terminal_result_observed=False)
q=read(R/'RECOVERY_QUEUE.json');ready=[v for v in q['entries'] if v['verification_status']=='READY_VERIFIED_REPAIR']
assert len(ready)==9 and all(v['repair_source_SHA']==S36 and v['new_worker_PID'] is None for v in ready)
requests={}
for row in ready:
    for receipt in [row['retry_request_receipt'],*row.get('retry_request_receipts_by_slot',{}).values()]:
        exact(receipt);req=read(receipt['path']);tag=req['day']+'_s'+str(req['worker_slot'])
        if tag in requests:continue
        assert req['implementation_SHA']==S36 and req['previous_attempts']==[] and req['native_budget_seconds']==5400
        requests[tag]=dict(original=receipt,copy=rawcopy(receipt['path'],'UNSTARTED_SOURCE36_'+tag+'_REQUEST_RAW.json'),
            result_path=req['result'],output=req['output'],result_exists=Path(req['result']).exists(),output_exists=Path(req['output']).exists())
assert len(requests)==27 and all(not r['result_exists'] and not r['output_exists'] for r in requests.values())
manifest=read(R/'B2_V36_ZERO_START_DEPLOYMENT_MANIFEST.json');science={}
for label,key in [('original1007','builder_original_sources'),('execution99','execution_sources')]:
    science[label]={}
    for name,sha in manifest[key].items():
        r=rec(C/name);assert r['sha256']==sha;science[label][name]=r
assert len(science['original1007'])==1007 and len(science['execution99'])==99
frozen={}
for v in ('35','36'):
    f=read(R/('autonomous/V'+v+'_SPARSE_IMMUTABLE_FREEZE.json'));frozen[v]=[exact(r) for r in f['source_files']];assert len(frozen[v])==1111
refs['science_records']=save('BASELINE_SCIENCE1007_EXEC99_FROZEN35_36_EACH1111_RECORDS.json',dict(science=science,frozen=frozen))
refs['OS']=save('BASELINE_OS_READONLY_SNAPSHOT.json',dict(UTC=datetime.now(timezone.utc).isoformat(),supervisor=sup,workers={k:v['process'] for k,v in workers.items()},checkpoint_state=cp['state'],first_sweep_retry_streak=cp.get('first_sweep_retry_streak',{})))
baseline=dict(schema='V42_SOURCE36_ACTUAL_TRANSITION_INITIAL_BASELINE_ONLY',UTC=datetime.now(timezone.utc).isoformat(),
    baseline_integrity_verified=True,observed_transition_event_count=0,transition_event_PASS=None,
    Source35_current_all3_running=True,Source36_current_READY9=True,Source36_actual_worker_birth_observed=False,
    supervisor=sup,workers=workers,Source36_READY_rows=ready,Source36_fresh_request_records27=requests,raw_refs=refs,
    Native_optimize_calls=0,real_Native_model_constructions=0,modelattempts=[],nativeattempts=[],
    science_or_Case_or_matrix_imports=0,production_queue_runtime_lease_source_test_process_Git_changes=0,
    scientific_final_PASS_or_Source36_performance_claimed=False,
    limitation='Baseline preservation only. No natural terminal, fresh Source36 birth or first RMP event has yet been observed.')
r=save('SOURCE36_TRANSITION_INITIAL_BASELINE_RECEIPT.json',baseline);print(json.dumps(r))

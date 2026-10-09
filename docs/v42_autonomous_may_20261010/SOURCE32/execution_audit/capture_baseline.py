"""Single-read deployment baseline; no production or process mutations."""
from pathlib import Path
import json,hashlib
from datetime import datetime,timezone
import psutil

ROOT=Path('D:/v42_may_restart_20261010_02');OUT=Path(__file__).parent
RAW=OUT/'baseline_raw';RAW.mkdir(exist_ok=False)
records=[];cache={}
def rec(path,data):return dict(path=str(path),bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
def snapshot(path):
    path=Path(path).resolve()
    if path in cache:return cache[path]
    data=path.read_bytes();target=RAW/(f'{len(records):03d}_'+path.name)
    with target.open('xb') as stream:stream.write(data)
    record=dict(source=rec(path,data),snapshot=rec(target,data),source_read_count=1)
    records.append(record);cache[path]=(json.loads(data.decode('utf-8-sig')),record)
    return cache[path]
cp,cp_rec=snapshot(ROOT/'SUPERVISOR_STATE.json')
registry,_=snapshot(ROOT/'AUTONOMOUS_MANIFEST.json')
queue,_=snapshot(ROOT/'RECOVERY_QUEUE.json')
supervisor_doc,supervisor_rec=snapshot(ROOT/'SUPERVISOR_PROCESS.json')
workers=[]
for key,row in cp['workers'].items():
    request,request_rec=snapshot(row['request']);attempt=Path(row['request']).parent
    ledger,ledger_rec=snapshot(attempt/'NATIVE_RUNTIME_LEDGER.json')
    p=psutil.Process(row['PID']);actual=dict(PID=p.pid,create_time=p.create_time(),cmdline=p.cmdline(),cwd=p.cwd())
    assert abs(actual['create_time']-row['created'])<.001 and actual['cmdline']==row['command']
    assert Path(actual['cwd']).resolve()==Path('D:/v42run30').resolve()
    assert request['implementation_SHA']==row['source_SHA'] and actual['cmdline'][-1]==row['request']
    workers.append(dict(key=key,controller=row,process=actual,request=request_rec,ledger=ledger_rec,
        Native_Runtime=ledger.get('measured_native_runtime',ledger.get('measured_Native_Runtime')),calls=ledger['calls'],inflight=ledger.get('inflight')))
assert {x['key'] for x in workers}=={'B2/2025-05-04','B2/2025-05-05','B2/2025-05-06'}
prior_path=Path('D:/v42_full_lp_warmstart_readonly_review_20261010_01/SOURCE32_OPERATIONAL_HELPERS_STATIC_READ_ONLY_REVIEW.json')
prior,prior_rec=snapshot(prior_path)
prior_workers={row['key']:row for row in prior['current_worker_snapshot']}
for row in workers:
    before=prior_workers[row['key']]
    assert before['observed']==dict(PID=row['process']['PID'],create_time=row['process']['create_time'],cmdline=row['process']['cmdline'],cwd=row['process']['cwd'])
    assert before['request']==row['request']['source']
ready=[row for row in queue['entries'] if row['verification_status']=='READY_VERIFIED_REPAIR']
doc=dict(PASS=True,UTC=datetime.now(timezone.utc).isoformat(),schema='V42_SOURCE32_PRE_ENQUEUE_BASELINE',
    current_future_code_root=registry['B2_code_root'],workers=workers,ready=ready,supervisor_record=supervisor_rec,
    prior_helper_review=prior_rec,prior_helper_process_request_identities_match=True,
    raw_ledger_capture_time_is_this_baseline_not_prior_helper_review=True,raw_records=records,
    Native_optimize_calls=0,model_constructions=0,production_immutable_queue_manifest_changes=0,process_actions=0)
target=OUT/'SOURCE32_PRE_ENQUEUE_NATIVE_CONTINUITY_BASELINE.json'
with target.open('x',encoding='utf-8') as stream:json.dump(doc,stream,ensure_ascii=False,indent=2);stream.write('\n')
data=target.read_bytes();print(json.dumps(dict(PASS=True,receipt=rec(target,data),workers=[dict(day=x['key'],PID=x['process']['PID'],Native=x['Native_Runtime'],calls=len(x['calls'])) for x in workers],READY=len(ready)),ensure_ascii=False))

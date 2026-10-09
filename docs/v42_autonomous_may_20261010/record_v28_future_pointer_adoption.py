"""Observe live immutable workers and the verified future deployment only."""
import json,sys
from pathlib import Path
import psutil
sys.path.insert(0,'D:/MobileESS_v42_autonomous')
from v42_b2_seed_recovery_v19.common import read,record,atomic,now
ROOT=Path('D:/v42_may_restart_20261010_02')
SOURCE28='0f56f65e266b55354cb29db2be65a8fa2f77d0cc26222e1e1eb1736606fa012d'
SOURCE27='889e3508e3d267a648251ecf48f143d9288adaca8e2f208b15a07d326485a98f'
registry=read(ROOT/'AUTONOMOUS_MANIFEST.json')
assert registry['B2_source_SHA']==SOURCE28
assert registry['B2_code_root']==r'D:\v42run28'
assert registry['B2_workers']==3 and registry['B3_workers']==1
prepared=read(ROOT/'autonomous/V28_ZERO_START_RETRY_PREPARATION.json')
deployed=read(ROOT/'autonomous/V28_ZERO_START_RETRY_DEPLOYMENT.json')
assert prepared['PASS'] is True and deployed['PASS'] is True
for receipt in (prepared['deployment'],prepared['validation'],deployed['deployment'],deployed['validation']):
    assert record(receipt['path'])==receipt
cp=read(ROOT/'SUPERVISOR_STATE.json')
assert len(cp['workers'])==3
expected={'2025-05-01':69164,'2025-05-02':106548,'2025-05-03':98068}
workers=[]
for day,pid in expected.items():
    w=cp['workers']['B2/'+day]
    assert w['PID']==pid and w['source_SHA']==SOURCE27
    p=psutil.Process(pid)
    assert abs(p.create_time()-w['created'])<0.001
    assert p.cmdline()==w['command'] and Path(p.cwd()).resolve()==Path('D:/v42run27').resolve()
    request=read(w['request'])
    assert request['implementation_SHA']==SOURCE27 and request['previous_attempts']==[]
    assert request['restart_from_zero'] is True
    ledger_path=Path(w['request']).parent/'NATIVE_RUNTIME_LEDGER.json'
    ledger=read(ledger_path)
    workers.append(dict(day=day,worker=w,request=record(w['request']),
        ledger=record(ledger_path),current_native_runtime=ledger.get('Native_Runtime'),
        original_source_preserved=True,process_identity_MATCH=True))
supervisor=read(ROOT/'SUPERVISOR_PROCESS.json')
assert supervisor['PID']==87676
p=psutil.Process(supervisor['PID'])
assert abs(p.create_time()-supervisor['created'])<0.001 and p.cmdline()==supervisor['command']
assert Path(p.cwd()).resolve()==Path('D:/MobileESS_v42_autonomous').resolve()
heartbeat=read(ROOT/'SUPERVISOR_HEARTBEAT.json')
assert heartbeat['process']['PID']==87676 and heartbeat['state']=='B2_RUNNING'
queue=read(ROOT/'RECOVERY_QUEUE.json')
entries=[e for e in queue['entries'] if e['repair_source_SHA']==SOURCE28]
assert len(entries)==9
for e in entries:
    assert e['verification_status']=='READY_VERIFIED_REPAIR'
    assert e['initial_native_runtime']==0 and e['remaining_native_seconds']==5400
    assert e['restart_from_zero'] is True and e['previous_checkpoint_reuse'] is False
    assert e['previous_native_budget_carry'] is False and e['new_worker_PID'] is None
    assert e['retry_priority']==(1000 if e['date'][-2:] in ('01','02','03') else 100)
doc=dict(schema='V42_V28_FUTURE_POINTER_AND_ACTIVE_WORKER_OBSERVATION',PASS=True,UTC=now(),
    registry=record(ROOT/'AUTONOMOUS_MANIFEST.json'),deployment=record(ROOT/'B2_V28_ZERO_START_DEPLOYMENT_MANIFEST.json'),
    preparation=record(ROOT/'autonomous/V28_ZERO_START_RETRY_PREPARATION.json'),
    queue_deployment=record(ROOT/'autonomous/V28_ZERO_START_RETRY_DEPLOYMENT.json'),
    actual_workers=workers,supervisor=supervisor,heartbeat=heartbeat,
    queue=[dict(date=e['date'],queue_id=e['queue_id'],status=e['verification_status'],
        initial_native_runtime=e['initial_native_runtime'],remaining_native_seconds=e['remaining_native_seconds'],priority=e['retry_priority']) for e in entries],
    registry_reread_each_existing_cycle=True,supervisor_restart_needed=False,
    supervisor_termination=False,worker_termination=False,hotpatch=False,
    Native_optimize_calls=0,model_constructions=0,actual_Source28_Native_started=False,
    actual_Source28_performance_or_final_PASS_claimed=False,first_three_final_PASS_pending=True,
    source_script=record(__file__))
target=ROOT/'autonomous/V28_FUTURE_POINTER_ACTIVE_WORKER_VERIFICATION.json'
assert not target.exists()
atomic(target,doc)
print(json.dumps(dict(PASS=True,receipt=record(target),worker_PIDs=expected,Source28_READY_count=len(entries))))

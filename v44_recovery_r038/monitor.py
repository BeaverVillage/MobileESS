"""Report preparation and resumed Actual workers without mislabelling the barrier."""
from pathlib import Path
import json,sqlite3,psutil
from v44.common import read,record,verify,atomic,now
from v44.locks import alive
from v44.config import DAYS,ARMS
from . import operations as op

def optional(path):return read(path) if Path(path).exists() else None

def collect():
    op.validate();handoff=read(op.OPS/'CURRENT_HANDOFF.json');cases=[];active=[]
    dispatch=op.states(op.CAMPAIGN)
    for day in DAYS:
        for arm in ARMS:
            p=op.latest(op.CAMPAIGN,day,arm);item=dict(day=day,arm=arm,status='READY')
            if p:
                result=optional(p/'RESULT.json') or {};start=optional(p/'ACTUAL_START.json')
                if not start or not alive(start):start=optional(p/'START.json')
                item.update(root=str(p),attempt=p.name,status=result.get('status','UNSEALED_DEAD_WORKER'),PASS=result.get('PASS',False))
                if start and alive(start):
                    progress=optional(p/'progress.json') or {};stage=progress.get('stage','STARTING')
                    item.update(status='RUNNING',pid=start['pid'],stage=stage,worker_slot=start.get('parallel_actual_slot',1))
                    folder=p/('ACTUAL' if stage=='ACTUAL_FRESH' else stage)
                    details=dict(item,progress=optional(folder/'progress.json'),heartbeat=optional(folder/'HEARTBEAT.json'))
                    for label in ('K48','JOINT'):
                        ledger=optional(folder/(label+'_NATIVE_LEDGER.json'))
                        if ledger:details[label]=dict(measured_seconds=ledger['measured_Native_Runtime'],ceiling_seconds=ledger['Native_ceiling_seconds'],inflight=ledger['inflight'],last_Native_call=ledger['calls'][-1] if ledger['calls'] else {})
                    active.append(details)
                elif result.get('status')=='PRE_ACTUAL_READY':item['status']='PRE_ACTUAL_READY'
                elif dispatch.get((day,arm))=='READY' and not result.get('PASS'):item['status']='RETRY_READY'
                for key in ('error','Actual96_execution_PASS','Fresh96_physical_PASS','Fresh_violations','peak_line_phase_loading','M_gap_certified'):
                    if key in result:item[key]=result[key]
            cases.append(item)
    auto={}
    db=Path('C:/Users/kjw39/.codex/sqlite/codex-dev.db')
    with sqlite3.connect(db.as_uri()+'?mode=ro',uri=True) as connection:
        connection.row_factory=sqlite3.Row
        row=connection.execute('select id,status,kind,rrule,target_thread_id,next_run_at,last_run_at from automations where id=?',('v44-may-campaign-autonomous-recovery',)).fetchone()
        if row:auto=dict(row)
    counts=dict(PASS=sum(r.get('PASS') is True for r in cases),FAIL=sum(r['status'] in ('FAILED','BLOCKED','BLOCKED_DEPENDENCY') for r in cases),
        RUNNING=len(active),WAITING=sum(not r.get('PASS') and r['status']!='RUNNING' for r in cases),
        RECOVERY_QUEUED=sum(r['status']=='RETRY_READY' for r in cases),PRE_ACTUAL_READY=sum(r['status']=='PRE_ACTUAL_READY' for r in cases))
    lease=read(op.CAMPAIGN/'COORDINATOR_LEASE.json')
    value=dict(UTC=now(),active_revision=handoff['active_revision'],pending_revision=handoff.get('pending_revision'),automation=auto,
        counts=counts,cases=cases,active=active,coordinator_alive=alive(lease),coordinator=lease,
        r038_batch=optional(op.STATE),r038_cpu_placement=op.authority()['cpu_placement'],
        permit=record(op.PERMIT),active_source_verified=True,physical_checks_removed=0)
    atomic(op.CAMPAIGN/'V44_30MIN_WATCHDOG_RECEIPT.json',value)
    return value

def audit():
    op.validate();h=read(op.OPS/'CURRENT_HANDOFF.json');requests=[]
    for worker in op.base.workers():
        command=worker['cmdline'];pointer=Path(command[command.index('--worker')+1]);request=read(pointer)
        verify(request['sources']);requests.append(dict(pid=worker['pid'],request=record(pointer),source_pins=len(request['sources'])))
        if op.ENTRY in command:op.authorize(request)
    pending=h.get('pending_revision')=='v44_recovery_r038'
    if pending:
        hb=read(op.OPS/'R038_HANDOVER_HEARTBEAT.json')
        if not alive(hb):raise PermissionError('R038_PENDING_HANDOVER_NOT_LIVE')
    value=dict(UTC=now(),PASS=True,active=h['active_revision'],pending=h.get('pending_revision'),requests=requests,
        authorization=record(op.AMENDMENT),P_cores_only=True,physics_changed=False)
    atomic(op.OPS/'R038_ACTIVE_SOURCE_AUDIT.json',value);return value

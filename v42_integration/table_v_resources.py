"""Live build/native resource admission with durable, append-only receipts."""
import json
import math
import os
from pathlib import Path
from time import time
import uuid

from .a_engine import digest
from .m_engine import file_record
from .table_v_memory import memory_sample


def _snapshot():
    import psutil
    memory=memory_sample();limit=memory['system_commit_limit_bytes'];used=memory['system_committed_bytes']
    workers=[]
    for process in psutil.process_iter(['pid','name','cmdline']):
        try:
            args=process.info['cmdline'] or []
            heavy=(process.info['name'] or '').lower().startswith('gurobi') or any(
                Path(x).name=='run_v42_table_v.py' for x in args) and any(x in ('B1','B2','B3') for x in args)
            heavy=heavy or any(Path(x).name=='run_v42_production_campaign.py' for x in args) and '--execute' in args
            heavy=heavy or any(Path(x).name=='run_v42_table_v_serial_arms.py' for x in args)
            if heavy:workers.append(dict(pid=process.pid,name=process.info['name'],heavy_worker=True))
        except (psutil.NoSuchProcess,psutil.AccessDenied):continue
    return dict(memory=dict(AvailableMBytes=memory['system_available_bytes']/2**20,
        CommittedBytes=used,CommitLimit=limit,
        PercentCommittedBytesInUse=None if not limit or used is None else 100*used/limit),
        process=memory,workers=workers)


def admit_resources(budget,*,phase,owned_lock=False,snapshot=None):
    import psutil
    sample=snapshot if snapshot is not None else _snapshot()
    process=sample.get('process') or memory_sample();memory=sample.get('memory') or {}
    errors=[];lock=Path(budget.worker_lock);owner=None;lock_record=None
    finite=lambda v:type(v) in (int,float) and math.isfinite(v)
    if (not finite(memory.get('AvailableMBytes')) or memory['AvailableMBytes']<8192
            or not finite(memory.get('PercentCommittedBytesInUse')) or memory['PercentCommittedBytesInUse']>=75):
        errors.append('RAM_AVAILABLE_OR_SYSTEM_COMMIT_LIMIT')
    if not finite(process.get('RSS_bytes')) or process['RSS_bytes']<0:
        errors.append('PROCESS_RSS_MEASUREMENT_REQUIRED')
    limit=memory.get('CommitLimit');committed=memory.get('CommittedBytes')
    if limit is not None and (not finite(limit) or limit<=0 or not finite(committed) or committed<0 or committed>=.75*limit):
        errors.append('LIVE_COMMITTED_BYTES_LIMIT')
    owner_alive=None;owner_matches=False
    if lock.exists():
        lock_record=file_record(lock)
        try:
            owner=json.loads(lock.read_text(encoding='utf8'))
            owner_alive=psutil.pid_exists(owner.get('pid')) if type(owner.get('pid')) is int else False
            owner_matches=(owner.get('schema')=='V42_RELEASE_OWNED_LOCK_V1' and owner.get('kind')=='HEAVY_WORKER'
                and owner.get('pid')==os.getpid() and owner_alive is True and bool(owner.get('nonce'))
                and owner.get('ledger_path')==str(Path(budget.path).resolve())
                and owner.get('authorization_sha')==digest(budget.authorization))
        except (ValueError,OSError,TypeError,AttributeError):errors.append('UNREADABLE_OR_UNOWNED_HEAVY_LOCK')
        if not owned_lock or not owner_matches:errors.append('HEAVY_WORKER_LOCK_PID_OR_OWNERSHIP_CONFLICT')
    elif owned_lock:errors.append('NATIVE_OWNED_HEAVY_LOCK_MISSING')
    foreign=[r for r in sample.get('workers',[]) if r.get('heavy_worker') is True and r.get('pid')!=os.getpid()]
    if foreign:errors.append('OTHER_HEAVY_WORKER_PID_PRESENT')
    receipt=dict(schema='TABLE_V_LIVE_RESOURCE_ADMISSION_V1',phase=phase,status='PASS' if not errors else 'DENIED',
        epoch_seconds=time(),pid=os.getpid(),snapshot=sample,process=process,errors=errors,
        lock_record=lock_record,lock_owner=owner,lock_owner_PID_alive=owner_alive,
        lock_owner_matches_current_budget=owner_matches,Worker=1,Threads=1,Native_calls=0)
    if hasattr(budget,'path'):
        folder=Path(budget.path).parent/'RESOURCE_ADMISSIONS';folder.mkdir(parents=True,exist_ok=True)
        with (folder/(uuid.uuid4().hex+'.json')).open('x',encoding='utf8') as stream:
            json.dump(receipt,stream,indent=2,allow_nan=False)
    if errors:raise RuntimeError('TABLE_V_RESOURCE_ADMISSION_DENIED:'+','.join(errors))
    return receipt

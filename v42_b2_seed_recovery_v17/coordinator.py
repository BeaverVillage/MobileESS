"""Canary first, then RAM-based concurrency; no automatic failed-date retry."""
from pathlib import Path
import argparse
import math
import subprocess
import sys
import time
import psutil
from .common import ROOT,read,atomic,record,sha,now,process,exclusive_lock
from .policy import VERSION,MANIFEST,ATTEMPT,verify_manifest,verify_request


def request_for(root,manifest,day,slot):
    attempt=root/'dates/B2'/day/'attempts'/ATTEMPT;attempt.mkdir(parents=True,exist_ok=True)
    request=dict(root=str(root),run_id=manifest['run_id'],arm='B2',day=day,worker_slot=slot,Threads=1,
        P2_calls=0,native_budget_seconds=5400,wall_budget_seconds=None,target_gap=.03,
        input_folder=manifest['input_folders'][day],manifest=str(root/MANIFEST),manifest_SHA=sha(root/MANIFEST),
        implementation_SHA=manifest['execution_SHA'],algorithm_version=VERSION,policy_version=VERSION,
        attempt_id=ATTEMPT,started_UTC=now(),input_authority_root=str(root),
        stationary_dispatch_seed=True)
    request.update({k:str(attempt/name) for k,name in
        (('output','output'),('progress','progress.json'),('result','RESULT.json'),('error','error.json'))})
    path=attempt/'request.json'
    if path.exists():raise PermissionError('V17_REQUEST_NEVER_OVERWRITTEN')
    atomic(path,request);verify_request(request)
    return path,request


def canary_gate(request):
    out=Path(request['output']);result=read(request['result'])
    files=('INITIAL_STRICT_UB_CERTIFICATE.json','INITIAL_EXACT_LB_CERTIFICATE.json')
    if not all((out/n).exists() and read(out/n).get('PASS') is True for n in files):return False
    m=read(out/'M_STAGE_RESULT.json')
    return (not result.get('error') and not m.get('error') and m.get('UB') is not None and m.get('global_LB') is not None
        and m.get('termination') in ('INDEPENDENT_GLOBAL_GAP_3_PERCENT_CERTIFIED',
            'NATIVE_BUDGET_WINDOW_CLOSED','NATIVE_BUDGET_WINDOW_CLOSED_AT_SOLVER_BOUNDARY')
        and (out/'BEST_STRICT_UB_CERTIFICATE.json').exists() and (out/'BEST_EXACT_LB_CERTIFICATE.json').exists())


def concurrency(available_bytes,peak_bytes):
    per_worker=max(4.5*1024**3,peak_bytes)
    return max(1,min(3,math.floor(max(0,available_bytes-4*1024**3)/per_worker)))


def run(root):
    root=Path(root).resolve();manifest=verify_manifest(root/MANIFEST)
    with exclusive_lock(root/'COORDINATOR_V17.lock'):
        cp=read(root/'CHECKPOINT_V17.json');children={};workers={};limit=1
        if cp['state']!='CANARY_READY':raise PermissionError('V17_COORDINATOR_RESTART_REQUIRES_ORPHAN_ADOPTION_REVIEW')
        pending=['2025-05-01'];released=False
        atomic(root/'COORDINATOR_V17_PROCESS.json',process())
        while pending or children:
            if (root/'HOLD_V17.json').exists():cp['state']='HOLD';atomic(root/'CHECKPOINT_V17.json',cp);return
            for day in list(children):
                child,request=children[day]
                if child.poll() is None:continue
                if not Path(request['result']).exists():
                    cp['state']='QUARANTINE';atomic(root/'CHECKPOINT_V17.json',cp)
                    raise RuntimeError('V17_WORKER_EXIT_WITHOUT_MEASURED_RESULT')
                result=read(request['result']);row=cp['dates']['B2/'+day]
                row.update(status=result['status'],result=request['result'],result_SHA=sha(request['result']),
                    Native_Runtime=result.get('Native_Runtime'),source_SHA=manifest['execution_SHA'])
                del children[day];workers.pop(day,None)
                if day=='2025-05-01':
                    if not canary_gate(request):
                        cp['state']='CANARY_FAILED_REMAINING_DATES_HELD';pending=[]
                    else:
                        heartbeat=read(Path(request['result']).parent/'HEARTBEAT.json')
                        ram=psutil.virtual_memory();limit=concurrency(ram.available,heartbeat.get('peak_process_RSS_bytes',0))
                        pending=[f'2025-05-{n:02d}' for n in range(2,32)];released=True
                        cp.update(state='B2_RUNNING',parallel_workers=limit,canary_PASS=True,
                            RAM_available_bytes=ram.available,canary_peak_process_RSS_bytes=heartbeat.get('peak_process_RSS_bytes'))
            for slot in range(1,limit+1):
                if not pending or slot in {r['worker_slot'] for r in workers.values()}:continue
                day=pending.pop(0);path,request=request_for(root,manifest,day,slot)
                command=[sys.executable.replace('pythonw.exe','python.exe'),'-B','-X','utf8','-m',
                    'v42_b2_seed_recovery_v17.worker',str(path)]
                with (path.parent/'stdout.log').open('ab') as stdout,(path.parent/'stderr.log').open('ab') as stderr:
                    child=subprocess.Popen(command,cwd=ROOT,stdout=stdout,stderr=stderr)
                children[day]=(child,request);workers[day]=request
                cp['dates']['B2/'+day].update(status='RUNNING',current_attempt=ATTEMPT,request=str(path),worker_slot=slot)
            cp.update(workers={day:dict(PID=c.pid,request=str(Path(r['result']).parent/'request.json')) for day,(c,r) in children.items()},UTC=now())
            atomic(root/'CHECKPOINT_V17.json',cp)
            atomic(root/'COORDINATOR_V17_HEARTBEAT.json',dict(process=process(),timestamp_UTC=now(),state=cp['state']))
            time.sleep(1)
        if released:cp['state']='COMPLETE';atomic(root/'CHECKPOINT_V17.json',cp)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root');a=p.parse_args();run(a.root)

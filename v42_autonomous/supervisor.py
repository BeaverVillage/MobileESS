"""OS-owned dispatch with fixed B2=3/B3=1 and restart adoption."""
from pathlib import Path
import argparse, subprocess, sys, time
import psutil
from v42_b2_seed_recovery_v19.common import read,atomic,record,sha,now,process,same_process,exclusive_lock
from v42_b2_seed_recovery_v19.policy import verify_manifest
from v42_b2_seed_recovery_v19.coordinator import request_for

DAYS=tuple(f'2025-05-{i:02d}' for i in range(1,32))

def sweep_complete(cp,arm):
    return all(cp['dates'][arm+'/'+d]['status'] not in ('PENDING','RUNNING','RETRY_READY') for d in DAYS)

def transition(cp,state):
    if cp['state']==state:return
    cp.setdefault('transition_history',[]).append(dict(before=cp['state'],after=state,UTC=now()))
    cp['state']=state

def next_day(cp,arm):
    pending=[d for d in DAYS if cp['dates'][arm+'/'+d]['status']=='PENDING']
    return pending[0] if pending else None

def collect(root,cp,key,worker):
    request=read(worker['request']);p=Path(request['result'])
    row=cp['dates'][key]
    if p.exists():
        result=read(p)
        row.update(status=result['status'],result=str(p),result_SHA=sha(p),
            Native_Runtime=result.get('Native_Runtime'),source_SHA=result.get('source_SHA'),
            finished_UTC=result.get('finished_UTC'))
    else:
        exit_receipt=p.parent/'WORKER_EXIT_WITHOUT_RESULT.json'
        if not exit_receipt.exists():atomic(exit_receipt,dict(worker=worker,request=record(worker['request']),
            status='QUARANTINE',Native_Runtime='UNKNOWN',UTC=now(),reason='WORKER_EXIT_WITHOUT_MEASURED_RESULT'))
        row.update(status='QUARANTINE',Native_Runtime=None,failure_receipt=record(exit_receipt))
    cp['workers'].pop(key)

def b3_request(root,manifest,day,slot):
    attempt_id='b3_production_01'
    attempt=root/'dates/B3'/day/'attempts'/attempt_id
    attempt.mkdir(parents=True,exist_ok=True)
    output=Path(manifest['code_root'])/'runtime/b3'/manifest['run_id']/day/attempt_id
    request=dict(root=str(root),campaign_root=str(root),code_root=manifest['code_root'],run_id=manifest['run_id'],
        arm='B3',day=day,worker_slot=slot,attempt_id=attempt_id,canary=day==DAYS[0],output=str(output),
        result=str(attempt/'RESULT.json'),progress=str(attempt/'progress.json'),error=str(attempt/'error.json'),
        started_UTC=now(),manifest=str(root/'AUTONOMOUS_MANIFEST.json'))
    path=attempt/'request.json'
    if path.exists():raise PermissionError('B3_REQUEST_NEVER_OVERWRITTEN')
    atomic(path,request);return path,request

def dispatch(root,manifest,cp,arm,day,slot):
    key=arm+'/'+day
    if key in cp['workers']:raise PermissionError('DUPLICATE_DAY')
    if arm=='B2':
        m=verify_manifest(root/'CONTINUATION_V19_MANIFEST.json')
        path,request=request_for(root,m,day,slot);module='v42_b2_seed_recovery_v19.worker'
    else:path,request=b3_request(root,manifest,day,slot);module='v42_autonomous_b3.worker'
    command=[sys.executable.replace('pythonw.exe','python.exe'),'-B','-X','utf8','-m',module,str(path)]
    # Persist launch intent before Popen. A restart reconciles intent by request
    # path and never overwrites an existing attempt or launches it twice.
    cp['dates'][key].update(status='RUNNING',request=str(path),current_attempt=request['attempt_id'],worker_slot=slot)
    cp['workers'][key]=dict(request=str(path),launch_intent=True,worker_slot=slot,arm=arm,day=day)
    atomic(root/'SUPERVISOR_STATE.json',cp)
    with (path.parent/'stdout.log').open('ab') as out,(path.parent/'stderr.log').open('ab') as err:
        child=subprocess.Popen(command,cwd=manifest['code_root'],stdout=out,stderr=err,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform=='win32' else 0)
    cp['workers'][key].update(process(child.pid),launch_intent=False,source_SHA=request.get('implementation_SHA'),
        source_commit=manifest['source_commit'])
    atomic(root/'SUPERVISOR_STATE.json',cp)

def adopt_intents(cp):
    for key,w in cp['workers'].items():
        if not w.get('launch_intent'):continue
        matches=[]
        for p in psutil.process_iter(['name']):
            if (p.info['name'] or '').lower() not in ('python.exe','pythonw.exe'):continue
            try:
                args=p.cmdline()
                if args and args[-1]==w['request']:matches.append(p.pid)
            except psutil.Error:continue
        if len(matches)>1:raise PermissionError('MULTIPLE_WORKERS_SAME_REQUEST')
        if matches:w.update(process(matches[0]),launch_intent=False)

def run(root):
    root=Path(root).resolve();manifest=read(root/'AUTONOMOUS_MANIFEST.json')
    if manifest['B2_workers']!=3 or manifest['B3_workers']!=1:raise PermissionError('WORKER_COUNT_DRIFT')
    with exclusive_lock(root/'AUTONOMOUS_SUPERVISOR.lock'):
        cp=read(root/'SUPERVISOR_STATE.json');adopt_intents(cp)
        atomic(root/'SUPERVISOR_PROCESS.json',process())
        while cp['state'] not in ('CAMPAIGN_COMPLETE','CAMPAIGN_COMPLETE_WITH_FAILURES'):
            for key,w in list(cp['workers'].items()):
                if same_process(w):continue
                collect(root,cp,key,w)
            arm='B2' if cp['state'].startswith('B2') else 'B3'
            if sweep_complete(cp,arm) and not cp['workers']:
                transition(cp,arm+'_FINALIZING')
                all_pass=all(cp['dates'][arm+'/'+d]['status']=='PASS' for d in DAYS)
                if arm=='B2':
                    transition(cp,'B2_COMPLETE' if all_pass else 'B2_SWEEP_COMPLETE_WITH_FAILURES')
                    transition(cp,'B3_STARTING');transition(cp,'B3_RUNNING');arm='B3'
                else:
                    both=all(v['status']=='PASS' for v in cp['dates'].values())
                    transition(cp,'CAMPAIGN_COMPLETE' if both else 'CAMPAIGN_COMPLETE_WITH_FAILURES')
                    atomic(root/'SUPERVISOR_STATE.json',cp);break
            limit=3 if arm=='B2' else 1
            for slot in range(1,limit+1):
                if slot in {w['worker_slot'] for w in cp['workers'].values()}:continue
                # Verified repair attempts get the next free slot ahead of new days.
                from .recovery import dispatch_ready
                retry=dispatch_ready(root,arm,slot,manifest)
                if retry:
                    key=arm+'/'+retry['day'];cp['workers'][key]=retry
                    cp['dates'][key].update(status='RUNNING',request=retry['request'],worker_slot=slot)
                    continue
                day=next_day(cp,arm)
                if day:dispatch(root,manifest,cp,arm,day,slot)
            cp.update(UTC=now(),parallel_workers=limit)
            atomic(root/'SUPERVISOR_STATE.json',cp)
            atomic(root/'SUPERVISOR_HEARTBEAT.json',dict(process=process(),timestamp_UTC=now(),state=cp['state']))
            time.sleep(2)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root');a=p.parse_args()
    try:run(a.root)
    except BaseException as exc:
        import traceback
        atomic(Path(a.root)/'SUPERVISOR_ERROR.json',dict(error=repr(exc),traceback=traceback.format_exc(),UTC=now()))
        raise

"""OS-owned dispatch with fixed B2=3/B3=1 and restart adoption."""
from pathlib import Path
import argparse, subprocess, sys, time
import psutil
from v42_b2_seed_recovery_v19.common import read,atomic,record,sha,now,process,same_process,exclusive_lock

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
        identity=result.get('identity',{})
        source=result.get('source_SHA',result.get('source_sha',identity.get('source_SHA')))
        if (identity.get('arm')!=request['arm'] or identity.get('day')!=request['day']
            or identity.get('attempt_id')!=request['attempt_id']
            or worker.get('source_SHA') and source!=worker['source_SHA']):
            row.update(status='QUARANTINE',Native_Runtime=None,
                terminal_identity_error='RESULT_IDENTITY_OR_SOURCE_DRIFT',result=str(p),result_SHA=sha(p))
        else:
            row.update(status=result['status'],result=str(p),result_SHA=sha(p),
                Native_Runtime=result.get('Native_Runtime'),source_SHA=source,
                finished_UTC=result.get('finished_UTC',result.get('completed_UTC')))
        if worker.get('recovery_queue_id'):
            from .recovery import mark_finished,LeaseBusy
            try:mark_finished(root,worker['recovery_queue_id'],p)
            except LeaseBusy:return False
            except PermissionError as error:
                row.update(status='QUARANTINE',Native_Runtime=None,terminal_recovery_error=str(error))
    else:
        exit_receipt=p.parent/'WORKER_EXIT_WITHOUT_RESULT.json'
        if not exit_receipt.exists():atomic(exit_receipt,dict(worker=worker,request=record(worker['request']),
            status='QUARANTINE',Native_Runtime='UNKNOWN',UTC=now(),reason='WORKER_EXIT_WITHOUT_MEASURED_RESULT'))
        row.update(status='QUARANTINE',Native_Runtime=None,failure_receipt=record(exit_receipt))
    cp['workers'].pop(key)
    return True

def b2_request(root,manifest,day,slot):
    """Route future dates through the declared immutable deployment."""
    deployment=manifest.get('B2_deployment_manifest')
    if not deployment:
        from v42_b2_seed_recovery_v19.policy import verify_manifest
        from v42_b2_seed_recovery_v19.coordinator import request_for
        m=verify_manifest(root/'CONTINUATION_V19_MANIFEST.json')
        path,request=request_for(root,m,day,slot)
        return path,request,'v42_b2_seed_recovery_v19.worker',manifest['code_root'],m['source_commit']
    path=Path(deployment['path'] if isinstance(deployment,dict) else deployment).resolve()
    if isinstance(deployment,dict) and record(path)!=deployment:
        raise PermissionError('B2_DEPLOYMENT_MANIFEST_RECEIPT_DRIFT')
    m=read(path);code_root=manifest.get('B2_code_root',manifest['code_root'])
    module=manifest.get('B2_worker_module','v42_autonomous_b2.worker')
    if module not in ('v42_autonomous_b2.worker','v42_b2_seed_recovery_v19.worker'):
        raise PermissionError('B2_DECLARED_WORKER_MODULE_REQUIRED')
    if Path(code_root).resolve()==root or m['run_id']!=manifest['run_id']:
        raise PermissionError('B2_DEPLOYMENT_RUN_OR_CODE_ROOT_DRIFT')
    attempt_id=m.get('attempt_id_by_slot',{}).get(str(slot),m['attempt_id'])
    attempt=root/'dates/B2'/day/'attempts'/attempt_id
    request=dict(root=str(root),run_id=m['run_id'],arm='B2',day=day,worker_slot=slot,Threads=1,
        P2_calls=0,native_budget_seconds=5400,wall_budget_seconds=None,target_gap=.03,
        input_folder=m['input_folders'][day],manifest=str(path),manifest_SHA=sha(path),
        implementation_SHA=m['execution_SHA'],deployment_SHA=m['execution_SHA'],
        algorithm_version=m.get('algorithm_version',m['schema']),policy_version=m.get('policy_version',m['schema']),
        attempt_id=attempt_id,started_UTC=now(),input_authority_root=str(root),stationary_dispatch_seed=True)
    request.update({key:str(attempt/name) for key,name in
        (('output','output'),('progress','progress.json'),('result','RESULT.json'),('error','error.json'))})
    request_path=attempt/'request.json'
    if request_path.exists():raise PermissionError('B2_REQUEST_NEVER_OVERWRITTEN')
    atomic(request_path,request)
    verifier_module='v42_autonomous_b2.worker' if module=='v42_autonomous_b2.worker' else 'v42_b2_seed_recovery_v19.policy'
    verifier=('import json,sys; from '+verifier_module+' import verify_request; '
        'r=json.load(open(sys.argv[1],encoding="utf-8-sig")); verify_request(r)')
    subprocess.run([sys.executable.replace('pythonw.exe','python.exe'),'-B','-X','utf8','-c',verifier,str(request_path)],
        cwd=code_root,check=True,capture_output=True,text=True)
    return request_path,request,module,code_root,manifest.get('B2_source_commit',m['source_commit'])

def b3_request(root,manifest,day,slot):
    attempt_id=manifest.get('B3_attempt_id','b3_production_02')
    attempt=root/'dates/B3'/day/'attempts'/attempt_id
    attempt.mkdir(parents=True,exist_ok=True)
    code_root=manifest.get('B3_code_root',manifest['code_root'])
    output=Path(code_root)/'runtime/b3'/manifest['run_id']/day/attempt_id
    request=dict(root=str(root),campaign_root=str(root),code_root=code_root,run_id=manifest['run_id'],
        arm='B3',day=day,worker_slot=slot,attempt_id=attempt_id,canary=day==DAYS[0],output=str(output),
        result=str(attempt/'RESULT.json'),progress=str(attempt/'progress.json'),error=str(attempt/'error.json'),
        started_UTC=now(),manifest=str(root/'AUTONOMOUS_MANIFEST.json'))
    request['b1_campaign_root']=manifest.get('B1_campaign_root',str(root))
    seal=manifest.get('B3_source_seal')
    if not seal:raise PermissionError('B3_DECLARED_SOURCE_SEAL_REQUIRED')
    if isinstance(seal,dict):
        if record(seal['path'])!=seal:raise PermissionError('B3_SOURCE_SEAL_RECEIPT_DRIFT')
        request['source_seal']=seal['path']
    else:request['source_seal']=str(seal)
    sealed=read(request['source_seal'])
    source=manifest.get('B3_source_SHA',sealed.get('source_sha'))
    from .recovery import _sha
    if not _sha(source,64) or sealed.get('source_sha')!=source:
        raise PermissionError('B3_DECLARED_SOURCE_SHA_DRIFT')
    request.update(source_SHA=source,implementation_SHA=source)
    qualification=manifest.get('B3_qualification',str(root/'autonomous/B3_PRODUCTION_QUALIFICATION.json'))
    if isinstance(qualification,dict):
        if record(qualification['path'])!=qualification:raise PermissionError('B3_QUALIFICATION_RECEIPT_DRIFT')
        qualification=qualification['path']
    request['qualification_output']=str(qualification)
    if day!=DAYS[0]:request['qualification']=str(qualification)
    path=attempt/'request.json'
    if path.exists():raise PermissionError('B3_REQUEST_NEVER_OVERWRITTEN')
    atomic(path,request)
    verifier=('import json,sys; from pathlib import Path; '
        'from v42_autonomous_b3.admission import validate_request,validate_seal,source_seal; '
        'r=json.load(open(sys.argv[1],encoding="utf-8-sig")); validate_request(r); '
        's=json.load(open(r["source_seal"],encoding="utf-8-sig")); validate_seal(s,Path.cwd()); '
        'assert source_seal(Path.cwd())["source_sha"]==s["source_sha"]==r["implementation_SHA"]==r["source_SHA"]')
    subprocess.run([sys.executable.replace('pythonw.exe','python.exe'),'-B','-X','utf8','-c',verifier,str(path)],
        cwd=code_root,check=True,capture_output=True,text=True)
    return path,request

def dispatch(root,manifest,cp,arm,day,slot):
    key=arm+'/'+day
    if key in cp['workers']:raise PermissionError('DUPLICATE_DAY')
    if arm=='B2':
        path,request,module,code_root,source_commit=b2_request(root,manifest,day,slot)
    else:
        path,request=b3_request(root,manifest,day,slot);module='v42_autonomous_b3.worker'
        code_root=request['code_root'];source_commit=manifest.get('B3_source_commit',manifest['source_commit'])
    command=[sys.executable.replace('pythonw.exe','python.exe'),'-B','-X','utf8','-m',module,str(path)]
    # Persist launch intent before Popen. A restart reconciles intent by request
    # path and never overwrites an existing attempt or launches it twice.
    cp['dates'][key].update(status='RUNNING',request=str(path),current_attempt=request['attempt_id'],worker_slot=slot)
    cp['workers'][key]=dict(request=str(path),launch_intent=True,worker_slot=slot,arm=arm,day=day)
    atomic(root/'SUPERVISOR_STATE.json',cp)
    with (path.parent/'stdout.log').open('ab') as out,(path.parent/'stderr.log').open('ab') as err:
        child=subprocess.Popen(command,cwd=code_root,stdout=out,stderr=err,
            creationflags=(subprocess.CREATE_NO_WINDOW|subprocess.NORMAL_PRIORITY_CLASS) if sys.platform=='win32' else 0)
    cp['workers'][key].update(process(child.pid),launch_intent=False,source_SHA=request.get('implementation_SHA'),
        source_commit=source_commit)
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
        if matches:
            request=read(w['request'])
            w.update(process(matches[0]),launch_intent=False,source_SHA=request.get('implementation_SHA'))

def adopt_recovery_workers(root,cp):
    from .recovery import reconcile_workers,queue
    for worker in reconcile_workers(root):
        key=worker['arm']+'/'+worker['day']
        existing=cp['workers'].get(key)
        if existing and existing.get('request')!=worker['request']:
            raise PermissionError('RECOVERY_ADOPTION_CONFLICTING_ACTIVE_DATE')
        if any(other!=key and value.get('worker_slot')==worker['worker_slot'] for other,value in cp['workers'].items()):
            raise PermissionError('RECOVERY_ADOPTION_CONFLICTING_SLOT')
        cp['workers'][key]=worker
        cp['dates'][key].update(status='RUNNING',request=worker['request'],current_attempt=read(worker['request'])['attempt_id'])
    # A worker can finish between queue launch and supervisor persistence.
    for row in queue(root)['entries']:
        if not row.get('final_result_receipt'):continue
        key=row['arm']+'/'+row['date']
        request=row['retry_request_receipt']['path']
        current=cp['dates'][key]
        if key not in cp['workers'] and current.get('status')!='PASS' and (
            current.get('request') in (None,request) or
            current.get('result')==(row.get('original_result_receipt') or {}).get('path')):
            result=read(row['final_result_receipt']['path'])
            cp['dates'][key].update(status='PASS' if row['verification_status']=='RECOVERY_PASS'
                else 'QUARANTINE' if row['verification_status'].startswith('QUARANTINE') else result['status'],
                request=request,result=row['final_result_receipt']['path'],result_SHA=row['final_result_receipt']['sha256'],
                Native_Runtime=row.get('final_Native_Runtime'),source_SHA=row['repair_source_SHA'])

def recovery_pending(root,arm):
    from .recovery import queue
    return any(row['arm']==arm and row['verification_status'] in
        ('READY_VERIFIED_REPAIR','DISPATCH_INTENT','WORKER_ENTERED','NATIVE_PROGRESS_VERIFIED')
        for row in queue(root)['entries'])

def adopt_unjournaled_requests(root,cp,manifest):
    """Reconcile the request-write/launch-intent crash boundary conservatively."""
    from .recovery import queue,_request_workers
    queued=set()
    for row in queue(root)['entries']:
        queued.add(str(Path(row['retry_request_receipt']['path']).resolve()))
        queued.update(str(Path(value['path']).resolve()) for value in row.get('retry_request_receipts_by_slot',{}).values())
    deployment=manifest.get('B2_deployment_manifest')
    deployment_path=Path(deployment['path'] if isinstance(deployment,dict) else deployment) if deployment else root/'CONTINUATION_V19_MANIFEST.json'
    m=read(deployment_path)
    attempts=set(m.get('attempt_ids',[m['attempt_id']])) | set(m.get('attempt_id_by_slot',{}).values())
    for arm in ('B2','B3'):
        for day in DAYS:
            key=arm+'/'+day
            if cp['dates'][key]['status']!='PENDING' or key in cp['workers']:continue
            ids=attempts if arm=='B2' else {manifest.get('B3_attempt_id','b3_production_02')}
            for attempt_id in ids:
                path=root/'dates'/arm/day/'attempts'/attempt_id/'request.json'
                if not path.exists() or str(path.resolve()) in queued:continue
                request=read(path)
                if request.get('arm')!=arm or request.get('day')!=day or request.get('attempt_id')!=attempt_id:
                    raise PermissionError('ORPHAN_REQUEST_DATE_IDENTITY_DRIFT')
                matches=_request_workers(path)
                if len(matches)>1:raise PermissionError('MULTIPLE_UNJOURNALED_WORKERS_SAME_REQUEST')
                worker=dict(request=str(path),worker_slot=request['worker_slot'],arm=arm,day=day,
                    source_SHA=request.get('implementation_SHA'),launch_intent=not bool(matches))
                if matches:
                    worker.update(matches[0],launch_intent=False)
                    if any(value.get('worker_slot')==worker['worker_slot'] for value in cp['workers'].values()):
                        raise PermissionError('UNJOURNALED_WORKER_SLOT_CONFLICT')
                cp['workers'][key]=worker
                cp['dates'][key].update(status='RUNNING',request=str(path),current_attempt=attempt_id)
                break

def run(root):
    if sys.platform=='win32':psutil.Process().nice(psutil.NORMAL_PRIORITY_CLASS)
    root=Path(root).resolve();manifest=read(root/'AUTONOMOUS_MANIFEST.json')
    if manifest['B2_workers']!=3 or manifest['B3_workers']!=1:raise PermissionError('WORKER_COUNT_DRIFT')
    with exclusive_lock(root/'AUTONOMOUS_SUPERVISOR.lock'):
        cp=read(root/'SUPERVISOR_STATE.json');adopt_intents(cp)
        from .recovery import LeaseBusy,sync_worker
        try:adopt_recovery_workers(root,cp)
        except LeaseBusy:cp['recovery_adoption_pending']=True
        adopt_unjournaled_requests(root,cp,manifest)
        atomic(root/'SUPERVISOR_PROCESS.json',process())
        while cp['state'] not in ('CAMPAIGN_COMPLETE','CAMPAIGN_COMPLETE_WITH_FAILURES'):
            # Only later attempts read the updated deployment registry. Live
            # workers retain their immutable request, cwd and source seal.
            manifest=read(root/'AUTONOMOUS_MANIFEST.json')
            if manifest['B2_workers']!=3 or manifest['B3_workers']!=1:raise PermissionError('WORKER_COUNT_DRIFT')
            if cp.pop('recovery_adoption_pending',False):
                try:adopt_recovery_workers(root,cp)
                except LeaseBusy:cp['recovery_adoption_pending']=True
            for key,w in list(cp['workers'].items()):
                if same_process(w):
                    try:sync_worker(root,w)
                    except LeaseBusy:pass
                    continue
                collect(root,cp,key,w)
            arm='B2' if cp['state'].startswith('B2') else 'B3'
            if sweep_complete(cp,arm) and not cp['workers'] and not recovery_pending(root,arm):
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
                other=[]
                own={w.get('PID') for w in cp['workers'].values()}
                for p in psutil.process_iter(['name']):
                    if p.pid in own or (p.info['name'] or '').lower() not in ('python.exe','pythonw.exe'):continue
                    try:
                        a=p.cmdline();module=a[a.index('-m')+1] if '-m' in a else ''
                        if module.endswith('.worker') and module.startswith(('v42_may','v42_b2','v42_m1','v42_a_stage','v42_autonomous_b2','v42_autonomous_b3')):
                            other.append(process(p.pid))
                    except psutil.Error:continue
                if other:
                    cp['dispatch_wait']=dict(reason='EXTERNAL_SCIENTIFIC_WORKER_ACTIVE',workers=other,UTC=now())
                    continue
                # Verified repair attempts get the next free slot ahead of new days.
                from .recovery import dispatch_ready,LeaseBusy
                try:retry=dispatch_ready(root,arm,slot,manifest)
                except LeaseBusy:
                    cp['dispatch_wait']=dict(reason='RECOVERY_QUEUE_BEING_UPDATED',UTC=now())
                    continue
                if retry:
                    key=arm+'/'+retry['day'];cp['workers'][key]=retry
                    cp['dates'][key].update(status='RUNNING',request=retry['request'],worker_slot=slot)
                    atomic(root/'SUPERVISOR_STATE.json',cp)
                    continue
                day=next_day(cp,arm)
                if arm=='B3':
                    # The first real day is the canary. Further Native work is
                    # admitted only by its completed qualification receipt.
                    available=(Path(manifest.get('B3_code_root',manifest['code_root']))/'v42_autonomous_b3/worker.py').exists()
                    first=cp['dates']['B3/'+DAYS[0]]
                    if not available or (day!=DAYS[0] and first['status']!='PASS'):
                        cp['B3_admission']='WAITING_FOR_IMPLEMENTATION' if not available else 'WAITING_FOR_REAL_CANARY_PASS'
                        continue
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

"""OS-owned dispatch with fixed B2=3/B3=1 and restart adoption."""
from pathlib import Path
import argparse, hashlib, json, re, subprocess, sys, time, uuid
import psutil
from v42_b2_seed_recovery_v19.common import read,atomic,record,sha,now,process,same_process,exclusive_lock

DAYS=tuple(f'2025-05-{i:02d}' for i in range(1,32))

def public_status(status):
    if status in ('PASS','FAIL','QUARANTINE','RETRY_PENDING','PENDING','RUNNING','SOURCE_BLOCKED'):return status
    if str(status).startswith('QUARANTINE') or 'UNKNOWN' in str(status):return 'QUARANTINE'
    if status=='RETRY_READY':return 'RETRY_PENDING'
    return 'FAIL'

def sweep_complete(cp,arm):
    return all(cp['dates'][arm+'/'+d].get('first_attempt_terminal') is not None or
        cp['dates'][arm+'/'+d]['status'] not in ('PENDING','RUNNING','RETRY_READY','RETRY_PENDING','SOURCE_BLOCKED') for d in DAYS)

def transition(cp,state):
    if cp['state']==state:return
    cp.setdefault('transition_history',[]).append(dict(before=cp['state'],after=state,UTC=now()))
    cp['state']=state

def next_day(cp,arm):
    pending=[d for d in DAYS if cp['dates'][arm+'/'+d]['status']=='PENDING' and
        cp['dates'][arm+'/'+d].get('first_attempt_terminal') is None]
    return pending[0] if pending else None

def first_terminal(cp,key,worker=None):
    row=cp['dates'][key]
    if row.get('first_attempt_terminal') is not None or (worker or {}).get('recovery_queue_id'):return
    row['first_attempt_terminal']={field:row.get(field) for field in
        ('status','worker_status','current_attempt','request','result','result_SHA','Native_Runtime','source_SHA','finished_UTC','failure_receipt')}
    row['first_attempt_terminal']['recorded_UTC']=now()

def initialize_history(cp):
    cp.setdefault('first_sweeps_completed',{})
    for key,row in cp['dates'].items():
        if not key.startswith(('B2/','B3/')):continue
        normalized=public_status(row['status'])
        if normalized!=row['status']:row.update(worker_status=row['status'],status=normalized)
        if row['status'] not in ('PENDING','RUNNING','RETRY_READY','RETRY_PENDING','SOURCE_BLOCKED'):
            first_terminal(cp,key)

def activate_retry(cp,key,worker):
    """Keep historical evidence out of the new running attempt's fields."""
    row=cp['dates'][key];request=read(worker['request'])
    changed=row.get('current_attempt')!=request['attempt_id'] or row.get('request')!=worker['request']
    terminal_fields=('result','result_SHA','failure_receipt','error','error_receipt','finished_UTC',
        'terminal_identity_error','terminal_policy_error','terminal_recovery_error')
    if changed or any(row.get(field) is not None for field in terminal_fields):
        snapshot=json.loads(json.dumps({field:value for field,value in row.items()
            if field not in ('first_attempt_terminal','attempt_history')},ensure_ascii=False))
        history=row.setdefault('attempt_history',[])
        key_fields=('current_attempt','request','result','result_SHA','failure_receipt')
        if not any(all(previous.get(field)==snapshot.get(field) for field in key_fields) for previous in history):
            history.append(dict(snapshot,archived_UTC=now(),superseded_by_attempt_id=request['attempt_id']))
    keep={'arm','day','attempt_count','first_attempt_terminal','attempt_history','retry_queue_ids','last_terminal_status'}
    for field in list(row):
        if field not in keep:row.pop(field)
    row.update(status='RUNNING',current_attempt=request['attempt_id'],request=worker['request'],
        worker_slot=worker['worker_slot'],source_SHA=worker.get('source_SHA',request.get('implementation_SHA')),
        source_commit=worker.get('source_commit'),Native_Runtime=None,
        native_runtime_state='AWAITING_CURRENT_ATTEMPT_LEDGER',active_recovery_queue_id=worker.get('recovery_queue_id'))
    cp['workers'][key]=worker

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
        elif (result.get('status')=='PASS') != (result.get('PASS') is True):
            row.update(status='QUARANTINE',Native_Runtime=result.get('Native_Runtime'),
                terminal_policy_error='RESULT_PASS_STATUS_DISAGREEMENT',worker_status=result.get('status'),
                result=str(p),result_SHA=sha(p),source_SHA=source)
        else:
            status=public_status(result['status'])
            if status!='PASS' and result.get('Native_Runtime') is None:status='QUARANTINE'
            row.update(status=status,worker_status=result['status'],result=str(p),result_SHA=sha(p),
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
    first_terminal(cp,key,worker)
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
    try:m=read(path)
    except (OSError,ValueError) as error:
        from .recovery import SourceBlocked
        raise SourceBlocked('COMMON_ENVIRONMENT_FAILURE:B2_DEPLOYMENT_UNAVAILABLE:'+str(error)) from error
    code_root=manifest.get('B2_code_root',manifest['code_root'])
    if not Path(code_root).is_dir():
        from .recovery import SourceBlocked
        raise SourceBlocked('COMMON_ENVIRONMENT_FAILURE:B2_CHECKOUT_MISSING')
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
    try:
        subprocess.run([sys.executable.replace('pythonw.exe','python.exe'),'-B','-X','utf8','-c',verifier,str(request_path)],
            cwd=code_root,check=True,capture_output=True,text=True)
    except Exception as error:
        error.request_path=str(request_path)
        raise
    return request_path,request,module,code_root,manifest.get('B2_source_commit',m['source_commit'])

def b3_request(root,manifest,day,slot):
    attempt_id=manifest.get('B3_attempt_id','b3_production_02')
    attempt=root/'dates/B3'/day/'attempts'/attempt_id
    attempt.mkdir(parents=True,exist_ok=True)
    code_root=manifest.get('B3_code_root',manifest['code_root'])
    output=Path(code_root)/'runtime/b3'/manifest['run_id']/day/attempt_id
    request=dict(root=str(root),campaign_root=str(root),code_root=code_root,run_id=manifest['run_id'],
        arm='B3',day=day,worker_slot=slot,attempt_id=attempt_id,canary=True,output=str(output),
        result=str(attempt/'RESULT.json'),progress=str(attempt/'progress.json'),error=str(attempt/'error.json'),
        started_UTC=now(),manifest=str(root/'AUTONOMOUS_MANIFEST.json'))
    request['b1_campaign_root']=manifest.get('B1_campaign_root',str(root))
    seal=manifest.get('B3_source_seal')
    if not seal:raise PermissionError('B3_DECLARED_SOURCE_SEAL_REQUIRED')
    try:
        if isinstance(seal,dict):
            if record(seal['path'])!=seal:raise PermissionError('B3_SOURCE_SEAL_RECEIPT_DRIFT')
            request['source_seal']=seal['path']
        else:request['source_seal']=str(seal)
        sealed=read(request['source_seal'])
    except (OSError,ValueError) as error:
        from .recovery import SourceBlocked
        raise SourceBlocked('GLOBAL_SOURCE_INTEGRITY_FAILURE:B3_SOURCE_SEAL_UNAVAILABLE:'+str(error)) from error
    source=manifest.get('B3_source_SHA',sealed.get('source_sha'))
    from .recovery import _sha
    if not _sha(source,64) or sealed.get('source_sha')!=source:
        raise PermissionError('B3_DECLARED_SOURCE_SHA_DRIFT')
    request.update(source_SHA=source,implementation_SHA=source)
    run_id=manifest['run_id']
    safe_id=run_id if re.fullmatch(r'[A-Za-z0-9_-]{1,100}',run_id) else (
        re.sub(r'[^A-Za-z0-9_-]','_',run_id)[:87]+'_'+hashlib.sha256(run_id.encode()).hexdigest()[:12])
    request['scientific_run_id']=manifest.get('B3_scientific_run_id',safe_id)
    qualification=manifest.get('B3_qualification',str(root/'autonomous/B3_PRODUCTION_QUALIFICATION.json'))
    if isinstance(qualification,dict):qualification=qualification['path']
    request['qualification_output']=str(qualification)
    path=attempt/'request.json'
    if path.exists():raise PermissionError('B3_REQUEST_NEVER_OVERWRITTEN')
    verifier=('import json,sys; from pathlib import Path; '
        'from v42_autonomous_b3.admission import validate_request,validate_seal,source_seal,qualification_status,scientific_run_id; '
        'r=json.load(sys.stdin); validate_request(r); '
        's=json.load(open(r["source_seal"],encoding="utf-8-sig")); validate_seal(s,Path.cwd()); '
        'assert source_seal(Path.cwd())["source_sha"]==s["source_sha"]==r["implementation_SHA"]==r["source_SHA"],"GLOBAL_SOURCE_INTEGRITY_FAILURE"; '
        'print(json.dumps({"qualification_status":qualification_status(r["qualification_output"],s["source_sha"],seal=s,code_root=Path.cwd()),'
        '"scientific_run_id":scientific_run_id(r)}))')
    verified=subprocess.run([sys.executable.replace('pythonw.exe','python.exe'),'-B','-X','utf8','-c',verifier],
        input=json.dumps(request),cwd=code_root,check=True,capture_output=True,text=True)
    admission=json.loads(verified.stdout)
    if admission['scientific_run_id']!=request['scientific_run_id']:
        raise PermissionError('B3_SCIENTIFIC_RUN_ID_BINDING_DRIFT')
    mode=admission['qualification_status']
    if mode.get('global_source_block'):
        from .recovery import SourceBlocked
        raise SourceBlocked('GLOBAL_SOURCE_INTEGRITY_FAILURE:'+mode.get('reason',''))
    qualified=mode['status']=='QUALIFIED'
    request.update(canary=not qualified,qualification_status=mode['status'],qualification_admission=mode)
    if qualified:request['qualification']=mode['qualification']['path']
    atomic(path,request)
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
    cp['workers'][key].update(popen_returned=True,PID=child.pid)
    atomic(root/'SUPERVISOR_STATE.json',cp)
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
        activate_retry(cp,key,worker)
    # A worker can finish between queue launch and supervisor persistence.
    for row in queue(root)['entries']:
        if not row.get('final_result_receipt'):continue
        key=row['arm']+'/'+row['date']
        request=row['retry_request_receipt']['path']
        current=cp['dates'][key]
        if key not in cp['workers'] and (current.get('request')==request or current.get('status')!='PASS' and (
            current.get('request') is None or
            current.get('result')==(row.get('original_result_receipt') or {}).get('path'))):
            result=read(row['final_result_receipt']['path'])
            status='PASS' if row['verification_status']=='RECOVERY_PASS' else (
                'QUARANTINE' if row['verification_status'].startswith('QUARANTINE') else public_status(result['status']))
            if (result.get('status')=='PASS') != (result.get('PASS') is True):
                status='QUARANTINE';current['terminal_policy_error']='RESULT_PASS_STATUS_DISAGREEMENT'
            cp['dates'][key].update(status=status,worker_status=result['status'],
                current_attempt=read(request)['attempt_id'],
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
                if cp['dates'][key].get('source_blocked_request')==str(path):continue
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

def source_registry(manifest):
    fields=('B2_code_root','B2_source_SHA','B2_source_commit','B2_deployment_manifest','B2_worker_module',
        'B3_code_root','B3_source_SHA','B3_source_commit','B3_source_seal','B3_scientific_run_id','environment_repair_revision')
    freeze={field:manifest.get(field) for field in fields}
    return freeze,hashlib.sha256(json.dumps(freeze,sort_keys=True,ensure_ascii=False).encode()).hexdigest()

def block_source(root,manifest,cp,error,*,arm=None,day=None,before_popen=False):
    freeze,fingerprint=source_registry(manifest)
    detail=str(error)+'\n'+str(getattr(error,'stderr','') or '')
    receipt=root/'autonomous'/('SOURCE_BLOCK_'+uuid.uuid4().hex+'.json')
    document=dict(UTC=now(),reasonCode=type(error).__name__+':'+str(error).split('\n',1)[0],
        affectedScope='COMMON_SOURCE_OR_ENVIRONMENT_FUTURE_ADMISSION',arm=arm,day=day,
        reason=detail[:50000],manifestSourceFreeze=freeze,source_registry_SHA=fingerprint,
        before_Popen=before_popen,new_attempt_native_runtime=0. if before_popen else None,
        existing_workers_preserved=True)
    atomic(receipt,document)
    if cp['state']!='SOURCE_BLOCKED':cp['source_block_resume_state']=cp['state']
    cp['source_block']=dict(document,receipt=record(receipt))
    transition(cp,'SOURCE_BLOCKED')

def refresh_retries(root,cp):
    from .recovery import retire_satisfied_ready,LeaseBusy
    try:
        current_queue=retire_satisfied_ready(root,cp)
    except LeaseBusy:
        # An operator may be sealing a verified replacement under this lock.
        # Keep current PASS/failure/worker state intact and retry next cycle.
        return
    grouped={}
    for entry in current_queue['entries']:grouped.setdefault(entry['arm']+'/'+entry['date'],[]).append(entry)
    for key,entries in grouped.items():
        if key in cp['workers']:continue
        row=cp['dates'][key]
        pending=[entry for entry in entries if entry['verification_status'] in ('READY_VERIFIED_REPAIR','DISPATCH_INTENT')]
        if pending:
            if row['status'] not in ('PENDING','RUNNING','RETRY_READY','RETRY_PENDING'):first_terminal(cp,key)
            row.setdefault('last_terminal_status',row['status'])
            row.update(status='RETRY_PENDING',retry_queue_ids=[entry['queue_id'] for entry in pending])
        elif row['status']=='RETRY_PENDING':
            denied=[entry for entry in entries if entry.get('admission_failure_receipt')]
            if denied:
                latest=max(denied,key=lambda entry:entry.get('admission_failed_UTC',''))
                row.update(status='QUARANTINE',failure_receipt=latest['admission_failure_receipt'],
                    terminal_recovery_error='REPAIR_ADMISSION_FAILED; ORIGINAL_NATIVE_ACCOUNTING_PRESERVED')
            else:row['status']=row.get('last_terminal_status','QUARANTINE')

def external_workers(cp):
    other=[];own={w.get('PID') for w in cp['workers'].values()}
    for p in psutil.process_iter(['name']):
        if p.pid in own or (p.info['name'] or '').lower() not in ('python.exe','pythonw.exe'):continue
        try:
            args=p.cmdline();module=args[args.index('-m')+1] if '-m' in args else ''
            if module.endswith('.worker') and module.startswith(('v42_may','v42_b2','v42_m1','v42_a_stage','v42_autonomous_b2','v42_autonomous_b3')):
                other.append(process(p.pid))
        except psutil.Error:continue
    return other

def safe_dispatch(root,manifest,cp,arm,day,slot):
    """A failed date cannot kill the coordinator or consume another date."""
    from .recovery import common_failure,_request_workers,_measured
    key=arm+'/'+day
    try:
        dispatch(root,manifest,cp,arm,day,slot)
        return True
    except Exception as error:
        worker=cp['workers'].get(key,{})
        if worker.get('popen_returned'):
            # Native may have begun. Keep the launch receipt for real result
            # collection/adoption; never manufacture a Native-zero failure.
            cp['recovery_adoption_pending']=True
            if common_failure(error):block_source(root,manifest,cp,error,arm=arm,day=day)
            return False
        request_path=worker.get('request',getattr(error,'request_path',None))
        if request_path:
            matches=_request_workers(request_path)
            if matches:
                if len(matches)>1:
                    block_source(root,manifest,cp,PermissionError('GLOBAL_SOURCE_INTEGRITY_FAILURE:DUPLICATE_REQUEST_WORKERS'),arm=arm,day=day)
                else:worker.update(matches[0],launch_intent=False,popen_returned=True)
                return False
        cp['workers'].pop(key,None)
        row=cp['dates'][key]
        if common_failure(error):
            row.update(status='PENDING',source_blocked_request=request_path)
            block_source(root,manifest,cp,error,arm=arm,day=day,before_popen=True)
            return False
        carried=0.
        if arm=='B2':
            deployment=manifest.get('B2_deployment_manifest')
            if deployment:
                sealed=read(deployment['path'] if isinstance(deployment,dict) else deployment)
                carried=sealed.get('prior_attempts',{}).get(day,{}).get('Native_Runtime',0.)
        receipt=root/'dates'/arm/day/('DISPATCH_ADMISSION_FAILURE_'+uuid.uuid4().hex+'.json')
        status='QUARANTINE' if isinstance(error,PermissionError) else 'FAIL'
        document=dict(arm=arm,day=day,UTC=now(),status=status,PASS=False,
            failure_class=type(error).__name__,reason=str(error),stderr=str(getattr(error,'stderr','') or '')[:50000],
            before_Popen=True,before_Native=True,new_attempt_native_runtime=0.,
            Native_Runtime=carried if _measured(carried) else None,
            native_runtime_state='KNOWN' if _measured(carried) else 'UNKNOWN',
            budget_basis='VERIFIED_PRELAUNCH_NATIVE_ZERO_WITH_PRIOR_ACCOUNTING_PRESERVED',
            control_source_files=[record(Path(__file__)),record(Path(__file__).with_name('recovery.py'))])
        atomic(receipt,document)
        row.update(status=status,Native_Runtime=document['Native_Runtime'],failure_receipt=record(receipt),
            new_attempt_native_runtime=0.,native_runtime_state=document['native_runtime_state'],finished_UTC=now())
        first_terminal(cp,key)
        return False

def advance_sweeps(cp):
    if cp['workers']:return
    for arm in ('B2','B3'):
        if arm in cp['first_sweeps_completed'] or not sweep_complete(cp,arm):continue
        if arm=='B3' and 'B2' not in cp['first_sweeps_completed']:continue
        cp['first_sweeps_completed'][arm]=dict(UTC=now(),dates=31,
            first_attempt_statuses={day:cp['dates'][arm+'/'+day]['first_attempt_terminal']['status'] for day in DAYS})
        transition(cp,arm+'_FINALIZING')
        all_pass=all(cp['dates'][arm+'/'+day]['first_attempt_terminal']['status']=='PASS' for day in DAYS)
        transition(cp,arm+'_COMPLETE' if all_pass else arm+'_SWEEP_COMPLETE_WITH_FAILURES')
        if arm=='B2':transition(cp,'B3_STARTING');transition(cp,'B3_RUNNING')

def record_heartbeat_observation_error(cp,key,worker,error):
    """Preserve observation faults separately from scientific status/accounting."""
    errors=cp.setdefault('worker_observation_errors',{})
    identity={name:worker.get(name) for name in ('PID','created','request','recovery_queue_id')}
    previous=errors.get(key)
    consecutive=previous['consecutive_failures']+1 if previous and previous['worker_identity']==identity else 1
    status='PERSISTENT_WORKER_HEARTBEAT_IO_ERROR' if consecutive>=3 else 'DEFERRED_WORKER_HEARTBEAT_IO_OBSERVATION'
    entry=dict(status=status,worker_identity=identity,consecutive_failures=consecutive,
        first_seen_UTC=previous['first_seen_UTC'] if previous and consecutive>1 else now(),
        last_seen_UTC=now(),original_read_error=previous['original_read_error'] if previous and consecutive>1 else dict(error.observation),
        last_read_error=dict(error.observation),scientific_status_and_native_accounting_unchanged=True,
        counter_basis='CONSECUTIVE_ACCESS_FAILURES_WITHOUT_MATCHING_CLEAN_HEARTBEAT_READ')
    errors[key]=entry
    if not previous or previous['status']!=status or previous['worker_identity']!=identity:
        cp.setdefault('worker_observation_error_history',[]).append(dict(key=key,**entry))


def resolve_heartbeat_observation_error(cp,key,worker):
    previous=cp.get('worker_observation_errors',{}).get(key)
    identity={name:worker.get(name) for name in ('PID','created','request','recovery_queue_id')}
    if previous and previous['worker_identity']!=identity:return False
    if previous:
        cp['worker_observation_errors'].pop(key)
        cp.setdefault('worker_observation_error_history',[]).append(dict(key=key,**previous,
            observation_resolved_UTC=now(),resolution='CLEAN_OWNED_HEARTBEAT_READ_FOR_SAME_WORKER_IDENTITY'))
    return bool(previous)


def cycle(root,manifest,cp):
    """One durable scheduling cycle; individual failures remain local."""
    from .recovery import LeaseBusy,HeartbeatObservationDeferred,HeartbeatObservationRead,queue,dispatch_ready,sync_worker,common_failure
    root=Path(root)
    adopt_intents(cp)
    initialize_history(cp)
    if cp['state']=='SOURCE_BLOCKED':
        _,fingerprint=source_registry(manifest)
        if fingerprint!=cp.get('source_block',{}).get('source_registry_SHA'):
            cp.setdefault('source_block_history',[]).append(cp.pop('source_block'))
            transition(cp,cp.pop('source_block_resume_state','B2_RUNNING'))
    if cp.pop('recovery_adoption_pending',False):
        try:adopt_recovery_workers(root,cp)
        except LeaseBusy:cp['recovery_adoption_pending']=True
    for key,worker in list(cp['workers'].items()):
        if same_process(worker):
            try:
                observation=sync_worker(root,worker)
                if isinstance(observation,HeartbeatObservationRead):resolve_heartbeat_observation_error(cp,key,worker)
            except LeaseBusy:pass
            except HeartbeatObservationDeferred as error:record_heartbeat_observation_error(cp,key,worker,error)
            continue
        try:
            collect(root,cp,key,worker)
            row=cp['dates'][key]
            if row.get('result'):
                result=read(row['result'])
                error=PermissionError(str(result.get('reason','')))
                if result.get('PASS') is not True and common_failure(error):
                    block_source(root,manifest,cp,error,arm=worker['arm'],day=worker['day'])
        except Exception as error:
            receipt=root/'dates'/worker['arm']/worker['day']/('WORKER_COLLECTION_FAILURE_'+uuid.uuid4().hex+'.json')
            atomic(receipt,dict(worker=worker,status='QUARANTINE',Native_Runtime='UNKNOWN',UTC=now(),
                reason=str(error),failure_class=type(error).__name__,original_files_preserved=True))
            cp['dates'][key].update(status='QUARANTINE',Native_Runtime=None,failure_receipt=record(receipt))
            cp['workers'].pop(key,None);first_terminal(cp,key,worker)
            if common_failure(error):block_source(root,manifest,cp,error,arm=worker['arm'],day=worker['day'])
    refresh_retries(root,cp)
    if cp['state']=='SOURCE_BLOCKED':
        cp.update(UTC=now(),parallel_workers=0)
        return
    advance_sweeps(cp)
    both=all(arm in cp['first_sweeps_completed'] for arm in ('B2','B3'))
    if not both:
        arm='B2' if 'B2' not in cp['first_sweeps_completed'] else 'B3'
    elif cp['workers']:
        arms={worker['arm'] for worker in cp['workers'].values()}
        if len(arms)!=1:
            block_source(root,manifest,cp,PermissionError('GLOBAL_SOURCE_INTEGRITY_FAILURE:CROSS_ARM_WORKERS'))
            return
        arm=next(iter(arms))
    else:
        pending=[row for row in queue(root)['entries'] if row['verification_status'] in ('READY_VERIFIED_REPAIR','DISPATCH_INTENT')]
        pending.sort(key=lambda row:(-row['retry_priority'],row['queued_UTC']))
        arm=pending[0]['arm'] if pending else None
    if arm is None:
        complete=all(row['status']=='PASS' for row in cp['dates'].values())
        transition(cp,'CAMPAIGN_COMPLETE' if complete else 'CAMPAIGN_SWEEP_COMPLETE_WITH_FAILURES')
        cp.update(UTC=now(),parallel_workers=0)
        return
    if both:transition(cp,arm+'_REPAIRING')
    limit=3 if arm=='B2' else 1
    # A first sweep ends at all 31 terminal first attempts. Queued retries can
    # use free slots while ordinary dates remain, then yield to the next arm.
    allow_retries=both or not sweep_complete(cp,arm)
    atomic(root/'SUPERVISOR_STATE.json',cp)
    for slot in range(1,limit+1):
        if cp['state']=='SOURCE_BLOCKED':break
        if slot in {worker['worker_slot'] for worker in cp['workers'].values()}:continue
        other=external_workers(cp)
        if other:
            cp['dispatch_wait']=dict(reason='EXTERNAL_SCIENTIFIC_WORKER_ACTIVE',workers=other,UTC=now())
            continue
        retry=None
        if allow_retries:
            try:retry=dispatch_ready(root,arm,slot,manifest)
            except LeaseBusy:
                cp['dispatch_wait']=dict(reason='RECOVERY_QUEUE_BEING_UPDATED',UTC=now());continue
            except Exception as error:
                if common_failure(error):block_source(root,manifest,cp,error,arm=arm)
                else:cp['dispatch_wait']=dict(reason='RECOVERY_RECONCILIATION_REQUIRED',error=str(error),UTC=now())
                continue
        if retry:
            key=arm+'/'+retry['day'];activate_retry(cp,key,retry)
            atomic(root/'SUPERVISOR_STATE.json',cp);continue
        day=None if both else next_day(cp,arm)
        if day:safe_dispatch(root,manifest,cp,arm,day,slot)
    refresh_retries(root,cp)
    cp.update(UTC=now(),parallel_workers=limit if cp['state']!='SOURCE_BLOCKED' else 0)

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
        while True:
            # Only later attempts read the updated deployment registry. Live
            # workers retain their immutable request, cwd and source seal.
            manifest=read(root/'AUTONOMOUS_MANIFEST.json')
            if manifest['B2_workers']!=3 or manifest['B3_workers']!=1:raise PermissionError('WORKER_COUNT_DRIFT')
            cycle(root,manifest,cp)
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

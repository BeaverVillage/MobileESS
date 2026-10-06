"""Serial independent dates; timeout/failure isolation and bounded infra retry.

Locks are OS byte locks, released by the OS after crashes. PID identity includes
creation time and command. A live orphan worker is adopted, never duplicated.
Resource observations do not control admission, settings or cancellation.
"""
import msvcrt,time,traceback,threading
from .common import *

TERMINAL={'PASS','TIMEOUT','INCONCLUSIVE','SCIENTIFIC_INFEASIBLE','NUMERICAL_FAILURE','IMPLEMENTATION_FAILURE','OS_RESOURCE_FAILURE','FRESH_AC_FAILURE','VALIDATION_FAILURE'}
INFRA_RETRIES=2

def load_checkpoint(root,freeze):
    path=root/'CHECKPOINT.json'
    if path.exists():
        try:cp=read(path)
        except (ValueError,OSError) as e:
            # Restore only a SHA-verified prior atomic generation. Preserve bad
            # bytes. A valid live worker identity is kept in separate ACTIVE.
            backup=root/'CHECKPOINT_PREVIOUS.json';receipt=root/'CHECKPOINT_PREVIOUS_SHA.json'
            if not backup.is_file() or not receipt.is_file() or sha(backup)!=read(receipt)['sha256']:raise ValueError('CORRUPT_CHECKPOINT_NO_VERIFIED_BACKUP') from e
            damaged=root/('CHECKPOINT_CORRUPT_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'.json');path.replace(damaged)
            cp=read(backup);atomic(path,cp)
    else:cp=dict(run_id=freeze['run_id'],dates={d:dict(status='PENDING',infra_retries=0,attempts=0) for d in DAYS},stages={},state='RUNNING')
    if cp.get('run_id')!=freeze['run_id'] or set(cp['dates'])!=set(DAYS):raise PermissionError('CHECKPOINT_RUN_OR_DATE_AXIS_DRIFT')
    return cp

def save_checkpoint(root,cp):
    path=root/'CHECKPOINT.json'
    if path.is_file():
        import shutil
        shutil.copyfile(path,root/'CHECKPOINT_PREVIOUS.json');atomic(root/'CHECKPOINT_PREVIOUS_SHA.json',dict(sha256=sha(root/'CHECKPOINT_PREVIOUS.json')))
    cp['updated_UTC']=now();atomic(path,cp)

def counts(cp):
    rows=list(cp['dates'].values());return dict(PASS=sum(r['status']=='PASS' for r in rows),TIMEOUT=sum(r['status']=='TIMEOUT' for r in rows),
        FAIL=sum(r['status'] in TERMINAL-{'PASS','TIMEOUT'} for r in rows),pending=sum(r['status'] not in TERMINAL for r in rows))

def recover_active_checkpoint(root,freeze,cp):
    active=read(root/'ACTIVE.json') if (root/'ACTIVE.json').exists() else {}
    if not active.get('request'):return
    req=read(active['request']);day,stage=req['day'],req['stage']
    if req['identity']!=identity(freeze,day,stage) or not Path(active['request']).resolve().is_relative_to(root):raise ValueError('ORPHAN_REQUEST_IDENTITY')
    for prior,row in req['dependencies'].items():
        receipt=read(row['receipt'])
        if sha(row['receipt'])!=row['sha256'] or not valid_receipt(receipt,identity(freeze,day,prior),root):raise ValueError('ORPHAN_CAUSAL_DEPENDENCY')
        cp['stages'][day+'/'+prior]=dict(status='PASS',receipt=row['receipt'],sha256=row['sha256'])
    key=day+'/'+stage
    if cp['stages'].get(key,{}).get('status')!='PASS':
        cp['stages'][key]=dict(status='RUNNING',request=active['request'],attempt=int(Path(active['request']).parent.name))
        cp['dates'][day]['status']='RUNNING';cp['dates'][day]['stage']=stage
    elif same_process(active.get('worker',{})):raise ValueError('LIVE_WORKER_FOR_ALREADY_COMPLETE_STAGE')

def status(root,freeze,cp,active):
    current=read(root/'ACTIVE.json') if (root/'ACTIVE.json').exists() else active
    progress={}
    if current and current.get('request') and Path(current['request']).exists():
        req=read(current['request']);p=Path(req['progress'])
        if p.is_file():
            try:progress=read(p)
            except (OSError,ValueError):pass
    totals=counts(cp);memory=psutil.virtual_memory()
    hb=dict(timestamp_UTC=now(),process=process(),state=cp['state'],active=current,resource_information_only=True)
    atomic(root/'B1_HEARTBEAT.json',hb)
    atomic(root/'B1_LIVE_STATUS.json',dict(state=cp['state'],run_id=freeze['run_id'],PASS_days=totals['PASS'],timeout_days=totals['TIMEOUT'],failed_days=totals['FAIL'],
        pending_days=totals['pending'],active=current,progress=progress,day_rows=[dict(day=d,**r) for d,r in cp['dates'].items()],
        total_dates=31,completed_stages=sum(r.get('status')=='PASS' for r in cp['stages'].values()),memory_information_only=True,
        memory_available=memory.available,memory_total=memory.total,commit_information=psutil.swap_memory()._asdict(),timestamp_UTC=now()))

def observe(root):
    active=read(root/'ACTIVE.json') if (root/'ACTIVE.json').is_file() else {}
    mem=psutil.virtual_memory();row=dict(UTC=now(),day=active.get('day'),stage=active.get('stage'),worker_PID=None,RSS=None,CPU_seconds=None,
        available_RAM=mem.available,total_RAM=mem.total,telemetry_only=True,admission_or_cancellation_action=False)
    if same_process(active.get('worker',{})):
        p=psutil.Process(active['worker']['PID']);cpu=p.cpu_times();row.update(worker_PID=p.pid,RSS=p.memory_info().rss,CPU_seconds=cpu.user+cpu.system)
    path=root/'MAY_B1_RESOURCE_LEDGER.csv';new=not path.exists()
    with path.open('a',encoding='utf8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(row),lineterminator='\n')
        if new:w.writeheader()
        w.writerow(row)

def append_error(root,day,failure,error,action,resolution='RECORDED'):
    path=root/'ERROR_REPAIR_LEDGER.json';rows=read(path) if path.exists() else []
    rows.append(dict(timestamp=now(),date=day,failure_class=failure,error=error,root_cause=error,code_changed=False,scientific_model_changed=False,
        tests='frozen infrastructure regressions',old_SHA='',new_SHA='',action=action,rerun_required=action=='RETRY_FROM_VALID_STAGE',resolution=resolution))
    atomic(path,rows)
    table(root/'MAY_B1_ERROR_REPAIR_LEDGER.csv',rows,['timestamp','date','failure_class','error','root_cause','code_changed','scientific_model_changed','tests','old_SHA','new_SHA','action','rerun_required','resolution'])

def export(root,freeze,cp):
    totals=counts(cp);rows=[dict(day=d,**r) for d,r in cp['dates'].items()]
    table(root/'MAY_B1_PROGRESS.csv',rows,['day','status','stage','attempts','infra_retries','error','reused'])
    table(root/'MAY_B1_FINAL_DATE_STATUS.csv',rows,['day','status','stage','attempts','infra_retries','error','reused'])
    order={'IMPLEMENTATION_FAILURE':1,'OS_RESOURCE_FAILURE':1,'VALIDATION_FAILURE':2,'FRESH_AC_FAILURE':2,'NUMERICAL_FAILURE':3,'TIMEOUT':4,'INCONCLUSIVE':5,'SCIENTIFIC_INFEASIBLE':5}
    repair=[dict(r,priority=order.get(r['status'],9),resolution='RECORDED_BUDGET_UNCHANGED' if r['status']=='TIMEOUT' else 'NEEDS_EXACT_REPAIR') for r in rows if r['status'] in TERMINAL-{'PASS'}]
    repair.sort(key=lambda r:(r['priority'],r['day']))
    table(root/'MAY_B1_REPAIR_QUEUE.csv',repair,['day','status','priority','stage','attempts','infra_retries','error','resolution'])
    atomic(root/'CAMPAIGN_SUMMARY.json',dict(run_id=freeze['run_id'],counts=totals,all_31_attempted=totals['pending']==0,
        repair_queue_resolved=not repair,repair_queue_count=len(repair),Actual_reoptimization=0,PQ_repair=0,memory_guards=False,
        artificial_slowdown=False,parameter_sweep=False,cumulative_budget_per_date=BUDGET,scientific_infeasible_proven_dates=0))

def result_or_error(root,freeze,cp,day,stage,req,exit_code):
    entry=cp['stages'][day+'/'+stage]
    result=Path(req['result']);error=Path(req['error'])
    if result.is_file():
        receipt=read(result)
        if valid_receipt(receipt,identity(freeze,day,stage),root):
            entry.update(status='PASS',receipt=str(result),sha256=sha(result));save_checkpoint(root,cp);return 'PASS'
        failure='IMPLEMENTATION_FAILURE';detail='OUTPUT_RECEIPT_IDENTITY_OR_SHA_FAILED';transient=False
    elif error.is_file():
        e=read(error);failure=e['classification'];detail=e['error'];transient=e['type'] in ('OSError','IOError') and not detail.startswith('[Errno 2]')
    else:
        # STATUS_NO_MEMORY / STATUS_INSUFFICIENT_RESOURCES are actual OS exit
        # evidence. Memory size alone never supplies an OOM diagnosis.
        failure='OS_RESOURCE_FAILURE' if exit_code is not None and exit_code&0xffffffff in (0xc0000017,0xc000009a) else 'IMPLEMENTATION_FAILURE'
        detail='WORKER_EXIT_WITHOUT_ATOMIC_RECEIPT:'+str(exit_code);transient=True
    entry.update(status='FAIL',error=detail,failure_class=failure)
    dr=cp['dates'][day]
    if transient and dr['infra_retries']<INFRA_RETRIES:
        dr['infra_retries']+=1;dr['status']='PENDING'
        append_error(root,day,failure,detail,'RETRY_FROM_VALID_STAGE','BOUNDED_RETRY_SCHEDULED')
        save_checkpoint(root,cp);return 'RETRY'
    dr.update(status=failure,stage=stage,error=detail)
    append_error(root,day,failure,detail,'REPAIR_QUEUE_CONTINUE_NEXT_DATE')
    save_checkpoint(root,cp);return 'FAIL'

def run(root):
    root=Path(root).resolve();freeze=read(root/'B1_PRODUCTION_FREEZE_MANIFEST.json');verify_freeze(freeze)
    lock=(root/'COORDINATOR.lock').open('a+b');lock.seek(0)
    if not lock.read(1):lock.write(b'0');lock.flush()
    lock.seek(0)
    try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
    except OSError:return 0
    cp=load_checkpoint(root,freeze);recover_active_checkpoint(root,freeze,cp);cp['state']='RUNNING';save_checkpoint(root,cp);stop=threading.Event()
    def ticker():
        while not stop.wait(1):
            try:status(root,freeze,cp,None);observe(root)
            except Exception as e:atomic(root/'STATUS_EXCEPTION.json',dict(UTC=now(),error=str(e)))
    monitor=threading.Thread(target=ticker,daemon=True);monitor.start()
    try:
        for day in DAYS:
            dr=cp['dates'][day]
            if dr['status'] in TERMINAL:continue
            if day not in freeze['day_input_SHA']:
                dr.update(status='IMPLEMENTATION_FAILURE',stage='INPUT',attempts=1,error='ORIGINAL_PR134_INPUT_AUTHORITY_UNAVAILABLE')
                append_error(root,day,'IMPLEMENTATION_FAILURE',dr['error'],'REPAIR_QUEUE_CONTINUE_NEXT_DATE');save_checkpoint(root,cp);continue
            dr['status']='RUNNING'
            for stage in STAGES:
                key=day+'/'+stage;entry=cp['stages'].get(key,{})
                if entry.get('status')=='PASS':
                    if sha(entry['receipt'])!=entry['sha256'] or not valid_receipt(read(entry['receipt']),identity(freeze,day,stage),root):raise ValueError('COMPLETED_STAGE_TAMPER:'+key)
                    continue
                while True:
                    dr['stage']=stage;deps={s:dict(receipt=cp['stages'][day+'/'+s]['receipt'],sha256=cp['stages'][day+'/'+s]['sha256']) for s in STAGES[:STAGES.index(stage)]}
                    orphan=read(root/'ACTIVE.json') if (root/'ACTIVE.json').exists() else None
                    adopt=bool(orphan and orphan.get('day')==day and orphan.get('stage')==stage and same_process(orphan.get('worker',{})))
                    child=None
                    if orphan and same_process(orphan.get('worker',{})) and not adopt:raise ValueError('LIVE_ORPHAN_DIFFERENT_STAGE_REQUIRES_CAUSAL_CHECKPOINT_RECONSTRUCTION')
                    if entry.get('status')=='RUNNING' and not adopt and entry.get('request'):
                        prior_request=read(entry['request'])
                        prior_outcome=result_or_error(root,freeze,cp,day,stage,prior_request,None)
                        atomic(root/'ACTIVE.json',{})
                        if prior_outcome=='PASS':outcome='PASS';break
                        if prior_outcome=='FAIL':outcome='FAIL';break
                        entry=cp['stages'][key]
                    if adopt:
                        req=read(orphan['request']);active=orphan;entry=cp['stages'][key]
                    else:
                        number=int(entry.get('attempt',0))+1;attempt=root/'stages'/day/stage/str(number);attempt.mkdir(parents=True,exist_ok=False)
                        req=dict(root=str(root),day=day,stage=stage,identity=identity(freeze,day,stage),dependencies=deps,output=str(attempt/'output'),
                            progress=str(attempt/'progress.json'),result=str(attempt/'result.json'),error=str(attempt/'error.json'))
                        atomic(attempt/'request.json',req);entry=dict(status='RUNNING',request=str(attempt/'request.json'),attempt=number);cp['stages'][key]=entry
                        dr['attempts']+=stage=='A1';save_checkpoint(root,cp)
                        try:
                            stdout=(attempt/'stdout.log').open('ab');stderr=(attempt/'stderr.log').open('ab')
                            child=subprocess.Popen([freeze['Python'],'-X','utf8','-m','v42_pr134_b1.worker',str(attempt/'request.json')],cwd=ROOT,stdout=stdout,stderr=stderr)
                            child_identity=process(child.pid);stdout.close();stderr.close()
                        except OSError as e:
                            atomic(req['error'],dict(type='OSError',classification='IMPLEMENTATION_FAILURE',error=str(e),UTC=now()));child_identity={}
                        active=dict(day=day,stage=stage,request=entry['request'],worker=child_identity,started_UTC=now())
                        atomic(root/'ACTIVE.json',active)
                    status(root,freeze,cp,active)
                    while same_process(active['worker']):
                        if child and child.poll() is not None:break
                        time.sleep(.5)
                    code=child.wait() if child else None
                    outcome=result_or_error(root,freeze,cp,day,stage,req,code)
                    atomic(root/'ACTIVE.json',{})
                    if outcome=='RETRY':entry=cp['stages'][key];continue
                    break
                if outcome=='FAIL':break
            if all(cp['stages'].get(day+'/'+s,{}).get('status')=='PASS' for s in STAGES):dr['status']='PASS';dr['finished_UTC']=now()
            save_checkpoint(root,cp);export(root,freeze,cp)
        cp['state']='COMPLETE' if counts(cp)['pending']==0 else 'FAIL';save_checkpoint(root,cp);export(root,freeze,cp);status(root,freeze,cp,None)
        # Scientific/numerical/validation defects remain honest repair cases.
        # Only infrastructure cases have deterministic bounded retries above.
        from .finalize import publish
        publish(root,freeze,cp)
    except BaseException as error:
        atomic(root/'COORDINATOR_ERROR.json',dict(error=str(error),traceback=traceback.format_exc(),UTC=now(),process=process()))
        raise
    finally:
        stop.set();monitor.join(timeout=3);lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_UNLCK,1);lock.close()
    return 0

if __name__=='__main__':
    import sys
    sys.exit(run(sys.argv[1]))

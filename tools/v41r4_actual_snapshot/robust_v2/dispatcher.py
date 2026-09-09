"""One shared four-day budget. Adopt live DA workers; dispatch Actual first."""
from binding import *
import time,subprocess,traceback,psutil,re
POLICIES=('B0','B1','B2','B3')
DA_PHASES=['electrical','domain']+[p+'_DA' for p in POLICIES]
CAP=4
HISTORICAL=ROOT/'frozen_artifacts/v41r4_actual_eta95_qsafe_v1'

def diagnostic_jobs():
    path=OUT/'DIAGNOSTIC_QUEUE.json'
    return read(path) if path.exists() else []

def atomic(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(path.name+f'.{os.getpid()}.tmp')
    tmp.write_text(json.dumps(value,indent=2,ensure_ascii=False),encoding='utf-8')
    # The live monitor can briefly hold the destination open on Windows.
    for attempt in range(101):
        try:
            os.replace(tmp,path)
            break
        except PermissionError:
            if attempt==100:raise
            time.sleep(.05)

def scan_workers():
    found=[]
    diagnostic_scripts={str(Path(r['script'])).replace('\\','/').lower() for r in diagnostic_jobs()}
    for p in psutil.process_iter(['pid','cmdline','create_time']):
        cmd=p.info['cmdline'] or []
        scripts=[str(x).replace('\\','/').lower() for x in cmd]
        if any(x.endswith(('/mission_cut_worker.py','/mission_empty_recover.py','/v41r4_search_worker.py','/mission_worker.py','/mission_actual_worker.py','/v41r4_loop_worker.py')) or x in {str(OUT/'actual_worker.py').replace('\\','/').lower(),str(HISTORICAL/'actual_worker.py').replace('\\','/').lower()} or x in diagnostic_scripts for x in scripts):
            day=next((x for x in cmd if len(x)==10 and x.startswith('2025-05-')),None)
            if day:found.append(dict(pid=p.pid,day=day,cmd=cmd,created_at=p.info['create_time']))
    occupied={r['day'] for r in found}
    # A bounded solver belongs to its parent day, not a second day worker.
    # If that parent exits unexpectedly, retain its capacity reservation.
    for p in psutil.process_iter(['pid','cmdline','create_time']):
        cmd=p.info['cmdline'] or []
        if any('dayahead.v41r1.bounded_' in str(x) for x in cmd):
            match=re.search(r'2025-05-\d{2}',' '.join(cmd))
            if match and match.group() not in occupied:
                day=match.group();found.append(dict(pid=p.pid,day=day,cmd=cmd,created_at=p.info['create_time'],orphan_bounded_solver=True));occupied.add(day)
    return found

def alive(r):
    try:
        p=psutil.Process(r['worker_pid'])
        return p.is_running() and p.create_time()==r['created_at']
    except psutil.NoSuchProcess:return False

def da_pass(day,policy):
    path=RUN/'audit'/day/f'PHASE_{policy}_DA.json'
    return path.exists() and read(path).get('status')=='PASS' and (RUN/day/policy/'dayahead/DAYAHEAD_RECEIPT.json').exists()

def actual_done(day,policy):
    path=OUT/'replays'/day/policy/'CANDIDATE_RECEIPT.json'
    return path.exists() and read(path).get('status')=='COMPLETE'

def choose(days,occupied,blocked,recovery_used):
    resource_path=OUT/'TEMPORARY_RESOURCE_POLICY.json'
    resource=read(resource_path) if resource_path.exists() else {}
    split=resource.get('status')=='ACTIVE'
    current=scan_workers()
    diag_scripts={str(Path(j['script'])).replace('\\','/').lower() for j in diagnostic_jobs()}
    def actual_or_audit(r):
        return any(str(x).replace('\\','/').lower() in diag_scripts or str(x).endswith(('actual_worker.py','performance_worker.py')) for x in r['cmd'])
    actual_count=sum(actual_or_audit(r) for r in current)
    da_count=len(current)-actual_count
    for job in diagnostic_jobs():
        if split and actual_count>=resource['MAX_ACTUAL_WORKERS']:break
        if job['day'] in occupied or (job['day'],job['phase']) in blocked:continue
        if Path(job['result']).exists():continue
        if any(not Path(p).exists() or read(p).get('status')!='COMPLETE' for p in job.get('depends_on',[])):continue
        assert any(Path(job['script']).resolve().is_relative_to((OUT/name).resolve()) for name in ('diagnostics','acceleration_audit'))
        assert sha(job['script'])==job['script_SHA']
        return job['day'],job['phase'],[job['script'],*job.get('arguments',[job['day']])],False
    for day in days:
        hold=OUT/'ACTUAL_DISPATCH_HOLD.json'
        if hold.exists() and read(hold).get('status')=='HOLD':break
        if split and actual_count>=resource['MAX_ACTUAL_WORKERS']:break
        if day in occupied:continue
        for policy in POLICIES:
            phase=policy+'_ETA95_QSAFE_AC'
            if (day,phase) not in blocked and da_pass(day,policy) and not actual_done(day,policy):
                return day,phase,[str(OUT/'actual_worker.py'),day,policy],False
    if split and da_count>=resource['MAX_DA_FRESH_WORKERS']:return None
    for day in sorted(days):
        if day in occupied:continue
        for phase in DA_PHASES:
            r=RUN/'audit'/day/f'PHASE_{phase}.json'
            if r.exists() and read(r).get('status')=='PASS':continue
            if (day,phase) in blocked:break
            if not r.exists():
                # Never restart a completed expensive DA optimization because a phase wrapper is missing.
                if phase.endswith('_DA') and (RUN/day/phase[:2]/'dayahead/DAYAHEAD_RECEIPT.json').exists():
                    blocked.add((day,phase));break
                return day,phase,[str(ROOT/'mission_cut_worker.py'),day,phase],False
            error=read(r).get('error','')
            key=(day,phase)
            if key not in recovery_used and phase in ('B2_DA','B3_DA') and error=="ValueError('DAYAHEAD_FRESH_PHYSICAL_VIOLATION')":
                return day,phase,[str(ROOT/'mission_cut_worker.py'),'resume',day,phase[:2]],True
            if key not in recovery_used and phase=='B0_DA' and 'DataFrame.columns are different' in error and 'inferred_type' in error:
                return day,phase,[str(ROOT/'mission_empty_recover.py'),day],True
            blocked.add(key);break
    return None

def main():
    method=verify_method();days=method['development_days']+method['holdout_days']
    from dayahead.v41.campaign import campaign_lock
    with campaign_lock(OUT/'dispatcher_lock'):
        snapshot=read(OUT/'HANDOFF_SNAPSHOT.json');active={};children={};started=time.time()
        prior_status=OUT/'DISPATCHER_STATE.json'
        resume=read(prior_status) if prior_status.exists() else None
        if resume:
            for r in resume['active']:
                r.setdefault('policy',r['phase'][:2] if r['phase'].startswith('B') else None)
                if alive(r):active[r['day']]=r
        else:
            for r in snapshot['live_workers']:
                entry={k:v for k,v in r.items() if k not in ('command','CPU_seconds')}
                entry['adopted']=True
                if entry['kind']=='ACTUAL_ONLY':
                    entry['kind']='HISTORICAL_ACTUAL_DRAIN'
                    entry['phase']=entry['policy']+'_HISTORICAL_ACTUAL_DRAIN'
                    entry['historical_receipt']=str(HISTORICAL/'replays'/entry['day']/entry['policy']/'CANDIDATE_RECEIPT.json')
                if alive(entry):active[entry['day']]=entry
        # Retire the suspended parent only; no child process is stopped or suspended.
        old_pid=read(OUT/'SWITCH_STATUS.json')['legacy_coordinator_suspended_pid']
        try:
            parent=psutil.Process(old_pid)
            assert any(str(x).endswith('dispatcher.py') for x in parent.cmdline())
            parent.terminate();parent.wait(timeout=10)
        except psutil.NoSuchProcess:pass
        # Retire the legacy status publisher so historical Actual cannot mask the candidate status.
        for p in psutil.process_iter(['cmdline']):
            if any(str(x).endswith('mission_loop_ui.py') for x in (p.info['cmdline'] or [])):
                p.terminate()
        with campaign_lock(RUN):
            errors=list(resume.get('errors',[])) if resume else []
            completed=list(resume.get('completed_phases',[])) if resume else []
            blocked=set(tuple(x) for x in resume.get('blocked',[])) if resume else set()
            recovery_used=set(tuple(x) for x in resume.get('recovery_used',[])) if resume else set()
            launches=list(read(OUT/'RESOURCE_LAUNCH_AUDIT.json')) if (OUT/'RESOURCE_LAUNCH_AUDIT.json').exists() else []
            atomic(OUT/'HANDOFF_COMPLETE.json',dict(status='PASS',at=started,new_supervisor_pid=os.getpid(),adopted_workers=list(active.values()),expensive_worker_preemptions=0,old_parent_only_retired=old_pid,common_cap=CAP))
            last_report=0
            while True:
                verify_method()
                for day,r in list(active.items()):
                    if alive(r):continue
                    proc=children.pop(r['worker_pid'],None)
                    if proc:proc.poll()
                    active.pop(day)
                    if r['kind']=='HISTORICAL_ACTUAL_DRAIN':
                        receipt=Path(r['historical_receipt']);ok=receipt.exists() and read(receipt).get('status')=='COMPLETE'
                    elif r['kind']=='DIAGNOSTIC_ONLY':
                        receipt=Path(r['diagnostic_result']);ok=receipt.exists() and read(receipt).get('status')=='COMPLETE'
                    elif r['kind']=='ACTUAL_ONLY':ok=actual_done(day,r['policy'])
                    else:
                        receipt=RUN/'audit'/day/f"PHASE_{r['phase']}.json"
                        ok=receipt.exists() and read(receipt).get('status')=='PASS'
                    if ok:
                        completed.append(dict(day=day,phase=r['phase'],worker_pid=r['worker_pid'],finished_at=time.time()))
                        print('WORK_COMPLETE',day,r['phase'],flush=True)
                    else:
                        if r['kind'] in ('ACTUAL_ONLY','DIAGNOSTIC_ONLY') or r.get('recovery'):blocked.add((day,r['phase']))
                        errors.append(dict(day=day,phase=r['phase'],error='WORKER_EXIT_REQUIRES_DIAGNOSIS',log=r['log'],time=time.time()))
                        print('ISOLATED_FAILURE',day,r['phase'],r['log'],flush=True)
                actual_workers=scan_workers()
                known={r['worker_pid'] for r in active.values()}
                unowned=[r for r in actual_workers if r['pid'] not in known]
                # An unexpected external worker counts against capacity and blocks its date.
                occupied=set(active)|{r['day'] for r in unowned}
                while len(actual_workers)<CAP and psutil.virtual_memory().available>4*1024**3:
                    job=choose(days,occupied,blocked,recovery_used)
                    if not job:break
                    day,phase,args,recovery=job
                    verify_method()
                    log=OUT/'logs'/day/f'{phase}_{time.time_ns()}.log';log.parent.mkdir(parents=True,exist_ok=True)
                    env=os.environ.copy();env.pop('V41R3_MAY_DATE',None);env.pop('V41_FO_RECOVERY_PLAN',None)
                    env['V41R4_MAY_DATE']=day;env['PYTHONDONTWRITEBYTECODE']='1'
                    is_actual=phase.endswith('_ETA95_QSAFE_AC')
                    diagnostic=next((j for j in diagnostic_jobs() if j['day']==day and j['phase']==phase),None)
                    env['PYTHONPATH']=str(ROOT) if is_actual or diagnostic else str(ROOT/'v41r4_search_bootstrap')+os.pathsep+str(ROOT)
                    if is_actual or diagnostic:
                        for k in ('OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS','NUMEXPR_NUM_THREADS'):env[k]='1'
                    # Recount immediately before launch, with the single campaign lock held.
                    current=scan_workers()
                    if len(current)>=CAP or any(r['day']==day for r in current):break
                    with log.open('x',encoding='utf-8') as f:
                        proc=subprocess.Popen([sys.executable,'-u',*args],cwd=ROOT,env=env,stdin=subprocess.DEVNULL,stdout=f,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
                    created=psutil.Process(proc.pid).create_time()
                    r=dict(day=day,phase=phase,worker_pid=proc.pid,created_at=created,started_at=time.time(),log=str(log),kind='DIAGNOSTIC_ONLY' if diagnostic else 'ACTUAL_ONLY' if is_actual else 'DA_FRESH',policy=phase[:2] if phase.startswith('B') else None,recovery=recovery)
                    if diagnostic:r['diagnostic_result']=diagnostic['result']
                    active[day]=r;children[proc.pid]=proc;occupied.add(day)
                    if recovery:recovery_used.add((day,phase))
                    launches.append(dict(**r,workers_before=len(current),workers_after=len(current)+1,available_RAM_GB=psutil.virtual_memory().available/1024**3,method_SHA=sha(OUT/'METHOD_FREEZE.json')))
                    atomic(OUT/'RESOURCE_LAUNCH_AUDIT.json',launches)
                    print('LAUNCH',day,phase,'COMMON_WORKERS',len(current)+1,flush=True)
                    actual_workers=scan_workers()
                total=sum(actual_done(d,p) for d in days for p in POLICIES)
                state=dict(status='RUNNING' if active else 'COMPLETE' if total==124 else 'NEEDS_ATTENTION',supervisor_pid=os.getpid(),active=list(active.values()),external_workers=unowned,completed_phases=completed,errors=errors,blocked=sorted(blocked),recovery_used=sorted(recovery_used),updated_at=time.time(),started_at=started,day_workers=CAP,solver_threads_per_day=4,alpha_BG=1.15,Actual_method=method['version'],Actual_completed_units=total,Actual_total_units=124,Actual_priority=True,common_active_workers=len(actual_workers))
                atomic(OUT/'DISPATCHER_STATE.json',state);atomic(RUN/'campaign_progress.json',state);atomic(RUN/'audit/MAY_CAMPAIGN_STATUS.json',state)
                units={}
                for day in sorted(days):
                    for policy in POLICIES:
                        complete=actual_done(day,policy)
                        r=dict(day=day,policy=policy,status='COMPLETE' if complete else 'DA_COMPLETE' if da_pass(day,policy) else 'WAITING',phase='ETA95_QSAFE complete' if complete else 'Actual 대기' if da_pass(day,policy) else 'queued',worker_pid=None,Actual_method=method['version'],historical_Actual_available=(RUN/day/policy/'actual/ACTUAL_RECEIPT.json').exists())
                        a=active.get(day)
                        if a and (a.get('policy')==policy or (policy=='B0' and a['phase'] in ('electrical','domain'))):r.update(status='RUNNING',phase=a['phase'],worker_pid=a['worker_pid'],log=a['log'])
                        failed=[e for e in errors if e['day']==day and e['phase'].startswith(policy) and (day,e['phase']) in blocked]
                        if failed and not complete:r.update(status='FAILED',error=failed[-1]['error'])
                        units[day+'|'+policy]=r
                atomic(RUN/'campaign_state.json',dict(status=state['status'],units=units,updated_at=time.time(),source=method['version']))
                if time.time()-last_report>60:
                    try:
                        from report_candidate import publish
                        publish()
                    except Exception:print('REPORT_ERROR',traceback.format_exc(),flush=True)
                    last_report=time.time()
                if not active and not unowned:
                    if total==124:atomic(OUT/'CAMPAIGN_FINISHED.json',dict(status='COMPLETE',finished_at=time.time(),Actual_completed_units=total))
                    print('DISPATCHER_IDLE',state['status'],total,flush=True)
                    if total==124:break
                time.sleep(3)

if __name__=='__main__':
    try:main()
    except BaseException:
        atomic(OUT/'DISPATCHER_FATAL.json',dict(at=time.time(),traceback=traceback.format_exc()))
        raise

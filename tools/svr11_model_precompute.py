"""Separate ten-worker Forecast-only stage; no policy solver or Actual calls."""
from pathlib import Path
import sys,os,time,subprocess,threading,traceback,copy
import psutil
SOURCE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SOURCE));sys.path.insert(0,str(SOURCE/'tools'))
from v42_pr134_b1.common import read,record,atomic,now,sha
from v42_common_campaign.authority import singleton
from v42_svr11.authority import verify,scope
from v42_svr11.processes import identity,live
from v42_svr11 import DAYS
SCRIPT=Path(__file__).resolve()
GIB=1024**3

def contract(root):
    m=verify(root/'CAMPAIGN_MANIFEST.json');c=read(root/'MODEL_PRECOMPUTE_REQUEST.json')
    if not (c['PASS'] and c['source_SHA']==m['execution_SHA'] and c['model_only']
        and c['max_workers']==10 and c['Native_optimizer_calls']==c['Actual_calls']==0):
        raise PermissionError('SVR11_GLOBAL_MODEL_PRECOMPUTE_CONTRACT_DRIFT')
    for key in ('thread_budget_validation',):
        if key in c and record(c[key]['path'])!=c[key]:raise PermissionError('SVR11_GLOBAL_MODEL_PRECOMPUTE_PROOF_DRIFT')
    return m,c

def admits(memory,peers,c):
    ram=c['worker_reservation_bytes'];commit=c.get('commit_reservation_bytes',2*GIB)
    ram_growth=ram;commit_growth=commit
    for p in peers:
        v=psutil.Process(p['PID']).memory_info()
        ram_growth+=max(0,ram-v.rss)
        commit_growth+=max(0,commit-getattr(v,'private',v.rss))
    reserve=c['system_reserve_bytes']
    return memory['RAM_available']>=reserve+ram_growth and memory['Commit_available']>=reserve+commit_growth

def check_model(root,m,day):
    from v42_svr11.model import load_coefficients,verify_coefficients
    path=root/'models'/day/'ELECTRICAL_CERTIFICATE.json';v=read(path)
    if not (v['day']==day and v['source_SHA']==m['execution_SHA'] and v['Actual_inputs_read']==0
        and v['tap_optimization_variables']==0 and v['scenario_SHA']==read(m['scenario']['path'])['scenario_SHA']
        and v['equipment_SHA']==read(m['hardware']['path'])['equipment_SHA']):
        raise PermissionError('SVR11_GLOBAL_PRECOMPUTED_MODEL_BINDING_DRIFT')
    with scope(root/'CAMPAIGN_MANIFEST.json'):verify_coefficients(v,day,load_coefficients(v,day))
    return record(path)

def worker(path):
    request=read(path);root=Path(request['root']);day=request['day'];attempt=Path(path).parent
    start=time.perf_counter();me=identity();state=dict(day=day,phase='MODEL_ONLY_ADMISSION',source_SHA=request['source_SHA'],
        worker=me,Native_Runtime=0,Actual_calls=0);stop=threading.Event();mutex=threading.RLock()
    def progress(v):
        with mutex:
            state.update(v,UTC=now(),wall_seconds=time.perf_counter()-start)
            info=psutil.Process().memory_info();state.update(RSS_bytes=info.rss,private_bytes=getattr(info,'private',info.rss))
            atomic(attempt/'progress.json',state)
    def ticker():
        while not stop.wait(10):progress({})
    thread=threading.Thread(target=ticker,daemon=True)
    result=dict(PASS=False,status='FAIL',day=day,source_SHA=request['source_SHA'],worker=me,
        request=record(path),Native_optimizer_calls=0,Actual_calls=0,Native_Runtime=0)
    with singleton(root/'models'/day/'MODEL_ONLY.lock'):
        if (attempt/'RESULT.json').exists():raise PermissionError('MODEL_ONLY_COMPLETED_ATTEMPT_NEVER_REEXECUTED')
        thread.start();progress({})
        try:
            m,c=contract(root)
            if request['source_SHA']!=m['execution_SHA'] or request['manifest']!=record(root/'CAMPAIGN_MANIFEST.json'):
                raise PermissionError('SVR11_GLOBAL_MODEL_ONLY_REQUEST_DRIFT')
            from v42_may_campaign_native90.common import environment
            environment(attempt)
            # Only the already-reviewed input/model producer is invoked here.
            # Policy optimization and Actual execution are outside this process.
            from v42_svr11.stages import inputs
            with scope(root/'CAMPAIGN_MANIFEST.json'):
                inputs(dict(day=day,arm='B2',input_folder=str(root/'model_inputs'/day)),progress)
            cert=check_model(root,m,day)
            if list(attempt.rglob('NATIVE_RUNTIME_LEDGER.json')):
                raise PermissionError('SVR11_GLOBAL_MODEL_ONLY_NATIVE_CALL_FORBIDDEN')
            result.update(PASS=True,status='PASS',certificate=cert)
        except Exception as error:
            result.update(reason=repr(error),traceback=traceback.format_exc(),
                source_global_integrity_block='SVR11_GLOBAL_' in str(error),
                retryable_technical_error=isinstance(error,OSError))
        finally:
            result.update(wall_seconds=time.perf_counter()-start,finished_UTC=now())
            atomic(attempt/'RESULT.json',result);stop.set();thread.join(timeout=2)
            progress(dict(phase='TERMINAL',status=result['status']))
    return result

def initial():return dict(status='RUNNING',dates={d:dict(day=d,status='NOT_EXECUTED',attempts=[]) for d in DAYS})

def peers(ledger):
    return [r['worker'] for r in ledger['dates'].values() if r['status']=='RUNNING' and live(r.get('worker',{}))]

def reconcile(ledger):
    for row in ledger['dates'].values():
        if row['status']!='RUNNING' or live(row.get('worker',{})):continue
        path=Path(row['request']).parent/'RESULT.json'
        if path.exists():
            v=read(path);row.update(status=v['status'],result=record(path),reason=v.get('reason'),
                wall_seconds=v['wall_seconds'],certificate=v.get('certificate'))
            row['retry_pending']=bool(not v['PASS'] and v.get('retryable_technical_error') and not v.get('source_global_integrity_block') and len(row['attempts'])<3)
        else:
            atomic(path,dict(PASS=False,status='FAIL',day=row['day'],source_SHA=ledger['source_SHA'],
                reason='MODEL_ONLY_PROCESS_EXIT_WITHOUT_RESULT',retryable_technical_error=True,
                Native_optimizer_calls=0,Actual_calls=0,Native_Runtime=0,wall_seconds=None,UTC=now()))
            row.update(status='FAIL',result=record(path),reason='MODEL_ONLY_PROCESS_EXIT_WITHOUT_RESULT',retry_pending=len(row['attempts'])<3)

def spawn(root,m,row):
    attempt=root/'model_precompute'/row['day']/f"attempt_{len(row['attempts'])+1:02d}";attempt.mkdir(parents=True,exist_ok=True)
    path=attempt/'request.json';atomic(path,dict(root=str(root),day=row['day'],source_SHA=m['execution_SHA'],
        manifest=record(root/'CAMPAIGN_MANIFEST.json'),model_only=True,Native_optimizer_calls=0,Actual_calls=0,UTC=now()))
    env=os.environ.copy()
    for name in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):env[name]='1'
    with (attempt/'STDOUT.log').open('ab') as log:
        p=subprocess.Popen([sys.executable,'-B','-X','utf8',str(SCRIPT),'worker',str(path)],cwd=SOURCE,
            stdout=log,stderr=subprocess.STDOUT,env=env,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    row.update(status='RUNNING',worker=identity(psutil.Process(p.pid)),request=str(path),retry_pending=False)
    row['attempts'].append(record(path))

def import_dependency_failures(root,m,ledger):
    campaign=read(root/'CAMPAIGN_LEDGER.json');proofs=[]
    for day,row in ledger['dates'].items():
        if row['status']!='FAIL':continue
        for arm in ('B2','B1','B3'):
            current=campaign['dates'][arm+'/'+day]
            if current['status']!='NOT_EXECUTED' or current['attempts']:continue
            dest=root/'dates'/arm/day/'attempts/model_precompute_dependency';dest.mkdir(parents=True,exist_ok=True)
            path=dest/'RESULT.json';v=dict(PASS=False,status='FAIL',reason='DEPENDENCY_FAILED:MODEL_PRECOMPUTE',
                source_SHA=m['execution_SHA'],day=day,arm=arm,Native_Runtime=0,Actual_PQ_repair=0,Actual_reoptimization=0,
                AC_status='NOT_EXECUTED',optimization_status='NOT_EXECUTED',FULL_feasible_certified=False,global_gap_certified=False,
                dependency=row['result'],native_ledgers=[],metrics=dict(environments={}),wall_seconds=0,UTC=now())
            atomic(path,v)
            from v42_svr11.controller import record_terminal
            record_terminal(current,path);current.update(retry_pending=False,dependency_FAILED=True)
            proofs.append(record(path))
    if proofs:atomic(root/'CAMPAIGN_LEDGER.json',campaign)
    return proofs

def coordinator(root):
    root=Path(root).resolve();m,c=contract(root)
    from v42_svr11.resources import snapshot
    path=root/'MODEL_PRECOMPUTE_LEDGER.json'
    with singleton(root/'MODEL_PRECOMPUTE_COORDINATOR.lock'):
        atomic(root/'MODEL_PRECOMPUTE_PROCESS.json',dict(identity(),root=str(root),source_SHA=m['execution_SHA']))
        ledger=read(path) if path.exists() else initial();ledger.update(source_SHA=m['execution_SHA'],max_workers=10)
        while True:
            verify(root/'CAMPAIGN_MANIFEST.json');reconcile(ledger);active=peers(ledger)
            pending=[r for r in ledger['dates'].values() if r['status']=='NOT_EXECUTED']
            pending += [r for r in ledger['dates'].values() if r.get('retry_pending')]
            memory=snapshot()
            while len(active)<10 and pending and admits(memory,active,c):
                row=pending.pop(0);spawn(root,m,row);active=peers(ledger);atomic(path,ledger);memory=snapshot()
            ledger.update(active_workers=active,memory=memory,counts={s:sum(r['status']==s for r in ledger['dates'].values()) for s in ('PASS','FAIL','RUNNING','NOT_EXECUTED')},UTC=now())
            atomic(path,ledger)
            if not active and not pending:
                evidence=[]
                for day,row in ledger['dates'].items():
                    if row['status']=='PASS':evidence.append(check_model(root,m,day))
                failures=import_dependency_failures(root,m,ledger)
                ledger.update(status='COMPLETE',UTC=now());atomic(path,ledger)
                atomic(root/'MODEL_PRECOMPUTE_READY.json',dict(PASS=True,source_SHA=m['execution_SHA'],
                    all31_terminal=True,successful_models=len(evidence),failed_models=len(failures)//3,
                    evidence=evidence,dependency_failures=failures,healthy_model_workers_remaining=0,
                    Native_optimizer_calls=0,Actual_calls=0,UTC=now()))
                from svr11_monitor_ui import safeguard
                safeguard(root);return
            time.sleep(5)

def ensure(root):
    root=Path(root).resolve();m,c=contract(root);ready=root/'MODEL_PRECOMPUTE_READY.json'
    if ready.exists():
        v=read(ready)
        if not (v['PASS'] and v['source_SHA']==m['execution_SHA'] and v['all31_terminal'] and v['healthy_model_workers_remaining']==0):
            raise PermissionError('SVR11_GLOBAL_MODEL_PRECOMPUTE_READY_DRIFT')
        return True
    with singleton(root/'MODEL_PRECOMPUTE_LAUNCH.lock'):
        path=root/'MODEL_PRECOMPUTE_PROCESS.json'
        if path.exists() and live(read(path)):return False
        found=[]
        for p in psutil.process_iter(['pid','name']):
            try:
                args=p.cmdline()
                if str(SCRIPT) in args and 'coordinator' in args and args[-1]==str(root):found.append(p)
            except psutil.Error:continue
        if len(found)>1:raise PermissionError('SVR11_GLOBAL_DUPLICATE_MODEL_PRECOMPUTE_COORDINATOR')
        if found:
            atomic(path,dict(identity(found[0]),root=str(root),source_SHA=m['execution_SHA']));return False
        with (root/'MODEL_PRECOMPUTE_STDOUT.log').open('ab') as log:
            subprocess.Popen([sys.executable,'-B','-X','utf8',str(SCRIPT),'coordinator',str(root)],cwd=SOURCE,
                stdout=log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    return False

if __name__=='__main__':
    if sys.argv[1]=='worker':raise SystemExit(0 if worker(Path(sys.argv[2]))['PASS'] else 1)
    elif sys.argv[1]=='coordinator':coordinator(Path(sys.argv[2]))
    else:raise ValueError(sys.argv[1])

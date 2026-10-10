"""Persistent B0→B2→B1→B3 dispatch. PASS count never gates progress."""
from pathlib import Path
import sys,subprocess,time,traceback
from v42_pr134_b1.common import read,record,atomic,now,sha
from v42_common_campaign.authority import ROOT,VERSION,singleton
from . import DAYS,ORDER
from .authority import verify
from .processes import identity,workers,live

def initial():
    return dict(schema='V42_SVR11_CAMPAIGN_LEDGER_V1',status='RUNNING',policy='B0',dates={a+'/'+d:dict(arm=a,day=d,status='NOT_EXECUTED',attempts=[]) for a in ORDER for d in DAYS})

def next_policy(ledger):
    return next((a for a in ORDER if any(ledger['dates'][a+'/'+d]['status'] not in ('PASS','FAIL') for d in DAYS)),None)

def make_request(root,m,row,slot):
    number=len(row['attempts'])+1;attempt_id=f'attempt_{number:02d}';attempt=root/'dates'/row['arm']/row['day']/'attempts'/attempt_id
    attempt.mkdir(parents=True,exist_ok=True)
    r=dict(root=str(root),campaign_root=str(root),code_root=str(ROOT),run_id=m['run_id'],svr11_campaign=True,
        arm=row['arm'],day=row['day'],worker_slot=slot,attempt_id=attempt_id,manifest=str(root/'CAMPAIGN_MANIFEST.json'),manifest_SHA=sha(root/'CAMPAIGN_MANIFEST.json'),
        source_SHA=m['execution_SHA'],input_folder=str(root/'inputs'/row['arm']/row['day']),output=str(attempt/'output'),
        result=str(attempt/'RESULT.json'),progress=str(attempt/'progress.json'),error=str(attempt/'error.json'),
        source_seal=str(root/'B3_SOURCE_SEAL.json'),started_UTC=now(),Threads=1,P2_calls=0,native_budget_seconds=1800 if row['arm'] in ('B2','B3') else 5400,
        wall_budget_seconds=None,target_gap=.005 if row['arm']=='B1' else .03,algorithm_version=VERSION)
    path=attempt/'request.json';atomic(path,r);return path,r

def record_terminal(row,path):
    r=read(path)
    row.update(status='PASS' if r['PASS'] else 'FAIL',result=str(path),result_SHA=sha(path),reason=r.get('reason',r.get('scientific_status')),
        metrics=r.get('metrics',{}),Native_Runtime=r.get('Native_Runtime'),wall_seconds=r.get('wall_seconds'),
        Planning_objective=r.get('Planning_objective'),FULL_feasible_certified=r.get('FULL_feasible_certified'),global_gap_certified=r.get('global_gap_certified'),
        certified_LB=r.get('certified_LB'),certified_Gap=r.get('certified_Gap'))
    return r

def reconcile(root,m,ledger,active):
    bykey={p['arm']+'/'+p['day']:p for p in active}
    for key,row in ledger['dates'].items():
        if row['status'] in ('PASS','FAIL'):continue
        if key in bykey:
            p=bykey[key];r=read(p['request']);row.update(status='RUNNING',worker=p,request=p['request'])
            if p['request'] not in row['attempts']:row['attempts'].append(p['request'])
            continue
        if row['status']!='RUNNING':continue
        request=read(row['request']);result=Path(request['result'])
        if result.exists():
            r=record_terminal(row,result)
            if r.get('source_global_integrity_block'):raise PermissionError('SVR11_GLOBAL_WORKER_INTEGRITY_FAILURE:'+r.get('reason',''))
            if r.get('retryable_pre_native_technical_error') and not r.get('Native_Runtime') and not any(l.get('inflight') for l in r.get('native_ledgers',[])) and len(row['attempts'])<3:
                row.update(status='NOT_EXECUTED',recovery='Bounded pre-Native file-sharing retry; terminal evidence preserved')
            continue
        # Only a pre-Native technical process failure is restartable, twice.
        attempt=result.parent;ledgers=list(attempt.rglob('NATIVE_RUNTIME_LEDGER.json'))
        native_started=any(read(p).get('calls') or read(p).get('inflight') for p in ledgers)
        failure=dict(PASS=False,status='FAIL',reason='WORKER_PROCESS_EXITED_WITHOUT_RESULT',arm=row['arm'],day=row['day'],
            unknown_inflight_runtime=native_started,ledger_receipts=[record(p) for p in ledgers],UTC=now())
        atomic(attempt/'PROCESS_EXIT_FAILURE.json',failure)
        if not native_started and len(row['attempts'])<3:
            row.update(status='NOT_EXECUTED',recovery='Bounded pre-Native retry; previous evidence retained')
        else:
            atomic(result,failure);record_terminal(row,result)

def run(root):
    root=Path(root).resolve();m=verify(root/'CAMPAIGN_MANIFEST.json')
    with singleton(root/'SUPERVISOR.lock'):
        atomic(root/'SUPERVISOR_PROCESS.json',dict(identity(),root=str(root),source_SHA=m['execution_SHA']))
        ledger=read(root/'CAMPAIGN_LEDGER.json') if (root/'CAMPAIGN_LEDGER.json').exists() else initial()
        last_report=0.;last_policy=None
        while True:
            try:
                verify(root/'CAMPAIGN_MANIFEST.json');active=workers(root,m['execution_SHA']);reconcile(root,m,ledger,active)
                policy=next_policy(ledger);ledger.update(policy=policy,UTC=now(),source_SHA=m['execution_SHA'],active_workers=active,supervisor=identity())
                if policy is None:
                    ledger['status']='COMPLETE';atomic(root/'CAMPAIGN_LEDGER.json',ledger)
                    from .report import generate
                    generate(root,ledger);atomic(root/'CAMPAIGN_COMPLETION.json',dict(attempted=124,all_dates_terminal=True,source_SHA=m['execution_SHA'],UTC=now()))
                    return
                if any(p['arm']!=policy for p in active):raise PermissionError('SVR11_GLOBAL_POLICY_ORDER_CONFLICT')
                if last_policy and last_policy!=policy:
                    atomic(root/'LATEST_POLICY_TRANSITION.json',dict(previous=last_policy,current=policy,PASS_is_not_gate=True,UTC=now()))
                last_policy=policy;slots={p['worker_slot'] for p in active};capacity=m['worker_counts'][policy]
                for day in DAYS:
                    row=ledger['dates'][policy+'/'+day]
                    if row['status']!='NOT_EXECUTED' or len(active)>=capacity:continue
                    slot=next(n for n in range(1,capacity+1) if n not in slots);path,r=make_request(root,m,row,slot)
                    # Persist dispatch first. OS lifetime lock prevents duplicate
                    # workers if a supervisor dies in the Popen receipt window.
                    row.update(status='RUNNING',request=str(path));row['attempts'].append(str(path));atomic(root/'CAMPAIGN_LEDGER.json',ledger)
                    with (path.parent/'WORKER_STDOUT.log').open('ab') as log:
                        p=subprocess.Popen([sys.executable,'-B','-X','utf8','-m','v42_svr11.worker',str(path)],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,
                            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                    import psutil
                    peer=dict(identity(psutil.Process(p.pid)),arm=policy,day=day,worker_slot=slot,request=str(path));active.append(peer);slots.add(slot);row['worker']=peer
                ledger.update(active_workers=active,status='RUNNING');atomic(root/'CAMPAIGN_LEDGER.json',ledger)
                atomic(root/'SUPERVISOR_HEARTBEAT.json',dict(identity(),policy=policy,source_SHA=m['execution_SHA'],UTC=now()))
                if time.monotonic()-last_report>60:
                    from .report import generate
                    generate(root,ledger);last_report=time.monotonic()
                time.sleep(5)
            except Exception as error:
                ledger.update(status='GLOBAL_SYSTEM_ERROR',error=repr(error),UTC=now());atomic(root/'CAMPAIGN_LEDGER.json',ledger)
                atomic(root/'GLOBAL_SYSTEM_ERROR.json',dict(error=repr(error),traceback=traceback.format_exc(),UTC=now(),healthy_workers_not_terminated=True))
                raise

if __name__=='__main__':run(sys.argv[1])

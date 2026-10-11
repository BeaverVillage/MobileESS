"""Persistent B3 M1(all days) -> RAM/commit barrier -> A2 -> barrier -> M2 -> Actual."""
from pathlib import Path
import sys,subprocess
from v42_pr134_b1.common import atomic,read,record,sha,now
from v42_common_campaign.authority import ROOT
from v42_common_campaign.authority import VERSION
from . import DAYS
from .processes import live,identity
from . import resources

ORDER=('M1','A2','M2','ACTUAL')
CAP={'M1':3,'A2':1,'M2':3,'ACTUAL':1}
TERMINAL=('PASS','FAIL','DEPENDENCY_FAILED')

def initial():
    return dict(schema='SVR11_B3_STAGEWISE_BATCH_V1',stage='M1',status='RUNNING',barriers=[],
        stages={s:{d:dict(day=d,stage=s,status='NOT_EXECUTED',attempts=[]) for d in DAYS} for s in ORDER})

def next_stage(state,active,memory):
    current=state['stage'];rows=state['stages'][current]
    if any(r['status'] not in TERMINAL or r.get('retry_pending') for r in rows.values()):return current
    if active:return current
    before=state.get('last_active_memory',state.get('stage_entry_memory',memory))
    if not resources.returned(before,memory):
        state['status']='WAITING_MEMORY_RETURN';return current
    if not any(b['stage']==current for b in state['barriers']):
        state['barriers'].append(dict(stage=current,all31_terminal=True,worker_processes_exited=True,
            before=before,after=memory,observed_RAM_return_bytes=memory['RAM_available']-before['RAM_available'],
            observed_Commit_return_bytes=before['Commit_total']-memory['Commit_total'],UTC=now()))
    if current=='ACTUAL':state['status']='COMPLETE';return None
    state.update(stage=ORDER[ORDER.index(current)+1],status='RUNNING',stage_entry_memory=memory)
    state.pop('last_active_memory',None)
    return state['stage']

def dependencies(state,stage):
    if stage=='M1':return
    previous=ORDER[ORDER.index(stage)-1]
    for day,row in state['stages'][stage].items():
        if row['status']=='NOT_EXECUTED' and state['stages'][previous][day]['status']!='PASS':
            row.update(status='DEPENDENCY_FAILED',reason=previous+' has no independently verified FULL feasible result',UTC=now())

def make_request(root,m,row,slot):
    stage,day=row['stage'],row['day'];number=len(row['attempts'])+1
    attempt_id=f'{stage}_attempt_{number:02d}'
    attempt=root/'dates/B3'/day/'attempts'/attempt_id;attempt.mkdir(parents=True,exist_ok=True)
    parent=root/'dates/B3'/day/'BATCH'
    previous=row.get('pipeline')
    if previous is None and stage!='M1':
        state=read(root/'B3_BATCH_LEDGER.json')
        previous=state['stages'][ORDER[ORDER.index(stage)-1]][day].get('pipeline')
    pipeline=parent/f'PIPELINE_{stage}_{number:02d}' if number>1 else Path(previous) if previous else parent/'PIPELINE'
    r=dict(root=str(root),campaign_root=str(root),code_root=str(ROOT),run_id=m['run_id'],svr11_campaign=True,
        arm='B3',day=day,b3_stage=stage,b3_pipeline=str(pipeline),
        verified_prefix_root=str(previous) if number>1 and previous else None,
        worker_slot=slot,attempt_id=attempt_id,manifest=str(root/'CAMPAIGN_MANIFEST.json'),manifest_SHA=sha(root/'CAMPAIGN_MANIFEST.json'),
        source_SHA=m['execution_SHA'],input_folder=str(root/'inputs/B3'/day),output=str(attempt/'output'),
        result=str(attempt/'RESULT.json'),progress=str(attempt/'progress.json'),error=str(attempt/'error.json'),
        source_seal=str(root/'B3_SOURCE_SEAL.json'),retry_starts_from_native_zero=True,previous_attempts=list(row['attempts']),
        Threads=1,P2_calls=0,native_budget_seconds=5400 if stage=='A2' else 0 if stage=='ACTUAL' else 1800,
        wall_budget_seconds=None,started_UTC=now(),target_gap=.005 if stage=='A2' else .03,
        algorithm_version=VERSION)
    row['pipeline']=str(pipeline)
    path=attempt/'request.json';atomic(path,r);return path,r

def reconcile(state,active):
    byday={p['day']:p for p in active}
    stage=state['stage']
    if any(p.get('b3_stage')!=stage or p['arm']!='B3' for p in active):raise PermissionError('SVR11_GLOBAL_B3_STAGE_OVERLAP')
    for day,row in state['stages'][stage].items():
        if row['status']!='RUNNING' or day in byday:continue
        r=read(row['request']);path=Path(r['result'])
        if not path.exists():
            atomic(path,dict(PASS=False,status='FAIL',reason='B3_STAGE_WORKER_EXITED_WITHOUT_RESULT',
                stage=stage,day=day,source_SHA=r['source_SHA'],unknown_runtime_preserved=True,retryable_technical_error=True))
        result=read(path)
        if result.get('source_global_integrity_block'):raise PermissionError('SVR11_GLOBAL_B3_STAGE_SOURCE_FAILURE:'+result['reason'])
        row.update(status='PASS' if result['PASS'] else 'FAIL',result=str(path),result_SHA=sha(path),
            reason=result.get('reason'),Native_Runtime=result.get('Native_Runtime'),UTC=now())
        row.setdefault('terminal_history',[]).append(dict(result=record(path),status=row['status'],reason=row['reason']))
        if not result['PASS'] and result.get('retryable_technical_error') and len(row['attempts'])<3:
            i=DAYS.index(day)
            row.update(retry_pending=True,retry_after=DAYS[i+1] if i+1<len(DAYS) else None)

def dispatch_rows(state,stage):
    rows=state['stages'][stage]
    retries=[r for r in rows.values() if r.get('retry_pending') and r['status']=='FAIL'
        and (r.get('retry_after') is None or rows[r['retry_after']]['attempts'])]
    return retries[:1]+[r for r in rows.values() if r['status']=='NOT_EXECUTED']

def publish_dates(ledger,state):
    from .controller import record_terminal
    for day in DAYS:
        date=ledger['dates']['B3/'+day]
        actual=state['stages']['ACTUAL'][day]
        if actual['status']=='PASS' or actual['status']=='FAIL':
            if date['status'] not in ('PASS','FAIL'):record_terminal(date,actual['result'])
        elif actual['status']=='DEPENDENCY_FAILED':
            failures=[state['stages'][s][day] for s in ORDER if state['stages'][s][day]['status']=='FAIL']
            date.update(status='FAIL',reason='DEPENDENCY_FAILED',failed_stages=failures,AC_status='NOT_EXECUTED',
                FULL_feasible_certified=False,global_gap_certified=False)

def tick(root,m,ledger,active,*,memory=None,spawn=None):
    root=Path(root);state=ledger.setdefault('B3_batch',initial());memory=memory or resources.snapshot()
    reconcile(state,active)
    if active:state['last_active_memory']=memory
    stage=next_stage(state,active,memory)
    if state['stage']=='ACTUAL':publish_dates(ledger,state)
    state['memory']=memory
    if stage is None:
        publish_dates(ledger,state);atomic(root/'B3_BATCH_LEDGER.json',state);return active
    dependencies(state,stage);capacity=CAP[stage]
    if len(active)>capacity:raise PermissionError('SVR11_GLOBAL_B3_BATCH_CAPACITY')
    slots={p['worker_slot'] for p in active}
    atomic(root/'B3_BATCH_LEDGER.json',state)
    for row in dispatch_rows(state,stage):
        day=row['day']
        if len(active)>=capacity:continue
        if not resources.admits(memory,active,stage,m['B3_memory_admission']):
            state['status']='WAITING_MEMORY_ADMISSION';break
        slot=next(n for n in range(1,capacity+1) if n not in slots)
        path,r=make_request(root,m,row,slot);row.pop('retry_pending',None)
        row.update(status='RUNNING',request=str(path));row['attempts'].append(str(path))
        date=ledger['dates']['B3/'+day];date.update(status='RUNNING',request=str(path));date['attempts'].append(str(path))
        atomic(root/'CAMPAIGN_LEDGER.json',ledger);atomic(root/'B3_BATCH_LEDGER.json',state)
        if spawn:peer=spawn(path,r)
        else:
            with (path.parent/'WORKER_STDOUT.log').open('ab') as log:
                p=subprocess.Popen([sys.executable,'-B','-X','utf8','-m','v42_svr11.worker',str(path)],cwd=ROOT,
                    stdout=log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            import psutil
            peer=dict(identity(psutil.Process(p.pid)),arm='B3',day=day,b3_stage=stage,worker_slot=slot,request=str(path))
        active.append(peer);slots.add(slot);row['worker']=peer;date['worker']=peer
        memory=resources.snapshot() if spawn is None else memory
    state['active_workers']=active;state['completed_dates_in_stage']=sum(r['status'] in TERMINAL for r in state['stages'][stage].values())
    atomic(root/'B3_BATCH_LEDGER.json',state)
    return active

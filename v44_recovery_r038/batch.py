"""One preparation process at a time, followed by an all-ready Actual wave."""
from pathlib import Path
from contextlib import ExitStack
import os,sys,subprocess,time,traceback
from v44.common import read,record,verify,atomic,digest,now,DOC
from v44.locks import coordinator,alive
from . import operations as op

def all_prepared(jobs):return bool(jobs) and all(j['status']=='PREPARED' for j in jobs)

def publish(state):
    state['UTC']=now();atomic(op.STATE,state)

def write_status(state,running):
    statuses=op.states(op.CAMPAIGN)
    atomic(op.CAMPAIGN/'CAMPAIGN_STATUS.json',dict(UTC=now(),r038_phase=state['phase'],
        cases=[dict(day=d,arm=a,status=s) for (d,a),s in statuses.items()],
        workers=[dict(pid=p.pid,day=j['day'],arm=j['arm'],worker_slot=j.get('parallel_slot',1)) for p,j in running]))

def compose_request(job,lease):
    from v44.config import axis
    freeze=read(DOC/'SCIENTIFIC_FREEZE_MANIFEST.json');data=read(DOC/'SEVEN_DAY_INPUT_MANIFEST.json')
    rows=[r['V44'] for r in freeze['unchanged_source_rows']+freeze['unchanged_support_inputs']]+[
        r['source'] for r in freeze['inherited_external_M_algorithms']]+freeze['adapters']+freeze.get('physics_receipts',[])
    dated=next(r for r in data['days'] if r['day']==job['day']);rows+=list(dated['files'].values())
    parent=op.latest(op.CAMPAIGN,job['day'],job['arm']);number=int(parent.name[-3:])+1 if parent else 1
    root=op.CAMPAIGN/job['day']/job['arm']/f'attempt{number:03d}'
    if parent and (parent/'RESULT.json').exists() and read(parent/'RESULT.json').get('PASS'):raise PermissionError('R038_CANNOT_RERUN_COMPLETED_PASS')
    case=op.decorate(dict(day=job['day'],arm=job['arm'],worker_slot=1,lane='MAIN',case_root=str(root),
        campaign_root=str(op.CAMPAIGN),lease=lease,sources=rows,scientific_source_sha=freeze['source_sha'],
        axis=axis(job['day']),execution_permit=record(op.PERMIT),r038_phase='PREPARE_SERIAL'))
    if parent and job['arm']=='B1' and (parent/'A1/RESULT.json').exists():
        if read(parent/'A1/RESULT.json').get('error')=="ValueError('NEGATIVE_ANONYMOUS_GPU')":case['planning_repair_parent']=str(parent/'A1')
    verify(case['sources']);op.authorize(case)
    target=op.OPS/'requests'/f"{job['day']}_{job['arm']}_attempt{number:03d}.json"
    return case,target,number

def new_request(job,lease):
    case,target,number=compose_request(job,lease);root=Path(case['case_root'])
    atomic(target,case);job.update(case_root=str(root),prepare_request=str(target),status='PREPARING')
    pointer=op.CAMPAIGN/'requests'/f"{job['day']}_{job['arm']}.json"
    if pointer.exists():atomic(op.OPS/'request_history'/f"{pointer.stem}_before_r038_attempt{number:03d}.json",read(pointer))
    atomic(pointer,case);return target

def launch(pointer,label):
    env=dict(os.environ,PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',NUMEXPR_NUM_THREADS='1')
    logs=op.OPS/'launcher_logs';logs.mkdir(exist_ok=True)
    with (logs/(pointer.stem+'.'+label+'.out.log')).open('ab') as out,(logs/(pointer.stem+'.'+label+'.err.log')).open('ab') as err:
        return subprocess.Popen([sys.executable,'-u','-m',op.ENTRY,'--worker',str(pointer),'--algorithm',op.ALGORITHM],
            cwd=Path(__file__).resolve().parents[1],env=env,stdout=out,stderr=err,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))

def finish(process,job,expected):
    root=Path(job['case_root']);p=root/'RESULT.json'
    if not p.exists():atomic(p,dict(day=job['day'],arm=job['arm'],PASS=False,status='FAILED',error='R038_WORKER_EXIT_WITHOUT_RESULT',exit_code=process.returncode,finished_UTC=now()))
    result=read(p)
    if expected=='PREPARED':
        valid=(process.returncode==0 and result.get('status')=='PRE_ACTUAL_READY' and result.get('preparation_PASS') is True)
        if valid:
            verify([result['pre_actual_handoff']]);job['handoff']=result['pre_actual_handoff']
            atomic(root/'PRE_ACTUAL_RESULT.json',result)
        job['status']='PREPARED' if valid else 'PRE_FAILED'
    else:
        if result.get('status')=='PRE_ACTUAL_READY':
            result=dict(day=job['day'],arm=job['arm'],PASS=False,status='FAILED',
                error='R038_ACTUAL_WORKER_EXITED_BEFORE_FINAL_RESULT',exit_code=process.returncode,
                original_preparation=record(root/'PRE_ACTUAL_RESULT.json'),finished_UTC=now())
            atomic(p,result)
        job['status']='PASS' if process.returncode==0 and result.get('PASS') else 'ACTUAL_FAILED'
    job['result']=record(p);job['process_exit']=process.returncode
    atomic(root/('PREPARE_PROCESS_EXIT.json' if expected=='PREPARED' else 'ACTUAL_PROCESS_EXIT.json'),dict(UTC=now(),exit_code=process.returncode))
    if job['status'] in ('PRE_FAILED','ACTUAL_FAILED'):
        from v44_recovery_r029.failure_continue import defer
        defer(op.OPS,root,result)

def background_to_E():
    # This maintenance helper does no science; keep its IO/CPU off Actual P cores.
    import psutil
    from v44_recovery_r029.cpu_placement import windows_cpu_sets
    p=op.OPS/'R036_STORAGE_MAINTENANCE_LEASE.json'
    if not p.exists() or not alive(read(p)):return
    rows=windows_cpu_sets();highest=max(r['efficiency_class'] for r in rows)
    efficiency=[r['logical'] for r in rows if r['efficiency_class']<highest]
    if efficiency:psutil.Process(read(p)['pid']).cpu_affinity([min(efficiency)])

def run():
    auth=op.authority();verify([read(auth['boundary_request']['path'])['protected_request']])
    queue=read(auth['queue_plan']['path'])
    state=read(op.STATE) if op.STATE.exists() else dict(schema='V44_R038_BATCH_STATE_V1',phase='PREPARE_SERIAL',
        authorization=record(op.AMENDMENT),jobs=[dict(j,status='PENDING') for j in queue['jobs']])
    if state['authorization']!=record(op.AMENDMENT):raise PermissionError('R038_BATCH_AUTHORITY_CHANGED')
    if [(j['day'],j['arm']) for j in state['jobs']]!=[(j['day'],j['arm']) for j in queue['jobs']]:
        raise PermissionError('R038_FIXED_BATCH_MEMBERSHIP_CHANGED')
    if any(j['status'] in ('PREPARING','ACTUAL_RUNNING') for j in state['jobs']):
        state['phase']='INTERRUPTED_REQUIRES_DIAGNOSIS';publish(state);return
    with coordinator(op.CAMPAIGN) as lease:
        h=read(op.OPS/'CURRENT_HANDOFF.json');h.update(UTC=now(),active_revision='v44_recovery_r038',
            active_operational_entry=op.ENTRY,active_operational_permit=record(op.AMENDMENT),active_lease=lease,
            pending_revision=None,pending_permit=None,pending_validation=None,user_dispatch_pause=False,dispatch_hold_reason=None,
            collector=str(op.OPS/'collect_watchdog_r038.py'),active_source_auditor=str(op.OPS/'audit_active_revision_r038.py'),
            entry=f'python -m {op.ENTRY} --watchdog --algorithm {op.ALGORITHM}',
            latest_user_instruction=auth['user_instruction'],next='Complete all seven preparations with one worker, then seven independent P-only Actual/Fresh workers.')
        atomic(op.OPS/'CURRENT_HANDOFF.json',h);publish(state)
        for job in state['jobs']:
            if (op.OPS/'STOP_AUTONOMY.json').exists():return
            if job['status']!='PENDING':continue
            atomic(op.CAMPAIGN/'PHASE.json',dict(UTC=now(),lane='MAIN',r038_phase='PREPARE_SERIAL'))
            try:
                pointer=new_request(job,lease);publish(state);proc=launch(pointer,'prepare')
                while proc.poll() is None:write_status(state,[(proc,job)]);time.sleep(5)
                finish(proc,job,'PREPARED')
            except Exception as error:
                job.update(status='PRE_FAILED',dispatch_error=repr(error),traceback=traceback.format_exc())
            publish(state);write_status(state,[])
        if not all_prepared(state['jobs']):
            state['phase']='PREPARATION_FAILED';publish(state);return
        if (op.OPS/'STOP_AUTONOMY.json').exists():return
        from .cpu import reserve_pool
        with reserve_pool(auth['cpu_placement'],op.OPS,lease):
            # Persist/flush the complete barrier before the first process is launched.
            for job in state['jobs']:verify([job['handoff']])
            atomic(op.OPS/'R038_ALL_PRE_ACTUAL_READY.json',dict(UTC=now(),PASS=True,authorization=record(op.AMENDMENT),
                lease=lease,handoffs=[j['handoff'] for j in state['jobs']],prepared_jobs=len(state['jobs']),Actual_started_before_barrier=False))
            state['phase']='ACTUAL_PARALLEL';publish(state)
            atomic(op.CAMPAIGN/'PHASE.json',dict(UTC=now(),lane='ACTUAL_PARALLEL',max_workers=7))
            background_to_E();running=[]
            for slot,job in enumerate(state['jobs'],1):
                if (op.OPS/'STOP_AUTONOMY.json').exists():break
                case=read(job['prepare_request']);case.update(lease=lease,r038_phase='ACTUAL_PARALLEL',parallel_actual_slot=slot,
                    R038_pre_actual_handoff=job['handoff'],R038_all_prepared=record(op.OPS/'R038_ALL_PRE_ACTUAL_READY.json'))
                pointer=Path(job['prepare_request']).with_name(Path(job['prepare_request']).stem+'_ACTUAL.json')
                atomic(pointer,case);job.update(actual_request=str(pointer),parallel_slot=slot,status='ACTUAL_RUNNING')
                proc=launch(pointer,'actual');running.append((proc,job));publish(state)
            while running:
                for proc,job in running[:]:
                    if proc.poll() is not None:finish(proc,job,'ACTUAL');running.remove((proc,job));publish(state)
                write_status(state,running);background_to_E();time.sleep(5)
            state['phase']='COMPLETE' if all(j['status'] in ('PASS','ACTUAL_FAILED') for j in state['jobs']) else 'INTERRUPTED_REQUIRES_DIAGNOSIS'
            state['all_PASS']=all(j['status']=='PASS' for j in state['jobs']);publish(state);write_status(state,[])

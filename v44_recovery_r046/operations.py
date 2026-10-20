"""Current Actual drains, three failed Planning cases recover, seven ready cases run."""
from pathlib import Path
from contextlib import contextmanager
from types import FunctionType
from unittest.mock import patch
import argparse,os,sys,time,subprocess,inspect,textwrap,traceback
import v44_week2_restart_r045a as previous
from v44_recovery_r045 import operations as core
from v44_recovery_r044 import operations as old_repair
from v44.common import read,record,verify,atomic,digest,now
from v44.locks import alive,coordinator,exclusive_lock,process_identity

CAMPAIGN,OPS,STATE=core.CAMPAIGN,core.OPS,core.STATE
PARENT=CAMPAIGN/'2025-05-12/B3/attempt002'
AUTH=OPS/'R046_ACTUAL_PLANNING_ACTUAL_AUTHORIZATION.json'
VALIDATION=OPS/'R046_VALIDATION.json'
DRAIN=OPS/'R046_USER_ACTUAL_DRAIN_REQUEST.json'
REASON='R046_DRAIN_CURRENT_ACTUAL_THEN_REPAIR_PLANNING'
ENTRY='v44_recovery_r046.operations'
REPAIRS=(('2025-05-11','B1'),('2025-05-11','B3'),('2025-05-12','B3'))
_week_authority=core._original_authority
_worker=core.worker
_barrier=core.seq.validate_main_barrier
_actual=core.actual_main


def sources():return [record(p) for p in sorted(Path(__file__).parent.glob('*.py'))]


def helpers():return old_repair.sources()+core.sources()+[record(previous.__file__)]


def authority():
    core.seq.authority();v=read(AUTH)
    verify(v['sources']+v['helper_sources']+[v['previous_authorization'],v['validation'],v['user_request'],v['diagnosis']])
    if (v['sources']!=sources() or v['helper_sources']!=helpers() or v['previous_authorization']!=record(previous.AUTH)
        or not read(v['validation']['path'])['PASS'] or v['repairs']!=[list(k) for k in REPAIRS]
        or (v['prepare_workers'],v['actual_workers'],v['baseline_workers'])!=(1,7,1)):
        raise PermissionError('R046_SEALED_DRAIN_REPAIR_WAVE_REQUIRED')
    return v


def request_authority(r=None):
    if r is None:return _week_authority()
    v=authority();p=next((p for p in v['plan'] if core.seq.key(p)==core.seq.key(r)),None)
    if (not p or Path(r['case_root'])!=Path(p['case_root']) or r.get('R046_authorization')!=record(AUTH)
        or r.get('sequence_authorization')!=record(core.seq.AUTH)):
        raise PermissionError('R046_EXACT_NEW_OR_PRESERVED_CASE_REQUIRED')
    return _week_authority(dict(r,case_root=str(CAMPAIGN/r['day']/r['arm']/'attempt001')))


def validate_parent():
    from v44.checkpoints import assert_dead,checked,ledger_state
    from v44.stages import require_m1
    assert_dead(PARENT);old=read(PARENT/'M1/request.json')
    checked(PARENT/'M1/COMPLETED_STAGE_CHECKPOINT.json',old,'COMPLETED')
    m1=read(PARENT/'M1/RESULT.json');require_m1(m1,'2025-05-12')
    if 'A_CERTIFIED_LB_UB_CONFLICT' not in read(PARENT/'A2/RESULT.json').get('error',''):
        raise PermissionError('R046_ONLY_DIAGNOSED_MAY12_BOUND_CONFLICT')
    account=ledger_state(PARENT/'A2/NATIVE_RUNTIME_LEDGER.json',ceiling=5400.)
    if abs(account['measured']-15.969001770019531)>1e-7:raise PermissionError('R046_A2_INHERITED_ACCOUNT_DRIFT')
    ledger_state(PARENT/'M1/K48_NATIVE_LEDGER.json',ceiling=300.)
    ledger_state(PARENT/'M1/JOINT_NATIVE_LEDGER.json',ceiling=900.)
    return old,m1,account


def worker(path,entry_check=False):
    r=read(path)
    if entry_check:return _worker(path,True)
    if core.seq.key(r)==('2025-05-11','B1') and r['r038_phase']=='PREPARE_SERIAL':
        from .planning import a1_scope
        with a1_scope(CAMPAIGN/'2025-05-11/B1/attempt002/A1'):return _worker(path)
    if core.seq.key(r)!=('2025-05-12','B3') or r['r038_phase']!='PREPARE_SERIAL':return _worker(path)
    from v44_recovery_r045.admission import boundary
    from v44_recovery_r045.reference import project
    from v43_arms import reference
    from v44_recovery_r029 import handover,conditional_campaign
    from v44_recovery_r038 import operations as inherited
    from v44_recovery_r039 import latency
    from v44_recovery_r041.preparation import deny_actual
    from v44.execution import assert_current
    from v44 import worker as science
    request_authority(r);boundary(r)
    continued=FunctionType(old_repair.repaired_case.__code__,dict(old_repair.repaired_case.__globals__,
        __package__=__package__,PARENT=PARENT,PERMIT=AUTH,authority=authority,
        request_authority=request_authority,validate_parent=validate_parent),old_repair.repaired_case.__name__)
    with patch.object(handover,'require_boundary',lambda:boundary(r)),patch.object(reference,'project',project),inherited.previous.install(),latency.install(lambda:request_authority(assert_current()['request'])),patch.object(conditional_campaign,'run_case',continued),patch.object(science,'actual',deny_actual):
        return inherited.base.worker(r)


def new_request(job,lease,mode):
    p=next(p for p in authority()['plan'] if core.seq.key(p)==core.seq.key(job));r=read(p['original_request'])
    r.update(case_root=p['case_root'],lease=lease,sequence_mode=mode,sequence_authorization=record(core.seq.AUTH),
        R045_authorization=record(core.PERMIT),R046_authorization=record(AUTH),
        r038_phase='PREPARE_SERIAL' if mode=='MAIN' else 'BASELINE_SEQUENTIAL')
    r['sources']=list({x['path']:x for x in r['sources']+sources()+[record(AUTH)]}.values());r['source_sha']=digest(r['sources'])
    request_authority(r);path=OPS/'requests'/f"{r['day']}_{r['arm']}_R046.json";atomic(path,r)
    job.update(case_root=r['case_root'],prepare_request=str(path),status='PREPARING' if mode=='MAIN' else 'BASELINE_RUNNING')
    return path


def validate_barrier(value):
    completed=value.get('completed',[])
    if not completed:return _barrier(value)
    rows=value.get('ready',[])+value.get('excluded',[])+completed;keys=[core.seq.key(j) for j in rows]
    if len(keys)!=14 or len(set(keys))!=14 or set(keys)!=set(core.seq.MAIN):raise PermissionError('R046_ALL_MAIN_READY_COMPLETED_OR_EXCLUDED_REQUIRED')
    if not value.get('all_preparations_resolved') or value.get('Actual_started_before_barrier') is not False:
        raise PermissionError('R046_REPAIRED_PREPARATION_BARRIER_REQUIRED')
    for j in completed:
        verify([j['result']]);r=read(j['result']['path'])
        if (j['status'] not in ('PASS','ACTUAL_FAILED') or (r.get('PASS') is True)!=(j['status']=='PASS')
            or (r.get('day'),r.get('arm'))!=core.seq.key(j) or not r.get('finished_UTC')
            or Path(j['result']['path'])!=Path(j['case_root'])/'RESULT.json'):
            raise PermissionError('R046_PRESERVED_ACTUAL_TERMINAL_EVIDENCE_REQUIRED')
    if any(not j.get('handoff') for j in value['ready']) or any(not j.get('exclusion_reason') for j in value['excluded']):
        raise PermissionError('R046_READY_HANDOFF_AND_FAILED_REASON_REQUIRED')
    count=min(7,len(value['ready']));plan=value.get('cpu_placement')
    if (count and (not plan or len(plan['slots'])!=count)) or (not count and plan is not None):
        raise PermissionError('R046_SEVEN_WORKER_POOL_REQUIRED')
    return value


def actual_function():
    source=textwrap.dedent(inspect.getsource(_actual))
    old="R045_authorization=record(PERMIT),ready=ready,excluded=[j for j in main if j['status']=='EXCLUDED'],"
    new=old+"completed=[j for j in main if j['status'] in ('PASS','ACTUAL_FAILED')],"
    if source.count(old)!=1:raise ValueError('R046_ACTUAL_BARRIER_COMPLETED_MEMBERSHIP_BOUNDARY_DRIFT')
    ns=dict(_actual.__globals__);exec(compile(source.replace(old,new),__file__+'.actual.generated','exec'),ns)
    fn=ns['actual_main'];return FunctionType(fn.__code__,core.__dict__,fn.__name__,fn.__defaults__,fn.__closure__)


def adopt(lease):
    from v44_recovery_r038.phases import load_handoff
    state=read(STATE)
    if alive(state.get('lease')) or core.seq.STOP.exists():raise PermissionError('R046_OLD_OWNER_OR_USER_STOP_PRESERVED')
    atomic(OPS/'R046_STATE_BEFORE_REPAIR.json',state)
    for j in state['jobs']:
        if core.seq.key(j) in REPAIRS:
            root=Path(j['case_root']);p=next(p for p in authority()['plan'] if core.seq.key(p)==core.seq.key(j))
            if (root/'ACTUAL').exists() or Path(p['case_root']).exists():raise PermissionError('R046_NEW_PLANNING_ATTEMPT_REQUIRED')
            for field in ('result','process_exit','exclusion_reason','traceback','handoff','actual_request','parallel_slot'):j.pop(field,None)
            j.update(status='PENDING',case_root=p['case_root']);continue
        if j['status'] in ('PASS','ACTUAL_FAILED'):continue
        if j['status']=='BASELINE_QUEUED':continue
        if j['status']!='PREPARED':raise PermissionError('R046_CURRENT_ACTUAL_MUST_FINISH_BEFORE_PLANNING')
        r=read(j['prepare_request']);r.update(lease=lease,R046_authorization=record(AUTH),R045_authorization=record(core.PERMIT),
            sequence_mode='MAIN',sequence_authorization=record(core.seq.AUTH),r038_phase='PREPARE_SERIAL',R038_pre_actual_handoff=j['handoff'])
        request_authority(r);load_handoff(r)
        path=OPS/'requests'/f"{j['day']}_{j['arm']}_R046_ADOPTED.json";atomic(path,r);j['prepare_request']=str(path)
    state.update(lease=lease,phase='MAIN_PREPARE_SERIAL',all_PASS=False,R046_authorization=record(AUTH));return state


def run():
    authority()
    with exclusive_lock(OPS/'R046_CONTROLLER.lock'),coordinator(CAMPAIGN) as lease:
        state=None
        try:
            state=adopt(lease);pointer=Path('D:/MobileESS_V44/runtime/ACTIVE_CAMPAIGN.json');v=read(pointer)
            v.update(UTC=now(),coordinator=lease,status='RUNNING',operational_entry=ENTRY,operational_recovery=record(AUTH));atomic(pointer,v)
            core.publish(state)
            if not core.prepare_main(state,lease):return
            core.actual_main(state,lease)
            if core.seq.STOP.exists():state['phase']='USER_STOPPED';core.publish(state);return
            core.baseline_serial(state,lease)
            if core.seq.STOP.exists():state['phase']='USER_STOPPED';core.publish(state);return
            if not all(j['status'] in core.seq.MAIN_TERMINAL for j in state['jobs']):raise PermissionError('R046_UNRESOLVED_CASES_CANNOT_COMPLETE')
            state.update(phase='COMPLETE',all_PASS=all(j['status']=='PASS' for j in state['jobs']));core.publish(state)
            atomic(OPS/'FINAL_RESULT.json',dict(UTC=now(),phase='COMPLETE',PASS=state['all_PASS'],jobs=state['jobs'],authorization=record(AUTH)))
        except BaseException as error:
            if state is not None:state.update(phase='INFRASTRUCTURE_BLOCKED',all_PASS=False);core.publish(state)
            atomic(OPS/'R046_CONTROLLER_ERROR.json',dict(UTC=now(),error=repr(error),traceback=traceback.format_exc()));raise


def transition():
    authority()
    with exclusive_lock(OPS/'R046_TRANSITION.lock'):
        while True:
            stop=read(core.seq.STOP) if core.seq.STOP.exists() else {}
            if stop.get('reason')!=REASON or stop.get('authorization')!=record(DRAIN):
                atomic(OPS/'R046_NEW_USER_STOP_PRESERVED.json',dict(UTC=now(),stop=stop));return
            state=read(STATE);active=[]
            for j in state['jobs']:
                root=Path(j['case_root'])
                for name in ('START.json','ACTUAL_START.json'):
                    p=root/name
                    if p.exists() and alive(read(p)):active.append(read(p)['pid'])
            atomic(OPS/'R046_TRANSITION_HEARTBEAT.json',dict(UTC=now(),**process_identity(),
                old_coordinator_alive=alive(state.get('lease')),active_workers=active,
                next='Repair May11 B1/B3 and May12 B3 Planning serially, then ready Actual up to seven workers.'))
            if not alive(state.get('lease')) and not active:break
            time.sleep(5)
        atomic(OPS/'R046_DRAINED_STATE.json',state);atomic(OPS/'R046_DRAIN_STOP_PRESERVED.json',stop);core.seq.STOP.unlink()
        env=dict(os.environ,PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',NUMEXPR_NUM_THREADS='1')
        with (OPS/'r046_controller.log').open('ab') as stream:
            p=subprocess.Popen([sys.executable,'-X','utf8','-u','-m',ENTRY,'--run'],cwd=core.week.RUNNER_ROOT,env=env,
                stdout=stream,stderr=stream,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        atomic(OPS/'R046_RUN_LAUNCH.json',dict(UTC=now(),pid=p.pid,process_created=__import__('psutil').Process(p.pid).create_time(),authorization=record(AUTH)))


@contextmanager
def bindings():
    with core.week.bindings(),patch.object(core,'ENTRY',ENTRY),patch.object(core,'authority',authority),patch.object(core,'request_authority',request_authority),patch.object(core.week,'authority',request_authority),patch.object(core,'worker',worker),patch.object(core,'new_request',new_request),patch.object(core.seq,'validate_main_barrier',validate_barrier),patch.object(core,'actual_main',actual_function()):yield


def main():
    p=argparse.ArgumentParser();p.add_argument('--transition',action='store_true');p.add_argument('--run',action='store_true');p.add_argument('--worker',type=Path);p.add_argument('--entry-check',action='store_true');a=p.parse_args()
    with bindings():
        try:
            if a.worker:return worker(a.worker,a.entry_check)
            if a.transition:return transition()
            if a.run:return run()
            p.error('Choose --transition, --run or --worker')
        except BaseException as error:
            atomic(OPS/'R046_ENTRY_ERROR.json',dict(UTC=now(),error=repr(error),traceback=traceback.format_exc()));raise

if __name__=='__main__':main()

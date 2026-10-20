"""Explicit shared-parent B0 lane, then exclusive serial B2 continuation.

The parent alone publishes the main state while it runs. This controller owns
an independent lease and B0 slot. A matching drain marker prevents duplicate
baseline dispatch; global OS locks transfer only after the parent's natural
exit. Completed B0 results merge exactly once, with no live workers at merge.
"""
from pathlib import Path
from contextlib import contextmanager,ExitStack
from unittest.mock import patch
import argparse,os,sys,time,traceback,psutil
from v44_recovery_r046 import operations as parent
from v44.common import read,record,verify,atomic,digest,now
from v44.locks import alive,exclusive_lock,process_identity,EXTERNAL_LOCKS

core=parent.core
CAMPAIGN,OPS,STATE=parent.CAMPAIGN,parent.OPS,parent.STATE
ENTRY='v44_recovery_r047.operations'
AUTH=OPS/'R047_B0_PARALLEL_AUTHORIZATION.json'
AUX=OPS/'R047_B0_PARALLEL'
AUX_STATE=AUX/'STATE.json'
LEASE=AUX/'COORDINATOR_LEASE.json'
OWNERSHIP=AUX/'RESOURCE_OWNERSHIP.json'
REASON='R047_B0_PARALLEL_NATURAL_HANDOVER'


def sources():return [record(p) for p in sorted(Path(__file__).parent.glob('*.py'))]


def authority():
    parent.authority();v=read(AUTH)
    verify(v['sources']+[v['previous_authorization'],v['validation'],v['user_request']])
    if (v['sources']!=sources() or v['previous_authorization']!=record(parent.AUTH)
        or not read(v['validation']['path'])['PASS'] or v['B0_workers']!=1
        or v['days']!=list(core.week.DAYS) or v['parallel_arms']!=['B0']):
        raise PermissionError('R047_EXACT_TESTED_B0_ONLY_POLICY_REQUIRED')
    return v


def request_authority(r=None):
    if r is None:return parent._week_authority()
    authority();parent.request_authority(r)
    if r.get('R047_authorization')!=record(AUTH) or r['arm'] not in ('B0','B2'):
        raise PermissionError('R047_AUTHORIZED_BASELINES_ONLY')
    return r


def expected_stop():return dict(reason=REASON,authorization=record(AUTH),user_stop=False)


def stop_matches():
    return core.seq.STOP.exists() and all(read(core.seq.STOP).get(k)==v for k,v in expected_stop().items())


def resources_ready():
    """Check explicit shared ownership, or the receipt for transferred OS locks."""
    v=authority();owner=read(OWNERSHIP)
    if owner.get('mode')=='EXCLUSIVE':
        if owner.get('lease')!=read(LEASE) or not alive(owner['lease']):raise PermissionError('R047_EXCLUSIVE_OWNER_DEAD')
        return
    p=v['parent_lease']
    if alive(p) and p==read(CAMPAIGN/'COORDINATOR_LEASE.json') and stop_matches():return
    # Parent exit and OS lock transfer may occur between two source admissions.
    for _ in range(120):
        if not alive(read(LEASE)):break
        if read(OWNERSHIP).get('mode')=='EXCLUSIVE':return resources_ready()
        time.sleep(.25)
    raise PermissionError('R047_SHARED_PARENT_OR_TRANSFERRED_OS_LOCKS_REQUIRED')


@contextmanager
def shared_resources(path):
    from v44.execution import assert_current
    request_authority(assert_current()['request'])
    if Path(path).resolve() not in [p.resolve() for p in EXTERNAL_LOCKS]:raise PermissionError('R047_UNKNOWN_RESOURCE')
    resources_ready();yield


@contextmanager
def b0_slot(day,arm,slot,*,root,lease):
    if (arm!='B0' or slot!=1 or day not in core.week.DAYS or Path(root)!=CAMPAIGN
        or lease!=read(LEASE) or not alive(lease)):
        raise PermissionError('R047_ONE_B0_SLOT_AND_LIVE_AUX_OWNER_REQUIRED')
    resources_ready()
    with exclusive_lock(CAMPAIGN/'locks/B0_PARALLEL_SLOT_1.lock'),exclusive_lock(CAMPAIGN/f'locks/cases/{day}_B0.lock'):
        yield dict(**process_identity(),day=day,arm=arm,worker_slot=1,lane='B0_PARALLEL')


def boundary(r):
    from v44_recovery_r029 import operations as historical,handover
    request_authority(r)
    if r['lease']!=read(LEASE) or not alive(r['lease']):raise PermissionError('R047_AUX_LEASE_REQUIRED')
    args=psutil.Process(r['lease']['pid']).cmdline()
    if ENTRY not in args or '--run' not in args:raise PermissionError('R047_REAL_CONTROLLER_REQUIRED')
    foreign=[];peers=[]
    for p in historical.workers():
        args=p.get('cmdline') or []
        try:
            peer=read(args[args.index('--worker')+1])
            if p['pid']==os.getpid() and ENTRY in args and peer==r:continue
            if (parent.ENTRY in args and peer.get('lease')==authority()['parent_lease']
                and peer.get('r038_phase')=='ACTUAL_PARALLEL' and peer.get('sequence_mode')=='MAIN'):
                parent.request_authority(peer);peers.append(p['pid']);continue
        except (ValueError,IndexError,OSError,KeyError):pass
        foreign.append(p)
    guard=read(historical.OPS/'R029_HANDOVER_GUARD.json')
    if not handover.boundary(guard,lease=read(historical.CAMPAIGN/'COORDINATOR_LEASE.json'),workers=foreign):
        raise PermissionError('R047_FOREIGN_OR_HISTORICAL_PROTECTED_WORKER')
    if Path(r['case_root']).resolve()==Path(guard['protected_case_root']).resolve():raise PermissionError('R047_PROTECTED_CASE')
    resources_ready();return guard


def worker(path,entry_check=False):
    r=read(path);request_authority(r)
    if r['arm']=='B2':return parent.worker(path,entry_check)
    boundary(r)
    if entry_check:
        atomic(AUX/'ENTRY_CHECK.json',dict(PASS=True,UTC=now(),**process_identity(),request=record(path),Native_calls=0));return
    from v44 import campaign,execution
    from v44_recovery_r029 import handover
    from v44_recovery_r038 import operations as inherited
    from v44_recovery_r039 import latency
    from v44_recovery_r045.reference import project
    from v43_arms import reference
    with inherited.previous.install(),latency.install(lambda:request_authority(execution.assert_current()['request'])),patch.object(handover,'require_boundary',lambda:boundary(r)),patch.object(reference,'project',project),patch.object(campaign,'worker_slot',b0_slot),patch.object(execution,'shared_lease_scope',shared_resources):
        return inherited.base.worker(r)


def new_request(job,lease,mode):
    path=parent.new_request(job,lease,mode);r=read(path)
    r.update(R047_authorization=record(AUTH),B0_parallel=r['arm']=='B0')
    r['sources']=list({x['path']:x for x in r['sources']+sources()+[record(AUTH)]}.values());r['source_sha']=digest(r['sources'])
    request_authority(r);path=OPS/'requests'/f"{r['day']}_{r['arm']}_R047.json";atomic(path,r)
    job['prepare_request']=str(path);return path


def publish_aux(state,running=()):
    state.update(UTC=now(),workers=[dict(pid=p.pid,process_created=psutil.Process(p.pid).create_time(),day=j['day'],arm=j['arm']) for p,j in running if p.poll() is None])
    atomic(AUX_STATE,state)


def acquire_after_parent(stack):
    if read(OWNERSHIP)['mode']=='EXCLUSIVE':return
    if alive(authority()['parent_lease']):return
    state=read(STATE)
    if not stop_matches() or not core.seq.main_resolved(state['jobs']):raise PermissionError('R047_PARENT_MUST_DRAIN_ALL_MAIN_CASES')
    for j in state['jobs']:
        if j['arm'] not in ('B1','B3'):continue
        for name in ('START.json','ACTUAL_START.json'):
            f=Path(j['case_root'])/name
            if f.exists() and alive(read(f)):raise PermissionError('R047_PARENT_WORKER_STILL_ALIVE')
    stack.enter_context(exclusive_lock(CAMPAIGN/'locks/COORDINATOR.lock'))
    for path in EXTERNAL_LOCKS:stack.enter_context(exclusive_lock(path))
    atomic(OWNERSHIP,dict(UTC=now(),mode='EXCLUSIVE',lease=read(LEASE),parent=authority()['parent_lease'],external_locks=[str(p) for p in EXTERNAL_LOCKS]))


def merge_aux(state,aux):
    if alive(state.get('lease')) or aux.get('workers') or not core.seq.main_resolved(state['jobs']):raise PermissionError('R047_MERGE_ONLY_AT_DRAINED_BOUNDARY')
    if len(aux['jobs'])!=7 or {core.seq.key(j) for j in aux['jobs']}!={(d,'B0') for d in core.week.DAYS}:raise PermissionError('R047_ALL_SEVEN_UNIQUE_B0_RESULTS_REQUIRED')
    for new in aux['jobs']:
        old=next(j for j in state['jobs'] if core.seq.key(j)==core.seq.key(new))
        if old['status']!='BASELINE_QUEUED' or new['status'] not in core.seq.MAIN_TERMINAL:raise PermissionError('R047_EXACT_TERMINAL_B0_MERGE')
        verify([new['result']]);result=read(new['result']['path'])
        if (result.get('day'),result.get('arm'))!=core.seq.key(new) or not result.get('finished_UTC'):raise PermissionError('R047_DATED_FINISHED_RESULT_REQUIRED')
        if (result.get('PASS') is True)!=(new['status']=='PASS'):raise PermissionError('R047_NO_FALSE_PASS')
        old.update(new)
    return state


def run():
    v=authority();AUX.mkdir(exist_ok=True)
    with exclusive_lock(AUX/'CONTROLLER.lock'),ExitStack() as locks:
        if AUX_STATE.exists() or core.seq.STOP.exists():raise PermissionError('R047_NEW_DISPATCH_AND_NO_FOREIGN_STOP_REQUIRED')
        if read(STATE)['lease']!=v['parent_lease'] or not alive(v['parent_lease']):raise PermissionError('R047_LIVE_EXACT_PARENT_REQUIRED')
        if any(j['status']=='PREPARED' for j in read(STATE)['jobs']):raise PermissionError('R047_PRESERVE_UNLAUNCHED_MAIN_ACTUAL_QUEUE')
        lease=dict(**process_identity(),UTC=now(),root=str(AUX),external_locks=[str(p) for p in EXTERNAL_LOCKS],shared_parent=v['parent_lease'])
        atomic(LEASE,lease);atomic(OWNERSHIP,dict(UTC=now(),mode='SHARED_PARENT',lease=lease,parent=v['parent_lease']))
        atomic(core.seq.STOP,dict(UTC=now(),**expected_stop(),operational_transition=True,current_workers_must_finish=True,duplicate_B0_dispatch_prevented=True))
        state=dict(phase='B0_PARALLEL_SERIAL',lease=lease,authorization=record(AUTH),jobs=[dict(j) for j in read(STATE)['jobs'] if j['arm']=='B0'])
        try:
            for job in state['jobs']:
                if job['status']!='BASELINE_QUEUED' or Path(job['case_root']).exists():raise PermissionError('R047_UNSTARTED_B0_CASE_REQUIRED')
                if not stop_matches():state['phase']='USER_STOPPED';publish_aux(state);return
                acquire_after_parent(locks)
                path=new_request(job,lease,'BASELINE_FULL');publish_aux(state)
                checked=core.launch(path,'entry',entry_check=True)
                while checked.poll() is None:acquire_after_parent(locks);publish_aux(state);time.sleep(1)
                if checked.returncode!=0:raise RuntimeError('R047_REAL_B0_ENTRY_CHECK_FAILED')
                process=core.launch(path,'full_case')
                while process.poll() is None:acquire_after_parent(locks);publish_aux(state,[(process,job)]);time.sleep(3)
                core.collect(process,job,baseline=True);publish_aux(state)
            state['phase']='B0_COMPLETE_WAIT_PARENT';publish_aux(state)
            while alive(v['parent_lease']):
                if not stop_matches():return
                publish_aux(state);time.sleep(3)
            acquire_after_parent(locks)
            merged=merge_aux(read(STATE),state);atomic(AUX/'MAIN_STATE_BEFORE_MERGE.json',read(STATE))
            if not stop_matches():return
            atomic(AUX/'DRAIN_MARKER_PRESERVED.json',read(core.seq.STOP));core.seq.STOP.unlink()
            lease=dict(**process_identity(),UTC=now(),root=str(CAMPAIGN),external_locks=[str(p) for p in EXTERNAL_LOCKS])
            atomic(CAMPAIGN/'COORDINATOR_LEASE.json',lease);merged['lease']=lease
            merged['R047_authorization']=record(AUTH);core.publish(merged)
            pointer=Path('D:/MobileESS_V44/runtime/ACTIVE_CAMPAIGN.json');p=read(pointer)
            p.update(UTC=now(),coordinator=lease,operational_entry=ENTRY,operational_recovery=record(AUTH));atomic(pointer,p)
            state['phase']='MERGED_B2_SERIAL';publish_aux(state)
            core.baseline_serial(merged,lease)
            if core.seq.STOP.exists():merged['phase']='USER_STOPPED';core.publish(merged);return
            if not all(j['status'] in core.seq.MAIN_TERMINAL for j in merged['jobs']):raise PermissionError('R047_UNRESOLVED_CASES')
            merged.update(phase='COMPLETE',all_PASS=all(j['status']=='PASS' for j in merged['jobs']));core.publish(merged)
            atomic(OPS/'FINAL_RESULT.json',dict(UTC=now(),phase='COMPLETE',PASS=merged['all_PASS'],jobs=merged['jobs'],authorization=record(AUTH)))
        except BaseException as error:
            state.update(phase='INFRASTRUCTURE_BLOCKED',error=repr(error));publish_aux(state)
            atomic(AUX/'ERROR.json',dict(UTC=now(),error=repr(error),traceback=traceback.format_exc()));raise


@contextmanager
def bindings():
    with parent.bindings(),patch.object(core,'ENTRY',ENTRY),patch.object(core,'request_authority',request_authority),patch.object(core.week,'authority',request_authority),patch.object(core,'new_request',new_request),patch.object(core,'worker',worker):yield


def main():
    p=argparse.ArgumentParser();p.add_argument('--run',action='store_true');p.add_argument('--worker',type=Path);p.add_argument('--entry-check',action='store_true');a=p.parse_args()
    with bindings():
        if a.worker:return worker(a.worker,a.entry_check)
        if a.run:return run()
        p.error('Choose --run or --worker')

if __name__=='__main__':main()

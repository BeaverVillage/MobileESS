"""One monthly B0 lane plus preserved main Actual and later serial B2.

Only the idle r047 controller is superseded. Its seven completed B0 results
are adopted after the live r046 Actual owner drains. No live case is killed,
restarted, or overwritten. New weeks authorize B0 only; other arms stay held.
"""
from pathlib import Path
from contextlib import contextmanager,ExitStack
from unittest.mock import patch
import argparse,os,sys,time,subprocess,traceback,psutil
from v44_recovery_r047 import operations as old
from v44.common import read,record,verify,atomic,digest,now
from v44.locks import alive,exclusive_lock,process_identity,EXTERNAL_LOCKS

core=old.core
MAIN,OPS=old.CAMPAIGN,old.OPS
HOME=OPS/'R048_MONTH_B0';AUTH=HOME/'AUTHORIZATION.json';STATE=HOME/'STATE.json'
LEASE=HOME/'COORDINATOR_LEASE.json';OWNER=HOME/'RESOURCE_OWNERSHIP.json'
ENTRY='v44_recovery_r048.operations';REASON='R048_B0_THROUGH_MAY31_NATURAL_HANDOVER'
DAYS=tuple(f'2025-05-{n:02d}' for n in range(15,32))
ROOT=MAIN.parent
CAMPAIGNS=(ROOT/'campaign006_may15_21',ROOT/'campaign007_may22_31')


def sources():return [record(p) for p in sorted(Path(__file__).parent.glob('*.py'))]


def campaign_for(day):
    if day not in DAYS:raise PermissionError('R048_EXACT_MAY15_31_DATE_REQUIRED')
    return CAMPAIGNS[0] if day<='2025-05-21' else CAMPAIGNS[1]


def authority():
    v=read(AUTH);verify(v['sources']+[v['validation'],v['user_request'],v['previous_authorization']]+v['prepared_evidence'])
    if v['sources']!=sources() or v['days']!=list(DAYS) or v['new_execution_arms']!=['B0'] or v['B0_workers']!=1:
        raise PermissionError('R048_SEALED_ONE_B0_WORKER_ONLY')
    if not read(v['validation']['path'])['PASS']:raise PermissionError('R048_TESTS_REQUIRED')
    return v


def stop_matches():
    return core.seq.STOP.exists() and read(core.seq.STOP).get('reason')==REASON and read(core.seq.STOP).get('authorization')==record(AUTH)


def authorize_case(r):
    v=authority();verify(r['sources'])
    if r.get('R048_authorization')!=record(AUTH) or r['worker_slot']!=1:raise PermissionError('R048_REQUEST_AUTHORITY_REQUIRED')
    arm,day=r['arm'],r['day']
    if arm=='B0':
        root=campaign_for(day);p=next(p for p in v['plan'] if p['day']==day)
        if not p['eligible']:raise PermissionError('R048_INPUT_BLOCKED_DATE_CANNOT_EXECUTE')
        if Path(r['campaign_root'])!=root or Path(r['case_root'])!=root/day/'B0/attempt001':raise PermissionError('R048_DATED_B0_ROOT_REQUIRED')
        permit=root/'OPERATIONS/B0_EXECUTION_PERMIT.json'
        if r['execution_permit']!=record(permit) or r['lease']!=read(LEASE):raise PermissionError('R048_B0_PERMIT_AND_AUX_LEASE_REQUIRED')
        frozen=read(root/'OPERATIONS/templates'/f'{day}_B0.json')
        expected={x['path']:x for x in frozen['input_records'].values()};actual={x['path']:x for x in r['sources']}
        if any(actual.get(k)!=x for k,x in expected.items()):raise PermissionError('R048_EXACT_DATED_INPUT_RECORDS_REQUIRED')
    elif arm=='B2' and day in core.week.DAYS:
        old.parent.request_authority(r)
        if r['lease']!=read(MAIN/'COORDINATOR_LEASE.json') or read(OWNER)['mode']!='EXCLUSIVE':raise PermissionError('R048_EXCLUSIVE_MAIN_B2_REQUIRED')
    else:raise PermissionError('R048_OTHER_NEW_ARMS_REMAIN_HELD')
    if not alive(r['lease']):raise PermissionError('R048_LIVE_OWNER_REQUIRED')
    return r


def resources_ready():
    v=authority();ownership=read(OWNER)
    if ownership.get('mode')=='EXCLUSIVE' and ownership.get('lease')==read(LEASE) and alive(ownership['lease']):return
    p=v['parent_lease']
    if alive(p) and p==read(MAIN/'COORDINATOR_LEASE.json') and stop_matches():return
    for _ in range(120):
        if not alive(read(LEASE)):break
        if read(OWNER).get('mode')=='EXCLUSIVE':return resources_ready()
        time.sleep(.25)
    raise PermissionError('R048_REAL_PARENT_OR_TRANSFERRED_RESOURCE_OWNERSHIP_REQUIRED')


@contextmanager
def shared_resources(path):
    from v44.execution import assert_current
    authorize_case(assert_current()['request'])
    if Path(path).resolve() not in [p.resolve() for p in EXTERNAL_LOCKS]:raise PermissionError('R048_UNKNOWN_LEGACY_RESOURCE')
    resources_ready();yield


@contextmanager
def slot(day,arm,n,*,root,lease):
    if n!=1 or not alive(lease):raise PermissionError('R048_SINGLE_WORKER_SLOT_REQUIRED')
    if arm=='B0':
        if Path(root)!=campaign_for(day) or lease!=read(LEASE):raise PermissionError('R048_EXACT_B0_SLOT_REQUIRED')
        name='B0_MONTH_SLOT_1';case_root=Path(root)
    elif arm=='B2' and day in core.week.DAYS:
        state=read(core.STATE)
        if Path(root)!=MAIN or lease!=read(MAIN/'COORDINATOR_LEASE.json') or not core.seq.main_resolved(state['jobs']):raise PermissionError('R048_MAIN_MUST_RESOLVE_BEFORE_B2')
        name='B2_SLOT_1';case_root=MAIN
    else:raise PermissionError('R048_ONLY_AUTHORIZED_B0_OR_EXISTING_B2')
    resources_ready()
    with exclusive_lock(HOME/(name+'.lock')),exclusive_lock(case_root/f'locks/cases/{day}_{arm}.lock'):
        yield dict(**process_identity(),day=day,arm=arm,worker_slot=1,lane=name)


def boundary(r):
    from v44_recovery_r029 import operations as historical,handover
    authorize_case(r);v=authority();foreign=[]
    if ENTRY not in psutil.Process(r['lease']['pid']).cmdline():raise PermissionError('R048_REAL_CONTROLLER_REQUIRED')
    for p in historical.workers():
        args=p.get('cmdline') or []
        try:
            peer=read(args[args.index('--worker')+1])
            if ENTRY in args:
                authorize_case(peer)
                if peer['lease']['pid']==r['lease']['pid']:continue
            if old.parent.ENTRY in args and peer.get('lease')==v['parent_lease'] and peer.get('r038_phase')=='ACTUAL_PARALLEL':
                old.parent.request_authority(peer);continue
        except (ValueError,IndexError,OSError,KeyError):pass
        foreign.append(p)
    guard=read(historical.OPS/'R029_HANDOVER_GUARD.json')
    if not handover.boundary(guard,lease=read(historical.CAMPAIGN/'COORDINATOR_LEASE.json'),workers=foreign):raise PermissionError('R048_FOREIGN_OR_PROTECTED_CASE')
    if Path(r['case_root']).resolve()==Path(guard['protected_case_root']).resolve():raise PermissionError('R048_PROTECTED_CASE')
    resources_ready();return guard


def project(native):
    from v44_recovery_r045.reference import roster,_original_project
    from v44.daily import clone
    rows=read(native['reference']['path']);selected,extra=roster(native,rows)
    source=Path(native['reference']['path']).resolve();original_read=_original_project.__globals__['read']
    def exact_read(path):return selected if Path(path).resolve()==source else original_read(path)
    result=clone(_original_project,read=exact_read)(native)
    from v44.execution import assert_current
    case=Path(assert_current()['request']['case_root'])
    atomic(case/'R048_R0_PROJECTION.json',dict(day=native['day'],original_reference=record(source),
        original_rows=len(rows),native_rows=len(selected),extra_posth_UIDs=[r['job_uid'] for r in extra],removed_native_jobs=0))
    return result


def worker(path,entry_check=False):
    r=read(path);boundary(r)
    if entry_check:atomic(HOME/(path.stem+'.ENTRY_CHECK.json'),dict(PASS=True,UTC=now(),**process_identity(),request=record(path),Native_calls=0));return
    from v44 import campaign,execution
    from v44_recovery_r029 import handover
    from v44_recovery_r038 import operations as inherited
    from v44_recovery_r039 import latency
    from v43_arms import reference
    with inherited.previous.install(),latency.install(lambda:authorize_case(execution.assert_current()['request'])),patch.object(handover,'require_boundary',lambda:boundary(r)),patch.object(reference,'project',project),patch.object(campaign,'worker_slot',slot),patch.object(execution,'shared_lease_scope',shared_resources):
        return inherited.base.worker(r)


@contextmanager
def bindings(r=None):
    from v44 import prepare,inputs,public_inputs,daily
    from v44_recovery_r029 import a2_cache
    original=prepare.require_execution_permit
    root=Path(r['campaign_root']) if r else MAIN
    if root not in (MAIN,)+CAMPAIGNS:raise PermissionError('R048_KNOWN_CAMPAIGN_ONLY')
    days=core.week.DAYS if root==MAIN else tuple(d for d in DAYS if campaign_for(d)==root)
    permit=root/'OPERATIONS/B0_EXECUTION_PERMIT.json';cert=root/'DOCUMENTS/B0_PREEXECUTION_CERTIFICATION.json'
    def require(path,certification):
        if root!=MAIN and Path(path).resolve()==permit.resolve():
            with core.week.period(days):v=original(path,read(cert))
            if v.get('allowed_arms')!=['B0'] or v.get('R048_authorization')!=record(AUTH):raise PermissionError('R048_B0_ONLY_EXECUTION_PERMIT')
            if r is not None and r['arm']!='B0':raise PermissionError('R048_PERMIT_CANNOT_RELEASE_OTHER_ARMS')
            verify(v['input_sources']+v['adapter_sources']);return v
        return fallback(path,certification)
    with core.week.bindings(),ExitStack() as stack,core.week.period(days):
        fallback=prepare.require_execution_permit
        if root!=MAIN:
            for m in (daily,inputs,public_inputs,a2_cache):stack.enter_context(patch.object(m,'DOC',root/'DOCUMENTS'))
            for m in (inputs,public_inputs):stack.enter_context(patch.object(m,'DAYS',days))
            stack.enter_context(patch.object(prepare,'require_execution_permit',require))
        yield


def new_request(job,lease):
    if job['arm']=='B2':
        path=old.parent.new_request(job,lease,'BASELINE_FULL');r=read(path)
    else:
        from v44_recovery_r038 import operations as inherited
        from v44_recovery_r039.operations import attach
        root=campaign_for(job['day']);f=read(root/'OPERATIONS/templates'/f"{job['day']}_B0.json")
        freeze=read(root/'DOCUMENTS/SCIENTIFIC_FREEZE_MANIFEST.json')
        rows=[x['V44'] for x in freeze['unchanged_source_rows']+freeze['unchanged_support_inputs']]+[x['source'] for x in freeze['inherited_external_M_algorithms']]+freeze['adapters']+freeze.get('physics_receipts',[])
        rows+=list(f['input_records'].values())
        r=attach(inherited.decorate(dict(day=job['day'],arm='B0',worker_slot=1,lane='B0_MONTH_SLOT_1',
            case_root=f['case_root'],campaign_root=str(root),axis=f['axis'],lease=lease,sources=rows,
            scientific_source_sha=freeze['source_sha'],execution_permit=record(root/'OPERATIONS/B0_EXECUTION_PERMIT.json'),r038_phase='BASELINE_SEQUENTIAL')))
    r['R048_authorization']=record(AUTH);r['sources']=list({x['path']:x for x in r['sources']+sources()+[record(AUTH),r['execution_permit']]}.values());r['source_sha']=digest(r['sources'])
    authorize_case(r);path=HOME/'requests'/f"{r['day']}_{r['arm']}.json";atomic(path,r)
    job.update(prepare_request=str(path),case_root=r['case_root'],status='BASELINE_RUNNING');return path


def launch(path,entry=False):
    args=[sys.executable,'-X','utf8','-u','-m',ENTRY,'--worker',str(path)]+(['--entry-check'] if entry else [])
    env=dict(os.environ,PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',NUMEXPR_NUM_THREADS='1')
    folder=HOME/'logs';folder.mkdir(exist_ok=True)
    with (folder/(path.stem+('.entry' if entry else '')+'.out.log')).open('ab') as out,(folder/(path.stem+('.entry' if entry else '')+'.err.log')).open('ab') as err:
        return subprocess.Popen(args,cwd=core.week.RUNNER_ROOT,env=env,stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW)


def publish(state,running):
    workers=[dict(pid=p.pid,process_created=psutil.Process(p.pid).create_time(),day=j['day'],arm=j['arm'],campaign_root=j['campaign_root']) for p,j,entry in running if p.poll() is None and not entry]
    state.update(UTC=now(),workers=workers);atomic(STATE,state)
    for root in CAMPAIGNS:
        s=read(root/'OPERATIONS/BATCH_STATE.json');updates={(j['day'],j['arm']):j for j in state['jobs'] if j['campaign_root']==str(root)}
        s['jobs']=[dict(j,**updates.get((j['day'],j['arm']),{})) for j in s['jobs']]
        s.update(UTC=now(),phase='B0_ONLY_ACTIVE' if any(j['status'] not in core.seq.MAIN_TERMINAL for j in updates.values()) else 'B0_RESOLVED_OTHERS_HELD',
            execution_authorized_arms=['B0'],R048_authorization=record(AUTH),auto_start=False)
        atomic(root/'OPERATIONS/BATCH_STATE.json',s)
        atomic(root/'CAMPAIGN_STATUS.json',dict(UTC=now(),phase=s['phase'],cases=s['jobs'],workers=[w for w in workers if w['campaign_root']==str(root)],execution_authorized_arms=['B0']))


def acquire_main(stack,state):
    if state.get('main_adopted'):return read(MAIN/'COORDINATOR_LEASE.json')
    v=authority()
    if alive(v['parent_lease']):return None
    s=read(core.STATE)
    if not stop_matches() or not core.seq.main_resolved(s['jobs']):raise PermissionError('R048_MAIN_DRAIN_REQUIRED')
    if alive(v['old_aux_lease']):raise PermissionError('R048_IDLE_OLD_CONTROLLER_MUST_EXIT')
    for j in s['jobs']:
        for name in ('START.json','ACTUAL_START.json'):
            f=Path(j['case_root'])/name
            if f.exists() and alive(read(f)):raise PermissionError('R048_OLD_CASE_STILL_ALIVE')
    stack.enter_context(exclusive_lock(MAIN/'locks/COORDINATOR.lock'))
    for p in EXTERNAL_LOCKS:stack.enter_context(exclusive_lock(p))
    atomic(OWNER,dict(mode='EXCLUSIVE',UTC=now(),lease=read(LEASE),external_locks=[str(p) for p in EXTERNAL_LOCKS]))
    s=old.merge_aux(s,read(old.AUX_STATE));atomic(HOME/'MAIN_STATE_BEFORE_ADOPTION.json',read(core.STATE))
    lease=dict(**process_identity(),UTC=now(),root=str(MAIN),external_locks=[str(p) for p in EXTERNAL_LOCKS])
    atomic(MAIN/'COORDINATOR_LEASE.json',lease);s.update(lease=lease,phase='BASELINE_SEQUENTIAL',R048_authorization=record(AUTH));core.publish(s)
    atomic(HOME/'DRAIN_MARKER_PRESERVED.json',read(core.seq.STOP));core.seq.STOP.unlink()
    state.update(main_adopted=True,main_jobs=s['jobs']);pointer=Path('D:/MobileESS_V44/runtime/ACTIVE_CAMPAIGN.json');a=read(pointer)
    a.update(UTC=now(),coordinator=lease,operational_entry=ENTRY,operational_recovery=record(AUTH));atomic(pointer,a)
    return lease


def run():
    v=authority();HOME.mkdir(exist_ok=True)
    with exclusive_lock(HOME/'CONTROLLER.lock'),ExitStack() as locks:
        if STATE.exists():raise PermissionError('R048_SINGLE_USE_DISPATCH')
        if not old.stop_matches() or read(old.AUX_STATE)['phase']!='B0_COMPLETE_WAIT_PARENT' or read(old.AUX_STATE)['workers']:
            raise PermissionError('R048_ONLY_IDLE_COMPLETED_OLD_B0_CONTROLLER_CAN_HAND_OVER')
        if read(core.STATE)['lease']!=v['parent_lease']:raise PermissionError('R048_PARENT_IDENTITY_CHANGED')
        atomic(HOME/'PREVIOUS_DRAIN_MARKER.json',read(core.seq.STOP))
        atomic(core.seq.STOP,dict(UTC=now(),reason=REASON,authorization=record(AUTH),operational_transition=True,user_stop=False,current_workers_must_finish=True))
        while alive(v['old_aux_lease']):time.sleep(1)
        lease=dict(**process_identity(),UTC=now(),root=str(HOME),external_locks=[str(p) for p in EXTERNAL_LOCKS],shared_parent=v['parent_lease'])
        atomic(LEASE,lease);atomic(OWNER,dict(mode='SHARED_PARENT',UTC=now(),lease=lease,parent=v['parent_lease']))
        state=dict(phase='B0_MONTH_PARALLEL',lease=lease,authorization=record(AUTH),main_adopted=False,jobs=[])
        for p in v['plan']:
            state['jobs'].append(dict(day=p['day'],arm='B0',campaign_root=p['campaign_root'],case_root=p['case_root'],
                status='BASELINE_QUEUED' if p['eligible'] else 'EXCLUDED',exclusion_reason=None if p['eligible'] else 'INPUT_BLOCKED:'+str(p['blockers'])))
        running=[];main_lease=None
        try:
            while True:
                main_lease=acquire_main(locks,state)
                stopped=core.seq.STOP.exists() and (state['main_adopted'] or not stop_matches())
                for process,job,entry in running[:]:
                    if process.poll() is None:continue
                    running.remove((process,job,entry))
                    if entry:
                        if process.returncode!=0:raise RuntimeError('R048_REAL_ENTRY_CHECK_FAILED:'+str((job['day'],job['arm'])))
                        path=Path(job['prepare_request']);running.append((launch(path),job,False))
                    else:core.collect(process,job,baseline=True)
                if not stopped:
                    for arm in ('B0','B2'):
                        if any(j['arm']==arm for _,j,_ in running):continue
                        jobs=state['jobs'] if arm=='B0' else state.get('main_jobs',[])
                        if arm=='B2' and not main_lease:continue
                        job=next((j for j in jobs if j['arm']==arm and j['status']=='BASELINE_QUEUED'),None)
                        if job:
                            job.setdefault('campaign_root',str(MAIN));path=new_request(job,lease if arm=='B0' else main_lease)
                            running.append((launch(path,True),job,True))
                publish(state,running)
                if state['main_adopted']:
                    s=read(core.STATE);s['jobs']=state['main_jobs'];core.publish(s,[(p,j) for p,j,e in running if j['arm']=='B2' and not e])
                if stopped and not running:state['phase']='USER_STOPPED';publish(state,[]);return
                b0_done=all(j['status'] in core.seq.MAIN_TERMINAL for j in state['jobs'])
                main_done=state['main_adopted'] and all(j['status'] in core.seq.MAIN_TERMINAL for j in state['main_jobs'])
                if b0_done and main_done:
                    s=read(core.STATE);s.update(phase='COMPLETE',all_PASS=all(j['status']=='PASS' for j in s['jobs']));core.publish(s)
                    atomic(OPS/'FINAL_RESULT.json',dict(UTC=now(),phase='COMPLETE',PASS=s['all_PASS'],jobs=s['jobs'],authorization=record(AUTH)))
                    state['phase']='COMPLETE';publish(state,[]);return
                time.sleep(3)
        except BaseException as error:
            # A running case retains its live owner until natural exit.
            state.update(phase='INFRASTRUCTURE_BLOCKED',error=repr(error));publish(state,running)
            atomic(HOME/'ERROR.json',dict(UTC=now(),error=repr(error),traceback=traceback.format_exc()))
            while any(p.poll() is None for p,_,_ in running):publish(state,running);time.sleep(3)
            raise


def main():
    p=argparse.ArgumentParser();p.add_argument('--run',action='store_true');p.add_argument('--worker',type=Path);p.add_argument('--entry-check',action='store_true');a=p.parse_args()
    if a.worker:
        r=read(a.worker)
        with bindings(r):return worker(a.worker,a.entry_check)
    if a.run:
        with bindings():return run()
    p.error('Choose --run or --worker')

if __name__=='__main__':main()

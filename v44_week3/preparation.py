"""Build an isolated, held seven-day input pack without running a campaign."""
from pathlib import Path
from contextlib import contextmanager,ExitStack
from unittest.mock import patch
import argparse,inspect,copy
import numpy as np
from v44.common import read,record,verify,atomic,digest,now,DOC as BASE_DOC
from v44_week2 import operations as previous

DAYS=tuple(f'2025-05-{n:02d}' for n in range(15,22))
ARMS=('B0','B1','B2','B3')
CAMPAIGN=Path('D:/MobileESS_V44/runtime/v43_planning_svr12_actual_v1/campaign006_may15_21')
DOC=CAMPAIGN/'DOCUMENTS'
OPS=CAMPAIGN/'OPERATIONS'
AUTH=OPS/'PREPARATION_AUTHORIZATION.json'
STATE=OPS/'BATCH_STATE.json'
VALIDATION=OPS/'PREPARATION_VALIDATION.json'
ACTIVE=Path('D:/MobileESS_V44/runtime/ACTIVE_CAMPAIGN.json')


def sources():return [record(p) for p in sorted(Path(__file__).parent.glob('*.py'))]


def denied(*args,**kwargs):raise PermissionError('MAY15_21_PREPARATION_ONLY_NO_NATIVE_OR_CAMPAIGN_EXECUTION')


@contextmanager
def bindings():
    from v44 import inputs,public_inputs,daily
    with previous.period(DAYS),ExitStack() as stack:
        for module in (inputs,public_inputs,daily):stack.enter_context(patch.object(module,'DOC',DOC))
        for module in (inputs,public_inputs):stack.enter_context(patch.object(module,'DAYS',DAYS))
        yield


@contextmanager
def no_execution():
    import gurobipy as gp
    from v44 import worker,campaign
    # No coordinator lease, subprocess worker, Native solve, or control replay.
    with ExitStack() as stack:
        for name in ('optimize','presolve','optimizeAsync'):
            if hasattr(gp.Model,name):stack.enter_context(patch.object(gp.Model,name,denied))
        for name in ('a_stage','m_stage','actual'):stack.enter_context(patch.object(worker,name,denied))
        for name in ('run','run_case','coordinator'):stack.enter_context(patch.object(campaign,name,denied))
        yield


def init_day(day):
    from v44 import inputs,daily
    from v44.initial_states import mess_contract
    from v43_actual.vendor.initial_state import prepare_initialization
    from v43_actual.vendor.initialization import initialize_running
    target=DOC/'initial_states'/day;local=target/'INPUT';local.mkdir(parents=True,exist_ok=True)
    pairs=((inputs.NATIVE_ROOT/day/'NATIVE_INPUT.json','NATIVE_INPUT_TEMPLATE_B1.json'),
        (inputs.BUNDLE_ROOT/('DAY_'+day.replace('-',''))/'PLANNING_INPUT_BUNDLE.json','PLANNING_INPUT_BUNDLE.json'))
    for source,name in pairs:(local/name).write_bytes(source.read_bytes())
    def initialize(*args,**kwargs):
        kwargs['expected_counts']=None;return initialize_running(*args,**kwargs)
    result=daily.clone(prepare_initialization,initialize_running=initialize)(local,target/'RUNNING',budget=None,
        source_assessment=dict(policy='INITIAL_RUNNING_SITE_MODEL_ASSUMED',private_completion_or_runtime_reads=0,
            reuse='Unchanged issue-only V43 initializer, independent same-date source'))
    if not result['policy']['PASS']:raise ValueError('WEEK3_INITIALIZATION_FAILED:'+day)
    native=read(local/'NATIVE_INPUT_TEMPLATE_B1.json');mess=target/'MESS_DAILY_INITIAL_STATE.json'
    atomic(mess,mess_contract(day,native))
    return dict(initial_running=record(target/'RUNNING/SYNTHETIC_INITIALIZATION_POLICY.json'),initial_MESS=record(mess))


def reference_fixture(day):
    """Pure original R0 projection for adapter validation, outside case outputs."""
    from v44.daily import clone,day_inputs,load_aidc
    from v44_recovery_r045.reference import roster,_original_project
    from v42_temporal.native import load_power
    from v42_integrated.contract import physical_authority
    row=day_inputs(day);native=read(row['files']['native']['path'])
    raw=read(native['reference']['path']);selected_rows,extra=roster(native,raw)
    original_read=_original_project.__globals__['read'];source=Path(native['reference']['path']).resolve()
    def exact_read(path):return selected_rows if Path(path).resolve()==source else original_read(path)
    sites,caps,known,anon,selected,x,carry,cons=clone(_original_project,read=exact_read)(native)
    with physical_authority():_,power,idle,swing=load_power(native)
    gpu=known+anon;it=idle*caps+swing*gpu
    pcc=np.array([[power[s,t].slope*it[t,j]+power[s,t].intercept_kw for j,s in enumerate(sites)] for t in range(96)])
    if not np.isfinite(pcc).all() or np.any(gpu>caps+1e-6):raise ValueError('WEEK3_REFERENCE_PHYSICAL_ARRAYS:'+day)
    arrays=dict(sites=np.array(sites),capacities=caps,known_gpu=known,cc4_served_gpu=anon,GPU=gpu,IT_kw=it,
        PCC_P_kw=pcc,PCC_Q_kvar=pcc*np.tan(np.arccos(.95)))
    folder=DOC/'reference_preflight'/day;folder.mkdir(parents=True,exist_ok=False)
    np.savez_compressed(folder/'PLANNING_PHYSICAL.npz',**arrays)
    aidc=dict(selected_jobs=selected,CC4_service=x,CC4_carryout=carry,
        AIDC_P_by_site={s:pcc[:,j].tolist() for j,s in enumerate(sites)},
        AIDC_Q_by_site={s:arrays['PCC_Q_kvar'][:,j].tolist() for j,s in enumerate(sites)})
    identity=dict(day=day,arm='B0',stage='REFERENCE',preparation_only=True,execution_authorized=False,
        parent_case_sha=row['files']['native']['sha256'],aidc_anchor=digest(aidc),input=row['files']['native'],
        windows=row['files']['windows'],reference=native['reference'],physical=record(folder/'PLANNING_PHYSICAL.npz'),
        source=sources()+list(row['files'].values()),conservation=cons,AIDC_optimization_calls=0,MESS_optimization_calls=0,
        rule='EXACT_PR189_R0_Q50_WITH_R045_NATIVE_ROSTER_ADMISSION',B1_optimized_commands_read=False)
    atomic(folder/'AIDC_REFERENCE.json',dict(identity=identity,**aidc));load_aidc(folder,day)
    return folder,dict(day=day,native_known=len(native['known_population']),R0_rows=len(raw),
        removed_current_native_jobs=0,proven_outside_native_posth_UIDs=[r['job_uid'] for r in extra],
        arrays_shape=list(gpu.shape),conservation=cons,reference=record(folder/'AIDC_REFERENCE.json'))


def validate_actual_adapter(day,folder):
    from v44.daily import ActualBinding,day_inputs
    from v44_recovery_r029.initial_running import install
    output=DOC/'actual_input_preflight'/day;output.mkdir(parents=True,exist_ok=False)
    with install():args,identity=ActualBinding('B0',folder,None,day).prepare(output,private_service=True)
    row=day_inputs(day);axis=row['axis']
    if args['begin']!=axis['issue_seconds'] or args['end']!=axis['end_seconds'] or identity['day']!=day:
        raise ValueError('WEEK3_ACTUAL_AXIS_DRIFT:'+day)
    native=read(row['files']['native']['path']);actual=read(row['files']['actual_input']['path'])
    if identity['Known']!=len(native['known_population']) or identity['Unknown']!=len(actual['post_issue_arrivals']):
        raise ValueError('WEEK3_ACTUAL_POPULATION_JOIN:'+day)
    if identity.get('private_exact_join_count')!=identity['Known']+identity['Unknown']:
        raise ValueError('WEEK3_PRIVATE_EVENT_JOIN_INCOMPLETE:'+day)
    if any(identity.get(k) is not False for k in ('Actual96_PASS','Fresh96_PASS')):raise ValueError('WEEK3_NO_RUN_NO_PASS')
    return dict(day=day,Known=identity['Known'],Unknown=identity['Unknown'],initial_Running=identity['initial_Running'],
        private_exact_join_count=identity['private_exact_join_count'],issue_seconds=args['begin'],end_seconds=args['end'],
        binding=record(output/'CASE_BINDINGS.json'),Native_calls=0,control_ticks=0,Actual_Fresh_executed=False,
        optimized_B1_B3_handoffs='Created only by later authorized same-date Planning; no prior-date plan reused')


def template(day,arm,row):
    if day not in DAYS or arm not in ARMS or row['day']!=day:raise ValueError('WEEK3_EXACT_DAY_ARM_REQUIRED')
    root=CAMPAIGN/day/arm/'attempt001'
    return dict(schema='V44_PREPARATION_ONLY_CASE_TEMPLATE_V1',day=day,arm=arm,status='PREPARED_HELD',
        campaign_root=str(CAMPAIGN),case_root=str(root),axis=row['axis'],input_folder=row['native_folder'],
        actual_bundle=row['actual_bundle'],input_records=row['files'],lease=None,execution_permit=None,
        execution_authorized=False,worker_started=False,planning_started=False,Actual_started=False,
        initial_state_policy='INDEPENDENT_SAME_DATE_ISSUE_ONLY_NO_PREVIOUS_OPTIMIZED_DAY',
        source_revision='V44 r047 dispatch / r046 A1 live compiler / original pinned science',
        required_stages={'B0':['REFERENCE','ACTUAL','FRESH'],'B1':['A1','ACTUAL','FRESH'],
            'B2':['REFERENCE','M1','ACTUAL','FRESH'],'B3':['A1_SAME_DATE_REUSE','M1','A2','M2','ACTUAL','FRESH']}[arm],
        same_date_B1_A1_required=str(CAMPAIGN/'B1_A1'/f'{day}.json') if arm=='B3' else None,
        reference_preflight=str(DOC/'reference_preflight'/day/'AIDC_REFERENCE.json'))


def validate_templates(values):
    from v44.config import axis
    expected={(d,a) for d in DAYS for a in ARMS}
    if len(values)!=28 or {(r['day'],r['arm']) for r in values}!=expected:raise ValueError('WEEK3_ALL_28_UNIQUE_CASES_REQUIRED')
    for r in values:
        if (r.get('execution_authorized') is not False or r.get('lease') is not None or r.get('execution_permit') is not None
            or r.get('status')!='PREPARED_HELD' or r.get('worker_started') is not False):raise PermissionError('WEEK3_EXPLICIT_PREPARATION_HOLD_REQUIRED')
        day,arm=r['day'],r['arm']
        if (Path(r['campaign_root'])!=CAMPAIGN or Path(r['case_root'])!=CAMPAIGN/day/arm/'attempt001'
            or Path(r['input_folder']).name!=day or Path(r['actual_bundle']).name!='DAY_'+day.replace('-','')
            or r['axis']!=axis(day)):raise ValueError('WEEK3_CROSS_DATE_INPUT_REJECTED')
        required=dict(native=Path(r['input_folder'])/'NATIVE_INPUT.json',windows=Path(r['input_folder'])/'WINDOWS.json',
            planning_input=Path(r['actual_bundle'])/'PLANNING_INPUT_BUNDLE.json',actual_input=Path(r['actual_bundle'])/'ACTUAL_INPUT_BUNDLE.json',
            provenance=Path(r['actual_bundle'])/'SOURCE_PROVENANCE.json',power_authority=Path(r['actual_bundle'])/'POWER_AUTHORITY.json',
            request_descriptors=DOC/'input_metadata'/day/'PUBLIC_REQUEST_DESCRIPTORS.json',
            initial_running_authority=DOC/'initial_states'/day/'RUNNING/SYNTHETIC_INITIALIZATION_POLICY.json',
            initial_MESS_authority=DOC/'initial_states'/day/'MESS_DAILY_INITIAL_STATE.json')
        if any(Path(r['input_records'][k]['path'])!=p for k,p in required.items()):raise ValueError('WEEK3_CROSS_DATE_SOURCE_RECEIPT_REJECTED')
        if arm=='B3' and r['same_date_B1_A1_required']!=str(CAMPAIGN/'B1_A1'/f'{day}.json'):
            raise ValueError('WEEK3_CROSS_DATE_A1_DEPENDENCY_REJECTED')
        verify(list(r['input_records'].values()))


def assert_unstarted():
    forbidden=[CAMPAIGN/'COORDINATOR_LEASE.json',OPS/'EXECUTION_PERMIT.json']
    forbidden+=[CAMPAIGN/d/a/'attempt001' for d in DAYS for a in ARMS]
    if any(p.exists() for p in forbidden):raise PermissionError('WEEK3_PREPARATION_MUST_NOT_HAVE_LIVE_CASE_OR_EXECUTION_PERMIT')


def prepare():
    from v44 import inputs,public_inputs,daily
    from v44_recovery_r047 import operations as current
    if CAMPAIGN.exists():raise FileExistsError('WEEK3_EXISTING_PREPARATION_REQUIRES_VERIFY_NOT_OVERWRITE')
    pointer_before=ACTIVE.read_bytes();current_lease=read(current.STATE).get('lease')
    main_identities=[]
    from v44.locks import alive
    for w in read(current.CAMPAIGN/'CAMPAIGN_STATUS.json').get('workers',[]):
        import psutil
        if psutil.pid_exists(w['pid']):main_identities.append(dict(pid=w['pid'],process_created=psutil.Process(w['pid']).create_time()))
    DOC.mkdir(parents=True);OPS.mkdir()
    try:
        atomic(DOC/'SCIENTIFIC_FREEZE_MANIFEST.json',read(BASE_DOC/'SCIENTIFIC_FREEZE_MANIFEST.json'))
        public_inputs.prepare_descriptors();links=read(DOC/'DAILY_AUTHORITY_BINDINGS.json')
        for day in DAYS:
            print('INITIAL_STATE '+day,flush=True);links[day].update(init_day(day))
        atomic(DOC/'DAILY_AUTHORITY_BINDINGS.json',links)
        manifest=inputs.manifest();atomic(DOC/'SEVEN_DAY_INPUT_MANIFEST.json',manifest)
        blockers=[dict(day=r['day'],blockers=r['blockers']) for r in manifest['days'] if r['blockers']]
        if blockers:raise ValueError(dict(INPUT_BLOCKERS=blockers))
        references=[];adapters=[];templates=[]
        for day in DAYS:
            print('REFERENCE_AND_ACTUAL_INPUT_JOIN '+day,flush=True)
            folder,detail=reference_fixture(day);references.append(detail);adapters.append(validate_actual_adapter(day,folder))
            row=daily.day_inputs(day)
            for arm in ARMS:
                r=template(day,arm,row);templates.append(r);atomic(OPS/'templates'/f'{day}_{arm}.json',r)
        validate_templates(templates);assert_unstarted()
        if ACTIVE.read_bytes()!=pointer_before:raise PermissionError('ACTIVE_CAMPAIGN_CHANGED_DURING_PREPARATION')
        # Natural worker completion is valid; no worker process operation occurs.
        atomic(VALIDATION,dict(PASS=True,UTC=now(),scope='Date/IO and full Actual input construction; no simulation or optimization',
            days=list(DAYS),cases=28,references=references,actual_input_adapters=adapters,Native_calls=0,control_ticks=0,
            A_M_Planning_executed=False,Actual_Fresh_executed=False,active_campaign_pointer_unchanged=True,
            active_campaign_worker_processes_at_start=main_identities,initial_state_previous_day_reads=0,
            all_28_templates=record_list(OPS/'templates'),manifest=record(DOC/'SEVEN_DAY_INPUT_MANIFEST.json')))
        instruction=OPS/'USER_PREPARE_ONLY_REQUEST.json'
        atomic(instruction,dict(UTC=now(),text='5/15~5/21 캠페인 준비. 아직 실행하지 말고 준비. 5/8~5/14 끝나면 실행 예정. 오류 없이 날짜별 데이터 연결.',execution_authorized=False,automatic_launch_authorized=False))
        atomic(AUTH,dict(UTC=now(),mode='PREPARE_ONLY',sources=sources(),days=list(DAYS),arms=list(ARMS),
            validation=record(VALIDATION),user_request=record(instruction),execution_authorized=False,automatic_launch_armed=False,
            predecessor_campaign=str(current.CAMPAIGN),release_requires='Separate explicit execution authorization after May08-14 terminal review',
            planned_dispatch=dict(B1_B3_Planning_workers=1,B1_B3_Actual_workers=7,B0_parallel_full_case_workers=1,B2_later_full_case_workers=1),
            scientific_sources_unchanged=True))
        jobs=[dict(day=r['day'],arm=r['arm'],status='PREPARED_HELD',template=record(OPS/'templates'/f"{r['day']}_{r['arm']}.json")) for r in templates]
        atomic(STATE,dict(UTC=now(),phase='PREPARED_HELD',jobs=jobs,preparation_authorization=record(AUTH),lease=None,auto_start=False,execution_authorized=False))
        atomic(CAMPAIGN/'CAMPAIGN_STATUS.json',dict(UTC=now(),phase='PREPARED_HELD',cases=jobs,workers=[],execution_authorized=False,auto_start=False))
        atomic(DOC/'PREEXECUTION_CERTIFICATION.json',dict(status='PREPARED_HELD',UTC=now(),days=list(DAYS),inputs='PASS',
            blockers=[],validation=record(VALIDATION),execution_authorized=False,automatic_launch_armed=False,
            note='Input readiness only. Planning/Actual/Fresh results and execution permission do not exist.'))
        return verify_prepared()
    except BaseException as error:
        atomic(OPS/'PREPARATION_ERROR.json',dict(UTC=now(),error=repr(error),execution_authorized=False));raise


def record_list(folder):return [record(p) for p in sorted(folder.glob('*.json'))]


def verify_prepared():
    assert_unstarted();v=read(AUTH);verify(v['sources']+[v['validation'],v['user_request']])
    if v['sources']!=sources() or v['mode']!='PREPARE_ONLY' or v['execution_authorized'] is not False or v['automatic_launch_armed'] is not False:
        raise PermissionError('WEEK3_HELD_PREPARATION_AUTHORITY_REQUIRED')
    verify(read(VALIDATION)['all_28_templates']);values=[read(p) for p in sorted((OPS/'templates').glob('*.json'))];validate_templates(values)
    state=read(STATE)
    if state['phase']!='PREPARED_HELD' or len(state['jobs'])!=28 or state['lease'] is not None or state['auto_start'] is not False:
        raise PermissionError('WEEK3_NO_DISPATCH_ALLOWED')
    return dict(PASS=True,phase='PREPARED_HELD',days=list(DAYS),cases=len(values),Native_calls=0,execution_authorized=False,auto_start=False,root=str(CAMPAIGN))


def main():
    p=argparse.ArgumentParser();group=p.add_mutually_exclusive_group(required=True)
    group.add_argument('--prepare',action='store_true');group.add_argument('--verify',action='store_true');args=p.parse_args()
    with bindings(),no_execution():print(prepare() if args.prepare else verify_prepared(),flush=True)

if __name__=='__main__':main()

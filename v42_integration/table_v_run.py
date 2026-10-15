"""Serial four-arm supervisor and evidence contracts, original engines only."""
from copy import deepcopy
import csv
import gc
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter
import traceback
import threading

from .a_engine import digest
from .m_engine import _write,file_record
from .table_v_budget import TableVStageBudget,MAIN_CAPS,K48_CAPS,SCHEMA
from .table_v_control import require_running, CampaignStopped
from .table_v_progress import write_progress
from .table_v_status import failed_stage_status

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'docs/v42_unified_aidc_mess_research_20261014/RELEASE_RECOVERY_20261015'
DEFAULT=BASE/'RC04/TABLE_V/EXECUTION01'
HISTORY=[ROOT/'docs/v42_unified_aidc_mess_research_20261014/UNIFIED_NATIVE_RUNTIME_LEDGER.json',
         BASE/'RC01/A1_P1_120/SEPARATE_NATIVE_LEDGER_180.json']
ARM_STAGES={'B0':[],'B1':['A1'],'B2':['M1'],'B3':['A1','M1','A2','M2']}


def adapters():
    names=['table_v_run.py','table_v_a.py','table_v_budget.py','table_v_mess.py','table_v_k48.py',
           'table_v_flex_planning.py','table_v_reference.py','tablev_actual.py','table_v_progress.py',
           'tablev_fullflex_actual.py','table_v_status.py','table_v_control.py','table_v_reuse.py',
           'table_v_dw.py','table_v_dw_reuse.py','table_v_gap_contract.py','table_v_dates.py','table_v_campaign.py','table_v_memory.py',
           'table_v_resources.py','table_v_launch.py','table_v_launch_evidence.py',
           'table_v_geometry_cache.py','table_v_compression.py','table_v_compression_verify.py',
           'table_v_compression_adapter.py','m_adaptive.py','m_warm.py','table_v_evaluation.py','m_source_revision.py',
           'table_v_global_control.py','table_v_a_control.py','table_v_phase_policy.py']
    return [file_record(Path(__file__).with_name(n)) for n in names]+[
        file_record(ROOT/'v42_may_campaign_native90/m_model.py'),
        file_record(Path(__file__).with_name('release_production_budget.py'))]


def verify_adapters(output):
    freeze=json.loads((Path(output)/'EXECUTION_SOURCE_FREEZE.json').read_text(encoding='utf8'))
    if (freeze['source_sha']!=digest(freeze['files'])
            or any(file_record(r['path'])!=r for r in freeze['files'])):
        raise ValueError('TABLE_V_EXECUTED_ADAPTER_BYTES_DRIFT')
    return freeze


def prepare(output=DEFAULT,*,day='2025-05-01',carry_forward_native_ledgers=(),authorizations=None):
    from .release_date_case import compile_date_case
    from .table_v_flex_planning import compile_table_v_flex_context
    from .table_v_reference import make_reference
    output=Path(output)
    from .release_date_case import require_day
    require_day(day)
    # The supervisor supplies the actual human-authorized documents. Never
    # invent an approval or total-cap waiver merely because prepare was called.
    if not authorizations or set(authorizations) != {'PLANNING','K48'}:
        raise PermissionError('EXPLICIT_PLANNING_AND_K48_AUTHORIZATION_DOCUMENTS_REQUIRED')
    from .table_v_budget import require_authorization
    for name,document in authorizations.items():
        require_authorization(document)
        kind='K48_SEPARATE' if name=='K48' else 'PLANNING_NATIVE'
        if (document['budget_kind']!=kind
                or Path(document['authorized_ledger_path']).resolve()!=(output/(name+'_NATIVE_LEDGER.json')).resolve()):
            raise PermissionError('EXACT_OUTPUT_LEDGER_AUTHORIZATION_REQUIRED')
    if output.exists():raise FileExistsError('TABLE_V_EXECUTION_ROOT_ALREADY_EXISTS')
    output.mkdir(parents=True)
    began=perf_counter()
    basic=compile_date_case(day,output=output/'INPUTS/BASIC',call_cap=5400.)
    context=compile_table_v_flex_context(basic,output=output/'INPUTS/FULL_FLEX',call_cap=5400.)
    reference=make_reference(context,output=output/'REFERENCE')
    # Reference producer returns (result, acceptance); there is one common pair.
    if isinstance(reference,tuple):ref,receipt=reference
    else:ref,receipt=reference['result'],reference['acceptance']
    _write(output/'REFERENCE_RESULT.json',ref);_write(output/'REFERENCE_ACCEPTANCE.json',receipt)
    state=context['state'];manifest=context['manifest']
    common=dict(schema='TABLE_V_COMMON_INITIAL_STATE_CERTIFICATE_V1',day=day,
        initial_state_sha=state['common_initial_state_sha'],initial_source=manifest['initial_record'],
        RUNNING_UIDs=len(state['running']),RUNNING_GPU=sum(r['gpu'] for r in state['running']),
        PENDING_UIDs=len(state['pending']),Known_UIDs=len(state['running'])+len(state['pending']),
        AIDC_count=len(state['capacities']),GPU_capacity=sum(state['capacities'].values()),
        capacities=state['capacities'],all_arms_same_initial=True,future_Unknown_UIDs_planning_used=False,
        prefix_hours=0,source_identity=manifest['identity'],source_sha=manifest['source_sha'])
    if ((common['AIDC_count'],common['GPU_capacity'])!=(12,780)
            or common['Known_UIDs']!=len(context['data'][4])
            or manifest['day']!=day or state['day']!=day):
        raise ValueError('TABLE_V_APPROVED_COMMON_INITIAL_ROSTER_DRIFT')
    _write(output/'TABLE_V_COMMON_INITIAL_STATE_CERTIFICATE.json',common)
    _write(output/'TABLE_V_FLEXIBILITY_POLICY_FREEZE.json',context['tablev_flex'])
    contract=dict(schema='TABLE_V_FOUR_ARM_CONTRACT_V1',day=day,
        Arms={a:dict(stages=s,computing='REFERENCE' if a in ('B0','B2') else 'FULL_E1_FLEX30_R1',
            MESS='OFF_LITERAL_ZERO_PQ' if a in ('B0','B1') else 'ORIGINAL_FULL_FOUR_MESS_ALL_IDC_AND_STA_PQ') for a,s in ARM_STAGES.items()},
        reference_result_sha=digest(ref),reference_acceptance_sha=digest(receipt),
        common_initial_state_sha=state['common_initial_state_sha'],source_identity=manifest['identity'],source_sha=manifest['source_sha'],
        official_physics='900_SECONDS_X_96_SETTLE_SLOT_THEN_MEASURE_FULL_NETWORK',
        substep_diagnostics_are_mandatory_gate=False,original_11SVR_7RegControl_AUTO_delays_history=True,
        P2_calls=0,Worker=1,Threads=1,R2='HOLD_PRESERVE_ONLY_NO_IMPLEMENT_MODIFY_RUN_VALIDATE',
        run_order=['B0','B1','B2','B3'],arm_failure_does_not_stop_others=True,
        total_native_limit_seconds=None,total_native_limit_enabled=False,stage_caps_seconds=MAIN_CAPS,
        K48_separate_stage_caps_seconds=K48_CAPS,K48_target_failure_blocks_feasible_Actual=False,
        historical_Basic_A1_not_new_fullflex_optimum=True,
        input_preparation_wall_seconds=perf_counter()-began)
    _write(output/'TABLE_V_FOUR_ARM_CONTRACT.json',contract)
    if day=='2025-05-01':
        for name,value in [('MAY01_COMMON_INITIAL_STATE_CERTIFICATE.json',common),
                           ('MAY01_FLEXIBILITY_POLICY_FREEZE.json',context['tablev_flex']),
                           ('MAY01_TABLE_V_FOUR_ARM_CONTRACT.json',contract)]:
            _write(output/name,value)
    for kind,caps,name in [('PLANNING_NATIVE',MAIN_CAPS,'PLANNING'),('K48_SEPARATE',K48_CAPS,'K48')]:
        predecessors=[file_record(p) for p in carry_forward_native_ledgers
            if json.loads(Path(p).read_text(encoding='utf8'))['authorization_document']['budget_kind']==kind]
        auth=deepcopy(authorizations[name])
        expected=[dict(day=day,source_sha=manifest['source_sha'],source_identity=manifest['identity'])]
        if auth['source_cases']!=expected or auth.get('carry_forward_ledgers',[])!=predecessors:
            raise PermissionError('EXACT_SOURCE_AND_CUMULATIVE_PREDECESSORS_AUTHORIZATION_REQUIRED')
        _write(output/(name+'_AUTHORIZATION.json'),auth)
        TableVStageBudget(auth['authorized_ledger_path'],authorization=auth,historical_ledgers=HISTORY)
    files=adapters()+[file_record(ROOT/'tools/run_v42_table_v.py')]
    _write(output/'EXECUTION_SOURCE_FREEZE.json',dict(files=files,source_sha=digest(files)))
    return context


def load_context(output=DEFAULT):
    from .release_date_case import load_date_case
    from .table_v_flex_planning import compile_table_v_flex_context
    output=Path(output);verify_adapters(output)
    saved=json.loads((output/'INPUTS/FULL_FLEX/TABLE_V_FLEX_CASE_MANIFEST.json').read_text(encoding='utf8'))
    day=saved['day']
    basic=load_date_case(day,output/'INPUTS/BASIC',call_cap=5400.)
    with TemporaryDirectory(prefix='table_v_public_recheck_') as temp:
        scratch=Path(temp)/'FULL_FLEX'
        context=compile_table_v_flex_context(basic,output=scratch,call_cap=5400.)
        for p in scratch.rglob('*'):
            if p.is_file():
                saved=output/'INPUTS/FULL_FLEX'/p.relative_to(scratch)
                if not saved.is_file() or saved.read_bytes()!=p.read_bytes():
                    raise ValueError('TABLE_V_PUBLIC_INPUT_REPLAY_DRIFT:'+str(saved))
    return context


def budget(output,kind):
    name='K48' if kind=='K48' else 'PLANNING'
    auth=json.loads((Path(output)/(name+'_AUTHORIZATION.json')).read_text(encoding='utf8'))
    return TableVStageBudget(auth['authorized_ledger_path'],authorization=auth,historical_ledgers=HISTORY)


def current_build_admission(budget,*,arm,stage,operation):
    from .table_v_resources import admit_resources
    resource_admission=admit_resources(budget,phase='PRE_MODEL_BUILD:'+operation)
    snapshot=resource_admission['snapshot']
    return dict(status='PASS',arm=arm,stage=stage,operation=operation,
        concurrent_heavy_solver=False,supervisor_serial_window=True,resource_snapshot=snapshot,
        live_resource_admission=resource_admission)


def require_arm_launch(output,launch_authority,*,actual_slots=None,arm=None):
    manifest=json.loads((Path(output)/'INPUTS/FULL_FLEX/TABLE_V_FLEX_CASE_MANIFEST.json').read_text(encoding='utf8'))
    from .table_v_dates import require_day
    day=require_day(manifest['day'])
    if not launch_authority:raise PermissionError('ALL_ARMS_REQUIRE_PRODUCTION_LAUNCH_APPROVAL_LATER_DATE_CANARY_GATE')
    from .table_v_campaign import _launch_gate
    plan,gate=launch_authority['plan'],launch_authority['gate']
    if arm is not None and arm not in plan.get('run_arms',list(ARM_STAGES)):
        raise PermissionError('ARM_NOT_IN_EXACT_APPROVED_RELEASE_PLAN')
    if actual_slots is not None and actual_slots!=plan.get('actual_slots',96):
        raise PermissionError('ACTUAL_SLOT_CLI_OPTION_DIFFERS_FROM_APPROVED_PLAN')
    expected=dict(day=day,source_sha=manifest['source_sha'],source_identity=manifest['identity'])
    if (day not in plan.get('dates',[]) or plan['case_bindings'].get(day)!=expected
            or Path(plan['execution_roots'][day]).resolve()!=Path(output).resolve()):
        raise PermissionError('EXACT_DATE_ARM_EXECUTION_ROOT_AND_CASE_APPROVAL_REQUIRED')
    _launch_gate(plan,gate)
    return day


def run_arm(arm,output=DEFAULT,*,attempt=None,actual_slots=96,launch_authority=None):
    """Every arm commits its own exact outcome even when a stage fails."""
    from .table_v_a import execute_current_a
    from .table_v_mess import TableVMessStages
    from .tablev_actual import run_tablev_actual,run_tablev_fresh
    from .release_ac_contract import CONTRACT
    from .table_v_memory import memory_sample
    if actual_slots not in (16,96):raise ValueError('TABLE_V_CANARY16_OR_FULL96_REQUIRED')
    output=Path(output);require_running(output);require_arm_launch(output,launch_authority,actual_slots=actual_slots,arm=arm);arm_folder=output/arm
    if attempt is not None and (not attempt.startswith('ATTEMPT') or not attempt.replace('_','').isalnum()):
        raise ValueError('EXPLICIT_APPEND_ONLY_ATTEMPT_NAME_REQUIRED')
    folder=arm_folder if attempt is None else arm_folder/attempt
    if folder.exists():raise FileExistsError('TABLE_V_ARM_ATTEMPT_ALREADY_EXISTS')
    folder.mkdir(parents=True)
    if attempt is not None:
        _write(arm_folder/'LATEST_ATTEMPT.json',dict(path=str(folder.resolve()),name=attempt,
            prior_attempts_preserved=True,Native_budget_reset=False))
    began=perf_counter();current='PUBLIC_INPUT_RECHECK';stages={};outcome={};day=None
    context=factory=case=point=kwargs=main=k48=None
    stop=threading.Event();resource_rows=[]
    def monitor():
        while not stop.is_set():
            try:
                resource_rows.append(dict(elapsed_seconds=perf_counter()-began,stage=current,**memory_sample()))
            except Exception:pass
            stop.wait(1.)
    observer=threading.Thread(target=monitor,daemon=True);observer.start()
    def progress(value):
        write_progress(folder/'LIVE_PROGRESS.json',dict(arm=arm,stage=current,elapsed_wall_seconds=perf_counter()-began,progress=value))
    try:
        context=load_context(output)
        day=context['manifest']['day']
        ref=json.loads((output/'REFERENCE_RESULT.json').read_text(encoding='utf8'))
        ref_accept=json.loads((output/'REFERENCE_ACCEPTANCE.json').read_text(encoding='utf8'))
        main=budget(output,'PLANNING');k48=budget(output,'K48');factory=TableVMessStages(context,main)
        aidc,aa=ref,ref_accept;mr=ma=None;m1_handoff=None
        for current in ARM_STAGES[arm]:
            require_running(output);verify_adapters(output);progress('STARTED')
            if current.startswith('A'):
                from .table_v_reuse import discover_a1_attempts
                reuse=discover_a1_attempts(output,context) if arm=='B3' and current=='A1' else None
                aidc,aa=execute_current_a(context,main,arm=arm,stage=current,output=folder/current,
                    parent_result=mr,parent_acceptance=ma,progress=progress,
                    reuse_a1=reuse)
                stages[current]=dict(result=aidc,acceptance=aa)
                if aa is None:raise RuntimeError('A_STAGE_HAS_NO_ORIGINAL_FULL_FEASIBLE_POINT')
            else:
                admission=current_build_admission(main,arm=arm,stage=current,operation='CURRENT_M_NATIVE0_BUILD')
                case=factory.prepare(arm,current,aidc,aa,folder/current,build_admission=admission,progress=progress)
                main.bind_table_v_case(arm=arm,stage=current,stage_case_sha=case.case_sha,
                    source_sha=context['manifest']['source_sha'],parent_result=aidc,
                    source_identity=context['manifest']['identity'],parent_acceptance=aa)
                warm_point=None;warm_receipt=None
                if arm=='B3' and current=='M2' and m1_handoff is not None:
                    from .m_warm import admit_m1
                    warm_point,warm_receipt=admit_m1(case,m1_handoff)
                mr,ma,point,kval=factory.execute_cooperative(arm,current,case,aidc,aa,k48_budget=k48,
                    k48_admission=lambda:current_build_admission(k48,arm=arm,stage=current,operation='CURRENT_K48_NATIVE_BUILD'),
                    initial_point=warm_point)
                warm_point=None

                stages[current]=dict(result=mr,acceptance=ma,warm_admission=warm_receipt)
                if ma is None:raise RuntimeError('M_STAGE_HAS_NO_ORIGINAL_FULL_FEASIBLE_POINT')
                stages[current]['K48']=kval
                if arm=='B3' and current=='M1':
                    from .m_warm import save_m1
                    m1_handoff=save_m1(case,point,mr,ma)
                del case,point;gc.collect()
            _write(folder/'PLANNING_STAGE_RESULTS.json',stages)
        require_running(output);current='ACTUAL'+str(actual_slots);progress('STARTED')
        actual_runner=run_tablev_actual
        kwargs=dict(context=context,arm=arm,reference_result=ref,reference_acceptance=ref_accept,
            output=folder/current,m_result=mr,m_acceptance=ma,
            gate=dict(Gate_contract=CONTRACT,official_contract_authorized=True),slots=actual_slots)
        if arm in ('B1','B3'):
            from .tablev_fullflex_actual import run_fullflex_actual
            actual_runner=run_fullflex_actual
            kwargs.update(a_result=aidc,a_acceptance=aa)
        arm_sources=adapters()
        if arm in ('B1','B3'):
            arm_sources.append(file_record(Path(__file__).with_name('tablev_fullflex_actual.py')))
        _write(folder/'ARM_EXECUTION_SOURCE_FREEZE.json',dict(files=arm_sources,source_sha=digest(arm_sources)))
        actual=actual_runner(**kwargs)
        _write(folder/'ACTUAL_RESULT.json',actual)
        if actual.get('status')!='FULL_PASS':raise RuntimeError('ACTUAL_STAGE_NOT_FULL_ACCEPTED')
        require_running(output);current='FRESH_AC'+str(actual_slots);progress('STARTED')
        fresh=run_tablev_fresh(context=context,actual_result=actual,output=folder/current,
            m_result=mr,m_acceptance=ma,slots=actual_slots)
        _write(folder/'FRESH_AC_RESULT.json',fresh)
        outcome=dict(status='FULL_PASS' if actual['status']=='FULL_PASS' and fresh['status']=='FULL_PASS' else 'PHYSICAL_OR_ACTUAL_FAIL',
            actual=actual,fresh=fresh,completed_planning_stages=list(stages),
            executed_actual_slots=actual_slots,executed_fresh_slots=actual_slots)
    except Exception as exc:
        status='INTERRUPTED_BY_USER' if isinstance(exc,CampaignStopped) else failed_stage_status(stages,current)
        outcome=dict(status=status,failed_stage=current,error=repr(exc),traceback=traceback.format_exc(),
            completed_planning_stages=[s for s,r in stages.items() if r.get('acceptance') is not None],
            attempted_planning_stages=list(stages),physical_PASS_claimed=False)
        _write(folder/'PLANNING_STAGE_RESULTS.json',stages)
    finally:
        stop.set();observer.join(timeout=2.)
        before_release=memory_sample()
        context=factory=case=point=kwargs=main=k48=None
        gc.collect()
        after_release=memory_sample()
        _write(folder/'WALL_RAM_RESOURCE_REPORT.json',dict(samples=resource_rows,
            peak_RSS_bytes=max((r['RSS_bytes'] for r in resource_rows),default=None),
            peak_private_bytes=max((r['private_bytes'] or 0 for r in resource_rows),default=None),
            wall_seconds=perf_counter()-began,Native_seconds_ledger_separate=True,
            model_build_and_forecast_and_Actual_and_AC_included_in_total_wall=True))
        _write(folder/'RESOURCE_RELEASE.json',dict(before_release=before_release,after_release=after_release,
            stage_objects_released=True,garbage_collection_completed=True,python_allocator_OS_return_not_guaranteed=True))
        outcome.update(day=day,arm=arm,wall_seconds=perf_counter()-began,P2_calls=0,R2='HOLD')
        _write(folder/'ARM_OUTCOME.json',outcome)
    return outcome

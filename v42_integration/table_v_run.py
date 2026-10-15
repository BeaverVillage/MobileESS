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

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'docs/v42_unified_aidc_mess_research_20261014/RELEASE_RECOVERY_20261015'
DEFAULT=BASE/'RC04/TABLE_V/EXECUTION01'
HISTORY=[ROOT/'docs/v42_unified_aidc_mess_research_20261014/UNIFIED_NATIVE_RUNTIME_LEDGER.json',
         BASE/'RC01/A1_P1_120/SEPARATE_NATIVE_LEDGER_180.json']
ARM_STAGES={'B0':[],'B1':['A1'],'B2':['M1'],'B3':['A1','M1','A2','M2']}


def adapters():
    names=['table_v_run.py','table_v_a.py','table_v_budget.py','table_v_mess.py','table_v_k48.py',
           'table_v_flex_planning.py','table_v_reference.py','tablev_actual.py']
    return [file_record(Path(__file__).with_name(n)) for n in names]


def verify_adapters(output):
    freeze=json.loads((Path(output)/'EXECUTION_SOURCE_FREEZE.json').read_text(encoding='utf8'))
    if (freeze['source_sha']!=digest(freeze['files'])
            or any(file_record(r['path'])!=r for r in freeze['files'])):
        raise ValueError('TABLE_V_EXECUTED_ADAPTER_BYTES_DRIFT')
    return freeze


def prepare(output=DEFAULT):
    from .release_date_case import compile_date_case
    from .table_v_flex_planning import compile_table_v_flex_context
    from .table_v_reference import make_reference
    output=Path(output)
    if output.exists():raise FileExistsError('TABLE_V_EXECUTION_ROOT_ALREADY_EXISTS')
    output.mkdir(parents=True)
    began=perf_counter()
    basic=compile_date_case('2025-05-01',output=output/'INPUTS/BASIC',call_cap=5400.)
    context=compile_table_v_flex_context(basic,output=output/'INPUTS/FULL_FLEX',call_cap=5400.)
    reference=make_reference(context,output=output/'REFERENCE')
    # Reference producer returns (result, acceptance); there is one common pair.
    if isinstance(reference,tuple):ref,receipt=reference
    else:ref,receipt=reference['result'],reference['acceptance']
    _write(output/'REFERENCE_RESULT.json',ref);_write(output/'REFERENCE_ACCEPTANCE.json',receipt)
    state=context['state'];manifest=context['manifest']
    common=dict(schema='MAY01_COMMON_INITIAL_STATE_CERTIFICATE_V1',day='2025-05-01',
        initial_state_sha=state['common_initial_state_sha'],initial_source=manifest['initial_record'],
        RUNNING_UIDs=len(state['running']),RUNNING_GPU=sum(r['gpu'] for r in state['running']),
        PENDING_UIDs=len(state['pending']),Known_UIDs=len(state['running'])+len(state['pending']),
        AIDC_count=len(state['capacities']),GPU_capacity=sum(state['capacities'].values()),
        capacities=state['capacities'],all_arms_same_initial=True,future_Unknown_UIDs_planning_used=False,
        prefix_hours=0,source_identity=manifest['identity'],source_sha=manifest['source_sha'])
    if (common['RUNNING_UIDs'],common['RUNNING_GPU'],common['PENDING_UIDs'],common['Known_UIDs'],common['AIDC_count'],common['GPU_capacity'])!=(324,472,1300,1624,12,780):
        raise ValueError('TABLE_V_APPROVED_COMMON_INITIAL_ROSTER_DRIFT')
    _write(output/'MAY01_COMMON_INITIAL_STATE_CERTIFICATE.json',common)
    _write(output/'MAY01_FLEXIBILITY_POLICY_FREEZE.json',context['tablev_flex'])
    contract=dict(schema='MAY01_TABLE_V_FOUR_ARM_CONTRACT_V1',day='2025-05-01',
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
    _write(output/'MAY01_TABLE_V_FOUR_ARM_CONTRACT.json',contract)
    for kind,caps,name in [('PLANNING_NATIVE',MAIN_CAPS,'PLANNING'),('K48_SEPARATE',K48_CAPS,'K48')]:
        auth=dict(schema=SCHEMA,approved=True,budget_kind=kind,stage_caps_seconds=caps,
            total_limit_seconds=None,total_limit_enabled=False,
            timeout_basis='CUMULATIVE_GUROBI_NATIVE_OPTIMIZE_PER_ARM_STAGE',P2_calls=0,Worker=1,Threads=1,
            authorization_id='USER_TABLE_V_MAY01_STAGE_ONLY_'+name+'_'+output.name,
            authorized_ledger_path=str((output/(name+'_NATIVE_LEDGER.json')).resolve()),
            human_approval_reference=dict(latest_user_reply='총량 제한 폐지, Stage Timeout만 적용',
                stage_limits='B1 A1/B3 A1/A2 5400 sec each; B2 M1/B3 M1/M2 1800 sec each',
                K48='Table V attachment prior explicit K48 300 sec per M stage; separate ledger; no extra grant'),
            source_cases=[dict(day='2025-05-01',source_sha=manifest['source_sha'],source_identity=manifest['identity'])])
        _write(output/(name+'_AUTHORIZATION.json'),auth)
        TableVStageBudget(auth['authorized_ledger_path'],authorization=auth,historical_ledgers=HISTORY)
    files=adapters()+[file_record(ROOT/'tools/run_v42_table_v.py')]
    _write(output/'EXECUTION_SOURCE_FREEZE.json',dict(files=files,source_sha=digest(files)))
    return context


def load_context(output=DEFAULT):
    from .release_date_case import load_date_case
    from .table_v_flex_planning import compile_table_v_flex_context
    output=Path(output);verify_adapters(output)
    basic=load_date_case('2025-05-01',output/'INPUTS/BASIC',call_cap=5400.)
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


def run_arm(arm,output=DEFAULT,*,attempt=None):
    """Every arm commits its own exact outcome even when a stage fails."""
    from .table_v_a import execute_current_a
    from .table_v_mess import TableVMessStages
    from .tablev_actual import run_tablev_actual,run_tablev_fresh
    from .release_ac_contract import CONTRACT
    output=Path(output);arm_folder=output/arm
    if attempt is not None and (not attempt.startswith('ATTEMPT') or not attempt.replace('_','').isalnum()):
        raise ValueError('EXPLICIT_APPEND_ONLY_ATTEMPT_NAME_REQUIRED')
    folder=arm_folder if attempt is None else arm_folder/attempt
    if folder.exists():raise FileExistsError('TABLE_V_ARM_ATTEMPT_ALREADY_EXISTS')
    folder.mkdir(parents=True)
    if attempt is not None:
        _write(arm_folder/'LATEST_ATTEMPT.json',dict(path=str(folder.resolve()),name=attempt,
            prior_attempts_preserved=True,Native_budget_reset=False))
    began=perf_counter();current='PUBLIC_INPUT_RECHECK';stages={};outcome={}
    stop=threading.Event();resource_rows=[]
    def monitor():
        import psutil
        process=psutil.Process()
        while not stop.is_set():
            try:
                memory=process.memory_info()
                resource_rows.append(dict(elapsed_seconds=perf_counter()-began,stage=current,
                    RSS_bytes=memory.rss,private_bytes=getattr(memory,'private',None),
                    system_available_bytes=psutil.virtual_memory().available))
            except Exception:pass
            stop.wait(1.)
    observer=threading.Thread(target=monitor,daemon=True);observer.start()
    def progress(value):
        _write(folder/'LIVE_PROGRESS.json',dict(arm=arm,stage=current,elapsed_wall_seconds=perf_counter()-began,progress=value))
    try:
        context=load_context(output)
        ref=json.loads((output/'REFERENCE_RESULT.json').read_text(encoding='utf8'))
        ref_accept=json.loads((output/'REFERENCE_ACCEPTANCE.json').read_text(encoding='utf8'))
        main=budget(output,'PLANNING');k48=budget(output,'K48');factory=TableVMessStages(context,main)
        aidc,aa=ref,ref_accept;mr=ma=None
        for current in ARM_STAGES[arm]:
            verify_adapters(output);progress('STARTED')
            if current.startswith('A'):
                aidc,aa=execute_current_a(context,main,arm=arm,stage=current,output=folder/current,
                    parent_result=mr,parent_acceptance=ma,progress=progress,
                    reuse_a1=output/'B1/A1' if arm=='B3' and current=='A1' and (output/'B1/A1/P1_ONLY_ACCEPTANCE.json').is_file() else None)
                stages[current]=dict(result=aidc,acceptance=aa)
                if aa is None:raise RuntimeError('A_STAGE_HAS_NO_ORIGINAL_FULL_FEASIBLE_POINT')
            else:
                admission=dict(status='PASS',arm=arm,stage=current,operation='CURRENT_M_NATIVE0_BUILD',
                    concurrent_heavy_solver=False,supervisor_serial_window=True)
                case=factory.prepare(arm,current,aidc,aa,folder/current,build_admission=admission,progress=progress)
                main.bind_table_v_case(arm=arm,stage=current,stage_case_sha=case.case_sha,
                    source_sha=context['manifest']['source_sha'],parent_result=aidc,
                    source_identity=context['manifest']['identity'],parent_acceptance=aa)
                mr,ma,point=factory.execute(arm,current,case,aidc,aa,stage_total_cap=1800.)
                stages[current]=dict(result=mr,acceptance=ma)
                if ma is None:raise RuntimeError('M_STAGE_HAS_NO_ORIGINAL_FULL_FEASIBLE_POINT')
                try:
                    kval=factory.execute_k48(arm,current,case,mr,ma,point,k48_budget=k48,output=folder/(current+'_K48'),
                        build_admission=dict(status='PASS',arm=arm,stage=current,operation='CURRENT_K48_NATIVE_BUILD',
                            concurrent_heavy_solver=False,supervisor_serial_window=True))
                    stages[current]['K48']=kval
                except Exception as exc:
                    stages[current]['K48']=dict(status='NOT_CERTIFIED',error=repr(exc),
                        traceback=traceback.format_exc(),physical_FULL_handoff_still_allowed=True)
                del case,point;gc.collect()
            _write(folder/'PLANNING_STAGE_RESULTS.json',stages)
        current='ACTUAL96';progress('STARTED')
        actual_runner=run_tablev_actual
        kwargs=dict(context=context,arm=arm,reference_result=ref,reference_acceptance=ref_accept,
            output=folder/'ACTUAL96',m_result=mr,m_acceptance=ma,
            gate=dict(Gate_contract=CONTRACT,official_contract_authorized=True),slots=96)
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
        current='FRESH_AC96';progress('STARTED')
        fresh=run_tablev_fresh(context=context,actual_result=actual,output=folder/'FRESH_AC96',
            m_result=mr,m_acceptance=ma,slots=96)
        _write(folder/'FRESH_AC_RESULT.json',fresh)
        outcome=dict(status='FULL_PASS' if actual['status']=='FULL_PASS' and fresh['status']=='FULL_PASS' else 'PHYSICAL_OR_ACTUAL_FAIL',
            actual=actual,fresh=fresh,completed_planning_stages=list(stages))
    except Exception as exc:
        outcome=dict(status='NOT_CERTIFIED',failed_stage=current,error=repr(exc),traceback=traceback.format_exc(),
            completed_planning_stages=list(stages),physical_PASS_claimed=False)
        _write(folder/'PLANNING_STAGE_RESULTS.json',stages)
    finally:
        stop.set();observer.join(timeout=2.)
        _write(folder/'WALL_RAM_RESOURCE_REPORT.json',dict(samples=resource_rows,
            peak_RSS_bytes=max((r['RSS_bytes'] for r in resource_rows),default=None),
            peak_private_bytes=max((r['private_bytes'] or 0 for r in resource_rows),default=None),
            wall_seconds=perf_counter()-began,Native_seconds_ledger_separate=True,
            model_build_and_forecast_and_Actual_and_AC_included_in_total_wall=True))
        outcome.update(arm=arm,wall_seconds=perf_counter()-began,P2_calls=0,R2='HOLD')
        _write(folder/'ARM_OUTCOME.json',outcome)
    return outcome

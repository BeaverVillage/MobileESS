"""Single-coordinator fail-continue recovery using unchanged Q250/M4 science."""
from pathlib import Path
import argparse
import os
import subprocess
import sys
import time
import traceback
import psutil
from v44.common import ROOT,DOC,read,record,verify,atomic,digest,now
from v44 import q250_m4_v2 as q
from v44.locks import coordinator,exclusive_lock,alive,process_identity

CAMPAIGN=q.CAMPAIGN
OPS=CAMPAIGN/'AUTONOMOUS_RECOVERY'
PERMIT=OPS/'RECOVERY_R020_EXECUTION_PERMIT.json'


def sources():
    return [record(p) for p in sorted(Path(__file__).parent.glob('*.py'))]


def schema_backend_sources():
    from importlib.util import find_spec
    if os.environ.get('DSS_EXTENSIONS_DEBUG')=='1':raise PermissionError('R020_RELEASE_SCHEMA_BACKEND_REQUIRED')
    backend=Path(find_spec('dss_python_backend').origin).parent
    direct=Path(find_spec('opendssdirect').origin).parent
    return [record(p) for p in [backend/'__init__.py',backend/'_dss_capi.pyd',backend/'dss_capi.dll',
        backend/'libklusolvex.dll',backend/'libwinpthread-1.dll',direct/'Properties.py']]


def validate():
    value=q.validate(PERMIT)
    revision=value['autonomous_recovery_overlay']
    verify(revision['sources'])
    verify(revision['schema_backend_sources'])
    verify([revision['handover_guard'],revision['validation']])
    if revision['schema_backend_sources']!=schema_backend_sources():
        raise PermissionError('R020_NATIVE_SCHEMA_BACKEND_IDENTITY_DRIFT')
    if revision['sources']!=sources() or value['autonomous_recovery_policy_sha']!=digest(revision):
        raise PermissionError('IMMUTABLE_RECOVERY_REVISION_DRIFT')
    return value


def make_permit():
    value=q.validate(q.PERMIT)
    revision=dict(policy='V44_AUTONOMOUS_RECOVERY_R020',sources=sources(),schema_backend_sources=schema_backend_sources(),
        handover_guard=record(OPS/'R020_HANDOVER_GUARD.json'),
        validation=record(OPS/'R020_CHANGE_AND_VALIDATION.json'),
        improved_arms=['B0','B1','B3'],Fresh_all_live_measurements=True,
        explicit_A2_checkpoint_resume=dict(day='2025-05-02',arm='B3',parent_attempt='attempt001',
            preserved_M1=True,start_solve=15,native_total_ceiling=5400.,native_clock_reset=False,
            normalization='PRESERVE_EXACT_RESTORED_S14_ARTIFICIAL_WEIGHTS_AND_SIGNS'),
        diagnostic_only_fix='NONFINITE_SOLVER_BOUND_NULL_WITH_EXPLICIT_NONFINITE_TAG',
        source_IO_policy='WINDOWS_READ_ONLY_SHARE_SOURCE_HANDLES_PARENT_NO_DELETE_LOCKS_MAPPED_BYTES_FULL_SHA_RECOMPUTED_ON_EVERY_RECORD_UNKNOWN_PATHS_ORIGINAL_IO_NO_DIGEST_MEMO',
        A1_A2_snapshot_enum_checks='ALL_CURRENT_U1_ROW_SENSES_AND_VTYPES_VECTOR_EQUALITY_SAME_ALLOWED_LABELS_ERRORS_NO_CACHE_OR_TOLERANCE_CHANGE_OTHER_INPUT_TYPES_ORIGINAL_LOOP',
        science_parameters_changed=False,Native_budgets_changed=False,
        legacy_source_IO_ports='V43_AND_PR134_RECORD_SHA_AND_V44_SHA_MAPPED_SOURCE_FULL_REHASH_EACH_CALL_ORIGINAL_ARGUMENTS_KEYS_ORDER_AND_UNKNOWN_MUTABLE_IO',
        exact_clean='EXACT_PLAIN_BUILTIN_FAST_PATH_NUMPY_PATH_SUBCLASS_FALLBACK_ORIGINAL_NONFINITE_ENCODING_AND_JSON_BYTES_UNCHANGED',
        all_stage_observability='REFERENCE_A1_M1_A2_M2_ACTUAL_AND_NESTED_INDEPENDENT_FRESH_WALL_CPU_SOURCE_IO_NATIVE_TIMING_NEW_SEPARATE_JSONL_NO_PROBES_ADDED',
        weather_observation_policy='REJECT_NONFINITE_ROWS_THEN_UNCHANGED_ASOF_MAX_AGE7200',
        weather_raw_modified=False,weather_values_imputed=False,
        initial_running_contract='EXISTING_CONTINUATION_ONLY_FOR_ALL_SOURCE_RUNNING_WITHOUT_NATIVE_WINDOW_NO_NEW_PENDING_STARTS',
        Joint_parameter_lookup='LIVE_APPROVED_M_ONLY_SCOPE_THREADS4_METHOD2_GAP003_WITH_MAY02_ROBUST_BARRIER',
        Actual_wall_budget_seconds=None,
        Actual_wall_policy_basis='V44_CAMPAIGN_STAGE_REQUEST_WALL_BUDGET_NONE_NOT_V43_40_MINUTE_DEFAULT',
        Actual_fresh_context='NEW_INDEPENDENT_NO_PARTIAL_TAP_QUEUE_REUSE',
        A2_cache_binding='ACCEPTED_SAME_DATE_A1_PROOF_AND_BYTE_IDENTICAL_PRODUCER_RELOCATION_ORIGINAL_SEMANTIC_DOMAIN_VERIFIER_TAIL',
        Current_AC_performance='EXACT_PREFIX_HISTORY_AUDIT_REUSE_WITH_LIVE_BOUNDARIES_AND_IMMUTABLE_PHYSICS',
        Historical_audit_guard='FIRST_AND_FINAL_FULL_LIVE_CONTROLS_RATINGS_AND_EXACT_NATIVE_STAMP',
        Historical_audit_identity='ARM_DAY_ISSUE_HARDWARE_SOURCE_SCENARIO_MESS_SITES_FULL_INPUT_PREFIX_EXACT_TAPS_CAPS_QUEUE_TIME_ALL_COMPLEX_VOLTAGES_AND_SOLUTION_COUNTERS',
        Historical_native_state_snapshot_restored=False,
        Historical_audit_cache_max_slots=120,Historical_audit_cache_max_bytes=134217728,
        Historical_low_cost_slots='UNCHANGED_R016_SETTLE_PATH_WHEN_PREVIOUS_CONTROL_CALL_COUNT_LE3',
        performance_scope='B0_B1_B3_DAY_GE_2025_05_03_AFTER_MAY02_B3_ENTIRE_CASE_FINISHES',
        Phase_I_rebuild='STAGE_LOCAL_FULL_INPUT_GUARDED_NATIVE_CLASS_BLOCK_AND_EXACT_PROJECTION_PROOF_REUSE_SINGLE_PASS_COLUMN_AND_UNIT_INDEX_BATCH_GRAPH_LEDGER',
        Phase_I_weights='FREEZE_INITIAL_REFERENCE_POSITIVE_DYADIC_WEIGHTS_AND_SIGNS_THROUGHOUT_PHASE_I_ALL_ORIGINAL_INCLUSION_CHECKS_RETAINED',
        Current_AC_state_reads='EXACT_LIVE_CONSUMED_TAPS_CAPS_QUEUE_TIME_FIELDS',
        SVR_measurement='ONE_FULL_MEASURE_PLUS_EXACT_SAME_STATE_IMMEDIATE_SECOND_READ_REUSE',
        Raw_JSON='BYTE_IDENTICAL_ROW_ENCODING_MEMO_ALL_RAW_FILES_PRESERVED',
        Independent_Fresh='FULL_INDEPENDENT_MEASUREMENTS_LIVE_PROPERTY_READS_PURE_EXPECTED_COPY_NO_HISTORY_OR_BANK_REUSE',
        property_metadata='INHERITED_R016_LIVE_READERS_CURRENT_AND_FRESH_ALL_LIVE_HISTORICAL_CERTIFICATES_ONLY_BETWEEN_FULL_LIVE_SLOT_GUARDS_BACKEND_SHA_PINNED',
        named_equipment_reads='IDENTICAL_NATIVE_NAME_GETTER_CALLS_SKIP_FAILED_PYTHON_INT_CONVERSION',
        Actual_processor_placement='ONE_PHYSICAL_P_CORE_FIRST_OS_CORE_RESERVATION_E_ONLY_IF_P_CORES_UNAVAILABLE_RESTORE_ON_EXIT',
        single_thread_processor_placement='A1_A2_NATIVE1_AND_ALL_ARMS_ACTUAL_FRESH1_P_FIRST_E_ONLY_IF_P_UNAVAILABLE',
        four_thread_processor_placement='FOUR_DISTINCT_PHYSICAL_CORES_P_FIRST_E_ONLY_FOR_UNAVAILABLE_P_CAPACITY_OS_CORE_RESERVATIONS',
        physical_copy='IMMUTABLE_PHYSICAL_EVIDENCE_SHARED_IN_CURRENT_HISTORY_ONLY_OTHER_VALUES_INHERITED_R016_CLONES_INDEPENDENT_FRESH_NO_HISTORY_REUSE',
        Actual_numerical_threads=1,model_build_threads=4,
        model_parallel_scope='INDEPENDENT_COEFFICIENT_ROWS_AND_BLAS_ONLY_NATIVE_CONTEXT_AND_GUROBI_OBJECT_SINGLE_OWNER',
        first_task='NEXT_READY_CASE_ONLY_AFTER_CURRENT_HEALTHY_CASE_NATURAL_COMPLETION',
        later_M_retries='NEW_ATTEMPT_NATIVE0_NO_SEED_OR_CLOCK_INHERITANCE',max_attempts=3,
        user_instruction='Improve Phase I non-native rebuild bottlenecks and automatically apply from May03 onward to B0/B1/B3. Preserve running May02 B3 case and its r019 source, all constraints, tolerances, pricing order and Native budgets. Retain all earlier Actual/Fresh performance improvements.',
        original_permit=record(q.PERMIT))
    value.update(UTC=now(),autonomous_recovery_overlay=revision,autonomous_recovery_policy_sha=digest(revision))
    if PERMIT.exists():raise FileExistsError('IMMUTABLE_RECOVERY_PERMIT_ALREADY_EXISTS')
    atomic(PERMIT,value);validate();return value


def latest(root,day,arm):
    attempts=sorted((Path(root)/day/arm).glob('attempt[0-9][0-9][0-9]'))
    return attempts[-1] if attempts else None


def needs_retry(parent,result):
    if (parent is not None and parent.parent.name=='B3' and parent.parent.parent.name=='2025-05-02'
            and parent.name=='attempt002' and (parent/'A2/RESULT.json').exists()
            and read(parent/'A2/RESULT.json').get('error')=='NameError("name \'folder\' is not defined")'):
        return True
    if (parent is not None and parent.parent.name=='B3' and parent.parent.parent.name=='2025-05-02'
            and parent.name=='attempt001' and (parent/'A2/RESULT.json').exists()
            and read(parent/'A2/RESULT.json').get('error')=="ValueError('PRIOR_WITNESS_FROZEN_ARTIFICIAL_WEIGHT_OR_SIGN_DRIFT')"):
        return True
    if (parent is not None and parent.parent.name=='B3' and int(parent.name[-3:])<3
            and result.get('error')=="ValueError('INCOMPLETE_OR_FAILED_PARENT')"
            and (parent/'A2/RESULT.json').exists()
            and read(parent/'A2/RESULT.json').get('error')=="RuntimeError('A2_REQUIRED_COMPLETE_LOCAL_DOMAIN_REUSE_FAILED')"
            and not (parent/'RECOVERY_R020_APPLIED.json').exists()):
        return True
    if (parent is not None and parent.parent.name in ('B1','B3')
            and int(parent.name[-3:])<3
            and result.get('error')=="RuntimeError('V43_ACTUAL_USER_40_MINUTE_WALL_LIMIT_REACHED')"
            and not (parent/'RECOVERY_R020_APPLIED.json').exists()):
        return True
    # One new revision recovery after a proven common input-adapter cause.
    # Attempt004 is Actual/Fresh only; it does not reset any M Native clock.
    if (parent is not None and parent.parent.name=='B2' and parent.parent.parent.name=='2025-05-03'
            and parent.name=='attempt002' and result.get('error')=="ValueError('ORIGINAL_KNOWN_WINDOW_REQUIRED')"):
        return True
    if parent is None or int(parent.name[-3:])>=3:return False
    # Only a diagnosed error with an implemented fix, or the explicit user stop.
    if 'V43_M_OFFICIAL_STOP_REQUESTED' in result.get('error',''):return True
    if result.get('error') == "ValueError('EXACT_THREADS_BOUNDARY_DRIFT:native_optimize')":
        return not (parent/'RECOVERY_R020_APPLIED.json').exists()
    for name in ('M1','M2'):
        m=parent/name/'RESULT.json'
        if m.exists() and read(m).get('implementation_errors')==[
            "ValueError('Out of range float values are not JSON compliant: -inf')"]:
            return not (parent/'RECOVERY_R020_APPLIED.json').exists()
    return False


def states(root):
    from v44.config import DAYS,ARMS
    result={}
    for day in DAYS:
        for arm in ARMS:
            p=latest(root,day,arm)
            if p is None:state='READY'
            elif not (p/'RESULT.json').exists():
                # An unsealed dead worker is quarantined for a diagnosed new
                # attempt by the Codex heartbeat; never silently inherit state.
                state='BLOCKED'
            else:
                r=read(p/'RESULT.json');state=r['status']
                if needs_retry(p,r):state='READY'
            result[(day,arm)]=state
    return result


def decorate(case,permit):
    extra=[permit['Q250_M4_overlay']['source']]+permit['Q250_M4_overlay']['adapter_sources']+sources()+permit['autonomous_recovery_overlay']['schema_backend_sources']
    rows=list({r['path']:r for r in case['sources']+extra}.values())
    case.update(execution_policy_sha=permit['execution_policy_sha'],operational_overlay=permit['operational_overlay'],
        numerical_overlay=permit['numerical_overlay'],numerical_policy_sha=permit['numerical_policy_sha'],
        Q250_M4_overlay=permit['Q250_M4_overlay'],Q250_M4_policy_sha=permit['Q250_M4_policy_sha'],
        autonomous_recovery_overlay=permit['autonomous_recovery_overlay'],
        autonomous_recovery_policy_sha=permit['autonomous_recovery_policy_sha'],Joint_call_cap_seconds=300.,
        sources=rows,source_sha=digest(rows))
    return case


def worker(request):
    from .finite_bound import install
    from .weather import install as weather_install
    from .initial_running import install as running_install
    from .actual_wall import install as wall_install
    from .a2_cache import install as cache_install
    from .current_ac_performance import install as performance_install
    from .thread_policy import install as thread_install
    from .native_cpu import install as native_cpu_install
    from .source_io import install as source_io_install
    from .snapshot_checks import install as snapshot_install
    from .source_ports import install as source_ports_install
    from .exact_clean import install as clean_install
    from .stage_costs import install as costs_install
    from .phase_rebuild import install as rebuild_install
    from v44.campaign import run_case
    validate();verify(request['sources'])
    from .handover import require_boundary
    guard=require_boundary()
    if Path(request['case_root']).resolve()==Path(guard['protected_case_root']).resolve():
        raise PermissionError('R020_CANNOT_RESTART_OR_OVERWRITE_PROTECTED_B3')
    with source_io_install(request['sources'],Path(request['case_root'])/'R020_SOURCE_IO_PERFORMANCE.json') as source_io,source_ports_install(source_io),clean_install(),q.install(PERMIT),install(),weather_install(Path(request['case_root'])/'WEATHER_OBSERVATION_ADMISSION.json'),running_install(),wall_install(),cache_install(),snapshot_install(),native_cpu_install(),thread_install(),performance_install(),rebuild_install(),costs_install(request,source_io):
        if request.get('a2_checkpoint_parent'):
            from .a2_resume_case import run
            return run(request)
        if request.get('wall_resume_parent'):
            from .wall_resume import run
            return run(request)
        if request.get('actual_resume_parent'):
            from .actual_resume import run
            return run(request)
        return run_case(request)


def run():
    from v44.config import B2_ORDER,MAIN_ORDER,axis
    permit=validate();freeze=read(DOC/'SCIENTIFIC_FREEZE_MANIFEST.json')
    from .handover import require_boundary,activate
    require_boundary()
    base=[r['V44'] for r in freeze['unchanged_source_rows']+freeze['unchanged_support_inputs']]+[
        r['source'] for r in freeze['inherited_external_M_algorithms']]+freeze['adapters']+freeze.get('physics_receipts',[])
    verify(base);data=read(DOC/'SEVEN_DAY_INPUT_MANIFEST.json')
    with coordinator(CAMPAIGN) as lease:
        activate(lease)
        atomic(OPS/'COORDINATOR_START.json',dict(UTC=now(),**process_identity(),permit=record(PERMIT)))
        while not (OPS/'STOP_AUTONOMY.json').exists():
            validate();state=states(CAMPAIGN)
            # Explicit latest instruction has priority over the May02 queue.
            may03=latest(CAMPAIGN,'2025-05-03','B2')
            priority=(may03 is not None and may03.name=='attempt002' and state[('2025-05-03','B2')]=='READY')
            wall_priority=next((key for key in MAIN_ORDER if state.get(key)=='READY'
                and latest(CAMPAIGN,*key) is not None
                and read(latest(CAMPAIGN,*key)/'RESULT.json').get('error')=="RuntimeError('V43_ACTUAL_USER_40_MINUTE_WALL_LIMIT_REACHED')"),None)
            checkpoint_parent=latest(CAMPAIGN,'2025-05-02','B3')
            checkpoint_priority=(state.get(('2025-05-02','B3'))=='READY' and checkpoint_parent is not None and checkpoint_parent.name in ('attempt001','attempt002'))
            target=('2025-05-02','B3') if checkpoint_priority else wall_priority or (('2025-05-03','B2') if priority else next((key for key in (*B2_ORDER,*MAIN_ORDER) if state.get(key)=='READY'),None))
            if target is None:
                atomic(OPS/'TERMINAL_SWEEP.json',dict(UTC=now(),all_cases_terminal=True,
                    all_PASS=all(s=='COMPLETE' for s in state.values()),
                    cases=[dict(day=d,arm=a,status=s) for (d,a),s in state.items()]))
                return
            day,arm=target;parent=latest(CAMPAIGN,day,arm);number=int(parent.name[-3:])+1 if parent else 1
            case_root=CAMPAIGN/day/arm/f'attempt{number:03d}'
            lane='B2' if arm=='B2' else 'MAIN'
            atomic(CAMPAIGN/'PHASE.json',dict(lane=lane,UTC=now()))
            dated=next(r for r in data['days'] if r['day']==day)
            case=decorate(dict(day=day,arm=arm,worker_slot=1,lane=lane,case_root=str(case_root),
                campaign_root=str(CAMPAIGN),lease=lease,sources=base+list(dated['files'].values()),
                scientific_source_sha=freeze['source_sha'],axis=axis(day),execution_permit=record(PERMIT)),permit)
            if priority:case['actual_resume_parent']=str(parent)
            if wall_priority and not checkpoint_priority:case['wall_resume_parent']=str(parent)
            if checkpoint_priority:
                from .a2_continue import ADMISSION
                proof=read(ADMISSION);case['a2_checkpoint_parent']=proof['parent']
                checkpoint_original=Path(proof['parent'])
                extra=proof['sources']+[proof['checkpoint'],proof['parent_request'],record(ADMISSION),
                    record(checkpoint_original/'M1/RESULT.json'),record(checkpoint_original/'M1/COMPLETED_STAGE_CHECKPOINT.json')]
                case['sources']=list({row['path']:row for row in case['sources']+extra}.values())
                case['source_sha']=digest(case['sources'])
            verify(case['sources'])
            pointer=OPS/'requests'/f'{day}_{arm}_attempt{number:03d}.json';atomic(pointer,case)
            old=CAMPAIGN/'requests'/f'{day}_{arm}.json'
            if old.exists():
                archived=OPS/'request_history'/f'{day}_{arm}_before_attempt{number:03d}.json'
                if not archived.exists():atomic(archived,read(old))
            atomic(old,case)
            if arm=='B3' and not (CAMPAIGN/'B1_A1'/f'{day}.json').exists():
                case_root.mkdir(parents=True,exist_ok=False)
                atomic(case_root/'RESULT.json',dict(day=day,arm=arm,PASS=False,status='BLOCKED_DEPENDENCY',
                    reason='SAME_DATE_B1_A1_UNAVAILABLE',finished_UTC=now()))
                continue
            log=OPS/'launcher_logs';log.mkdir(parents=True,exist_ok=True)
            with (log/(pointer.stem+'.out.log')).open('ab') as out,(log/(pointer.stem+'.err.log')).open('ab') as err:
                env=dict(os.environ,PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',NUMEXPR_NUM_THREADS='1')
                proc=subprocess.Popen([sys.executable,'-u','-m','v44_recovery_r020.operations','--worker',str(pointer)],
                    cwd=ROOT,env=env,stdout=out,stderr=err,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            while True:
                state=states(CAMPAIGN);state[target]='RUNNING'
                atomic(CAMPAIGN/'CAMPAIGN_STATUS.json',dict(UTC=now(),cases=[dict(day=d,arm=a,status=s) for (d,a),s in state.items()],
                    workers=[dict(pid=proc.pid,day=day,arm=arm,worker_slot=1)]))
                if proc.poll() is not None:break
                time.sleep(1.)
            atomic(case_root.with_suffix('.PROCESS_EXIT.json'),dict(UTC=now(),exit_code=proc.returncode))
            if not (case_root/'RESULT.json').exists():
                atomic(case_root/'RESULT.json',dict(day=day,arm=arm,status='FAILED',PASS=False,
                    error='WORKER_EXIT_WITHOUT_RESULT',exit_code=proc.returncode,finished_UTC=now()))
            atomic(case_root/'RECOVERY_R020_APPLIED.json',dict(UTC=now(),permit=record(PERMIT),
                new_M_Native_clocks_from_zero=not priority and not wall_priority and not checkpoint_priority,prior_M_UB_LB_seed_inherited=False,
                A2_checkpoint_resumed=checkpoint_priority,M1_preserved_from_parent=checkpoint_priority,
                Actual_context='NEW_INDEPENDENT',original_parent=str(parent) if parent else None))
            state=states(CAMPAIGN)
            atomic(CAMPAIGN/'CAMPAIGN_STATUS.json',dict(UTC=now(),cases=[dict(day=d,arm=a,status=s) for (d,a),s in state.items()],workers=[]))
            if checkpoint_priority and not read(case_root/'RESULT.json').get('PASS'):
                a2_result=read(case_root/'A2/RESULT.json') if (case_root/'A2/RESULT.json').exists() else {}
                error=read(case_root/'RESULT.json').get('error','')
                if (a2_result.get('classification')=='IMPLEMENTATION_FAILURE'
                        or any(name in error for name in ('PermissionError','KeyError','FileNotFoundError','TypeError','AttributeError','WORKER_EXIT_WITHOUT_RESULT'))):
                    atomic(OPS/'STOP_AUTONOMY.json',dict(UTC=now(),user_stop=False,
                        reason='R020_A2_CONTINUATION_TECHNICAL_ERROR_HOLD',
                        failed_case=str(case_root),error=error,policy='PRESERVE_ALL_ACCOUNTING_AND_DIAGNOSE_NO_DUPLICATE_RETRY'))
                    return


def workers():
    found=[]
    for p in psutil.process_iter(['pid','name','cmdline','create_time']):
        try:
            cmd=' '.join(p.info['cmdline'] or [])
            if p.info['name'].lower() in ('python.exe','pythonw.exe') and '--worker' in cmd and (
                    'v44.q250_m4_v2' in cmd or 'v44_recovery_' in cmd):found.append(p.info)
        except (psutil.Error,AttributeError):pass
    return found


def watchdog():
    # Independent of Codex lifetime. It never terminates or suspends a Solver.
    with exclusive_lock(OPS/'SUPERVISOR.lock'):
        while not (OPS/'STOP_AUTONOMY.json').exists():
            try:
                lease=read(CAMPAIGN/'COORDINATOR_LEASE.json');live=alive(lease);active=workers()
                atomic(OPS/'SUPERVISOR_HEARTBEAT.json',dict(UTC=now(),**process_identity(),
                    coordinator_alive=live,workers=active,stalled_solver_killed=False))
                if not live and not active and not (OPS/'TERMINAL_SWEEP.json').exists():
                    validate()
                    log=OPS/'supervisor_coordinator.log'
                    with log.open('ab') as stream:
                        proc=subprocess.Popen([sys.executable,'-u','-m','v44_recovery_r020.operations','--coordinator'],
                            cwd=ROOT,stdout=stream,stderr=stream,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                    atomic(OPS/'SUPERVISOR_RESTART.json',dict(UTC=now(),pid=proc.pid,previous_lease=lease))
            except Exception as error:
                atomic(OPS/'SUPERVISOR_ERROR.json',dict(UTC=now(),error=repr(error),traceback=traceback.format_exc()))
            time.sleep(30.)


def main():
    p=argparse.ArgumentParser();p.add_argument('--worker',type=Path);p.add_argument('--coordinator',action='store_true')
    p.add_argument('--watchdog',action='store_true');p.add_argument('--make-permit',action='store_true')
    p.add_argument('--handover',action='store_true');a=p.parse_args()
    if a.make_permit:make_permit()
    elif a.worker:worker(read(a.worker))
    elif a.coordinator:run()
    elif a.watchdog:watchdog()
    elif a.handover:
        from .handover import run as handover
        handover()
    else:raise PermissionError('EXPLICIT_RECOVERY_MODE_REQUIRED')


if __name__=='__main__':main()

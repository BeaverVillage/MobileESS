"""Bounded B1 research only: fresh A1 attempt, then explicitly separate diagnostic."""
from copy import deepcopy
from pathlib import Path
from time import perf_counter
from types import SimpleNamespace
import argparse, hashlib, json, math, os, subprocess, sys, time
import numpy as np
import psutil

from .partial_canary import SOURCE_DIR, OLD_INTEGRATION_LEDGER, OLD_B2_LEDGER, source_known_records, resource_snapshot, coverage_estimate
from .production_case import build_integration_case, read, ARCHIVE, TIMING
from .experimental_planning import bind_experimental_planning
from .experimental_actual import prepare_conditional_arguments
from .known_commands import compile_known_commands
from .sensitivity_policy import build_grid_packet
from .mess_actual import consume_frozen_mess
from .m_engine import _write, file_record
from .policy import digest
from .trajectory_tracking import TrackingReference, TrajectoryTrackingPolicy, TrackingJobEventController
from .actual import run_actual

ROOT=Path(__file__).resolve().parents[1]
HISTORICAL_A1=Path('D:/v42_integration_validation_20261013/DDAY_V5_B3_FINAL_ATTEMPT01/B3/A1/A_RESULT.json')
PREVIOUS=ROOT/'docs/v42_may01_b1_partial_canary_20261014/RUN_ATTEMPT02'


def prepare(output):
    """Original lazy descriptors, Full96 gate and Issue Known only binding."""
    began=perf_counter()
    initial=SOURCE_DIR/'V42_MAY01_DDAY_INITIAL_STATE_FREEZE.json'
    strict=SOURCE_DIR/'QOS_EMPIRICAL_STATS_STRICT.json'
    case=build_integration_case(source_freeze=read(SOURCE_DIR/'SOURCE_FREEZE_DDAY_GRID_V5.json'),
        strict_stats=strict,output=output/'CASE',a_call_cap=297,initial_state_freeze=initial)
    from .coordinator import _require_actual_gate
    _require_actual_gate(case,case.planning_slot_zero_seconds+21600)
    original=case.qos_provider
    native=read(ARCHIVE/'raw/2025-05-01/NATIVE_INPUT_TEMPLATE_B1.json')
    records=source_known_records(original,native)
    bind_experimental_planning(case,records,scenario='E1',participation='FLEX30')
    a_case=case.make_a_case('B1','A1',case.initial_mess,output/'A1')
    if len(records)!=1649 or len(a_case.data[1])!=1499:raise ValueError('SOURCE_KNOWN_ROSTER_DRIFT')
    if len(a_case.data[3].capacities)!=12 or sum(a_case.data[3].capacities.values())!=780:raise ValueError('SOURCE_CAPACITY_DRIFT')
    _write(output/'PREPARATION_RECEIPT.json',dict(case_sha=case.case_sha,science_sha=case.science_sha,
        wall_seconds=perf_counter()-began,Known_issue_UIDs=len(records),Known_native_UIDs=len(a_case.data[1]),
        Planning_slots=96,Actual_slots=16,Future_Unknown_UID_in_Planning=0,
        MESS_OFF=True,common_initial_state_sha=case.actual_gate['common_initial_state_sha']))
    return case,a_case,records,original


def a1_attempt(output):
    from .budget import IntegrationBudget
    from .a_engine import optimize_aidc
    output.mkdir(parents=True,exist_ok=True)
    budget=IntegrationBudget(output/'NEW_A1_NATIVE_LEDGER.json',limit=300)
    case,a_case,_,_=prepare(output)
    _write(output/'A1_STAGE.json',dict(stage='ORIGINAL_FULL_MODEL_BUILD_AND_NATIVE',case_sha=case.case_sha))
    result=optimize_aidc(a_case,case.initial_mess,case.qos_provider,budget)
    _write(output/'A1_ATTEMPT_COMPLETION.json',dict(FULL_feasible=result.get('FULL_feasible'),
        case_sha=case.case_sha,Native_Runtime=budget.document['Gurobi_Native_seconds'],P2_certified=result.get('P2_contract_certified',False)))


def reference_from_anchor(case,a_case,records,anchor,output):
    """Historical A1 used literally; independent 96-slot physical audit only.

    This is not a new-case full MILP replay or a new E1 P1/P2 certificate.
    """
    grid=a_case.grid;bundle,jobs,_,hardware,*_=a_case.data
    sites=tuple(sorted(hardware.capacities))
    known=np.array([anchor['known_site_GPU'][s] for s in sites],float).T
    unknown=np.array([anchor['nominal_site_GPU'][s] for s in sites],float).T
    p=np.array([anchor['AIDC_P_by_site'][s] for s in sites],float).T
    q=np.array([anchor['AIDC_Q_by_site'][s] for s in sites],float).T
    total=known+unknown
    it=grid.idle_kw*np.array([hardware.capacities[s] for s in sites])+grid.swing_kw*total
    rebuilt=np.array([[grid.power[s,t].slope*it[t,j]+grid.power[s,t].intercept_kw
                        for j,s in enumerate(sites)] for t in range(96)])
    if not np.allclose(p,rebuilt,rtol=0,atol=1e-7) or not np.allclose(q,p*np.tan(np.arccos(.95)),rtol=0,atol=1e-7):
        raise ValueError('HISTORICAL_REFERENCE_C1_PQ_DRIFT')
    if set(anchor['selected_jobs'])!=set(jobs):raise ValueError('HISTORICAL_KNOWN_ROSTER_DRIFT')
    # Independently reconstruct continuous Known service, without Actual bank.
    reconstructed=np.zeros_like(known)
    for uid,option in anchor['selected_jobs'].items():
        for site,a,b in option['segments']:
            for t in range(max(24,int(a)),min(120,int(b))):
                reconstructed[t-24,sites.index(site)]+=jobs[uid].gpu
    if not np.allclose(known,reconstructed,rtol=0,atol=1e-7):raise ValueError('HISTORICAL_KNOWN_SERVICE_INTEGRAL_DRIFT')
    import pandas as pd
    from .cc4_policy_inputs import load_frozen_cc4
    from .production_case import KERNEL
    cc4=load_frozen_cc4('D:/MobileESS_V42/docs/v42_may_b0_zero_margin_holdout/MAY_CC4_BINDING.json',
        'D:/MobileESS_V42/docs/v42_may_b0_zero_margin_holdout/CC4/DAY_20250501.json',kernel_path=KERNEL,
        runtime_integrity_path=ROOT/'v42_final/runtime_bundle/INTEGRITY.json',
        planning_bundle_path=ARCHIVE/'raw/2025-05-01/NATIVE_INPUT_TEMPLATE_B1.json')
    responses=sorted({c.coefficient_sha256 for c in grid.coefficients})
    bindings=dict(science_sha=case.science_sha,qos_sha=case.qos_provider.stats.sha,case_sha=case.case_sha,
        aidc_anchor=anchor['aidc_anchor'],mess_anchor=case.initial_mess['plan_sha'],cc4_sha=cc4['prediction_sha'],
        runtime_sha=cc4['runtime_sha'],response_sha=responses[0] if len(responses)==1 else digest(responses),
        initial_state_sha=case.actual_gate['common_initial_state_sha'])
    packet=build_grid_packet(grid.coefficients,grid.power,grid.swing_kw,hardware.capacities,anchor,case.initial_mess,
        grid.authority,bindings,begin_seconds=case.planning_slot_zero_seconds+21600,known_gpu=known,
        mess_validation=consume_frozen_mess(case.initial_mess,day_begin_seconds=case.planning_slot_zero_seconds+21600,evidence_kind='REAL_DATA'),
        rack_compatibility=hardware.rack_limits)
    peaks=[];violations=[]
    for t in range(96):
        peak,bad=packet._at_slot(t,np.zeros(len(sites)));peaks.append(peak);violations.extend(bad)
    commands=compile_known_commands(anchor['selected_jobs'],slot_zero_seconds=case.planning_slot_zero_seconds,
        migration_authority=case.experimental_migration_authority,gpu_by_uid={u:j.gpu for u,j in records.items()})
    identity=dict(bindings,Source_SHA=case.source_freeze['source_sha'],Case_SHA=case.case_sha,
        original_anchor_case_sha=anchor['case_sha'],A1_Anchor_SHA=anchor['aidc_anchor'],
        source_A1_artifact=file_record(HISTORICAL_A1),CC4_SHA=cc4['prediction_sha'],Runtime_Provider_SHA=cc4['runtime_sha'],
        C1_Power_Model_SHA=case.actual_arguments['power_model'].authority_sha,
        Signed_Grid_Authority_SHA=digest(packet.authority),Known_commands_SHA=digest(commands),
        lineage='HISTORICAL_SOURCE18R_V5_A1_DIAGNOSTIC_NOT_NEW_E1_OPTIMUM',
        new_A1_status='NEW_A1_NOT_CERTIFIED',new_E1_FULL_MILP_replay=False,
        independent_96_slot_C1_PQ_GPU_service_PASS=True,independent_96_slot_affine_PASS=not violations,
        independent_96_slot_affine_rho=max(peaks),independent_96_slot_affine_violations=violations,
        source_A1_original_FULL_feasible=anchor['FULL_feasible'],P2_certified=False,
        CC4_service=anchor['CC4_service'],CC4_carryout=anchor['CC4_carryout'],
        CC4_Q50=cc4['q50_hourly_GPUh'],CC4_Q90=cc4['q90_hourly_GPUh'],
        Timing_CDF_Q10=pd.read_csv(TIMING).Q10.tolist(),Timing_CDF_Q90=pd.read_csv(TIMING).Q90.tolist(),
        Timing_CDF_SHA=file_record(TIMING)['sha256'],Nominal_Unknown_GPUh=float(unknown.sum()/4),
        future_Actual_UIDs_or_completion_used=False)
    reference=TrackingReference(known,unknown,it,p,q,sites=sites,begin=packet.begin_seconds,commands=commands,identity=identity)
    reference.save(output/'DAYAHEAD_TRACKING_REFERENCE.npz')
    _write(output/'PLANNING_TARGET_IDENTITY.json',dict(identity,Tracking_Target_SHA=reference.sha))
    _write(output/'DAYAHEAD_TRACKING_REFERENCE_SHA.json',dict(target_sha=reference.sha,
        npz=file_record(output/'DAYAHEAD_TRACKING_REFERENCE.npz'),Known_commands_SHA=digest(commands),bindings=bindings))
    _write(output/'KNOWN_FROZEN_COMMANDS.json',commands)
    return reference,packet,cc4


def run(output,*,a1_wall=600,prior_a1=None,prior_wall=0):
    output.mkdir(parents=True,exist_ok=True);began=perf_counter()
    if (output/'SOLVER_AND_CONTROLLER_RUNTIME_LEDGER.json').exists():raise RuntimeError('NO_AUTOMATIC_ATTEMPT_REUSE')
    pre=resource_snapshot();memory=pre['memory']
    permitted={os.getpid(),int(os.environ.get('V42_TRACKING_WATCH_PID','0'))}
    others=[p for p in pre['workers'] if p['ProcessId'] not in permitted
        and not str(p.get('CommandLine','')).endswith('MONITOR_ADAPTER.py serve')]
    if others:raise RuntimeError('EXTERNAL_HEAVY_WORKER_PRESENT')
    old=[file_record(p) for p in (OLD_INTEGRATION_LEDGER,OLD_B2_LEDGER)]
    if read(OLD_INTEGRATION_LEDGER)['inflight'] or read(OLD_B2_LEDGER)['inflight']:raise RuntimeError('OLD_NATIVE_CALL_INFLIGHT')
    runtime=dict(wall_limit_seconds=1200,Native_limit_seconds=300,Threads=1,Worker=1,
        attribution='NEW_TRACKING_RESEARCH_ONE_ATTEMPT;HISTORICAL_LEDGERS_READ_ONLY',
        old_ledgers_before=old,previous_645_second_canary=file_record(PREVIOUS/'WATCHDOG_RECEIPT.json'),
        previous_attempt_merged=False,Native_global_optimize_Actual_calls=0,
        A1_attempt_status='STARTED',Full96_Actual=False,Fresh_AC_calls=0,replay_wall_seconds={},
        prior_execution_wall_seconds=prior_wall,remaining_wall_seconds=1200-prior_wall)
    _write(output/'SOLVER_AND_CONTROLLER_RUNTIME_LEDGER.json',runtime)
    attempt=Path(prior_a1) if prior_a1 is not None else output/'NEW_A1_ATTEMPT'
    if prior_a1 is None:
        attempt.mkdir()
        with (attempt/'STDOUT.log').open('w',encoding='utf8') as out,(attempt/'STDERR.log').open('w',encoding='utf8') as err:
            child=subprocess.Popen([sys.executable,'-u','-m','v42_integration.tracking_canary','--a1-only','--output',str(attempt)],
                cwd=ROOT,stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW)
            at=perf_counter();peak=0
            while child.poll() is None and perf_counter()-at<a1_wall:
                try: peak=max(peak,psutil.Process(child.pid).memory_info().rss)
                except psutil.NoSuchProcess:break
                time.sleep(1)
            stopped=child.poll() is None
            if stopped:child.kill()
            code=child.wait()
        attempt_wall=perf_counter()-at
    else:
        stop=read(attempt.parent/'PRE_ACTUAL_CONTRACT_REPAIR_STOP.json')
        if stop['actual_started'] or stop['Native_Optimize_calls']:raise ValueError('PRE_ACTUAL_REPAIR_EVIDENCE_REQUIRED')
        receipt=read(attempt.parent/'WATCHDOG_RECEIPT.json')
        prior_receipts=[attempt.parent/'WATCHDOG_RECEIPT.json']
        prior_receipts += sorted(p for p in attempt.parent.glob('*/WATCHDOG_RECEIPT.json') if p.parent!=output)
        expected_prior=sum(read(p)['wall_seconds'] for p in prior_receipts)
        if not math.isclose(expected_prior,prior_wall,rel_tol=0,abs_tol=1e-9):raise ValueError('CUMULATIVE_RESEARCH_WALL_ATTRIBUTION_DRIFT')
        runtime['prior_watchdog_receipts']=[file_record(p) for p in prior_receipts]
        attempt_wall=stop['A1_elapsed_seconds'];code=receipt['exit_code'];stopped=True
        peak=max(s['RSS_bytes'] for s in receipt['samples'])
        runtime['controller_repair_evidence']=file_record(attempt.parent/'PRE_ACTUAL_CONTRACT_REPAIR_STOP.json')
        runtime['Native_retry_calls']=0
    ledger=read(attempt/'NEW_A1_NATIVE_LEDGER.json')
    runtime.update(A1_attempt_wall_seconds=attempt_wall,A1_attempt_exit=code,A1_model_peak_RSS=peak,
        A1_owned_worker_stopped=stopped,A1_Native_seconds=ledger['Gurobi_Native_seconds'],
        A1_conservative_seconds=ledger['conservative_solve_seconds'],A1_inflight=ledger['inflight'])
    runtime['A1_attempt_status']='NEW_A1_NOT_CERTIFIED'
    _write(output/'SOLVER_AND_CONTROLLER_RUNTIME_LEDGER.json',runtime)
    if ledger['inflight']:
        # No further native call. Preserve the interrupted ledger literally;
        # upper-bound its unclosed call conservatively in this research report.
        runtime['A1_unclosed_native_conservative_cap_seconds']=300
    case,a_case,records,strict=prepare(output/'DIAGNOSTIC_SETUP')
    attempted_case=read(attempt/'PREPARATION_RECEIPT.json')['case_sha']
    if prior_a1 is None and attempted_case!=case.case_sha:raise ValueError('A1_DIAGNOSTIC_CURRENT_CASE_DRIFT')
    runtime['A1_attempted_case_SHA']=attempted_case
    runtime['post_repair_diagnostic_case_SHA']=case.case_sha
    runtime['attempted_A1_case_promoted_to_new_policy_case']=False
    anchor=read(HISTORICAL_A1)
    fresh=attempt/'A1/A_RESULT.json'
    if fresh.exists() and read(fresh).get('FULL_feasible'):
        # A fresh full-feasible result still needs the full P2/source replay
        # certification; never promote an uncertified point automatically.
        runtime['fresh_FULL_feasible_uncertified_artifact']=file_record(fresh)
    at=perf_counter();reference,packet,cc4=reference_from_anchor(case,a_case,records,anchor,output)
    runtime['reference_build_wall_seconds']=perf_counter()-at
    runtime['C1_compile']=dict(status='NOT_RUN',reason='FULL_DOMAIN_ESTIMATE_EXCEEDS_BOUNDED_RESOURCES',
        Source_only_estimate=coverage_estimate(packet.capacities,packet.rack_compatibility),
        literal_templates=None,partial_fixture_not_claimed_as_actual=True,wall_seconds=0)
    variants=[('C0',dict(basic=True)),('C2',dict()),('C3',dict(preplace=False))]
    specs={label:TrajectoryTrackingPolicy(reference,packet,bindings=packet.bindings,
        migration_authority=case.experimental_migration_authority,**opts).spec for label,opts in variants}
    _write(output/'TRACKING_POLICY_SPEC.json',dict(variants=specs,known_commands_sha=digest(reference.commands),
        target_sha=reference.sha,freeze_before_Actual=True,C1=runtime['C1_compile']))
    manifests=[]
    for label,opts in variants:
        if prior_wall+perf_counter()-began>1100 and label=='C3':runtime['C3_status']='NOT_RUN_WALL_BUDGET';break
        at=perf_counter()
        # New provider, reference, forecast, reservations and queue per run.
        base=deepcopy(dict(case.actual_arguments,qos_window_provider=strict))
        projected=prepare_conditional_arguments(base,records,scenario='E1',participation='FLEX30',case_sha=case.case_sha)
        args=projected['arguments'];args['end']=args['begin']+14400;args['weather']=args['weather'][:16]
        args['requests']=[r for r in args['requests'] if r.submit<args['end']]
        fair=dict(requests=[dict(uid=r.uid,submit=r.submit,gpu=r.gpu,q50=r.q50,metadata=r.metadata) for r in args['requests']],
            running=[dict(uid=r.uid,site=s,start=t,metadata=r.metadata) for r,s,t in args['running']],
            private_environment=vars(args['environment']),known_commands_sha=digest(reference.commands),
            initial_state_sha=case.actual_gate['common_initial_state_sha'],target_sha=reference.sha)
        manifest=digest(fair);manifests.append(manifest)
        policy=TrajectoryTrackingPolicy(reference,packet,bindings=packet.bindings,
            migration_authority=case.experimental_migration_authority,**opts)
        result=run_actual(**args,arm='B1',frozen_policy=policy,known_schedule=reference.commands,
            expected_bindings=packet.bindings,controller_class=TrackingJobEventController)
        result['tracking_canary']=dict(label=label,lineage=reference.identity['lineage'],
            new_A1_status='NEW_A1_NOT_CERTIFIED',Partial_slots=16,Planning_slots=96,Full96_PASS=False,
            controller_global_optimizer_calls=0,input_SHA=manifest,policy_sha=policy.sha,
            Known_schedule_sha=digest(reference.commands),wall_seconds=perf_counter()-at,
            policy_audit=policy.audit,migration_funnel=policy.funnel,decision_seconds=policy.times,
            target_sha=reference.sha,begin=args['begin'],end=args['end'])
        from .tracking_metrics import summarize
        metrics,occupied,compute=summarize(result,reference,packet)
        _write(output/(label+'_METRICS.json'),metrics)
        _write(output/(label+'_RESULT.json'),result)
        np.savez_compressed(output/(label+'_ACTUAL_ARRAYS.npz'),GPU=result['occupancy_GPU'],Compute=result['compute_occupancy_GPU'],
            Known_GPU=occupied['Known'],Unknown_GPU=occupied['Unknown'],
            Known_Compute=compute['Known'],Unknown_Compute=compute['Unknown'],
            **{k:v for k,v in result['physical'].items() if isinstance(v,np.ndarray)})
        runtime['replay_wall_seconds'][label]=perf_counter()-at
        _write(output/'SOLVER_AND_CONTROLLER_RUNTIME_LEDGER.json',runtime)
        print(label+' EXECUTED_PARTIAL_DIAGNOSTIC',flush=True)
    if len(set(manifests))!=1:raise ValueError('COUNTERFACTUAL_INPUT_DRIFT')
    from .coordinator import verify_sources
    verify_sources(case.source_freeze,case.input_receipts)
    for receipt in old:
        if file_record(receipt['path'])['sha256']!=receipt['sha256']:raise ValueError('HISTORICAL_LEDGER_DRIFT')
    runtime.update(wall_seconds=perf_counter()-began,cumulative_execution_wall_seconds=prior_wall+perf_counter()-began,
        old_ledgers_after=[file_record(p) for p in (OLD_INTEGRATION_LEDGER,OLD_B2_LEDGER)],
        same_inputs_PASS=True,status='PARTIAL_DIAGNOSTIC_COMPLETE_NEW_A1_NOT_CERTIFIED',
        process_RSS_end=psutil.Process().memory_info().rss)
    _write(output/'SOLVER_AND_CONTROLLER_RUNTIME_LEDGER.json',runtime)
    _write(output/'SOURCE_CASE_POLICY_SHA_MANIFEST.json',dict(parent_PR228='7f1f92308dc24096933b39dfe0666ee21089612a',
        input_SHA=manifests[0],target_SHA=reference.sha,bindings=packet.bindings,
        source_freeze=file_record(SOURCE_DIR/'SOURCE_FREEZE_DDAY_GRID_V5.json'),
        source_files={p.name:file_record(p) for p in (ROOT/'v42_integration').glob('*.py')},
        historical_anchor=file_record(HISTORICAL_A1),Full96_Actual_PASS=False,Fresh_AC_PASS=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--a1-only',action='store_true');parser.add_argument('--a1-wall',type=float,default=600)
    parser.add_argument('--prior-a1',type=Path);parser.add_argument('--prior-wall',type=float,default=0)
    args=parser.parse_args()
    try:
        if args.a1_only:a1_attempt(args.output)
        else:run(args.output,a1_wall=args.a1_wall,prior_a1=args.prior_a1,prior_wall=args.prior_wall)
    except BaseException as exc:
        import traceback
        _write(args.output/'EXECUTION_FAILURE.json',dict(error=repr(exc),traceback=traceback.format_exc(),
            fail_closed=True,Native_auto_retry=False,Full96_Actual_PASS=False))
        raise

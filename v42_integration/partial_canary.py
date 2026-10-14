"""Isolated May01 B1 Canary; production Full96 coordinator gate is untouched."""
from collections import Counter
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from time import perf_counter
import json
import hashlib
import math
import subprocess
import numpy as np
import psutil

from .policy import digest
from .m_engine import file_record,_write
from .production_case import build_integration_case,read,ARCHIVE
from .experimental_planning import bind_experimental_planning
from .qos import ObservedJob

PARENT='7f1f92308dc24096933b39dfe0666ee21089612a'
SOURCE_DIR=Path('D:/v42_common_am_qos_integration_20261013/docs/v42_common_am_qos_integration')
OLD_INTEGRATION_LEDGER=Path('D:/v42_integration_validation_20261013/INTEGRATION_BUDGET_LEDGER.json')
OLD_B2_LEDGER=Path('D:/v42_b2_global_lb_alternative_20261014/docs/v42_b2_global_lb_alternative_research_20261014/NATIVE_RUNTIME_BUDGET_LEDGER.json')
CORE_FILES=('experimental_planning.py','frozen_unknown.py','known_commands.py','experimental_actual.py',
    'reservation_state.py','coordinator.py','action_metrics.py')


def resource_snapshot():
    code="@{memory=Get-CimInstance Win32_PerfFormattedData_PerfOS_Memory | Select-Object AvailableMBytes,CommittedBytes,CommitLimit,PercentCommittedBytesInUse; workers=@(Get-CimInstance Win32_Process | Where-Object {$_.Name -match 'python|gurobi|dss|worker'} | Select-Object ProcessId,Name,CommandLine)} | ConvertTo-Json -Depth 5 -Compress"
    result=json.loads(subprocess.check_output(['powershell','-NoProfile','-Command',code],text=True,encoding='utf8'))
    result['psutil_available_RAM_bytes']=psutil.virtual_memory().available
    result['CPU_percent']=psutil.cpu_percent(interval=.1)
    return result


def source_known_records(provider,native):
    rows={r['job_uid']:r for r in native['known_population']};out={}
    assert set(rows)==set(provider.receipts)
    for uid,receipt in provider.receipts.items():
        job=ObservedJob(uid=uid,submit_seconds=datetime.fromisoformat(rows[uid]['submit_time'].replace('Z','+00:00')).timestamp(),
            event_seconds=receipt.issued_at_seconds,reference_start_seconds=receipt.reference_start_seconds,
            t50_seconds=receipt.t50_seconds,origin_unknown=False,state=rows[uid]['state'],**receipt.hard_contract)
        if job.authority_sha!=receipt.authority_sha:raise ValueError('ISSUE_KNOWN_RECEIPT_RECONSTRUCTION_DRIFT:'+uid)
        out[uid]=job
    return out


def coverage_estimate(capacities,racks,runtime_buckets=5,time_slots=96):
    largest=int(max(min(capacities[s],max(racks[s])) for s in capacities))
    counts=[sum(g<=capacities[s] and g<=max(racks[s]) for s in capacities) for g in range(1,largest+1)]
    return dict(whole_GPU_gangs=largest,templates=sum(counts)*4*runtime_buckets*time_slots,
        candidate_variants=sum(n*n for n in counts)*10*runtime_buckets*time_slots,
        ranking_and_risk_records_minimum_bytes=sum(n*n for n in counts)*10*runtime_buckets*time_slots*1024,
        Source_only=True,Actual_future_UIDs_read=0)


def preregister_coverage(records,capacities,racks):
    if any(j.origin_unknown for j in records.values()):raise ValueError('NO_ACTUAL_FUTURE_UID_AT_PLANNING')
    frequencies=Counter(j.gpu for j in records.values())
    gang=min(frequencies,key=lambda g:(-frequencies[g],g))
    sites=sorted(s for s in capacities if gang<=capacities[s] and gang<=max(racks[s]))
    conditions=[dict(state=state,qos=qos,gpu=gang,reference_site=source,compatible_sites=sites,
        runtime_lower_seconds=0.,runtime_upper_seconds=900.,time_slots=list(range(16)))
        for state in ('PENDING','RUNNING') for qos in ('normal','standby') for source in sites]
    receipt=dict(status='PARTIAL_POLICY_COVERAGE',selection='MODAL_SOURCE_ISSUE_KNOWN_GANG_TIE_SMALLEST;FIRST_SOURCE_SUPPORTED_900S_BUCKET',
        selected_GPU_gang=gang,issue_known_GPU_histogram=dict(frequencies),runtime_bounds_seconds=[0,900],
        event_slots=list(range(16)),compatible_destinations=sites,Unknown_future_arrival_inspection=False,
        E1_all_delay_options=dict(normal=[0,900,1800],verified_standby=[0,900,1800,2700,3600]),
        unsupported_action='SAFE_ORIGINAL_REFERENCE_WITH_CURRENT_PHYSICAL_GUARD;REASON_LOGGED',
        full_domain_estimate=coverage_estimate(capacities,racks),conditions=conditions,
        compile_wall_cap_seconds=120)
    return conditions,receipt


def prepare_canary(output):
    root=Path(__file__).resolve().parents[1];output=Path(output);output.mkdir(parents=True,exist_ok=True)
    began=perf_counter();resources=resource_snapshot()
    source_path=SOURCE_DIR/'SOURCE_FREEZE_DDAY_GRID_V5.json'
    initial=SOURCE_DIR/'V42_MAY01_DDAY_INITIAL_STATE_FREEZE.json'
    strict=SOURCE_DIR/'QOS_EMPIRICAL_STATS_STRICT.json'
    old_integrated=read(OLD_INTEGRATION_LEDGER);old_b2=read(OLD_B2_LEDGER)
    if old_integrated['inflight'] or old_b2['inflight']:raise RuntimeError('HISTORICAL_NATIVE_CALL_INFLIGHT')
    if old_integrated['conservative_solve_seconds']!=621.2855198158068 or old_b2['effective_cumulative_Native_Runtime']!=1257.5220000743866:
        raise RuntimeError('HISTORICAL_LEDGER_PREFIX_DRIFT')
    receipts=[file_record(p) for p in (OLD_INTEGRATION_LEDGER,OLD_B2_LEDGER,source_path,initial,strict)]
    core={name:file_record(root/'v42_integration'/name) for name in CORE_FILES}
    for name,record in core.items():
        original=subprocess.check_output(['git','show',PARENT+':v42_integration/'+name],cwd=root)
        if hashlib.sha256(original).hexdigest()!=record['sha256']:raise ValueError('PR228_CORE_SOURCE_DRIFT:'+name)
    contract=dict(schema='V42_MAY01_B1_PR228_CANARY_BUDGET_V1',parent=PARENT,arm='B1',day='2025-05-01',
        scenario='E1',participation='FLEX30',Native_ceiling_seconds=300,wall_ceiling_seconds=900,
        policy_compile_ceiling_seconds=120,replay_ceiling_seconds_each=120,Threads=1,Worker=1,
        attribution='EXPLICIT_NEW_B1_RESEARCH_ATTEMPT_AUTHORIZED_BY_CURRENT_USER;OLD_B2_AND_INTEGRATION_LEDGERS_READ_ONLY',
        old_ledger_receipts=receipts[:2],old_ledgers_merged_or_reset=False,
        Native_ledger=str((output/'B1_RESEARCH_NATIVE_LEDGER.json').resolve()),source_files=core)
    contract['canary_runner_source_sha']=file_record(Path(__file__))['sha256']
    contract['contract_sha']=digest(contract)
    _write(output/'BUDGET_ATTRIBUTION_FREEZE.json',contract)
    memory=resources['memory']
    if memory['AvailableMBytes']<8192 or memory['PercentCommittedBytesInUse']>=75:
        raise RuntimeError('PRE_NATIVE_RAM_COMMIT_GATE')
    owned_supervisor=int(__import__('os').environ.get('V42_CANARY_SUPERVISOR_PID','0'))
    external=[r for r in resources['workers'] if r['ProcessId']!=__import__('os').getpid()
        and not (r['ProcessId']==owned_supervisor and 'watch_may01_b1_canary.py' in str(r.get('CommandLine','')))
        and not str(r.get('CommandLine','')).endswith('MONITOR_ADAPTER.py serve')]
    if external:raise RuntimeError('EXTERNAL_PYTHON_OR_NATIVE_WORKER_PRESENT')
    case=build_integration_case(source_freeze=read(source_path),strict_stats=strict,output=output/'CASE',
        a_call_cap=297.,initial_state_freeze=initial)
    from .coordinator import _require_actual_gate
    _require_actual_gate(case,case.planning_slot_zero_seconds+21600)
    original_provider=case.qos_provider
    native=read(ARCHIVE/'raw/2025-05-01/NATIVE_INPUT_TEMPLATE_B1.json')
    records=source_known_records(original_provider,native)
    original_a=case.make_a_case('B1','A1',case.initial_mess,output/'DESCRIPTOR_ONLY')
    bundle,jobs,bounds,hardware,*_=original_a.data
    conditions,coverage=preregister_coverage(records,hardware.capacities,hardware.rack_limits)
    _write(output/'PARTIAL_POLICY_COVERAGE_AUDIT.json',coverage)
    bind_experimental_planning(case,records,scenario='E1',participation='FLEX30',unknown_conditions=conditions)
    a_case=case.make_a_case('B1','A1',case.initial_mess,output/'B1'/'A1')
    # Native0 checks complete declared windows and source physics. Expanding
    # every migration graph twice would consume the bounded Canary in setup.
    # The original producer performs full domain/graph construction once below.
    data=a_case.data
    if len(records)!=1649 or len(data[1])!=1499:raise ValueError('ORIGINAL_KNOWN_ISSUE_DOMAIN_ROSTER_DRIFT')
    if len(hardware.capacities)!=12 or sum(hardware.capacities.values())!=780:raise ValueError('MAY01_12_AIDC_780_GPU_SOURCE_REQUIRED')
    if any(j.unknown_arrival for j in data[1].values()):raise ValueError('UNKNOWN_UID_IN_PLANNING')
    if any(v for f in ('P_by_site','Q_by_site') for r in case.initial_mess[f].values() for v in r):raise ValueError('B1_MESS_NOT_OFF')
    receipt=dict(PASS=True,Native_Optimize_calls=0,case_sha=case.case_sha,science_sha=case.science_sha,
        Known_issue_UID=1649,Known_native_UID=1499,Unknown_future_UIDs_at_Planning=0,
        installed_GPU=sum(hardware.capacities.values()),AIDC_count=len(hardware.capacities),
        original_Full96_gate_preserved=True,Planning_slots=96,Actual_observation_slots=16,
        resources=resources,budget_contract=contract,source_receipts=receipts,
        E1_FLEX30_receipts_SHA=digest(case.qos_provider.to_dict()),
        declared_Known_window_SHA=digest(a_case.window_slots),
        full_graph_and_model_build='DEFERRED_TO_UNMODIFIED_A1_PRODUCER_ONCE',
        Native0_is_not_FULL_model_certificate=True,
        common_initial_state_sha=case.actual_gate['common_initial_state_sha'],
        Target_Gap=.005,P1_P2_source_unchanged=True,wall_seconds=perf_counter()-began)
    _write(output/'NATIVE0_PREFLIGHT.json',receipt)
    _write(output/'SOURCE_CASE_POLICY_MANIFEST.json',dict(parent=PARENT,case_sha=case.case_sha,science_sha=case.science_sha,
        source_files=core,source_receipts=receipts,policy_sha=None,policy_status='NOT_YET_COMPILED',
        common_initial_state_sha=case.actual_gate['common_initial_state_sha'],Partial_Canary=True,Full96_PASS=False))
    return case,a_case,records,original_provider,receipt


def freeze_variant(policy,mode):
    """Planning-only ablation/filter; retain existing scores, never rerank online."""
    from copy import deepcopy
    from .frozen_unknown import FrozenUnknownPolicy
    if mode not in ('REFERENCE_ONLY','FROZEN','NO_PREPLACE'):raise ValueError('PREREGISTERED_CANARY_VARIANT_REQUIRED')
    document=policy.document;document.pop('content_sha',None)
    document['canary_execution_mode']=mode
    document['canary_scope']='PARTIAL_POLICY_16_EVENT_SLOTS_96_SLOT_PLANNING'
    document['unsupported_reference_contract']='ORIGINAL_CAUSAL_REFERENCE;CURRENT_SIGNED_AFFINE_GPU_RACK;PROTECT_OTHER_HARD_BOOKINGS'
    if mode=='NO_PREPLACE':
        for template in document['templates']:
            rows=[r for r in template['ordered_actions'] if r['action']!='PREPLACE']
            for rank,row in enumerate(rows):
                row['parent_R2_rank']=row['frozen_rank'];row['frozen_rank']=rank
                row['alternative_id']=template['template_id']+':R3:'+str(rank)
            template['ordered_actions']=rows
    document['policy_sha']=digest({k:v for k,v in document.items() if k not in ('metrics','policy_sha')})
    result=CanaryFrozenPolicy(dict(document,content_sha=digest(document)))
    result.bind_runtime_packet(policy.packet)
    return result


from .frozen_unknown import FrozenUnknownPolicy
class CanaryFrozenPolicy(FrozenUnknownPolicy):
    """Prespecified safe Source reference for unrepresented conditions only."""
    def _reference(self,metadata,receipt,now,reservations,reason,reserve=True):
        from .policy import _receipt
        r=_receipt(receipt);site=metadata.get('reference_site',metadata.get('source_site'))
        start=math.ceil(max(now,r['reference_start_seconds'],metadata.get('release_seconds') or -math.inf,
            metadata.get('hard_earliest_start_seconds') or -math.inf)/900)*900
        end=start+max(metadata['t50_seconds'],1e-9)
        veto=None
        if site not in metadata['compatible_sites']:veto='REFERENCE_SITE_AUTHORITY_MISSING'
        for field,value in (('hard_latest_start_seconds',start),('completion_deadline_seconds',end)):
            if metadata.get(field) is not None and value>metadata[field]:veto='EMPTY_AUTHORIZED_HARD_WINDOW'
        segments=[dict(resource='gpu:'+site,begin=start,end=end,quantity=metadata['gpu'])]
        if veto is None:veto=self.current_guard(metadata,segments,now,self._current[1])
        if veto is None:veto=reservations.feasible(segments,exclude=metadata['uid'])
        if veto is None and reserve:
            ok,status=reservations.reserve(metadata['uid'],segments,replace=True)
            if not ok:veto=status
        decision=dict(uid=metadata['uid'],action='QUEUE' if veto else 'START',status='SAFE_SOURCE_REFERENCE_PARTIAL_COVERAGE',
            reason=veto or reason,coverage_unsupported_reason=reason,site=site,start_seconds=start,
            nominal_end_seconds=end,segments=segments,rule_id=None,policy_sha=self.sha,
            canary_reference=True,additional_start_delay_seconds=metadata.get('additional_start_delay_seconds',0),
            online_grid_horizon_evaluations=0,online_global_optimizer_calls=0)
        return self._record(metadata,now,decision)

    def select(self,metadata,receipt,now,reservations,*,reserve=True):
        template,reason=self.lookup(metadata,receipt,now)
        if metadata.get('is_observed',True) is not True or metadata['submit_seconds']>now:
            return dict(uid=metadata['uid'],action='QUEUE',status='NOT_YET_SUBMITTED',reason='OBSERVATION_REQUIRED',
                online_grid_horizon_evaluations=0)
        if self._body.get('canary_execution_mode')=='REFERENCE_ONLY' or template is None:
            return self._reference(metadata,receipt,now,reservations,
                'PREREGISTERED_UNKNOWN_REFERENCE_ONLY' if self._body.get('canary_execution_mode')=='REFERENCE_ONLY' else reason,reserve)
        return super().select(metadata,receipt,now,reservations,reserve=reserve)

    def revalidate_command(self,metadata,receipt,now,reservations,decision,observed,*,failure_reason):
        if decision.get('canary_reference') or self._body.get('canary_execution_mode')=='REFERENCE_ONLY':
            self.set_current_resources(now,observed)
            return self._reference(metadata,receipt,now,reservations,decision.get('coverage_unsupported_reason','PREREGISTERED_UNKNOWN_REFERENCE_ONLY'))
        return super().revalidate_command(metadata,receipt,now,reservations,decision,observed,failure_reason=failure_reason)

    def select_migration(self,metadata,receipt,now,reservations,**kwargs):
        if metadata.get('origin_unknown') is not True:raise ValueError('KNOWN_NEVER_ENTERS_UNKNOWN_POLICY')
        if self._body.get('canary_execution_mode')=='REFERENCE_ONLY':
            return self._record(metadata,now,dict(uid=metadata['uid'],action='STAY',status='PREREGISTERED_UNKNOWN_REFERENCE_ONLY',
                reason='UNKNOWN_FLEXIBILITY_DISABLED_R1',online_grid_horizon_evaluations=0))
        return super().select_migration(metadata,receipt,now,reservations,**kwargs)


def classify_a1(result):
    if not result.get('FULL_feasible'):return 'A1_NO_ACCEPTABLE_INCUMBENT',None
    upper=float(result['rho']);lower=float(result.get('local_bound',float('-inf')))
    gap=None if not math.isfinite(lower) else max(0.,upper-lower)/max(abs(upper),1e-10)
    # The reused producer records P2_calls=0. Never certify the original
    # lexicographic contract from a P1-only partial incumbent.
    accepted=(gap is not None and gap<=.005 and result.get('global_gap_certified')
        and result.get('P2_contract_certified') is True)
    return ('ACCEPTED' if accepted else 'PARTIAL_A1_FEASIBLE_NOT_CERTIFIED'),gap


def run_canary(output):
    from .budget import IntegrationBudget
    from .a_engine import optimize_aidc
    from .mess_actual import consume_frozen_mess
    from .coordinator import _full_a,verify_sources
    from .known_commands import compile_known_commands
    from .experimental_actual import prepare_conditional_arguments,run_experimental_actual
    from .action_metrics import unknown_actual_metrics
    output=Path(output);began=perf_counter();state=dict(stage='NATIVE0',wall_cap_seconds=900)
    def stage(name,cap):
        state.update(stage=name,stage_cap_seconds=cap,stage_started_elapsed=perf_counter()-began,
            elapsed_seconds=perf_counter()-began)
        if state['elapsed_seconds']>=900:raise RuntimeError('CANARY_WALL_BUDGET_EXHAUSTED')
        _write(output/'LIVE_STAGE.json',state)
    output.mkdir(parents=True,exist_ok=True)
    stage('NATIVE0',300)
    case,a_case,records,strict,preflight=prepare_canary(output)
    ledger=output/'B1_RESEARCH_NATIVE_LEDGER.json'
    if ledger.exists():raise RuntimeError('RESEARCH_ATTEMPT_ALREADY_STARTED_NO_NATIVE_RETRY')
    budget=IntegrationBudget(ledger,limit=300.)
    native_started=perf_counter();stage('A1_BUILD_AND_NATIVE',min(600,900-state['elapsed_seconds']))
    a1=optimize_aidc(a_case,case.initial_mess,case.qos_provider,budget)
    status,gap=classify_a1(a1)
    receipt=dict(status=status,case_sha=case.case_sha,science_sha=case.science_sha,
        parent_PR228=PARENT,full96_Known_domain=True,Known_native_UIDs=1499,
        Target_Global_Gap=.005,Global_UB=a1.get('rho'),Global_LB=a1.get('local_bound'),Global_Gap=gap,
        P2_calls=a1.get('P2_calls'),P2_certified=False,FULL_feasible=a1.get('FULL_feasible',False),
        Native_Runtime_seconds=budget.document['Gurobi_Native_seconds'],wall_seconds=perf_counter()-native_started,
        Known_Planning=a1.get('Known_planning_metrics'),source_A_RESULT=file_record(a_case.output/'A_RESULT.json'))
    _write(output/'A1_KNOWN_OPTIMIZATION_RECEIPT.json',receipt)
    if status=='A1_NO_ACCEPTABLE_INCUMBENT':
        _write(output/'CANARY_STOP.json',dict(stage='A1',reason=status,auto_retry=False));return
    _full_a(a1);verify_sources(case.source_freeze,case.input_receipts)
    stage('POLICY_COMPILE',120);compile_started=perf_counter()
    folder=output/'B1';folder.mkdir(exist_ok=True)
    bindings=dict(science_sha=case.science_sha,qos_sha=case.qos_provider.stats.sha,case_sha=case.case_sha,
        aidc_anchor=a1['aidc_anchor'],mess_anchor=case.initial_mess['plan_sha'])
    policy=case.control_policy_factory(arm='B1',aidc=a1,mess=case.initial_mess,bindings=bindings,
        envelope=a1['anonymous_resource_envelope'],output=folder,
        mess_validation=consume_frozen_mess(case.initial_mess,day_begin_seconds=case.planning_slot_zero_seconds+21600,evidence_kind='REAL_DATA'))
    if perf_counter()-compile_started>120:raise RuntimeError('POLICY_COMPILE_BUDGET_EXHAUSTED')
    variants={r:freeze_variant(policy,mode) for r,mode in (('R0','REFERENCE_ONLY'),('R1','REFERENCE_ONLY'),('R2','FROZEN'),('R3','NO_PREPLACE'))}
    for label,p in variants.items():p.save(output/(label+'_FROZEN_POLICY.json'))
    _write(output/'UNKNOWN_FROZEN_POLICY_SHA.json',dict(status='FROZEN_BEFORE_ACTUAL',
        policy_SHAs={r:p.sha for r,p in variants.items()},bindings=policy.bindings,compile_wall_seconds=perf_counter()-compile_started,
        coverage='PARTIAL_POLICY_COVERAGE',Actual_new_grid_objective_calls=0))
    gpu={u:j.gpu for u,j in records.items()}
    commands=compile_known_commands(a1['selected_jobs'],slot_zero_seconds=case.planning_slot_zero_seconds,
        migration_authority=case.experimental_migration_authority,gpu_by_uid=gpu)
    _write(output/'A1_KNOWN_FROZEN_COMMANDS.json',commands)
    _write(output/'CANARY_PLANNING_FREEZE.json',dict(status=status,case_sha=case.case_sha,science_sha=case.science_sha,
        Known_schedule_sha=digest(commands),Known_schedule=commands,policy_SHAs={r:p.sha for r,p in variants.items()},
        common_initial_state_sha=preflight['common_initial_state_sha'],Planning_slots=96,Actual_slots=16,
        Full96_PASS=False,MESS_OFF=True,Freeze_before_Actual=True))
    for label,p in variants.items():
        if label=='R3' and perf_counter()-began>760:
            _write(output/'R3_NOT_RUN.json',dict(reason='OPTIONAL_ABLATION_WALL_BUDGET'));continue
        stage('ACTUAL_'+label,120);at=perf_counter()
        projected=prepare_conditional_arguments(dict(case.actual_arguments,qos_window_provider=strict),records,
            scenario='E1',participation='FLEX30',case_sha=case.case_sha)
        args=projected['arguments'];args['end']=args['begin']+14400;args['weather']=args['weather'][:16]
        args['requests']=[r for r in args['requests'] if r.submit<args['end']]
        loaded=CanaryFrozenPolicy.load(output/(label+'_FROZEN_POLICY.json'),bindings=p.bindings);loaded.bind_runtime_packet(policy.packet)
        before=loaded.packet.evaluation_calls
        result=run_experimental_actual(**args,arm='B0' if label=='R0' else 'B1',
            frozen_policy=loaded,known_schedule={} if label=='R0' else commands,expected_bindings=loaded.bindings)
        if loaded.packet.evaluation_calls!=before:raise ValueError('ACTUAL_NEW_GRID_OBJECTIVE_SCORING')
        metrics=unknown_actual_metrics(result)
        if not metrics['Known_Unknown_action_ledger_disjoint'] or metrics['QoS_intentional_budget_excess_UID']:
            raise ValueError('CAUSAL_OR_QOS_EXECUTION_GUARD')
        if perf_counter()-at>120:raise RuntimeError('ACTUAL_REPLAY_BUDGET_EXHAUSTED')
        result['canary']=dict(label=label,Planning_slots=96,Actual_slots=16,Full96_PASS=False,
            common_initial_state_sha=preflight['common_initial_state_sha'],Known_schedule_sha=None if label=='R0' else digest(commands),
            status='EXECUTED_PARTIAL_CANARY_NOT_FULL96_CERTIFICATE',wall_seconds=perf_counter()-at,Unknown_metrics=metrics,
            policy_sha=loaded.sha,begin=args['begin'],end=args['end'])
        _write(output/(label+'_PARTIAL_RESULT.json'),result)
        np.savez_compressed(output/(label+'_ACTUAL_ARRAYS.npz'),GPU=result['occupancy_GPU'],Compute=result['compute_occupancy_GPU'],
            **{k:v for k,v in result['physical'].items() if isinstance(v,np.ndarray)})
        print(label+' PARTIAL EXECUTED',flush=True)
    stage('COMPLETE',0)
    _write(output/'CANARY_COMPLETION.json',dict(completed=True,wall_seconds=perf_counter()-began,
        Native_Runtime_seconds=budget.document['Gurobi_Native_seconds'],Full96_PASS=False))


if __name__=='__main__':
    import argparse,traceback
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--native0-only',action='store_true')
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    try:
        if args.native0_only:prepare_canary(args.output)
        else:run_canary(args.output)
    except BaseException as exc:
        _write(args.output/'CANARY_EXECUTION_FAILURE.json',dict(status='STOPPED_FAIL_CLOSED',
            error=repr(exc),traceback=traceback.format_exc(),Native_auto_retry=False,
            Original_Full96_Gate_weakened=False,Full96_PASS=False))
        raise

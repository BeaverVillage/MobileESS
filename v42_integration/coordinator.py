"""One common production call path for comparison Arms; no dispatcher/server.

Execution is an explicitly supplied isolated case. The existing 31-day
dispatcher remains HOLD and is never invoked by this entrypoint.
"""
from dataclasses import dataclass,field
from pathlib import Path
import json
from .a_engine import optimize_aidc,digest
from .m_engine import optimize_mess
from .policy import compile_policy,FrozenControlPolicy
from .actual import run_actual


@dataclass
class IntegrationCase:
    case_sha: str
    science_sha: str
    qos_provider: object
    reference_aidc: dict
    initial_mess: dict
    make_a_case: object
    make_m_case: object
    signed_grid_coefficients: dict
    actual_arguments: dict
    input_receipts: list
    source_freeze: dict
    evidence_kind: str = 'REAL_DATA'
    planning_slot_zero_seconds: float = -21600.
    fresh_evaluator: object = None
    actual_gate: dict | None = None
    control_policy_factory: object = None
    unified_bindings: dict | None = None
    unified_actual_runner: object = None
    unified_m_optimizer: object = None
    _consumed: bool = field(default=False,init=False,repr=False)


def _write(path,doc):
    from .m_engine import _json_value
    Path(path).write_text(json.dumps(_json_value(doc),indent=2,allow_nan=False),encoding='utf8')


def verify_sources(freeze,receipts):
    from .m_engine import file_record
    for expected in list(freeze['files'])+list(receipts):
        actual=file_record(expected['path'])
        if any(actual[k]!=expected[k] for k in ('path','sha256','bytes')):
            raise ValueError('INTEGRATION_FROZEN_INPUT_OR_SOURCE_DRIFT:'+expected['path'])


def _full_a(result):
    required=('selected_jobs','AIDC_P_by_site','AIDC_Q_by_site','CC4_service','CC4_carryout','anonymous_resource_envelope')
    if not result.get('FULL_feasible') or any(k not in result for k in required):
        raise RuntimeError('A_FULL_HANDOFF_NOT_ESTABLISHED')
    if result['aidc_anchor']!=digest({k:result[k] for k in required}):
        raise ValueError('A_FULL_FIXED_ANCHOR_DRIFT')
    return result


def _full_m(result):
    plan=result.get('mess')
    if not result.get('FULL_validated') or not plan or any(k not in plan for k in ('routes','P_by_site','Q_by_site','SOC','Mode','plan_sha')):
        raise RuntimeError('M_COMPLETE_PHYSICAL_HANDOFF_NOT_ESTABLISHED')
    if digest({k:v for k,v in plan.items() if k!='plan_sha'})!=plan['plan_sha']:
        raise ValueError('M_FULL_FIXED_ANCHOR_DRIFT')
    return plan


def _require_actual_gate(case, midnight):
    if case.evidence_kind!='REAL_DATA':return
    gate=case.actual_gate
    if (not isinstance(gate,dict) or gate.get('status')!='DDAY_INITIAL_STATE_AUTHORIZED'
            or gate.get('initial_queue_verified') is not True
            or gate.get('active_running_site_authority') is not True):
        raise ValueError('DDAY_ACTUAL_INITIAL_STATE_NOT_AUTHORIZED')
    from .dday_boundary import assert_full96_authority
    assert_full96_authority(gate)
    arguments=case.actual_arguments
    if arguments.get('begin')!=midnight or arguments.get('end')!=midnight+86400:
        raise ValueError('DDAY_ACTUAL_EXACT_96_SLOT_SCOPE_REQUIRED')


def run_arm(arm, case, budget, output, *, planning_only=False):
    """Final A2+M2 policy is recompiled, reloaded, then used by common Actual."""
    if arm not in ('B0','B2','B1','B3'):
        raise ValueError('COMPARISON_ARM_REQUIRED')
    if case._consumed:
        raise ValueError('INTEGRATION_CASE_ALREADY_CONSUMED_BUILD_FRESH_CASE_PER_ARM')
    if case.unified_bindings is not None:
        from .unified_contract import load_contracts, require_bindings
        common=load_contracts()['bindings']
        expected=dict(common,aidc_anchor=case.reference_aidc['aidc_anchor'],
                      mess_anchor=case.initial_mess['plan_sha'])
        require_bindings(case.unified_bindings,expected)
        if (case.science_sha!=common['science_sha'] or case.case_sha!=common['case_sha']
                or case.qos_provider.stats.sha!=common['qos_sha']):
            raise ValueError('UNIFIED_CASE_SCIENCE_QOS_DRIFT')
    midnight=case.planning_slot_zero_seconds+24*900
    if not planning_only:_require_actual_gate(case,midnight)
    verify_sources(case.source_freeze,case.input_receipts)
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    case._consumed=True
    calls=[];handoffs=[];aidc=case.reference_aidc;mess=case.initial_mess
    initial=None;registry=[]
    if arm=='B1' and any(float(v)!=0. for field in ('P_by_site','Q_by_site') for row in mess[field].values() for v in row):
        raise ValueError('B1_MESS_PQ_MUST_BE_ZERO')
    stages={'B0':(),'B2':('M1',),'B1':('A1',),'B3':('A1','M1','A2','M2')}[arm]
    results={}
    for stage in stages:
        verify_sources(case.source_freeze,case.input_receipts)
        before=dict(AIDC_anchor=aidc['aidc_anchor'],MESS_anchor=mess['plan_sha'])
        stage_bindings=None if case.unified_bindings is None else dict(case.unified_bindings,
            aidc_anchor=aidc['aidc_anchor'],mess_anchor=mess['plan_sha'])
        if stage.startswith('A'):
            a_case=case.make_a_case(arm,stage,mess,output/stage)
            if stage_bindings is not None:a_case.unified_bindings=dict(stage_bindings)
            result=optimize_aidc(a_case,mess,case.qos_provider,budget)
            aidc=_full_a(result)
            consumed=dict(fixed_mess_plan_sha=mess['plan_sha'],QoS_SHA=case.qos_provider.stats.sha)
        else:
            m_case=case.make_m_case(arm,stage,aidc,output/stage)
            if stage_bindings is not None:m_case.unified_bindings=dict(stage_bindings)
            if m_case.identity.get('aidc_anchor')!=aidc['aidc_anchor']:
                raise ValueError('M_STAGE_AIDC_ANCHOR_MISMATCH')
            # A new anchor receives the old vector only as a FULL-replayed warm
            # candidate; registry bindings/LB do not transfer to this new case.
            m_optimizer=case.unified_m_optimizer or optimize_mess
            result,initial=m_optimizer(m_case,initial,registry,budget)
            mess=_full_m(result);registry=result['incumbent_registry']
            consumed=dict(fixed_aidc_anchor=aidc['aidc_anchor'],full_PQ_and_anonymous_frozen=True)
        results[stage]=result
        calls.append(dict(stage=stage,arm=arm,engine=result.get('engine',result.get('engine_version')),case_sha=result['case_sha']))
        handoffs.append(dict(stage=stage,producer_anchor_before=before,consumed=consumed,
            result_AIDC_anchor=aidc['aidc_anchor'],result_MESS_anchor=mess['plan_sha'],
            unified_input_bindings=stage_bindings))
        _write(output/'A_M_CALLGRAPH.json',calls);_write(output/'STAGE_HANDOFF_AUDIT.json',handoffs)
    if case.unified_bindings is not None and arm=='B3':
        from .unified_contract import validate_handoffs
        _write(output/'UNIFIED_HANDOFF_VALIDATION.json',validate_handoffs(handoffs,
            case.unified_bindings,case.reference_aidc['aidc_anchor'],case.initial_mess['plan_sha']))
    bindings=dict(science_sha=case.science_sha,qos_sha=case.qos_provider.stats.sha,
        case_sha=case.case_sha,aidc_anchor=aidc['aidc_anchor'],mess_anchor=mess['plan_sha'])
    if case.unified_bindings is not None:
        bindings=dict(case.unified_bindings,**bindings)
    # Native slot 24 is planning-day midnight; Actual has its own explicit
    # seconds origin. This is a conversion, never an inferred array offset.
    envelope=[dict(r,slot_start=r['slot_start']+midnight,slot_end=r['slot_end']+midnight,
        carryout_end=r.get('carryout_end',86400.)+midnight) for r in aidc['anonymous_resource_envelope']]
    effects={(s,t+midnight):v for (s,t),v in case.signed_grid_coefficients.items()}
    sensitivity=arm in ('B1','B3') and case.control_policy_factory is not None
    mess_actual=None
    if sensitivity:
        from .mess_actual import consume_frozen_mess
        mess_actual=consume_frozen_mess(mess,day_begin_seconds=midnight,evidence_kind=case.evidence_kind,
            original_full_validated=any(r.get('FULL_validated') is True for s,r in results.items() if s.startswith('M')))
        _write(output/'MESS_ACTUAL_EXECUTION_RECEIPT.json',mess_actual)
        try:
            policy=case.control_policy_factory(arm=arm,aidc=aidc,mess=mess,bindings=bindings,
                envelope=envelope,output=output,mess_validation=mess_actual)
        except Exception as error:
            _write(output/'CONTROL_POLICY_COMPILATION_FAILURE.json',dict(status='FAILED_CLOSED',
                reason=str(error),bindings=bindings,final_A_stage='A2' if arm=='B3' else 'A1',
                final_MESS_stage='M2' if arm=='B3' else 'SOURCE_MESS_OFF_ANCHOR',
                legacy_policy_fallback_used=False,actual_started=False))
            raise
        expanded=policy.bindings
        if any(expanded.get(key)!=value for key,value in bindings.items()):
            raise ValueError('CONTROL_POLICY_FACTORY_FINAL_A_M_BINDING_DRIFT')
        bindings=expanded
        path=output/'OPTIMIZED_CONDITIONAL_CONTROL_POLICY.json'
    else:
        policy=compile_policy(envelope,bindings,effects)
        path=output/'UNKNOWN_CONTROL_POLICY.json'
    policy.save(path)
    reload=type(policy).load(path,bindings=bindings)
    if hasattr(reload,'bind_runtime_packet'):
        reload.bind_runtime_packet(policy.packet)
    if sensitivity:
        # Retain the established consumer filename with identical content.
        reload.save(output/'UNKNOWN_CONTROL_POLICY.json')
        _write(output/'CONTROL_POLICY_RELOAD_TEST.json',dict(PASS=reload.sha==policy.sha,
            policy_sha=reload.sha,bindings=bindings,reloaded_before_actual=True,
            semantic_document_equal=reload.document==policy.document,
            actual_global_optimizer_calls=0,source='FROZEN_FILE_ROUNDTRIP'))
    from .m_engine import file_record
    from . import SCIENCE_VERSION
    freeze=dict(science_version=case.source_freeze.get('science_version',SCIENCE_VERSION),**bindings,
        Known_schedule=aidc['selected_jobs'],QoS_receipts=case.qos_provider.to_dict(),
        resource_envelope=aidc['anonymous_resource_envelope'],MESS_plan=mess,
        source_freeze=case.source_freeze,inputs=case.input_receipts,policy_file=file_record(path),
        control_policy_algorithm=policy.document.get('policy_version'),
        sensitivity_policy_enabled=sensitivity,
        Known_planning_metrics=aidc.get('Known_planning_metrics'),
        research_contract_binding=getattr(case,'research_contract_binding',None),
        stages=results,campaign_HOLD=True,campaign_started=False,
        global_AIDC_MESS_gap='NOT_CERTIFIED',evidence_kind=case.evidence_kind,
        actual_gate=case.actual_gate,Actual_execution_authorized=not planning_only)
    freeze['evaluation_case_sha']=getattr(case,'evaluation_case_sha',None)
    if sensitivity:
        _write(output/'CONTROL_POLICY_SHA_MANIFEST.json',dict(policy_sha=reload.sha,bindings=bindings,
            source_freeze_sha=case.source_freeze.get('source_sha'),policy_file=file_record(path),
            final_A_stage='A2' if arm=='B3' else 'A1',
            final_MESS_stage='M2' if arm=='B3' else 'SOURCE_MESS_OFF_ANCHOR',
            stale_A1_policy_reused=False,source_input_receipts=case.input_receipts,
            compiler_source_sha=policy.document.get('compiler_source_sha')))
    _write(output/'PLANNING_FREEZE.json',freeze)
    from .known_commands import compile_known_commands
    gpu_by_uid={u:r.hard_contract['gpu'] for u,r in case.qos_provider.receipts.items() if not r.origin_unknown}
    commands=compile_known_commands(aidc['selected_jobs'],slot_zero_seconds=case.planning_slot_zero_seconds,
        migration_authority=getattr(case,'experimental_migration_authority',None),gpu_by_uid=gpu_by_uid)
    if planning_only:
        _write(output/'RELOAD_CONSUMPTION_RECEIPT.json',dict(policy_sha=reload.sha,anchors=bindings,
            reloaded_before_actual=True,status='RELOADED_PLANNING_ONLY_ACTUAL_NOT_RUN',
            runtimeQueries=0,online_global_optimize_calls=0,actual_gate=case.actual_gate,
            fixture=case.evidence_kind!='REAL_DATA'))
        result=dict(arm=arm,stages=results,freeze=freeze,actual=None,planning_only=True,
            status='PLANNING_ONLY_ACTUAL_NOT_AUTHORIZED',campaign_HOLD=True,actual_gate=case.actual_gate)
        _write(output/'PLANNING_ONLY_RESULT.json',result)
        return result
    actual_arguments=case.actual_arguments
    if hasattr(case,'prepare_research_actual_arguments'):
        actual_arguments,projection=case.prepare_research_actual_arguments()
        _write(output/'ACTUAL_RESEARCH_MODEL_PROJECTION.json',dict(projection,
            projected_after_policy_freeze=True,frozen_policy_sha=reload.sha))
    arguments=dict(actual_arguments,frozen_policy=reload,qos_window_provider=case.qos_provider,
        arm=arm,known_schedule=commands,expected_bindings=bindings)
    if case.unified_actual_runner is not None:
        if case.unified_bindings is None:
            raise ValueError('UNIFIED_ACTUAL_REQUIRES_SHARED_BINDINGS')
        actual=case.unified_actual_runner(**arguments)
    elif getattr(case.qos_provider,'scenario','E0')!='E0':
        from .experimental_actual import run_experimental_actual
        if not getattr(reload,'lookup_only',False):raise ValueError('UNKNOWN_ACTUAL_FROZEN_LOOKUP_ONLY_REQUIRED')
        actual=run_experimental_actual(**arguments)
        actual['experimental_scope'].update(fixed_A2_M2_conditional_replay=False,
            Known_domain_handoff_verified=True,final_Known_stage='A2' if arm=='B3' else 'A1',
            new_Known_contract_domain_optimized=all(results[s].get('engine')=='v42_integration.a_engine.optimize_aidc'
                for s in stages if s.startswith('A')))
    else:
        actual=run_actual(**arguments)
    actual['receipt'].update(common_initial_state_sha=(case.actual_gate or {}).get('common_initial_state_sha'),
        evaluation_case_sha=getattr(case,'evaluation_case_sha',None))
    from .action_metrics import unknown_actual_metrics
    if isinstance(actual.get('carryout'),dict) and 'controller' in actual['carryout']:
        actual['Unknown_actual_metrics']=unknown_actual_metrics(actual,begin=midnight)
        _write(output/'KNOWN_UNKNOWN_ACTION_METRICS.json',dict(
            Known_Planning=aidc.get('Known_planning_metrics'),Unknown_Actual=actual['Unknown_actual_metrics']))
    from .mess_actual import consume_frozen_mess
    if mess_actual is None:
        mess_actual=consume_frozen_mess(mess,day_begin_seconds=midnight,evidence_kind=case.evidence_kind,
            original_full_validated=any(r.get('FULL_validated') is True for s,r in results.items() if s.startswith('M')))
    actual['MESS_execution']=mess_actual
    _write(output/'MESS_ACTUAL_EXECUTION_RECEIPT.json',mess_actual)
    # Retain the completed event execution before the separate electrical
    # consumer runs, including when that later check fails.
    for filename,key in (('JOB_EVENT_LEDGER.json','job_event_ledger'),
        ('RESERVATION_LEDGER.json','reservation_ledger'),('CC4_DEPLETION_LEDGER.json','cc4_depletion_ledger'),
        ('MIGRATION_RECEIPTS.json','migration_receipts'),('QOS_ACTUAL_RECEIPTS.json','qos_ledger'),
        ('QOS_BUDGET_LEDGER.json','qos_budget_ledger'),('ACTUAL_QUEUE_LEDGER.json','queue_ledger'),
        ('CARRYOUT_RECEIPT.json','carryout'),('RULE_CONSUMPTION_RECEIPT.json','rule_consumption_receipt')):
        _write(output/filename,actual[key])
    _write(output/'ACTUAL_RESULT.json',actual)
    if sensitivity:
        import csv
        from collections import Counter
        columns=('time_seconds','uid','action','policy_action','status','reason','rule_id','policy_sha','site','estimated_worst_peak','decision_json')
        with (output/'UNKNOWN_POLICY_ACTION_LEDGER.csv').open('w',newline='',encoding='utf8') as stream:
            writer=csv.DictWriter(stream,fieldnames=columns);writer.writeheader()
            for row in actual['rule_consumption_receipt']:
                writer.writerow({**{key:row.get(key) for key in columns if key!='decision_json'},
                    'decision_json':json.dumps(row,sort_keys=True,default=str)})
        excess=[r['uid'] for r in actual['qos_ledger'] if r['total_intentional_burden_seconds']>r['budget_seconds']+1e-9]
        _write(output/'QOS_MIGRATION_RESERVATION_AUDIT.json',dict(
            intentional_burden_excess_UIDs=excess,capacity_violations=actual['receipt']['capacity_violations'],
            migration_count=len(actual['migration_receipts']),
            actual_occupation_GPUh=actual['receipt']['actual_occupation_GPUh'],
            actual_compute_GPUh=actual['receipt']['actual_compute_GPUh'],
            CC4_depletion_count=len(actual['cc4_depletion_ledger']),
            CC4_unique_UIDs=len({r['uid'] for r in actual['cc4_depletion_ledger']}),
            action_counts=dict(Counter(r.get('action') for r in actual['rule_consumption_receipt'])),
            reservation_ledger=actual['reservation_ledger'],physical_power_recomputed=actual['receipt']['actual_power_recomputed'],
            online_global_optimizer_calls=actual['receipt']['actual_global_reoptimization'],
            same_frozen_policy_sha=reload.sha,Fresh_AC_status='PENDING_SEPARATE_CONSUMER'))
        runtime_path=output/'CONTROL_POLICY_RUNTIME_MEMORY.json'
        runtime=json.loads(runtime_path.read_text(encoding='utf8')) if runtime_path.exists() else {}
        metrics=reload.runtime_metrics() if hasattr(reload,'runtime_metrics') else {}
        runtime.update(metrics,Actual_rule_queries=len(actual['rule_consumption_receipt']),
            Actual_event_count=len(actual['job_event_ledger']),Actual_status='EXECUTED')
        _write(runtime_path,runtime)
    if actual.get('physical') is not None:
        import numpy as np
        start=case.actual_arguments.get('begin',0.)
        first=round((midnight-start)/900)
        if first<0:raise ValueError('ACTUAL_FULL96_BEGIN_AXIS')
        physical=actual['physical']
        GPU=np.asarray(actual['occupancy_GPU'])
        expected_slots=round((case.actual_arguments.get('end',86400.)-start)/900)
        if (midnight-start)/900!=first or GPU.ndim!=2 or GPU.shape!=(expected_slots,len(actual['sites'])):
            raise ValueError('ACTUAL_OCCUPANCY_TIME_SITE_AXIS_DRIFT')
        if any(np.asarray(physical[k]).shape!=GPU.shape for k in ('IT_kw','PCC_P_kw','PCC_Q_kvar')):
            raise ValueError('ACTUAL_POWER_OCCUPANCY_AXIS_DRIFT')
        count=min(96,expected_slots-first)
        if count<=0 or (case.evidence_kind=='REAL_DATA' and count!=96):
            raise ValueError('ACTUAL_REAL_FULL96_TRACE_REQUIRED')
        trace=output/'ACTUAL_OCCUPANCY_POWER_TRACE.npz'
        np.savez_compressed(trace,sites=np.asarray(actual['sites']),timestamps_start_epoch_seconds=midnight+np.arange(count)*900,
            GPU=GPU[first:first+count],
            compute_GPU=actual['compute_occupancy_GPU'][first:first+count],
            **{k:physical[k][first:first+count] for k in ('IT_kw','PCC_P_kw','PCC_Q_kvar')})
        if case.fresh_evaluator is not None:
            actual['Fresh_AC']=case.fresh_evaluator(trace,mess,output/'FRESH_PHYSICAL',budget,arm=arm)
            mess_actual['electrical_consumer_status']='CONSUMED_BY_FRESH_AC'
            mess_actual['fresh_AC_PASS']=actual['Fresh_AC'].get('PASS')
            actual['receipt']['physical_ac_status']=actual['Fresh_AC']['status']
            _write(output/'MESS_ACTUAL_EXECUTION_RECEIPT.json',mess_actual)
            if sensitivity:
                audit_path=output/'QOS_MIGRATION_RESERVATION_AUDIT.json'
                audit=json.loads(audit_path.read_text(encoding='utf8'))
                audit.update(Fresh_AC_status=actual['Fresh_AC']['status'],Fresh_AC_PASS=actual['Fresh_AC'].get('PASS'))
                _write(audit_path,audit)
    _write(output/'ACTUAL_RESULT.json',actual)
    _write(output/'RELOAD_CONSUMPTION_RECEIPT.json',dict(policy_sha=reload.sha,
        anchors=bindings,reloaded_before_actual=True,online_global_optimize_calls=0,
        fixture=case.evidence_kind!='REAL_DATA'))
    return dict(arm=arm,stages=results,freeze=freeze,actual=actual,campaign_HOLD=True)

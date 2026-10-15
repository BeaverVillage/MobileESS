"""Current accepted A2/M2 -> original event driver -> original settled Fresh.

This additive path never uses the historical PR223 reference fallback. Planning
identities stay intact; each Actual policy and scope has a separate canonical
evaluation case. Private input preparation is called only after public gates.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import heapq
import json
from pathlib import Path
from time import perf_counter

import numpy as np

from .actual import JobEventController, run_actual
from .aidc_sensitivity_runtime import CurrentEventJobEventController, _bind_driver_current_c1
from .policy import digest
from .m_engine import file_record, _write, _json_value
from .release_ac_contract import (CONTRACT, actual_evaluation_case_payload,
    require_current_settled_evidence, validate_settled_fresh)
from .release_actual import ReleasePolicy, ReleaseController, completed_prefix, initial_authority
from .research_presite_actual import ResearchReleasePolicy, ResearchCurrentAC
from .rc02_prefix_cache import PrefixCachedCurrentAC, memory_gate

SUPPORTED_PRODUCTION_DAYS=tuple(f'2025-05-{day:02d}' for day in range(1,32))


def _read(record):
    if file_record(record['path']) != record:
        raise ValueError('PRODUCTION_ACTUAL_INPUT_SOURCE_BYTES_DRIFT')
    return json.loads(Path(record['path']).read_text(encoding='utf-8-sig'))


def source_case(context):
    manifest=context['manifest']
    begin=manifest['time_axis']['evaluation_begin_seconds']
    day=datetime.fromtimestamp(begin,timezone(timedelta(hours=10))).date().isoformat()
    return dict(day=day,source_identity=deepcopy(manifest['identity']),source_sha=manifest['source_sha'])


def require_actual_gates(context, a_result, a_acceptance, m_result, m_acceptance, *, slots, gate):
    """Every check precedes loading private durations or completion truth."""
    from .release_p1_production import verify_context, require_production_acceptance
    verify_context(context)
    source=source_case(context);identity=source['source_identity']
    if source['day'] not in SUPPORTED_PRODUCTION_DAYS:
        raise ValueError('PRODUCTION_APPROVED_MAY_DATE_REQUIRED')
    if slots not in (16,96) or not isinstance(gate,dict):
        raise ValueError('PRODUCTION_EXPLICIT_CANARY16_OR_FULL96_GATE_REQUIRED')
    if (gate.get('Gate_contract') != CONTRACT or gate.get('official_contract_authorized') is False):
        raise ValueError('PRODUCTION_ORIGINAL_SETTLED_CONTRACT_AUTHORIZATION_REQUIRED')
    for result,acceptance,stage in ((a_result,a_acceptance,'A2'),(m_result,m_acceptance,'M2')):
        require_production_acceptance(acceptance,stage=stage,identity=identity,result=result)
        if acceptance['source_sha'] != source['source_sha']:
            raise ValueError('PRODUCTION_CURRENT_PLANNING_SOURCE_REQUIRED')
    if (m_acceptance['parent_acceptance_sha'] != a_acceptance['acceptance_sha']
            or m_acceptance['AIDC_anchor'] != a_acceptance['AIDC_anchor']
            or a_result['aidc_anchor'] != a_acceptance['AIDC_anchor']
            or m_result['mess']['plan_sha'] != m_acceptance['MESS_anchor']):
        raise ValueError('PRODUCTION_CURRENT_A2_M2_PARENT_AND_ANCHOR_REQUIRED')
    # No default to SourceStrict can silently change the requested main R1 arm.
    policy=deepcopy(gate.get('actual_policy_by_day',{}).get(source['day'],gate.get('actual_policy')))
    ancestors=dict(A2_result=a_result,A2_acceptance=a_acceptance,M2_result=m_result,M2_acceptance=m_acceptance)
    payload=actual_evaluation_case_payload(source,ancestors,policy,slots)
    if slots==96:
        if source['day']=='2025-05-01':
            require_current_settled_evidence(gate['physical_evidence'],source_case=source,
                ancestors=ancestors,slots=16,expected_actual_policy=policy)
        else:
            # May01 is a launch prerequisite, never the new date's physical
            # certificate. Every new date still executes its own Fresh96.
            from .release_production_campaign import require_planning_checkpoint
            may01=gate['settled_source_case']
            if may01.get('day')!='2025-05-01':raise ValueError('MAY01_FULL96_LAUNCH_SOURCE_REQUIRED')
            imported=require_planning_checkpoint(gate['planning_checkpoint'],source_case=may01)
            expected=gate.get('actual_policy_by_day',{}).get('2025-05-01',gate.get('may01_actual_policy',gate.get('actual_policy')))
            require_current_settled_evidence(gate['full96_evidence'],source_case=may01,
                ancestors=imported['ancestors'],slots=96,expected_actual_policy=expected)
    proof=dict(schema='RELEASE_PRIVATE_ACTUAL_PREPARATION_GATE_V1',status='PASS',
        source_identity=identity,source_sha=source['source_sha'],clock_contract=CONTRACT,slots=slots,
        ancestors=deepcopy(ancestors),actual_policy=policy,evaluation_case_payload=payload,
        evaluation_case_sha=digest(payload))
    proof['preparation_gate_sha']=digest(proof)
    return proof


def initial_pending_placement(controller, uid, now):
    """A2's first site designation is not alternate-site change permission.

    This narrow exception applies only to a source-less, never-started, exact
    approved initial PENDING UID. It never authorizes a corrective move.
    """
    m=controller.metadata[uid];request=controller.requests[uid]
    raw=controller.production_initial_pending.get(uid)
    contract=controller.production_backlog
    command=controller.planning_commands.get(uid)
    job=controller.ledger.jobs.get(uid,{})
    if (raw is None or command is None or m.get('state')!='PENDING' or m.get('origin_unknown') is not False
            or request.source_site is not None or raw.get('site') is not None
            or job.get('start_time') is not None or m.get('accumulated_compute_seconds',0)!=0
            or uid in controller.corrective_commands or command.get('command_type')!='D0_PENDING_NEW_OPTIMIZED_START'
            or contract.get('pending_source_compatible_placement_research_authorized') is not True
            or command['site'] not in request.compatible or request.gpu!=raw['gpu']
            or request.q50!=raw['q50'] or command['start_seconds']>now):
        return None
    if controller._hard_window(uid,now):return None
    site=command['site'];policy=controller.policy
    if request.gpu>max(policy.packet.rack_compatibility[site]):return None
    use=controller.reservations.current_gpu_use(now,exclude=uid)
    if use[site]+request.gpu>controller.ledger.capacities[site]:return None
    return dict(uid=uid,action='START',site=site,start_seconds=now,
        nominal_end_seconds=now+max(request.q50,1e-9),plan_start_seconds=command['start_seconds'],
        additional_start_delay_seconds=max(0.,command['start_seconds']-controller.budgets[uid].reference_start_seconds),
        unavoidable_resource_wait_seconds=max(0.,now-command['start_seconds']),
        status='A2_APPROVED_BASIC_INITIAL_PLACEMENT_SOURCE_FLAGS_UNCHANGED')


class ProductionResearchPolicy(ResearchReleasePolicy):
    """Same research provider, with explicit GPU/Rack-before-data funnel."""
    def _candidate(self,m,site,now,*,changing=False):
        if changing:
            use=self._current_resource_ledger.current_gpu_use(now,exclude=m['uid'])
            reason=None
            if site not in m['compatible_sites']:reason='SOURCE_SITE_INCOMPATIBLE'
            elif m['gpu']>max(self.packet.rack_compatibility[site]):reason='RACK_GANG_INCOMPATIBLE'
            elif use[site]+m['gpu']>self.packet.capacities[site]:reason='CURRENT_GPU_CAPACITY'
            if reason:
                return dict(site=site,kind='PRE_SITE',feasible=False,reason=reason,
                    basic_site=self.initial[m['uid']]['basic_site'],sensitivity_score=None,
                    research_data_contract=None,data_QoS_AC='NOT_EVALUATED',executable_now=False)
        return super()._candidate(m,site,now,changing=changing)


class ProductionCurrentController(CurrentEventJobEventController):
    """Accepted D0 commands; no PR223 reference/FCFS fallback inheritance."""
    def __init__(self,*args,initial_pending,backlog_contract,**kwargs):
        super().__init__(*args,**kwargs)
        self.production_initial_pending=deepcopy(initial_pending)
        self.production_backlog=deepcopy(backlog_contract)
        self.actual_start_events=[];self.control_tick_times=[];self.observed_known_waits={}

    def submit(self,request,now):
        super().submit(request,now);m=self.metadata[request.uid]
        self.policy.designate(m,now)
        if hasattr(self.policy,'register_observed'):self.policy.register_observed(m,now)

    def _known_decision(self,uid,now):
        decision=super()._known_decision(uid,now)
        if decision.get('status')=='PLAN_SITE_NO_SOURCE_AUTHORITY':
            return initial_pending_placement(self,uid,now) or decision
        prior=self.observed_known_waits.get(uid)
        if (decision.get('status')=='KNOWN_MISSED_UNOBSERVED_PLANNING_START' and prior is not None
                and prior['time_seconds']<now):
            retry=initial_pending_placement(self,uid,now)
            command=self.planning_commands[uid];request=self.requests[uid]
            if (retry is None and self.metadata[uid]['state']=='PENDING' and self._hard_window(uid,now) is None
                    and command['site']==request.source_site and command['site'] in request.compatible
                    and request.gpu<=max(self.policy.packet.rack_compatibility[command['site']])
                    and self.reservations.current_gpu_use(now,exclude=uid)[command['site']]+request.gpu<=self.ledger.capacities[command['site']]):
                retry=dict(uid=uid,action='START',site=command['site'],start_seconds=now,
                    nominal_end_seconds=now+max(request.q50,1e-9),plan_start_seconds=command['start_seconds'],
                    additional_start_delay_seconds=max(0.,command['start_seconds']-self.budgets[uid].reference_start_seconds),
                    unavoidable_resource_wait_seconds=max(0.,now-command['start_seconds']))
            if retry is not None:
                retry.update(status='OBSERVED_ADMISSION_RESOURCE_WAIT_RETRY_SAME_A2_COMMAND',
                    observed_wait_proof=deepcopy(prior),planning_command_modified=False)
                return retry
        return decision

    def _corrective_decision(self,uid,now,use):
        command=self.planning_commands[uid]
        # Reuse only the current-AC corrective method, never the historical
        # controller's _known_decision/_reference_decision or queue order.
        return ReleaseController._guard_known(self,uid,now,dict(uid=uid,action='START',
            site=command['site'],start_seconds=command['start_seconds'],
            nominal_end_seconds=now+max(self.requests[uid].q50,1e-9)))

    def admit(self,now):
        if now%900:return []
        began=perf_counter();count=len(self.pending)
        self.policy.oracle.observe(now,completed_prefix(self,now))
        try:
            if digest(self.known_schedule)!=self.frozen_known_sha:
                raise ValueError('PRODUCTION_IMMUTABLE_A2_COMMAND_DRIFT')
            self.policy.require_bindings(self.policy.bindings)
            remaining=[];starts=[]
            for row in sorted(self.pending,key=lambda r:(self.metadata[r[1]]['origin_unknown'],r[0],r[1])):
                uid=row[1];self.pending=[row];self.decisions.pop(uid,None)
                self.policy.observe(now,self.reservations.current_gpu_use(now,exclude=uid),self.metadata)
                if not self.metadata[uid]['origin_unknown'] and uid not in self.planning_commands:
                    self.decisions[uid]=dict(uid=uid,action='QUEUE',status='SAME_CASE_KNOWN_PLANNING_COMMAND_MISSING')
                one=JobEventController.admit(self,now);starts.extend(one);remaining.extend(self.pending)
                d=self.decisions.get(uid,{})
                if (not one and uid in self.planning_commands and d.get('action') in ('START','PREPLACE')
                        and d.get('start_seconds',float('inf'))<=now):
                    # An actual START was attempted and the preserved atomic
                    # guard declined it. This is observed waiting, not an
                    # unobserved historical command or intentional time shift.
                    event=next((e for e in reversed(self.events) if e['uid']==uid and e['time_seconds']==now),None)
                    if event and event['event']=='QUEUED':
                        self.observed_known_waits[uid]=dict(time_seconds=now,queue_event=deepcopy(event),
                            original_command_sha=digest(self.planning_commands[uid]),
                            actual_START_attempt_observed=True,command_or_source_flags_changed=False)
                if one:
                    m=self.metadata[uid]
                    self.actual_start_events.append(dict(uid=uid,time_seconds=now,site=m['current_site'],
                        GPU=self.requests[uid].gpu,origin_unknown=m['origin_unknown'],
                        basic_site=self.policy.initial.get(uid,{}).get('basic_site'),atomic_AC_rechecked=True))
                    if uid in self.corrective_commands:
                        self.corrective_commands[uid]['actual_start_seconds']=now
                        for entry in self.corrective_audit:
                            if entry.get('uid')==uid:entry['actual_start_seconds']=now
                    if uid in self.planning_commands:
                        self.known_actual_audit.append(dict(uid=uid,original_command=deepcopy(self.planning_commands[uid]),
                            actual_site=m['current_site'],actual_start_seconds=now,planning_command_modified=False))
            self.pending=remaining;heapq.heapify(self.pending)
            if self.resource_bridge is not None:self.resource_bridge.snapshot(now,self.metadata,self.reservations)
            return starts
        finally:
            self.control_tick_times.append(dict(time_seconds=now,wall_seconds=perf_counter()-began,
                pending_before=count,pending_after=len(self.pending),scope='ENTIRE_CONTROLLER_ADMIT_900_SECOND_TICK'))

    def snapshot(self,now):
        result=super().snapshot(now)
        result['production_state']=dict(actual_starts=deepcopy(self.actual_start_events),
            initial_placements=deepcopy(self.policy.initial_events),control_tick_timings=deepcopy(self.control_tick_times),
            prefix=completed_prefix(self,now),historical_reference_fallback_used=False,
            observed_known_admission_waits=deepcopy(self.observed_known_waits),
            planning_commands_modified=False,Running_migration='HOLD')
        return result


def _physical_packet(context,a_result,mess,arguments,commands,policy_spec):
    from .production_case import planning_power
    from .sensitivity_policy import build_grid_packet
    from .trajectory_tracking import TrackingReference
    from v42_native.grid import GridAuthority
    from v42_native.voltage import Stage,voltage_for
    manifest=context['manifest'];bundle=context['data'][0]
    physical=context.get('physical')
    if physical is None:physical=context['materialize_physical']()['physical']
    power,idle,swing,_=planning_power(bundle,physical.certificate)
    limits=voltage_for(Stage.A2)
    authority=GridAuthority(physical.certificate['input_identity']['identity']['inputs']['OpenDSS_master']['sha256'],
        digest(bundle['capacities']),digest(bundle),digest(bundle['battery']),limits.lower_squared,limits.upper_squared,
        True,stage=Stage.A2,transformer_current_authority_sha256=physical.thermal['transformer_current_authority_sha256'],
        thermal_authority=physical.thermal,require_all_transformer_currents=True)
    bindings=dict(manifest['identity'],qos_sha=arguments['qos_window_provider'].stats.sha,
        aidc_anchor=a_result['aidc_anchor'],mess_anchor=mess['plan_sha'],physical_sha=manifest['physical_sha'],
        time_axis_sha=manifest['time_axis_sha'],response_sha=digest(sorted({c.coefficient_sha256 for c in physical.coefficients})),
        interface_sha=digest(dict(controller='PRODUCTION_CURRENT_EVENT_ORIGINAL_AC_V1',policy=policy_spec)))
    sites=tuple(sorted(arguments['capacities']))
    arrays={k:np.asarray([a_result[k][s] for s in sites],float).T
        for k in ('known_site_GPU','nominal_site_GPU','AIDC_P_by_site','AIDC_Q_by_site')}
    packet=build_grid_packet(physical.coefficients,power,swing,arguments['capacities'],a_result,mess,authority,bindings,
        begin_seconds=arguments['begin'],known_gpu=arrays['known_site_GPU'],power_factor=arguments['power_model'].power_factor,
        mess_validation=dict(plan_sha=mess['plan_sha'],frozen_execution_validated=True),
        rack_compatibility={s:tuple(r['compatibility_GPU_limit'] for r in bundle['racks'] if r['aidc_id']==s) for s in sites})
    reference=TrackingReference(arrays['known_site_GPU'],arrays['nominal_site_GPU'],
        idle*np.asarray([arguments['capacities'][s] for s in sites])+swing*(arrays['known_site_GPU']+arrays['nominal_site_GPU']),
        arrays['AIDC_P_by_site'],arrays['AIDC_Q_by_site'],sites=sites,begin=arguments['begin'],commands=commands,
        identity=dict(planning_identity=manifest['identity'],A2_anchor=a_result['aidc_anchor'],MESS_anchor=mess['plan_sha']))
    return packet,reference,bindings


def _resource_bridge(context,a_result,capacities):
    import pandas as pd
    from .production_case import TIMING
    from .aidc_resource_bridge import PlanningActualResourceBridge
    manifest=context['manifest'];cc4=context['cc4'];timing=pd.read_csv(TIMING)
    identity=dict(source_sha=manifest['source_sha'],stage_case_sha=a_result['case_sha'],
        science_sha=manifest['identity']['science_sha'],initial_state_sha=manifest['identity']['initial_state_sha'],
        time_axis_sha=manifest['time_axis_sha'],cc4_sha=manifest['identity']['cc4_sha'],runtime_sha=manifest['identity']['runtime_sha'])
    authority={k:cc4[k] for k in ('model_id','prediction_sha','kernel_sha')}
    authority.update(timing_envelope_sha=file_record(TIMING)['sha256'],aidc_anchor=a_result['aidc_anchor'],
        future_Actual_or_UID_inputs_used=False,forecast_modifications=0)
    bridge=PlanningActualResourceBridge(a_result,identity=identity,expected_identity=identity,capacities=capacities,
        q50=cc4['q50_hourly_GPUh'],q90=cc4['q90_hourly_GPUh'],timing_lower=timing.Q10,timing_upper=timing.Q90,
        cc4_source_authority=authority,begin_seconds=manifest['time_axis']['evaluation_begin_seconds'])
    return bridge,identity


def _actual_source(context, private, policy_spec, output):
    modules=(__file__,'release_date_execution.py','release_private_actual_inputs.py','release_actual.py',
        'current_ac_admission.py','research_presite_actual.py','research_presite_contract.py','rc02_prefix_cache.py',
        'research_presite_transfer_literature.py','release_date_ac.py','release_ac_contract.py','actual.py',
        'aidc_sensitivity_runtime.py','aidc_resource_bridge.py')
    files=[file_record(Path(__file__).with_name(p)) if p!=__file__ else file_record(p) for p in modules]
    files.extend(private['sources'])
    if policy_spec.get('research_contract'):files.append(policy_spec['research_contract'])
    files=list({r['path']:r for r in files}.values())
    receipt=dict(planning_identity=context['manifest']['identity'],planning_source_sha=context['manifest']['source_sha'],
        files=files,source_sha=digest(files))
    _write(output/'PRODUCTION_ACTUAL_SOURCE_FREEZE.json',receipt)
    bypath={r['path']:r for r in context['manifest']['source_freeze']['files']}
    for r in files:
        if r['path'] in bypath and r!=bypath[r['path']]:raise ValueError('PRODUCTION_PLANNING_OR_ACTUAL_SOURCE_DRIFT')
        bypath[r['path']]=r
    merged=list(bypath.values())
    return receipt,dict(files=merged,source_sha=digest(merged),science_version='RELEASE_PRODUCTION_ORIGINAL_CURRENT_AC_V1')


def run_production_actual(*,context,a_result,a_acceptance,m_result,m_acceptance,output,slots=96,gate):
    proof=require_actual_gates(context,a_result,a_acceptance,m_result,m_acceptance,slots=slots,gate=gate)
    output=Path(output)
    if output.exists() and any(output.iterdir()):raise FileExistsError('PRODUCTION_ACTUAL_MUST_NOT_OVERWRITE')
    output.mkdir(parents=True,exist_ok=True)
    # Importing/calling private preparation is deliberately below every gate.
    from .release_private_actual_inputs import prepare_private_actual_inputs
    private_context=dict(context,private_actual_preparation_gate=proof)
    private=prepare_private_actual_inputs(private_context,output=output/'PRIVATE_INPUTS',slots=slots)
    args=dict(private['arguments']);environment=args['environment']
    from .release_date_execution import compile_date_commands, require_date_actual_handoff
    commands=compile_date_commands(a_result,context);args['known_schedule']=commands
    bridge,identity=_resource_bridge(context,a_result,args['capacities'])
    handoff=require_date_actual_handoff(a_result,context,args,identity=identity)
    policy_spec=proof['actual_policy'];mess=m_result['mess']
    actual_source,freeze=_actual_source(context,private,policy_spec,output)
    packet,reference,bindings=_physical_packet(context,a_result,mess,args,commands,policy_spec)
    from .production_case import ARCHIVE
    from .actual_validation import read,_validated_hardware_context
    campaign=read(ARCHIVE/'CAMPAIGN_MANIFEST.json')
    from .release_date_ac import DatePrefixCachedCurrentAC,DateResearchCurrentAC
    oracle_class=DatePrefixCachedCurrentAC if policy_spec['mode']=='SOURCE_STRICT' else DateResearchCurrentAC
    oracle=oracle_class(begin=args['begin'],sites=packet.sites,power_model=args['power_model'],
        observations=private['observations'],source_freeze=freeze,manifest=campaign,mess=mess,
        proof_records=actual_source['files'])
    kw=dict(variant=policy_spec['variant'],oracle=oracle,bindings=bindings,expected_bindings=bindings,
        evidence_scope='REAL_PRODUCTION',source_identity=dict(planning_identity=identity,study_case_sha=proof['evaluation_case_sha']),
        site_authority=initial_authority(bindings,proof['evaluation_case_sha']))
    if policy_spec['mode']=='SOURCE_STRICT':policy=ReleasePolicy(reference,packet,**kw)
    else:
        from .research_presite_contract import ResearchPresiteProvider
        from .research_presite_transfer_literature import LiteratureTransferProvider, PAYLOAD_MODEL
        spec=_read(policy_spec['research_contract'])
        provider_type=LiteratureTransferProvider if spec.get('payload_model')==PAYLOAD_MODEL else ResearchPresiteProvider
        provider=provider_type(spec,native_wan=context['data'][0]['WAN'])
        policy=ProductionResearchPolicy(reference,packet,research_provider=provider,
            source_authority_lookup=private['source_authority_lookup'],**kw)
    policy.spec.update(release_scope='REAL_PRODUCTION_CURRENT_ACCEPTED_D0_A2_M2',
        scheduling='IMMUTABLE_CURRENT_D0_A2_COMMANDS_NO_HISTORICAL_REFERENCE_FALLBACK',
        evaluation_case_sha=proof['evaluation_case_sha'],actual_policy=policy_spec,
        frozen_affine_is_runtime_admission_or_ranking_authority=False)
    policy.sha=digest(policy.spec);_bind_driver_current_c1(policy,args);policy.save(output/'FROZEN_POLICY.json')
    obs=private['observations'];args.update(arm='B3',frozen_policy=policy,expected_bindings=bindings,
        weather=[obs.at(args['begin']+t*900,observed_now=args['begin']+t*900)['weather']['values'] for t in range(slots)])
    def controller(*a,**kw):
        return ProductionCurrentController(*a,resource_bridge=bridge,actual_identity=identity,
            initial_pending={r['uid']:r for r in context['state']['pending']},backlog_contract=context['backlog'],**kw)
    from .isolated_unknown import no_native
    memory_gate();began=perf_counter()
    with no_native() as attempts, _validated_hardware_context(freeze,campaign):
        result=run_actual(**args,controller_class=controller)
    if args['environment'] is not environment or attempts:raise ValueError('PRODUCTION_PRIVATE_ENVIRONMENT_OR_NATIVE_GUARD_DRIFT')
    state=result['carryout']['controller']['production_state'];prefix=state['prefix']
    np.testing.assert_allclose(result['occupancy_GPU'],[r['GPU'] for r in prefix],rtol=0,atol=1e-10)
    np.testing.assert_allclose(result['physical']['PCC_P_kw'],[r['P'] for r in prefix],rtol=0,atol=1e-9)
    np.testing.assert_allclose(result['physical']['PCC_Q_kvar'],[r['Q'] for r in prefix],rtol=0,atol=1e-9)
    trace=output/'ACTUAL_OCCUPANCY_POWER_TRACE.npz'
    np.savez_compressed(trace,sites=result['sites'],timestamps_start_epoch_seconds=np.arange(args['begin'],args['end'],900),
        GPU=result['occupancy_GPU'],compute_GPU=result['compute_occupancy_GPU'],**result['physical'])
    for name,value in dict(PUBLIC_EPISODE_STATE=result['carryout']['controller'],CURRENT_CANDIDATE_AC_LEDGER=oracle.audit,
            CONDITIONAL_PUBLIC_Q50_PREDICTION_LEDGER=oracle.prediction_audit,CONTROL_TICK_TIMINGS=state['control_tick_timings'],
            INITIAL_PLACEMENT_LEDGER=policy.initial_events,ACTUAL_START_LEDGER=state['actual_starts'],
            PENDING_PRE_SITE_LEDGER=policy.candidate_events,KNOWN_CORRECTIVE_PREPLACEMENT=result['carryout']['controller']['current_event_state'],
            QOS_ACTUAL_LEDGER=result['qos_ledger'],QUEUE_LEDGER=result['queue_ledger'],JOB_EVENT_LEDGER=result['job_event_ledger'],
            CC4_RESOURCE_BRIDGE=bridge.export()).items():_write(output/(name+'.json'),value)
    if hasattr(policy,'research'):_write(output/'RESEARCH_DATA_ACCESS_LEDGER.json',policy.research.export())
    receipt=dict(schema='RELEASE_PRODUCTION_ACTUAL_EXECUTION_V1',status='EXECUTED_NOT_FRESH_CERTIFIED',fixture=False,
        day=source_case(context)['day'],source_sha=context['manifest']['source_sha'],source_identity=context['manifest']['identity'],
        evaluation_case_payload=proof['evaluation_case_payload'],evaluation_case_sha=proof['evaluation_case_sha'],
        actual_policy=policy_spec,research_contract=policy_spec.get('research_contract'),
        initial_state_sha=identity['initial_state_sha'],**{k:proof['evaluation_case_payload'][k] for k in
            ('A2_result_sha','A2_acceptance_sha','M2_result_sha','M2_acceptance_sha')},
        MESS_plan_sha=mess['plan_sha'],commands_sha=digest(commands),executed_actual_slots=slots,
        actual_trace=file_record(trace),actual_specific_source_freeze=file_record(output/'PRODUCTION_ACTUAL_SOURCE_FREEZE.json'),
        initial_state_join=handoff['actual_initial_state_join'],handoff=handoff,
        private_Environment_identity_preserved=True,Actual_global_MILP_calls=0,Original_event_driver_reused=True,
        projection_receipt=private['projection_receipt'],actual_wall_seconds=perf_counter()-began,
        raw_folder=str(private['raw_folder']),receipt=result['receipt'],Gate_contract=CONTRACT,
        Source_planning_13_modified=False,ASOF_substep_diagnostic_is_official_veto=False)
    if any(file_record(r['path'])!=r for r in actual_source['files']):raise ValueError('PRODUCTION_ACTUAL_SOURCE_CHANGED_DURING_EXECUTION')
    failures=[k for k in ('capacity_violations','dropped_jobs','future_duration_controller_reads',
        'future_completion_controller_reads','optimizer_calls','actual_global_reoptimization') if result['receipt'][k]!=0]
    tick_max=max((r['wall_seconds'] for r in state['control_tick_timings']),default=float('inf'))
    for row in result['qos_ledger']:
        if row['total_intentional_burden_seconds']>row['budget_seconds']+1e-7:
            failures.append('SHARED_INTENTIONAL_QOS_BUDGET_EXCEEDED:'+row['uid'])
    stage_ok=not failures and tick_max<900
    receipt.update(Actual_stage_PASS=stage_ok,Actual_stage_failures=failures,controller_max_seconds=tick_max,
        Fresh_AC_status='NOT_RUN',Actual_PASS_is_not_Fresh_PASS=True)
    _write(output/'PRODUCTION_ACTUAL_EXECUTION.json',receipt)
    return dict(status='FULL_PASS' if stage_ok else 'NOT_CERTIFIED',result=receipt,
        raw_records=[file_record(output/'PRODUCTION_ACTUAL_EXECUTION.json'),file_record(trace)])


def run_production_fresh(*,context,actual_result,m_result,m_acceptance,output,slots=96,gate):
    from .release_p1_production import verify_context,require_production_acceptance
    from .actual_validation import fresh_ac_minimum
    from .mess_actual import consume_frozen_mess
    verify_context(context)
    identity=context['manifest']['identity'];source=source_case(context)
    require_production_acceptance(m_acceptance,stage='M2',identity=identity,result=m_result)
    # The Actual receipt carries its exact public A2/M2 chain. Raw receipt SHA
    # and current Source material must be checked before offline truth access.
    actual=actual_result
    if (actual.get('schema')!='RELEASE_PRODUCTION_ACTUAL_EXECUTION_V1' or actual.get('fixture') is not False
            or actual.get('Actual_stage_PASS') is not True
            or actual.get('source_identity')!=identity or actual.get('source_sha')!=source['source_sha']
            or actual.get('executed_actual_slots')!=slots or actual.get('M2_result_sha')!=digest(m_result)
            or actual.get('M2_acceptance_sha')!=m_acceptance['acceptance_sha']
            or actual.get('actual_policy')!=gate.get('actual_policy_by_day',{}).get(source['day'],gate.get('actual_policy'))
            or gate.get('Gate_contract')!=CONTRACT or gate.get('official_contract_authorized') is False):
        raise ValueError('PRODUCTION_FRESH_EXACT_CURRENT_ACTUAL_AND_M2_REQUIRED')
    output=Path(output)
    if output.exists() and any(output.iterdir()):raise FileExistsError('PRODUCTION_FRESH_MUST_NOT_OVERWRITE')
    output.mkdir(parents=True,exist_ok=True)
    actual_path=Path(actual['actual_trace']['path']).parent/'PRODUCTION_ACTUAL_EXECUTION.json'
    actual_record=file_record(actual_path)
    if _read(actual_record)!=actual:raise ValueError('PRODUCTION_FRESH_RAW_ACTUAL_RECEIPT_DRIFT')
    source_freeze=_read(actual['actual_specific_source_freeze'])
    if any(file_record(r['path'])!=r for r in source_freeze['files']):raise ValueError('PRODUCTION_FRESH_ACTUAL_SOURCE_BYTES_DRIFT')
    if file_record(actual['actual_trace']['path'])!=actual['actual_trace']:raise ValueError('PRODUCTION_FRESH_TRACE_BYTES_DRIFT')
    records={r['path']:r for r in context['manifest']['source_freeze']['files']+source_freeze['files']}
    freeze=dict(files=list(records.values()),source_sha=digest(list(records.values())),science_version='RELEASE_CURRENT_PRODUCTION_FRESH_V1')
    mess=m_result['mess'];begin=context['manifest']['time_axis']['evaluation_begin_seconds']
    execution=consume_frozen_mess(mess,day_begin_seconds=begin,original_full_validated=True)
    _write(output/'MESS_ACTUAL_EXECUTION_RECEIPT.json',execution)
    from .production_case import ARCHIVE
    from .isolated_unknown import no_native
    memory_gate()
    with no_native() as attempts:
        fresh=fresh_ac_minimum(actual['raw_folder'],actual_path.parent,output/'ORIGINAL_FRESH',source_freeze=freeze,
            campaign_manifest=ARCHIVE/'CAMPAIGN_MANIFEST.json',slots=slots,mess_plan=mess,mess_execution_receipt=execution,
            trace_path=actual['actual_trace']['path'],arm='B3',case_scope=dict(partial_actual_trace_authorized=slots==16,
                evaluation_case_sha=actual['evaluation_case_sha'],common_initial_state_sha=identity['initial_state_sha']))
    rows_record=file_record(output/'ORIGINAL_FRESH/FRESH_PHYSICAL_SLOTS.json');rows=_read(rows_record)
    certificate=validate_settled_fresh(fresh,rows,day=source['day'],case_sha=actual['evaluation_case_sha'],
        initial_state_sha=identity['initial_state_sha'],mess_plan_sha=mess['plan_sha'],trace_record=actual['actual_trace'],slots=slots)
    body=dict(schema='RELEASE_PRODUCTION_SETTLED_CANARY16_V1' if slots==16 else 'RELEASE_PRODUCTION_SETTLED_FULL96_V1',
        Gate_contract=CONTRACT,status=certificate['status'],day=source['day'],source_sha=source['source_sha'],source_identity=identity,
        evaluation_case_payload=actual['evaluation_case_payload'],evaluation_case_sha=actual['evaluation_case_sha'],
        actual_policy=actual['actual_policy'],research_contract=actual.get('research_contract'),initial_state_sha=identity['initial_state_sha'],
        MESS_plan_sha=mess['plan_sha'],executed_actual_slots=slots,**{k:actual[k] for k in
            ('A2_result_sha','A2_acceptance_sha','M2_result_sha','M2_acceptance_sha')},
        raw_fresh_receipt=file_record(output/'ORIGINAL_FRESH/FRESH_PHYSICAL_RESULT.json'),raw_slot_rows=rows_record,
        raw_actual_trace=actual['actual_trace'],raw_actual_execution_receipt=actual_record,
        official_certificate=certificate,blocked_native_attempts=attempts)
    key='canary_proof_sha' if slots==16 else 'full96_proof_sha';body[key]=digest(body)
    target=output/('PRODUCTION_SETTLED_CANARY16.json' if slots==16 else 'PRODUCTION_SETTLED_FULL96.json');_write(target,body)
    return dict(status='FULL_PASS' if certificate['status']=='PASS' else 'PHYSICAL_FAIL',result=body,
        raw_records=[file_record(target),body['raw_fresh_receipt'],rows_record])

"""Declared E1/E2 controller adapter on the unchanged common event simulator."""
from copy import deepcopy
from dataclasses import asdict,fields,replace
from types import SimpleNamespace
import math
from pathlib import Path
import json,time,heapq
import numpy as np

from .actual import JobEventController,run_actual,_require_public_metadata
from .policy import digest,ReservationLedger
from .qos import ObservedJob
from .experimental_qos import ExperimentalQoSProvider,FROZEN_SEED


def prepare_conditional_arguments(strict_arguments,known_observed_records,*,scenario,
                                  participation,case_sha,seed=FROZEN_SEED,existing_provider=None):
    """Project public issue records into a separately identified research case.

    Environment and all physical quantities are passed through unchanged. The
    original immutable Planning proof is retained verbatim alongside the new
    model receipt. Known participation is issued at original Planning issue,
    using UID identity when no issue-time public episode was frozen.
    """
    strict=strict_arguments['qos_window_provider']
    provider=existing_provider or ExperimentalQoSProvider(strict,scenario=scenario,participation=participation,
        case_sha=case_sha,provider_sha=strict.provider_sha,seed=seed)
    if (provider.case_sha!=case_sha or provider.scenario!=scenario or provider.participation!=participation
            or provider.provider_sha!=strict.provider_sha):
        raise ValueError('EXPERIMENTAL_ISSUE_PROVIDER_BINDING_DRIFT')
    arguments=dict(strict_arguments)
    arguments['qos_window_provider']=provider
    if scenario=='E0':
        return dict(arguments=arguments,new_qos_provider=provider,
            projection_receipt=dict(scenario='E0',strict_input_projection=False,
                source_case_sha=strict.case_sha,case_sha=case_sha,private_environment_unchanged=True))
    if case_sha==strict.case_sha:
        raise ValueError('EXPERIMENTAL_CONTRACT_REQUIRES_NEW_CASE_IDENTITY')
    records={}
    for uid,value in known_observed_records.items():
        job=value if isinstance(value,ObservedJob) else ObservedJob(**{
            f.name:value[f.name] for f in fields(ObservedJob) if f.name in value})
        if uid!=job.uid or job.origin_unknown or job.provider_sha!=strict.provider_sha:
            raise ValueError('ORIGINAL_KNOWN_ISSUE_OBSERVATION_REQUIRED')
        _require_public_metadata(asdict(job))
        provider.register_observed(uid)  # Issue-time UID fallback, frozen once.
        records[uid]=job
        provider.issue(job)
    projected={};rows=[]
    def project(request):
        if request.uid in projected:return projected[request.uid]
        raw=deepcopy(request.metadata)
        _require_public_metadata(raw)
        raw['experimental_prediction_Q50_seconds']=float(request.q50)
        # A later DD00 model episode is not an issue-time public episode.
        # The prereregistered May issue/submit receipts use UID fallback.
        raw['experimental_participation_episode_id']=None
        if raw.get('origin_unknown') is False:
            if request.uid not in records:
                raise ValueError('EXPERIMENTAL_KNOWN_ISSUE_RECORD_MISSING')
            job=records[request.uid];receipt=provider.receipts[request.uid]
            if (job.gpu!=request.gpu or job.submit_seconds!=request.submit
                    or job.t50_seconds!=request.q50):
                raise ValueError('EXPERIMENTAL_PUBLIC_REQUEST_CHANGED')
            old_proof=deepcopy(raw.get('reused_planning_qos_authority'))
            if old_proof is not None:raw['original_source_planning_authority']=old_proof
            raw['reused_planning_qos_authority']=dict(uid=request.uid,case_sha=provider.case_sha,
                provider_sha=provider.provider_sha,stats_sha=provider.stats.sha,
                reference_sha=receipt.reference_sha,authority_sha=receipt.authority_sha,gpu=request.gpu)
            rows.append(dict(uid=request.uid,issued_at_seconds=receipt.issued_at_seconds,
                original_authority_sha=job.authority_sha,experimental_receipt_sha=digest(receipt.to_dict()),
                original_source_planning_authority=old_proof,observed_source_SLA_changed=False))
        projected[request.uid]=replace(request,metadata=raw)
        return projected[request.uid]
    arguments['requests']=[project(r) for r in strict_arguments.get('requests',[])]
    arguments['running']=[(project(r),site,start) for r,site,start in strict_arguments.get('running',[])]
    receipt=dict(policy_id='V42_EXPERIMENTAL_FLEXIBLE_QOS_CONTROL_V1',scenario=scenario,
        participation=participation,source_case_sha=strict.case_sha,case_sha=case_sha,
        source_provider_sha=strict.provider_sha,experimental_spec_sha=provider.stats.sha,
        Known_issue_record_count=len(records),Known_active_projected_count=len(rows),
        Known_issuer_records_sha=digest({uid:asdict(j) for uid,j in records.items()}),
        projected_proofs=rows,private_environment_unchanged=True,
        historical_starts_sites_gpu_Q50_unchanged=True,original_raw_files_modified=False,
        source_contract_and_model_contract_separate=True,fixed_A2_M2_conditional_scope=True,
        new_Known_domain_optimized=False)
    receipt['projection_sha']=digest(receipt)
    return dict(arguments=arguments,new_qos_provider=provider,projection_receipt=receipt)


class ExperimentalReservationLedger(ReservationLedger):
    """Nominal first booking; the physical EpisodeLedger always keeps Running.

    Only E1/E2 instantiate this class. The first initial observed Running hold
    forecasts public Q50 minus observed elapsed, with at least the current
    control slot retained. Later observed overruns extend the physical hold.
    """
    def __init__(self,owner,**kwargs):
        super().__init__(**kwargs);self.owner=owner
        self._resource_view_generation=0
        self._resource_views={}
        self.resource_view_cache_hits=0;self.resource_view_cache_misses=0

    def invalidate_resource_views(self):
        """All production mutations use the overridden atomic Base methods.

        A test/manual direct reservation mutation must explicitly invalidate;
        experimental continuation with arbitrary imported state fails closed.
        """
        with self._lock:
            self._resource_view_generation+=1
            self._resource_views.clear()

    def _fits(self,segments,*,exclude=None,envelope=None,scope='physical'):
        with self._lock:
            resources=frozenset(seg['resource'] for seg in segments)
            key=(self._resource_view_generation,resources)
            view=self._resource_views.get(key)
            if view is None:
                rows={}
                for uid,row in self.reservations.items():
                    matching=[seg for seg in row['segments'] if seg['resource'] in resources]
                    if matching:rows[uid]=dict(row,segments=matching)
                view=SimpleNamespace(capacities=self.capacities,reservations=rows)
                self._resource_views[key]=view
                if len(self._resource_views)>128:self._resource_views.pop(next(iter(self._resource_views)))
                self.resource_view_cache_misses+=1
            else:self.resource_view_cache_hits+=1
            # Invoke the literal original algorithm on the same query segments.
            # Only irrelevant existing resources have been removed; peer order,
            # endpoints, scopes, capacities, WAN and global transfer math persist.
            return ReservationLedger._fits(view,segments,exclude=exclude,envelope=envelope,scope=scope)

    def reserve(self,*args,**kwargs):
        with self._lock:
            result=super().reserve(*args,**kwargs)
            if result[0]:self.invalidate_resource_views()
            return result

    def activate(self,*args,**kwargs):
        with self._lock:
            result=super().activate(*args,**kwargs)
            self.invalidate_resource_views()
            return result

    def release(self,*args,**kwargs):
        with self._lock:
            result=super().release(*args,**kwargs)
            self.invalidate_resource_views()
            return result

    def retain_running(self,uid,site,now,next_control,gpu):
        with self._lock:
            metadata=self.owner.metadata.get(uid,{})
            if uid not in self.reservations and metadata.get('state')=='RUNNING':
                self.owner._overlay(uid,'RUNNING')
                request=self.owner.requests[uid]
                elapsed=metadata.get('accumulated_compute_seconds',0)
                next_control=max(now+max(0.,request.q50-elapsed),math.floor(now/900)*900+900)
                metadata['experimental_initial_nominal_reservation_end_seconds']=float(next_control)
                metadata['experimental_initial_reservation_basis']='PUBLIC_Q50_MINUS_OBSERVED_ELAPSED_MIN_NEXT_CONTROL'
                metadata['initial_booking_is_actual_completion_prediction']=False
            result=super().retain_running(uid,site,now,next_control,gpu)
            self.invalidate_resource_views()
            return result

class ExperimentalJobEventController(JobEventController):
    def __init__(self,*args,**kwargs):
        legacy_diagnostic=kwargs.pop('legacy_diagnostic',False)
        provider=kwargs['qos_window_provider'];policy=kwargs.get('frozen_policy')
        authority=getattr(policy,'migration_authority',None)
        if provider.scenario!='E0' and authority:
            inherited=dict(kwargs.get('wan_capacities') or {})
            proposed=authority['wan_capacities']
            if any(key in inherited and inherited[key]!=value for key,value in proposed.items()):
                raise ValueError('EXPERIMENTAL_WAN_SOURCE_CAPACITY_DRIFT')
            kwargs['wan_capacities']={**inherited,**proposed}
        super().__init__(*args,**kwargs)
        self.experimental=self.qos.scenario!='E0'
        self.experimental_events=[]
        self._public_submission_generation=0
        self._context_cache_key=None;self._context_cache_value=None
        self.observed_context_cache_hits=0
        if self.experimental:
            if self.policy is None:raise ValueError('EXPERIMENTAL_SIGNED_GRID_SELECTOR_REQUIRED')
            if not getattr(self.policy,'lookup_only',False) and not legacy_diagnostic:
                raise ValueError('UNKNOWN_ACTUAL_FROZEN_LOOKUP_ONLY_REQUIRED')
            if getattr(self.policy,'lookup_only',False):
                from .reservation_state import ContractReservationLedger
                self.reservations=ContractReservationLedger(self,capacities=self.ledger.capacities,
                    wan_capacities=kwargs.get('wan_capacities'))
            else:
                self.reservations=ExperimentalReservationLedger(self,capacities=self.ledger.capacities,
                    wan_capacities=kwargs.get('wan_capacities'))
            self.frozen_known_schedule=deepcopy(self.known_schedule)
            # Issue-time Known commands remain immutable, including unmodeled
            # Known reference fallbacks. Only Unknown enters conditional lookup.

    def submit(self,request,now):
        if self.experimental:
            context=self.qos.contexts.get(request.uid)
            if context is None:
                episode=request.metadata.get('experimental_participation_episode_id',request.metadata.get('episode_id'))
                self.qos.register_observed(request.uid,episode_id=episode,
                    source_authority=request.metadata.get('source_qos_authority'))
        super().submit(request,now)
        self._public_submission_generation+=1
        if self.experimental:
            self._overlay(request.uid,self.observed[request.uid].state)
            self.metadata[request.uid]['original_raw_request_metadata']=deepcopy(request.metadata)
            self.metadata[request.uid]['experimental_prediction_Q50_seconds']=float(request.q50)
            if (getattr(self.policy,'lookup_only',False) and request.uid in self.known_schedule
                    and request.uid not in self.reservations.known_plans):
                command=self.known_schedule[request.uid]
                boundary=self.metadata[request.uid].get('dday_initialization_seconds',self.policy.packet.begin_seconds)
                if command['start_seconds']>=boundary:
                    self.reservations.install_known(request.uid,[dict(resource='gpu:'+command['site'],
                        begin=command['start_seconds'],end=command['start_seconds']+max(request.q50,1e-9),quantity=request.gpu)])

    def _overlay(self,uid,state):
        overlay=self.qos.metadata_overlay(self.observed[uid],self.budgets[uid],state=state)
        raw=self.requests[uid].metadata
        source_preplace=raw.get('can_prestart_place') is True and state=='PENDING'
        overlay['Can_Preplace']=overlay['Can_Preplace'] or source_preplace
        overlay['can_prestart_place']=overlay['can_prestart_place'] or source_preplace
        overlay['preplace_authority_classes']=([
            'ORIGINAL_MODEL_INITIALIZER_APPROVED'] if source_preplace else [])+([
            'ASSUMED_EXPERIMENTAL_PARTICIPATION'] if self.budgets[uid].participant
                and self.budgets[uid].eligible_for_contract and state=='PENDING' else [])
        overlay['source_preplace_is_observed_Kestrel_SLA']=False
        self.metadata[uid].update(overlay)

    def _observed_context(self,now,observed_use=None):
        use=self.ledger.physical(now) if observed_use is None else dict(observed_use)
        if getattr(self.policy, 'lookup_only', False):
            self.policy.set_current_resources(now, use)
            return use
        # Within a serial pass, submission/start are the only pending mutations.
        # A start changes both pending count and physical use. No cache survives
        # a changed public clock, forecast depletion, or submission generation.
        forecast_key=None if self.forecast is None else (tuple(self.forecast.q50),tuple(self.forecast.q90),
            tuple(sorted(self.forecast.consumed.items())),len(self.cc4_ledger))
        key=(float(now),tuple(sorted(use.items())),len(self.pending),self._public_submission_generation,forecast_key)
        if key==self._context_cache_key:
            self.observed_context_cache_hits+=1
            return use
        work={uid:self.requests[uid].gpu*max(0.,self.requests[uid].q50)/3600
              for _,uid in self.pending}
        if self.forecast is None:
            q50=self.policy.q50.tolist();q90=self.policy.q90.tolist();depletion=dict(available=False)
        else:
            q50=[];q90=[]
            for hour in range(24):
                row=self.forecast.row(hour,now)
                q50.append(row['remaining_CC4_Q50_GPUh']);q90.append(row['remaining_CC4_Q90_GPUh'])
            depletion=dict(available=True,as_of_seconds=now,
                original_Q50_GPUh=sum(self.forecast.q50),original_Q90_GPUh=sum(self.forecast.q90),
                remaining_Q50_GPUh=sum(q50),remaining_Q90_GPUh=sum(q90),
                assigned_forecast_Q90_nominal_GPUh=sum(self.forecast.q90)-sum(q90),
                CC4_depletion_UIDs=len(self.cc4_ledger),no_future_UID_or_completion_values=True)
        self.policy.set_observed_context(now=now,observed_gpu=use,pending_nominal_work=work,
            remaining_q50=q50,remaining_q90=q90,forecast_depletion=depletion)
        self._context_cache_key=key
        return use

    def _policy_resource_guard(self,now,*,lookup_at=None,observed_use=None):
        if not self.experimental:return super()._policy_resource_guard(now,lookup_at=lookup_at,observed_use=observed_use)
        use=self._observed_context(now,observed_use)
        # Forecast support is a diagnostic. Actual reservation feasibility and
        # original Q50 grid rows remain candidate-specific hard checks.
        context=dict(observed_at_seconds=now,observed_GPU_by_site=use,
            observed_resource_sha=digest(use),forecast_deviation_is_not_blanket_veto=True,
            grid_safety_guaranteed=False,source='CURRENT_EPISODE_LEDGER_NOT_FUTURE_ACTUAL')
        if getattr(self.policy,'lookup_only',False):
            return None,context
        slot=int((now-self.policy.packet.begin_seconds)//900)
        if 0<=slot<96:
            baseline=self.policy.packet.known_gpu[slot]+self.policy.frozen_anonymous[slot]
            context['observed_GPU_deviation_from_frozen_Q50_by_site']={
                site:float(use[site]-baseline[i]) for i,site in enumerate(self.policy.packet.sites)}
            context['original_frozen_resource_baseline_sha']=digest(baseline.tolist())
        self.experimental_events.append(deepcopy(context))
        return None,context

    def _reference_decision(self,uid,now):
        if self.experimental:
            selected=self.policy.last_selection.get(uid,{})
            if selected.get('physical_or_Q50_veto'):
                return dict(uid=uid,action='QUEUE',status='EXPERIMENTAL_HARD_GUARD_FALLBACK_RETAINS_QUEUE',
                    reason=selected.get('reason'),grid_safety_guaranteed=False)
        return super()._reference_decision(uid,now)

    def admit(self,now):
        if self.experimental and now%900==0:
            # A delayed command remains the same command until due. At start,
            # recheck its actual nominal profile against newly observed holds;
            # an overrun cannot silently change the scored start interval.
            for _,uid in sorted(self.pending):
                if not self.metadata[uid]['origin_unknown']:continue
                decision=self.decisions.get(uid)
                if decision is None or decision['action']=='QUEUE' or decision['start_seconds']>now:continue
                self._observed_context(now)
                metadata=self.metadata[uid]
                segment=[dict(resource='gpu:'+decision['site'],begin=now,
                    end=now+max(self.requests[uid].q50,1e-9),quantity=self.requests[uid].gpu)]
                if getattr(self.policy, 'lookup_only', False):
                    reason=self.policy.current_guard(metadata,segment,now,self.ledger.physical(now))
                    if reason is None:reason=self.reservations.feasible(segment,exclude=uid)
                    self._event(uid,now,'FROZEN_COMMAND_CURRENT_GUARD_REVALIDATED',passed=reason is None,
                        reason=reason,online_grid_horizon_evaluations=0)
                    if reason:
                        metadata['additional_start_delay_seconds']=max(metadata.get('additional_start_delay_seconds',0),
                            decision.get('additional_start_delay_seconds',0))
                        self.decisions[uid]=self.policy.revalidate_command(metadata,self.budgets[uid],now,
                            self.reservations,decision,self.ledger.physical(now),failure_reason=reason)
                    continue
                reason=self.policy._rack_reason(metadata,decision['site'])
                window=decision.get('execution_window_receipt')
                if window is not None and (now>window['latest_start_seconds'] or now not in window['allowed_starts_seconds']):
                    reason='FROZEN_EXPERIMENTAL_EXECUTION_WINDOW_EXPIRED'
                if reason is None:reason=self.reservations.feasible(segment,exclude=uid)
                score=None
                if reason is None:
                    score,reason=self.policy._score(metadata,segment,now,self.reservations,replace=True,
                        reference_segments=decision.get('reference_segments'))
                    if reason is None and not score['q50_hard_feasible']:reason='CURRENT_Q50_ORIGINAL_HARD_ROWS_REVALIDATION_FAILED'
                self._event(uid,now,'EXPERIMENTAL_COMMAND_REVALIDATED',passed=reason is None,
                    reason=reason,previous_scheduled_start_seconds=decision['start_seconds'],
                    actual_nominal_start_seconds=now,Q50_prediction_only=True,Fresh_AC_status='NOT_RUN')
                if reason is not None:
                    # Planned intentional waiting already elapsed. Cancellation
                    # cannot refund or renew that shared immutable budget.
                    metadata['additional_start_delay_seconds']=max(metadata['additional_start_delay_seconds'],
                        decision.get('additional_start_delay_seconds',0))
                    self.reservations.release(uid,now)
                    self.decisions[uid]=self.policy._terminal(metadata,now,'QUEUE',
                        'CACHED_COMMAND_CURRENT_HARD_GUARD_REJECTED',reason)
        blocked=[entry for entry in self.pending if self.decisions.get(entry[1],{}).get('revalidated_at_seconds')==now
            and self.decisions[entry[1]].get('status')=='ALL_SAME_ROW_FROZEN_ALTERNATIVES_INFEASIBLE']
        if blocked:
            self.pending=[entry for entry in self.pending if entry not in blocked];heapq.heapify(self.pending)
        try:return super().admit(now)
        finally:
            for entry in blocked:heapq.heappush(self.pending,entry)

    def snapshot(self,now):
        result=super().snapshot(now)
        if self.experimental:
            state=dict(policy_sha=self.policy.sha,case_sha=self.qos.case_sha,
                references=deepcopy(self.policy.references),observed_blocks=deepcopy(self.policy.observed_blocks),
                reference_audit=deepcopy(self.policy.reference_audit),
                continuation_status='NOT_SUPPORTED_FAIL_CLOSED_FIXED_ONE_DAY_ANCHOR')
            if getattr(self.policy,'lookup_only',False):state['active_service_frame_id']=self.policy.active_service_frame_id
            state['runtime_state_sha']=digest(state)
            result['experimental_runtime_state']=state
        return result

    def restore(self,snapshot):
        if self.experimental:
            raise ValueError('EXPERIMENTAL_CONTINUATION_NOT_SUPPORTED_NO_REFERENCE_RENEWAL')
        return super().restore(snapshot)

    def migration(self,uid,now,physical_checkpoint):
        if self.experimental:
            self._overlay(uid,'RUNNING')
        return super().migration(uid,now,physical_checkpoint)


def run_experimental_actual(capacities,requests,environment,*,qos_window_provider,frozen_policy,
                            arm='B3',legacy_diagnostic=False,**kwargs):
    """Causal counterfactual Actual; all private service stays in Environment."""
    if qos_window_provider.scenario=='E0':
        result=run_actual(capacities,requests,environment,arm=arm,qos_window_provider=qos_window_provider,
            frozen_policy=frozen_policy,**kwargs)
    else:
        if not getattr(frozen_policy,'lookup_only',False) and not legacy_diagnostic:
            raise ValueError('UNKNOWN_ACTUAL_FROZEN_LOOKUP_ONLY_REQUIRED')
        if legacy_diagnostic:
            from functools import partial
            controller_class=partial(ExperimentalJobEventController,legacy_diagnostic=True)
        else:controller_class=ExperimentalJobEventController
        result=run_actual(capacities,requests,environment,arm=arm,qos_window_provider=qos_window_provider,
            frozen_policy=frozen_policy,controller_class=controller_class,**kwargs)
    result['experimental_scope']=dict(policy_id='V42_EXPERIMENTAL_FLEXIBLE_QOS_CONTROL_V1',
        scenario=qos_window_provider.scenario,participation=qos_window_provider.participation,
        fixed_A2_M2_conditional_replay=True,new_A_M_optimality=False,
        Actual_Maximum_Line_Loading=None,Fresh_AC='NOT_RUN',Native_Optimize_calls=0,
        observed_source_or_raw_contract_fields_modified=False,
        new_Known_contract_domain_optimized=False)
    result['experimental_scope'].update(legacy_online_selector_diagnostic=legacy_diagnostic,
        integrated_contract_performance_eligible=False,
        Unknown_lookup_only=getattr(frozen_policy,'lookup_only',False))
    if qos_window_provider.scenario!='E0':
        result['experimental_candidate_audit']=deepcopy(frozen_policy.audit)
        result['experimental_reference_audit']=deepcopy(frozen_policy.reference_audit)
        completed_or_started={r['job_uid'] for r in result['queue_ledger'] if r.get('admitted_time') is not None}
        meta=result['carryout']['controller']['metadata']
        end=kwargs.get('end',86400)
        pending_risk=[]
        for uid,ref in frozen_policy.references.items():
            if uid in completed_or_started:continue
            delay=float(meta[uid].get('additional_start_delay_seconds',0))
            pause=float(meta[uid].get('cumulative_migration_interruption_seconds',0))
            deadline=ref['reference_start_seconds']+qos_window_provider.receipts[uid].budget_seconds-ref['intentional_burden_at_reference_seconds']-pause
            advances=[r for r in frozen_policy.reference_audit if r['uid']==uid and r['event']=='OBSERVED_PHYSICAL_REFERENCE_ADVANCE']
            pending_risk.append(dict(uid=uid,first_causal_reference_start_seconds=ref['first_reference_start_seconds'],
                current_causal_reference_start_seconds=ref['reference_start_seconds'],evaluation_end_seconds=end,
                elapsed_since_first_feasible_reference_seconds=max(0,end-ref['first_reference_start_seconds']),
                assumed_budget_seconds=qos_window_provider.receipts[uid].budget_seconds,
                committed_intentional_delay_seconds=delay,cumulative_migration_interruption_seconds=pause,
                current_execution_deadline_seconds=deadline,contract_overdue_at_end=end>deadline,
                observed_physical_reference_advance_count=len(advances),
                physical_resource_wait_seconds=sum(r['new_reference_start_seconds']-r['old_reference_start_seconds']
                    for r in advances if r['wait_class']=='OBSERVED_PHYSICAL_RESOURCE_WAIT'),
                grid_required_wait_seconds=sum(r['new_reference_start_seconds']-r['old_reference_start_seconds']
                    for r in advances if r['wait_class']=='GRID_REQUIRED_WAIT'),
                unsupported_policy_wait_not_hidden_as_capacity=True,source_observed_whole_SLA_certified=False))
        result['experimental_pending_contract_risk']=pending_risk
        result['experimental_policy_metrics']=dict(events=len(frozen_policy.audit),
            bounded_event_score_calls=sum(r['signed_packet_evaluation_calls'] for r in frozen_policy.audit),
            event_median_seconds=float(np.median(frozen_policy.times)) if frozen_policy.times else None,
            event_P95_seconds=float(np.percentile(frozen_policy.times,95)) if frozen_policy.times else None,
            online_global_optimizer_calls=0,causal_SourceReplay=True)
    return result


def run_conditional_case(source,*,scenario,participation,algorithm,case_sha,
                         source_freeze_sha,output=None,end_slots=96,unknown_conditions=None,service_reallocation=False):
    """Execute one independently initialized causal fixed-anchor experiment.

    The loader supplies future service solely through its private Environment.
    Short benchmark horizons are explicitly partial and cannot certify Full96.
    """
    if not 1<=end_slots<=96:raise ValueError('CONDITIONAL_REPLAY_SLOT_SCOPE')
    if scenario!='E0' and any(k not in source for k in ('nominal_service','train_cdf_lower','train_cdf_upper','recourse_source_authority')):
        raise ValueError('LITERAL_A2_NOMINAL_AND_ORIGINAL_TRAIN_CDF_RECOURSE_REQUIRED')
    prepared,planning=source['fresh_actual_inputs']()
    known={uid:row['observed'] for uid,row in planning['known_receipts'].items()}
    projection=prepare_conditional_arguments(prepared['arguments'],known,scenario=scenario,
        participation=participation,case_sha=case_sha)
    arguments=projection['arguments'];provider=projection['new_qos_provider']
    original_known_schedule=source['known_commands']
    arguments['known_schedule']=deepcopy(original_known_schedule)
    arguments['arm']='B3'
    arguments['end']=arguments['begin']+900*end_slots
    if arguments.get('weather') is not None:
        arguments['weather']=arguments['weather'][:end_slots]
    if scenario=='E0':
        selector=source['original_policy']
    else:
        from .experimental_policy import load_experimental_migration_authority
        from .frozen_unknown import compile_unknown_policy,coverage_grammar
        bindings=dict(source['bindings'],case_sha=case_sha,qos_sha=provider.stats.sha,
            science_sha=source_freeze_sha)
        if algorithm!='GRID_SENSITIVITY_AWARE':raise ValueError('LEGACY_ABLATIONS_DIAGNOSTIC_ONLY')
        packet=deepcopy(source['packet']);packet.bindings=bindings
        selector=compile_unknown_policy(packet,bindings,qos_provider=provider,
            nominal_service=source['nominal_service'],q90_hourly=source['q90_hourly'],
            timing_lower=source['train_cdf_lower'],timing_upper=source['train_cdf_upper'],
            source_authority=source['recourse_source_authority'],
            conditions=coverage_grammar(packet) if unknown_conditions is None else unknown_conditions,
            envelope=source['original_policy'].document['envelope'],
            migration_authority=load_experimental_migration_authority(),service_reallocation=service_reallocation)
    arguments['frozen_policy']=selector
    arguments['expected_bindings']=selector.bindings
    started=time.perf_counter()
    result=run_experimental_actual(**arguments)
    result['conditional_case']=dict(scenario=scenario,participation=participation,algorithm=algorithm,
        effective_algorithm='STRICT_SOURCE_BASELINE_ALIAS' if scenario=='E0' else algorithm,
        E0_algorithm_alias=scenario=='E0',
        case_sha=case_sha,source_freeze_sha=source_freeze_sha,policy_sha=selector.sha,
        issuer_spec_sha=provider.stats.sha,projection_sha=projection['projection_receipt'].get('projection_sha'),
        begin_seconds=arguments['begin'],end_seconds=arguments['end'],slots=end_slots,
        Full96=end_slots==96,wall_seconds=time.perf_counter()-started,
        execution_kind='CAUSAL_EVENT_COUNTERFACTUAL',selected_actions_executed=True,
        fixed_A2_M2=True,new_Known_domain_optimized=False,source_observed_SLA_claim=False,
        Actual_Maximum_Line_Loading=None,Fresh_AC_status='NOT_RUN',Native_Optimize_calls=0)
    if output is not None:
        destination=Path(output);destination.mkdir(parents=True,exist_ok=True)
        arrays={k:result[k] for k in ('occupancy_GPU','compute_occupancy_GPU')}
        for key,value in (result.get('physical') or {}).items():
            if isinstance(value,np.ndarray):arrays['physical_'+key]=value
        np.savez_compressed(destination/'ACTUAL_PHYSICAL_ARRAYS.npz',**arrays)
        def serial(value):
            if isinstance(value,np.ndarray):return value.tolist()
            if isinstance(value,np.generic):return value.item()
            raise TypeError(type(value).__name__)
        for name,value in (('CONDITIONAL_ACTUAL_RESULT.json',result),
            ('INPUT_MODEL_PROJECTION.json',projection['projection_receipt']),
            ('EXPERIMENTAL_QOS_RECEIPTS.json',provider.to_dict()),
            ('EXPERIMENTAL_CONTROL_POLICY.json',selector.document)):
            (destination/name).write_text(json.dumps(value,default=serial,ensure_ascii=False,
                sort_keys=True),encoding='utf-8')
        from hashlib import sha256
        files={p.name:sha256(p.read_bytes()).hexdigest() for p in destination.iterdir() if p.is_file()}
        (destination/'ATTEMPT_SOURCE_RESULT_RECEIPT.json').write_text(json.dumps(dict(
            source_epoch_sha=source_freeze_sha,case_sha=case_sha,result_files_sha256=files,
            Native_Optimize_calls=0,Fresh_AC_status='NOT_RUN',old_results_modified=False),sort_keys=True),encoding='utf-8')
    return result


def benchmark_conditional_event(source,*,case_sha,source_epoch_sha,output,
                                scenario='E1',participation='FLEX30',repetitions=3,participant_only=False):
    """Profile the preregistered first FCFS DD00 job; no physical execution.

    Public initial RUNNING and submitted Pending are replayed to an observed
    state only. Neither Environment values nor later arrivals are inspected.
    The target cannot be changed after seeing feasibility or grid scores.
    """
    from .experimental_policy import ExperimentalControlPolicy
    prepared,planning=source['fresh_actual_inputs']()
    projected=prepare_conditional_arguments(prepared['arguments'],
        {u:r['observed'] for u,r in planning['known_receipts'].items()},scenario=scenario,
        participation=participation,case_sha=case_sha)
    args=projected['arguments'];provider=projected['new_qos_provider'];begin=args['begin']
    bindings=dict(source['bindings'],case_sha=case_sha,qos_sha=provider.stats.sha,science_sha=source_epoch_sha)
    selector=ExperimentalControlPolicy(source['packet'],bindings,qos_provider=provider,
        q50_hourly=source['q50_hourly'],q90_hourly=source['q90_hourly'],kernel=source['kernel'],
        queue_authority=source['queue_authority'],frozen_anonymous_gpu=source['frozen_anonymous_gpu'],
        nominal_service=source['nominal_service'],train_cdf_lower=source['train_cdf_lower'],
        train_cdf_upper=source['train_cdf_upper'],recourse_source_authority=source['recourse_source_authority'])
    controller=ExperimentalJobEventController(args['capacities'],arm='B3',qos_window_provider=provider,
        frozen_policy=selector,known_schedule=source['planning_freeze']['Known_schedule'],
        reference=args.get('reference'),forecast=args.get('forecast'),wan_capacities=args.get('wan_capacities'))
    initial=sorted(args['running'],key=lambda row:(row[0].submit,row[0].uid))
    for request,site,start in initial:
        if request.uid not in controller.reference.assigned:
            controller.reference.observe_running(request,site=site,start_seconds=start,event_seconds=begin,
                elapsed_compute_seconds=request.metadata.get('elapsed_compute_seconds',begin-start))
    for request,site,start in initial:
        controller.submit(request,begin);controller.pending.remove((request.submit,request.uid))
        controller.ledger.start(request.uid,site,begin,request.metadata.get('episode_id','PUBLIC:'+request.uid))
        controller.ledger.jobs[request.uid]['start_time']=start
        controller.metadata[request.uid].update(state='RUNNING',current_site=site,
            accumulated_compute_seconds=request.metadata.get('elapsed_compute_seconds',begin-start))
        controller.reservations.retain_running(request.uid,site,begin,args['end'],request.gpu)
    heapq.heapify(controller.pending)
    observed_requests=sorted((r for r in args['requests'] if r.submit<=begin),key=lambda r:(r.submit,r.uid))
    for request in observed_requests:controller.submit(request,begin)
    if not controller.pending:raise ValueError('PREREGISTERED_FIRST_FCFS_COHORT_EMPTY')
    targets=sorted(controller.pending)
    if participant_only:targets=[row for row in targets if provider.receipts[row[1]].participant
        and provider.receipts[row[1]].eligible_for_contract]
    if not targets:raise ValueError('PREREGISTERED_FIRST_FCFS_PARTICIPANT_COHORT_EMPTY')
    uid=targets[0][1]
    rows=[]
    import cProfile,pstats,io,tracemalloc
    profiler=cProfile.Profile()
    import psutil
    process=psutil.Process();rss_before=process.memory_info().rss
    for repetition in range(repetitions):
        before=selector.packet.evaluation_calls;started=time.perf_counter()
        controller._policy_resource_guard(begin)
        decision=selector.select(controller.metadata[uid],controller.budgets[uid],begin,
            controller.reservations,reserve=False)
        rows.append(dict(repetition=repetition,wall_seconds=time.perf_counter()-started,
            decision=decision['action'],reason=decision.get('reason'),
            signed_packet_evaluations=selector.packet.evaluation_calls-before,
            same_state_cache_warm=repetition>0,process_RSS_bytes=process.memory_info().rss))
    tracemalloc.start();profiler.enable()
    controller._policy_resource_guard(begin)
    selector.select(controller.metadata[uid],controller.budgets[uid],begin,
        controller.reservations,reserve=False)
    profiler.disable()
    current,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
    stream=io.StringIO();pstats.Stats(profiler,stream=stream).sort_stats('cumulative').print_stats(25)
    result=dict(scope='NATIVE0_DD00_FIRST_FCFS_PUBLIC_STATE_SELECTOR_BENCHMARK_NOT_ACTUAL',
        source_epoch_sha=source_epoch_sha,case_sha=case_sha,scenario=scenario,participation=participation,
        target_selection=('FIRST_SORTED_PUBLIC_PARTICIPANT_SUBMIT_UID' if participant_only else 'FIRST_SORTED_OBSERVED_SUBMIT_UID')+
            '_NO_FEASIBILITY_OR_OUTCOME_RESELECTION',
        uid=uid,initial_Running=len(initial),initial_Pending=len(controller.pending),
        public_running_GPU=sum(r.gpu for r,_,_ in initial),private_Environment_reads=0,
        future_UIDs_entering_controller=0,Native_Optimize_calls=0,Fresh_AC_calls=0,
        selected_actions_executed=False,executed_actions=None,rows=rows,
        median_wall_seconds=float(np.median([r['wall_seconds'] for r in rows])),
        P95_wall_seconds=float(np.percentile([r['wall_seconds'] for r in rows],95)),
        cold_wall_seconds=rows[0]['wall_seconds'],
        warmed_same_state_wall_seconds=[r['wall_seconds'] for r in rows[1:]],
        repeated_state_benchmark_not_whole_replay_extrapolation=True,
        process_RSS_before_bytes=rss_before,process_RSS_after_bytes=process.memory_info().rss,
        Python_tracemalloc_peak_bytes=peak,profiler_top=stream.getvalue(),
        conditional_candidate_audit=selector.audit,projection_sha=projected['projection_receipt']['projection_sha'])
    destination=Path(output);destination.mkdir(parents=True,exist_ok=True)
    (destination/'CONTROL_POLICY_RUNTIME_MEMORY.json').write_text(json.dumps(result,sort_keys=True),encoding='utf-8')
    return result

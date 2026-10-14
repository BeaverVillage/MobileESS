"""Issue-time anonymous compilation; observed Unknown runtime lookup only.

Uses PR225's queue recourse and original signed response. The compiler accepts
an explicit anonymous coverage grammar, never an Actual request collection.
Coverage is recorded in full; unsupported conditions retain QUEUE/STAY.
"""
from copy import deepcopy
from pathlib import Path
import math
import time
import numpy as np

from .policy import digest, ReservationLedger, migration_guard
from .sensitivity_policy import (FrozenSensitivityPolicy, POLICY_ID, REQUIRED_BINDINGS,
                                  _profile, _json)
from .q90_policy import FrozenQueueAwarePolicy, POLICY_ID as QUEUE_ID
from .q90_recourse import evaluate_q90_recourse
from .experimental_policy import segments_gpu


def coverage_grammar(packet, *, runtime_bounds=(900., 3600., 14400., 86400., 604800.),
                     time_slots=range(96), gpu_gangs=None):
    """All source-feasible destinations and integer gangs; no top-K cut."""
    maximum=int(max(min(packet.capacities[s], max(packet.rack_compatibility[s])) for s in packet.sites))
    gangs=range(1, maximum+1) if gpu_gangs is None else tuple(gpu_gangs)
    out=[]
    for gpu in gangs:
        if type(gpu) is not int or gpu < 1:raise ValueError('WHOLE_GPU_GANG_REQUIRED')
        sites=[s for s in packet.sites if gpu<=packet.capacities[s] and gpu<=max(packet.rack_compatibility[s])]
        for state in ('PENDING','RUNNING'):
            for qos in ('normal','standby'):
                for site in sites:
                    lower=0.
                    for upper in runtime_bounds:
                        if not math.isfinite(upper) or upper<=lower:raise ValueError('ORDERED_RUNTIME_BUCKETS_REQUIRED')
                        out.append(dict(state=state,qos=qos,gpu=gpu,reference_site=site,
                            compatible_sites=sites,runtime_lower_seconds=lower,runtime_upper_seconds=float(upper),
                            time_slots=list(time_slots)))
                        lower=float(upper)
    return out


def _migration_capability(authority, source, destination, gpu):
    if not authority:return None
    routes=[(name,row) for name,row in authority['routes'].items()
            if row['source']==source and row['destination']==destination]
    # Ambiguous routing is unsupported, never choose a path without authority.
    if len(routes)!=1:return None
    name,row=routes[0]
    return dict(source_sha=authority['packet_source_sha'],checkpoint_authorized=True,
        allowed_destinations=[destination],gpu_type_confirmed=True,rack_gang_confirmed=True,
        data_residency_confirmed=True,wan_path=name,bandwidth_bytes_per_second=row['bandwidth_bytes_per_second'],
        payload_bytes=authority['scalar']['bytes_per_GPU']*gpu,
        restart_seconds=authority['scalar']['current_conservative_restart_seconds'],source_wait_seconds=0,
        source_hold_until=authority['protocol']['source_hold_until'],
        destination_hold_from=authority['protocol']['destination_hold_from'],assumption=True,
        route_links=row['links'],measured_Kestrel_capability=False)


def compile_unknown_policy(packet, bindings, *, qos_provider, nominal_service, q90_hourly,
                           timing_lower, timing_upper, source_authority, conditions,
                           envelope, migration_authority=None, service_reallocation=False,
                           evidence_kind='REAL_DATA_CONDITIONAL_POLICY_NOT_AC_CERTIFICATE'):
    """Freeze every supplied condition and candidate with robust bucket scores.

    Linear response extrema occur at service endpoints and control breakpoints.
    Q90 queue risk is assessed at those same points and mass receipts are saved.
    No model Optimize, Actual environment or individual future UID is accepted.
    """
    from .experimental_qos import SCENARIOS
    if bindings!=packet.bindings or any(not bindings.get(k) for k in REQUIRED_BINDINGS):
        raise ValueError('FINAL_A_M_SOURCE_BINDINGS_REQUIRED')
    if qos_provider.scenario not in ('E1','E2'):raise ValueError('EXPERIMENTAL_CONTRACT_REQUIRED')
    if qos_provider.case_sha!=bindings['case_sha'] or qos_provider.stats.sha!=bindings['qos_sha']:
        raise ValueError('PLANNING_QOS_CASE_BINDING_DRIFT')
    if (nominal_service['site_axis']!=list(packet.sites)
            or not np.array_equal(nominal_service['known_site_GPU'],packet.known_gpu)):
        raise ValueError('FINAL_KNOWN_NOMINAL_ANCHOR_DRIFT')
    anonymous=np.asarray(nominal_service['nominal_site_GPU'],float)
    templates=[];generated=0;began=time.perf_counter();frame_catalog={};frame_cache={}
    baseline_score=packet.evaluate(np.zeros_like(anonymous))
    for ordinal,condition in enumerate(conditions):
        if any(k in condition for k in ('uid','job_uid','future_queue','actual_end','realized_seconds')):
            raise ValueError('UNKNOWN_NOT_PRESENT_AT_PLANNING')
        allowed_fields={'state','qos','gpu','reference_site','compatible_sites',
            'runtime_lower_seconds','runtime_upper_seconds','time_slots'}
        if set(condition)-allowed_fields:raise ValueError('UNSUPPORTED_ANONYMOUS_CONDITION_FIELDS')
        lo,hi=condition['runtime_lower_seconds'],condition['runtime_upper_seconds']
        gpu=condition['gpu'];source=condition['reference_site'];state=condition['state'];qos=condition['qos']
        if not 0<=lo<hi or type(gpu) is not int or gpu<1 or state not in ('PENDING','RUNNING'):
            raise ValueError('ANONYMOUS_CONDITION_INVALID')
        sites=condition['compatible_sites']
        if source not in sites or any(s not in packet.sites or gpu>packet.capacities[s]
            or gpu>max(packet.rack_compatibility[s]) for s in sites):
            raise ValueError('SOURCE_GPU_RACK_COMPATIBILITY_REQUIRED')
        budget=SCENARIOS[qos_provider.scenario][qos]
        endpoints=sorted({max(lo,1e-9),hi}|{float(v) for v in np.arange(math.ceil(lo/900)*900,hi,900) if v>0})
        for slot in condition['time_slots']:
            if type(slot) is not int or not 0<=slot<96:raise ValueError('CONTROL_SLOT_REQUIRED')
            now=packet.begin_seconds+slot*900
            frame_key=(slot,source,gpu,hi)
            if frame_key not in frame_cache:
                from .anonymous_allocation import spatial_frames
                reserved_reference,_=_profile(packet.sites,source,slot*900,hi,gpu)
                frame_cache[frame_key]=spatial_frames(nominal_service,packet.sites,slot,
                    preserve_reference=reserved_reference) if service_reallocation else [
                    dict(frame_id='BASE',delta=np.zeros_like(anonymous),certificate=dict(Q50_CDF_and_mass_unchanged=True))]
                for frame in frame_cache[frame_key]:frame_catalog[frame['frame_id']]={k:v for k,v in frame.items() if k!='delta'}
            variants=[(s,d,None) for d in range(0,budget+1,900) for s in sites] if state=='PENDING' else [(source,0,None)]+[
                (s,0,_migration_capability(migration_authority,source,s,gpu)) for s in sites if s!=source]
            ordered=[];rejected=[];comparisons=[]
            variants=[(destination,delay,cap,frame) for destination,delay,cap in variants for frame in frame_cache[frame_key]]
            for destination,delay,cap,frame in variants:
                action=('STAY' if destination==source else 'CHECKPOINT_MIGRATE') if state=='RUNNING' else (
                    'PREPLACE' if destination!=source else 'DELAY' if delay else 'START_NOW')
                generated+=1;scores=[];mass=[];risk=[];profile=None;reason=None
                for service in endpoints:
                    reference,_=_profile(packet.sites,source,slot*900,service,gpu)
                    if state=='RUNNING' and destination!=source:
                        if not cap:reason='MIGRATION_CAPABILITY_UNCONFIRMED';break
                        metadata=dict(uid='__ANONYMOUS_PROTOTYPE__',origin_unknown=True,is_observed=True,state='RUNNING',
                            gpu=gpu,t50_seconds=service+1800,accumulated_compute_seconds=1800,current_site=source,
                            source_site=source,compatible_sites=sites,migration_count=0,protected=False,qos=qos,
                            batch_eligible=True,migration_capability=cap,additional_start_delay_seconds=0,
                            cumulative_migration_interruption_seconds=0)
                        receipt=dict(uid=metadata['uid'],case_sha=bindings['case_sha'],budget_seconds=budget)
                        profile,reason=migration_guard(metadata,receipt,now=now,accumulated_compute_seconds=1800,
                            destination=destination,remaining_nominal_seconds=service,
                            reservations=ReservationLedger(packet.capacities,(migration_authority or {}).get('wan_capacities')),
                            checkpoint_at=now)
                        if profile is None:break
                        reason=None
                        a,b=profile['times']['transfer_start'],profile['times']['transfer_end']
                        profile['segments'].extend(dict(resource='wan:LINK::'+link,begin=a,end=b,
                            quantity=cap['bandwidth_bytes_per_second']) for link in cap['route_links'])
                        after=segments_gpu(profile['segments'],packet.sites,packet.begin_seconds)
                    else:after,_=_profile(packet.sites,destination,slot*900+delay,service,gpu)
                    delta=after-reference+frame['delta']
                    score=packet.evaluate(delta,remaining_slot=slot)
                    total=(packet.known_gpu+anonymous+delta)[slot:]
                    if np.any((anonymous+delta)[slot:]<-1e-8):
                        score=dict(score,hard_feasible=False,violations=score['violations']+[
                            dict(reason='UNKNOWN_ANONYMOUS_REFERENCE_SUPPORT_MISSING')])
                    if np.any(total<-1e-8) or np.any(total>np.array([packet.capacities[s] for s in packet.sites])+1e-8):
                        score=dict(score,hard_feasible=False,violations=score['violations']+[dict(reason='GPU_CAPACITY')])
                    scores.append(score)
                    if not score['hard_feasible']:continue
                    recourse=evaluate_q90_recourse(packet,nominal_service,q90_hourly,timing_lower,timing_upper,
                        candidate_gpu_delta=delta,remaining_slot=slot,source_authority=source_authority)
                    mass.append(recourse['mass'])
                    risk.append(dict(physical=recourse['physical_hard_feasible'],peak=recourse['original_grid_score']['peak_score'],
                        carry=recourse['risk_total_unfinished_GPUh'],queue=recourse['queue_area_GPUh_hours'],
                        timing=recourse['CDF_timing_status'],cdf_deficit=recourse['CDF_lower_max_deficit_GPUh'],
                        timing_violations=len(recourse['CDF_timing_violations'])))
                passed=not reason and len(scores)==len(endpoints) and all(s['hard_feasible'] for s in scores) and all(r['physical'] for r in risk)
                row=dict(action=action,site=destination,delay_seconds=delay,
                    allocation_frame_id=frame['frame_id'],Q50_service_certificate=frame['certificate'],
                    qos_consumption_seconds=delay if profile is None else profile['interruption_seconds'],
                    q50_primary_score=max((s['peak_score'] for s in scores),default=None),
                    critical_line_exposure_loading_hours=max((sum(s['per_slot_peak'])*.25 for s in scores),default=None),
                    q90_queue_risk=risk,q90_mass_conservation=mass,runtime_endpoints_seconds=endpoints,
                    compute_service_GPUh=gpu*hi/3600,reference_service_GPUh=gpu*hi/3600,
                    estimated_delta_P_kw_sparse_upper=([[int(t),packet.sites[j],float(delta[t,j]*packet.p_slope[t,j])]
                        for t,j in zip(*np.nonzero(delta))] if len(scores)==len(endpoints) else []),
                    critical_time_delta_max_line_loading_upper=([float(v)-baseline_score['per_slot_peak'][slot+t]
                        for t,v in enumerate(scores[-1]['per_slot_peak'])] if len(scores)==len(endpoints) else []),
                    hard_feasible=passed,violations=[v for s in scores for v in s['violations']],reason=reason)
                if passed:
                    row.update(worst_peak_score=row['q50_primary_score'],scenario_scores=dict(NOMINAL_Q50=row['q50_primary_score']))
                    if profile:
                        row.update(migration_capability=cap,migration_timing_offsets_seconds={k:v-now for k,v in profile['times'].items()},
                            migration_hold_contract=profile['hold_contract'])
                    ordered.append(row)
                else:rejected.append(row)
                comparisons.append(deepcopy(row))
            reference_row=next((r for r in comparisons if r['site']==source and r['delay_seconds']==0 and r['allocation_frame_id']=='BASE'),None)
            for row in comparisons+ordered:
                row['P1_improves_reference']=(None if reference_row is None or reference_row['q50_primary_score'] is None
                    or row['q50_primary_score'] is None else row['q50_primary_score']<reference_row['q50_primary_score']-1e-9)
                row['P1_ties_reference']=(False if reference_row is None or reference_row['q50_primary_score'] is None
                    or row['q50_primary_score'] is None else abs(row['q50_primary_score']-reference_row['q50_primary_score'])<=1e-9)
            ordered.sort(key=lambda r:r['q50_primary_score'])
            ranked=[]
            while ordered:
                minimum=ordered[0]['q50_primary_score']
                n=next((i for i,r in enumerate(ordered) if r['q50_primary_score']-minimum>1e-9),len(ordered))
                peers,ordered=ordered[:n],ordered[n:]
                peers.sort(key=lambda r:(max(x['timing_violations'] for x in r['q90_queue_risk']),
                    max(x['cdf_deficit'] for x in r['q90_queue_risk']),max(x['carry'] for x in r['q90_queue_risk']),
                    max(x['queue'] for x in r['q90_queue_risk']),r['critical_line_exposure_loading_hours'],
                    max(x['peak'] for x in r['q90_queue_risk']),r['qos_consumption_seconds'],
                    r['action'] not in ('START_NOW','STAY'),r['allocation_frame_id']!='BASE',r['site'],r['allocation_frame_id']))
                ranked.extend(peers)
            ordered=ranked
            for rank,row in enumerate(ordered):
                row.update(frozen_rank=rank,alternative_id=f'U{ordinal}_{slot}:{rank}',
                    earliest_execution_offset_seconds=row['delay_seconds'],latest_execution_offset_seconds=row['delay_seconds'],
                    required_gpu=gpu,required_rack_sites=sites,
                    required_authorities=['OBSERVED_UID','SOURCE_COMPATIBLE_MASK','IMMUTABLE_QOS_BUDGET','CURRENT_PHYSICAL_AND_SIGNED_AFFINE_GUARD'],
                    delay_requires_TimeShift=row['delay_seconds']>0,placement_requires_Preplace=row['site']!=source)
            templates.append(dict(template_id=f'U{ordinal}_{slot}',time_slot=slot,state=state,qos=qos,gpu=gpu,
                reference_site=source,runtime_lower_seconds=lo,runtime_upper_seconds=hi,service_seconds=hi,
                compatible_site_mask=sites,Planning_headroom_by_site={s:float(packet.capacities[s]-packet.known_gpu[slot,j]-anonymous[slot,j]) for j,s in enumerate(packet.sites)},
                participation_permission='IMMUTABLE_OBSERVED_RECEIPT_AT_LOOKUP',execution_slots_15min=[slot],
                Event30=dict(status='NOT_AUTHORIZED_THRESHOLD_METRIC_SOURCE_MISSING',global_optimizer_triggered=False),
                ordered_actions=ordered,rejected_candidates=rejected,scenario_comparisons=comparisons,
                migration_capability_status='SOURCE_CONTRACT_SUPPLIED' if migration_authority else 'MIGRATION_CAPABILITY_UNCONFIRMED',
                fallback='QUEUE' if state=='PENDING' else 'STAY'))
    by_condition={}
    for t in templates:
        key=(t['time_slot'],t['state'],t['qos'],t['gpu'],t['reference_site'])
        by_condition.setdefault(key,[]).append(t)
    for peers in by_condition.values():
        for t in peers:
            t['adjacent_bucket_fallback_ids']=[r['template_id'] for r in peers if r is not t
                and r['runtime_lower_seconds']==t['runtime_upper_seconds']]
            t['adjacent_fallback_certificate']='SHARED_BOUNDARY_ENDPOINT_INDEPENDENTLY_EVALUATED_NO_LONG_JOB_SHORT_BUCKET'
    body=dict(policy_version=POLICY_ID,queue_recourse_policy_id=QUEUE_ID,unknown_policy_version='V42_UNKNOWN_FROZEN_CONDITIONS_V1',
        bindings=dict(bindings),evidence_kind=evidence_kind,begin_seconds=packet.begin_seconds,end_seconds=packet.begin_seconds+86400,
        envelope=deepcopy(envelope),templates=templates,rules=[],site_axis=list(packet.sites),
        physical_site_capacities=packet.capacities,physical_resource_authority_sha=digest(packet.capacities),
        runtime_resource_baseline_GPU=(packet.known_gpu+anonymous).tolist(),runtime_resource_support=None,
        packet_authority_sha=digest(packet.authority),migration_authority=migration_authority,
        coverage=deepcopy(conditions),qos_scenario=qos_provider.scenario,qos_spec_sha=qos_provider.stats.sha,
        cc4_q90_hourly=list(q90_hourly),nominal_service_sha=nominal_service['nominal_service_sha'],
        source_authority=deepcopy(source_authority),original_grid_authority=packet.authority,
        service_reallocation=service_reallocation,anonymous_service_frames=frame_catalog,
        allocation_resolution='ONE_FROZEN_REPLACEMENT_PROFILE_ID;NEVER_SUM_FRAME_DELTAS;NO_HARD_ANONYMOUS_BOOKING',
        objective='ORIGINAL_Q50_P1_THEN_Q90_QUEUE_RISK_THEN_LESS_INTERVENTION',
        candidate_comparison_audit=[dict(template_id=t['template_id'],candidate_scores=t['scenario_comparisons']) for t in templates],
        policy_scope='ISSUE_ANONYMOUS_CONDITIONS_UNKNOWN_ONLY_LOOKUP_AFTER_OBSERVATION',
        scenario_audit=dict(Q90_method=QUEUE_ID,Q90_is_Actual_load=False),
        execution_contract_version='MULTI_ALTERNATIVE_RESERVATION_ROLES_V2',
        ranking_contract=['Q50_RHO_MAX_PRIMARY_TOL_1E-9','Q90_CDF_VIOLATION_COUNT','Q90_CDF_DEFICIT','Q90_CARRY','Q90_QUEUE_AREA',
            'Q50_ALL_LINE_MAX_EXPOSURE_LOADING_HOURS','Q90_PEAK','QOS_BURDEN','LESS_INTERVENTION','STABLE_SOURCE_SITE_FRAME_ID'],
        q50_tie_tolerance=1e-9,ranking_is_not_A_stage_P2=True,
        compiler_source_sha=__import__('hashlib').sha256(Path(__file__).read_bytes()).hexdigest(),
        Unknown_never_borrows_Known_service=True,Actual_future_UID_inputs=0,online_grid_horizon_evaluations=0,
        online_global_optimizer_calls=0,status='OFFLINE_POLICY_OPTIMIZATION_VALIDATED',Fresh_AC_status='NOT_RUN',
        metrics=dict(templates=len(templates),bounded_candidates=generated,candidates_truncated=0,
            compile_wall_seconds=time.perf_counter()-began,Native_Optimize_calls=0))
    body=_json(body)
    # Share exact recorded values only. No candidate, rank, precision, or risk
    # scenario is removed, and Actual performs no new numerical evaluation.
    shared={}
    shared_keys=('q50_primary_score','q90_queue_risk','q90_mass_conservation','estimated_delta_P_kw_sparse_upper',
        'critical_time_delta_max_line_loading_upper','runtime_endpoints_seconds','violations')
    for template in body['templates']:
        for field in ('ordered_actions','rejected_candidates','scenario_comparisons'):
            for row in template[field]:
                refs={}
                for key in shared_keys:
                    if key not in row:continue
                    value=row.pop(key);sha=digest(value);shared.setdefault(sha,value);refs[key]=sha
                row['shared_value_refs']=refs
    body['shared_numeric_values']=shared
    body['compression']='EXACT_JSON_VALUE_INTERNING_NO_QUANTIZATION_NO_CANDIDATE_DELETION'
    body['candidate_comparison_audit']=[dict(template_id=t['template_id'],candidate_scores=t['scenario_comparisons']) for t in body['templates']]
    body['policy_sha']=digest({k:v for k,v in body.items() if k!='metrics'})
    result=FrozenUnknownPolicy(dict(body,content_sha=digest(body)));result.bind_runtime_packet(packet)
    return result


class FrozenUnknownPolicy(FrozenQueueAwarePolicy):
    lookup_only=True
    def __init__(self,document):
        if document.get('unknown_policy_version')!='V42_UNKNOWN_FROZEN_CONDITIONS_V1':
            raise ValueError('UNKNOWN_FROZEN_CONDITIONAL_DOCUMENT_REQUIRED')
        if document.get('execution_contract_version')!='MULTI_ALTERNATIVE_RESERVATION_ROLES_V2':
            raise ValueError('FROZEN_ALTERNATIVE_CONTRACT_VERSION_REQUIRED')
        super().__init__(document)
        self.packet=None;self.audit=[];self.references={};self.reference_audit=[];self.observed_blocks={}
        self.last_selection={};self.times=[];self._current=None
        self.migration_authority=deepcopy(self._body.get('migration_authority'))
        self._templates={r['template_id']:self._expanded_template(r) for r in self._body['templates']}
        self.active_service_frame_id='BASE'

    def bind_runtime_packet(self,packet):
        if packet.bindings!=self.bindings or digest(packet.authority)!=self._body['packet_authority_sha']:
            raise ValueError('FROZEN_CURRENT_GUARD_SOURCE_DRIFT')
        self.packet=packet

    def set_current_resources(self,now,observed):self._current=(float(now),dict(observed))

    def _expanded_template(self,template):
        out=dict(template)
        for field in ('ordered_actions','rejected_candidates','scenario_comparisons'):
            out[field]=[dict(r,**{k:self._body['shared_numeric_values'][sha] for k,sha in r.get('shared_value_refs',{}).items()})
                for r in template[field]]
        return out

    def expanded_document(self):
        out=self.document;out['templates']=deepcopy(list(self._templates.values()))
        out['expansion_is_display_only_original_policy_SHA_retained']=True
        return out

    def lookup(self,metadata,receipt,now):
        if metadata.get('origin_unknown') is not True:raise ValueError('KNOWN_NEVER_ENTERS_UNKNOWN_POLICY')
        template,reason=super().lookup(metadata,receipt,now)
        if template is None:return None,reason
        template=self._templates[template['template_id']]
        if not template['ordered_actions']:
            service=(metadata['t50_seconds']-metadata.get('accumulated_compute_seconds',0) if metadata.get('state')=='RUNNING'
                else metadata.get('nominal_service_seconds',metadata['t50_seconds']))
            for ident in template['adjacent_bucket_fallback_ids']:
                neighbor=self._templates[ident]
                if neighbor['runtime_lower_seconds']<=service<=neighbor['runtime_upper_seconds'] and neighbor['ordered_actions']:
                    return neighbor,'PRECOMPILED_ADJACENT_BOUNDARY_FALLBACK'
        return template,reason

    def runtime_metrics(self):
        samples=np.asarray(self.times)*1000
        return dict(lookup_calls=len(self.audit),event_median_ms=None if not len(samples) else float(np.median(samples)),
            event_p95_ms=None if not len(samples) else float(np.percentile(samples,95)),
            timing_scope='SUCCESSFUL_PENDING_LOOKUPS_ONLY_NOT_FULL96_END_TO_END',
            online_grid_horizon_evaluations=0,online_global_optimizer_calls=0)

    def current_guard(self,metadata,segments,now,observed):
        if self.packet is None:return 'CURRENT_GRID_PACKET_NOT_BOUND'
        slot=int((now-self.packet.begin_seconds)//900)
        if not 0<=slot<96:return 'CURRENT_GRID_SLOT_UNSUPPORTED'
        instant=np.array([observed[s] for s in self.packet.sites],float)
        if metadata.get('state')=='RUNNING':instant[self.packet.sites.index(metadata['current_site'])]-=metadata['gpu']
        for seg in segments:
            if not seg['resource'].startswith('gpu:'):continue
            site=seg['resource'][4:]
            if metadata['gpu']>max(self.packet.rack_compatibility[site]):return 'RACK_GANG_INCOMPATIBLE'
            if seg['begin']<=now<seg['end']:instant[self.packet.sites.index(site)]+=seg['quantity']
        if np.any(instant>np.array([self.packet.capacities[s] for s in self.packet.sites])+1e-9):return 'GPU_CAPACITY'
        _,violations=self.packet._at_slot(slot,instant-np.asarray(self._body['runtime_resource_baseline_GPU'][slot]))
        return None if not violations else 'CURRENT_OBSERVED_'+violations[0]['reason']

    def candidates(self,metadata,receipt,now):
        template,reason=self.lookup(metadata,receipt,now)
        if template is None or metadata.get('state')!='PENDING':return [],reason
        return self._materialize(template,metadata,receipt,now,now),'MATCH'

    def _materialize(self,template,metadata,receipt,origin,now):
        from .policy import _receipt
        receipt=_receipt(receipt);out=[]
        service=float(metadata.get('nominal_service_seconds',metadata['t50_seconds']))
        for row in template['ordered_actions']:
            site=row['site'];start=origin+row['delay_seconds'];end=start+service
            spend=max(metadata.get('additional_start_delay_seconds',0),start-receipt['reference_start_seconds'])
            if (start<now or start not in receipt['allowed_starts_seconds']
                    or spend+metadata.get('cumulative_migration_interruption_seconds',0)>receipt['budget_seconds']+1e-9
                    or site not in metadata['compatible_sites']
                    or (spend>metadata.get('additional_start_delay_seconds',0) and metadata.get('Can_TimeShift') is not True)
                    or (site!=template['reference_site'] and metadata.get('can_prestart_place') is not True)):
                continue
            if start<max(metadata.get('release_seconds') or -math.inf,metadata.get('hard_earliest_start_seconds') or -math.inf):continue
            if any(metadata.get(k) is not None and value>metadata[k] for k,value in (
                ('hard_latest_start_seconds',start),('completion_deadline_seconds',end))):continue
            out.append(dict(uid=metadata['uid'],action='PREPLACE' if row['action']=='PREPLACE' else 'DELAY' if row['delay_seconds'] else 'START',
                policy_action=row['action'],site=site,start_seconds=start,nominal_end_seconds=end,
                additional_start_delay_seconds=spend,rule_id=template['template_id'],
                frozen_alternative_rank=row['frozen_rank'],alternative_id=row['alternative_id'],
                allocation_frame_id=row['allocation_frame_id'],estimated_worst_peak=row['q50_primary_score'],
                q90_queue_risk=deepcopy(row['q90_queue_risk']),q90_mass_conservation=deepcopy(row['q90_mass_conservation']),
                segments=[dict(resource='gpu:'+site,begin=start,end=end,quantity=metadata['gpu'])]))
        return out

    def _record(self,metadata,now,decision):
        decision['physical_or_Q50_veto']=decision['action']=='QUEUE'
        self.last_selection[metadata['uid']]=deepcopy(decision)
        self.audit.append(dict(uid=metadata['uid'],time_seconds=now,state=metadata['state'],selected_action=decision['action'],
            lookup_success=decision.get('rule_id') is not None,rejected=decision.get('rejected_candidates',[]),
            signed_packet_evaluation_calls=0,generated=0,candidates_truncated=0))
        return decision

    def select(self,metadata,receipt,now,reservations,*,reserve=True):
        if metadata.get('origin_unknown') is not True:raise ValueError('KNOWN_NEVER_ENTERS_UNKNOWN_POLICY')
        if metadata.get('is_observed',True) is not True or metadata['submit_seconds']>now:
            return dict(uid=metadata['uid'],action='QUEUE',status='NOT_YET_SUBMITTED',reason='OBSERVATION_REQUIRED',
                online_grid_horizon_evaluations=0,online_global_optimizer_calls=0)
        began=time.perf_counter();template,_=self.lookup(metadata,receipt,now)
        if reserve:
            from .policy import _receipt
            r=_receipt(receipt)
            self.references.setdefault(metadata['uid'],dict(first_reference_start_seconds=r['reference_start_seconds'],
                reference_start_seconds=r['reference_start_seconds'],intentional_burden_at_reference_seconds=0.,
                site=metadata.get('reference_site',metadata.get('source_site'))))
        rows,reason=self.candidates(metadata,receipt,now);rejected=[]
        for row in rows:
            reason=reservations.feasible(row['segments'],exclude=metadata['uid'])
            if reason is None:
                reason=('CURRENT_RESOURCE_OBSERVATION_REQUIRED' if self._current is None or self._current[0]!=now
                    else self.current_guard(metadata,row['segments'],now,self._current[1]))
            if reason is None and reserve:
                ok,reason=reservations.reserve(metadata['uid'],row['segments'],replace=True)
                if ok:reason=None
            if reason is None:
                if reserve:
                    metadata['additional_start_delay_seconds']=max(metadata.get('additional_start_delay_seconds',0),
                        row['additional_start_delay_seconds'])
                    self.active_service_frame_id=row['allocation_frame_id']
                self.times.append(time.perf_counter()-began)
                return self._record(metadata,now,dict(row,status='SELECTED_FROZEN_OFFLINE_RANK',policy_sha=self.sha,
                    policy_lookup_time_seconds=now,
                    online_grid_horizon_evaluations=0,online_global_optimizer_calls=0,rejected_candidates=rejected))
            rejected.append(dict(action=row['action'],site=row['site'],reason=reason,
                conflict=deepcopy(getattr(reservations,'last_conflict',None))))
        return self._record(metadata,now,dict(uid=metadata['uid'],action='QUEUE',status='NO_MATCH_OR_FEASIBLE_FROZEN_ACTION',
            reason=reason,rule_id=None if template is None else template['template_id'],
            rejected_candidates=rejected,policy_sha=self.sha,online_grid_horizon_evaluations=0))

    def revalidate_command(self,metadata,receipt,now,reservations,decision,observed,*,failure_reason):
        """Use later entries in the very same frozen row; no new ranking."""
        from .policy import _receipt
        receipt=_receipt(receipt);template=self._templates[decision['rule_id']]
        origin=decision['policy_lookup_time_seconds'];start_rank=decision['frozen_alternative_rank']+1
        rejected=[dict(reason=failure_reason,rank=decision['frozen_alternative_rank'],event='COMMAND_REVALIDATION_FAILED')]
        for rank,row in enumerate(template['ordered_actions'][start_rank:],start_rank):
            start=origin+row['delay_seconds'];site=row['site'];service=metadata['t50_seconds']
            spend=max(metadata.get('additional_start_delay_seconds',0),start-receipt['reference_start_seconds'])
            if start<now or start not in receipt['allowed_starts_seconds'] or spend+metadata.get('cumulative_migration_interruption_seconds',0)>receipt['budget_seconds']+1e-9:
                rejected.append(dict(rank=rank,reason='EXPIRED_FROZEN_TIME_OR_SHARED_BUDGET'));continue
            if site not in metadata['compatible_sites'] or (site!=metadata.get('reference_site',metadata.get('source_site')) and metadata.get('can_prestart_place') is not True):
                rejected.append(dict(rank=rank,reason='CURRENT_JOB_SITE_AUTHORITY'));continue
            if spend>metadata.get('additional_start_delay_seconds',0) and metadata.get('Can_TimeShift') is not True:
                rejected.append(dict(rank=rank,reason='NO_ADDITIONAL_DELAY_AUTHORITY'));continue
            end=start+service
            if any(metadata.get(k) is not None and value>metadata[k] for k,value in (
                ('hard_latest_start_seconds',start),('completion_deadline_seconds',end))):continue
            segments=[dict(resource='gpu:'+site,begin=start,end=end,quantity=metadata['gpu'])]
            reason=self.current_guard(metadata,segments,now,observed)
            if reason is None:
                ok,reason=reservations.reserve(metadata['uid'],segments,replace=True)
                if ok:
                    metadata['additional_start_delay_seconds']=spend
                    self.active_service_frame_id=row['allocation_frame_id']
                    return self._record(metadata,now,dict(decision,site=site,start_seconds=start,nominal_end_seconds=end,
                        segments=segments,additional_start_delay_seconds=spend,action='PREPLACE' if row['action']=='PREPLACE' else 'DELAY' if row['delay_seconds'] else 'START',
                        frozen_alternative_rank=rank,rebound_score_frozen=row['q50_primary_score'],
                        alternative_id=row['alternative_id'],allocation_frame_id=row['allocation_frame_id'],
                        status='SELECTED_SAME_FROZEN_ROW_FALLBACK',rejected_candidates=rejected,
                        reservation_replaced_atomically=True,online_grid_horizon_evaluations=0))
            rejected.append(dict(rank=rank,site=site,reason=reason,conflict=deepcopy(getattr(reservations,'last_conflict',None))))
        reservations.release(metadata['uid'],now)
        return self._record(metadata,now,dict(uid=metadata['uid'],action='QUEUE',rule_id=template['template_id'],
            policy_sha=self.sha,status='ALL_SAME_ROW_FROZEN_ALTERNATIVES_INFEASIBLE',reason=failure_reason,
            revalidated_at_seconds=now,rejected_candidates=rejected,online_grid_horizon_evaluations=0))

    def select_migration(self,metadata,receipt,now,reservations,*,checkpoint_at=None,reserve=True):
        if metadata.get('origin_unknown') is not True:raise ValueError('KNOWN_NEVER_ENTERS_UNKNOWN_POLICY')
        if (metadata.get('is_observed',True) is not True or metadata['submit_seconds']>now
                or metadata.get('state')!='RUNNING'):
            return dict(uid=metadata['uid'],action='STAY',status='NO_OBSERVED_RUNNING_AUTHORITY',reason='NO_OBSERVED_RUNNING_AUTHORITY',
                online_grid_horizon_evaluations=0)
        if metadata.get('migration_count',0)>0:
            return self._record(metadata,now,dict(uid=metadata['uid'],action='STAY',status='ONE_MIGRATION_ALREADY_USED',reason='MAXIMUM_ONE_MIGRATION'))
        accumulated=metadata.get('accumulated_compute_seconds',0)
        if accumulated<1800 or abs(accumulated%1800)>1e-7:
            return self._record(metadata,now,dict(uid=metadata['uid'],action='STAY',
                status='NOT_EXECUTION_ANCHORED_CHECKPOINT',reason='NOT_EXECUTION_ANCHORED_CHECKPOINT',online_grid_horizon_evaluations=0))
        if checkpoint_at is not None and checkpoint_at>now:
            return dict(uid=metadata['uid'],action='STAY',status='CHECKPOINT_NOT_OBSERVED',reason='CHECKPOINT_NOT_OBSERVED',
                online_grid_horizon_evaluations=0)
        first=metadata.get('frozen_first_checkpoint_attempt_seconds')
        if first is not None and first!=now:
            return self._record(metadata,now,dict(uid=metadata['uid'],action='STAY',status='FIRST_VALID_CHECKPOINT_ALREADY_CONSUMED',reason='FIRST_CHECKPOINT_ONLY'))
        if reserve and metadata.get('Can_Checkpoint_Migrate') is True:
            metadata.setdefault('frozen_first_checkpoint_attempt_seconds',now)
        control=math.ceil((now if checkpoint_at is None else checkpoint_at)/900)*900
        template,reason=self.lookup(metadata,receipt,control);rejected=[]
        if template and metadata.get('Can_Checkpoint_Migrate') is True:
            for row in template['ordered_actions']:
                if row['action']=='STAY':
                    if reserve:self.active_service_frame_id=row['allocation_frame_id']
                    return self._record(metadata,now,dict(uid=metadata['uid'],action='STAY',rule_id=template['template_id'],
                        status='SELECTED_FROZEN_STAY_RANK',reason='FROZEN_STAY_RANK',policy_sha=self.sha,
                        allocation_frame_id=row['allocation_frame_id'],frozen_alternative_rank=row['frozen_rank'],
                        rejected_candidates=rejected,online_grid_horizon_evaluations=0))
                if row['site'] not in metadata.get('compatible_sites',()):
                    rejected.append(dict(site=row['site'],reason='CURRENT_JOB_DESTINATION_INCOMPATIBLE'));continue
                cap=deepcopy(metadata.get('migration_capability') or row.get('migration_capability'))
                if cap.get('wan_path')!=row['migration_capability']['wan_path']:
                    rejected.append(dict(reason='OBSERVED_WAN_PATH_OUTSIDE_FROZEN_RULE'));continue
                candidate=dict(metadata,migration_capability=cap)
                if metadata.get('data_residency_confirmed') is False:
                    rejected.append(dict(reason='DATA_RESIDENCY_NOT_AUTHORIZED'));continue
                migration,reason=migration_guard(candidate,receipt,now=now,
                    accumulated_compute_seconds=metadata.get('accumulated_compute_seconds',0),destination=row['site'],
                    remaining_nominal_seconds=metadata['t50_seconds']-metadata.get('accumulated_compute_seconds',0),
                    reservations=reservations,checkpoint_at=checkpoint_at)
                if migration is None:rejected.append(dict(site=row['site'],reason=reason));continue
                if {k:v-control for k,v in migration['times'].items()}!=row['migration_timing_offsets_seconds']:
                    rejected.append(dict(reason='MIGRATION_PROFILE_OUTSIDE_FROZEN_BUCKET'));continue
                cap=candidate['migration_capability'];a,b=migration['times']['transfer_start'],migration['times']['transfer_end']
                migration['segments'].extend(dict(resource='wan:LINK::'+link,begin=a,end=b,
                    quantity=cap['bandwidth_bytes_per_second']) for link in row['migration_capability']['route_links'])
                reason=reservations.feasible(migration['segments'],exclude=metadata['uid'])
                if reason is None:
                    reason=('CURRENT_RESOURCE_OBSERVATION_REQUIRED' if self._current is None or self._current[0]!=now
                        else self.current_guard(candidate,migration['segments'],now,self._current[1]))
                if reason is None and reserve:
                    ok,reason=reservations.reserve(metadata['uid'],migration['segments'],replace=True)
                    if ok:reason=None
                if reason is None:
                    if reserve:
                        metadata['migration_capability']=cap
                        self.active_service_frame_id=row['allocation_frame_id']
                    return self._record(metadata,now,dict(uid=metadata['uid'],action='CHECKPOINT_MIGRATE',migration=migration,
                        rule_id=template['template_id'],policy_sha=self.sha,status='SELECTED_FROZEN_OFFLINE_RANK',
                        allocation_frame_id=row['allocation_frame_id'],frozen_alternative_rank=row['frozen_rank'],
                        alternative_id=row['alternative_id'],
                        online_grid_horizon_evaluations=0,rejected_candidates=rejected))
                rejected.append(dict(site=row['site'],reason=reason))
        return self._record(metadata,now,dict(uid=metadata['uid'],action='STAY',status='FROZEN_STAY_OR_UNSUPPORTED',
            reason=reason,rule_id=None if template is None else template['template_id'],
            rejected_candidates=rejected,policy_sha=self.sha,online_grid_horizon_evaluations=0))

"""Reclassify existing finite prototypes using A2 nominal and excess recourse.

Request rights, nominal scores, source-envelope rejection and runtime buckets
come from the frozen compiler. PR224's capability and past-slot fixes remain
in its unchanged runtime class. No new optimizer or forecast is constructed.
"""
from copy import deepcopy
from pathlib import Path
from collections import Counter
import time,hashlib
import numpy as np
from .policy import digest
from .sensitivity_policy import FrozenSensitivityPolicy,_profile
from .q90_recourse import evaluate_q90_recourse

POLICY_ID='V42_CC4_V21_Q90_QUEUE_AWARE_RECOURSE_V1'


class FrozenQueueAwarePolicy(FrozenSensitivityPolicy):
    def __init__(self,document):
        if document.get('queue_recourse_policy_id')!=POLICY_ID:
            raise ValueError('QUEUE_RECOURSE_SOURCE_BOUNDARY_REQUIRED')
        super().__init__(document)

    def resource_support_at(self,now):
        slot=int((now-self._body['begin_seconds'])//900)
        if not 0<=slot<96:return None
        caps=self._body['physical_site_capacities']
        return dict(lower_by_site={s:0. for s in caps},upper_by_site=dict(caps),
            source_sha=self._body['physical_resource_authority_sha'],
            scenario_ids=['ORIGINAL_PHYSICAL_CAPACITY_NOT_FORECAST_SUPPORT'],
            support_is_necessary_guard_not_Actual_grid_certificate=True,
            forecast_deviation_is_not_blanket_veto=True)


def compile_queue_aware_policy(frozen_policy,packet,nominal,q90_hourly,timing_lower,timing_upper,
                              *,bindings,source_authority):
    """Reuse the exact recorded candidate population and nominal hard scores."""
    started=time.perf_counter();doc=frozen_policy.document
    for key,value in frozen_policy.bindings.items():
        if key!='science_sha' and bindings.get(key)!=value:
            raise ValueError('Q90_CORRECTION_CANNOT_CHANGE_QOS_CASE_OR_NUMERIC_ANCHORS:'+key)
    before=dict(templates=len(doc['templates']),generated=doc['metrics']['bounded_candidates'],
        scored=sum(len(t['scenario_comparisons']) for t in doc['templates']),
        approved=sum(len(t['ordered_actions']) for t in doc['templates']))
    funnel=[];evaluations=[];action_counts=Counter()
    for template in doc['templates']:
        slot=template['time_slot'];reference_site=template['reference_site'];gpu=template['gpu']
        # V5 omits delay in rejection rows. Their append order is the exact
        # scored-variant order after removing already-approved variants.
        # PREPLACE repeats at different delays, so a (action,site) map loses
        # evidence. Bind the ordinal and assert both original scenario scores.
        rejected=[r for r in template['rejected_candidates'] if 'scenarios' in r]
        rejected_ordinal=0
        ordered=[];updated_comparisons=[]
        for candidate in template['scenario_comparisons']:
            if not candidate['hard_feasible']:
                if rejected_ordinal>=len(rejected):raise ValueError('FROZEN_REJECTION_ORDINAL_MISSING')
                previous=rejected[rejected_ordinal];rejected_ordinal+=1
                if ((previous['action'],previous['site'])!=(candidate['action'],candidate['site'])
                        or any(previous['scenarios'][name]['peak_score']!=score
                            for name,score in candidate['scenario_scores'].items())):
                    raise ValueError('FROZEN_VARIANT_ORDINAL_OR_SCENARIO_SCORE_MISMATCH')
                nominal_score=previous['scenarios']['NOMINAL_Q50']
            else:
                original=next((r for r in template['ordered_actions'] if
                    (r['action'],r['site'],r['delay_seconds'])==
                    (candidate['action'],candidate['site'],candidate['delay_seconds'])),None)
                if original is None:raise ValueError('FROZEN_APPROVED_VARIANT_IDENTITY_MISSING')
                low,high=template['runtime_lower_seconds'],template['runtime_upper_seconds']
                endpoints=sorted({high,max(low,1e-9)}|{float(v) for v in np.arange(
                    np.ceil(low/900)*900,high,900) if v>0})
                nominal_score=dict(hard_feasible=True,peak_score=original['scenario_scores']['NOMINAL_Q50'],
                    runtime_bucket_piecewise_endpoints_seconds=endpoints)
            row=dict(template_id=template['template_id'],time_slot=slot,state=template['state'],
                action=candidate['action'],site=candidate['site'],delay_seconds=candidate['delay_seconds'],
                q50_hard_pass=nominal_score['hard_feasible'],q50_peak=nominal_score['peak_score'],
                old_all_scenario_hard_pass=candidate['hard_feasible'],new_physical_recourse_pass=False,
                q90_queue_aware_status='NOT_RUN_Q50_HARD_REJECTED',q90_peak=None,
                extra_pending_carry_GPUh=None,approved=False)
            if not nominal_score['hard_feasible']:
                funnel.append(row);updated_comparisons.append(dict(candidate,new_queue_aware_hard_feasible=False,
                    q90_queue_aware_status=row['q90_queue_aware_status']));continue
            scores=[]
            for endpoint in nominal_score['runtime_bucket_piecewise_endpoints_seconds']:
                reference,_=_profile(packet.sites,reference_site,slot*900,endpoint,gpu)
                if candidate['action']=='STAY':after=reference
                elif template['state']=='PENDING':
                    after,_=_profile(packet.sites,candidate['site'],slot*900+candidate['delay_seconds'],endpoint,gpu)
                else:raise ValueError('UNRECORDED_MIGRATION_MUST_NOT_BE_FABRICATED')
                result=evaluate_q90_recourse(packet,nominal,q90_hourly,timing_lower,timing_upper,
                    candidate_gpu_delta=after-reference,remaining_slot=slot,source_authority=source_authority)
                scores.append(result)
            physical=all(s['physical_hard_feasible'] for s in scores)
            q90_peak=max(s['original_grid_score']['peak_score'] for s in scores)
            carry=max(s['mass']['extra_terminal_backlog_GPUh'] for s in scores)
            timing_risk=any(s['CDF_timing_status'] not in {'PASS','MET'} for s in scores)
            row.update(new_physical_recourse_pass=physical,q90_queue_aware_status='PHYSICAL_PASS_TIMING_RISK'
                if physical and timing_risk else 'PHYSICAL_PASS' if physical else 'PHYSICAL_HARD_REJECTED',
                q90_peak=q90_peak,extra_pending_carry_GPUh=carry,approved=physical)
            updated_comparisons.append(dict(candidate,new_queue_aware_hard_feasible=physical,
                q90_queue_aware_status=row['q90_queue_aware_status'],
                new_scenario_scores=dict(NOMINAL_Q50=nominal_score['peak_score'],Q90_QUEUE_AWARE=q90_peak)))
            evaluations.append(dict(identity=row,endpoint_evaluations=scores))
            if physical:
                service=template['service_seconds'];delay=candidate['delay_seconds']
                action=dict(action=candidate['action'],site=candidate['site'],delay_seconds=delay,
                    qos_consumption_seconds=delay if template['state']=='PENDING' else 0.,
                    tail_GPUh=gpu*max(0.,slot*900+delay+service-86400)/3600,
                    service_seconds=service,compute_service_GPUh=gpu*service/3600,
                    reference_service_GPUh=gpu*service/3600,service_preserved=True,
                    worst_peak_score=max(nominal_score['peak_score'],q90_peak),
                    q50_primary_score=nominal_score['peak_score'],
                    scenario_scores=dict(NOMINAL_Q50=nominal_score['peak_score'],Q90_QUEUE_AWARE=q90_peak),
                    q90_queue_risk=dict(extra_terminal_backlog_GPUh=carry,timing_risk=timing_risk,
                        timing_violation_count=max(len(s['CDF_timing_violations']) for s in scores),
                        CDF_lower_max_deficit_GPUh=max(s['CDF_lower_max_deficit_GPUh'] for s in scores),
                        queue_area_GPUh_hours=max(s['queue_area_GPUh_hours'] for s in scores),
                        anonymous_future_QoS_certified=False),
                    original_A_source_variables=sorted({r['source_variable'] for r in doc['envelope']
                        if r['site']==candidate['site'] and r['slot_start']<packet.begin_seconds+slot*900+delay+service
                        and r['slot_end']>packet.begin_seconds+slot*900+delay}))
                ordered.append(action);action_counts[action['action']]+=1
            funnel.append(row)
        ordered.sort(key=lambda r:(r['scenario_scores']['NOMINAL_Q50'],
            r['q90_queue_risk']['extra_terminal_backlog_GPUh'],r['q90_queue_risk']['timing_risk'],
            r['q90_queue_risk']['CDF_lower_max_deficit_GPUh'],r['q90_queue_risk']['queue_area_GPUh_hours'],
            r['scenario_scores']['Q90_QUEUE_AWARE'],r['qos_consumption_seconds'],r['site'],r['action']))
        if rejected_ordinal!=len(rejected):raise ValueError('UNBOUND_FROZEN_REJECTION_EVIDENCE')
        template['ordered_actions']=ordered
        template['original_fixed_Q90_scenario_comparisons']=template['scenario_comparisons']
        template['scenario_comparisons']=updated_comparisons
        template['status']='OFFLINE_POLICY_OPTIMIZATION_VALIDATED' if ordered else 'NO_FEASIBLE_ACTION'
    doc.pop('content_sha',None);doc.pop('policy_sha',None)
    doc['original_fixed_Q90_candidate_comparison_audit']=doc['candidate_comparison_audit']
    doc['candidate_comparison_audit']=[dict(template_id=t['template_id'],
        candidate_scores=t['scenario_comparisons'],selected=t['ordered_actions'][0] if t['ordered_actions'] else None,
        remaining_all_line_slots=96-t['time_slot']) for t in doc['templates']]
    doc.update(bindings=dict(bindings),queue_recourse_policy_id=POLICY_ID,
        physical_site_capacities=dict(packet.capacities),physical_resource_authority_sha=digest(packet.capacities),
        resource_guard='FORECAST_DEVIATION_DIAGNOSTIC_THEN_ORIGINAL_PHYSICAL_RESERVATIONS',
        status='OFFLINE_POLICY_OPTIMIZATION_VALIDATED' if any(t['ordered_actions'] for t in doc['templates']) else 'POLICY_COMPILER_ONLY',
        objective='Q50_PEAK_THEN_Q90_QUEUE_AND_TIMING_RISK_THEN_LESS_BURDEN_NOT_NEW_A_STAGE_P2',
        compiler_source_sha=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        old_Q50_scores_reused_only_with_identical_numerical_case=True,old_Fresh_or_global_gap_transferred=False)
    doc['Q50_evidence_binding']='EXACT_COMPILER_VARIANT_ORDER_PLUS_ACTION_SITE_AND_ALL_SCENARIO_SCORE_ASSERTIONS'
    doc['scenario_audit']=dict(doc['scenario_audit'],Q90_fixed_target_hard_veto=False,
        Q90_method='A2_NOMINAL_PLUS_HOURLY_Q90_MINUS_Q50_CDF_BOUNDED_PHYSICAL_RECOURSE',
        kernel_fixed_actual_schedule=False,anonymous_QoS_guaranteed=False)
    original_metrics=deepcopy(doc['metrics'])
    try:
        import psutil
        memory=psutil.Process().memory_info()
        rss=memory.rss;peak=getattr(memory,'peak_wset',None)
    except ImportError:rss=peak=None
    doc['metrics']=dict(original_frozen_compiler_metrics=original_metrics,
        compile_wall_seconds=time.perf_counter()-started,
        queue_aware_compile_wall_seconds=time.perf_counter()-started,
        RSS_bytes_at_compile_end=rss,process_lifetime_peak_RSS_bytes=peak,
        peak_RSS_scope='CURRENT_PROCESS_INCLUDING_REFERENCE_LOAD_AND_QUEUE_COMPILER',
        templates=len(doc['templates']),bounded_candidates=before['generated'],
        new_approved=sum(len(t['ordered_actions']) for t in doc['templates']),Native_Optimize_calls=0)
    doc['policy_sha']=digest({k:v for k,v in doc.items() if k!='metrics'})
    policy=FrozenQueueAwarePolicy(dict(doc,content_sha=digest(doc)))
    return dict(policy=policy,before=before,funnel=funnel,evaluations=evaluations,
        approved_action_counts=dict(action_counts),new_approved=doc['metrics']['new_approved'],
        scope='REUSED_ANONYMOUS_PROTOTYPES_NOT_JOB_SLA_OR_FRESH_AC_CERTIFICATE')

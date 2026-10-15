"""RC01: preserved scheduling, basic designation, optional Pending pre-site.

This diagnostic reuses the byte-pinned PR223 reference/fallback and fixed M2.
It is not the new D0 A1->M1->A2->M2 handoff or a Full96 certificate.
"""
from copy import deepcopy
import heapq
import math
from pathlib import Path
from time import perf_counter
import numpy as np

from .actual import JobEventController,run_actual
from .aidc_sensitivity_runtime import CurrentEventSensitivityPolicy,_bind_driver_current_c1
from .isolated_unknown import (IsolatedReferenceController,prepare_source,prepare_packet,no_native,
    ROOT,RAW,ORIGINAL,record,read,write,_csv)
from .current_ac_admission import CausalObservations,CurrentACAdmission
from .policy import digest,_receipt
from .trajectory_tracking import require_tracking_public

SCOPE='RC01_PR223_REFERENCE_FIXED_M2_INITIAL_STAY_OPTIONAL_PENDING_PRESITE'


def initial_authority(bindings,study_case_sha):
    """Existing user-authorized initial-placement study, not change consent."""
    return dict(schema='PUBLIC_UNKNOWN_PRESTART_COMPATIBLE_SITE_STUDY_V1',
        interface_sha=bindings['interface_sha'],study_case_sha=study_case_sha,
        candidate_axis='SOURCE_COMPATIBLE_SITES_ONLY',intentional_delay_seconds=0,max_sites=12,
        Known_commands_modified=False,source_customer_SLA_claim=False,source_customer_permission_claim=False,
        authority_scope='USER_AUTHORIZED_UNKNOWN_ALLOCATION_RESEARCH_CASE',Strict_Source_certificate=False,
        Known_corrective_permission_granted=False,Source_release_GPU_rack_grid_compatibility_preserved=True)


class ReleasePolicy(CurrentEventSensitivityPolicy):
    def __init__(self,*args,variant,oracle,**kwargs):
        if variant not in ('C0','C1'):raise ValueError('RC01_VARIANT_REQUIRED')
        super().__init__(*args,basic=False,runtime_repair=False,**kwargs)
        self.variant=variant;self.oracle=oracle;self.initial={};self.initial_events=[];self.candidate_events=[]
        self.spec.update(release_scope=SCOPE,variant=variant,
            scheduling='BYTE_PINNED_PR223_REFERENCE_AND_PRE_DDAY_FALLBACK',
            initial_placement='SAME_CAUSAL_REFERENCE_SITE_NO_SENSITIVITY',
            presite='C1_ONLY_PENDING_SOURCE_CHANGE_AUTHORITY_AND_READY_DATA_STRICTLY_BETTER_THAN_STAY',
            electrical_admission='CURRENT_CAUSAL_ORIGINAL_11SVR_7REGCONTROL_CANDIDATE_AC',
            frozen_forecast_affine_is_admission_or_ranking_authority=False,
            ranking='CONDITIONAL_PUBLIC_Q50_CURRENT_EXOGENOUS_HOLD_COUNTERFACTUAL_AC_ALL_PHASE_LINES',
            future_prediction_is_actual_state=False,future_Known_speculative_GPU_veto=False,
            initial_research_authority_grants_presite=False,checkpoint_migration='HOLD')
        self.sha=digest(self.spec)

    def designate(self,m,now):
        require_tracking_public(m)
        if not m.get('origin_unknown'):return
        if m['uid'] in self.initial:return
        site=m['reference_site']
        source_strict=m.get('source_site')==site and m.get('source_site') is not None
        study=self._study_site_authorized(m)
        allowed=site in m['compatible_sites'] and (source_strict or study)
        row=dict(uid=m['uid'],time_seconds=now,basic_site=site,allowed=allowed,
            authority='SOURCE_STRICT' if source_strict else 'RESEARCH_INITIAL_PLACEMENT' if study else 'MISSING',
            source_customer_permission_claim=False if not source_strict else True,
            can_prestart_place=m.get('can_prestart_place'),preplace_permission_required=False,
            sensitivity_used=False,GPU_registered=False,Initial_is_not_PreSite=True)
        self.initial[m['uid']]=row;self.initial_events.append(deepcopy(row))

    def _candidate(self,m,site,now,*,changing=False):
        reason=None;receipt=None;prep=None
        basic=self.initial[m['uid']]['basic_site'];end=now+max(m['t50_seconds'],1e-9)
        if m['state']!='PENDING':reason='PENDING_ONLY_RUNNING_MOVE_HOLD'
        elif not self.initial[m['uid']]['allowed']:reason='INITIAL_AUTHORITY_MISSING'
        elif now<self._earliest_event(m,None):reason='SOURCE_RELEASE_WINDOW'
        elif now not in set(m.get('representation_starts_seconds') or ()):reason='SOURCE_REPRESENTATION_WINDOW'
        elif m.get('hard_latest_start_seconds') is not None and now>m['hard_latest_start_seconds']:reason='SOURCE_LATEST_START_WINDOW'
        elif m.get('completion_deadline_seconds') is not None and end>m['completion_deadline_seconds']:reason='SOURCE_COMPLETION_DEADLINE'
        elif site not in m['compatible_sites']:reason='SOURCE_SITE_INCOMPATIBLE'
        elif m['gpu']>max(self.packet.rack_compatibility[site]):reason='RACK_GANG_INCOMPATIBLE'
        base=np.array([self.current[1][s] for s in self.packet.sites],float)
        if reason is None and base[self.packet.sites.index(site)]+m['gpu']>self.packet.capacities[site]:reason='CURRENT_GPU_CAPACITY'
        if reason is None and changing:
            if m.get('can_prestart_place') is not True:reason='SOURCE_PREPLACEMENT_AUTHORITY_MISSING'
            else:
                prep,reason=self._current_resource_ledger.owner._preparation(m['uid'],site,now)
                # A transfer may not be fabricated or treated as already ready.
                if reason is None and prep['ready_at_seconds']>now:reason='SOURCE_DATA_WAN_NOT_YET_READY_STAY_AVAILABLE'
                if reason is None and prep['ready_at_seconds']-now>self._current_resource_ledger.owner.budgets[m['uid']].budget_seconds:
                    reason='SHARED_QOS_PREPARATION_BUDGET_EXCEEDED'
        if reason is None:
            vector=base.copy();vector[self.packet.sites.index(site)]+=m['gpu']
            receipt=self.oracle.evaluate(now,vector,uid=m['uid'])
            if receipt.get('PASS') is not True:reason='CURRENT_CANDIDATE_AC_'+receipt.get('status','NOT_CERTIFIED')
        return dict(site=site,kind='PRE_SITE' if changing else 'STAY',feasible=reason is None,reason=reason,
            candidate_AC_input_sha=None if receipt is None else receipt['input_sha'],
            physical=None if receipt is None else {k:receipt[k] for k in ('PASS','status','cache_hit','AC_wall_seconds') if k in receipt},
            preparation=prep,basic_site=basic,sensitivity_score=None)

    def select(self,m,receipt,now,reservations,*,reserve=True):
        began=perf_counter();require_tracking_public(m);self.designate(m,now)
        stay=self._candidate(m,self.initial[m['uid']]['basic_site'],now);rows=[stay]
        alternatives=[]
        # C0 intentionally does not run sensitivity. Both arms keep identical
        # feasibility functions, Source and atomic-start AC rechecks.
        if self.variant=='C1' and m['state']=='PENDING':
            for site in sorted(set(m['compatible_sites'])-{stay['site']}):
                row=self._candidate(m,site,now,changing=True);rows.append(row)
                if row['feasible']:alternatives.append(row)
        chosen=stay if stay['feasible'] else None
        if alternatives:
            for row in [stay,*alternatives]:
                if row['feasible']:row['sensitivity_score']=self.oracle.predicted_score(now,m,row['site'],self.metadata)
            baseline=stay['sensitivity_score']
            for row in sorted(alternatives,key=lambda r:(math.inf if r['sensitivity_score'].get('status')!='PASS'
                    else r['sensitivity_score']['grid_peak'],r['site'])):
                score=row['sensitivity_score']
                if score.get('status')!='PASS':continue
                if chosen is None or baseline is not None and baseline.get('status')=='PASS' and score['grid_peak']<baseline['grid_peak']-1e-10:
                    chosen=row;break
        event=dict(uid=m['uid'],time_seconds=now,basic_site=stay['site'],candidates=deepcopy(rows),
            presite_failed_does_not_fail_initial=True,chosen_site=None if chosen is None else chosen['site'],
            future_private_reads=0)
        self.candidate_events.append(event)
        if chosen is None:decision=dict(uid=m['uid'],action='QUEUE',status='BASIC_SITE_WAIT',reason=stay['reason'])
        else:decision=dict(uid=m['uid'],action='START' if chosen is stay else 'PREPLACE',site=chosen['site'],
            start_seconds=now,nominal_end_seconds=now+max(m['t50_seconds'],1e-9),status='BASIC_STAY' if chosen is stay else 'PENDING_PRE_SITE',
            additional_start_delay_seconds=0,source_reference_start_seconds=_receipt(receipt)['reference_start_seconds'])
        return self._record(m,now,decision,began,len(rows),[r for r in rows if not r['feasible']])

    def current_guard(self,m,segments,now,observed):
        # Atomic, whole gang check immediately before the preserved start.
        use=self._current_resource_ledger.current_gpu_use(now,exclude=m['uid'])
        vector=np.array([use[s] for s in self.packet.sites],float)
        for row in segments:
            if row['resource'].startswith('gpu:') and row['begin']<=now<row['end']:
                site=row['resource'][4:]
                if site not in m['compatible_sites']:return 'ATOMIC_SOURCE_SITE_INCOMPATIBLE'
                if row['quantity']>max(self.packet.rack_compatibility[site]):return 'ATOMIC_RACK_GANG_INCOMPATIBLE'
                vector[self.packet.sites.index(site)]+=row['quantity']
        if any(vector[j]>self.packet.capacities[s] for j,s in enumerate(self.packet.sites)):return 'ATOMIC_GPU_CAPACITY'
        proof=self.oracle.evaluate(now,vector,uid=m['uid'])
        return None if proof.get('PASS') is True else 'ATOMIC_CURRENT_CANDIDATE_AC_'+proof.get('status','NOT_CERTIFIED')


def completed_prefix(controller,now):
    """Already observed episode intervals, integrated exactly like Actual."""
    oracle=controller.policy.oracle;rows=[];sites=oracle.sites
    for slot in range(int((now-oracle.begin)/900)):
        begin=oracle.begin+slot*900;end=begin+900;gpu=np.zeros(len(sites))
        for uid,job in controller.ledger.jobs.items():
            start=job.get('start_time');finish=job.get('completion_observed_time')
            if start is None:continue
            if finish is not None and finish>now:raise ValueError('FUTURE_COMPLETION_IN_PUBLIC_LEDGER')
            finish=now if finish is None else finish
            overlap=max(0.,min(end,finish)-max(begin,start))
            if overlap:gpu[sites.index(job['current_site'])]+=controller.requests[uid].gpu*overlap/900
        observed=oracle.observations.at(begin,observed_now=now)
        physical=oracle.model.recompute(gpu[None,:],sites,[observed['weather']['values']])
        rows.append(dict(slot=slot,start_seconds=begin,end_seconds=end,GPU=gpu.tolist(),
            P=physical['PCC_P_kw'][0].tolist(),Q=physical['PCC_Q_kvar'][0].tolist(),observations=observed,
            authority='OBSERVED_EPISODE_INTERVAL_INTEGRAL_NOT_PREVIOUS_TICK_GPU_HOLD'))
    return rows


class ReleaseController(IsolatedReferenceController):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs);self.actual_start_events=[];self.prefix_rows=[]

    def submit(self,request,now):
        super().submit(request,now);self.policy.designate(self.metadata[request.uid],now)

    def _guard_known(self,uid,now,decision):
        if decision['action']=='QUEUE' or decision['start_seconds']>now:return decision
        use=self.reservations.current_gpu_use(now,exclude=uid);m=self.metadata[uid]
        existing=self.corrective_commands.get(uid)
        if existing:
            if existing['ready_at_seconds']>now:return dict(uid=uid,action='QUEUE',status='KNOWN_PREPARATION_IN_PROGRESS')
            decision=dict(decision,site=existing['actual_site'],start_seconds=now,action='PREPLACE')
        if use[decision['site']]+m['gpu']<=self.ledger.capacities[decision['site']]:return decision
        rejected=[];legal=[]
        if self.policy.corrective_allowed(m):
            for site in sorted(set(m['compatible_sites'])-{decision['site']}):
                reason=None;prep=None
                if use[site]+m['gpu']>self.ledger.capacities[site]:reason='CURRENT_GPU_CAPACITY'
                elif m['gpu']>max(self.policy.packet.rack_compatibility[site]):reason='RACK_GANG_INCOMPATIBLE'
                if reason is None:prep,reason=self._preparation(uid,site,now)
                delay=math.inf if prep is None else prep['ready_at_seconds']-now
                total=max(0.,decision['start_seconds']-self.budgets[uid].reference_start_seconds)+delay
                if reason is None and total>self.budgets[uid].budget_seconds:reason='SHARED_QOS_PREPARATION_BUDGET_EXCEEDED'
                if reason is None:reason=self._hard_window(uid,prep['ready_at_seconds'])
                if reason is None:
                    vector=np.array([use[s] for s in self.policy.packet.sites]);vector[self.policy.packet.sites.index(site)]+=m['gpu']
                    proof=self.policy.oracle.evaluate(now,vector,uid=uid)
                    if proof.get('PASS') is not True:reason='CURRENT_CANDIDATE_AC_FAIL'
                    else:legal.append((max(s['maximum_phase_line_loading'] for s in proof['physical_steps'][-1:]),site,prep))
                if reason:rejected.append(dict(site=site,reason=reason))
        else:rejected.append(dict(site=None,reason='PENDING_KNOWN_PREPLACEMENT_AUTHORITY_MISSING'))
        if legal:
            _,site,prep=min(legal);row=dict(uid=uid,command_type='ACTUAL_CORRECTIVE_COMMAND',
                trigger_seconds=now,original_planned_site=decision['site'],actual_site=site,
                actual_start_seconds=None,reason='ACTUAL_RUNNING_GPU_CAPACITY_CONFLICT',GPU_capacity_conflict=True,
                planning_command_modified=False,**prep)
            if prep['wan_segments']:
                ok,reason=self.reservations.reserve(uid,prep['wan_segments'],replace=True)
                if not ok:return dict(uid=uid,action='QUEUE',status=reason)
            self.corrective_commands[uid]=row;self.corrective_audit.append(deepcopy(row))
            if prep['ready_at_seconds']>now:return dict(uid=uid,action='QUEUE',status='KNOWN_PREPARATION_IN_PROGRESS')
            return dict(decision,site=site,action='PREPLACE')
        self.corrective_audit.append(dict(uid=uid,trigger_seconds=now,status='QUEUE',
            reason='NO_SAFE_CORRECTIVE_SITE',rejected_candidates=rejected,planning_command_modified=False))
        return dict(uid=uid,action='QUEUE',status='NO_SAFE_CORRECTIVE_SITE')

    def _admit_at_tick(self,now):
        self.prefix_rows=completed_prefix(self,now);self.policy.oracle.observe(now,self.prefix_rows)
        starts=super()._admit_at_tick(now)
        for uid in starts:
            row=dict(uid=uid,time_seconds=now,site=self.metadata[uid]['current_site'],GPU=self.requests[uid].gpu,
                origin_unknown=self.metadata[uid]['origin_unknown'],event='ACTUAL_GPU_START',
                basic_site=self.policy.initial.get(uid,{}).get('basic_site'),atomic_AC_rechecked=True)
            self.actual_start_events.append(row)
        print('RC01_TICK',self.policy.variant,int((now-self.policy.oracle.begin)/900),
            'starts',len(starts),'AC',self.policy.oracle.calls,flush=True)
        return starts

    def snapshot(self,now):
        result=super().snapshot(now)
        result['release_state']=dict(scope=SCOPE,initial_placements=deepcopy(self.policy.initial_events),
            actual_starts=deepcopy(self.actual_start_events),prefix=completed_prefix(self,now),
            known_corrective=deepcopy(self.corrective_audit),Running_migration='HOLD')
        return result


def run_variant(source,label,output,*,slots=16):
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    args=deepcopy(source['arguments']);args['end']=args['begin']+slots*900
    args['requests']=[r for r in args['requests'] if r.submit<args['end']]
    obs=source['observations'];sites=tuple(sorted(args['capacities']))
    args['weather']=[obs.at(args['begin']+t*900,observed_now=args['begin']+t*900)['weather']['values'] for t in range(slots)]
    from .production_case import ARCHIVE
    oracle=CurrentACAdmission(begin=args['begin'],sites=sites,power_model=args['power_model'],observations=obs,
        source_freeze=source['freeze']['source_freeze'],manifest=read(ARCHIVE/'CAMPAIGN_MANIFEST.json'),mess=source['mess'])
    policy=ReleasePolicy(source['reference'],source['packet'],variant=label,oracle=oracle,
        bindings=source['bindings'],expected_bindings=source['bindings'],evidence_scope=SCOPE,
        source_identity=dict(study_case_sha=source['release_case_sha'],historical_case_sha=source['freeze']['case_sha']),
        site_authority=initial_authority(source['bindings'],source['release_case_sha']))
    _bind_driver_current_c1(policy,args);policy.save(output/'FROZEN_POLICY.json')
    args.update(arm='B3',frozen_policy=policy,known_schedule=source['commands'],expected_bindings=source['bindings'])
    began=perf_counter();result=run_actual(**args,controller_class=ReleaseController);wall=perf_counter()-began
    state=result['carryout']['controller']['release_state'];prefix=state['prefix']
    np.testing.assert_allclose(result['occupancy_GPU'],[r['GPU'] for r in prefix],rtol=0,atol=1e-10)
    np.testing.assert_allclose(result['physical']['PCC_P_kw'],[r['P'] for r in prefix],rtol=0,atol=1e-9)
    np.testing.assert_allclose(result['physical']['PCC_Q_kvar'],[r['Q'] for r in prefix],rtol=0,atol=1e-9)
    np.savez_compressed(output/'ACTUAL_GPU_PQ.npz',sites=np.array(result['sites']),
        slot_start_seconds=np.arange(args['begin'],args['end'],900),GPU=result['occupancy_GPU'],
        compute_GPU=result['compute_occupancy_GPU'],**{k:result['physical'][k] for k in ('IT_kw','PCC_P_kw','PCC_Q_kvar')})
    write(output/'PUBLIC_PREFIX_ORIGINAL_C1.json',prefix)
    write(output/'INITIAL_PLACEMENT_LEDGER.json',policy.initial_events)
    write(output/'ACTUAL_START_LEDGER.json',state['actual_starts'])
    write(output/'PENDING_PRE_SITE_LEDGER.json',policy.candidate_events)
    write(output/'CURRENT_CANDIDATE_AC_LEDGER.json',oracle.audit)
    write(output/'CONDITIONAL_PUBLIC_Q50_PREDICTION_LEDGER.json',oracle.prediction_audit)
    write(output/'KNOWN_CORRECTIVE_PREPLACEMENT.json',state['known_corrective'])
    for name,key in (('JOB_EVENT_LEDGER.json','job_event_ledger'),('QUEUE_LEDGER.json','queue_ledger'),
        ('QOS_ACTUAL_LEDGER.json','qos_ledger'),('QOS_BUDGET_LEDGER.json','qos_budget_ledger'),
        ('CC4_DEPLETION_LEDGER.json','cc4_depletion_ledger'),('PHYSICAL_RESERVATION_LEDGER.json','reservation_ledger')):
        write(output/name,result[key])
    ticks=result['carryout']['controller']['isolated_reference_state']['control_tick_timings']
    write(output/'CONTROL_TICK_TIMINGS.json',ticks)
    write(output/'PUBLIC_EPISODE_STATE.json',result['carryout']['controller'])
    unknown=[r for r in result['queue_ledger'] if r['origin_unknown']]
    starts=[r for r in state['actual_starts'] if r['origin_unknown']]
    changes=[r for r in starts if r['site']!=r['basic_site']]
    byuid={r['job_uid']:r for r in unknown}
    changed_gpu_h=sum(r['GPU']*max(0.,min(args['end'],byuid[r['uid']]['completion_observed_time'] or args['end'])-
        r['time_seconds'])/3600 for r in changes)
    times=[r['wall_seconds'] for r in ticks]
    metrics=dict(status='EXECUTED_DIAGNOSTIC',scope=SCOPE,policy=label,slots=slots,receipt=result['receipt'],
        release_case_sha=source['release_case_sha'],historical_case_sha=source['freeze']['case_sha'],
        MESS_plan_sha=source['mess']['plan_sha'],policy_sha=policy.sha,Unknown_submitted_UIDs=len(unknown),
        Unknown_initial_placed_UIDs=sum(r['allowed'] for r in policy.initial_events),Unknown_started_UIDs=len(starts),
        PreSite_candidate_UIDs=len({e['uid'] for e in policy.candidate_events if any(r['kind']=='PRE_SITE' for r in e['candidates'])}),
        authorized_ready_alternative_UIDs=len({e['uid'] for e in policy.candidate_events if any(r['kind']=='PRE_SITE' and r['feasible'] for r in e['candidates'])}),
        PreSite_changed_UIDs=len(changes),changed_GPUh=changed_gpu_h,Unknown_STAY_started_UIDs=len(starts)-len(changes),
        Unknown_queued_UIDs=sum(r['admitted_time'] is None for r in unknown),Actual_wall_seconds=wall,
        controller_P50_seconds=float(np.percentile(times,50)),controller_P95_seconds=float(np.percentile(times,95)),
        controller_max_seconds=max(times),controller_900_seconds_PASS=max(times)<900,
        AC_calls=oracle.calls,AC_cache_hits=sum(r['cache_hit'] for r in oracle.audit),
        prefix_GPU_and_Original_C1_PQ_equal_Actual_arrays=True,Native_calls=0,Fresh_AC='NOT_RUN',
        new_D0_planning_handoff=False,Full96='NOT_RUN',campaign_ready=False)
    write(output/'ACTUAL_RESULT.json',metrics)
    return metrics


def run_comparison(output,*,first_event=True):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    if (output/'EXECUTED_SOURCE.json').exists():raise FileExistsError('RC01_NO_OVERWRITE')
    code=[ROOT/'v42_integration'/name for name in ('release_actual.py','current_ac_admission.py',
        'isolated_unknown.py','actual.py','actual_validation.py','aidc_sensitivity_runtime.py')]+[ROOT/'tools/run_v42_release_actual.py']
    receipts=[record(path) for path in code]
    write(output/'EXECUTED_SOURCE.json',dict(scope=SCOPE,files=receipts,Native_calls=0))
    import shutil
    for path in code:
        dest=output/'SOURCE'/path.relative_to(ROOT);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,dest)
    with no_native() as attempts:
        source=prepare_packet(prepare_source());args=source['arguments']
        obs=CausalObservations.load(RAW,begin=args['begin'],end=args['begin']+16*900)
        source['observations']=obs
        common=dict(schema='RC01_SHARED_INITIAL_STAY_OPTIONAL_PENDING_PRESITE_V1',scope=SCOPE,
            historical_PR223_source=source['audit'],new_D0_planning_handoff=False,
            unknown_policy_difference='OPTIONAL_AUTHORIZED_PENDING_PRESITE_ONLY',
            observed_source_bundle_sha=obs.sha,observed_sources=obs.sources,
            current_inputs='OBSERVATION_TIME_AND_LASTCHANGED_LE_NOW_ASOF_NO_INTERPOLATION',
            weather_availability='OBSERVATION_TIMESTAMP_MODEL_NOT_HISTORICAL_INGESTION_CERTIFICATE',
            background_mapping='ORIGINAL_INTERVAL_END_STATIC_LABEL_WITH_INTERVAL_START_ASOF_INPUT',
            Known_commands_sha=digest(source['commands']),MESS_plan_sha=source['mess']['plan_sha'],
            Original_C1_SHA=args['power_model'].authority_sha,code_files=receipts,
            initial_placement_permission_is_not_pre_site_permission=True,old_affine_not_safety_or_ranking_authority=True)
        common['release_case_sha']=digest(common);source['release_case_sha']=common['release_case_sha']
        write(output/'COMMON_RUN_INPUTS.json',common)
        first=min((r for r in args['requests'] if r.submit>args['begin']),key=lambda r:(r.submit,r.uid))
        tick=math.ceil(first.submit/900)*900
        write(output/'FIRST_LEGAL_UNKNOWN_EVENT.json',dict(uid=first.uid,submit_seconds=first.submit,first_control_seconds=tick))
        if first_event:
            count=int((tick-args['begin'])/900)+1
            for label in ('C0','C1'):
                m=run_variant(source,label,output/'FIRST_EVENT'/label,slots=count)
                if not m['Unknown_initial_placed_UIDs'] or not m['Unknown_started_UIDs']:
                    write(output/'FIRST_EVENT_GATE.json',dict(status='FAIL_OR_QUEUED',metrics=m))
                    raise ValueError('RC01_FIRST_REAL_UNKNOWN_NOT_STARTED')
            write(output/'FIRST_EVENT_GATE.json',dict(status='PASS',real_event=True,Native_calls=0))
        results={label:run_variant(source,label,output/label) for label in ('C0','C1')}
        if attempts:raise RuntimeError('RC01_NATIVE_ATTEMPT')
        if [record(path) for path in code]!=receipts:raise ValueError('RC01_EXECUTED_SOURCE_CHANGED')
        summary=dict(status='COMPARISON_COMPLETE',scope=SCOPE,release_case_sha=source['release_case_sha'],
            results=results,Native_calls=0,new_D0_full_chain=False,Full96='NOT_RUN',Fresh_AC='ROOT_VERIFIER_PENDING')
        write(output/'COMPARISON_COMPLETE.json',summary);return summary

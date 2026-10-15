"""RC03 observed-PENDING R1/R2 experiments; PR223 reference/fixed M2 only.

Initial allocation, Known scheduling, private event driver and Source7 are
unchanged. Research data assumptions are distinct from Source permissions.
"""
from copy import deepcopy
import math
from pathlib import Path
from time import perf_counter

import numpy as np

from .release_actual import ReleasePolicy,ReleaseController,completed_prefix,initial_authority
from .rc02_prefix_cache import PrefixCachedCurrentAC
from .research_presite_contract import ResearchPresiteProvider,source_authority
from .policy import digest,_receipt
from .trajectory_tracking import require_tracking_public
from .actual_validation import read,record,write,_validated_hardware_context
from .actual import run_actual
from .aidc_sensitivity_runtime import _bind_driver_current_c1

SCOPE='RC03_RESEARCH_PRESITE_PR223_REFERENCE_FIXED_M2_NOT_D0_FULL_CHAIN'


def control_tick_timings(result):
    return result['carryout']['controller']['isolated_reference_state']['control_tick_timings']


class ObservedSourceAuthority:
    """Private runner lookup returns a single arrived public request projection."""
    def __init__(self,path):
        self.path=Path(path);self.receipt=record(path)

    def at(self,metadata,now):
        # Never attach the future roster to a policy/controller. The original
        # file is checked and one arrived UID is projected by the strict helper.
        if record(self.path)!=self.receipt:raise ValueError('RC03_ORIGINAL_REQUEST_SOURCE_BYTES_DRIFT')
        bundle=read(self.path)
        matches=[r for r in bundle['post_issue_arrivals'] if str(r['job_uid'])==metadata['uid']]
        if len(matches)!=1:raise ValueError('RC03_EXACT_OBSERVED_UNKNOWN_SOURCE_REQUIRED')
        return source_authority(matches[0],self.receipt,now=now)


class ResearchCurrentAC(PrefixCachedCurrentAC):
    def predicted_score(self,now,metadata,site,public_jobs,*,start_seconds=None):
        ready=now if start_seconds is None else max(now,float(start_seconds))
        finish=ready+max(float(metadata['t50_seconds']),1e-9)
        if finish>self.begin+86400:
            return dict(status='NOT_CERTIFIED',reason='PUBLIC_Q50_TAIL_OUTSIDE_FIXED_96_MESS_SUPPORT',
                nominal_horizon_tail_seconds=finish-(self.begin+86400),tail_carry_certified=False,
                current_hard_veto=False,initial_STAY_not_blocked=True)
        if start_seconds is None or start_seconds<=now:
            return super().predicted_score(now,metadata,site,public_jobs)
        # R2 public ready time is conditional, not a future Actual observation.
        if now!=self.now or start_seconds%900:raise ValueError('RC03_PUBLIC_READY_CONTROL_EVENT_REQUIRED')
        first=int((now-self.begin)/900);finish=start_seconds+max(float(metadata['t50_seconds']),1e-9)
        stop=min(96,max(first+1,math.ceil((finish-self.begin)/900)))
        obs=self.observations.at(now,observed_now=now);rows=[]
        for t in range(first,stop):
            begin=self.begin+t*900;end=begin+900;gpu=np.zeros(len(self.sites))
            for m in public_jobs.values():
                if m.get('state')!='RUNNING':continue
                nominal_end=now+max(0.,m['t50_seconds']-m.get('accumulated_compute_seconds',0.))
                if t==first or min(end,nominal_end)>max(begin,now):gpu[self.sites.index(m['current_site'])]+=m['gpu']
            if min(end,finish)>max(begin,start_seconds):gpu[self.sites.index(site)]+=metadata['gpu']
            power=self.model.recompute(gpu[None,:],self.sites,[obs['weather']['values']])
            rows.append(dict(slot=t,start_seconds=begin,GPU=gpu.tolist(),P=power['PCC_P_kw'][0].tolist(),
                Q=power['PCC_Q_kvar'][0].tolist(),observations=obs))
        if start_seconds>=self.begin+86400 or perf_counter()-self.tick_began>self.max_tick_seconds:
            return dict(status='NOT_CERTIFIED',reason='RC03_PUBLIC_READY_OUTSIDE_HORIZON_OR_RESOURCE_CAP')
        if self.probe is not None:
            callback=getattr(self.probe,'predicted_score',None)
            result=callback(deepcopy(rows)) if callback else dict(status='NOT_CERTIFIED',reason='NO_PREDICTION_FIXTURE')
        else:
            self.prediction_calls+=1;proof=self._probe(self.history,rows[0],future_rows=rows)
            peak=max(s['maximum_phase_line_loading'] for s in proof['physical_steps']
                if s['kind'].startswith('CONDITIONAL_PUBLIC_') and s['native_seconds']>=start_seconds-self.begin)
            result=dict(status='PASS',grid_peak=peak,physical_receipt=proof)
        result.update(checked_slots=list(range(int((start_seconds-self.begin)/900),stop)),
            projection='PUBLIC_Q50_STARTING_AT_CONTRACT_READY_WITH_CURRENT_EXOGENOUS_HOLD',
            public_ready_at_seconds=start_seconds,future_Actual_Tap_Completion_reads=0,
            predicted_AUTO_actions_are_not_Actual_state=True,current_hard_veto=False,
            nominal_horizon_tail_seconds=max(0.,finish-(self.begin+86400)),tail_carry_certified=False)
        self.prediction_audit.append(deepcopy(result));return result


class ResearchReleasePolicy(ReleasePolicy):
    def __init__(self,*args,research_provider,source_authority_lookup,**kwargs):
        if not isinstance(research_provider,ResearchPresiteProvider):raise ValueError('RC03_VERSIONED_RESEARCH_PROVIDER_REQUIRED')
        super().__init__(*args,**kwargs)
        self.research=research_provider;self.authority_lookup=source_authority_lookup
        self.research_selections=[]
        self.spec.update(release_scope=SCOPE,research_environment=deepcopy(self.research.spec),
            research_science_sha=self.research.science_sha,
            initial_authority_grants_presite=False,source_metadata_modified=False,
            research_assumption_is_customer_permission=False,
            conditional_Q50_prediction_is_actual=False,
            prefix_observation_cache='EXACT_SOURCE_BOUND_PROOF_ALL_NATIVE_SOLVES_RETAINED')
        self.sha=digest(self.spec)

    def register_observed(self,m,now):
        if m.get('origin_unknown') is True:
            authority=self.authority_lookup.at(m,now)
            self.research.register_observed(m,authority,now=now)

    def _candidate(self,m,site,now,*,changing=False):
        if not changing:return super()._candidate(m,site,now,changing=False)
        owner=self._current_resource_ledger.owner
        proposal=self.research.propose(m,site,now,day_begin=self.reference.begin,qos_receipt=owner.budgets[m['uid']])
        if proposal['status']=='REJECTED':
            return dict(site=site,kind='PRE_SITE',feasible=False,reason=proposal['reason'],
                basic_site=self.initial[m['uid']]['basic_site'],sensitivity_score=None,
                research_data_contract=proposal,executable_now=False)
        # Common Source/GPU/rack/current-candidate AC checks are identical to
        # STAY. This does not mutate a raw/default can_prestart_place flag.
        result=super()._candidate(m,site,now,changing=False)
        result.update(kind='PRE_SITE',research_data_contract=proposal,
            executable_now=proposal['status']=='READY',
            preparation=dict(ready_at_seconds=proposal['ready_at_seconds'],
                transfer_seconds=proposal['transfer_seconds'],preparation_seconds=proposal['preparation_seconds'],
                WAN_segments=proposal['WAN_segments'],provenance_class='ASSUMED',
                research_science_sha=self.research.science_sha))
        return result

    def select(self,m,receipt,now,reservations,*,reserve=True):
        began=perf_counter();require_tracking_public(m);self.designate(m,now)
        stay=self._candidate(m,self.initial[m['uid']]['basic_site'],now);rows=[stay]
        alternatives=[]
        if self.variant=='C1' and m['state']=='PENDING':
            for site in sorted(set(m['compatible_sites'])-{stay['site']}):
                row=self._candidate(m,site,now,changing=True);rows.append(row)
                if row['feasible']:alternatives.append(row)
        chosen=stay if stay['feasible'] else None
        if alternatives:
            for row in [stay,*alternatives]:
                if row['feasible']:
                    start=now if row is stay else max(now,row['research_data_contract']['ready_at_seconds'])
                    try:row['sensitivity_score']=self.oracle.predicted_score(now,m,row['site'],self.metadata,start_seconds=start)
                    except (ValueError,RuntimeError) as exc:
                        row['sensitivity_score']=dict(status='NOT_CERTIFIED',reason='OPTIONAL_RESEARCH_Q50_PREDICTION:'+str(exc))
            baseline=stay['sensitivity_score']
            for row in sorted(alternatives,key=lambda r:(math.inf if r['sensitivity_score'].get('status')!='PASS'
                    else r['sensitivity_score']['grid_peak'],r['site'])):
                score=row['sensitivity_score']
                if score.get('status')!='PASS':continue
                if chosen is None or baseline is not None and baseline.get('status')=='PASS' and score['grid_peak']<baseline['grid_peak']-1e-10:
                    chosen=row;break
        transfer_wait=False;transfer_failure=None
        if chosen is not None and chosen is not stay and not chosen['executable_now']:
            proposal=chosen['research_data_contract']
            if proposal.get('transfer_committed'):
                transfer_wait=True
            elif self.research.spec['scenario']=='R2':
                committed,transfer_failure=self.research.commit_transfer(proposal,current_metadata=m,now=now)
                transfer_wait=committed
            else:
                # R1 delayed readiness follows the same original QoS gate.
                transfer_wait=True
            if transfer_failure:chosen=stay if stay['feasible'] else None
        event=dict(uid=m['uid'],episode_id=m.get('episode_id'),time_seconds=now,basic_site=stay['site'],
            scenario=self.research.spec['scenario'],research_science_sha=self.research.science_sha,
            candidates=deepcopy(rows),chosen_site=None if chosen is None else chosen['site'],
            transfer_or_access_wait=transfer_wait,transfer_failure=transfer_failure,
            initial_failure_inferred_from_presite_failure=False,source_metadata_changed=False,
            future_private_reads=0)
        self.candidate_events.append(event);self.research_selections.append(deepcopy(event))
        if chosen is None:decision=dict(uid=m['uid'],action='QUEUE',status='BASIC_SITE_WAIT',reason=stay['reason'])
        elif transfer_wait:decision=dict(uid=m['uid'],action='QUEUE',status='RESEARCH_DATA_PREPARATION_PENDING',
            ready_at_seconds=chosen['research_data_contract']['ready_at_seconds'],GPU_started=False)
        else:
            preparation_delay=0.
            if chosen is not stay:
                p=chosen['research_data_contract']
                if p.get('transfer_committed'):preparation_delay=p['ready_at_seconds']-p['transfer_begin_seconds']
            decision=dict(uid=m['uid'],action='START' if chosen is stay else 'PREPLACE',site=chosen['site'],
                start_seconds=now,nominal_end_seconds=now+max(m['t50_seconds'],1e-9),
                status='BASIC_STAY' if chosen is stay else 'RESEARCH_PENDING_PRE_SITE',
                additional_start_delay_seconds=preparation_delay,
                source_reference_start_seconds=_receipt(receipt)['reference_start_seconds'])
        charged_preparation=decision.get('additional_start_delay_seconds',0)
        result=self._record(m,now,decision,began,len(rows),[r for r in rows if not r['feasible']])
        if charged_preparation>0:
            # Preparation consumes the unchanged source budget. It is not a
            # new scheduling/time-shifting permission, and cannot be erased
            # by the inherited Initial/STAY-only receipt normalization.
            result.update(additional_start_delay_seconds=charged_preparation,
                research_preparation_budget_used_seconds=charged_preparation,
                intentional_time_shift_seconds=0)
            self.last_selection[m['uid']]=deepcopy(result)
            self.audit[-1]['decision']=deepcopy(result)
        return result


class ResearchReleaseController(ReleaseController):
    def submit(self,request,now):
        super().submit(request,now)
        self.policy.register_observed(self.metadata[request.uid],now)

    def snapshot(self,now):
        result=super().snapshot(now)
        result['release_state'].update(scope=SCOPE,research_science_sha=self.policy.research.science_sha,
            research_assumptions_are_Source_facts=False,Source_metadata_changed=False)
        return result


def run_research_variant(source,label,output,*,spec,proof_records,slots=16):
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    args=deepcopy(source['arguments']);args['end']=args['begin']+slots*900
    args['requests']=[r for r in args['requests'] if r.submit<args['end']]
    obs=source['observations'];sites=tuple(sorted(args['capacities']))
    args['weather']=[obs.at(args['begin']+t*900,observed_now=args['begin']+t*900)['weather']['values'] for t in range(slots)]
    from .production_case import ARCHIVE
    from .isolated_unknown import RAW
    native=read(RAW/'NATIVE_INPUT_TEMPLATE_B1.json')
    provider=ResearchPresiteProvider(spec,native_wan=native['WAN'])
    oracle=ResearchCurrentAC(begin=args['begin'],sites=sites,power_model=args['power_model'],observations=obs,
        source_freeze=source['freeze']['source_freeze'],manifest=read(ARCHIVE/'CAMPAIGN_MANIFEST.json'),mess=source['mess'],
        proof_records=proof_records)
    policy=ResearchReleasePolicy(source['reference'],source['packet'],variant=label,oracle=oracle,
        research_provider=provider,source_authority_lookup=ObservedSourceAuthority(RAW/'ACTUAL_INPUT_BUNDLE.json'),
        bindings=source['bindings'],expected_bindings=source['bindings'],evidence_scope=SCOPE,
        source_identity=dict(study_case_sha=source['release_case_sha'],historical_case_sha=source['freeze']['case_sha']),
        site_authority=initial_authority(source['bindings'],source['release_case_sha']))
    _bind_driver_current_c1(policy,args);policy.save(output/'FROZEN_POLICY.json')
    args.update(arm='B3',frozen_policy=policy,known_schedule=source['commands'],expected_bindings=source['bindings'])
    began=perf_counter()
    with _validated_hardware_context(oracle.freeze,oracle.manifest):
        result=run_actual(**args,controller_class=ResearchReleaseController)
    wall=perf_counter()-began
    state=result['carryout']['controller']['release_state'];prefix=state['prefix']
    np.testing.assert_allclose(result['occupancy_GPU'],[r['GPU'] for r in prefix],rtol=0,atol=1e-10)
    np.testing.assert_allclose(result['physical']['PCC_P_kw'],[r['P'] for r in prefix],rtol=0,atol=1e-9)
    np.savez_compressed(output/'ACTUAL_GPU_PQ.npz',sites=np.array(result['sites']),
        slot_start_seconds=np.arange(args['begin'],args['end'],900),GPU=result['occupancy_GPU'],
        compute_GPU=result['compute_occupancy_GPU'],**{k:result['physical'][k] for k in ('IT_kw','PCC_P_kw','PCC_Q_kvar')})
    ledgers={'PUBLIC_PREFIX_ORIGINAL_C1.json':prefix,'INITIAL_PLACEMENT_LEDGER.json':policy.initial_events,
        'ACTUAL_START_LEDGER.json':state['actual_starts'],'PENDING_PRE_SITE_LEDGER.json':policy.candidate_events,
        'CURRENT_CANDIDATE_AC_LEDGER.json':oracle.audit,'CONDITIONAL_PUBLIC_Q50_PREDICTION_LEDGER.json':oracle.prediction_audit,
        'KNOWN_CORRECTIVE_PREPLACEMENT.json':state['known_corrective'],'RESEARCH_DATA_ACCESS_LEDGER.json':provider.export(),
        'JOB_EVENT_LEDGER.json':result['job_event_ledger'],'QUEUE_LEDGER.json':result['queue_ledger'],
        'QOS_ACTUAL_LEDGER.json':result['qos_ledger'],'QOS_BUDGET_LEDGER.json':result['qos_budget_ledger'],
        'PHYSICAL_RESERVATION_LEDGER.json':result['reservation_ledger'],'CC4_DEPLETION_LEDGER.json':result['cc4_depletion_ledger'],
        'CONTROL_TICK_TIMINGS.json':control_tick_timings(result)}
    for name,value in ledgers.items():write(output/name,value)
    write(output/'PUBLIC_EPISODE_STATE.json',result['carryout']['controller'])
    starts=[r for r in state['actual_starts'] if r['origin_unknown']]
    changed=[r for r in starts if r['site']!=r['basic_site']]
    unknown={r['job_uid']:r for r in result['queue_ledger'] if r['origin_unknown']}
    changed_gpuh=sum(r['GPU']*max(0.,min(args['end'],unknown[r['uid']]['completion_observed_time'] or args['end'])-
        r['time_seconds'])/3600 for r in changed)
    ticks=[r['wall_seconds'] for r in ledgers['CONTROL_TICK_TIMINGS.json']]
    metrics=dict(status='EXECUTED_DIAGNOSTIC',scope=SCOPE,scenario=spec['scenario'],policy=label,
        release_case_sha=source['release_case_sha'],research_science_sha=provider.science_sha,
        research_environment_sha=digest(spec),historical_case_sha=source['freeze']['case_sha'],
        MESS_plan_sha=source['mess']['plan_sha'],policy_sha=policy.sha,slots=slots,receipt=result['receipt'],
        Unknown_submitted_UIDs=len(unknown),Unknown_initial_placed_UIDs=len(policy.initial_events),Unknown_started_UIDs=len(starts),
        PreSite_eligible_UIDs=len({r['uid'] for r in provider.audit if r['eligible']}),
        authorized_ready_alternative_UIDs=len({e['uid'] for e in policy.candidate_events if any(
            r['kind']=='PRE_SITE' and r['feasible'] and r.get('executable_now') for r in e['candidates'])}),
        PreSite_changed_UIDs=len(changed),changed_GPUh=changed_gpuh,Unknown_STAY_started_UIDs=len(starts)-len(changed),
        Unknown_queued_UIDs=sum(r['admitted_time'] is None for r in unknown.values()),
        Actual_wall_seconds=wall,controller_P50_seconds=float(np.percentile(ticks,50)),
        controller_P95_seconds=float(np.percentile(ticks,95)),controller_max_seconds=max(ticks),
        controller_900_seconds_PASS=max(ticks)<900,AC_calls=oracle.calls,prefix_proof_cache_hits=oracle.prefix_hits,
        conditional_prediction_AC_calls=oracle.conditional_engine_calls,
        conditional_prediction_requests=oracle.prediction_calls,
        conditional_prediction_exact_cache_hits=oracle.conditional_proof_hits,
        AC_cache_hits=sum(r['cache_hit'] for r in oracle.audit),
        research_transfer_commits=len(provider.transfer_history),research_assumptions_are_source_facts=False,
        original_source_metadata_changed=False,original_QoS_extended=False,Native_calls=0,
        Fresh_AC='NOT_RUN',Gate_contract='SLOTTED_SETTLED_ORIGINAL_PR223_V1',
        diagnostic_substep_status='PRIOR_FIXED_M2_SUBSTEP_PHYSICAL_FAIL_PRESERVED_NOT_OFFICIAL_VETO',
        new_D0_planning_handoff=False,Full96='NOT_RUN',campaign_ready=False)
    write(output/'ACTUAL_RESULT.json',metrics)
    return metrics

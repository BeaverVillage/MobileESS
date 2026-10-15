"""Separate per-job literature R2 replay, preserving RC03 attempt 02 bytes.

Only the explicitly approved payload example and the requested guard order
differ. The original event/reference/fixed-MESS diagnostic remains unchanged.
"""
from copy import deepcopy
from pathlib import Path
from time import perf_counter

import numpy as np

from .actual import run_actual
from .actual_validation import read,write,_validated_hardware_context
from .aidc_sensitivity_runtime import _bind_driver_current_c1
from .research_presite_actual import (ResearchReleasePolicy,ResearchReleaseController,
    ResearchCurrentAC,ObservedSourceAuthority,control_tick_timings)
from .research_presite_transfer_literature import LiteratureTransferProvider,validate_literature_spec
from .release_actual import initial_authority
from .policy import digest

SCOPE='RC03_LITERATURE_PER_JOB_R2_PR223_REFERENCE_FIXED_M2_NOT_D0_FULL_CHAIN'


class LiteratureReleasePolicy(ResearchReleasePolicy):
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


def run_literature_variant(source,label,output,*,spec,proof_records,slots=16):
    validate_literature_spec(spec)
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    args=deepcopy(source['arguments']);args['end']=args['begin']+slots*900
    args['requests']=[r for r in args['requests'] if r.submit<args['end']]
    obs=source['observations'];sites=tuple(sorted(args['capacities']))
    args['weather']=[obs.at(args['begin']+t*900,observed_now=args['begin']+t*900)['weather']['values'] for t in range(slots)]
    from .production_case import ARCHIVE
    from .isolated_unknown import RAW
    native=read(RAW/'NATIVE_INPUT_TEMPLATE_B1.json')
    provider=LiteratureTransferProvider(spec,native_wan=native['WAN'])
    oracle=ResearchCurrentAC(begin=args['begin'],sites=sites,power_model=args['power_model'],observations=obs,
        source_freeze=source['freeze']['source_freeze'],manifest=read(ARCHIVE/'CAMPAIGN_MANIFEST.json'),mess=source['mess'],
        proof_records=proof_records)
    policy=LiteratureReleasePolicy(source['reference'],source['packet'],variant=label,oracle=oracle,
        research_provider=provider,source_authority_lookup=ObservedSourceAuthority(RAW/'ACTUAL_INPUT_BUNDLE.json'),
        bindings=source['bindings'],expected_bindings=source['bindings'],evidence_scope=SCOPE,
        source_identity=dict(study_case_sha=source['release_case_sha'],historical_case_sha=source['freeze']['case_sha']),
        site_authority=initial_authority(source['bindings'],source['release_case_sha']))
    policy.spec.update(release_scope=SCOPE,candidate_guard_order='COMPATIBILITY_GPU_RACK_DATA_QOS_CURRENT_AC_SENSITIVITY',
        payload_model=spec['payload_model'],legacy_80GB_per_GPU_proxy_used=False)
    policy.sha=digest(policy.spec);_bind_driver_current_c1(policy,args);policy.save(output/'FROZEN_POLICY.json')
    args.update(arm='B3',frozen_policy=policy,known_schedule=source['commands'],expected_bindings=source['bindings'])
    began=perf_counter()
    with _validated_hardware_context(oracle.freeze,oracle.manifest):
        result=run_actual(**args,controller_class=ResearchReleaseController)
    wall=perf_counter()-began;state=result['carryout']['controller']['release_state'];prefix=state['prefix']
    for actual,key in ((result['occupancy_GPU'],'GPU'),(result['physical']['PCC_P_kw'],'P'),(result['physical']['PCC_Q_kvar'],'Q')):
        np.testing.assert_allclose(actual,[r[key] for r in prefix],rtol=0,atol=1e-9)
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
    gpuh=sum(r['GPU']*max(0.,min(args['end'],unknown[r['uid']]['completion_observed_time'] or args['end'])-r['time_seconds'])/3600 for r in changed)
    ticks=[r['wall_seconds'] for r in ledgers['CONTROL_TICK_TIMINGS.json']]
    metrics=dict(status='EXECUTED_DIAGNOSTIC',scope=SCOPE,scenario='R2',policy=label,slots=slots,
        release_case_sha=source['release_case_sha'],research_science_sha=provider.science_sha,research_environment_sha=digest(spec),
        historical_case_sha=source['freeze']['case_sha'],MESS_plan_sha=source['mess']['plan_sha'],policy_sha=policy.sha,receipt=result['receipt'],
        Unknown_submitted_UIDs=len(unknown),Unknown_initial_placed_UIDs=len(policy.initial_events),Unknown_started_UIDs=len(starts),
        PreSite_eligible_UIDs=len({r['uid'] for r in provider.audit if r['eligible']}),
        PreSite_changed_UIDs=len(changed),changed_GPUh=gpuh,Unknown_STAY_started_UIDs=len(starts)-len(changed),
        Unknown_queued_UIDs=sum(r['admitted_time'] is None for r in unknown.values()),
        authorized_ready_alternative_UIDs=len({e['uid'] for e in policy.candidate_events if any(r['kind']=='PRE_SITE' and r['feasible'] and r.get('executable_now') for r in e['candidates'])}),
        Actual_wall_seconds=wall,controller_P50_seconds=float(np.percentile(ticks,50)),controller_P95_seconds=float(np.percentile(ticks,95)),
        controller_max_seconds=max(ticks),controller_900_seconds_PASS=max(ticks)<900,AC_calls=oracle.calls,
        prefix_proof_cache_hits=oracle.prefix_hits,AC_cache_hits=sum(r['cache_hit'] for r in oracle.audit),
        conditional_prediction_AC_calls=oracle.conditional_engine_calls,research_transfer_commits=len(provider.transfer_history),
        payload_MB_per_job=spec['absolute_payload_MB_per_job'],payload_is_Kestrel_measurement=False,payload_scales_with_GPU=False,
        legacy_80GB_per_GPU_proxy_used=False,original_source_metadata_changed=False,original_QoS_extended=False,
        Fresh_AC='NOT_RUN',Gate_contract='SLOTTED_SETTLED_ORIGINAL_PR223_V1',Native_calls=0,
        new_D0_planning_handoff=False,Full96='NOT_RUN',campaign_ready=False)
    write(output/'ACTUAL_RESULT.json',metrics);return metrics

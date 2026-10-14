"""Native0 contract audit. Private Environment values are never accessed."""
from pathlib import Path
import sys, json, csv, hashlib, time
from collections import Counter
from copy import deepcopy
from dataclasses import asdict, fields, replace
ROOT=Path(__file__).parents[2]
sys.path.insert(0,str(ROOT))
from v42_integration.experimental_replay import load_conditional_source
from v42_integration.experimental_qos import (ExperimentalQoSProvider, ExperimentalBudgetReceipt,
    bind_experimental_native_job,participation_for,digest,FROZEN_SEED,SCENARIOS,PARTICIPATION)
from v42_integration.qos import ObservedJob
from v42_a_stage_domain_v2.domain import physical_starts
from v42_job_capability import Option,validate
from v42_boundary.generator import Generator
OUT=Path(__file__).parent
def write(name,value):
    (OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
def record(path):
    path=Path(path)
    return dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest())
start=time.perf_counter()
source=load_conditional_source()
prepared,planning=source['fresh_actual_inputs']()
arguments=prepared['arguments'];strict=planning['qos_provider'];data=source['data']
known_issue={uid:ObservedJob(**dict(row['observed'],representation_starts_seconds=tuple(row['observed']['representation_starts_seconds'])))
             for uid,row in planning['known_receipts'].items()}
observed_requests=[r for r in arguments['requests'] if r.submit<=arguments['begin']]+[r[0] for r in arguments['running']]
observed_requests += sorted([r for r in arguments['requests'] if r.submit>arguments['begin']],key=lambda r:(r.submit,r.uid))
active_known={r.uid for r in observed_requests if not r.metadata['origin_unknown']}
unknown_requests=[r for r in observed_requests if r.metadata['origin_unknown']]
assert len(known_issue)==1649 and len(active_known)==1546 and len(unknown_requests)==774
assert len(set(r.uid for r in observed_requests))==2320
reference=deepcopy(arguments['reference'])
unknown={}
for request in unknown_requests:
    now=max(arguments['begin'],request.submit)
    ref=reference.assigned.get(request.uid)
    if ref is None:ref=reference.submit(request,event_seconds=now)
    args={f.name:request.metadata[f.name] for f in fields(ObservedJob) if f.name in request.metadata}
    args.update(uid=request.uid,submit_seconds=request.submit,event_seconds=now,
        reference_start_seconds=request.metadata.get('reference_start_seconds',ref['reference_start_seconds']),
        t50_seconds=request.q50,gpu=request.gpu,is_observed=True,provider_sha=strict.provider_sha,
        reference_sha=reference.reference_sha)
    unknown[request.uid]=ObservedJob(**args)
assert len(unknown)==774
all_observed={**known_issue,**unknown}
known_sha=digest({u:asdict(j) for u,j in sorted(known_issue.items())})
raw_sha=digest({u:asdict(j) for u,j in sorted(all_observed.items())})
source_manifests=[record(ROOT/'v42_integration/experimental_qos.py'),record(ROOT/'tests/test_v42_experimental_qos.py')]
source_manifests+=source['source_receipts']
def jsonable(value):
    if isinstance(value,dict):return {str(k):jsonable(v) for k,v in value.items()}
    if isinstance(value,(tuple,list)):return [jsonable(v) for v in value]
    return value
native_physical_sha=digest(jsonable(asdict(data[3])))
membership=[];cases=[];equivalence=[];domain_rows=[];domain_cache={}
native_fields=('uid','state','submit','event','reference_start','reference_site','service_slots','gpu',
               'elapsed_seconds','unknown_arrival','duration_authority','migrations_used')
for scenario in SCENARIOS:
    for flex in PARTICIPATION:
        check_begin=time.perf_counter()
        strict_case=deepcopy(strict)
        proto=ExperimentalQoSProvider(strict_case,scenario=scenario,participation=flex)
        case_sha=(strict.case_sha if scenario=='E0' else digest(dict(policy_spec_sha=proto.stats.sha,
            original_planning_case_sha=strict.case_sha,known_issue_observed_sha=known_sha,
            seed=FROZEN_SEED,scope='NEW_KNOWN_CONTRACT_DOMAIN_NATIVE_NOT_SOLVED')))
        provider=ExperimentalQoSProvider(strict_case,scenario=scenario,participation=flex,case_sha=case_sha)
        receipts={};model_counts=Counter();budget_counts=Counter()
        for uid,job in sorted(known_issue.items()):
            receipts[uid]=provider.issue(job)
        assert len(provider.receipts)==1649 # No future Unknown at Planning.
        planning_ledger_sha=digest(provider.export_ledger())
        for uid,job in sorted(unknown.items(),key=lambda row:(row[1].event_seconds,row[0])):
            receipts[uid]=provider.issue(job)
        for uid,job in sorted(all_observed.items()):
            rec=receipts[uid];member=participation_for(uid,seed=FROZEN_SEED)
            model=(rec.model_metadata if isinstance(rec,ExperimentalBudgetReceipt) else dict(qos=job.qos,
                protected=job.protected,batch_eligible=job.batch_eligible))
            eligible=(rec.eligible_for_contract if isinstance(rec,ExperimentalBudgetReceipt) else rec.budget_seconds>0)
            participant=(rec.participant and eligible if isinstance(rec,ExperimentalBudgetReceipt) else False)
            origin='KNOWN_ISSUE' if uid in known_issue else 'UNKNOWN_OBSERVED_SUBMIT'
            active=uid not in known_issue or uid in active_known
            gpu_h=job.gpu*job.t50_seconds/3600
            membership.append(dict(scenario=scenario,participation=flex,uid=uid,episode_identity='UID_FALLBACK',
                origin=origin,active_Dday=active,observed_event_seconds=job.event_seconds,
                state_at_issue=job.state,source_qos=job.qos,source_protected=job.protected,
                source_batch_eligible=job.batch_eligible,modeled_qos=model['qos'],
                eligible_for_assumed_contract=eligible,research_contract_participant=participant,
                hash_threshold_selected=member['membership'][flex],membership_sha=member['membership_sha'],
                nominal_GPUh=gpu_h,contract_budget_seconds=rec.budget_seconds,
                original_reference_start_seconds=rec.reference_start_seconds,
                original_issue_allowed_starts=len(rec.allowed_starts_seconds),
                Can_TimeShift_assumed=(participant and job.state=='PENDING' and rec.budget_seconds>0),
                Can_Preplace_assumed=(participant and job.state=='PENDING'),
                Can_Checkpoint_Migrate_assumed=(participant and job.state=='RUNNING'),
                physical_migration_validated=False,contract_is_observed_SLA=False,
                receipt_sha=digest(rec.to_dict()),policy_case_sha=case_sha))
            if active:model_counts[model['qos']]+=1;budget_counts[str(rec.budget_seconds)]+=1
            # Same public observation at a different origin/event has same eligibility,
            # participation and immutable B. This is a formula test, not a future replay.
            if scenario!='E0':
                mirror_provider=ExperimentalQoSProvider(strict,scenario=scenario,participation=flex,case_sha=case_sha)
                mirror=mirror_provider.issue(replace(job,origin_unknown=not job.origin_unknown,event_seconds=job.event_seconds+900))
                assert (rec.budget_seconds,rec.participant,rec.model_metadata)==(mirror.budget_seconds,mirror.participant,mirror.model_metadata)
        selected=[r for r in membership if r['scenario']==scenario and r['participation']==flex]
        subsets={}
        for key,predicate in [('Known_issue_1649',lambda r:r['origin']=='KNOWN_ISSUE'),
            ('Known_active_1546',lambda r:r['origin']=='KNOWN_ISSUE' and r['active_Dday']),
            ('Unknown_observed_774',lambda r:r['origin']=='UNKNOWN_OBSERVED_SUBMIT'),
            ('Dday_active_2320',lambda r:r['active_Dday'])]:
            rows=[r for r in selected if predicate(r)];participants=[r for r in rows if r['research_contract_participant']]
            total_h=sum(r['nominal_GPUh'] for r in rows);selected_h=sum(r['nominal_GPUh'] for r in participants)
            subsets[key]=dict(jobs=len(rows),participants=len(participants),participant_job_percent=100*len(participants)/len(rows),
                nominal_GPUh=total_h,participant_nominal_GPUh=selected_h,participant_nominal_GPUh_percent=100*selected_h/total_h,
                positive_budget_jobs=sum(r['contract_budget_seconds']>0 for r in rows),
                assumed_pending_preplace_jobs=sum(r['Can_Preplace_assumed'] for r in rows),
                assumed_running_checkpoint_jobs=sum(r['Can_Checkpoint_Migrate_assumed'] for r in rows))
        # Exact source native local domains, no solver/coupled schedulability claim.
        resources=data[3]
        generator=Generator(resources,max(b.latest_completion for b in data[2].values()))
        total_stays=total_blocks=total_taus=empty=0;changed_preserved=True;history=True
        for uid,native in sorted(data[1].items()):
            rec=receipts[uid]
            baseline_preplace=bool(planning['known_receipts'][uid]['native_reference'].get('can_prestart_place'))
            bound_native=bind_experimental_native_job(native,rec,axis_origin_seconds=prepared['issue_epoch_seconds'],
                source_can_prestart_place=baseline_preplace,
                assumed_checkpoint_authorized=False,migration_physical_authority_sha=native_physical_sha)
            # Source RUNNING remaining-service origin never becomes a restart instruction.
            starts=bound_native.qos_allowed_starts
            boundary=replace(data[2][uid],allowed_starts=starts)
            signature=asdict(bound_native);signature.pop('qos_receipt_sha')
            cache_key=digest(dict(job=signature,boundary=asdict(boundary)))
            if cache_key not in domain_cache:
                # Exact original STAY membership: finite physical_starts +
                # original whole-gang/rack static sites + immutable GPU masks.
                # Avoid one full service-array reconstruction per option.
                initial,_=generator.static_sites(bound_native)
                kept=[]
                for t in physical_starts(bound_native,boundary,resources.control_end):
                    if bound_native.qos_start_delay_seconds+max(0,t-bound_native.reference_start)*900>bound_native.qos_budget_seconds+1e-9:
                        continue
                    for site in initial:
                        if generator.fits(site,t,bound_native.service_slots,bound_native.gpu):kept.append((t,site))
                if kept:
                    for t,site in {kept[0],kept[-1]}:
                        validate(bound_native,Option(t,site,((site,t,t+bound_native.service_slots),)),boundary,resources)
                domain_cache[cache_key]=dict(stays=len(kept),blocks=0,taus=0,
                    physical_support_sha=digest(dict(stays=kept,migration='NOT_ENUMERATED_PHASE_A_STAY_SCOPE')))
            count=domain_cache[cache_key];blocks=count['blocks'];taus=count['taus']
            total_stays+=count['stays'];total_blocks+=blocks;total_taus+=taus;empty+=not(count['stays'] or blocks)
            preserved=all(getattr(native,k)==getattr(bound_native,k) for k in native_fields)
            changed_preserved &= preserved
            if native.state=='RUNNING':history &= starts==(native.reference_start,)
            domain_rows.append(dict(scenario=scenario,participation=flex,uid=uid,state=native.state,
                gpu=native.gpu,service_slots=native.service_slots,original_reference_start=native.reference_start,
                authorized_start_count=len(starts),stay_options=count['stays'],migration_blocks=blocks,
                migration_transfer_timestamp_options=taus,source_can_prestart_place=baseline_preplace,
                checkpoint_authorized=bound_native.checkpoint_authorized,contract_budget_seconds=rec.budget_seconds,
                quantity_service_history_preserved=preserved,physical_support_sha=count['physical_support_sha'],
                coupled_feasibility='NOT_RUN_NO_GLOBAL_WITNESS'))
        assert changed_preserved and history
        cases.append(dict(scenario=scenario,participation=flex,policy_spec_sha=proto.stats.sha,new_planning_case_sha=case_sha,
            same_UID_fallback_identity=True,planning_unknown_UIDs_issued=0,planning_receipts=1649,
            planning_ledger_sha=planning_ledger_sha,observed_execution_receipts=len(receipts),
            active_source_qos='UNCONFIRMED',model_qos_counts=dict(model_counts),budget_counts=dict(budget_counts),
            populations=subsets,native_jobs=len(data[1]),native_local_stays=total_stays,
            native_migration_blocks=total_blocks,native_migration_transfer_timestamp_options=total_taus,
            native_empty_local_domains=empty,source_native_quantity_service_history_preserved=changed_preserved,
            expanded_assumed_Native_migration_enumeration='NOT_RUN_PHASE_A_STAY_DOMAIN_SCOPE',
            running_native_boundary_preserved=history,native_domain_is_global_feasibility_proof=False,
            full_A_M_or_Actual_or_AC='NOT_RUN',elapsed_seconds=time.perf_counter()-check_begin,
            E0_strict_ledger_unchanged=digest({u:receipts[u].to_dict() for u in known_issue})==
                digest({u:strict.receipts[u].to_dict() for u in known_issue}) if scenario=='E0' else None))
        equivalence.append(dict(scenario=scenario,participation=flex,public_jobs_compared=len(all_observed),
            same_formula=True,origin_event_invariance='STRICT_DELEGATION' if scenario=='E0' else 'PASS',
            same_UID_fallback=True,known_issue_only_at_planning=True,unknown_only_after_observation=True))
        print(f'{scenario}/{flex}: active contract {subsets["Dday_active_2320"]["participants"]}; native stays {total_stays}, blocks {total_blocks}, empty {empty}',flush=True)
for name,rows in [('FLEX20_30_40_MEMBERSHIP_AUDIT.csv',membership),('NATIVE_KNOWN_DOMAIN_AUDIT.csv',domain_rows)]:
    with (OUT/name).open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
assert digest({u:asdict(j) for u,j in sorted(all_observed.items())})==raw_sha
for uid in all_observed:
    flags=participation_for(uid,seed=FROZEN_SEED)['membership']
    assert not flags['FLEX20'] or flags['FLEX30']
    assert not flags['FLEX30'] or flags['FLEX40']
write('E0_E1_E2_POLICY_MANIFEST.json',dict(schema='EXPERIMENTAL_QOS_PHASE_A_NATIVE0_V1',policy_id=proto.spec['policy_id'],
    seed=FROZEN_SEED,threshold_rule='HASH_PER_OBSERVED_UID_NO_EXACT_QUOTA_NO_FUTURE_SELECTION',cases=cases,
    original_source_science_sha=source['original_source_science_sha'],original_planning_case_sha=strict.case_sha,
    source_native_physical_sha=native_physical_sha,known_issue_observed_sha=known_sha,
    post_submit_observed_audit_sha=raw_sha,source_receipts=source_manifests,
    raw_observation_mutations=0,private_Environment_accesses=0,Native_Optimize_calls=0,AC_calls=0,Actual_runs=0,
    old_FULL_or_LB_transferred=False,new_policy_source_frozen=False,elapsed_seconds=time.perf_counter()-start))
write('SOURCE_VS_ASSUMED_QOS_CONTRACT.json',dict(source_observed=dict(active_jobs=2320,qos={'UNCONFIRMED':2320},
    protected='UNCONFIRMED_NONE',batch='UNCONFIRMED_NONE',raw_fields_unmodified=True,
    planning_known_legacy_classes='MODELED_SOURCE_DOMAIN_LABELS_NOT_OBSERVED_REQUEST_QOS'),
    assumed=dict(default_missing='ASSUMED_NORMAL_BATCH',scenario_caps_seconds=SCENARIOS,
        participation_seed=FROZEN_SEED,checkpoint='ASSUMED_CHECKPOINTABLE_FOR_EXPERIMENT',
        physical_WAN_payload_restart='ORIGINAL_NATIVE_RESOURCES_WITH_POSITIVE_TRANSFER_AND_RESTART',
        physical_authority_sha=native_physical_sha,protected_high_urgent_nonbatch_preserved=True,
        contract_is_observed_SLA=False),execution_semantics=dict(original_reference_and_budget_immutable=True,
        candidate_local_reference='OBSERVED_GRID_BLIND_FEASIBLE_REFERENCE_V1',
        unavoidable_capacity_wait_is_not_intentional=True,cumulative_burden_not_renewed=True,
        burden='prior_intentional_start_delay + new_intentional_start_delay + all_migration_interruption <= immutable_B'),
    evidence_scope='SOURCE_CONTRACT_AND_EXACT_LOCAL_NATIVE_STAY_DOMAINS_NO_OPTIMIZE',
    expanded_assumed_native_migration_enumeration='NOT_RUN_BOUNDED_CONTROL_REPLAY_SEPARATE'))
write('KNOWN_UNKNOWN_POLICY_EQUIVALENCE.json',dict(PASS=True,cases=equivalence,
    UID_EPISODE_rule='ALL_SOURCE_AUDIT_USES_UID_FALLBACK_ALSO_USED_AT_ORIGINAL_KNOWN_ISSUE',
    raw_observation_mutations=0,Known_original_receipts=1649,Known_active=1546,Known_historical=103,
    Unknown_observed=774,Unknown_prefix=78,Unknown_Dday_submit=696,
    nominal_GPUh_measure='FROZEN_GPU_GANG_TIMES_TOTAL_Q50_SECONDS_NOT_ACTUAL_REMAINING_SERVICE',
    Native_Optimize_calls=0,Actual_runs=0,AC_calls=0,Source_SLA_claim=False))
(OUT/'EXPERIMENTAL_FLEX_QOS_POLICY_KO.md').write_text('''# 실험용 QoS 계약 — Phase A Native0\n\nE0는 기존 Source-only issuer를 그대로 사용한다. E1은 Normal 30분·Standby 60분, E2는 Normal 60분·Standby 120분을 연구용 추가 지연 상한으로 부여한다. 실제 Kestrel SLA를 관측한 값이 아니다. 확인된 High/Urgent/Protected 및 명시적 non-batch 권한은 유지한다.\n\nMay01 요청 QoS는 UNCONFIRMED이며 보호·Batch 권한도 확인되지 않았다. 본 연구의 주 가정은 ASSUMED_NORMAL_BATCH다. 기존 Planning 도메인의 Standby 라벨을 관측된 요청 QoS로 승격하지 않는다. 원시 관측값은 별도로 유지한다.\n\n참여 Seed는 May 성능 실험 전 고정했다. UID fallback과 SHA256 임계값으로 FLEX20/30/40를 중첩 선택한다. 미래 Unknown 전체를 보고 정확한 비율을 맞추지 않는다. Known 1,649건은 원래 issue 정보로 결정하고, Unknown 774건은 제출·초기 관측 후에만 결정했다. D-day 활성 Known은 1,546건이며 완료된 103건의 원래 receipt는 보존한다. 실제 참여 Job 비율과 total Q50 nominal GPUh 비율은 CSV 및 manifest에서 별도로 보고한다.\n\n발급 시 원래 기준 시작·계약 B는 불변이다. 경량 replay는 현재 관측된 grid-blind feasible reference를 후보별로 기록하여 불가피한 용량 대기를 의도적 지연과 분리한다. 이전 의도적 지연과 모든 Migration 중단은 같은 B에서 계속 차감하고 재발급하지 않는다.\n\nNative 도메인은 원래 1,499개 modeling Job의 GPU·서비스·RUNNING 경계를 보존하며 원본 Generator로 local hard-valid 후보를 셌다. 연구용 Checkpoint 가능성은 참여 집단에 가정하되 원래 WAN/Payload/Restart 모델을 함께 적용했다. local 후보 수는 공동 스케줄 가능성의 증명이 아니다. 새로운 QoS 도메인에는 새로운 Case SHA가 필요하며 이전 A/M FULL·LB·Gap을 이전하지 않는다.\n\n이 산출물은 Phase A Source 및 Native0 감사다. Native Optimize, Actual 실행, Fresh AC는 0회다. 별도 경량 replay 및 새 통합 Full96 결과는 이 문서의 검증으로 주장하지 않는다. B2/B3 M 및 전체 캠페인 HOLD는 유지한다.\n''',encoding='utf-8')
write('QOS_PHASE_A_ARTIFACT_MANIFEST.json',dict(status='PASS_NATIVE0_SOURCE_CONTRACT_AUDIT',
    artifacts=[record(OUT/name) for name in ['E0_E1_E2_POLICY_MANIFEST.json','SOURCE_VS_ASSUMED_QOS_CONTRACT.json',
        'KNOWN_UNKNOWN_POLICY_EQUIVALENCE.json','FLEX20_30_40_MEMBERSHIP_AUDIT.csv','NATIVE_KNOWN_DOMAIN_AUDIT.csv',
        'EXPERIMENTAL_FLEX_QOS_POLICY_KO.md']],Native0=True,Actual_runs=0,AC_calls=0,
    shared_solver_budget_debit=0,source_snapshot_sha=digest(source_manifests[:2])))

"""Read-only V5 Job/QoS/candidate funnel audit; snapshot code, immutable receipts."""
from pathlib import Path
from collections import Counter,defaultdict,deque
import csv,hashlib,json,math,sys
ROOT=Path('D:/v42_policy_root_cause_20261013');sys.path.insert(0,str(ROOT))
OUT=ROOT/'audit/job_actual';OUT.mkdir(parents=True,exist_ok=True)
RUN=Path('D:/v42_integration_validation_20261013/DDAY_V5_B3_FINAL_ATTEMPT01')
P=RUN/'B3';RAW=Path('D:/v42_may_joint_repair_campaign_20261013/raw/2025-05-01')
def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def record(path):
    path=Path(path);data=path.read_bytes();return dict(path=str(path),bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
def write(name,value):
    (OUT/name).write_text(json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf8')
def rows(name,data):
    keys=list(dict.fromkeys(k for row in data for k in row))
    with (OUT/name).open('w',newline='',encoding='utf-8-sig') as f:
        out=csv.DictWriter(f,fieldnames=keys);out.writeheader()
        for row in data:out.writerow({k:json.dumps(v,ensure_ascii=False,sort_keys=True) if isinstance(v,(list,dict,tuple)) else v for k,v in row.items()})
a=read(P/'ACTUAL_RESULT.json');pol=read(P/'OPTIMIZED_CONDITIONAL_CONTROL_POLICY.json');freeze=read(P/'PLANNING_FREEZE.json')
binding=read(RUN/'CASE/ACTUAL_INITIAL_STATE_BINDING.json');initial=read(binding['initial_state_freeze']['path'])
plan=read(RAW/'PLANNING_INPUT_BUNDLE.json');raw=read(RAW/'ACTUAL_INPUT_BUNDLE.json')
stats_receipt=next(r for r in binding['source_receipts'] if Path(r['path']).name=='QOS_EMPIRICAL_STATS_STRICT.json')
stats=read(stats_receipt['path']);assert record(stats_receipt['path'])==stats_receipt
controller=a['carryout']['controller'];meta=controller['metadata'];budgets=a['qos_budget_ledger'];rules=a['rule_consumption_receipt']
queue={r['job_uid']:r for r in a['queue_ledger']};known={r['job_uid'] for r in plan['known_population']}
run={r['uid'] for r in initial['running']};pending={r['uid'] for r in initial['pending']};historical={r['job_uid'] for r in initial['historical_completed']}
begin=initial['begin_epoch_seconds'];end=initial['end_epoch_seconds'];active=set(meta)
by_uid=defaultdict(list)
for rule in rules:by_uid[rule['uid']].append(rule)
checkpoint_by_uid=Counter(e['uid'] for e in a['job_event_ledger'] if e['event']=='RUNNING_STAY')
def population(uid):return 'INITIAL_RUNNING' if uid in run else 'INITIAL_PENDING' if uid in pending else 'DDAY_UNKNOWN_SUBMISSION'
def eligible_delay(uid):
    m=meta[uid];r=budgets[uid]
    return m.get('protected') is False and m.get('batch_eligible') is True and m.get('qos') in ('normal','standby') and r['budget_seconds']>0
def preplace(uid):return meta[uid].get('can_prestart_place') is True and len(meta[uid]['compatible_sites'])>1
def migrate(uid):return bool(meta[uid].get('migration_capability')) and meta[uid].get('migration_count',0)<1
job_rows=[]
for uid in sorted(active):
    m=meta[uid];q=queue[uid];r=budgets[uid];events=by_uid[uid]
    full_reasons=list(r['reasons'])
    if m.get('qos') not in ('normal','standby'):full_reasons.append('OBSERVED_QOS_CLASS_UNCONFIRMED_OR_INELIGIBLE')
    if stats['accepted_unique_uids']==0:full_reasons.append('STRICT_TRAIN_ALL_ROWS_SOURCE_PROVENANCE_EXCLUDED')
    if m.get('requested_walltime_seconds') is None:full_reasons.append('REQUESTED_WALLTIME_UNCONFIRMED')
    if not m.get('partition'):full_reasons.append('PARTITION_UNCONFIRMED')
    record_episode=controller['episode_jobs'][uid]['episode_id']
    job_rows.append(dict(uid=uid,episode_id=record_episode,population=population(uid),origin_unknown=m['origin_unknown'],
        raw_Planning_Known_UID=uid in known,initial_state='RUNNING' if uid in run else 'PENDING' if uid in pending else 'NOT_YET_SUBMITTED_AT_DD00',
        submit_seconds=controller['requests'][uid]['submit'],gpu=controller['requests'][uid]['gpu'],
        observed_qos=m['qos'],protected=m.get('protected'),batch_eligible=m.get('batch_eligible'),
        requested_walltime_seconds=m.get('requested_walltime_seconds'),request_version_authority=m.get('request_version_authority'),
        source_cohort_evidence_proxy=m.get('source_cohort_evidence'),
        budget_seconds=r['budget_seconds'],reference_wait_seconds=r['reference_wait_seconds'],
        empirical_wait_seconds=r['empirical_wait_seconds'],cohort_n=r['cohort_n'],cohort_level=r['cohort_level'],
        receipt_status=r['status'],first_issuer_reason=r['reasons'][0],all_issuer_reason_codes=r['reasons'],all_independent_source_predicates=full_reasons,
        additional_delay_capability=eligible_delay(uid),source_preplace_flag=preplace(uid),
        migration_packet_present=bool(m.get('migration_capability')),checkpoint_observed_events=checkpoint_by_uid[uid],
        migration_runtime_count=m.get('migration_count',0),known_frozen_schedule_present=uid in controller.get('decisions',{}) and uid in freeze['Known_schedule'],
        controller_policy_dispatch_events=len(events),pending_dispatch_events=sum(e['action']=='QUEUE' for e in events),
        running_dispatch_events=sum(e['action']=='STAY' for e in events),
        first_actual_dispatch_failure=None if not events else events[0]['reason'],
        all_recorded_actual_failure_reasons=sorted({e['reason'] for e in events}),
        policy_select_or_lookup_reached_events=0,actual_individual_candidates_generated=0,
        actual_individual_grid_scores=0,actual_policy_approved_actions=0,actual_policy_executed_actions=0,
        final_state=q['latest_state'],actual_admitted_time=q['admitted_time'],intentional_burden_seconds=next(x['total_intentional_burden_seconds'] for x in a['qos_ledger'] if x['uid']==uid),
        actual_fallback_or_stay=bool(events),counterfactual_lookup_authority_block='NOT_EXECUTED_IN_PRODUCTION; source lookup requires protectedFalse/batchTrue',
        first_failure_scope='ACTUAL_OUTER_RESOURCE_SUPPORT_GUARD' if events else 'NO_POLICY_EVENT_BEFORE_DAY_END'))
rows('MAY01_UID_EPISODE_ELIGIBILITY_AUDIT.csv',job_rows)
groups=dict(ALL_ACTIVE=active,INITIAL_RUNNING=run,INITIAL_PENDING=pending,
    ACTIVE_D1_KNOWN=active&known,PREFIX_UNKNOWN_ACTIVE=(run|pending)-known,
    DDAY_UNKNOWN_SUBMISSIONS=active-run-pending,INITIAL_KNOWN_RUNNING=run&known,
    INITIAL_UNKNOWN_RUNNING=run-known,INITIAL_KNOWN_PENDING=pending&known,INITIAL_UNKNOWN_PENDING=pending-known)
funnel=[]
for name,uids in groups.items():
    dispatch=[r for r in rules if r['uid'] in uids];queried=set(r['uid'] for r in dispatch)
    values=[('1_TOTAL',len(uids),'UID_EPISODE'),('2_CONTROLLER_DISPATCH_ENTERED',len(queried),'UID_EPISODE'),
        ('2_CONTROLLER_DISPATCH_EVENTS',len(dispatch),'EVENT'),('2_POLICY_SELECT_LOOKUP_ENTERED',0,'EVENT'),
        ('3_SUPPORTED_QOS_COHORT',sum(budgets[u]['cohort_n']>=100 for u in uids),'UID_EPISODE'),
        ('4_POSITIVE_INTENTIONAL_DELAY_BUDGET',sum(budgets[u]['budget_seconds']>0 for u in uids),'UID_EPISODE'),
        ('5_INDEPENDENT_SOURCE_PREPLACE_FLAG',sum(preplace(u) for u in uids),'UID_EPISODE'),
        ('6_SOURCE_MIGRATION_PACKET',sum(migrate(u) for u in uids),'UID_EPISODE'),
        ('6_PHYSICAL_CHECKPOINT_OBSERVED_UID',sum(checkpoint_by_uid[u]>0 for u in uids),'UID_EPISODE'),
        ('7_ACTUAL_INDIVIDUAL_CANDIDATE_GENERATED',0,'CANDIDATE'),('8_ACTUAL_CANDIDATE_HARD_PASS',0,'CANDIDATE'),
        ('9_ACTUAL_CANDIDATE_GRID_SCORE',0,'CANDIDATE'),('10_ACTUAL_CANDIDATE_IMPROVEMENT',0,'CANDIDATE'),
        ('11_ACTUAL_POLICY_APPROVAL',0,'CANDIDATE'),('12_ACTUAL_POLICY_EXECUTION',0,'ACTION'),
        ('13_ACTUAL_GUARDED_FALLBACK_UID',len(queried),'UID_EPISODE'),('13_ACTUAL_GUARDED_FALLBACK_EVENTS',len(dispatch),'EVENT')]
    funnel.extend(dict(population=name,stage=stage,count=count,count_unit=unit,
        mapping_scope='REAL_OBSERVED_JOB; NOT_OFFLINE_ANONYMOUS_PROTOTYPE',
        known_command_preplace_is_separate=True,origin_unknown_exclusion_in_policy=False) for stage,count,unit in values)
funnel += [dict(population='OFFLINE_ANONYMOUS_PROTOTYPES',stage=stage,count=count,count_unit=unit,
    mapping_scope='NO_FUTURE_UID_MAPPING_NOT_JOB_COUNT') for stage,count,unit in [
    ('1_TEMPLATE',len(pol['templates']),'TEMPLATE'),('7_VARIANTS_MATERIALIZED',pol['metrics']['bounded_candidates'],'CANDIDATE'),
    ('9_OFFLINE_CANDIDATE_SCORED',sum(len(t['scenario_comparisons']) for t in pol['templates']),'CANDIDATE'),
    ('11_OFFLINE_CANDIDATE_APPROVED',sum(len(t['ordered_actions']) for t in pol['templates']),'CANDIDATE')]]
funnel += [dict(population=name,stage='1_SOURCE_POPULATION_IDENTITY',count=count,count_unit='UID',
    mapping_scope=scope) for name,count,scope in [
    ('ALL_RAW_KNOWN_PLUS_POST_ISSUE',2498,'FULL_RAW_SOURCE_ROSTER_NOT_ACTIVE_JOB_COUNT'),
    ('D1_KNOWN_ORIGINAL_ISSUE',1649,'1546_ACTIVE_PLUS103_HISTORICAL_KNOWN'),
    ('ORIGIN_UNKNOWN_ALL_POST_ISSUE',849,'78_PREFIX_ACTIVE_PLUS696_DDAY_SUBMIT_PLUS75_HISTORICAL_UNKNOWN'),
    ('HISTORICAL_COMPLETED_ALL',178,'OUTSIDE_DDAY_ACTIVE_ROSTER'),
    ('HISTORICAL_COMPLETED_KNOWN',103,'RECEIPTS_RETAINED_PLANNING_NO_ACTIVE_GPU'),
    ('HISTORICAL_COMPLETED_UNKNOWN',75,'NO_DDAY_ACTIVE_GPU_NO_CC4_DEPLETION')]]
rows('MAY01_POLICY_ELIGIBILITY_FUNNEL.csv',funnel)

# Recover original finite variant enumeration; preserve generated-vs-attempted
# migration distinction and every recorded score/rejection in source order.
candidate_rows=[];rejection_rows=[];scores_seen=0;resource_seen=0;baseline_skipped=0
for template in pol['templates']:
    tid=template['template_id'];state=template['state'];site=template['reference_site']
    rejected=template['rejected_candidates'];unscored=[r for r in rejected if r.get('reason')=='PROTOTYPE_REFERENCE_NOT_IN_ANONYMOUS_ENVELOPE']
    scoreq=deque(template['scenario_comparisons']);rejectq=deque(r for r in rejected if r.get('reason') not in ('PROTOTYPE_REFERENCE_NOT_IN_ANONYMOUS_ENVELOPE','NO_AUTHORITY_CAPABILITY_UNCONFIRMED'))
    variants=[('STAY',site,0)] if state=='RUNNING' else [
        ('PREPLACE' if dest!=site else 'START_NOW' if delay==0 else 'DELAY_'+str(delay//60),dest,delay)
        for delay in (0,900,1800,2700,3600) for dest in pol['site_axis']]
    for ordinal,(action,destination,delay) in enumerate(variants):
        first=None;score=None;failure=None
        if unscored:first='PROTOTYPE_REFERENCE_NOT_IN_ANONYMOUS_ENVELOPE';baseline_skipped+=1
        elif scoreq and (scoreq[0]['action'],scoreq[0]['site'],scoreq[0]['delay_seconds'])==(action,destination,delay):
            score=scoreq.popleft();scores_seen+=1
            if not score['hard_feasible']:
                failure=rejectq.popleft();assert failure['action']==action and failure['site']==destination
                first=failure['reason']
        else:
            failure=rejectq.popleft();assert failure['action']==action and failure['site']==destination
            first=failure['reason'];resource_seen+=1
        cid=tid+':VARIANT:'+str(ordinal)
        candidate_rows.append(dict(candidate_id=cid,scope='OFFLINE_ANONYMOUS_PROTOTYPE_NOT_ACTUAL_UID',template_id=tid,
            time_slot=template['time_slot'],state=state,gpu=template['gpu'],qos=template['qos'],
            action=action,site=destination,delay_seconds=delay,variant_materialized=True,
            actual_UID=None,prototype_reference_supported=not bool(unscored),
            first_failure=first,resource_guard_pass=score is not None,grid_score_executed=score is not None,
            candidate_score_count=0 if score is None else len(score['scenario_scores']),
            scenario_scores=None if score is None else score['scenario_scores'],
            hard_constraints_pass=False if score is None else score['hard_feasible'],approved=False,actual_executed=False))
        if failure and failure.get('scenarios'):
            for scenario,value in failure['scenarios'].items():
                for v in value['violations']:
                    rejection_rows.append(dict(candidate_id=cid,template_id=tid,scope='OFFLINE_CANDIDATE_SCORED',
                        first_failure=first,all_failure_reason=v['reason'],scenario=scenario,
                        runtime_endpoint_aggregation=True,occurrences=v.get('occurrences'),
                        slot_count=v.get('slot_count'),slot_examples=v.get('slot_examples'),
                        branch_count=v.get('branch_count'),branch_examples=v.get('branch_examples'),
                        occurrences_not_unique_candidate_count=True))
        else:rejection_rows.append(dict(candidate_id=cid,template_id=tid,scope='OFFLINE_CANDIDATE_FIRST_REACHABLE_FAILURE',first_failure=first,all_failure_reason=first,
            unreachable_later_guard_reasons='NOT_EVALUATED_NO_INVENTED_ALL_REASONS'))
    assert not scoreq and not rejectq
    for ordinal,rejection in enumerate(r for r in rejected if r.get('reason')=='NO_AUTHORITY_CAPABILITY_UNCONFIRMED'):
        rejection_rows.append(dict(candidate_id=tid+':MIGRATION_ATTEMPT:'+str(ordinal),template_id=tid,
            scope='MIGRATION_GUARD_ATTEMPT_NOT_MATERIALIZED_VARIANT',first_failure=rejection['reason'],
            all_failure_reason=rejection['reason'],site=rejection['site'],candidate_materialized=False))
assert len(candidate_rows)==4392 and scores_seen==309 and resource_seen==972 and baseline_skipped==3111
rows('MAY01_CANDIDATE_GENERATION_AUDIT.csv',candidate_rows)
rows('MAY01_CANDIDATE_REJECTION_REASONS.csv',rejection_rows)
runtime=[];boundary=[];policy_begin=pol['begin_seconds'];policy_end=pol['end_seconds']
for ordinal,event in enumerate(rules):
    control=event['frozen_support_control_seconds'];physical=event['time_seconds'];index=math.floor((control-policy_begin)/900)
    outside=[]
    if 0<=index<96:
        support=pol['runtime_resource_support']
        for j,site in enumerate(pol['site_axis']):
            observed=event['observed_GPU_by_site'][site];lower=support['lower_GPU'][index][j];upper=support['upper_GPU'][index][j]
            if observed<lower-1e-9 or observed>upper+1e-9:outside.append(site)
        assert outside==event['outside_support_sites']
    else:assert event['reason']=='NO_FROZEN_RESOURCE_SUPPORT_AUTHORITY'
    row=dict(event_id=ordinal,uid=event['uid'],episode_id=controller['episode_jobs'][event['uid']]['episode_id'],
        population=population(event['uid']),origin_unknown=meta[event['uid']]['origin_unknown'],
        dispatch_action=event['action'],physical_time_seconds=physical,control_lookup_seconds=control,policy_slot_index=index,
        first_executed_failure=event['reason'],resource_support_missing_is_end_boundary=index==96,
        outside_support_sites=outside,actual_policy_lookup_reached=False,
        independent_not_reached_authority_failure='ACTION_QOS_AUTHORITY_UNCONFIRMED',
        independent_not_reached_qos_class_failure='NO_NORMAL_OR_STANDBY_OBSERVED_REQUEST_AUTHORITY',
        offgrid_migration_template_failure_not_reached=event['action']=='STAY' and physical%900!=0,
        later_candidates_grid_scores_not_reached=True)
    runtime.append(row)
    if index==96:boundary.append(row)
rows('ACTUAL_FIRST_GUARD_EVENT_AUDIT.csv',runtime)
rows('MISSING_SUPPORT_53_BOUNDARY_AUDIT.csv',boundary)
earliest=rules[0];site_evidence=[]
for j,site in enumerate(pol['site_axis']):
    site_evidence.append(dict(site=site,Actual_GPU=earliest['observed_GPU_by_site'][site],
        frozen_nominal_GPU=pol['runtime_resource_baseline_GPU'][0][j],
        lower_GPU=pol['runtime_resource_support']['lower_GPU'][0][j],
        upper_GPU=pol['runtime_resource_support']['upper_GPU'][0][j],
        A2_known_GPU=read(P/'A2/A_RESULT.json')['known_site_GPU'][site][0],
        A2_anonymous_GPU=read(P/'A2/A_RESULT.json')['nominal_site_GPU'][site][0]))
write('DD00_RUNTIME_RESOURCE_SUPPORT_MISMATCH.json',dict(first_UID=earliest['uid'],
    first_time=earliest['time_seconds'],physical_sites=site_evidence,
    initial_only_running_GPU=sum(r['gpu'] for r in initial['running']),
    initial_admission_pass_counts_observed_after_known_starts=True,
    actual_initial_state_SHA=initial['common_initial_state_sha'],A2_anchor=freeze['aidc_anchor'],M2_anchor=freeze['mess_anchor'],
    source_axis_correct=policy_begin==begin and policy_end==end,
    classification='OBSERVED_REAL_MODEL_INITIAL_CAPACITY_OCCUPATION_OUTSIDE_FROZEN_NOMINAL_AND_Q90_POINTWISE_SUPPORT',
    scope='CONSERVATIVE_SUPPORT_GUARD; NOT_PROOF_PHYSICAL_CURRENT_STATE_UNSAFE; NOT_INDEX_SHIFT'))
reason_counts=Counter(x for r in budgets.values() for x in r['reasons'])
qos_audit=dict(schema='QOS_ZERO_BUDGET_CAUSE_AUDIT_V1',PASS=True,
    strict_TRAIN_loaded_and_SHA_verified=stats_receipt,strict_TRAIN=stats,
    minimum100_or_backoff_failure_primary=False,backoff_L0_L3_available=True,
    TRAIN_first_failure=dict(function='TrainingStatistics.from_records',condition='provenance not in supported_request_provenances',
        first_reason='UNSUPPORTED_REQUEST_PROVENANCE',rows=439534,accepted_UIDs=0,cohorts=0),
    May_independent_metadata_failures=dict(active_UIDs=2320,protected_unconfirmed=2320,batch_unconfirmed=2320,
        observed_qos_UNCONFIRMED=2320,confirmed_normal=0,confirmed_standby=0,
        minimum100_or_requested_walltime_not_first_select_failure='select returnsNone on protectedNone before bucket matching'),
    issuer_receipts=dict(total=2423,Planning_known=1649,active_known_reused=1546,inactive_historical_known=103,
        Actual_origin_unknown_issued=774,Actual_prefix_unknown=78,Actual_Dday_unknown=696,
        active_UIDs=2320,positive_budget_UIDs=0,first_reason_counts=dict(Counter(r['reasons'][0] for r in budgets.values())),
        all_recorded_reason_counts=dict(reason_counts),reference_wait_is_primary=False,
        baseline_QOS_excess_count=reason_counts['BASELINE_QOS_EXCESS'],empirical_wait_values_all_null=all(r['empirical_wait_seconds'] is None for r in budgets.values())),
    issuer_expression='B=0 if reasons else 900*floor(min(max(0,empirical_wait-reference_wait),3600)/900)',
    raw_known_population_qos_fields_present=sum('qos' in r for r in plan['known_population']),
    actual_preplace_independent=dict(source_flag_TRUE=1245,active_known_initial_pending_TRUE=1245,all_unknown_TRUE=0,
        migration_packet_present=0,positive_delay_budget=0,can_prestart_place_not_derived_from_B=True,
        universal_lookup_mask='protectedFalse AND batchTrue applied before action-specific filtering; latentpreplacemaskreviewownedlead',
        no_May_unknown_preplace_authority_demonstrated=True),
    hard_contract_earliest_latest_deadline_confirmed=0,representation_completion_promoted_to_deadline=False,
    no_budget_reissue_or_enlargement=True,Known_receipt_identity_preserved=True,
    quantities_seconds_and_900slots_checked=True,
    source_semantics='StrictsourceaccountingproxyCannotAuthorizeRequestVersion; no60minRelaxationOrMayRefit',
    Source18r_original_known_job_qos_model_labels=dict(Counter(j['qos'] for j in read(P/'FRESH_PHYSICAL/FRESH_PHYSICAL_RESULT.json')['case_scope']['planning_identity']['known_job_descriptors'].values())),
    offline_template_qos=dict(Counter(t['qos'] for t in pol['templates'])))
write('QOS_ZERO_BUDGET_CAUSE_AUDIT.json',qos_audit)
missing_known=sorted(u for u in active if not by_uid.get(u) and u in known)
missing_unknown=sorted(u for u in active if not by_uid.get(u) and u not in known)
assert len(missing_known)==1498 and len(missing_unknown)==8
not_entered=[]
initial_by_uid={r['uid']:r for r in initial['running']}
for uid in missing_unknown:
    if uid in run:
        row=initial_by_uid[uid];elapsed=row['elapsed_compute_seconds']
        next_checkpoint=begin+1800-elapsed%1800
        observed_completion=queue[uid]['completion_observed_time']
        assert observed_completion is not None and observed_completion<=next_checkpoint
        not_entered.append(dict(uid=uid,population='INITIAL_UNKNOWN_RUNNING',reason='COMPLETED_BEFORE_NEXT_EXECUTION_CHECKPOINT',
            initial_elapsed_compute_seconds=elapsed,next_checkpoint_seconds=next_checkpoint,completion_observed_seconds=observed_completion,
            source='POSTRUN_OBSERVED_EVENT_AUDIT_ONLY_NOT_PLANNING_FEATURE'))
    else:
        submit=controller['requests'][uid]['submit'];first_due=math.ceil(submit/900)*900
        assert first_due==end and queue[uid]['admitted_time'] is None
        not_entered.append(dict(uid=uid,population='DDAY_UNKNOWN_SUBMISSION',reason='NO_ADMISSION_CONTROL_BOUNDARY_BEFORE_DAY_END',
            submit_seconds=submit,first_admission_control_seconds=first_due,day_end_seconds=end,carryout=True))
write('UNKNOWN_8_NO_POLICY_EVENT_AUDIT.json',dict(UID_count=8,initial_running_completed_before_checkpoint=5,
    late_Dday_pending_no_admission_boundary=3,records=not_entered))
runtime_audit=dict(schema='POLICY_FREEZE_RELOAD_RUNTIME_AUDIT_JOB_PARTITION_V1',PASS=True,
    real_May_scope=True,source_snapshot=record(ROOT/'audit/SOURCE_SNAPSHOT.json'),
    policy_freeze_loaded=record(P/'OPTIMIZED_CONDITIONAL_CONTROL_POLICY.json'),
    freeze_bindings={k:freeze[k] for k in ('science_sha','case_sha','aidc_anchor','mess_anchor','initial_state_sha')},
    Actual_policy_SHA=a['carryout']['policy_sha'],policy_SHA=pol['policy_sha'],
    full_Model_scope_not_original_Kestrel_site_observation=True,
    dispatch_events=5816,dispatch_unique_UIDs=814,dispatch_unknown_UIDs=766,dispatch_known_UIDs=48,
    policy_actual_select_lookup_reached=0,resource_outer_first_reasons=dict(Counter(r['reason'] for r in rules)),
    pending_controller_policy_attempts=748,running_controller_policy_attempts=5068,
    offline_anonymous_templates=144,offline_materialized_variants=4392,offline_scored_candidates=309,
    offline_template_reference_skipped_variants=3111,offline_resource_rejected_variants=972,
    attempted_migration_destinations_not_generated=792,offline_hard_passed_scored_candidates=0,offline_ordered_approved_actions=0,
    Actual_individual_candidates_generated=0,Actual_individual_grid_score_calls=0,Actual_selected_control_actions=0,
    actual_unknown_population=774,Dday_unknown=696,prefix_unknown=78,
    actual_UNKNOWN_pending_policy_attempt_UIDs=748,actual_UNKNOWN_Dday_pending_attempt_UIDs=693,
    unknown_not_evaluated_uids=missing_unknown,
    unknown_not_evaluated_count=len(missing_unknown),
    unknown_missing_policy_event_reasons=dict(Counter(r['reason'] for r in not_entered)),
    late_Dday_unknown_missing_policy_due_before_end=[u for u in missing_unknown if u not in run|pending],
    known_not_entering_unknown_policy_dispatch_UID_count=len(missing_known),
    known_not_entering_unknown_policy_dispatch_UIDs=missing_known,
    known_frozen_command_preplace_flags=1245,
    first_vs_all_reasons_scope='Recordedresourceguardfirst; QoS/cohort/capabilityadditionalpredicatesnotexecuted; noinventedcounterfactualcandidateapproval',
    missing_support_53=dict(events=53,physical_at_end=43,physical_lastslot_ceil_to_end=10,all_STAY=True,
        policy_axis_begin=policy_begin,policy_axis_end=policy_end,Actual_axis_begin=begin,Actual_axis_end=end,
        reason='resource_support_at computes96outside[0,96); no epoch/slot-origin mismatch'),
    actual_fallback_action_counts=dict(Counter(r['action'] for r in rules)),
    origin_unknown_not_global_exclusion=True,origin_known_RUNNING_can_enter_policy_without_frozen_command=True,
    actual_GlobalOptimizerCalls=0,ML_fit_calls=0,AC_reruns=0,
    behavioral_effectiveness='NOT_ESTABLISHED',Full96_AC_PASS_is_separate=True)
assert runtime_audit['Actual_policy_SHA']==runtime_audit['policy_SHA']
write('POLICY_FREEZE_RELOAD_RUNTIME_AUDIT.json',runtime_audit)
sources=[record(P/name) for name in ('ACTUAL_RESULT.json','OPTIMIZED_CONDITIONAL_CONTROL_POLICY.json','PLANNING_FREEZE.json','CONTROL_POLICY_RUNTIME_MEMORY.json')]
sources += [record(ROOT/name) for name in ('v42_integration/actual.py','v42_integration/qos.py','v42_integration/sensitivity_policy.py','v42_integration/actual_validation.py')]
sources += [stats_receipt,record(RAW/'PLANNING_INPUT_BUNDLE.json'),record(RAW/'ACTUAL_INPUT_BUNDLE.json'),record(Path(__file__))]
write('JOB_ACTUAL_SOURCE_MANIFEST.json',dict(source_sha=freeze['science_sha'],snapshot_source_sha=read(ROOT/'audit/SOURCE_SNAPSHOT.json')['source_sha'],sources=sources,
    no_source_or_original_artifact_edits=True,Native_Optimize_calls=0,Full96_Actual_replays=0,AC_reruns=0))
print(json.dumps(dict(output=str(OUT),active=len(active),qos_receipts=len(budgets),dispatch_UIDs=814,
    actual_lookup=0,candidate_variants=len(candidate_rows),scores=scores_seen,baseline_skipped=baseline_skipped,
    resource_rejected=resource_seen,preplace_flag_True=1245,UnknownpreplaceTrue=0)))

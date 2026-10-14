"""Summarize executed counterfactuals without transferring AC/optimality proof."""
from pathlib import Path
import json,gzip,csv,collections,hashlib,math
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'audit/control/FINAL_FLEX_COMPARISON'
def read(p):return json.loads(Path(p).read_text(encoding='utf8'))
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
def result(p):
    with gzip.open(p,'rt',encoding='utf8') as stream:return json.load(stream)


def day_wait_audit(ledger,started_UIDs,receipt):
    begin=receipt.get('begin_seconds');end=receipt.get('end_seconds')
    audit=dict(scope='PUBLIC_QUEUE_LEDGER_DDAY_ONLY_WAIT_EXCLUDING_INITIAL_RUNNING',
        formula='max(0,min(actualStart_or_dayEnd,dayEnd)-max(dayBegin,observedSubmit))',
        time_axis_authority=receipt.get('reporting_day_axis_authority','EXPLICIT_EXECUTION_RECEIPT_BEGIN_END'),
        time_axis_source_fields=receipt.get('reporting_day_axis_source_fields',
            ['EXECUTION_RECEIPT.begin_seconds','EXECUTION_RECEIPT.end_seconds']),
        begin_seconds=begin,end_seconds=end,total_seconds=None,initial_running_excluded=0,
        newly_started_jobs=0,pending_at_day_end_jobs=0,eligible_jobs=0,missing_or_invalid_UIDs=[],
        private_realized_runtime_or_completion_used=False,intentional_delay_equivalent=False)
    if begin is None or end is None or not math.isfinite(begin) or not math.isfinite(end) or end<=begin:
        audit['status']='NOT_ESTABLISHED_PUBLIC_DAY_AXIS_MISSING';return audit
    total=0.;excluded=[]
    for row in ledger:
        uid=row['job_uid'];submit=row.get('submit_time');start=row.get('admitted_time')
        if submit is None or not math.isfinite(submit) or submit>end:
            audit['missing_or_invalid_UIDs'].append(uid);continue
        if start is not None and (not math.isfinite(start) or start>end):
            audit['missing_or_invalid_UIDs'].append(uid);continue
        if start is not None and uid not in started_UIDs:
            if start<=begin:
                excluded.append(uid);continue
            audit['missing_or_invalid_UIDs'].append(uid);continue
        total+=max(0.,min(end if start is None else start,end)-max(begin,submit))
        audit['eligible_jobs']+=1
        audit['newly_started_jobs' if start is not None else 'pending_at_day_end_jobs']+=1
    audit['initial_running_excluded']=len(excluded)
    audit['initial_running_excluded_UIDs_sha256']=hashlib.sha256(
        json.dumps(sorted(excluded),separators=(',',':')).encode('utf8')).hexdigest()
    audit['status']='PASS_PUBLIC_TIMESTAMPS_COMPLETE' if not audit['missing_or_invalid_UIDs'] else 'NOT_ESTABLISHED_PUBLIC_TIMESTAMPS_INCOMPLETE'
    if not audit['missing_or_invalid_UIDs']:audit['total_seconds']=total
    return audit
def summarize(d,receipt):
    events=d['job_event_ledger'];audit=d.get('experimental_candidate_audit',[]);qos=d['qos_ledger']
    actions=collections.Counter(x.get('action','') for x in events if x['event']=='RUNNING')
    scores=[row['score'] for e in audit for row in e.get('q50_scores',[]) if row.get('hard')]
    risk=[e['selected_Q90_risk'] for e in audit if e.get('selected_Q90_risk')]
    selected_peaks=[e['selected_Q50_peak'] for e in audit if e.get('selected_Q50_peak') is not None]
    generated_actions=collections.Counter()
    for event in audit:generated_actions.update(event.get('generated_action_counts',{}))
    rules=d['rule_consumption_receipt'];budgets=d['qos_budget_ledger'];ledger=d['queue_ledger']
    active_UIDs={r['job_uid'] for r in ledger}
    # Action labels and delay burden differ: a site change is PREPLACE even
    # when its authorized start is delayed. Count physical starts by UID.
    starts=[x for x in events if x['event']=='RUNNING']
    started_UIDs={x['uid'] for x in starts}
    rows_by_UID={r['job_uid']:r for r in ledger}
    executed_positive_delay={uid for uid in started_UIDs
        if rows_by_UID[uid].get('intentional_delay_seconds',0)>0}
    delayed_preplace_UIDs={x['uid'] for x in starts if x.get('action')=='PREPLACE'
        and rows_by_UID[x['uid']].get('intentional_delay_seconds',0)>0}
    pending_risk=d.get('experimental_pending_contract_risk',[])
    physical_never_started_UIDs={r['job_uid'] for r in ledger if r.get('admitted_time') is None}
    pending_risk_UIDs={r['uid'] for r in pending_risk}
    experimental_reference_state=d.get('carryout',{}).get('controller',{}).get('experimental_runtime_state')
    no_physical_R0_UIDs=(physical_never_started_UIDs-set(experimental_reference_state['references'])
        if experimental_reference_state is not None else None)
    last_public_lookup={r['uid']:r for r in audit}
    last_control_seconds=(receipt['begin_seconds']+(receipt['slots']-1)*900
        if receipt.get('begin_seconds') is not None and receipt.get('slots') else None)
    reference_audit=d.get('experimental_reference_audit',[])
    reference_advances=[r for r in reference_audit if r['event']=='OBSERVED_PHYSICAL_REFERENCE_ADVANCE']
    final_public_reference={r['uid']:r for r in reference_audit if r['event']=='CAUSAL_REFERENCE_FROZEN'}
    physical_start_reference_delta={x['uid']:max(0.,x['time_seconds']-
        final_public_reference[x['uid']]['reference_start_seconds']) for x in starts
        if x['uid'] in final_public_reference}
    physical_delayed_preplace={x['uid'] for x in starts if x.get('action')=='PREPLACE'
        and physical_start_reference_delta.get(x['uid'],0)>1e-7}
    day_wait=day_wait_audit(ledger,started_UIDs,receipt)
    deadline_audit=dict(scope='PUBLIC_PENDING_RESEARCH_WINDOW_AND_REFERENCE_PROOF_AUDIT_NOT_OBSERVED_WHOLE_SLA',
        pending_reference_records=len(pending_risk),
        pending_positive_contract_overdue_jobs=sum(r.get('assumed_budget_seconds',0)>0 and r.get('contract_overdue_at_end',False)
            for r in pending_risk),
        pending_all_contract_overdue_jobs=sum(r.get('contract_overdue_at_end',False) for r in pending_risk),
        reference_advance_occurrences=len(reference_advances),
        reference_advance_unique_UIDs=len({r['uid'] for r in reference_advances}),
        observed_physical_resource_wait_seconds=sum(r.get('physical_resource_wait_seconds',0) for r in pending_risk),
        grid_required_wait_seconds=sum(r.get('grid_required_wait_seconds',0) for r in pending_risk),
        positive_executed_or_committed_intentional_budget_violation_jobs=sum(
            r['total_intentional_burden_seconds']>r['budget_seconds']+1e-7 for r in qos),
        legacy_issue_window_latest_start_excess_jobs=sum(r['latest_start_excess_seconds']>1e-7 for r in qos),
        pending_records=pending_risk,
        observed_source_or_research_whole_SLA_certificate=False,
        queue_wait_scope='SOURCE_SUBMIT_TO_START_OR_HORIZON_CONVENTION_INCLUDING_HISTORICAL_WAIT;NOT_INTENTIONAL_DELAY',
        legacy_window_excess_is_research_budget_violation=False,
        pending_overdue_is_normal_completion=False)
    ret=dict(scenario=receipt['scenario'],participation=receipt.get('participation'),algorithm=receipt.get('algorithm'),
        effective_algorithm=receipt.get('effective_algorithm'),case_sha=receipt.get('case_sha',receipt.get('source_case_sha')),
        source_sha=receipt.get('source_freeze_sha'),execution_scope='FIXED_ANCHOR_CAUSAL_FULL96_EVENT_REPLAY',
        unique_active_jobs=d['receipt']['submitted_jobs'],positive_contract_jobs=sum(x.get('budget_seconds',0)>0 for uid,x in budgets.items() if uid in active_UIDs),
        issued_positive_contract_receipts=sum(x.get('budget_seconds',0)>0 for x in budgets.values()),
        generated_candidates=sum(e['generated'] for e in audit),physical_and_grid_evaluated=sum(e['physically_and_grid_evaluated'] for e in audit),
        generated_START_NOW=generated_actions['START_NOW'],generated_DELAY=generated_actions['DELAY'],
        generated_PREPLACE=generated_actions['PREPLACE'],generated_MIGRATE=generated_actions['CHECKPOINT_MIGRATE'],
        generated_STAY=generated_actions['STAY'],
        approved_candidate_occurrences=sum(e['approved'] for e in audit),q50_hard_pass=sum(e['q50_hard_pass'] for e in audit),
        policy_lookup_events=len(audit),policy_lookup_UIDs=len({e['uid'] for e in audit}),
        policy_lookup_success_events=sum(e.get('selected_candidate') is not None for e in audit),
        selected_action_occurrences=dict(collections.Counter(e['selected_action'] for e in audit)),
        executed_START_NOW=actions['START'],executed_DELAY=actions['DELAY'],executed_PREPLACE=actions['PREPLACE'],
        executed_MIGRATE=len(d['migration_receipts']),executed_running_starts=sum(actions.values()),
        executed_jobs_with_positive_intentional_delay=len(executed_positive_delay),
        delayed_PREPLACE_jobs=len(delayed_preplace_UIDs),
        executed_start_intentional_delay_seconds=sum(rows_by_UID[uid].get('intentional_delay_seconds',0) for uid in started_UIDs),
        charged_intentional_delay_on_started_jobs_seconds=sum(rows_by_UID[uid].get('intentional_delay_seconds',0) for uid in started_UIDs),
        committed_intentional_delay_obligation_seconds=sum(x['intentional_start_delay_seconds'] for x in qos),
        delay_taxonomy_scope='PREPLACE_TAKES_LABEL_PRIORITY_WHEN_SITE_AND_START_BOTH_CHANGE;COMMITTED_AND_EXECUTED_DELAY_SEPARATE',
        executed_delay_scope='CUMULATIVE_CHARGED_INTENTIONAL_BURDEN_OF_JOBS_THAT_PHYSICALLY_STARTED;INCLUDES_PRIOR_CANCELLED_OR_REBASED_COMMAND_BURDEN;NOT_ALL_WALL_WAIT',
        physical_starts_with_public_final_causal_reference=len(physical_start_reference_delta),
        physical_start_after_final_causal_reference_jobs=sum(v>1e-7 for v in physical_start_reference_delta.values()),
        physical_delayed_PREPLACE_jobs=len(physical_delayed_preplace),
        physical_start_minus_final_causal_reference_seconds=sum(physical_start_reference_delta.values()),
        physical_start_delta_scope='PUBLIC_RUNNING_EVENT_TIME_MINUS_FINAL_FROZEN_CAUSAL_REFERENCE_START;SEPARATE_FROM_PERSISTENT_CHARGED_OBLIGATION;NOT_OBSERVED_CUSTOMER_SLA',
        physical_start_delta_count_tolerance_seconds=1e-7,
        completed_jobs=d['receipt']['completed_jobs'],carryout_jobs=d['receipt']['carryout_jobs'],
        actual_compute_GPUh=d['receipt']['actual_compute_GPUh'],actual_occupation_GPUh=d['receipt']['actual_occupation_GPUh'],
        queue_wait_seconds=sum(x.get('actual_wait_seconds',0) for x in qos),
        historical_issue_and_day_queue_wait_seconds=sum(x.get('actual_wait_seconds',0) for x in qos),
        DDay_queue_wait_seconds=day_wait['total_seconds'],DDay_queue_wait_audit=day_wait,
        intentional_delay_seconds=sum(x['intentional_start_delay_seconds'] for x in qos),
        migration_interruption_seconds=sum(x['migration_interruption_seconds'] for x in qos),
        intentional_budget_violation_jobs=sum(x['total_intentional_burden_seconds']>x['budget_seconds']+1e-7 for x in qos),
        legacy_window_latest_start_excess_jobs=sum(x['latest_start_excess_seconds']>1e-7 for x in qos),
        research_deadline_audit=deadline_audit,
        capacity_violations=d['receipt']['capacity_violations'],dropped_jobs=d['receipt']['dropped_jobs'],
        private_future_controller_reads=d['receipt']['future_duration_controller_reads']+d['receipt']['future_completion_controller_reads'],
        CC4_depletion_events=len(d['cc4_depletion_ledger']),CC4_depletion_unique_UIDs=len({x['uid'] for x in d['cc4_depletion_ledger']}),
        CC4_once_depletion_PASS=all(x['depletion_count']==1 for x in d['cc4_depletion_ledger']),
        predicted_Q50_evaluated_candidate_max_line_loading=max(scores) if scores else None,
        predicted_Q50_selected_profile_max_line_loading=max(selected_peaks) if selected_peaks else None,
        selected_Q90_carryout_max_GPUh=max((r['carryout_GPUh'] for r in risk),default=None),
        selected_Q90_queue_area_max_GPUh_hours=max((r['queue_GPUh_hours'] for r in risk),default=None),
        selected_Q90_predicted_line_max=max((r['peak_score'] for r in risk),default=None),
        selected_Q90_physical_hard_PASS=all(r['hard_feasible'] for r in risk) if risk else None,
        pending_research_contract_risk_count=len(d.get('experimental_pending_contract_risk',[])),
        physical_never_started_jobs=len(physical_never_started_UIDs),
        pending_first_reference_risk_unique_jobs=len(pending_risk_UIDs) if experimental_reference_state is not None else None,
        pending_not_in_first_reference_risk_jobs=len(physical_never_started_UIDs-pending_risk_UIDs)
            if experimental_reference_state is not None else None,
        pending_without_experimental_physical_R0_jobs=sum(uid not in experimental_reference_state['references']
            for uid in physical_never_started_UIDs) if experimental_reference_state is not None else None,
        pending_no_R0_last_NO_PHYSICAL_CAUSAL_REFERENCE_jobs=sum(last_public_lookup.get(uid,{}).get('terminal_status')=='NO_PHYSICAL_CAUSAL_REFERENCE'
            for uid in no_physical_R0_UIDs) if no_physical_R0_UIDs is not None else None,
        pending_no_R0_after_last_control_submit_lookup0_jobs=sum(rows_by_UID[uid]['submit_time']>last_control_seconds
            and uid not in last_public_lookup for uid in no_physical_R0_UIDs)
            if no_physical_R0_UIDs is not None and last_control_seconds is not None else None,
        pending_positive_budget_without_physical_R0_jobs=sum(budgets[uid]['budget_seconds']>0 for uid in no_physical_R0_UIDs)
            if no_physical_R0_UIDs is not None else None,
        pending_no_R0_deadline_assessment='NOT_ESTABLISHED_NO_FIRST_PHYSICAL_REFERENCE' if no_physical_R0_UIDs else
            'NONE_MISSING' if no_physical_R0_UIDs is not None else 'NOT_APPLICABLE_STRICT_E0',
        pending_risk_count_scope='FIRST_PHYSICAL_REFERENCE_SUBSET_OF_ALL_NEVER_STARTED;ABSENT_R0_DOES_NOT_ESTABLISH_DEADLINE_ASSESSMENT',
        pending_assumed_contract_overdue_jobs=sum(r.get('assumed_budget_seconds',0)>0 and r.get('contract_overdue_at_end',False)
            for r in d.get('experimental_pending_contract_risk',[])),
        first_reference_audit_records=len(d.get('experimental_reference_audit',[])),
        predicted_line_scope='AFFINE_FROZEN_Q50_CANDIDATE_PROFILES_NOT_ACTUAL_AC',
        Actual_Maximum_Line_Loading=None,Fresh_AC='NOT_RUN',
        electrical_violations_Actual=None,rack_WAN_validation='ORIGINAL_RESERVATION_AND_EXECUTION_GUARDS',
        WAN_payload_bytes=sum(x.get('payload_bytes',x.get('migration_capability_packet',{}).get('payload_bytes',0)) for x in d['migration_receipts']),
        WAN_saveIO_energy_joules=None,WAN_energy_scope='UNMODELED_NOT_ZERO',
        engine_wall_seconds=receipt['wall_seconds'],writer_inclusive_wall_seconds=receipt.get('writer_inclusive_wall_seconds'),
        frozen_program_compile_wall_seconds=receipt.get('frozen_program_compile_wall_seconds'),
        compiler_timing_scope='FROZEN_PROGRAM_BUILD_INCLUDES_LAZY_ORIGINAL_INPUT_PREPARATION_ON_FIRST_CASE_PER_PROCESS;NOT_SOLVER_OPTIMIZATION',
        engine_timing_scope='COMMON_ACTUAL_EVENT_ENGINE_WALL;EXCLUDES_PROGRAM_SETUP_AND_RESULT_SERIALIZATION',
        writer_inclusive_timing_scope='PROGRAM_BUILD_PLUS_CASE_PREPARATION_PLUS_ENGINE_PLUS_POST_EXECUTION_SERVICE_AUDIT_AND_ARTIFACT_WRITING',
        policy_metrics=d.get('experimental_policy_metrics'),retrospective_service_audit=receipt.get('retrospective_service_audit'),
        Native_Optimize_calls=0,new_A_M_optimum=False)
    return ret
DETAIL_FIELDS=('scenario','participation','algorithm','case_sha','uid','time_seconds','state',
    'generated','physical_and_grid_evaluated','q50_hard_pass','approved','selected_action',
    'selected_candidate','terminal_status')
FUNNEL_SUM_FIELDS=('generated','physical_and_grid_evaluated','q50_hard_pass','approved')


def funnel_detail(case,event):
    return dict(scenario=case['scenario'],participation=case['participation'],algorithm=case['algorithm'],
        case_sha=case['case_sha'],uid=event['uid'],time_seconds=event['time_seconds'],state=event['state'],
        generated=event['generated'],physical_and_grid_evaluated=event['physically_and_grid_evaluated'],
        q50_hard_pass=event['q50_hard_pass'],approved=event['approved'],selected_action=event['selected_action'],
        selected_candidate=event.get('selected_candidate'),terminal_status=event.get('terminal_status'))


def funnel_stats():
    return dict(events=0,**{k:0 for k in FUNNEL_SUM_FIELDS},selected=0,
        UID_all=set(),UID_generated=set(),UID_evaluated=set(),UID_approved=set(),UID_selected=set())


def consume_funnel(stats,event):
    stats['events']+=1;uid=str(event['uid']);stats['UID_all'].add(uid)
    for k in FUNNEL_SUM_FIELDS:stats[k]+=int(event[k])
    if int(event['generated']):stats['UID_generated'].add(uid)
    if int(event['physical_and_grid_evaluated']):stats['UID_evaluated'].add(uid)
    if int(event['approved']):stats['UID_approved'].add(uid)
    if event.get('selected_candidate'):
        stats['selected']+=1;stats['UID_selected'].add(uid)


def serial_funnel(stats):
    return {k:len(v) if isinstance(v,set) else v for k,v in stats.items()}


def main():
    manifest=read(OUT/'CASE_MANIFEST.json');rows=[];funnel=[];expected={};detail_events=0
    names=['_'.join(case[k] for k in ('scenario','participation','algorithm')) for case in manifest['cases']]
    missing=[name for name in names if not (OUT/name/'EXECUTION_RECEIPT.json').is_file()]
    if missing:raise ValueError('PENDING_FINAL_EXECUTION_RECEIPTS:'+','.join(missing))
    detail_path=ROOT/'audit/CONTROL_POLICY_CANDIDATE_FUNNEL_EVENT_DETAIL.csv'
    # Stream one finished case at a time. Keep the original complete event ledger;
    # the required small CSV contains its separately verified case aggregates.
    with detail_path.open('w',encoding='utf8',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=DETAIL_FIELDS);writer.writeheader()
        for case,name in zip(manifest['cases'],names):
            folder=OUT/name;receipt=read(folder/'EXECUTION_RECEIPT.json')
            d=result(folder/'CONDITIONAL_ACTUAL_RESULT.json.gz');row=summarize(d,receipt);rows.append(row)
            stats=funnel_stats();canonical=hashlib.sha256()
            for event in d.get('experimental_candidate_audit',[]):
                record=funnel_detail(case,event);writer.writerow(record);consume_funnel(stats,record)
                canonical.update((json.dumps(record,sort_keys=True,separators=(',',':'),ensure_ascii=False)+'\n').encode('utf8'))
            expected[name]=serial_funnel(stats);detail_events+=stats['events']
            aggregate=dict(scenario=case['scenario'],participation=case['participation'],algorithm=case['algorithm'],
                case_sha=case['case_sha'],source_sha=manifest['source_sha'],detail_row_count=stats['events'],
                unique_active_jobs=row['unique_active_jobs'],policy_lookup_unique_UIDs=len(stats['UID_all']),
                jobs_with_generated_candidates=len(stats['UID_generated']),jobs_with_evaluated_candidates=len(stats['UID_evaluated']),
                jobs_with_approved_candidates=len(stats['UID_approved']),jobs_with_selected_candidates=len(stats['UID_selected']),
                generated_candidate_occurrences=stats['generated'],evaluated_candidate_occurrences=stats['physical_and_grid_evaluated'],
                q50_hard_pass_candidate_occurrences=stats['q50_hard_pass'],approved_candidate_occurrences=stats['approved'],
                selected_candidate_occurrences=stats['selected'],executed_START_NOW=row['executed_START_NOW'],
                executed_DELAY=row['executed_DELAY'],executed_PREPLACE=row['executed_PREPLACE'],executed_MIGRATE=row['executed_MIGRATE'],
                physical_running_starts=row['executed_running_starts'],source_result_sha256=receipt['result_sha256'],
                detail_case_canonical_rows_sha256=canonical.hexdigest(),
                scope='CASE_AGGREGATE_OF_COMPLETE_UID_TIME_DETAIL;CANDIDATE_OCCURRENCES_ARE_NOT_UNIQUE_UIDS_OR_EXECUTED_ACTIONS')
            for action in ('START_NOW','DELAY','PREPLACE','MIGRATE','STAY'):
                aggregate['generated_'+action]=row['generated_'+action]
            for action in ('START','DELAY','PREPLACE','CHECKPOINT_MIGRATE','STAY','QUEUE'):
                aggregate['selected_'+action+'_occurrences']=row['selected_action_occurrences'].get(action,0)
            funnel.append(aggregate);del d
    baseline=ROOT/'audit/control/FINAL_E0_STRICT_BASELINE_FULL96';d=result(baseline/'CONDITIONAL_ACTUAL_RESULT.json.gz')
    receipt=read(baseline/'E0_EXECUTION_RECEIPT.json');receipt['retrospective_service_audit']=read(baseline/'RETROSPECTIVE_SERVICE_MASS.json')
    if receipt.get('begin_seconds') is None or receipt.get('end_seconds') is None:
        controller=d['carryout']['controller']
        observed_day_axes={m['dday_initialization_seconds'] for m in controller['metadata'].values()
            if m.get('dday_initialization_seconds') is not None}
        all_axis_metadata_present=bool(controller['metadata']) and all(
            m.get('dday_initialization_seconds') is not None for m in controller['metadata'].values())
        final_clock=controller.get('at_seconds')
        if all_axis_metadata_present and len(observed_day_axes)==1 and final_clock is not None:
            observed_begin=next(iter(observed_day_axes))
            if (receipt['Full96'] is True and len(d['occupancy_GPU'])==receipt['slots']==96
                    and final_clock-observed_begin==96*900):
                # Reporting-only provenance from the preserved public result.
                # Do not modify or backfill the historical execution receipt.
                receipt.update(begin_seconds=observed_begin,end_seconds=final_clock,
                    reporting_day_axis_authority='PUBLIC_CONTROLLER_UNIQUE_DDAY_INITIALIZATION_SECONDS_AND_FINAL_CLOCK;FULL96_900S_SPAN_VERIFIED',
                    reporting_day_axis_source_fields=['CONDITIONAL_ACTUAL_RESULT.carryout.controller.metadata[*].dday_initialization_seconds',
                        'CONDITIONAL_ACTUAL_RESULT.carryout.controller.at_seconds','CONDITIONAL_ACTUAL_RESULT.occupancy_GPU[96 rows]',
                        'E0_EXECUTION_RECEIPT.Full96','E0_EXECUTION_RECEIPT.slots'])
    strict=summarize(d,receipt)
    for flex in ('FLEX20','FLEX30','FLEX40'):
        for algorithm in ('FIXED','GREEDY','GRID_SENSITIVITY_AWARE'):
            rows.append(dict(strict,participation=flex,algorithm=algorithm,physical_execution_alias='FINAL_E0_STRICT_BASELINE_FULL96'))
    write(OUT/'COMPARISON_DETAIL.json',dict(science_version=manifest['science_version'],source_sha=manifest['source_sha'],
        cells=rows,E0_physical_executions=1,E1_E2_physical_executions=18,actual_electrical_performance_certificate=False,
        all_capacity_PASS=all(r['capacity_violations']==0 for r in rows),all_private_reads_zero=all(r['private_future_controller_reads']==0 for r in rows),
        all_service_mass_PASS=all(r['retrospective_service_audit']['PASS'] for r in rows)))
    fields=[k for k,v in rows[0].items() if not isinstance(v,(dict,list))]
    with (ROOT/'audit/POLICY_E0_E1_E2_COMPARISON.csv').open('w',encoding='utf8',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields,extrasaction='ignore');writer.writeheader();writer.writerows(rows)
    aggregate_path=ROOT/'audit/CONTROL_POLICY_CANDIDATE_FUNNEL.csv'
    with aggregate_path.open('w',encoding='utf8',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(funnel[0]));writer.writeheader();writer.writerows(funnel)
    reconstructed={name:funnel_stats() for name in names}
    with detail_path.open('r',encoding='utf8',newline='') as stream:
        for event in csv.DictReader(stream):
            name='_'.join(event[k] for k in ('scenario','participation','algorithm'))
            consume_funnel(reconstructed[name],event)
    checks={name:serial_funnel(reconstructed[name])==expected[name] for name in names}
    assert all(checks.values()),'FUNNEL_DETAIL_AGGREGATE_RECONCILIATION_FAILED'
    write(ROOT/'audit/CONTROL_POLICY_CANDIDATE_FUNNEL_RECONCILIATION.json',dict(
        source_sha=manifest['source_sha'],independent_executed_cases=len(funnel),aggregate_rows=len(funnel),
        detailed_event_rows=detail_events,detail_preserved=True,original_execution_results_modified=False,
        original_full_UID_time_detail_file=str(detail_path),
        original_full_UID_time_detail_sha256=hashlib.sha256(detail_path.read_bytes()).hexdigest(),
        aggregate_file=str(aggregate_path),aggregate_sha256=hashlib.sha256(aggregate_path.read_bytes()).hexdigest(),
        complete_detail_reparse_matches_each_case_aggregate=checks,PASS=all(checks.values()),
        per_case_expected=expected,detail_package_compression='GZIP_LOSSLESS_WITH_DECOMPRESSED_SHA_VERIFICATION',
        E0_scope='SEPARATE_ORIGINAL_EXECUTION_EVIDENCE;NINE_COMPARISON_ALIASES_NOT_NEW_FUNNEL_EXECUTIONS',
        case_result_sha_and_canonical_detail_rows_sha=dict((names[i],dict(
            source_result_sha256=funnel[i]['source_result_sha256'],
            detail_case_canonical_rows_sha256=funnel[i]['detail_case_canonical_rows_sha256'])) for i in range(len(funnel)))))
    write(ROOT/'audit/POLICY_GRID_GREEDY_FIXED_ABLATION.json',dict(source_sha=manifest['source_sha'],cells=rows,
        Actual_AC_performance_improvement=None,meaning='SAME_INPUTS_NEW_CONTRACT_CASES_DIFFERENT_FROZEN_BOUNDED_SELECTORS',
        E0_cells_are_explicit_aliases=True,E1_E2_independent_executions=18))
    print(json.dumps(dict(comparison_cells=len(rows),funnel_case_aggregates=len(funnel),funnel_events=detail_events,completed=True)))
if __name__=='__main__':main()

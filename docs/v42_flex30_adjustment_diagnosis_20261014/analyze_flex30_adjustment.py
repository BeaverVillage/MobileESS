"""Read-only UID decomposition of the frozen E1/FLEX30/GRID Full96 receipt.

This is retrospective evidence analysis. It performs no replay, selector call,
optimization, AC, or future-state feedback into a controller.
"""
from pathlib import Path
import bisect,collections,csv,gzip,hashlib,heapq,json
import numpy as np

ROOT=next(p for p in Path(__file__).resolve().parents if (p/'v42_integration').is_dir())
CASE=ROOT/'audit/control/FINAL_FLEX_COMPARISON/E1_FLEX30_GRID_SENSITIVITY_AWARE'
OUT=ROOT/'docs/v42_flex30_adjustment_diagnosis_20261014'
FLEX_ACTIONS={'PREPLACE','CHECKPOINT_MIGRATE'}

def flex_action(label):
    return label in FLEX_ACTIONS or label.startswith('DELAY')

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return h.hexdigest()

def csv_write(path,rows):
    with path.open('w',encoding='utf8',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    receipt=json.loads((CASE/'EXECUTION_RECEIPT.json').read_text(encoding='utf8'))
    path=CASE/'CONDITIONAL_ACTUAL_RESULT.json.gz'
    assert sha(path)==receipt['result_sha256']
    with gzip.open(path,'rt',encoding='utf8') as stream:data=json.load(stream)
    budgets=data['qos_budget_ledger'];queue={r['job_uid']:r for r in data['queue_ledger']}
    state=data['carryout']['controller'];metadata=state['metadata']
    participants={u for u in queue if budgets[u]['budget_seconds']>0}
    assert len(participants)==674
    stats={u:dict(lookup_events=0,pending_lookup_events=0,running_lookup_events=0,
        generated_flex=0,evaluated_flex=0,hard_approved_flex=0,
        selected_flex_events=0,reference_with_feasible_flex_events=0,
        reference_with_Q50_tied_flex_events=0,reference_with_worse_flex_events=0,
        strictly_better_flex_not_selected_events=0,
        candidate_truncated=0,rejections=collections.Counter(),
        flex_rejections=collections.Counter(),q50_hard_reasons=collections.Counter(),
        flex_generated_actions=collections.Counter(),flex_approved_actions=collections.Counter(),
        terminal_reasons=collections.Counter(),revalidation_failed=collections.Counter(),
        revalidation_passed=0) for u in queue}
    event_reason_actions=collections.Counter();reason_UIDs=collections.defaultdict(set)
    rank_examples=[];candidate_totals=collections.Counter()
    for index,event in enumerate(data['experimental_candidate_audit']):
        u=event['uid']
        if u not in stats:continue
        row=stats[u];row['lookup_events']+=1
        row['pending_lookup_events' if event['state']=='PENDING' else 'running_lookup_events']+=1
        row['candidate_truncated']+=event['candidates_truncated']
        # For this GRID case, every Q50 Hard row also passed recourse approval.
        assert event['q50_hard_pass']==event['approved']
        for action,count in event.get('generated_action_counts',{}).items():
            if flex_action(action):
                row['generated_flex']+=count;row['flex_generated_actions'][action]+=count
        feasible_flex=[]
        for candidate in event['q50_scores']:
            if not flex_action(candidate['action']):continue
            row['evaluated_flex']+=1
            if candidate['hard']:
                row['hard_approved_flex']+=1
                row['flex_approved_actions'][candidate['action'].split('_')[0]]+=1
                feasible_flex.append(candidate)
            else:row['q50_hard_reasons'].update(candidate.get('violation_reason_counts',{}))
        for rejection in event['rejected']:
            reason=rejection['reason'];action=rejection.get('action','UNRECORDED')
            row['rejections'][reason]+=1
            if flex_action(action):row['flex_rejections'][reason]+=1
            if u in participants:
                event_reason_actions[(reason,action)]+=1;reason_UIDs[(reason,action)].add(u)
                if event['generated']==0:row['terminal_reasons'][reason]+=1
        if flex_action(event['selected_action']):row['selected_flex_events']+=1
        elif feasible_flex and event.get('selected_candidate') is not None:
            row['reference_with_feasible_flex_events']+=1
            margin=min(r['score'] for r in feasible_flex)-event['selected_Q50_peak']
            if margin < -1.00001e-9:row['strictly_better_flex_not_selected_events']+=1
            elif margin<=1e-9:row['reference_with_Q50_tied_flex_events']+=1
            else:row['reference_with_worse_flex_events']+=1
            if u in participants and len(rank_examples)<20:
                rank_examples.append(dict(uid=u,audit_index=index,time_seconds=event['time_seconds'],
                    selected_action=event['selected_action'],selected_Q50_peak=event['selected_Q50_peak'],
                    best_flex_Q50_peak=min(r['score'] for r in feasible_flex),best_flex_minus_selected_Q50=margin,
                    Q90_all_alternative_values_saved=False))
        if u in participants:
            candidate_totals.update(generated=event['generated'],evaluated=event['physically_and_grid_evaluated'],
                q50_hard_pass=event['q50_hard_pass'],approved=event['approved'],
                lookup_events=1,selected_events=int(event.get('selected_candidate') is not None))
    starts={r['uid']:r for r in data['job_event_ledger'] if r['event']=='RUNNING'}
    for event in data['job_event_ledger']:
        if event['event']!='EXPERIMENTAL_COMMAND_REVALIDATED':continue
        row=stats[event['uid']]
        if event['passed']:row['revalidation_passed']+=1
        else:row['revalidation_failed'][event['reason']]+=1
    adjusted={u for u,r in starts.items() if flex_action(r['action'])}
    assert len(adjusted)==62 and len(adjusted&participants)==39
    assert sum(stats[u]['strictly_better_flex_not_selected_events'] for u in participants)==0
    categories=collections.Counter();details=[];reason_by_category=collections.defaultdict(collections.Counter)
    selected_commands=collections.defaultdict(list)
    for r in data['rule_consumption_receipt']:
        if r.get('uid') in participants and flex_action(r.get('action','')):
            selected_commands[r['uid']].append(r)
    # Reconstruct current GPU only from already-public start/completion events.
    # The receipt has no migrations; completion holds last until control release.
    # This separates instantaneous shortage from a nominal future booking clash.
    assert not data['migration_receipts']
    sites=data['sites'];site_index={site:i for i,site in enumerate(sites)}
    caps=json.loads((ROOT/'audit/cc4_service/A2_SERVICE_TIMING_SOURCE_PACKET.json').read_text(encoding='utf8'))['capacities_by_site']
    use={site:0 for site in sites};active=set();release_heap=[]
    begin=receipt['begin_seconds'];end=receipt['end_seconds'];clock=begin
    occupancy=np.zeros((96,len(sites)));revalidation=[];failure_classes=collections.Counter()
    all_commands=collections.defaultdict(list)
    for sequence,r in enumerate(data['rule_consumption_receipt']):
        if r.get('action') in ('START','DELAY','PREPLACE') and 'start_seconds' in r:
            all_commands[r['uid']].append(dict(r,selection_sequence=sequence))
    for r in all_commands.values():r.sort(key=lambda x:(x['time_seconds'],x['selection_sequence']))
    for u,q in queue.items():
        if q['admitted_time'] is not None and u not in starts:
            assert q['admitted_time']<=begin
            use[q['site']]+=q['GPU_gang'];active.add(u)
    def integrate(t):
        nonlocal clock
        assert t>=clock
        left=begin+np.arange(96)*900
        overlap=np.maximum(0.,np.minimum(t,left+900)-np.maximum(clock,left))/900
        for site in sites:occupancy[:,site_index[site]]+=overlap*use[site]
        clock=t
    for event in data['job_event_ledger']:
        t=event['time_seconds'];assert begin<=t<=end
        while release_heap and release_heap[0][0]<=t:
            release,u,site,gpu=heapq.heappop(release_heap);integrate(release)
            assert u in active;active.remove(u);use[site]-=gpu
        integrate(t);u=event['uid']
        if event['event']=='RUNNING':
            assert u not in active;active.add(u);use[event['site']]+=queue[u]['GPU_gang']
        elif event['event']=='COMPLETION_OBSERVED':
            heapq.heappush(release_heap,(event['release_control_seconds'],u,queue[u]['site'],queue[u]['GPU_gang']))
        elif event['event']=='EXPERIMENTAL_COMMAND_REVALIDATED' and u in participants:
            matching=[r for r in all_commands[u] if r['time_seconds']<t
                and r['start_seconds']==event['previous_scheduled_start_seconds']]
            command=matching[-1] if matching else None
            site=None if command is None else command['site'];gpu=queue[u]['GPU_gang']
            free=None if site is None else caps[site]-use[site]
            if event['passed']:failure_class='PASS'
            elif command is None:failure_class='COMMAND_BINDING_NOT_ESTABLISHED'
            elif event['reason']=='NO_CAPACITY':
                failure_class=('CURRENT_WHOLE_GANG_GPU_SHORTAGE' if free<gpu
                    else 'FUTURE_RESERVATION_OR_Q50_PROFILE_CONFLICT')
            elif event['reason']=='CURRENT_FUTURE_ACTUAL_RESERVATION_CAPACITY':
                failure_class='FUTURE_RESERVATION_OR_Q50_PROFILE_CONFLICT'
            elif event['reason'].startswith('CURRENT_OBSERVED_ORIGINAL_GRID_HARD'):
                failure_class='CURRENT_ORIGINAL_AFFINE_GRID_HARD'
            else:failure_class=event['reason']
            failure_classes[failure_class]+=1
            revalidation.append(dict(uid=u,time_seconds=t,passed=event['passed'],reason=event['reason'],
                failure_class=failure_class,command_action=None if command is None else command['action'],
                selected_at_seconds=None if command is None else command['time_seconds'],
                scheduled_start_seconds=event['previous_scheduled_start_seconds'],site=site,
                gpu= gpu,observed_GPU_at_site=None if site is None else use[site],
                observed_GPU_by_site_json=json.dumps(use,sort_keys=True),
                free_GPU_at_site=free,instant_gang_fits=None if free is None else free>=gpu,
                selected_in_advance=None if command is None else command['start_seconds']>command['time_seconds']))
    while release_heap and release_heap[0][0]<=end:
        release,u,site,gpu=heapq.heappop(release_heap);integrate(release)
        active.remove(u);use[site]-=gpu
    integrate(end)
    with np.load(CASE/'ACTUAL_PHYSICAL_ARRAYS.npz') as arrays:
        occupancy_numeric_error=float(np.max(np.abs(occupancy-arrays['occupancy_GPU'])))
        occupancy_byte_equal=bool(np.array_equal(occupancy,arrays['occupancy_GPU']))
        assert occupancy_numeric_error<=1e-9, occupancy_numeric_error
    # Only original frozen signed affine rows are evaluated here. No selector
    # or physical replay is run, and no Environment duration is consulted.
    import sys
    sys.path.insert(0,str(ROOT))
    from v42_integration.experimental_replay import load_conditional_source
    source=load_conditional_source();packet=source['packet']
    frozen_grid_base=packet.known_gpu+source['frozen_anonymous_gpu']
    program=json.loads((CASE/'FROZEN_CONDITIONAL_POLICY_PROGRAM.json').read_text(encoding='utf8'))
    assert packet.authority==program['source_grid_authority']
    assert tuple(packet.sites)==tuple(sites)
    for record in revalidation:
        t=record['time_seconds'];slot=int((t-begin)//900)
        before=json.loads(record['observed_GPU_by_site_json'])
        observed=np.array([before[site] for site in sites],float)
        if 0<=slot<96:
            baseline=frozen_grid_base[slot]
            _,before_violations=packet._at_slot(slot,observed-baseline)
            after=observed.copy()
            if record['site'] is not None:after[site_index[record['site']]]+=record['gpu']
            _,after_violations=packet._at_slot(slot,after-baseline)
            record.update(before_current_affine_reasons=json.dumps(dict(collections.Counter(r['reason'] for r in before_violations)),sort_keys=True),
                after_current_affine_reasons=json.dumps(dict(collections.Counter(r['reason'] for r in after_violations)),sort_keys=True),
                current_GPU_and_after_affine_feasible=record['instant_gang_fits'] is True and not after_violations,
                preexisting_current_affine_violation=bool(before_violations))
        else:record.update(before_current_affine_reasons='OUTSIDE_DAY',after_current_affine_reasons='OUTSIDE_DAY',
                current_GPU_and_after_affine_feasible=None,preexisting_current_affine_violation=None)
    reference_events=collections.defaultdict(list)
    for r in data['experimental_reference_audit']:
        if r['event']=='CAUSAL_REFERENCE_FROZEN':reference_events[r['uid']].append(r)
    def latest_reference(u,when):
        rows=[r for r in reference_events[u] if r['proof']['observed_at_seconds']<=when]
        return rows[-1] if rows else None
    adjusted_details=[]
    for u in sorted(participants):
        row=stats[u];run=starts.get(u);q=queue[u]
        if u in adjusted:category='EXECUTED_FLEX_ACTION'
        elif row['selected_flex_events']:category='FLEX_SELECTED_BUT_NOT_EXECUTED_AS_FLEX'
        elif row['hard_approved_flex']:
            category=('FEASIBLE_FLEX_Q50_TIE_BASELINE_SELECTED' if row['reference_with_Q50_tied_flex_events']
                else 'FEASIBLE_FLEX_WORSE_Q50_BASELINE_SELECTED')
        elif row['generated_flex']:category='FLEX_GENERATED_BUT_NEVER_HARD_APPROVED'
        elif row['lookup_events']:category='LOOKUP_BUT_NO_FLEX_VARIANT_GENERATED'
        else:category='NO_POLICY_LOOKUP'
        categories[category]+=1;reason_by_category[category].update(row['flex_rejections'])
        reasons=dict(row['terminal_reasons']);fail=dict(row['revalidation_failed'])
        ref=latest_reference(u,run['time_seconds']) if run else None
        physical_delta=None if ref is None else max(0.,run['time_seconds']-ref['reference_start_seconds'])
        details.append(dict(uid=u,origin='UNKNOWN' if budgets[u]['origin_unknown'] else 'KNOWN',
            budget_seconds=budgets[u]['budget_seconds'],gpu=q['GPU_gang'],
            nominal_service_GPUh=q['GPU_gang']*budgets[u]['t50_seconds']/3600,
            initially_running=q.get('admitted_time') is not None and u not in starts,
            end_state=q['latest_state'],started_during_day=u in starts,executed_action='' if run is None else run['action'],
            category=category,lookup_events=row['lookup_events'],pending_lookups=row['pending_lookup_events'],
            running_lookups=row['running_lookup_events'],generated_flex=row['generated_flex'],
            evaluated_flex=row['evaluated_flex'],hard_approved_flex=row['hard_approved_flex'],
            selected_flex_events=row['selected_flex_events'],
            baseline_with_feasible_flex_events=row['reference_with_feasible_flex_events'],
            baseline_Q50_tie_events=row['reference_with_Q50_tied_flex_events'],
            baseline_better_Q50_events=row['reference_with_worse_flex_events'],
            candidate_truncated=row['candidate_truncated'],
            future_selected_commands=sum(r['start_seconds']>r['time_seconds'] for r in selected_commands[u] if 'start_seconds' in r),
            command_revalidation_failed=sum(fail.values()),revalidation_fail_reasons=json.dumps(fail,sort_keys=True),
            generated_actions=json.dumps(dict(row['flex_generated_actions']),sort_keys=True),
            approved_actions=json.dumps(dict(row['flex_approved_actions']),sort_keys=True),
            terminal_reasons=json.dumps(reasons,sort_keys=True),
            flex_rejection_reasons=json.dumps(dict(row['flex_rejections']),sort_keys=True),
            q50_hard_violation_reasons=json.dumps(dict(row['q50_hard_reasons']),sort_keys=True),
            final_R0_to_physical_start_seconds=physical_delta,
            committed_intentional_delay_seconds=q.get('intentional_delay_seconds',0)))
    for u in sorted(adjusted):
        q=queue[u];run=starts[u];ref=latest_reference(u,run['time_seconds'])
        adjusted_details.append(dict(uid=u,FLEX30_positive_budget=u in participants,action=run['action'],
            source_model_zero_delay_preplace=metadata[u]['original_raw_request_metadata'].get('can_prestart_place') is True,
            origin='UNKNOWN' if budgets[u]['origin_unknown'] else 'KNOWN',gpu=q['GPU_gang'],
            nominal_GPUh=q['GPU_gang']*budgets[u]['t50_seconds']/3600,
            reference_site='' if ref is None else ref['site'],actual_site=run['site'],
            reference_start_seconds=None if ref is None else ref['reference_start_seconds'],
            actual_start_seconds=run['time_seconds'],
            start_minus_reference_seconds=None if ref is None else max(0,run['time_seconds']-ref['reference_start_seconds'])))
    assert sum(categories.values())==674
    all_stage_UIDs=dict(positive_contract=participants,lookup={u for u in participants if stats[u]['lookup_events']},
        flex_generated={u for u in participants if stats[u]['generated_flex']},
        flex_evaluated={u for u in participants if stats[u]['evaluated_flex']},
        flex_hard_approved={u for u in participants if stats[u]['hard_approved_flex']},
        flex_selected={u for u in participants if stats[u]['selected_flex_events']},executed_flex=participants&adjusted)
    reasons=[dict(reason=reason,action=action,candidate_or_terminal_occurrences=count,
        affected_participating_UIDs=len(reason_UIDs[(reason,action)])) for (reason,action),count in event_reason_actions.most_common()]
    csv_write(OUT/'FLEX30_UID_DECOMPOSITION.csv',details)
    csv_write(OUT/'ALL_62_ADJUSTED_UIDS.csv',adjusted_details)
    csv_write(OUT/'PARTICIPANT_GATE_REASONS.csv',reasons)
    csv_write(OUT/'PARTICIPANT_COMMAND_REVALIDATION.csv',revalidation)
    not_executed={r['uid'] for r in details if r['category']=='FLEX_SELECTED_BUT_NOT_EXECUTED_AS_FLEX'}
    failures_not_executed=[r for r in revalidation if r['uid'] in not_executed and not r['passed']]
    failure_uid_classes={reason:len({r['uid'] for r in failures_not_executed if r['failure_class']==reason})
        for reason in sorted({r['failure_class'] for r in failures_not_executed})}
    never_hard={r['uid'] for r in details if r['category']=='FLEX_GENERATED_BUT_NEVER_HARD_APPROVED'}
    hard_reasons=collections.Counter();hard_reason_UIDs=collections.defaultdict(set)
    for u in never_hard:
        hard_reasons.update(stats[u]['q50_hard_reasons'])
        for reason in stats[u]['q50_hard_reasons']:hard_reason_UIDs[reason].add(u)
    # Bounded mathematical witnesses, not a prevalence estimate: first twenty
    # sorted never-approved UIDs and their first evaluated pending event.
    # A PREPLACE row does not save start time, so try every recorded baseline
    # start offset and require matching score, violation counts AND slot masks.
    # A sign is called definite only when every consistent start agrees.
    from v42_integration.experimental_policy import segments_gpu
    witness_events={}
    for event in data['experimental_candidate_audit']:
        u=event['uid']
        if u not in never_hard or u in witness_events or event['state']!='PENDING' or not event['q50_scores']:continue
        labels=[r.get('action','') for r in event['q50_scores']+event['rejected']]
        baseline_labels={a for a in labels if a=='START_NOW' or a.startswith('DELAY_')}
        if baseline_labels:witness_events[u]=(event,baseline_labels)
    capacity_witnesses=[];witness_mismatches=[]
    for u in sorted(witness_events)[:20]:
        event,labels=witness_events[u];now=event['time_seconds'];slot=int((now-begin)//900)
        ref=latest_reference(u,now)
        possible_starts=[ref['reference_start_seconds']+(0 if label=='START_NOW' else float(label.split('_')[1])*60) for label in sorted(labels)]
        service=max(float(metadata[u]['experimental_prediction_Q50_seconds']),1e-9);gpu=queue[u]['GPU_gang']
        reference=[dict(resource='gpu:'+ref['site'],begin=max(now,ref['reference_start_seconds']),
            end=ref['reference_start_seconds']+service,quantity=gpu)]
        reference=[r for r in reference if r['end']>r['begin']]
        for scored in event['q50_scores']:
            if not flex_action(scored['action']):continue
            matches=[]
            starts_for_row=possible_starts if scored['action']=='PREPLACE' else [ref['reference_start_seconds']+float(scored['action'].split('_')[1])*60]
            for start in starts_for_row:
                future=[dict(resource='gpu:'+scored['site'],begin=max(now,start),end=start+service,quantity=gpu)]
                future=[r for r in future if r['end']>r['begin']]
                delta=segments_gpu(future,sites,begin)-segments_gpu(reference,sites,begin);delta[:slot]=0
                score=packet.evaluate(delta,remaining_slot=slot)
                error=abs(score['peak_score']-scored['score'])
                forecast=frozen_grid_base+delta;low=forecast[slot:]<-1e-8
                high=forecast[slot:]>np.array([caps[s] for s in sites])+1e-8
                violations=list(score['violations'])
                if np.any(low) or np.any(high):violations.append(dict(reason='LITERAL_A2_CANDIDATE_DELTA_PHYSICAL_CAPACITY',slot=slot))
                counts=dict(collections.Counter(v['reason'] for v in violations));slot_masks=collections.defaultdict(set)
                for v in violations:slot_masks[v['reason']].add(v['slot'])
                slot_masks={r:sorted(values) for r,values in slot_masks.items()}
                if error<=1e-12 and counts==scored['violation_reason_counts'] and slot_masks==scored['violation_slots_by_reason']:
                    matches.append(dict(start=start,error=error,negative=int(low.sum()),above=int(high.sum()),
                        minimum=float(forecast[slot:].min()),excess=float((forecast[slot:]-np.array([caps[s] for s in sites])).max())))
            if not matches:witness_mismatches.append(dict(uid=u,action=scored['action'],site=scored['site']));continue
            capacity_witnesses.append(dict(uid=u,time_seconds=now,action=scored['action'],destination=scored['site'],
                starts_consistent_with_saved_score_counts_and_slots=json.dumps([r['start'] for r in matches]),
                reference_start_seconds=ref['reference_start_seconds'],recorded_Q50_score=scored['score'],
                score_error=max(r['error'] for r in matches),consistent_start_count=len(matches),
                negative_profile_definite=all(r['negative']>0 for r in matches),
                above_cap_definite=all(r['above']>0 for r in matches),
                minimum_negative_cells=min(r['negative'] for r in matches),minimum_above_cap_cells=min(r['above'] for r in matches),
                minimum_literal_Q50_GPU=min(r['minimum'] for r in matches),
                maximum_capacity_excess_GPU=max(r['excess'] for r in matches),
                OriginalGridVoltageReject='ORIGINAL_PLANNING_VOLTAGE' in scored['violation_reason_counts'],
                physical_reservation_and_current_guards_already_passed=True))
    assert capacity_witnesses and not witness_mismatches,witness_mismatches
    csv_write(OUT/'Q50_CAPACITY_DIRECTION_WITNESSES.csv',capacity_witnesses)
    report=dict(schema='FLEX30_RETROSPECTIVE_ADJUSTMENT_DIAGNOSIS_V1',
        source_sha=receipt['source_freeze_sha'],case_sha=receipt['case_sha'],policy_sha=receipt['policy_sha'],
        result_sha256=receipt['result_sha256'],population=674,
        all_executed_changed_UIDs=62,participating_changed_UIDs=39,nonparticipating_changed_UIDs=23,
        participating_change_rate=39/674,all_actions=dict(collections.Counter(starts[u]['action'] for u in adjusted)),
        participating_actions=dict(collections.Counter(starts[u]['action'] for u in adjusted&participants)),
        participating_spatial_change_UIDs=sum(r['FLEX30_positive_budget'] and r['reference_site']!=r['actual_site'] for r in adjusted_details),
        participating_temporal_change_UIDs=sum(r['FLEX30_positive_budget'] and r['start_minus_reference_seconds']>0 for r in adjusted_details),
        participating_temporal_start_delta_seconds=sum(r['start_minus_reference_seconds'] for r in adjusted_details if r['FLEX30_positive_budget']),
        nonparticipant_source_preplace_permission_PASS=all(metadata[u]['original_raw_request_metadata'].get('can_prestart_place') is True for u in adjusted-participants),
        unique_UID_stage_funnel={stage:len(uids) for stage,uids in all_stage_UIDs.items()},
        disjoint_674_UID_categories=dict(categories),
        category_flex_gate_reason_occurrences={c:dict(r) for c,r in reason_by_category.items()},
        never_hard_approved_317_Q50_violation_occurrences=dict(hard_reasons),
        never_hard_approved_317_Q50_violation_affected_UIDs_overlapping={k:len(v) for k,v in hard_reason_UIDs.items()},
        nominal_capacity_predicate_limitation='SAVED_REASON_COMBINES_NEGATIVE_A2_PLUS_DELTA_PROFILE_AND_ABOVE_CAPACITY;DIRECTION_VALUES_NOT_SAVED',
        capacity_direction_witness_scope='FIRST20_SORTED_UIDS_FIRST_EVALUATED_EVENT;ALL_POSSIBLE_RECORDED_START_OFFSETS_MATCHED_SCORE_COUNTS_SLOT_MASKS;NOT_PREVALENCE_ESTIMATE',
        capacity_direction_witness_UIDs=len({r['uid'] for r in capacity_witnesses}),
        capacity_direction_witness_rows=len(capacity_witnesses),
        capacity_direction_witness_negative_profile_UIDs=len({r['uid'] for r in capacity_witnesses if r['negative_profile_definite']}),
        capacity_direction_witness_above_cap_UIDs=len({r['uid'] for r in capacity_witnesses if r['above_cap_definite']}),
        capacity_direction_witness_max_score_recompute_error=max(r['score_error'] for r in capacity_witnesses),
        participant_candidate_occurrences=dict(candidate_totals),
        feasible_flex_baseline_selection_events=sum(stats[u]['reference_with_feasible_flex_events'] for u in participants),
        feasible_flex_Q50_tie_baseline_events=sum(stats[u]['reference_with_Q50_tied_flex_events'] for u in participants),
        feasible_flex_worse_Q50_baseline_events=sum(stats[u]['reference_with_worse_flex_events'] for u in participants),
        strictly_better_Q50_flex_ignored_events=0,score_examples=rank_examples,
        participant_candidate_truncation=sum(stats[u]['candidate_truncated'] for u in participants),
        participant_revalidation_failures=dict(sum((stats[u]['revalidation_failed'] for u in participants),collections.Counter())),
        current_GPU_reconstructed_from_public_events_matches_Full96_arrays_PASS=True,
        reconstructed_Full96_occupation_max_numeric_error_GPU=occupancy_numeric_error,
        reconstructed_Full96_occupation_byte_equal=occupancy_byte_equal,
        reconstruction_numeric_tolerance_GPU=1e-9,
        participating_revalidation_failure_classes=dict(failure_classes),
        selected_but_not_executed_205_failure_occurrences=dict(collections.Counter(r['failure_class'] for r in failures_not_executed)),
        selected_but_not_executed_205_affected_UIDs_overlapping=failure_uid_classes,
        selected_but_not_executed_205_actual_outcomes=dict(collections.Counter(
            'PENDING' if u not in starts else starts[u]['action'] for u in not_executed)),
        selected_but_not_executed_205_future_clash_current_GPU_grid_safe_occurrences=sum(
            r['failure_class']=='FUTURE_RESERVATION_OR_Q50_PROFILE_CONFLICT' and r['current_GPU_and_after_affine_feasible'] is True for r in failures_not_executed),
        selected_but_not_executed_205_future_clash_current_GPU_grid_safe_UIDs=len({r['uid']
            for r in failures_not_executed if r['failure_class']=='FUTURE_RESERVATION_OR_Q50_PROFILE_CONFLICT'
                and r['current_GPU_and_after_affine_feasible'] is True}),
        hard_gate_information_limitation='CURRENT_GPU_CAN_BE_EXACTLY_CHECKED;FUTURE_BOOKING_CONFLICT_IS_NOT_PROOF_OF_FUTURE_ACTUAL_IMPOSSIBILITY',
        participant_initial_running=sum(r['initially_running'] for r in details),
        participant_day_started=sum(r['started_during_day'] for r in details),
        participant_never_started=sum(queue[u]['admitted_time'] is None for u in participants),
        participant_no_flex_generated_terminal_reasons=dict(sum((stats[u]['terminal_reasons'] for u in participants if not stats[u]['generated_flex']),collections.Counter())),
        physical_vs_model_scope='GPU/RACK/WAN_BOOKING_HARD_OR_FROZEN_SIGNED_AFFINE_GRID_MODEL;NOT_NEW_ACTUAL_AC_CERTIFICATE',
        unrecorded_information=['Migration guard prefilter rejected-destination reasons before variant append',
            'Future start_seconds for pre-score rejected candidate variants',
            'Nonselected candidates Q90 risk tie-break components'],
        parameter_or_production_edits=0,new_replays=0,Native_Optimize_calls=0,Fresh_AC='NOT_RUN',
        frozen_input_binding_PASS=True,all_674_exclusive_category_reconciliation_PASS=True)
    (OUT/'FLEX30_ADJUSTMENT_DIAGNOSIS.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({k:report[k] for k in ('participating_actions','unique_UID_stage_funnel',
        'disjoint_674_UID_categories','participant_initial_running','participant_day_started','participant_never_started',
        'participant_revalidation_failures','feasible_flex_Q50_tie_baseline_events','feasible_flex_worse_Q50_baseline_events')}))

if __name__=='__main__':main()

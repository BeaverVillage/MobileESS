"""Separate Planning Known changes from observed Unknown execution."""
from collections import Counter,defaultdict


def known_planning_metrics(jobs, selected, *, rho=None, site_gpu=None, site_power_slopes=None):
    changes={k:set() for k in ('TimeShift','Preplace','Migration')}
    moved=0;reference={s:[0.]*96 for s in (site_gpu or {})}
    for uid,option in selected.items():
        job=jobs[uid]
        if option['start']!=job.reference_start:
            changes['TimeShift'].add(uid);moved+=abs(option['start']-job.reference_start)
        if option['initial_site']!=job.reference_site:changes['Preplace'].add(uid)
        if option.get('checkpoint',-1)>=0:changes['Migration'].add(uid)
        if job.reference_site in reference:
            for slot in range(max(24,job.reference_start),min(120,job.reference_start+job.service_slots)):
                reference[job.reference_site][slot-24]+=job.gpu
    changed=set().union(*changes.values());work=lambda u:jobs[u].gpu*jobs[u].service_slots*.25
    delta={s:[float(v)-r for v,r in zip(row,reference[s])] for s,row in (site_gpu or {}).items()}
    return dict(Known_Planning_Eligible_UID=len(jobs),Known_Planning_Changed_UID=len(changed),
        TimeShift_UID=len(changes['TimeShift']),Total_Absolute_Start_Move_Slots=moved,
        Preplace_UID=len(changes['Preplace']),Migration_UID=len(changes['Migration']),
        changed_UIDs=sorted(changed),Changed_Nominal_GPUh=sum(work(u) for u in changed),
        Eligible_Nominal_GPUh=sum(work(u) for u in jobs),
        Known_Planning_Changed_UID_rate=len(changed)/len(jobs) if jobs else None,
        Changed_Nominal_GPUh_rate=sum(work(u) for u in changed)/sum(work(u) for u in jobs) if jobs else None,
        site_slot_GPU_delta=delta,
        site_slot_P_delta_kw=None if site_power_slopes is None else {
            s:[v*float(a) for v,a in zip(row,site_power_slopes[s])] for s,row in delta.items()},
        P_delta_scope='ORIGINAL_FROZEN_C1_AFFINE_WITH_ANONYMOUS_AND_MESS_FIXED',
        Planning_P1_rho=rho,scope='KNOWN_PLANNING_ONLY_NATIVE_24_TO_119')


def unknown_actual_metrics(actual, *, begin=None):
    metadata=actual['carryout']['controller']['metadata']
    unknown={u for u,m in metadata.items() if m['origin_unknown']}
    eligible={u for u in unknown if metadata[u].get('experimental_contract',{}).get('eligible_for_contract',False)}
    participant={u for u in eligible if metadata[u]['experimental_contract']['participant']}
    lookup={r['uid'] for r in actual['rule_consumption_receipt'] if r.get('rule_id') and r['uid'] in unknown}
    shift=set();place=set();migrate=set()
    for row in actual['queue_ledger']:
        uid=row['job_uid']
        if uid not in unknown or row.get('admitted_time') is None:continue
        final_references=actual['carryout']['controller'].get('experimental_runtime_state',{}).get('references',{})
        reference=final_references.get(uid,{}).get('reference_start_seconds',metadata[uid]['reference_start_seconds'])
        if row.get('policy_action') in ('DELAY','PREPLACE') and row['admitted_time']>reference+1e-9:shift.add(uid)
        if row.get('policy_action')=='PREPLACE':place.add(uid)
        if row.get('migration_count',0)>0:migrate.add(uid)
    changed=shift|place|migrate;work=lambda users:sum(metadata[u]['gpu']*metadata[u]['t50_seconds']/3600 for u in sorted(users))
    rule_rows=[r for r in actual['rule_consumption_receipt'] if r.get('uid') in unknown]
    controller=actual['carryout']['controller'];decisions=controller.get('decisions',{})
    executable_actions={'START','START_NOW','DELAY','PREPLACE','CHECKPOINT_MIGRATE'}
    feasible={r['uid'] for r in rule_rows if r.get('action') in executable_actions}
    feasible.update(u for u,d in decisions.items() if u in unknown and d.get('action') in executable_actions)
    reserved={r['uid'] for r in rule_rows if r.get('action') in {'DELAY','PREPLACE','CHECKPOINT_MIGRATE'}}
    admitted={r['job_uid'] for r in actual['queue_ledger'] if r['job_uid'] in unknown and r.get('admitted_time') is not None}
    ranks={u:decisions[u]['frozen_alternative_rank'] for u in admitted if u in decisions and 'frozen_alternative_rank' in decisions[u]}
    failed={r['uid'] for r in actual.get('experimental_candidate_audit',[]) if r['uid'] in reserved
        and any(v.get('event')=='COMMAND_REVALIDATION_FAILED' for v in r.get('rejected',[]))}
    deadline_risk=actual.get('experimental_pending_contract_risk',[])
    physical=actual.get('physical');power=None if physical is None else {
        field:physical[field].tolist() for field in ('IT_kw','PCC_P_kw','PCC_Q_kvar')}
    reasons=Counter();unique=defaultdict(set)
    for row in rule_rows:
        for rejected in row.get('rejected_candidates',[]):
            reason=rejected['reason'];reasons[reason]+=1;unique[reason].add(row['uid'])
    qrows=[r for r in actual['qos_ledger'] if r['uid'] in unknown]
    return dict(Unknown_Observed_UID=len(unknown),Unknown_Observed_Eligible_UID=len(eligible),
        Unknown_Participant_UID=len(participant),Unknown_Lookup_Success_UID=len(lookup),
        Unknown_Feasible_Frozen_Alternative_UID=len(feasible),Unknown_Flexible_Reserved_UID=len(reserved),
        Unknown_First_Alternative_Executed_UID=sum(rank==0 for rank in ranks.values()),
        Unknown_Later_Alternative_Executed_UID=sum(rank>0 for rank in ranks.values()),
        Unknown_Same_Row_Revalidation_Fallback_Executed_UID=sum(
            decisions[u].get('status')=='SELECTED_SAME_FROZEN_ROW_FALLBACK' for u in ranks),
        Frozen_rank_scope='OBSERVED_PENDING_START_COMMANDS_ONLY;LEGACY_SELECTOR_UNRANKED',
        Unknown_Reserved_Command_Revalidation_Failed_UID=len(failed),
        Unknown_Flexible_Reserved_Not_Executed_UID=len(reserved-admitted-migrate),
        Unknown_Actual_TimeShift_UID=len(shift),Unknown_Actual_Preplace_UID=len(place),Unknown_Actual_Migration_UID=len(migrate),
        Unknown_Actual_Changed_UID=len(changed),Changed_Nominal_GPUh=work(changed),Eligible_Nominal_GPUh=work(eligible),
        Unknown_committed_delay_obligation_UID=sum(metadata[u].get('additional_start_delay_seconds',0)>0 for u in unknown),
        Unknown_Actual_Changed_UID_rate=len(changed)/len(eligible) if eligible else None,
        Changed_Nominal_GPUh_rate=work(changed)/work(eligible) if work(eligible) else None,
        Unknown_Queue_UID=sum(u in unknown and r.get('admitted_time') is None for r in actual['queue_ledger'] for u in [r['job_uid']]),
        Unknown_Carryover_UID=sum(r['uid'] in unknown and r['unfinished'] for r in qrows),
        QoS_intentional_budget_excess_UID=sum(r['total_intentional_burden_seconds']>r['budget_seconds']+1e-9 for r in qrows),
        Contract_pending_overdue_UID=sum(r['uid'] in unknown and r['contract_overdue_at_end'] for r in deadline_risk),
        Contract_latest_start_excess_UID=sum(r.get('latest_start_excess_seconds',0)>0 for r in qrows),
        Contract_observed_completion_deadline_excess_UID=sum((r.get('actual_completion_deadline_excess_seconds') or 0)>0 for r in qrows),
        Actual_AIDC_IT_PCC_PQ=power,Actual_power_scope='TOTAL_OBSERVED_AIDC_OCCUPANCY_INCLUDES_KNOWN;MESS_ACCOUNTED_SEPARATELY',
        rejection_candidate_event_counts=dict(reasons),rejection_unique_UID_counts={k:len(v) for k,v in unique.items()},
        rejection_unique_UID_sets_overlap=True,Actual_PCC_PQ_delta_from_Unknown_alone=None,
        PCC_delta_status='REQUIRES_SAME_CASE_FIXED_KNOWN_MESS_COUNTERFACTUAL_REPLAY',
        Known_Unknown_action_ledger_disjoint=all(r['uid'] in unknown for r in actual['rule_consumption_receipt']),
        scope='UNKNOWN_ACTUAL_ONLY')

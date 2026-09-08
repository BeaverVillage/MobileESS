"""Deterministic same-site physical execution; planned decisions remain immutable."""
from copy import deepcopy
import heapq
import numpy as np
import pandas as pd
from dayahead.v40d_actual.job_replay import priority_key
from dayahead.v40g_segments.canonical import occupancy,terminal,identities
from dayahead.v40h.pre_day_complete import classify
from .actual import replay_jobs as naive_replay, power_from_execution
from .actual_audit import audit,NS,SLOT_NS
from .reserve import require
from .scientific_archive import document,scalar_frame
from .persistence import table

REASON='RESOURCE_CONTENTION_FROM_RUNTIME_OVERRUN'


def replay_jobs(jobs,observations,*,issue_time,site_capacity,racks,wan=None):
    before=identities(jobs); original={j['job_uid']:j for j in jobs}; issue=pd.Timestamp(issue_time)
    naive=naive_replay(jobs,observations,issue_time=issue_time,site_capacity=site_capacity,racks=racks)
    _,raw_violations,raw_jobs,raw_summary=audit(naive,observations,issue,site_capacity)
    result=deepcopy(naive); rows={j['job_uid']:j for j in result['job_ledger']}
    fixed=[]; pending=[]; durations={}; times={0,24*SLOT_NS,120*SLOT_NS}
    for uid,r in rows.items():
        if not r['frozen_policy_admitted']: continue
        obs=observations[uid]
        duration=int((pd.Timestamp(obs['end_time'])-(issue if r['state_at_issue']=='RUNNING' else pd.Timestamp(obs['start_time']))).value)
        durations[uid]=duration
        if r['state_at_issue']=='RUNNING':
            if r.get('migration_selected'):
                event=r['migration_events'][0]; source=min(duration,int(event['checkpoint'])*SLOT_NS)
                if source: fixed.append((uid,r['compute_segments'][0]['site'],0,source,r['requested_GPU']))
                if duration>source:
                    start=int(event['restart_end'])*SLOT_NS
                    fixed.append((uid,r['compute_segments'][1]['site'],start,start+duration-source,r['requested_GPU']))
            else: fixed.append((uid,r['AIDC_site'],0,duration,r['requested_GPU']))
        else:
            pending.append(uid); times.add(int(r['start_slot'])*SLOT_NS)
    migrated=any(r.get('migration_selected') for r in rows.values())
    if migrated:
        from dayahead.v41r1.migration_dispatch import execute
        execution=execute(rows,original,durations,site_capacity,wan)
        execution_parts=execution['parts'];blockers=execution['blockers'];waits=execution['waits']
        dispatched={u:v for u,v in execution_parts.items() if rows[u]['state_at_issue']=='PENDING'}
        result['migration_execution_replay']=dict(evidence=execution['evidence'],WAN_chunks=execution['WAN_chunks'],
            authority=execution['authority'],Actual_optimizer_calls=0)
    else:
        for uid,site,a,b,g in fixed: times.update((a,b))
        for t in sorted(times):
            for site,cap in site_capacity.items():
                require(sum(g for uid,s,a,b,g in fixed if s==site and a<=t<b)<=cap,'IMMUTABLE_RUNNING_EXECUTION_CAPACITY_CONFLICT')
        pending.sort(key=lambda uid:priority_key(original[uid]))
        queue=sorted(times); heapq.heapify(queue); queued=set(times); active={}; dispatched={}; blockers={uid:set() for uid in pending}; waits=[]

        def proposed(uid,t):
            r=rows[uid]
            return [(uid,r['AIDC_site'],t,t+durations[uid],r['requested_GPU'])]

        def conflicts(uid,parts):
            bad=[]
            for _,site,t,end,gpu in parts:
                occupied=[v for v in fixed if v[1]==site and v[2]<end and v[3]>t]
                occupied += [v for values in active.values() for v in values if v[1]==site and v[2]<end and v[3]>t]
                points={t}|{a for u,s,a,b,g in occupied if t<a<end}|{b for u,s,a,b,g in occupied if t<b<end}
                for point in sorted(points):
                    held=[v for v in occupied if v[2]<=point<v[3]]
                    if sum(v[4] for v in held)+gpu>site_capacity[site]:
                        bad.append((point,sorted({v[0] for v in held})))
            return sorted(bad)

        while queue:
            t=heapq.heappop(queue)
            active={u:v for u,v in active.items() if v[-1][3]>t}
            remaining=[]
            for uid in pending:
                r=rows[uid]; planned=int(r['start_slot'])*SLOT_NS
                if planned>t: remaining.append(uid); continue
                parts=proposed(uid,t);bad=conflicts(uid,parts)
                if bad:
                    held=sorted({u for point,ids in bad for u in ids}); blockers[uid].update(held)
                    waits.append(dict(job_id=uid,event_ns_from_issue=t,blocking_job_ids=held,
                        first_conflicting_ns_from_issue=bad[0][0],SITE=r['AIDC_site'],GPU_REQUEST=r['requested_GPU'],
                        frozen_priority_key=list(priority_key(original[uid])),DELAY_REASON=REASON))
                    remaining.append(uid); continue
                active[uid]=parts;dispatched[uid]=parts
                for _,_,a,b,_ in parts:
                    for event_time in (a,b):
                        if event_time>t and event_time not in queued:heapq.heappush(queue,event_time);queued.add(event_time)
            pending=remaining
        require(not pending,'DETERMINISTIC_DISPATCH_DID_NOT_DRAIN_ASSIGNED_JOBS')
        execution_parts=dispatched
    for uid,r in rows.items():
        planned=int(r['start_slot'])*SLOT_NS
        if uid in execution_parts:
            parts=execution_parts[uid];start=parts[0][2];end=parts[-1][3];delay=(start-planned)/NS
            require(delay>=0,'INVALID_EXECUTION_DISPATCH')
            r['actual_compute_segments']=[dict(site=site,start=a/SLOT_NS,end=b/SLOT_NS,
                Rack=(r['initial_Rack_label'] if r.get('migration_selected') and i==0 else r['Rack_label']),
                phase=('SOURCE' if i==0 else 'DESTINATION') if r.get('migration_selected') else 'SINGLE')
                for i,(_,site,a,b,_) in enumerate(parts)]
            r['migration_executed']=bool(r.get('migration_selected')) and len(parts)==2
            r.update(actual_start_ns_from_issue=start,actual_end_ns_from_issue=end,
                actual_execution_start=start/SLOT_NS,actual_residual_start=start/SLOT_NS,actual_execution_end=end/SLOT_NS,
                actual_Rack=r['actual_compute_segments'][-1]['Rack'],start_delay_seconds=delay,start_delay_slots=delay/900,
                actual_execution_origin='DETERMINISTIC_PHYSICAL_EXECUTION_WITHIN_FROZEN_SITE',
                delayed_by_GPU_capacity=delay>0,delayed_by_Rack_capacity=False)
            remaining=sum(max(0,b-max(120*SLOT_NS,a)) for _,site,a,b,g in parts)/NS
            r.update(unfinished_at_H=remaining>0,remaining_runtime_at_H=remaining,remaining_GPU_hours_at_H=remaining*r['requested_GPU']/3600,
                post_H_completion_time=end/SLOT_NS if end>120*SLOT_NS else None,
                post_H_site=parts[-1][1] if end>120*SLOT_NS else None)
            r['terminal_segment_state']=terminal(r,actual=True)
            r['counterfactual_day_classification']=classify(original[uid],observations[uid],issue,execution_segments=r['actual_compute_segments'])
        else:
            start=None if not r['frozen_policy_admitted'] else 0
            end=None if start is None else round(r['actual_execution_end']*SLOT_NS)
            delay=0.
        no_contention_end=round(naive['job_ledger'][next(i for i,v in enumerate(naive['job_ledger']) if v['job_uid']==uid)]['actual_execution_end']*SLOT_NS) if uid in dispatched else None
        deadline=int(r['RW_completion_slot'])*SLOT_NS
        extra_lateness=0. if no_contention_end is None else (max(0,end-deadline)-max(0,no_contention_end-deadline))/NS
        r.update(DA_PLANNED_START=(issue+pd.Timedelta(planned,unit='ns')).isoformat(),
            ACTUAL_EXECUTION_START=None if start is None else (issue+pd.Timedelta(start,unit='ns')).isoformat(),
            START_DELAY_SECONDS=delay,REALIZED_RUNTIME=r['actual_service_seconds'],
            ACTUAL_EXECUTION_END=None if end is None else (issue+pd.Timedelta(end,unit='ns')).isoformat(),
            ACTUAL_RACK=r['actual_Rack'],SITE=r['AIDC_site'],GPU_REQUEST=r['requested_GPU'],
            DA_INITIAL_SITE=original[uid]['compute_segments'][0]['site'],DA_FINAL_SITE=original[uid]['AIDC_site'],
            ACTUAL_INITIAL_SITE=r['actual_compute_segments'][0]['site'] if start is not None else None,
            ACTUAL_FINAL_SITE=r['actual_compute_segments'][-1]['site'] if start is not None else None,
            BLOCKING_JOB_IDS=sorted(blockers.get(uid,set())),DELAY_REASON=REASON if delay else None,
            frozen_priority_key=list(priority_key(original[uid])),
            contention_added_completion_lateness_seconds=extra_lateness,
            contention_caused_RW_deadline_miss=bool(no_contention_end is not None and no_contention_end<=deadline<end))
        r.update(job_id=uid,DA_SITE=original[uid]['AIDC_site'],ACTUAL_SITE=r['AIDC_site'],
            REALIZED_RUNTIME_SECONDS=r['actual_service_seconds'],
            EXECUTION_STATUS=('FROZEN_UNSELECTED_BACKLOG' if start is None else 'NOT_STARTED_BY_HORIZON' if start>=120*SLOT_NS
                              else 'STARTED_NOT_COMPLETED_BY_HORIZON' if end>120*SLOT_NS else 'COMPLETED_BY_HORIZON'))
    ledger=[rows[u] for u in sorted(rows)]; gpu,contributions=occupancy(ledger,sorted(site_capacity),actual=True)
    result.update(job_ledger=ledger,GPU=gpu,contributions=contributions,
        rack_ledger=[dict(job_uid=r['job_uid'],site=p['site'],rack_id=p['Rack'],start=p['start'],end=p['end'],
                          requested_GPU=r['requested_GPU'],phase=p['phase']) for r in ledger for p in r['actual_compute_segments']],
        rack_waits=waits,site_occupancy=[dict(slot=t,site_id=s,occupied_GPU_slots=int(gpu[t,i]),GPU_capacity=site_capacity[s])
            for t in range(96) for i,s in enumerate(sorted(site_capacity))],
        counterfactual_pre_day_complete_proofs=[r['counterfactual_day_classification'] for r in ledger
            if r['counterfactual_day_classification']['status']=='PRE_DAY_COMPLETE'])
    delays=np.array([rows[u]['start_delay_seconds'] for u in dispatched]); weights=np.array([rows[u]['requested_GPU'] for u in dispatched])
    positive=delays[delays>0]
    result['execution_delay_KPIs']=dict(delayed_jobs=int((delays>0).sum()),assigned_PENDING_jobs=len(delays),
        total_start_delay_seconds=float(delays.sum()),mean_start_delay_seconds=float(delays.mean()) if len(delays) else 0.,
        P95_start_delay_seconds=float(np.quantile(delays,.95)) if len(delays) else 0.,max_start_delay_seconds=float(delays.max()) if len(delays) else 0.,
        mean_delayed_job_seconds=float(positive.mean()) if len(positive) else 0.,
        P95_delayed_job_seconds=float(np.quantile(positive,.95)) if len(positive) else 0.,
        GPU_weighted_delay_seconds=float((delays*weights).sum()),
        GPU_weighted_mean_delay_seconds=float((delays*weights).sum()/weights.sum()) if weights.sum() else 0.,
        contention_added_completion_lateness_job_seconds=sum(r['contention_added_completion_lateness_seconds'] for r in ledger),
        contention_added_GPU_weighted_lateness_seconds=sum(r['requested_GPU']*r['contention_added_completion_lateness_seconds'] for r in ledger),
        contention_caused_RW_deadline_misses=sum(r['contention_caused_RW_deadline_miss'] for r in ledger),
        SLA_debt_authority='Diagnostic completion lateness against frozen RW completion; no new optimization debt variable')
    selected=[r for r in ledger if r['frozen_policy_admitted']]
    all_delays=np.array([r['start_delay_seconds'] for r in selected]); all_weights=np.array([r['requested_GPU'] for r in selected])
    kpi=result['execution_delay_KPIs']; kpi['mean_assigned_PENDING_delay_seconds']=kpi['mean_start_delay_seconds']
    for name,q in [('median',.5),('P90',.9),('P95',.95),('P99',.99)]:
        kpi[name+'_start_delay_seconds']=float(np.quantile(all_delays,q)) if len(all_delays) else 0.
    kpi.update(delay_population='All DayAhead selected jobs, including zero-delay RUNNING',
        mean_start_delay_seconds=float(all_delays.mean()) if len(all_delays) else 0.,
        GPU_weighted_mean_delay_seconds=float((all_delays*all_weights).sum()/all_weights.sum()) if all_weights.sum() else 0.)
    for label,threshold in [('15min',900),('1h',3600),('4h',14400)]:
        kpi['delayed_over_'+label+'_jobs']=int((all_delays>threshold).sum())
        kpi['delayed_over_'+label+'_fraction']=float((all_delays>threshold).mean()) if len(all_delays) else 0.
    started=sum(r['actual_residual_start']<120 for r in selected)
    completed=sum(r['actual_execution_end']<=120 for r in selected)
    result['execution_rate']=dict(N_DA_SELECTED_JOBS=len(selected),N_ACTUAL_STARTED_JOBS=started,
        N_ACTUAL_COMPLETED_JOBS=completed,N_DELAYED_JOBS=int((all_delays>0).sum()),
        N_NOT_STARTED_BY_HORIZON=len(selected)-started,N_NOT_COMPLETED_BY_HORIZON=len(selected)-completed,
        START_EXECUTION_RATE=started/len(selected) if selected else None,
        COMPLETION_RATE=completed/len(selected) if selected else None,
        N_EVENTUALLY_STARTED_JOBS=len(selected),N_EVENTUALLY_COMPLETED_JOBS=len(selected),
        horizon='Existing issue-relative H=120; starts strictly before H, completions at or before H',
        RUNNING_counted_as_continuing_execution=True,unselected_jobs_in_denominator=False,
        cross_day_state_carried=False)
    result['raw_runtime_contention']=dict(classification='RUNTIME_OVERRUN_INDUCED_RESOURCE_CONTENTION',
        naive_execution_feasibility=raw_summary,intervals=raw_violations.to_dict('records'),jobs=raw_jobs.to_dict('records'),
        final_physical_violation=False,ML_used_in_Actual=False)
    result['capacity_audit']=dict(status='PASS',violations=[],policy_start_reoptimized=False,physical_execution_delay=True)
    result['counters'].update(physical_execution_delayed_jobs=int((delays>0).sum()),start_changes=0,
        actual_execution_timestamp_changes=int((delays>0).sum()),Actual_optimizer_calls=0)
    events,vf,jf,summary=audit(result,observations,issue,site_capacity)
    require(summary['status']=='PASS','FINAL_PHYSICAL_GPU_CAPACITY_VIOLATION')
    result['exact_execution_feasibility']=summary
    require(identities(jobs)==before,'DISPATCH_MUTATED_DAYAHEAD_DECISIONS')
    return result


def persist(output,replay,observations,issue_time,capacity,racks):
    from .actual_audit import persist as persist_events
    final=persist_events(output,replay,observations,issue_time,capacity)
    require(final['status']=='PASS','FINAL_DISPATCH_EVENT_CAPACITY_FAILED')
    raw=replay['raw_runtime_contention']
    document(output/'aidc/NAIVE_RUNTIME_CONTENTION.json',raw)
    fields=['job_id','job_uid','DA_SITE','ACTUAL_SITE','EXECUTION_STATUS','REALIZED_RUNTIME_SECONDS',
        'DA_PLANNED_START','ACTUAL_EXECUTION_START','START_DELAY_SECONDS','REALIZED_RUNTIME',
        'ACTUAL_EXECUTION_END','ACTUAL_RACK','SITE','GPU_REQUEST','BLOCKING_JOB_IDS','DELAY_REASON',
        'frozen_priority_key','contention_added_completion_lateness_seconds','contention_caused_RW_deadline_miss']
    jobs=scalar_frame([{k:r[k] for k in fields} for r in replay['job_ledger']])
    table(output/'aidc/PHYSICAL_EXECUTION_DISPATCH.parquet',jobs)
    table(output/'aidc/DELAYED_JOBS.parquet',jobs[jobs.START_DELAY_SECONDS>0].reset_index(drop=True))
    document(output/'aidc/DISPATCH_PRIORITY_AUTHORITY.json',dict(
        source='dayahead.v40d_actual.job_replay.priority_key',keys=['frozen start_slot','existing qos tier','submit timestamp','job_uid'],
        ordering_unchanged=True,frozen_rack_preserved=True,RUNNING_decisions_immutable=True,
        RUNNING_event_clock_follows_actual_progress='migration_execution_replay' in replay,
        scheduling_optimizer_calls=0,ML_prediction_calls=0,DayAhead_feedback_calls=0))
    document(output/'ACTUAL_EXECUTION_DELAY_KPIS.json',replay['execution_delay_KPIs'])
    document(output/'ACTUAL_EXECUTION_RATE.json',replay['execution_rate'])
    resource_trace(output,replay,observations,issue_time,capacity,racks)
    if 'migration_execution_replay' in replay:
        from dayahead.v41r1.migration_dispatch import persist as persist_migrations
        persist_migrations(output,replay['migration_execution_replay'],issue_time)
    return final


def resource_trace(output,replay,observations,issue_time,capacity,racks):
    from .actual_audit import exact_intervals
    segments=exact_intervals(replay,observations,issue_time); issue=pd.Timestamp(issue_time)
    limits={(r.site,r.rack_id):r.capacity for r in racks}
    changes=[]
    for r in segments:
        require((r['site'],r['rack']) in limits and r['GPU']<=limits[r['site'],r['rack']], 'AUTHORITATIVE_RACK_GANG_LIMIT')
        for t,sign in ((r['start_ns'],1),(r['end_ns'],-1)):
            changes.append((t,sign,r))
    # All completions release resources before admissions at an identical time.
    original={r['job_uid']:r for r in replay['job_ledger']}
    changes.sort(key=lambda x:(x[0],x[1],priority_key(original[x[2]['job_id']])))
    occupied=dict.fromkeys(capacity,0); events=[]
    for t,sign,r in changes:
        site=r['site']; before=occupied[site]; after=before+sign*r['GPU']
        require(0<=after<=capacity[site],'EVENT_RESOURCE_CAPACITY_HARD_FAILURE')
        occupied[site]=after
        events.append(dict(timestamp=issue+pd.Timedelta(t,unit='ns'),event_ns_from_issue=t,IDC=site,rack=r['rack'],job_id=r['job_id'],
            event='JOB_START' if sign>0 else 'JOB_COMPLETION',GPU_delta=sign*r['GPU'],GPU_occupancy_before=before,
            GPU_occupancy_after=after,GPU_capacity=capacity[site],rack_single_gang_capacity=limits[site,r['rack']]))
    require(not any(occupied.values()),'FINAL_RESOURCE_LEDGER_NOT_DRAINED')
    table(output/'aidc/RESOURCE_CHANGE_EVENTS.parquet',pd.DataFrame(events))
    overlap=[]
    for r in segments:
        for slot in range(96):
            begin=(24+slot)*SLOT_NS; end=begin+SLOT_NS
            ns=max(0,min(end,r['end_ns'])-max(begin,r['start_ns']))
            if ns:
                overlap.append(dict(job_id=r['job_id'],IDC=r['site'],rack=r['rack'],slot=slot,
                    overlap_nanoseconds=ns,overlap_seconds=ns/NS,GPU_request=r['GPU'],GPU_seconds=ns*r['GPU']/NS,
                    exact_GPUh=ns*r['GPU']/NS/3600,mean_slot_GPU=ns*r['GPU']/SLOT_NS,
                    slot_start_GPU=r['GPU'] if r['start_ns']<=begin<r['end_ns'] else 0))
    frame=pd.DataFrame(overlap); table(output/'aidc/EXACT_JOB_SLOT_OVERLAP.parquet',frame)
    direct=sum(max(0,min(120*SLOT_NS,r['end_ns'])-max(24*SLOT_NS,r['start_ns']))*r['GPU'] for r in segments)
    recorded=sum(int(r.overlap_nanoseconds)*int(r.GPU_request) for r in frame.itertuples())
    require(direct==recorded,'EXACT_GPU_SERVICE_OVERLAP_CONSERVATION')
    document(output/'aidc/RESOURCE_TRACE_AUTHORITY.json',dict(status='PASS',event_rows=len(events),overlap_rows=len(frame),
        exact_GPU_nanoseconds=direct,GPU_capacity_hard=True,rack_gang_capacity_hard=True,
        rack_semantics='Existing non-additive single-gang compatibility envelopes; no invented cumulative per-label capacity',
        original_power_sampling='Existing slot-start instantaneous samples, using actual exact execution intervals',
        exact_overlap_saved_separately=True,planned_start_not_rounded_or_changed=True))

"""Independent exact-time execution events, raw contention and final feasibility."""
from collections import defaultdict
from datetime import timezone, timedelta
import numpy as np
import pandas as pd
from .reserve import require
from .persistence import table
from .scientific_archive import document, scalar_frame

NS=10**9
SLOT_NS=900*NS
AEST=timezone(timedelta(hours=10))


def exact_intervals(replay, observations, issue_time):
    issue=pd.Timestamp(issue_time)
    intervals=[]; by_uid={r['job_uid']:r for r in replay['job_ledger']}
    for uid,row in by_uid.items():
        if not row['frozen_policy_admitted']: continue
        o=observations[uid]
        seconds_ns=int((pd.Timestamp(o['end_time'])-(issue if row['state_at_issue']=='RUNNING' else pd.Timestamp(o['start_time']))).value)
        require(seconds_ns>0,'EXACT_ACTUAL_RUNTIME_NOT_POSITIVE')
        if row.get('migration_selected'):
            event=row['migration_events'][0]
            planned=(0 if row['state_at_issue']=='RUNNING' else int(row['start_slot']))*SLOT_NS
            begin=row.get('actual_start_ns_from_issue',planned)
            require(begin>=planned,'ACTUAL_MIGRATION_EXECUTION_BEFORE_PLAN')
            execution=row.get('actual_migration_execution')
            checkpoint=int(event['checkpoint'])*SLOT_NS
            restart=int(event['restart_end'])*SLOT_NS
            if execution:
                require(execution['CHECKPOINT_OFFSET_NS']==checkpoint-planned,'FROZEN_CHECKPOINT_OFFSET_DRIFT')
                require(execution['ACTUAL_CHECKPOINT_NS']==begin+checkpoint-planned,'ACTUAL_CHECKPOINT_PROGRESS_DRIFT')
                checkpoint=execution['ACTUAL_CHECKPOINT_NS']
                if execution['migration_executed']:
                    restart=execution['ACTUAL_RESTART_NS']
                    require(execution['ACTUAL_WAN_START_NS']>=checkpoint and restart>=execution['ACTUAL_WAN_END_NS']+SLOT_NS,
                        'ACTUAL_MIGRATION_EVENT_ORDER')
            source_ns=min(seconds_ns,checkpoint-begin)
            require(source_ns>0,'FROZEN_CHECKPOINT_PRECEDES_PHYSICAL_START')
            expected=[]
            if source_ns: expected.append((row['compute_segments'][0]['site'],begin,begin+source_ns))
            if seconds_ns>source_ns:
                start=restart
                expected.append((row['compute_segments'][1]['site'],start,start+seconds_ns-source_ns))
        else:
            planned=(0 if row['state_at_issue']=='RUNNING' else int(row['start_slot']))*SLOT_NS
            start=row.get('actual_start_ns_from_issue',planned)
            require(start>=planned and abs((start-planned)/NS-row['start_delay_seconds'])<1e-9,
                    'ACTUAL_EXECUTION_BEFORE_PLAN_OR_DELAY_MISMATCH')
            expected=[(row['AIDC_site'],start,start+seconds_ns)]
        actual=row['actual_compute_segments']
        require(len(expected)==len(actual),'EXACT_ACTUAL_SEGMENT_COUNT')
        for (site,start,end),segment in zip(expected,actual):
            require(site==segment['site'] and abs(start/SLOT_NS-segment['start'])<1e-9 and
                    abs(end/SLOT_NS-segment['end'])<1e-9,'FROZEN_START_RUNTIME_SEGMENT_RECALCULATION')
            intervals.append(dict(job_id=uid,site=site,start_ns=start,end_ns=end,GPU=int(row['requested_GPU']),rack=segment['Rack']))
    return intervals


def audit(replay, observations, issue_time, capacity):
    issue=pd.Timestamp(issue_time); by_uid={r['job_uid']:r for r in replay['job_ledger']}
    intervals=exact_intervals(replay,observations,issue)
    starts=defaultdict(list); ends=defaultdict(list)
    for r in intervals: starts[r['start_ns']].append(r); ends[r['end_ns']].append(r)
    times=sorted({0,24*SLOT_NS,120*SLOT_NS}|set(starts)|set(ends))
    active={s:{} for s in capacity}; events=[]; violations=[]; details=[]
    for i,t in enumerate(times):
        for r in ends[t]:
            require(active[r['site']].pop(r['job_id'],None)==r['GPU'],'EXACT_EVENT_RELEASE_IDENTITY')
        for r in starts[t]:
            require(r['job_id'] not in active[r['site']],'EXACT_EVENT_DOUBLE_COMPUTE')
            active[r['site']][r['job_id']]=r['GPU']
        until=times[i+1] if i+1<len(times) else t
        begin=issue+pd.Timedelta(t,unit='ns'); finish=issue+pd.Timedelta(until,unit='ns')
        for site in sorted(capacity):
            jobs=sorted(active[site]); count=sum(active[site].values()); excess=max(0,count-capacity[site])
            row=dict(event_index=i,site=site,start_ns_from_issue=t,end_ns_from_issue=until,
                exact_start_UTC=begin,exact_end_UTC=finish,duration_seconds=(until-t)/NS,
                GPU_capacity=int(capacity[site]),realized_GPU_occupancy=count,exceedance_GPU=excess,
                involved_job_ids=jobs,violation=excess>0)
            events.append(row)
            if excess and until>t:
                v=dict(row,violation_id=f'V{len(violations)+1:06d}',
                    exact_start_AEST=begin.tz_convert(AEST).isoformat(),exact_end_AEST=finish.tz_convert(AEST).isoformat(),
                    exceedance_GPUh=excess*(until-t)/NS/3600)
                violations.append(v)
                for uid in jobs:
                    j=by_uid[uid]; seconds=j['actual_service_seconds']; predicted=j['safe_duration_seconds']
                    details.append(dict(violation_id=v['violation_id'],job_id=uid,site=site,GPU_request=j['requested_GPU'],
                        frozen_DA_start_slot=j['start_slot'],DA_runtime_seconds=predicted,realized_runtime_seconds=seconds,
                        runtime_prediction_error_seconds=seconds-predicted,
                        observed_full_runtime_seconds=j['actual_runtime_seconds'],duration_authority=j['duration_authority'],
                        state_at_issue=j['state_at_issue'],frozen_admitted=j['frozen_policy_admitted'],
                        frozen_site=j['frozen_AIDC_site'],start_delay_seconds=j['start_delay_seconds']))
    event_frame=scalar_frame(events)
    # Independent integer-time sampling must match all inherited 15-min points.
    sampled=np.array([[sum(r['GPU'] for r in intervals if r['site']==s and r['start_ns']<=(24+t)*SLOT_NS<r['end_ns'])
                       for s in sorted(capacity)] for t in range(96)])
    require(np.array_equal(sampled,replay['GPU']),'EXACT_EVENT_TO_96_SLOT_OCCUPANCY_MISMATCH')
    violation_columns=list(events[0])+['violation_id','exact_start_AEST','exact_end_AEST','exceedance_GPUh']
    detail_columns=['violation_id','job_id','site','GPU_request','frozen_DA_start_slot','DA_runtime_seconds',
        'realized_runtime_seconds','runtime_prediction_error_seconds','observed_full_runtime_seconds',
        'duration_authority','state_at_issue','frozen_admitted','frozen_site','start_delay_seconds']
    vf=scalar_frame(violations) if violations else pd.DataFrame(columns=violation_columns)
    jf=pd.DataFrame(details,columns=detail_columns)
    summary=dict(status='FAIL' if violations else 'PASS',outcome='ACTUAL_EXECUTION_FEASIBILITY_VIOLATION' if violations else 'CAPACITY_FEASIBLE',
        exact_execution_events=len(times),site_event_rows=len(events),violation_intervals=len(violations),
        violation_duration_site_seconds=sum(v['duration_seconds'] for v in violations),
        exceedance_GPUh=sum(v['exceedance_GPUh'] for v in violations),
        max_exceedance_GPU=max((v['exceedance_GPU'] for v in violations),default=0),
        independent_96_slot_occupancy_equality=True,Actual_optimizer_calls=0,
        delayed_jobs=sum(j['start_delay_seconds']>0 for j in by_uid.values()),
        clipping_calls=0,site_changes=0,ordering_changes=0,migration_changes=0,
        power_trajectory_sampling='Inherited integer slot-start GPU occupancy; exact event intervals also retained, never averaged to hide violations')
    return event_frame,vf,jf,summary


def persist(output,replay,observations,issue_time,capacity):
    events,violations,jobs,summary=audit(replay,observations,issue_time,capacity)
    refs=dict(events=table(output/'aidc/EXACT_EXECUTION_EVENTS.parquet',events),
        violations=table(output/'aidc/EXECUTION_FEASIBILITY_VIOLATIONS.parquet',violations),
        involved_jobs=table(output/'aidc/VIOLATION_JOB_RUNTIME_ERRORS.parquet',jobs))
    summary['artifacts']=refs
    document(output/'ACTUAL_EXECUTION_FEASIBILITY.json',summary)
    return summary

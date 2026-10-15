"""Identical observed service/QoS accounting for Reference and Flexible arms."""
import numpy as np


def evaluate(result, *, arm, begin, end):
    public=result['carryout']['controller']
    metadata=public['metadata'];jobs=public['episode_jobs']
    failures=[];rows=[]
    for uid,meta in metadata.items():
        job=jobs[uid];start=job.get('start_time');finish=job.get('completion_observed_time')
        complete=finish is not None and finish<=end
        deadline=meta.get('completion_deadline_seconds')
        latest=meta.get('hard_latest_start_seconds');earliest=meta.get('hard_earliest_start_seconds')
        late=max(0.,(finish if complete else end)-deadline) if deadline is not None else 0.
        late_start=max(0.,(start if start is not None else end)-latest) if latest is not None else 0.
        early=max(0.,earliest-start) if earliest is not None and start is not None else 0.
        if late:failures.append('ACTUAL_SOURCE_HARD_DEADLINE:'+uid)
        if late_start:failures.append('ACTUAL_SOURCE_HARD_LATEST_START:'+uid)
        if early:failures.append('ACTUAL_SOURCE_HARD_EARLIEST_START:'+uid)
        ref=meta.get('reference_start_seconds')
        rows.append(dict(uid=uid,known=not meta['origin_unknown'],submitted=True,
            started=start is not None,started_in_day=start is not None and begin<=start<end,
            completed=complete,carry=not complete,waiting=not complete and start is None,
            wait_seconds=max(0.,(start if start is not None else end)-job['submit_time']),
            reference_start_deviation_seconds=None if start is None or ref is None else start-ref,
            source_deadline_violation_seconds=late,source_latest_start_violation_seconds=late_start,
            source_earliest_start_violation_seconds=early))
    groups={}
    for label,selected in [('all',rows),('known',[r for r in rows if r['known']]),('unknown',[r for r in rows if not r['known']])]:
        groups[label]={key:sum(r[key] for r in selected) for key in
            ('submitted','started','started_in_day','completed','carry','waiting','wait_seconds',
             'source_deadline_violation_seconds','source_latest_start_violation_seconds','source_earliest_start_violation_seconds')}
        groups[label]['conservation_PASS']=groups[label]['submitted']==groups[label]['completed']+groups[label]['carry']
    physical=result.get('receipt',{})
    common=dict(schema='TABLE_V_COMMON_OBSERVED_METRICS_V1',arm=arm,groups=groups,
        Compute_GPUh=float(np.asarray(result['compute_occupancy_GPU']).sum()*.25),
        Occupation_GPUh=float(np.asarray(result['occupancy_GPU']).sum()*.25),
        Source_deadline_violation_jobs=sum(r['source_deadline_violation_seconds']>0 for r in rows),
        Source_start_window_violation_jobs=sum(r['source_latest_start_violation_seconds']>0 or r['source_earliest_start_violation_seconds']>0 for r in rows),
        original_capacity_violations=physical.get('capacity_violations'),dropped_jobs=physical.get('dropped_jobs'),
        E1_applicable=arm in ('B1','B3'),Changed_GPUh_is_throughput=False,
        common_source_hard_deadline_gate=True,per_job=rows)
    return common,failures

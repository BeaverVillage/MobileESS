"""Exact immutable request recovery. No statistical or allocation fallback."""
from datetime import datetime
import math
import re
from .contracts import require


def positive_integer(value):
    return isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value) and value>0 and int(value)==value


def request_gpu(candidate):
    """Only explicit request quantities; occupancy/allocation are excluded."""
    values=[]
    raw=candidate.get('gpus_requested')
    if positive_integer(raw) or (isinstance(raw,(int,float)) and not isinstance(raw,bool) and raw==0):
        values.append((int(candidate['gpus_requested']),'RAW_REQUEST_GPU'))
    tres=candidate.get('ReqTRES')
    if isinstance(tres,str):
        gpu=[]
        for token in tres.split(','):
            m=re.fullmatch(r'gres/gpu(?::([A-Za-z0-9_-]+))?=(\d+)',token.strip())
            if m:gpu.append((m[1],int(m[2])))
            elif token.strip().startswith('gres/gpu'):
                return None,'AMBIGUOUS_SOURCE_MATCH'
        if len({kind for kind,n in gpu})!=len(gpu):
            return None,'AMBIGUOUS_SOURCE_MATCH'
        total=[n for kind,n in gpu if kind is None]
        typed=[n for kind,n in gpu if kind is not None]
        if total:values.extend((n,'EXACT_REQUEST_TRES') for n in total)
        if typed:values.append((sum(typed),'EXACT_REQUEST_TRES'))
    per_node=candidate.get('requested_gpus_per_node')
    nodes=candidate.get('nodes_req')
    if positive_integer(per_node) and positive_integer(nodes):
        values.append((int(per_node)*int(nodes),'EXACT_EXPLICIT_REQUEST_PER_NODE'))
    counts={n for n,method in values}
    if len(counts)>1:return None,'AMBIGUOUS_SOURCE_MATCH'
    if not counts or counts=={0}:return None,'SOURCE_FIELD_ABSENT'
    return values[0]


def recover_gpu(row,candidates,*,event_time):
    """Join full UID + submission event, never array-parent/neighbor identity."""
    event=datetime.fromisoformat(event_time)
    submitted=datetime.fromisoformat(row['submit_time'])
    require(event.tzinfo is not None and submitted.tzinfo is not None,'RECOVERY_TIMEZONE_REQUIRED')
    if submitted>event:
        return dict(GPU_gang=None,status='CAUSAL_AUTHORITY_FAILURE',method=None,candidate_count=0,ambiguity_count=0)
    uid_candidates=[c for c in candidates if c.get('job_uid')==row['job_uid']]
    exact=[c for c in uid_candidates if datetime.fromisoformat(c['submit_time'])==submitted and
           (not row.get('source_event_identity') or c.get('source_event_identity')==row['source_event_identity'])]
    if not exact:
        reason='IDENTITY_JOIN_FAILURE' if uid_candidates else 'MISSING_SOURCE_RECORD'
        return dict(GPU_gang=None,status=reason,method=None,candidate_count=0,ambiguity_count=0)
    if any(datetime.fromisoformat(c.get('request_observed_at',c['submit_time']))>event for c in exact):
        return dict(GPU_gang=None,status='CAUSAL_AUTHORITY_FAILURE',method=None,candidate_count=len(exact),ambiguity_count=0)
    extracted=[request_gpu(c) for c in exact]
    counts={count for count,method in extracted if count is not None}
    if len(counts)>1 or any(method=='AMBIGUOUS_SOURCE_MATCH' for count,method in extracted):
        return dict(GPU_gang=None,status='AMBIGUOUS_SOURCE_MATCH',method=None,candidate_count=len(exact),ambiguity_count=max(2,len(counts)))
    # A missing field in another exact version cannot be silently treated as
    # corroboration of a different version's request. Version history is needed.
    if not counts or any(count is None for count,method in extracted):
        return dict(GPU_gang=None,status='SOURCE_FIELD_ABSENT',method=None,candidate_count=len(exact),ambiguity_count=0)
    return dict(GPU_gang=next(iter(counts)),status='SOURCE_RECOVERED',method=extracted[0][1],candidate_count=len(exact),ambiguity_count=0)


def validate_date_axis(days):
    from datetime import date,timedelta
    expected=[(date(2025,4,1)+timedelta(days=i)).isoformat() for i in range(30)]
    require(list(days)==expected,'EXACT_APRIL_30_DAY_AXIS')


def reconcile_population(source_rows,bundle_rows):
    source={r['job_uid'] for r in source_rows};bundle={r['job_uid'] for r in bundle_rows}
    require(len(source)==len(source_rows) and len(bundle)==len(bundle_rows),'DUPLICATE_JOB_IDENTITY')
    require(source==bundle,'SILENT_WORKLOAD_DROP')
    by_id={r['job_uid']:r for r in source_rows}
    for row in bundle_rows:
        old=by_id[row['job_uid']]
        if old.get('GPU_gang') is not None:
            require(old['GPU_gang']==row.get('GPU_gang'),'IMMUTABLE_GPU_REQUEST_CHANGED')
    measurable=sum(r['GPU_gang']*r['service_slots']/4 for r in bundle_rows
                   if positive_integer(r.get('GPU_gang')) and isinstance(r.get('service_slots'),int))
    return dict(source_jobs=len(source_rows),bundle_jobs=len(bundle_rows),rows_retained=True,
                measurable_nominal_GPUh=measurable,
                total_nominal_GPUh=None if any(r.get('GPU_gang') is None or r.get('service_slots') is None for r in bundle_rows) else measurable,
                mass_complete=all(r.get('GPU_gang') is not None and r.get('service_slots') is not None for r in bundle_rows))

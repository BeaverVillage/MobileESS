"""Evidence adjudication independent of all science models and optimizers."""
from datetime import datetime
from .forensic import PRE,AUTH,MISS,CONFLICT,digest

def timestamp(value):
    t=datetime.fromisoformat(str(value).replace('Z','+00:00'))
    if t.tzinfo is None:raise ValueError('NAIVE_TIMESTAMP')
    return t

def classify(case_id,uid,boundary,evidence):
    """Adjudicated evidence must be bound to a verified source and execution domain.

    Source hashes alone establish identity, not truth. ``adjudicated`` records
    must come from a reviewed raw producer lineage; arbitrary candidate JSON
    is never passed to this interface as trusted evidence.
    """
    accepted=[];rejected=[]
    for e in evidence:
        if str(e.get('uid'))!=str(uid) or e.get('case_id')!=case_id:
            rejected.append('CASE_UID_SCOPE_MISMATCH');continue
        if not (e.get('adjudicated') is True and e.get('source_hash_verified') is True and
                e.get('source_path') and len(e.get('source_sha256',''))==64 and e.get('row_key')):
            rejected.append('UNVERIFIED_SOURCE_BINDING');continue
        if e.get('site_origin') in ('PLANNING','INFERRED','PHYSICAL_NODE_UNMAPPED'):
            rejected.append('NONAUTHORITATIVE_SITE_ORIGIN');continue
        if e.get('domain')!='CURRENT_CASE_EXECUTION':
            rejected.append('OBSERVED_HISTORY_NOT_CURRENT_EXECUTION');continue
        try:
            start,end=timestamp(e['actual_start']),timestamp(e['actual_end'])
            if end<=start:raise ValueError('INVALID_CHRONOLOGY')
        except (ValueError,KeyError,TypeError):
            rejected.append('INVALID_CHRONOLOGY');continue
        accepted.append((e,start,end))
    conflicts=[]
    for i,(a,sa,ea) in enumerate(accepted):
        for b,sb,eb in accepted[i+1:]:
            fields=[]
            if sa!=sb:fields.append('actual_start')
            if ea!=eb:fields.append('actual_end')
            if a.get('actual_site') is not None and b.get('actual_site') is not None and a['actual_site']!=b['actual_site']:
                fields.append('actual_site')
            if fields:conflicts.append({'source_A':a,'source_B':b,'conflicting_fields':fields})
    if conflicts:return {'classification':CONFLICT,'conflicts':conflicts,'rejected':rejected}
    if any(end<=timestamp(boundary) and e.get('complete_timing') is True for e,start,end in accepted):
        return {'classification':PRE,'conflicts':[],'rejected':rejected}
    if any(e.get('actual_site') and e.get('site_origin')=='DIRECT_EXECUTION_ALLOCATION' and
           e.get('complete_timing') is True and e.get('full_active_interval_site_coverage') is True
           for e,start,end in accepted):
        return {'classification':AUTH,'conflicts':[],'rejected':rejected}
    return {'classification':MISS,'conflicts':[],'rejected':rejected}

def aggregate(labels):
    if not labels:raise ValueError('EMPTY_CASE')
    if CONFLICT in labels:return CONFLICT
    if MISS in labels:return MISS
    return AUTH if AUTH in labels else PRE

def deduplicate_raw(rows):
    """Preserve all source bindings; flag conflicting records, never choose one."""
    groups={}
    for r in rows:
        key=(str(r['uid']),r['domain'])
        groups.setdefault(key,[]).append(r)
    conflicts=[]
    for key,values in groups.items():
        for i,a in enumerate(values):
            for b in values[i+1:]:
                fields=[k for k in ('actual_start','actual_end','nodes','gpus_requested') if a.get(k)!=b.get(k)]
                if fields:conflicts.append({'key':list(key),'source_A':a,'source_B':b,'conflicting_fields':fields})
    return groups,conflicts

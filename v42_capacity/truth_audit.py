"""Source-backed Actual environment truth, never admission/controller features."""
import zipfile
from collections import Counter
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from .common import *

def extract():
    archive=read(PRIOR/'BUNDLE/DAY_20250401/SOURCE_PROVENANCE.json')['archive']
    path=resolve(archive)
    member_keys={}; requested={}
    for d in range(1,31):
        day='2025-04-%02d'%d; folder=PRIOR/'BUNDLE'/day_folder(day)
        p=read(folder/'PLANNING_INPUT_BUNDLE.json'); a=read(folder/'ACTUAL_INPUT_BUNDLE.json')
        for row in p['known_population']+a['post_issue_arrivals']:
            key=(row['source_member'],int(row['source_row']))
            if key in requested and requested[key] != row['job_uid']: raise ValueError('SOURCE_ROW_IDENTITY_CONFLICT')
            requested[key]=row['job_uid']; member_keys.setdefault(row['source_member'],set()).add(int(row['source_row']))
    truth={}; cols=['id','submit_time','start_time','end_time','wallclock_used','state','state_simple']
    with zipfile.ZipFile(path) as z:
        for member, indices in sorted(member_keys.items()):
            if '/month=5/' in member: raise ValueError('MAY_RAW_DONOR_FORBIDDEN')
            with z.open(member) as f:
                pf=pq.ParquetFile(f); offset=0
                for batch in pf.iter_batches(columns=cols,batch_size=32768,use_threads=False):
                    frame=batch.to_pandas(); frame['source_row']=np.arange(offset,offset+len(frame)); offset+=len(frame)
                    frame=frame[frame.source_row.isin(indices)]
                    for row in frame.to_dict('records'):
                        uid=str(row['id']); key=(member,int(row['source_row']))
                        if requested[key]!=uid or uid in truth: raise ValueError('EXACT_ACTUAL_UID_SOURCE_JOIN')
                        start=row['start_time']; end=row['end_time']; submit=row['submit_time']
                        duration=(end-start).total_seconds() if pd.notna(start) and pd.notna(end) else None
                        used=row['wallclock_used'].total_seconds() if pd.notna(row['wallclock_used']) else None
                        valid=duration is not None and np.isfinite(duration) and duration>=0 and start>=submit
                        # Missing start cannot distinguish cancelled-before-service,
                        # censoring and an actual executed service obligation.
                        # wallclock_used==0 is not a uniquely realized service duration.
                        status='SOURCE_OBSERVED_END_MINUS_START' if valid else 'REALIZED_SERVICE_DURATION_NOT_IDENTIFIABLE'
                        truth[uid]=dict(job_uid=uid,submit_time=submit.isoformat(),
                            start_time=start.isoformat() if pd.notna(start) else None,
                            end_time=end.isoformat() if pd.notna(end) else None,
                            realized_seconds=duration if valid else None,source_wallclock_used_seconds=used,
                            source_state=row['state'],source_state_simple=row['state_simple'],
                            source_member=member,source_row=key[1],source_sha256=archive['sha256'],
                            authority=status,controller_receives_future_duration=False)
    if set(truth)!=set(requested.values()): raise ValueError('ACTUAL_SOURCE_POPULATION_JOIN_INCOMPLETE')
    return truth,dict(archive=archive,resolved_archive=record(path),raw_columns_read=cols,
                      raw_members_read=sorted(member_keys),May_members_read=[])

def main():
    truth,source=extract()
    missing=[r for r in truth.values() if r['realized_seconds'] is None]
    table(OUT,'ACTUAL_REALIZED_SERVICE_AUTHORITY_LEDGER.csv',list(truth.values()),list(next(iter(truth.values()))))
    perday=[]; affected=[]
    for d in range(1,31):
        day='2025-04-%02d'%d; folder=PRIOR/'BUNDLE'/day_folder(day)
        p=read(folder/'PLANNING_INPUT_BUNDLE.json'); a=read(folder/'ACTUAL_INPUT_BUNDLE.json')
        rows=p['known_population']+a['post_issue_arrivals']
        bad=[]
        for row in rows:
            t=truth[row['job_uid']]
            if t['realized_seconds'] is None:
                bad.append(row['job_uid']); affected.append(dict(day=day,population='KNOWN_D1' if row['state_at_D1_cutoff'] else 'ACTUAL_POST_ISSUE',**t))
        perday.append(dict(day=day,physical_jobs=len(rows),source_realized_duration_complete=not bad,
                          unresolved_count=len(bad),unresolved_UIDs=bad))
    table(OUT,'ACTUAL_MISSING_SERVICE_AUTHORITY.csv',affected,list(affected[0]) if affected else ['day','job_uid'])
    audit=dict(unique_physical_jobs=len(truth),uniquely_source_backed_realized_duration_jobs=len(truth)-len(missing),
        missing_realized_duration_unique_jobs=len(missing),missing_states=dict(Counter(str(r['source_state']) for r in missing)),
        source_wallclock_used_values_missing_rows=dict(Counter(str(r['source_wallclock_used_seconds']) for r in missing)),
        missing_actual_start=sum(r['start_time'] is None for r in missing),missing_actual_end=sum(r['end_time'] is None for r in missing),
        missing_wallclock_used=sum(r['source_wallclock_used_seconds'] is None for r in missing),
        alternative_positive_wallclock_used_missing_rows=sum(r['source_wallclock_used_seconds'] is not None and r['source_wallclock_used_seconds']>0 for r in missing),
        days=perday,complete_days=sum(r['source_realized_duration_complete'] for r in perday),source=source,
        requested_walltime_used_as_Actual_duration=False,Q50_used_as_Actual_duration=False,
        zero_duration_imputed=False,missing_jobs_excluded=False,May_scientific_outcomes_used=False,
        hidden_environment_interface_required=True)
    write(OUT,'ACTUAL_REALIZED_SERVICE_AUTHORITY_AUDIT.json',audit)
    print({k:v for k,v in audit.items() if k not in ('days','source')},flush=True)

if __name__=='__main__': main()

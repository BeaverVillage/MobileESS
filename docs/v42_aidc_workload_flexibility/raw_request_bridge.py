"""Compare frozen evaluation requests to raw final accounting request fields.

This is provenance diagnostics only; no realized evaluation timestamps are read,
and no value from this bridge enters eligibility or cohort fitting.
"""
from pathlib import Path
import json,zipfile
import pandas as pd
import pyarrow.parquet as pq
from study import HERE,RAW,sha,csv,dump

def main():
    refs=pd.read_csv(HERE/'REFERENCE_POPULATION.csv',dtype={'job_uid':str})
    ids=set(refs.job_uid);rows=[];inventory=[]
    with zipfile.ZipFile(RAW) as z:
        for name in sorted(z.namelist()):
            if not name.endswith('.parquet'):continue
            cols=['id','qos','partition','submit_time','gpus_requested','nodes_req','wallclock_req']
            f=pq.read_table(z.open(name),columns=cols).to_pandas()
            q=f[f.id.isin(ids)].copy()
            if len(q):
                q['requested_walltime_seconds']=q.wallclock_req.dt.total_seconds()
                rows.append(q.drop(columns=['wallclock_req']))
            inventory.append(dict(member=name,raw_rows=len(f),matched_rows=len(q)))
    raw=pd.concat(rows,ignore_index=True);assert raw.id.is_unique
    csv('RAW_EVALUATION_REQUESTS.csv',raw.sort_values('id'))
    joined=refs.merge(raw,left_on='job_uid',right_on='id',how='left',suffixes=('_reference','_raw'),validate='many_to_one')
    assert len(joined)==len(refs)
    mismatches={}
    for a,b in [('qos_reference','qos_raw'),('partition_reference','partition_raw'),('requested_GPU','gpus_requested'),('requested_nodes','nodes_req'),('requested_walltime_seconds_reference','requested_walltime_seconds_raw')]:
        mismatches[a]=int(joined[a].ne(joined[b]).sum())
    issues=pd.to_datetime(joined.day,utc=True)-pd.Timedelta(hours=16)
    submits=pd.to_datetime(joined.submit_time_raw,utc=True)
    dump('RAW_REQUEST_BRIDGE.json',dict(raw_archive_sha256=sha(RAW),raw_total_records=sum(r['raw_rows'] for r in inventory),reference_job_days=len(refs),unique_reference_jobs=len(ids),matched_unique_jobs=len(raw),missing_job_days=int(joined.id.isna().sum()),request_mismatches=mismatches,submit_after_issue=int(submits.gt(issues).sum()),partitions=inventory,read_columns=cols,historical_request_version_certification='UNVERIFIED; matching final accounting fields is not historical-version evidence',eligibility_affected=False))
    print(json.dumps(dict(mismatches=mismatches,matched=len(raw),required=len(ids))))

if __name__=='__main__':main()

from common7 import *
import io,zipfile
import numpy as np,pandas as pd

def main():
    idx=pd.read_parquet(LOCAL/'DUPLICATE_INDEX.parquet');parts=[]
    cols=['id','job_id','array_pos','array_range','submit_time','wallclock_req','gpus_requested','nodes_req','processors_req','memory_req','qos','partition','account_hash','user_hash','state_simple']
    with zipfile.ZipFile(RAW) as z:
        for member,ix in idx.groupby('source_member',observed=True):
            f=pd.read_parquet(io.BytesIO(z.read(str(member))),columns=cols);f=f.iloc[ix.source_row.to_numpy()].copy();f['source_member']=str(member);f['source_row']=ix.source_row.to_numpy()
            f.submit_time=pd.to_datetime(f.submit_time,utc=True);f['requested_seconds']=f.wallclock_req.dt.total_seconds();f=f.drop(columns='wallclock_req');parts.append(f)
    f=pd.concat(parts,ignore_index=True);assert len(f)==len(idx)
    f.to_parquet(ROOT/'REQUEUE_DUPLICATE_RECORDS.parquet',index=False)
    request=['requested_seconds','gpus_requested','nodes_req','processors_req','memory_req','qos','partition','account_hash','user_hash']
    rows=[]
    def values(g,c):return __import__('json').dumps(sorted(set(g[c].dropna().astype(str))),ensure_ascii=False)
    for key,g in f.groupby('job_id',sort=True):
        ap=g.array_pos;valid_pos=ap.notna()&(ap>=0)&(ap==np.floor(ap))
        sibling=bool(valid_pos.all() and ap.is_unique and g.id.is_unique)
        changed=[c for c in request if g[c].nunique(dropna=False)>1]
        rows.append(dict(job_identifier=int(key),record_count=len(g),full_ids=values(g,'id'),array_positions=values(g,'array_pos'),
          submit_timestamps=values(g,'submit_time'),submit_timestamp_count=g.submit_time.nunique(),requested_walltime_values=values(g,'requested_seconds'),GPU_values=values(g,'gpus_requested'),
          qos_values=values(g,'qos'),partition_values=values(g,'partition'),account_values=values(g,'account_hash'),state_values=values(g,'state_simple'),
          array_sibling_evidence=sibling,identity_class='DISTINCT_ARRAY_TASKS_NOT_REVISION_HISTORY' if sibling else 'AMBIGUOUS_SHARED_NUMERIC_ID',
          changed_request_fields='|'.join(changed),changed_field_count=len(changed),
          change_observed_within_same_task=False,earliest_observed_timestamp=str(g.submit_time.min()),
          earliest_record_unique=int(g.submit_time.eq(g.submit_time.min()).sum())==1,
          initial_request_reconstructable=False,requeue_indicator_available=False))
    a=pd.DataFrame(rows);a.to_csv(ROOT/'REQUEUE_DUPLICATE_AUDIT.csv',index=False,lineterminator='\n')
    f.sort_values(['job_id','array_pos','id']).head(100).to_csv(ROOT/'REQUEUE_DUPLICATE_SAMPLE.csv',index=False,lineterminator='\n')
    # Check all GPU array rows, including single observed elements not in duplicates.
    g=pd.read_parquet(LOCAL/'GPU_PREAPRIL.parquet');ap=g.array_pos
    array=g[ap.notna()];negative=int((ap.dropna()<0).sum());noninteger=int((ap.dropna()!=np.floor(ap.dropna())).sum())
    logical_dup=int(array.duplicated(['job_id','array_pos'],keep=False).sum())
    summary=read(ROOT/'DUPLICATE_INDEX_SUMMARY.json')
    summary.update(distinct_array_sibling_groups=int(a.array_sibling_evidence.sum()),ambiguous_numeric_groups=int((~a.array_sibling_evidence).sum()),
      groups_with_multiple_submit_timestamps=int(a.submit_timestamp_count.gt(1).sum()),groups_with_request_differences=int(a.changed_field_count.gt(0).sum()),
      groups_with_unique_earliest_observed_record=int(a.earliest_record_unique.sum()),same_task_request_changes_observed=0,
      initial_request_reconstructable_jobs=0,initial_request_reconstruction_proven_fraction=0.0,
      fraction_scope='0/N source-backed proofs; NOT an estimate that all requests were modified or original values never existed.',
      DUPLICATE_HISTORY_AVAILABLE=False,REQUEUE_HISTORY_AVAILABLE=False,terminal_requeue_rows=len(pd.read_parquet(ROOT/'REQUEUE_TERMINAL_STATE_ROWS.parquet')),
      reason='Unique full IDs; repeated numeric IDs are array siblings or ambiguous groups, not a time-version key. No attempt/restart/original-submit/effective-time columns. Final terminal states cannot rule out prior requeue.',
      gpu_array_rows=len(array),gpu_array_noninteger_positions=noninteger,gpu_array_negative_positions=negative,gpu_same_array_coordinate_duplicate_rows=logical_dup,
      identifier_semantics='Observed id often numeric per-task, job_id shared across distinct array_pos. Datacard id=JobID and job_id=JobIDRaw is not sufficient to establish exact export mapping; internal DB/export code needed.',
      no_deduplication_before_audit=True,April_May_payload_read=False)
    write('REQUEUE_DUPLICATE_SUMMARY.json',summary)
    write('SUBMIT_TIME_AUTHORITY_AUDIT.json',dict(category='D_PRESENT_IN_ARCHIVE_BUT_VERSION_UNRESOLVED',raw_field='sacct Submit',
      timezone='Published Arrow offset timestamp -> UTC normalization; not accounting insertion time by documented semantics.',
      original_vs_requeue='Either initial or later attempt submit; no OriginalSLUID/SLUID/Restarts/attempt_id or collection -D receipt.',
      upstream_code='Slurm23.11 job_mgr.c requeue path assigns a new details->submit_time; sacct -D needed to show duplicates. Historical Kestrel installed version/config not recovered.',
      multiple_submit_groups=summary['groups_with_multiple_submit_timestamps'],multiple_submit_groups_are_not_proven_requeue=True,
      ORIGINAL_SUBMIT_TIME_RECOVERABLE=False,verified_original_cohort_N=0,submit_hour_allowed=False,submit_day_of_week_allowed=False,
      non_requeue_final_state_is_not_no_requeue_proof=True,source_backed_earliest_record_fraction=0.0))
    print(summary,flush=True)
if __name__=='__main__':main()

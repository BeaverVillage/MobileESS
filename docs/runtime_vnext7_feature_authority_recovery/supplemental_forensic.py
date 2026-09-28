from common7 import *
import urllib.request,datetime,subprocess,pandas as pd

def main():
    base='https://raw.githubusercontent.com/NatLabRockies/hpc_tandem_predictions/77be4fd9f38627cf97fec3cc8794d02e040ea1de/'
    remote=[]
    for name in ['README.md','src/sbatch_pred/runtime_prediction/data_preprocessing.py','src/sbatch_pred/queuetime_prediction/system_state.py']:
        url=base+name;p=LOCAL/'authority'/('tandem_'+Path(name).name+'.source')
        with urllib.request.urlopen(url,timeout=40) as r:p.write_bytes(r.read())
        remote.append(dict(url=url,downloaded_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),**record(p)))
    write('SUPPLEMENTAL_AUTHORITY_SOURCES.json',dict(sources=remote,reason='Follow up all relevant official GitHub search results. Source inspection only; no public model/data payload opened or executed.'))
    a=pd.read_csv(ROOT/'REQUEUE_DUPLICATE_AUDIT.csv');f=pd.read_parquet(ROOT/'REQUEUE_DUPLICATE_RECORDS.parquet')
    ids=set(a.loc[a.identity_class.eq('AMBIGUOUS_SHARED_NUMERIC_ID'),'job_identifier']);rows=[]
    for key,g in f[f.job_id.isin(ids)].groupby('job_id'):
        indexed=g[g.array_pos.notna()];unindexed=g[g.array_pos.isna()]
        rows.append(dict(job_id=int(key),records=len(g),indexed_rows=len(indexed),unindexed_rows=len(unindexed),array_range_nonmissing=int(g.array_range.notna().sum()),
          indexed_coordinates_unique=indexed.array_pos.is_unique,unindexed_id_matches_group=bool(unindexed.id.astype(str).eq(str(key)).all()),
          interpretation='ARRAY_PARENT_OR_RANGE_PLUS_TASKS_PLAUSIBLE; exact export identity mapping unavailable',original_reconstruction=False))
    pd.DataFrame(rows).to_csv(ROOT/'AMBIGUOUS_ARRAY_IDENTITY_SUPPLEMENT.csv',index=False,lineterminator='\n')
    write('ARRAY_IDENTITY_SUPPLEMENT.json',dict(groups=len(rows),all_indexed_coordinates_unique=all(r['indexed_coordinates_unique'] for r in rows),
      all_have_single_unindexed_row=all(r['unindexed_rows']==1 for r in rows),all_unindexed_id_matches_group=all(r['unindexed_id_matches_group'] for r in rows),
      unindexed_row_distribution=pd.Series([r['unindexed_rows'] for r in rows]).value_counts().to_dict(),
      with_array_range=sum(r['array_range_nonmissing']>0 for r in rows),same_coordinate_duplicate_nonmissing_rows=int(f[f.array_pos.notna()].duplicated(['job_id','array_pos'],keep=False).sum()),
      changes_across_sibling_groups=a.loc[a.changed_field_count.gt(0),'changed_request_fields'].value_counts().to_dict(),
      multiple_submit_groups=a.loc[a.submit_timestamp_count.gt(1),['job_identifier','record_count','submit_timestamps','identity_class']].to_dict('records'),
      frozen_authority_changed=False))
    second=RAWROOT/'NLR Kestrel Jobs/esif.hpc.kestrel.job-anon.zip'
    write('ARCHIVE_COPY_AUDIT.json',dict(primary=record(RAW),second=record(second),identical=sha(RAW)==sha(second),independent_revision_history=False))
    print('SUPPLEMENT_COMPLETE',flush=True)
if __name__=='__main__':main()

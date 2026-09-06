"""Independent V40R3 ingestion: all raw submissions, no H100/status/F30 filter."""
from .common import *
import io, re, zipfile, time
import pyarrow.parquet as pq

RAW=Path('C:/Users/kjw39/OneDrive/Desktop/4-2/Mobile ESS/raw데이터/데이터 센터/NLR HPC Kestrel Jobs Data/esif.hpc.kestrel.job-anon.zip')
RAW_SHA='3a90f9ac40991712f8718c686fa7b05d7a303a44a87ed1a8f21b403c11efd26f'
DOC=RAW.parent/'datacard.md'
COLS=['id','partition','qos','submit_time','start_time','end_time','gpus_requested','wallclock_req']

def main():
    assert not (OUT/'V40R3_PREREGISTRATION.json').exists()
    assert sha(RAW)==RAW_SHA
    assert read('V40R3_DOWNSTREAM_WORKLOAD_CONTRACT_AUDIT.json')['slow_scheduling_grid_minutes']==30
    frames=[]; aggs=[]; groups=[]; skips=[]; seen=set(); decoded=0; unique=0; duplicate=0; t=time.monotonic()
    with zipfile.ZipFile(RAW) as z:
        for name in sorted(z.namelist()):
            m=re.search(r'year=(\d{4})/month=(\d{1,2})/',name)
            if not m or not name.endswith('.parquet') or not 202402<=int(m[1])*100+int(m[2])<=202502:continue
            pf=pq.ParquetFile(io.BytesIO(z.read(name))); names=pf.schema_arrow.names
            for i in range(pf.num_row_groups):
                safe=True; bounds={}
                for col in ['submit_time','start_time','end_time']:
                    stat=pf.metadata.row_group(i).column(names.index(col)).statistics
                    if stat is None or not stat.has_min_max:safe=False;continue
                    lo,hi=pd.Timestamp(stat.min),pd.Timestamp(stat.max)
                    if lo.tzinfo is None or hi.tzinfo is None:raise ValueError('RAW_TIMEZONE_AUTHORITY_MISSING')
                    bounds[col]={'min':lo,'max':hi}; safe &= hi<MAY
                if not safe:
                    skips.append({'member':name,'row_group':i,'bounds':bounds,'reason':'PHYSICAL_GROUP_NOT_PROVEN_PRE_MAY'})
                    continue
                f=pf.read_row_group(i,columns=COLS).to_pandas(); decoded+=len(f)
                for c in ['submit_time','start_time','end_time']: f[c]=pd.to_datetime(f[c],utc=True)
                if f.submit_time.isna().any():raise ValueError('INVALID_RAW_SUBMIT_TIME')
                ids=f.id.astype(str)
                keep=[]
                for ident in ids:
                    new=ident not in seen; keep.append(new)
                    if new:seen.add(ident)
                # A duplicate raw identity requires a full consistency audit, not silent collapse.
                duplicate+=len(f)-sum(keep)
                if duplicate:raise ValueError('DUPLICATE_RAW_IDS_REQUIRE_INDEPENDENT_AUDIT')
                unique+=len(f); f['id']=ids
                f['arrival_bin']=f.submit_time.dt.floor('30min')
                f['missing_end']=f.end_time.isna().astype('int64')
                aggs.append(f.groupby('arrival_bin').agg(submit_count=('id','size'),max_observed_end=('end_time','max'),unresolved_end_count=('missing_end','sum')).reset_index())
                f['partition']=f.partition.fillna('UNKNOWN').str.lower(); f['qos']=f.qos.fillna('UNKNOWN').str.lower()
                candidate=f.gpus_requested.gt(0)|f.partition.str.contains('gpu',case=False,regex=False)
                c=f.loc[candidate].copy()
                c['requested_seconds']=c.wallclock_req.dt.total_seconds();c=c.drop(columns=['wallclock_req','missing_end'])
                c['source_member']=name;frames.append(c)
                groups.append({'member':name,'group':i,'raw_rows':len(f),'GPU_related_candidate_rows':len(c),'bounds':bounds})
            print(f'Ingested pre-May member {m[1]}-{int(m[2]):02d}; {decoded:,} rows, {time.monotonic()-t:.1f}s',flush=True)
    del seen
    jobs=pd.concat(frames,ignore_index=True).sort_values(['submit_time','id']).reset_index(drop=True)
    bins=pd.concat(aggs,ignore_index=True).groupby('arrival_bin').agg(submit_count=('submit_count','sum'),max_observed_end=('max_observed_end','max'),unresolved_end_count=('unresolved_end_count','sum'))
    coverage=min(pd.Timestamp(s['bounds']['submit_time']['min']) for s in skips)
    bins=bins.loc[bins.index<coverage].sort_index()
    grid=pd.date_range(pd.Timestamp('2024-02-01',tz='UTC'),coverage.tz_convert('UTC').floor('30min'),freq='30min',inclusive='left')
    bins=bins.reindex(grid); bins.index.name='arrival_bin'
    bins[['submit_count','unresolved_end_count']]=bins[['submit_count','unresolved_end_count']].fillna(0).astype('int64')
    jobs['GPU_quantity_authorized']=jobs.gpus_requested.notna()&np.isfinite(jobs.gpus_requested)&jobs.gpus_requested.gt(0)
    jobs['runtime_seconds']=(jobs.end_time-jobs.start_time).dt.total_seconds()
    jobs['model_cohort']=jobs.GPU_quantity_authorized&jobs.start_time.notna()&jobs.end_time.notna()&jobs.runtime_seconds.gt(0)&jobs.start_time.ge(jobs.submit_time)
    # Missing GPU remains missing. Only authorized cohort records obtain a work label.
    jobs['work_GPUh']=np.nan
    jobs.loc[jobs.model_cohort,'work_GPUh']=jobs.loc[jobs.model_cohort,'gpus_requested']*jobs.loc[jobs.model_cohort,'runtime_seconds']/3600
    assert jobs.id.is_unique and jobs.work_GPUh.dropna().ge(0).all()
    for col in ['submit_time','start_time','end_time']:assert jobs[col].dropna().lt(MAY).all()
    jobs.to_parquet(OUT/'GPU_related_candidates_preMay.parquet',index=False)
    bins.to_parquet(OUT/'all_raw_submission_bins_preMay.parquet')
    dump('V40R3_RAW_INGESTION_RECEIPT.json',{'raw_path':RAW,'raw_SHA256':RAW_SHA,'datacard':DOC,'datacard_SHA256':sha(DOC),
      'raw_rows_decoded':decoded,'unique_raw_jobs':unique,'duplicate_IDs':duplicate,'GPU_related_candidates':len(jobs),
      'GPU_quantity_authorized':int(jobs.GPU_quantity_authorized.sum()),'GPU_quantity_missing':int(jobs.gpus_requested.isna().sum()),
      'model_cohort_jobs':int(jobs.model_cohort.sum()),'complete_submission_coverage_before_UTC':coverage,
      'safe_row_groups':groups,'skipped_row_groups':skips,'May_scientific_rows':0,'final_status_columns_read':False,
      'GPU_related_candidate_rule':'requested_gpu>0 OR partition string contains gpu; descriptive census only',
      'primary_population':'all requested_gpu>0 with valid observed submit/start/end and positive service, regardless of partition/QoS/final status',
      'mature_history_guard':'All raw submissions in the historical bin must have observed END events, including non-modeled jobs; conservatively avoids using future membership to declare a bin mature',
      'request_resource_features':'Not admitted: archive does not establish immutable submit-time versions',
      'raw_authority_limit':'Periodic sacct event-time reconstruction; archive latency and request-field version history not certified',
      'seconds':time.monotonic()-t})
    print(json.dumps({'raw':unique,'GPU_related':len(jobs),'modeled':int(jobs.model_cohort.sum()),'missing_gpu':int(jobs.gpus_requested.isna().sum())},indent=2))

if __name__=='__main__':main()

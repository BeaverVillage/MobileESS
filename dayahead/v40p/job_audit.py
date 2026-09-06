"""Read only raw archive row groups whose job event endpoints precede May."""
from .common import *
import io,re,zipfile,shutil
from scipy.stats import wasserstein_distance

RAW=Path(r'C:\Users\kjw39\OneDrive\Desktop\4-2\Mobile ESS\raw데이터\데이터 센터\NLR HPC Kestrel Jobs Data\esif.hpc.kestrel.job-anon.zip')

def main():
    snapshots=json.loads((OUT/'source_snapshots.json').read_text(encoding='utf-8'))
    package='kestrel_stage_k2_modular_v202'
    for rel in ['src/kestrel_pipeline/sql.py','config/pipeline.yaml']:
        p=TOOLS/package/rel;dest=OUT/'source_snapshots'/package/rel
        dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,dest)
        snapshots.append({'source':p,'snapshot':dest.relative_to(ROOT),'sha256':digest(dest)})
        record_access(p,'SOURCE_CODE_OR_CONFIG')
    dump('source_snapshots.json',snapshots)
    cols=['id','partition','qos','state_simple','submit_time','start_time','end_time','nodes_req','gpus_requested','wallclock_req']
    frames=[];opened=[];skipped=[]
    with zipfile.ZipFile(RAW) as archive:
        for name in sorted(archive.namelist()):
            match=re.search(r'year=(\d{4})/month=(\d{1,2})/',name)
            if not match or not name.endswith('.parquet'):continue
            month=int(match[1])*100+int(match[2])
            if not 202402<=month<=202503:continue
            pf=pq.ParquetFile(io.BytesIO(archive.read(name)))
            names=pf.schema_arrow.names;groups=[]
            for i in range(pf.num_row_groups):
                safe=True;bounds={}
                for c in ['submit_time','start_time','end_time']:
                    st=pf.metadata.row_group(i).column(names.index(c)).statistics
                    if st is None or not st.has_min_max:safe=False;continue
                    bound=pd.Timestamp(st.max);bound=bound.tz_localize('UTC') if bound.tzinfo is None else bound
                    bounds[c]=bound
                    safe &= bound<LIMIT
                if not safe:skipped.append({'member':name,'row_group':i,'maxima':bounds});continue
                f=pf.read_row_group(i,columns=cols).to_pandas()
                f=f.loc[f.partition.fillna('').str.lower().str.contains(r'(^|,)gpu-h100(s|l)?(-stdby)?($|,)',regex=True)].copy()
                for c in ['submit_time','start_time','end_time']:f[c]=pd.to_datetime(f[c],utc=True)
                f['archive_month']=month
                frames.append(f);groups.append(i)
            opened.append({'member':name,'row_groups':groups,'total_row_groups':pf.num_row_groups})
            record_access(str(RAW)+'!'+name,'PRE_MAY_RAW_JOB_GROUPS',groups=groups,total_groups=pf.num_row_groups)
    jobs=pd.concat(frames,ignore_index=True)
    jobs['requested_seconds']=jobs.wallclock_req.dt.total_seconds()
    jobs['runtime_s']=(jobs.end_time-jobs.start_time).dt.total_seconds()
    jobs['queue_s']=(jobs.start_time-jobs.submit_time).dt.total_seconds()
    valid=jobs.state_simple.eq('COMPLETED')&~jobs.partition.str.contains('-stdby',regex=False)&jobs.submit_time.notna()&jobs.start_time.notna()&jobs.end_time.notna()&jobs.runtime_s.gt(0)&jobs.queue_s.ge(0)&jobs.gpus_requested.gt(0)
    jobs=jobs.loc[valid].sort_values(['id','submit_time','start_time','end_time']).drop_duplicates('id').copy()
    jobs['flexible']=jobs.runtime_s.ge(1800)&jobs.queue_s.ge(900)
    jobs['fixed']=~jobs.flexible
    jobs['GPU_h']=jobs.gpus_requested*jobs.runtime_s/3600
    jobs['submit_bin']=jobs.submit_time.dt.floor('5min')
    # Lag-1 of an arrival mark at the following origin is late until actual completion.
    witness=jobs.loc[jobs.flexible & (jobs.end_time>jobs.submit_bin+pd.Timedelta(minutes=5))].copy()
    witness['lag1_origin']=witness.submit_bin+pd.Timedelta(minutes=5)
    witness['availability_delay_hours']=(witness.end_time-witness.lag1_origin).dt.total_seconds()/3600
    # Independent identity audit at preregistered fold-day noon origins on this raw cohort.
    overlap=[]
    for origin in pd.date_range('2024-09-01T12:00:00Z','2025-03-31T12:00:00Z',freq='D'):
        known=set(jobs.loc[jobs.submit_time.le(origin)&jobs.end_time.gt(origin),'id'])
        future=set(jobs.loc[jobs.flexible&jobs.submit_time.ge(origin+pd.Timedelta(minutes=5))&jobs.submit_time.lt(origin+pd.Timedelta(minutes=245)),'id'])
        overlap.append({'forecast_origin':origin,'known_jobs':len(known),'future_flexible_jobs':len(future),'overlap':len(known&future)})
    dump('job_identity_and_availability_evidence.json',{'source':RAW,'source_SHA256':digest(RAW),'raw_columns':cols,'opened_members':opened,'skipped_cross_May_groups':skipped,'safe_job_count':len(jobs),'F30_flexible_count':int(jobs.flexible.sum()),'F30_fixed_count':int(jobs.fixed.sum()),'unknown_valid_clean_cohort':0,'fixed_flexible_overlap':int((jobs.fixed&jobs.flexible).sum()),'late_lag1_mark_jobs':len(witness),'late_lag1_GPU_h':witness.GPU_h.sum(),'late_mark_delay_hours_P50_P95':witness.availability_delay_hours.quantile([.5,.95]).to_dict(),'examples':witness[['id','submit_time','start_time','end_time','lag1_origin','GPU_h','availability_delay_hours']].head(10).to_dict('records'),'known_future_checks':overlap,'known_future_overlap_total':sum(x['overlap'] for x in overlap),'limitations':['Completion-filtered cohort is itself retrospective. Excluded raw row groups with endpoint maxima in May or later; this job audit is not a census of every primary-data job.','May-coded scientific source snippets encountered during initial search are separately reported. No raw May endpoint group is decoded here.']})
    # Raw job shift complements primary complete-grid feature shift; preserve coverage warning.
    summary=[]
    for label,mask in [('TRAIN_2024',jobs.submit_time.dt.year.eq(2024)),('PREMAY_2025_JFM',jobs.submit_time.ge('2025-01-01'))]:
        f=jobs.loc[mask]
        rec={'cohort':label,'N':len(f),'GPU_per_job':f.gpus_requested.quantile([.05,.5,.95]).to_dict(),'requested_seconds':f.requested_seconds.quantile([.05,.5,.95]).to_dict(),'hardware':'Kestrel H100 by partition, unchanged hardware family','QoS':f.qos.fillna('MISSING').value_counts(normalize=True).to_dict(),'partition':f.partition.value_counts(normalize=True).to_dict()}
        summary.append(rec)
    tr=jobs.loc[jobs.submit_time.dt.year.eq(2024)];te=jobs.loc[jobs.submit_time.ge('2025-01-01')]
    distances={c:wasserstein_distance(tr[c].dropna(),te[c].dropna()) for c in ['gpus_requested','requested_seconds']}
    for c in ['qos','partition']:
        a=tr[c].fillna('MISSING').value_counts(normalize=True);b=te[c].fillna('MISSING').value_counts(normalize=True)
        distances[c+'_TV']=float((a.subtract(b,fill_value=0).abs().sum())/2)
    dump('raw_job_temporal_shift.json',{'summary':summary,'distances':distances,'coverage':'descriptive safe-endpoint subset only; excluded groups mean no unbiased population-shift claim'})
    jobs[['id','submit_time','start_time','end_time','gpus_requested','runtime_s','queue_s','requested_seconds','flexible','fixed','GPU_h']].to_parquet(OUT/'safe_preMay_job_witnesses.parquet',index=False)
    print(f'safe jobs={len(jobs)} flexible={jobs.flexible.sum()} lag1 future-mark jobs={len(witness)} skipped raw groups={len(skipped)}',flush=True)

if __name__=='__main__':main()

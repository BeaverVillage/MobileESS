"""Read raw accounting partitions once; publish exact offline job/issue membership."""
from common import *
import zipfile,pyarrow.parquet as pq

def main():
 require(not (ROOT/'PREPARATION_COMPLETE.json').exists(),'PREPARED_IMMUTABLE')
 require(sha(RAW)=='3a90f9ac40991712f8718c686fa7b05d7a303a44a87ed1a8f21b403c11efd26f','RAW_HASH')
 parts=[];inventory=[]
 cols=['id','submit_time','start_time','end_time','wallclock_req','gpus_requested','nodes_req','processors_req','memory_req','partition','qos','user_hash','account_hash']
 with zipfile.ZipFile(RAW) as z:
  for name in sorted(n for n in z.namelist() if re.search(r'year=\d{4}/month=\d+/.*\.parquet$',n)):
   with z.open(name) as stream:r=pq.read_table(stream,columns=cols,use_threads=False).to_pandas()
   n=len(r);r=r[pd.to_numeric(r.gpus_requested,errors='coerce').gt(0)&pd.to_datetime(r.submit_time,utc=True).lt(pd.Timestamp('2025-06-01',tz='UTC'))].copy()
   if len(r):
    f=normalize(r)
    for c in ['start_time','end_time']:f[c]=pd.to_datetime(r[c],utc=True).astype('datetime64[ns, UTC]')
    f['submit_time']=f.submit_time.astype('datetime64[ns, UTC]');f['runtime_seconds']=(f.end_time-f.start_time).dt.total_seconds()
    f['user']=r.user_hash;f['account']=r.account_hash
    parts.append(f)
   inventory.append(dict(member=name,raw_N=n,GPU_preJune_N=len(r)));print('RAW',name,n,len(r),flush=True)
 f=pd.concat(parts,ignore_index=True).sort_values('job_id',kind='stable').reset_index(drop=True)
 require(f.job_id.is_unique and np.isfinite(f.num_gpus_req).all(),'DUPLICATE_OR_INVALID_GPU')
 f['row_id']=np.arange(len(f),dtype=np.int32)
 # Complete-case eligibility applies only to training and identifiable outcomes;
 # unresolved submitted GPU Jobs stay in the issue population and audit.
 f['label_valid']=f.start_time.notna()&f.end_time.notna()&f.runtime_seconds.gt(0)&f.start_time.ge(f.submit_time)
 (ROOT/'cache').mkdir(exist_ok=True);f.to_parquet(ROOT/'cache/JOBS.parquet',index=False)
 f[['row_id','job_id','submit_time','start_time','end_time','num_gpus_req','label_valid']].to_parquet(ROOT/'JOB_MEMBERSHIP.parquet',index=False)
 old=Path('C:/codex_mobileess_workspace/MobileESS_v40s5_uncertainty_aware_direct_runtime/dayahead/artifacts/v40s4_request_state_proxy_runtime_risk/V40S4_PENDING_ISSUE_PANEL.parquet')
 oldf=pd.read_parquet(old);issues=oldf[['issue_time','role']].drop_duplicates().sort_values('issue_time')
 # Preserve the complete PR31 calendar and role assignments. May is exposed history.
 may=pd.DataFrame(dict(issue_time=pd.date_range('2025-04-30T08:00Z','2025-05-30T08:00Z'),role='MAY_HISTORICAL'))
 issues=pd.concat([issues,may],ignore_index=True);issues.to_csv(ROOT/'ISSUES.csv',index=False)
 panel=[];counts=[]
 for t,role in issues.itertuples(index=False,name=None):
  live=f.submit_time.le(t)&(f.end_time.gt(t)|f.end_time.isna());p=f[live].copy()
  p['state']=np.where(p.start_time.le(t),'RUNNING','PENDING');p['elapsed_seconds']=np.where(p.state.eq('RUNNING'),(t-p.start_time).dt.total_seconds(),0.)
  p['issue_time']=t;p['role']=role;p['job_issue_id']=p.job_id+'@'+t.isoformat();p['actual_seconds']=np.where(p.state.eq('RUNNING'),(p.end_time-t).dt.total_seconds(),p.runtime_seconds)
  p['actual_seconds']=p.actual_seconds.where(p.label_valid);panel.append(p)
  counts.append(dict(issue_time=t,role=role,N=len(p),pending=int(p.state.eq('PENDING').sum()),running=int(p.state.eq('RUNNING').sum()),unresolved=int(p.actual_seconds.isna().sum())))
 panel=pd.concat(panel,ignore_index=True);panel.to_parquet(ROOT/'cache/PANEL.parquet',index=False)
 panel[['job_issue_id','job_id','row_id','issue_time','role','state','elapsed_seconds','label_valid']].to_parquet(ROOT/'ISSUE_MEMBERSHIP.parquet',index=False)
 oldcols=oldf[['job_issue_uid','job_id','issue_time','role','reference_safe_sec']].copy();oldcols['job_issue_id']=oldcols.job_id.astype(str)+'@'+pd.to_datetime(oldcols.issue_time,utc=True).map(lambda t:t.isoformat())
 oldcols.to_parquet(ROOT/'PR31_REFERENCE_PANEL.parquet',index=False)
 dump('PREPARATION_COMPLETE.json',dict(time=now(),archive_sha256=sha(RAW),jobs_sha256=sha(ROOT/'cache/JOBS.parquet'),panel_sha256=sha(ROOT/'cache/PANEL.parquet'),
  raw_inventory=inventory,GPU_preJune_jobs=len(f),issues=counts,training_population='positive-GPU common cohort; same for every temporal/model arm',
  legacy_population_bridge='PR27 exact production replay retains all-job history; GPU-only MoE study arm is explicitly not that production model',
  all_requested_predictions_retained=True,no_feature_uses_final_label=True,request_version_provenance='UNVERIFIED',
  raw_issue_state_reconstruction='event-time only; no historical scheduler snapshot/change log certification'))

if __name__=='__main__':main()

"""Archive-conditional scheduler request/state proxy explicitly authorized by user.

No historical census/immutability/zero-change claim. Future completion values
are discarded before producing any model-facing feature, label or weight.
"""
import hashlib,json,zipfile
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from prepare import ROOT,BASE,RAW,JOBS,sha,need,save
FEATURES=['requested_seconds','num_nodes_req','num_cores_req','num_gpus_req','requested_memory_mib','partition','qos','user','account']
LANDMARKS=np.array([1800.,5400.,10800.,21600.,43200.])

def asof_rows(jobs,issue):
    t=pd.Timestamp(issue)
    f=jobs[jobs.submit_time.le(t)&jobs.start_time.notna()&jobs.start_time.ge(jobs.submit_time)&jobs.start_time.lt(t)].copy()
    # Only the Boolean occurrence of a completion before the cutoff is consulted.
    ended=f.end_time.lt(t)
    observed_end=f.end_time.where(ended)
    observation_time=observed_end.fillna(t)
    elapsed_observed=(observation_time-f.start_time).dt.total_seconds()
    landmark=LANDMARKS[pd.util.hash_pandas_object(f.job_id,index=False).to_numpy()%len(LANDMARKS)]
    safe=f[['row_id','job_id','submit_time','start_time',*FEATURES]].copy()
    safe['observed_end']=observed_end;safe['observation_time']=observation_time
    safe['elapsed_seconds']=landmark;safe['observed_total_seconds']=elapsed_observed
    safe['label_lower']=elapsed_observed-landmark;safe['label_upper']=np.where(ended,safe.label_lower,np.inf)
    safe['right_censored']=~ended
    safe=safe[(safe.label_lower>0)&safe.observation_time.ge(t-pd.Timedelta(days=180))]
    safe=safe.sort_values(['observation_time','job_id'],kind='stable')
    need(safe.observation_time.le(t).all(),'OBSERVATION_AFTER_ISSUE')
    need(safe.loc[~safe.right_censored,'observed_end'].lt(t).all(),'EXACT_LABEL_NOT_MATURE')
    return safe

def weight(frame,issue):
    recency=np.exp(-np.log(2)/14*(pd.Timestamp(issue)-frame.observation_time).dt.total_seconds().to_numpy()/86400)
    tail=1.+(frame.observed_total_seconds.to_numpy()>14400)
    factor=frame.num_gpus_req.to_numpy()*tail
    normalizer=np.sum(recency*factor)/np.sum(recency)
    return recency*factor/normalizer,float(normalizer)

def authorize_proxy():
    need(not (ROOT/'PROXY_AUTHORIZATION.json').exists(),'ALREADY_AUTHORIZED')
    j=pd.read_parquet(JOBS);found=[];all_gpu=0;all_gpu_null=0;states={};schemas=[]
    with zipfile.ZipFile(RAW) as z:
        for name in sorted(n for n in z.namelist() if n.endswith('.parquet')):
            with z.open(name) as stream:
                f=pq.read_table(stream,columns=['id','submit_time','start_time','end_time','gpus_requested','state_simple'],use_threads=False).to_pandas()
            f=f[pd.to_numeric(f.gpus_requested,errors='coerce').gt(0)]
            all_gpu+=len(f);all_gpu_null+=int(f.end_time.isna().sum())
            for k,v in f.state_simple.value_counts(dropna=False).items():states[str(k)]=states.get(str(k),0)+int(v)
            relevant=f[pd.to_datetime(f.submit_time,utc=True).lt(pd.Timestamp('2025-06-01',tz='UTC'))]
            found.extend(relevant.id.astype(str).tolist())
    need(len(found)==len(j) and set(found)==set(j.job_id),'CACHE_DROPS_RAW_GPU_ROWS')
    save('PROXY_AUTHORIZATION.json',dict(time=pd.Timestamp.now(tz='UTC').isoformat(),R3_status='AUTHORIZED_ARCHIVE_CONDITIONAL_PROXY',
        authority='explicit user override: inherit V40S4 D1_SCHEDULER_REQUEST_STATE_PROXY_V1; uncertified request/history is permitted as assumption-based proxy',
        earlier_assessment_sha256=sha(ROOT/'CENSORING_AUTHORITY.json'),scope='Observed final archive cohort conditional only; no claim of complete actual historical census or outcome-independent inclusion',
        raw_GPU_all_dates=all_gpu,raw_GPU_all_dates_missing_end=all_gpu_null,raw_GPU_all_dates_states=states,
        raw_GPU_preJune_membership_exact=True,relevant_GPU_jobs=len(j),raw_GPU_ID_digest=hashlib.sha256(('\n'.join(sorted(found))+'\n').encode()).hexdigest(),
        retained_missing_end_before_any_filter=True,filter='Only positiveGPU and submit<2025June1 cache bound; all issue times earlier, therefore no outcome-based population exclusion',
        censoring='known submit/start<=issue; end<issue exact only; otherwise lower=issue-start-landmark and upper=infinity; no futurecompletionvalue in labels/features/weights',
        provenance='UNVERIFIED/UNOBSERVED',historical_exactness_claimed=False,request_immutability_claimed=False,zero_change_claimed=False,
        historical_census_completeness='UNVERIFIED',hpc_07_authority='code/model authority only, never scheduler snapshot',
        production_readiness=False))
    print('R3 AUTHORIZED_ARCHIVE_CONDITIONAL_PROXY; complete raw relevant GPU membership verified',flush=True)

if __name__=='__main__':authorize_proxy()

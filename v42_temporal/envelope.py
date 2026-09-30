"""Completed submission-hour cohorts, supported pointwise TRAIN quantiles."""
import numpy as np
from v42_final.workload import execution_lag_kernel
from .common import *

def construct(frame, cutoff):
    require((frame.submit_time<cutoff).all() and (frame.start_time<cutoff).all(),'TRAIN_ONLY_ENVELOPE')
    f=frame.copy();f['hour']=f.submit_time.dt.floor('h')
    records=[];curves=[];supports=[];excluded=0
    for hour,g in f.groupby('hour',sort=True):
        if not (g.event & g.end_time.notna() & (g.end_time<cutoff)).all():
            excluded+=1;continue
        duration=(g.end_time-g.start_time).dt.total_seconds().to_numpy()
        if np.sum(duration*g.num_gpus_req.to_numpy())<=0:continue
        anchor=np.full(len(g),hour.timestamp())
        k,mass=execution_lag_kernel(anchor,g.start_time.astype('int64').to_numpy()/1e9,
                                   g.end_time.astype('int64').to_numpy()/1e9,g.num_gpus_req.to_numpy())
        cdf=np.minimum(1.,np.cumsum(k));cdf[-1]=1.
        support=int((cutoff-hour).total_seconds()//900)-1
        require(len(cdf)-1<=support,'COHORT_COMPLETION_OBSERVED')
        curves.append(cdf);supports.append(support)
        points=sorted(set([0,support]+np.flatnonzero(np.diff(np.r_[0.,cdf])>1e-14).tolist()))
        for lag in points:
            records.append(dict(submission_hour=hour.isoformat(),jobs=len(g),total_observed_GPUh=float(mass.sum()),
                lag_slot=lag,cumulative_fraction=float(cdf[min(lag,len(cdf)-1)]),supported_through_lag=support))
    require(bool(curves),'NO_COMPLETED_TRAIN_COHORTS')
    # Past the latest observed execution completion no new distributional
    # information exists; completed cohorts have observed F=1 plateaus only.
    last=max(len(c)-1 for c in curves)
    matrix=np.full((len(curves),last+1),np.nan)
    for i,(c,s) in enumerate(zip(curves,supports)):
        end=min(s,last)+1;matrix[i,:end]=1.;matrix[i,:min(len(c),end)]=c[:end]
    q=np.nanquantile(matrix,[.1,.5,.9],axis=0,method='linear')
    corrected=np.maximum.accumulate(q,axis=1)
    require(np.all(corrected[0]<=corrected[2]) and np.all((corrected>=0)&(corrected<=1)),'ENVELOPE_ORDER')
    return records,corrected,np.sum(np.isfinite(matrix),axis=0),dict(completed_cohorts=len(curves),excluded_incomplete_cohorts=excluded,
        monotonic_corrected_values=int(np.count_nonzero(corrected!=q)),last_supported_lag=last,
        minimum_cohorts_at_supported_lag=int(np.sum(np.isfinite(matrix),axis=0).min()))

def main():
    require(not (OUT/'CC4_SERVICE_TIMING_ENVELOPE_AUDIT.json').exists(),'ENVELOPE_ALREADY_FROZEN')
    f,cutoff=train_frame();records,q,n,audit=construct(f,cutoff)
    k=pd.read_csv(OLD/'CC4_EXECUTION_LAG_KERNEL.csv').kappa.to_numpy();ref=np.cumsum(k)
    csv('CC4_SERVICE_COHORT_CDF.csv',records)
    csv('CC4_SERVICE_TIMING_ENVELOPE.csv',[dict(lag_slot=l,lag_end_seconds=(l+1)*900,historical_submission_cohorts=int(n[l]),
        Q10=float(q[0,l]),median=float(q[1,l]),Q90=float(q[2,l]),reference_kernel_CDF=float(ref[min(l,len(ref)-1)])) for l in range(len(n))])
    dump('CC4_SERVICE_TIMING_ENVELOPE_AUDIT.json',dict(PASS=True,**audit,TRAIN_source=rec(TRAIN),cutoff=cutoff.isoformat(),
        preregistration=rec(OUT/'PREREGISTRATION.json'),May_outcomes_used=False,VALID_used=False,quantiles=[.1,.9],
        minimum_support_policy='At least one completed cohort; N disclosed per lag, no tuned threshold',
        CDF_encoding='Sparse exact change points, previous-value interpolation up to supported_through_lag only',
        reference_kernel=rec(OLD/'CC4_EXECUTION_LAG_KERNEL.csv'),reference_kernel_mass=float(k.sum()),
        alignment='Envelope anchored at submission-hour start. Frozen reference retains per-job-submit lags, anchored at forecast-hour start. No reference re-estimation.',
        unsupported_tail='No x variables beyond last supported lag; all unserved mass remains carryout'))
    print(audit)

if __name__=='__main__':main()

"""One approved OOF calibration (fold1-4), then one sealed fold5 report."""
from .common import *
from .reserve import survival,calibrate
from scipy.signal import fftconvolve


def load_fold(i):
    from .oof_causality import audit_fold
    # On a fresh authorized materialization, verify per-job submission-time
    # map availability BEFORE deriving any scale or holdout metric.
    audit_fold(i,read(V10/'TEMPORAL_FOLD_CONTRACT.json')['folds'][i-1])
    paths=[V9/f'.local/fold{i}/VALID.parquet',V10/f'.local/fold{i}/T3_ISOTONIC_ROLLING14_calibrated.npz']
    expected={str(Path(r['path']).resolve()):r['sha256'] for r in read(PR95/'CROSS_VERSION_SOURCE_MANIFEST.json')['files']}
    for p in paths:require(sha(p)==expected[str(p.resolve())],'OOF_SOURCE_IDENTITY')
    f=pd.read_parquet(paths[0],columns=['job_id','submit_time','start_time','end_time','event','censored','runtime_seconds','num_gpus_req'])
    with np.load(paths[1],allow_pickle=False) as z:q=z['quantiles'][:,0].copy()
    require(len(q)==len(f),'OOF_ORDER');f['q50']=q
    return f,[rec(p) for p in paths]


def concurrent(f,contract,kernel):
    begin=pd.Timestamp(contract['VALID_submit_from']);end=pd.Timestamp(contract['VALID_end'])
    n=int((end-begin).total_seconds()/900);impulse=np.zeros(n);delta=np.zeros(n+1)
    for r in f.itertuples():
        if pd.isna(r.start_time):continue
        nominal=r.start_time+pd.Timedelta(seconds=r.q50)
        a=int(np.ceil((nominal-begin).total_seconds()/900))
        if a<0 or a>=n:continue
        impulse[a]+=float(r.num_gpus_req)
        # A right-censored job is observed RUNNING until the fold cutoff; its
        # future completion is neither read nor manufactured.
        stop=min(r.end_time,end) if pd.notna(r.end_time) else end
        b=min(n,int(np.ceil((stop-begin).total_seconds()/900)))
        if b>a:delta[a]+=float(r.num_gpus_req);delta[b]-=float(r.num_gpus_req)
    observed=np.cumsum(delta[:-1]);exposure=np.maximum(fftconvolve(impulse,kernel)[:n],0.)
    exposure[exposure<1e-10]=0. # FFT numerical roundoff, not risk-model clipping
    return pd.DataFrame(dict(fold=contract['fold'],time=pd.date_range(begin,periods=n,freq='15min'),
        observed_overrun_GPU=observed,predicted_exposure_GPU=exposure))


def summary(g,gamma):
    o=g.observed_overrun_GPU.to_numpy();h=g.predicted_exposure_GPU.to_numpy();r=gamma*h
    return dict(N_slots=len(g),coverage=float((o<=r+1e-9).mean()),positive_demand_slots=int((o>0).sum()),
        positive_demand_coverage=float((o[o>0]<=r[o>0]+1e-9).mean()) if (o>0).any() else None,
        uncovered_GPUh=float(np.maximum(o-r,0).sum()*.25),maximum_uncovered_GPU=float(np.maximum(o-r,0).max()),
        reserve_GPUh=float(r.sum()*.25),actual_overrun_GPUh=float(o.sum()*.25),
        reserve_over_overrun_ratio=float(r.sum()/o.sum()) if o.sum()>0 else None,
        mean_reserve_GPU=float(r.mean()),maximum_reserve_GPU=float(r.max()),
        zero_exposure_positive_overrun_slots=int(((h==0)&(o>0)).sum()))


def main():
    require(not (OUT/'RUNTIME_RESERVE_CALIBRATION.json').exists(),'RESERVE_ALREADY_FROZEN_NO_RETUNING')
    contract=read(V10/'TEMPORAL_FOLD_CONTRACT.json');frames=[];sources=[];ys=[];qs=[]
    dump('RUNTIME_RESERVE_OOF_PREREGISTRATION.json',dict(authority='Explicit user clarification',
        supersedes_original_reserve_role_requirement=True,original_Runtime_folds_unchanged=True,
        kernel_and_gamma_folds=[1,2,3,4],validation_holdout_fold=5,gamma_refit_after_fold5=False,
        kernel='Pooled exact completed OOF residual survival, full observed lag support plus minimum96 slots',
        right_censored_policy='Do not use unobserved duration in survival. Include observed overrun occupancy until each fold cutoff in system concurrency.',
        sample_scope='Each fold submission cohort evaluated on that fold interval; no invented historical sites or unrelated carry-in jobs',
        coverage_scope='OOF submission-cohort system-wide control-boundary concurrency; not a full-cluster reliability guarantee',
        grid='UTC 900-second boundaries',nominal_end_mapping='ceil(actual historical start + stored Q50) to control boundary',
        scale='Single empirical Q90 O/max(H,1e-12), higher order statistic, no search',
        labels_preMay_only=True,March31_snapshot_retrospective_inference=False,May_gamma='identical fold1-4 frozen scale'))
    for i in range(1,5):
        f,s=load_fold(i);frames.append(f);sources+=s;m=f.event.to_numpy(bool)
        ys.extend(f.loc[m,'runtime_seconds'].to_numpy());qs.extend(f.loc[m,'q50'].to_numpy())
    y=np.array(ys);q=np.array(qs);max_lag=max(96,int(np.ceil(np.maximum(y-q,0).max()/900))+1)
    kernel=survival(y,q,max_lag)
    csv('RUNTIME_OVERRUN_SURVIVAL_KERNEL.csv',[dict(lag_slot=i,lag_seconds=i*900,survival=float(v),exact_sample_N=len(y),
        exceedance_N=int(np.count_nonzero(y>q+i*900))) for i,v in enumerate(kernel)])
    cal=pd.concat([concurrent(f,contract['folds'][i],kernel) for i,f in enumerate(frames)],ignore_index=True)
    cutoff=pd.Timestamp('2025-03-01T00:00:00Z')
    try:
        fit=calibrate(cal.observed_overrun_GPU,cal.predicted_exposure_GPU,role='CAL',event_times=cal.time,
            prediction_available_times=cal.time,observation_cutoff=cutoff)
    except ValueError as error:
        dump('RUNTIME_RESERVE_CALIBRATION.json',dict(status='FAIL_CLOSED',reason=str(error),gamma_90=None,sources=sources))
        raise
    gamma=fit['gamma_90'];LOCAL.mkdir(exist_ok=True)
    calpath=LOCAL/'OOF_FOLD1_4_RUNTIME_RESERVE_REPLAY.parquet';cal.to_parquet(calpath,index=False)
    freeze=dict(status='FROZEN_FOLD1_4_OOF',frozen_at=now(),**fit,calibration_folds=[1,2,3,4],
        exact_survival_samples=len(y),kernel_slots=len(kernel),maximum_positive_supported_lag=int(np.flatnonzero(kernel>0)[-1]),
        zero_support_tail_start=int(np.flatnonzero(kernel==0)[0]) if (kernel==0).any() else None,
        censored_rows=sum(int(f.censored.sum()) for f in frames),kernel=rec(OUT/'RUNTIME_OVERRUN_SURVIVAL_KERNEL.csv'),
        source_files=sources,calibration_replay=rec(calpath),calibration_summary=summary(cal,gamma),
        holdout_read_for_reserve_before_gamma_freeze=False,May_labels_read=False,Runtime_fit_calls=0,
        site_mapping='NONE_SYSTEM_WIDE',Planning_site_local_application='Same gamma times optimizer-selected local job exposure',
        Actual_duplicate_reserve=False)
    dump('RUNTIME_RESERVE_CALIBRATION.json',freeze);frozen_sha=sha(OUT/'RUNTIME_RESERVE_CALIBRATION.json')
    # Fold5 labels are accessed for reserve validation only AFTER gamma is sealed.
    f,s=load_fold(5);valid=concurrent(f,contract['folds'][4],kernel)
    vpath=LOCAL/'OOF_FOLD5_RUNTIME_RESERVE_VALIDATION.parquet';valid.to_parquet(vpath,index=False)
    rows=[dict(role='CALIBRATION',fold=i,**summary(g,gamma)) for i,g in cal.groupby('fold')]
    rows.append(dict(role='CALIBRATION',fold='POOLED',**summary(cal,gamma)))
    rows.append(dict(role='VALIDATION_ONCE_NO_RETUNING',fold=5,**summary(valid,gamma)))
    csv('RUNTIME_RESERVE_VALIDATION.csv',rows)
    temporal=[]
    for role,g in [('CALIBRATION',cal),('VALIDATION_ONCE',valid)]:
        for day,z in g.groupby(g.time.dt.date):temporal.append(dict(role=role,day=str(day),**summary(z,gamma)))
    csv('RUNTIME_RESERVE_TEMPORAL_VALIDATION.csv',temporal)
    dump('RUNTIME_RESERVE_HOLDOUT_RECEIPT.json',dict(PASS=True,validation_executions=1,gamma_90=gamma,
        calibration_sha_before=frozen_sha,calibration_sha_after=sha(OUT/'RUNTIME_RESERVE_CALIBRATION.json'),
        gamma_changed=False,validation_summary=summary(valid,gamma),validation_sources=s,validation_replay=rec(vpath),
        prior_intrinsic_ML_metric_exposure=True,untouched_means_not_used_for_reserve_parameter_estimation=True))
    require(frozen_sha==sha(OUT/'RUNTIME_RESERVE_CALIBRATION.json'),'GAMMA_CHANGED_AFTER_HOLDOUT')
    print(json.dumps(dict(gamma_90=gamma,calibration=summary(cal,gamma),holdout=summary(valid,gamma)),indent=2))


if __name__=='__main__':main()

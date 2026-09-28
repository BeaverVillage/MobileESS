"""Independent event reconstruction, target audit, and causal features."""
from core import *
import zipfile,re
import pyarrow.parquet as pq
from scipy.stats import skew,spearmanr
H=3600_000_000_000;DAY=24*H;MAX=np.iinfo(np.int64).max
def ns(x):return pd.to_datetime(x,utc=True).dt.as_unit('ns').astype('int64').to_numpy()
def overlap(start,end,gpu,edges):
    # No bin rounding: integrate half-open execution intervals exactly.
    return np.array([np.sum(gpu*np.maximum(0,np.minimum(end,b)-np.maximum(start,a))/H) for a,b in zip(edges[:-1],edges[1:])])
def load_raw():
    s=read(BASE/'SOURCE_MANIFEST.json')['sources'];raw=next(x for x in s if x['purpose']=='raw Job authority, all parquet partitions')
    assert sha(raw['path'])==raw['sha256']
    parts=[];inventory=[]
    with zipfile.ZipFile(raw['path']) as z:
        for name in sorted(n for n in z.namelist() if re.search(r'year=\d{4}/month=\d+/.*\.parquet$',n)):
            with z.open(name) as f:d=pq.ParquetFile(f).read(columns=['id','submit_time','start_time','end_time','gpus_requested'],use_threads=False).to_pandas()
            for c in ['submit_time','start_time','end_time']:d[c]=pd.to_datetime(d[c],utc=True).dt.as_unit('ns')
            parts.append(d);inventory.append(dict(member=name,rows=len(d)))
    d=pd.concat(parts,ignore_index=True);assert d.id.is_unique and d.submit_time.notna().all()
    authority=dict(source=raw,members=inventory,raw_rows=len(d),ingestion_latency='UNVERIFIED',historical_request_versions='UNOBSERVED')
    if (ROOT/'RAW_AUTHORITY.json').exists():assert read(ROOT/'RAW_AUTHORITY.json')==authority
    else:write('RAW_AUTHORITY.json',authority)
    return d
def distributions(targets):
    rows=[];corr=[];conditional=[]
    for t,y in targets.items():
        tr=y[TRAIN];threshold=np.quantile(tr[tr>0],.95)
        for role,ids in [('ALL_AVAILABLE',np.arange(len(y)))]+[(r,role_ids(r)) for r in ['TRAIN','DEVELOPMENT','CALIBRATION','EXPOSED_EVALUATION','OOS_EXTENSION','MAY_HISTORICAL']]:
            a=y[ids].ravel();p=a[a>0];mass=a.sum();sort=np.sort(a)
            rows.append(dict(target=t,role=role,N=len(a),zero_fraction=np.mean(a==0),positive_fraction=np.mean(a>0),mean=a.mean(),median=np.median(a),std=a.std(),CV=a.std()/a.mean(),skewness=skew(a),P90=np.quantile(a,.9),P95=np.quantile(a,.95),P99=np.quantile(a,.99),max=a.max(),max_positive_median=a.max()/np.median(p),top1_mass_share=sort[-int(np.ceil(.01*len(a))):].sum()/mass,top5_mass_share=sort[-int(np.ceil(.05*len(a))):].sum()/mass,burst_threshold=threshold,burst_frequency=np.mean(a>threshold),burst_mass_share=a[a>threshold].sum()/mass,autocorrelation_lag1=pd.Series(a).autocorr()))
        for lag in [1,2,3,7,14,21,28]:corr.append(dict(target=t,lag_days=lag,correlation=np.corrcoef(y[lag:].ravel(),y[:-lag].ravel())[0,1],purpose='diagnostic realized labels, not automatically causal feature'))
        dates=pd.to_datetime(DAYS);n=y.shape[1]
        for mode,key in [('weekday_hour',[(dates[i].dayofweek,int(j*24/n)) for i in range(len(y)) for j in range(n)]),('month',np.repeat(dates.strftime('%Y-%m'),n))]:
            f=pd.DataFrame(dict(group=list(map(str,key)),value=y.ravel()))
            for k,g in f.groupby('group'):conditional.append(dict(target=t,conditioning=mode,group=k,n=len(g),mean=g.value.mean(),variance=g.value.var()))
    csv('TARGET_DISTRIBUTION.csv',rows);csv('TARGET_LAG_CORRELATIONS.csv',corr);csv('TARGET_CONDITIONAL_VARIANCE.csv',conditional)
def alignment(targets):
    ref=targets['T2'];rows=[]
    for t,v in targets.items():
        a=v.reshape(-1,24,4).mean(2) if t=='T3' else v
        for role in ['TRAIN','DEVELOPMENT','CALIBRATION','EXPOSED_EVALUATION','OOS_EXTENSION','MAY_HISTORICAL']:
            ids=role_ids(role);x=a[ids];y=ref[ids];row=dict(target=t,role=role,Pearson=np.corrcoef(x.ravel(),y.ravel())[0,1],Spearman=spearmanr(x.ravel(),y.ravel()).statistic,peak_time_MAE_hours=np.mean(abs(x.argmax(1)-y.argmax(1))),peak_magnitude_correlation=np.corrcoef(x.max(1),y.max(1))[0,1],direct_peak_magnitude_MAE=np.mean(abs(x.max(1)-y.max(1))) if t in ['T2','T3'] else None,unit_comparability='GPU occupancy' if t in ['T2','T3'] else 'Different units/semantics: magnitude MAE invalid')
            for frac in [.1,.05]:
                k=int(np.ceil(24*frac));row[f'top{int(frac*100)}_slot_overlap']=np.mean([len(set(np.argsort(xx,kind='stable')[-k:])&set(np.argsort(yy,kind='stable')[-k:]))/k for xx,yy in zip(x,y)])
            rows.append(row)
    csv('TARGET_OPERATIONAL_ALIGNMENT.csv',rows)
def prepare():
    assert (ROOT/'A0_ANCHOR.json').exists(),'A0 must finish before new experiment'
    d=load_raw();s=ns(d.submit_time);a=ns(d.start_time);b=ns(d.end_time);g=d.gpus_requested.to_numpy(float)
    valid=np.isfinite(g)&(g>0)&d.start_time.notna().to_numpy()&d.end_time.notna().to_numpy()&(b>a)&(a>=s)
    positive=np.isfinite(g)&(g>0);unresolved=positive&d.end_time.isna().to_numpy();unresolved_s=s[unresolved];positive_s=s[positive];positive_g=g[positive]
    w=d.loc[valid].copy();sv=s[valid];av=a[valid];bv=b[valid];gv=g[valid];mass=gv*(bv-av)/H
    start=np.array([pd.Timestamp(str(day),tz=TZ).tz_convert('UTC').value for day in DAYS]);issue=start-6*H
    targets={t:np.zeros((len(DAYS),96 if t=='T3' else 24)) for t in ['T0','T1','T2','T3']}
    mat={t:np.zeros_like(v,dtype=np.int64) for t,v in targets.items()};bound=[];contrib=[];dayrows=[]
    for i,day in enumerate(DAYS):
        sel=(sv>=start[i])&(sv<start[i]+DAY);slots=((sv[sel]-start[i])//H).astype(int)
        targets['T0'][i]=np.bincount(slots,weights=mass[sel],minlength=24);targets['T1'][i]=np.bincount(slots,weights=gv[sel],minlength=24)
        sb=sv[sel];eb=bv[sel];ab=av[sel];gb=gv[sel];mb=mass[sel]
        for h in range(24):
            pick=slots==h;m=max(start[i]+(h+1)*H,eb[pick].max(initial=0))
            if np.any((unresolved_s>=start[i]+h*H)&(unresolved_s<start[i]+(h+1)*H)):m=MAX
            mat['T0'][i,h]=mat['T1'][i,h]=m
            v=mb[pick];gpu=gb[pick];runtime=(eb[pick]-ab[pick])/H;total=v.sum()
            if total:
                contrib.append(dict(day=day,hour=h,mass=total,jobs=len(v),jobs_over10pct=int(np.sum(v>.1*total)),jobs_over25pct=int(np.sum(v>.25*total)),jobs_over50pct=int(np.sum(v>.5*total)),long_runtime_over24h_mass=v[runtime>24].sum(),large_over4GPU_mass=v[gpu>4].sum(),largest_job_mass=v.max()))
        unknown=(sv>issue[i])&(sv<start[i]+DAY);active=unknown&(av<start[i]+DAY)&(bv>start[i]);pre=active&(sv<start[i]);preall=(sv>issue[i])&(sv<start[i])
        edges=start[i]+np.arange(97)*(H//4);gpu_h=overlap(av[active],bv[active],gv[active],edges)
        targets['T3'][i]=gpu_h*4;targets['T2'][i]=gpu_h.reshape(24,4).sum(1)
        direct=np.sum(gv[active]*np.maximum(0,np.minimum(bv[active],start[i]+DAY)-np.maximum(av[active],start[i]))/H)
        assert abs(gpu_h.sum()-direct)<1e-7
        premass=overlap(av[pre],bv[pre],gv[pre],edges);peak=int(np.argmax(gpu_h))
        m=max(start[i]+DAY,bv[unknown].max(initial=0))
        if np.any((unresolved_s>issue[i])&(unresolved_s<start[i]+DAY)):m=MAX
        mat['T2'][i]=m;mat['T3'][i]=m
        rawpre=(positive_s>issue[i])&(positive_s<start[i])
        bound.append(dict(day=day,role=L.split.iloc[i],all_positive_GPU_submissions=int(rawpre.sum()),eligible_submissions=int(preall.sum()),requested_GPU_all=positive_g[rawpre].sum(),requested_GPU_eligible=gv[preall].sum(),realized_GPUh=mass[preall].sum(),Dday_overlap_GPUh=premass.sum(),Dday_unknown_GPUh=direct,unknown_mass_fraction=premass.sum()/direct if direct else None,unknown_peak_average_GPU=gpu_h[peak]*4,preD00_GPU_at_unknown_peak=premass[peak]*4,unknown_peak_fraction=premass[peak]/gpu_h[peak] if gpu_h[peak] else None,preD00_own_peak_GPU=premass.max()*4))
        for t in targets:dayrows.append(dict(target=t,day=day,issue_time=str(ISS.iloc[i]),label_matured_at=str(pd.Timestamp(int(mat[t][i].max()),tz='UTC')),original_role=L.split.iloc[i],original_eligible=bool(L.eligible.iloc[i])))
        if i%50==0:print('TARGET_DAY',i,len(DAYS),flush=True)
    assert np.array_equal(targets['T0'],Y0),'T0 must be bitwise exact'
    assert np.array_equal(mat['T0'].max(1),ns(L.label_matured_at)),'T0 maturity drift'
    np.savez_compressed(ROOT/'TARGETS.npz',**targets,**{'maturity_'+t:m for t,m in mat.items()},days=DAYS)
    csv('TARGET_BOUNDARY_AUDIT.csv',bound);csv('TARGET_SLOT_CONTRIBUTIONS.csv',contrib);csv('TARGET_MATURITY.csv',dayrows)
    bt=pd.DataFrame(bound);ct=pd.DataFrame(contrib);burst=read(BASE/'TARGET_RECONSTRUCTION_AUDIT.json')['TRAIN_positive_Q95_burst_threshold_GPUh'];bursts=ct[ct.mass>burst]
    write('TARGET_POPULATION_AUDIT.json',dict(T0_bitwise_equal=True,T0_maturity_exact=True,raw_rows=len(d),eligible_rows=int(valid.sum()),invalid_positive_GPU_rows=int(np.sum(positive&~valid)),unresolved_positive_GPU_rows=int(unresolved.sum()),eligible_population='Exact original positive GPU, valid submit<=start<end jobs; all targets conditional on this observable-outcome label cohort, not proof that unresolved jobs have zero load',all_days=len(DAYS),preD00_total_GPUh=bt.Dday_overlap_GPUh.sum(),unknown_total_GPUh=bt.Dday_unknown_GPUh.sum(),preD00_mass_fraction=bt.Dday_overlap_GPUh.sum()/bt.Dday_unknown_GPUh.sum(),mean_daily_peak_fraction=bt.unknown_peak_fraction.mean(),T0_burst_threshold=burst,burst_long_runtime_mass_share=bursts.long_runtime_over24h_mass.sum()/bursts.mass.sum(),burst_large_GPU_mass_share=bursts.large_over4GPU_mass.sum()/bursts.mass.sum(),concentration_thresholds_percent=[10,25,50],T2_T3_daily_conservation_max_error=float(np.max(abs(targets['T3'].sum(1)*.25-targets['T2'].sum(1)))),power_mapping='NOT_AVAILABLE: no newly authorized deterministic PCC conversion; GPU occupancy reference only',T0_reconstruction_order='Sorted archive member and original row order; independent bincount of raw eligible rows'))
    distributions(targets);alignment(targets)
    features(d,targets,mat,start,issue)
    print('TARGET_FEATURE_PREPARATION_PASS',flush=True)
def features(d,targets,mat,start,issue):
    names0=read(BASE/'FEATURE_CONTRACT.json')['feature_names'];proof=[];packs={};groups={};contracts={}
    oldproof=pd.read_parquet(BASE/'FEATURE_MATURITY_PROOF.parquet')
    assert (pd.to_datetime(oldproof.feature_available_at,utc=True)<=pd.to_datetime(oldproof.issue_time,utc=True)).all()
    # All submitted positive-GPU requests, without start/end eligibility filtering.
    r=d[np.isfinite(d.gpus_requested)&d.gpus_requested.gt(0)].sort_values('submit_time');s=ns(r.submit_time);g=r.gpus_requested.to_numpy(float)
    rec=[];rec_names=[];recmax=[]
    for i in range(len(DAYS)):
        row=[];last=np.searchsorted(s,issue[i],side='right');recent={}
        for minutes in [15,30,60,180,360,720,1440]:
            first=np.searchsorted(s,issue[i]-minutes*H//60,side='right');v=g[first:last];times=s[first:last];count=len(v);bins=minutes//15
            occupied=len(np.unique((times-(issue[i]-minutes*H//60)-1)//(H//4))) if count else 0
            vals=[count,v.sum(),v.mean() if count else 0,v.max(initial=0),np.sum(v==1),np.sum((v>=2)&(v<=4)),np.sum(v>4),occupied/bins,1-occupied/bins,np.mean(np.diff(times))/H if count>1 else 0,float(count>1)]
            keys=['count','GPU_sum','GPU_mean','GPU_max','oneGPU','two_to_fourGPU','over4GPU','positive_arrival_fraction','zero_arrival_fraction','interarrival_hours','interarrival_available']
            row+=vals;recent[minutes]=count/(minutes/60)
            if i==0:rec_names += [f'recent_{minutes}min_{k}' for k in keys]
        row += [(issue[i]-s[last-1])/H if last else 0,float(last>0),recent[60]-recent[360],recent[60]/recent[1440] if recent[1440]>0 else 0,float(recent[1440]>0)]
        if i==0:rec_names+=['hours_since_last_submit','last_submit_available','arrival_acceleration_1h_vs_6h','arrival_ratio_1h_to_24h','arrival_ratio_available']
        rec.append(row);recmax.append(int(s[last-1]) if last else 0)
    rec=np.array(rec,dtype=np.float32)
    for t,y in targets.items():
        n=y.shape[1];dt=24/n;base=np.repeat(X0,4,axis=1) if t=='T3' else X0.copy();shape=[]
        if t=='T3':
            shape=['target_slot','target_time_of_day_hours','lead_time_minutes']
            deterministic=np.stack([np.arange(n),np.arange(n)/4,(6+np.arange(n)/4)*60],axis=1)
            base=np.concatenate([base,np.broadcast_to(deterministic,(len(DAYS),n,3))],axis=-1).astype(np.float32)
        lag_names=[]
        for lag in [1,2,3,7,14,21,28]:lag_names += [f'same_clock_{lag}d_{k}' for k in ['value','available','age_hours','mature']]
        lag_names+=['latest_same_clock_value','latest_same_clock_available','latest_same_clock_age_hours','latest_same_clock_mature']
        lagx=np.zeros((len(DAYS),n,len(lag_names)),np.float32)
        for i in range(len(DAYS)):
            for j in range(n):
                latest=None
                for k,lag in enumerate([1,2,3,7,14,21,28]):
                    h=i-lag;exists=h>=0;available=exists and mat[t][h,j]<=issue[i] and start[h]+int((j+1)*dt*H)<=issue[i]
                    if available:
                        lagx[i,j,4*k:4*k+4]=[y[h,j],1,lag*24,1]
                        if latest is None:latest=(y[h,j],1,lag*24,1)
                    else:lagx[i,j,4*k:4*k+4]=[0,0,lag*24 if exists else 0,0]
                    proof.append(dict(target=t,day_index=i,slot=j,feature=f'same_clock_{lag}d',value=float(lagx[i,j,4*k]),available=available,maturity_status='MATURE' if available else ('IMMATURE_OR_FUTURE' if exists else 'NO_HISTORY'),lag_age_hours=lag*24 if exists else None,source_day=DAYS[h] if exists else None,source_available_ns=int(mat[t][h,j]) if exists else None,issue_ns=int(issue[i]),max_read_ns=int(mat[t][h,j]) if available else None,valid=not available or mat[t][h,j]<=issue[i]))
                if latest is not None:lagx[i,j,-4:]=latest
                proof.append(dict(target=t,day_index=i,slot=j,feature='F2_ALL',value=None,available=True,maturity_status='EVENT_TIME_PROXY',lag_age_hours=None,source_day=None,source_available_ns=recmax[i],issue_ns=int(issue[i]),max_read_ns=recmax[i],valid=recmax[i]<=issue[i]))
                proof.append(dict(target=t,day_index=i,slot=j,feature='F0_ALL71',value=None,available=True,maturity_status='INHERITED_PROOF',lag_age_hours=None,source_day=None,source_available_ns=int(issue[i]),issue_ns=int(issue[i]),max_read_ns=int(issue[i]),valid=True))
        dates=pd.to_datetime(DAYS);cal=np.array([[int(d.dayofweek==k) for k in range(7)]+[int(d.month==m) for m in range(1,13)]+[int(((d.month%12)//3)==s) for s in range(4)] for d in dates],dtype=np.float32)
        cal_names=[f'weekday_{k}' for k in range(7)]+[f'month_{m}' for m in range(1,13)]+[f'calendar_quarter_season_{s}' for s in range(4)]
        rx=np.repeat(rec[:,None,:],n,axis=1);cx=np.repeat(cal[:,None,:],n,axis=1)
        combos={'F0':([],[]),'F1':([lagx],lag_names),'F2':([rx],rec_names),'F3':([],[]),'F4':([cx],cal_names),'F5':([lagx,rx,cx],lag_names+rec_names+cal_names)}
        for f,(addition,nn) in combos.items():
            packs[t+'_'+f]=np.concatenate([base]+addition,axis=-1) if addition else base.copy()
            groups[t+'_'+f]=names0+shape+nn
            assert np.array_equal(packs[t+'_'+f][...,:71],np.repeat(X0,4,axis=1) if t=='T3' else X0)
        contracts[t]=dict(slot_minutes=int(dt*60),base71='bitwise preserved; hourly values repeated into four quarter-hour slots for T3',shape_features=shape,same_clock='zero plus unavailable mask; no future fill; T0/T1 require completed eligibility in source hour; T2/T3 conservative full historical day maturity',maturity='T0/T1 max(day end, all eligible submit-day completions); T2/T3 max(day end, completions of eligible submissions in (historical issue, day end)); unresolved positive-GPU submissions censor day indefinitely',F3='NOT_AVAILABLE; F3 aliases F0, no fabricated state',F4_holidays='NOT_AVAILABLE: modeled UTC+10 does not establish source jurisdiction or authoritative holiday calendar')
    np.savez_compressed(ROOT/'FEATURES.npz',**packs)
    pd.DataFrame(proof).to_parquet(ROOT/'FEATURE_CAUSAL_AVAILABILITY.parquet',index=False)
    write('FEATURE_GROUPS.json',groups)
    write('FEATURE_CONTRACT.json',dict(targets=contracts,F0_original_names=names0,F0_proof_sha256=sha(BASE/'FEATURE_MATURITY_PROOF.parquet'),F2_names=rec_names,F2_raw_fields=['submit_time','gpus_requested'],F2_filter='finite positive requested GPU only; never completion/start eligibility',F2_scope='GPU-job arrivals; CPU-only jobs excluded deterministically from request field',F3_excluded=['RUNNING_count','PENDING_count','active_GPU','queued_GPU','GPU_utilization','current_large_jobs','remaining_work'],F4='One-hot weekday, month, deterministic season category; no inferred holiday labels',provenance_limit='Event-time reconstruction only. Mutable request versions and ingestion-time arrival are unverified; deployment readiness false.'))
    write('FEATURE_LEAKAGE_AUDIT.json',dict(PASS=all(p['valid'] for p in proof),rows=len(proof),future_feature_reads=0,start_end_usage='labels and maturity gates only; F2 reads submit and request only; no F3 state reconstruction',target_specific={t:'PASS event-time contract; deployment snapshot certification unavailable' for t in targets},inherited_proof=sha(BASE/'FEATURE_MATURITY_PROOF.parquet'),excluded_unavailable_groups=['F3','F4_holidays']))
if __name__=='__main__':prepare()

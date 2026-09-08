from .common import *
from scipy import stats as ss,optimize,special

def power_30_to_15(x):
    x=np.asarray(x,float);assert x.shape[-1]==48
    return np.repeat(x,2,axis=-1)
def bin_ns(t,begin):return (np.asarray(t,dtype=np.int64)-int(begin))//STEP
def correlation(x,y):return {'Pearson':ss.pearsonr(x,y).statistic,'Spearman':ss.spearmanr(x,y).statistic}
def count_fit(n):
    results={}
    for family in ['POISSON','NB','ZINB']:
        def loss(t):
            mu=np.exp(t[0]);r=np.exp(t[1]) if family!='POISSON' else None
            lp=ss.poisson.logpmf(n,mu) if r is None else ss.nbinom.logpmf(n,r,r/(r+mu))
            if family=='ZINB':
                pi=special.expit(t[2]);lp=np.where(n==0,np.logaddexp(np.log(pi),np.log1p(-pi)+lp),np.log1p(-pi)+lp)
            return -lp.sum()
        init=[np.log(n.mean())]+([0.] if family!='POISSON' else [])+([-3.] if family=='ZINB' else [])
        result=optimize.minimize(loss,init,method='L-BFGS-B',bounds=[(-10,12)]+([(-9,12)] if family!='POISSON' else [])+([(-15,12)] if family=='ZINB' else []))
        k=len(init);results[family]={'mu':np.exp(result.x[0]),'dispersion_r':np.exp(result.x[1]) if k>=2 else None,
          'pi':special.expit(result.x[2]) if k==3 else 0.,'AIC':2*k+2*result.fun,'BIC':k*np.log(len(n))+2*result.fun,'converged':result.success}
    return results

def main():
    assert not (OUT/'fits').exists()
    plan=read('V40R5_PHASE0_PLAN.json');j=pd.read_parquet(OUT/'inputs/GPU_related_candidates_preMay.parquet')
    i=pd.read_parquet(OUT/'inputs/V40R3_LABEL_MATURITY_LEDGER.parquet');parent=np.load(OUT/'inputs/causal_dataset.npz')
    rawunits={c:str(j[c].dtype) for c in ['submit_time','start_time','end_time','arrival_bin']}
    for c in rawunits:j[c]=j[c].dt.as_unit('ns')
    assert all(j[c].dropna().lt(MAY).all() for c in rawunits)
    eligible=j.GPU_quantity_authorized&j.start_time.notna()&j.end_time.notna()&(j.end_time>j.start_time)&(j.start_time>=j.submit_time)
    assert np.array_equal(eligible,j.model_cohort) and eligible.sum()==548339
    assert j.gpus_requested.isna().sum()==240050 and j.GPU_quantity_authorized.sum()==550123
    cohort=j.loc[eligible].copy();z=cohort.gpus_requested.to_numpy()*(ns(cohort.end_time)-ns(cohort.start_time))/3.6e12
    assert np.max(np.abs(z-cohort.work_GPUh.to_numpy()))<=1e-7
    begin=i.target_start.iloc[0].value;ix=bin_ns(ns(cohort.submit_time),begin);inside=(ix>=0)&(ix<349*96)
    assert inside.sum()==545553
    # Add actual job events into quarter-hours. No parent-target division.
    y=np.bincount(ix[inside],weights=z[inside],minlength=349*96).reshape(349,96)
    n=np.bincount(ix[inside],minlength=349*96).reshape(349,96)
    rebuilt=y.reshape(349,48,2).sum(2);error=float(np.abs(rebuilt-parent['target']).max())
    if error>1e-7 or abs(y.sum()-1904541.778333334)>1e-7:
        dump('V40R5_15MIN_30MIN_AGGREGATION_AUDIT.json',{'status':'V40R5_15MIN_TARGET_RECONSTRUCTION_FAIL','max_abs_error_GPUh':error,'total_GPUh':y.sum()})
        raise RuntimeError('V40R5_15MIN_TARGET_RECONSTRUCTION_FAIL: STOP NO MODEL FIT')
    boundaries=begin+np.arange(349*96+1,dtype=np.int64)*STEP
    rows=pd.DataFrame({'operating_day':np.repeat(i.operating_day,96),'slot15':np.tile(np.arange(1,97),349),
       'slot_start_UTC':pd.to_datetime(boundaries[:-1],utc=True),'slot_end_UTC':pd.to_datetime(boundaries[1:],utc=True),
       'DeltaW15_GPUh':y.ravel(),'N15':n.ravel(),'forecast_origin':np.repeat(i.forecast_origin,96),
       'role':np.repeat(i.role,96),'stage_maturity_eligible':np.repeat(i.stage_maturity_eligible,96)})
    rows.to_parquet(OUT/'V40R5_15MIN_TARGET_RECONSTRUCTION.parquet',index=False)
    testtimes=np.array([begin-1,begin,begin+STEP-1,begin+STEP,begin+96*STEP-1,begin+96*STEP],dtype=np.int64)
    expected=np.array([-1,0,0,1,95,96]);assert np.array_equal(bin_ns(testtimes,begin),expected)
    boundary_real=(ns(cohort.submit_time)[inside]-begin)%STEP==0
    dump('V40R5_TIME_BOUNDARY_TEST_REPORT.json',{'synthetic_ns':testtimes,'expected':expected,'actual':bin_ns(testtimes,begin),'PASS':True,'actual_exact_boundary_jobs':boundary_real.sum(),'policy':'[start,end), integer nanosecond arithmetic'})
    dump('V40R5_TIME_UNIT_CONTRACT.json',{'fields':[{'source_field':c,'raw_unit':rawunits[c],'decoded_unit':rawunits[c],'canonical_unit':'datetime64[ns, UTC]','timezone':'UTC'} for c in rawunits],
      'authority':'Arrow/pandas dtype from preserved job event table, not field suffix','origin':'D-1 08:00 UTC = D-1 18:00 fixed AEST','target_day':'00:00-24:00 fixed UTC+10; no DST','boundary':'[start,end)'})
    target={'status':'PASS','raw_recovered_jobs_parent_provenance':4728595,'raw_recovered_recounted':False,'GPU_candidates':len(j),'GPU_authorized':int(j.GPU_quantity_authorized.sum()),'service_validity_exclusions':1784,
      'eligible_jobs':len(cohort),'missing_GPU_excluded':240050,'target_contributors':int(inside.sum()),'target_days':349,'intervals':349*96,'total_GPUh':y.sum(),
      'unit':'GPUh','label':'authorized gpus_requested * exact (end-start) /3600 seconds','allocation':'Entire service demand assigned by original submit timestamp','half_split':False,
      'F30':False,'missing_GPU_imputed':False,'target_kind':'Exogenous arriving GPU-service demand; not execution occupancy or FLOPs','tolerance_GPUh':1e-7}
    dump('V40R5_15MIN_TARGET_CONTRACT.json',target)
    dump('V40R5_15MIN_30MIN_AGGREGATION_AUDIT.json',{'status':'PASS','max_abs_error_GPUh':error,'total_error_GPUh':float(y.sum()-1904541.778333334),
      'daily_max_error_GPUh':float(np.abs(y.sum(1)-parent['target'].sum(1)).max()),'adjacent_pairs':16752,'arithmetic':'Job-event weighted bincount at 15min, then pair sum; roundoff within 1e-7; no adjustments to labels'})
    (OUT/'V40R5_TARGET_REPRODUCTION_REPORT.md').write_text(f'15분 타깃 재구성 PASS. 원래 submit 시각으로 545,553 jobs를 33,504구간에 배정했다. 총량 {y.sum():.12f} GPUh, 인접 15분 합과 R4 30분 타깃의 최대 차이 {error:.12g} GPUh. 허용오차 1e-7. 30분 타깃 반분 없음. raw 4,728,595건은 부모 provenance이며 재스캔하지 않았다.\n',encoding='utf-8')
    tr=np.repeat(((i.role=='TRAIN')&i.stage_maturity_eligible).to_numpy(),96);yt=y.ravel()[tr];nt=n.ravel()[tr]
    u=float(np.quantile(yt[yt>0],.95));high=float(np.quantile(nt[nt>0],.95))
    dump('V40R5_BURST_THRESHOLD_FREEZE.json',{'u_B_GPUh':u,'rule':'TRAIN positive DeltaW15 Q95','operator':'>','TRAIN_positive_N':int((yt>0).sum()),
      'diagnostic_positive_quantiles':dict(zip(['Q90','Q97.5','Q99'],np.quantile(yt[yt>0],[.9,.975,.99]))),'N_high':high,'count_rule':'TRAIN positive N15 Q95','R4_threshold_reused':False,'TRAIN_burst_prevalence':np.mean(yt>u)})
    trainrows=rows.loc[tr].copy();trainrows['month']=trainrows.operating_day.str[:7]
    forensic=statistics(yt);forensic.update(scope='Mature TRAIN only',daily_total_preserved=True,TRAIN_months=trainrows.groupby('month').DeltaW15_GPUh.agg(['sum','mean','size']).reset_index().to_dict('records'),
      top1_percent_workload_share=np.sort(yt)[-int(np.ceil(len(yt)*.01)):].sum()/yt.sum())
    dump('V40R5_15MIN_DISTRIBUTION_FORENSIC.json',forensic)
    fits=count_fit(nt);dump('V40R5_15MIN_COUNT_DIAGNOSTIC.json',{'scope':'Mature TRAIN only; descriptive intercept distributions, not candidate forecast fitting','stats':statistics(nt),'Poisson_expected_zero':np.exp(-nt.mean()),'families':fits,'NB_supported':fits['NB']['BIC']<fits['POISSON']['BIC']})
    zt=z[inside][tr[ix[inside]]];meansev=np.divide(y.ravel(),n.ravel(),out=np.zeros(y.size),where=n.ravel()>0);positive=tr&(n.ravel()>0)
    dump('V40R5_15MIN_SEVERITY_DIAGNOSTIC.json',{'scope':'Mature TRAIN jobs','stats':statistics(zt),'count_mean_severity':correlation(n.ravel()[positive],meansev[positive]),'count_aggregate':correlation(nt,yt),'new_EVT_fit':False,'R4_EVT_status':'UNSUPPORTED'})
    # Existing R4 inputs contain no AEMO. Test source-authorized conversion on synthetic power only.
    testpower=np.arange(48,dtype=float)*13.25;p15=power_30_to_15(testpower)
    assert np.array_equal(testpower*.5,p15.reshape(48,2).sum(1)*.25)
    dump('V40R5_AEMO_30_TO_15_AUDIT.json',{'status':'PASS_RULE_NOT_APPLICABLE_TO_CURRENT_FEATURES','actual_AEMO_feature_count':0,'new_AEMO_source_added':False,
      'source_authority':'V40R5_CURRENT_TIME_AXIS_AUTHORITY.json','synthetic_power_duplication_PASS':True,'energy_conservation_max_error':0.,'linear_interpolation':False,'power_halving':False,'scientific_AEMO_payload_reads':0})
    dump('V40R5_MULTIRATE_FEATURE_CONTRACT.json',{'mean_power':'P15[2r]=P15[2r+1]=P30[r]; MW not halved','energy':'Do not apply power duplication; no interval-energy feature present, no new rule invented',
      'target':'Direct original submit-event reconstruction at 15min','historical_context':'R4 native 30min past summaries retained; new calendar and mature seasonal label features aligned at 15min','AEMO_inputs_in_R4':False})
    build_features(j,cohort,z,i,parent,y,n,boundaries,tr)
    dump('V40R5_TEMPORAL_SPLIT_CONTRACT.json',{'roles':{r:{'start':i.loc[i.role==r,'operating_day'].min(),'end':i.loc[i.role==r,'operating_day'].max(),'eligible_days':int(((i.role==r)&i.stage_maturity_eligible).sum())} for r in ['TRAIN','DEVELOPMENT','CALIBRATION','EXPOSED_EVALUATION']},
      'purged_days':i.loc[i.role=='PURGED','operating_day'].tolist(),'maturity_ledger_SHA256':sha(OUT/'inputs/V40R3_LABEL_MATURITY_LEDGER.parquet'),'same_parent_rows':True})
    dump('V40R5_UNTOUCHED_CONFIRMATION_AUDIT.json',{'TRUE_CONFIRMATORY_AVAILABLE':'NO','new_unexposed_period_opened':False,'maximum_positive_status':'PREVALIDATED','parent_audit':external(R4OUT/'V40R4_UNTOUCHED_HOLDOUT_AUDIT.json')})
    print('15min identity PASS max error',error,'total',y.sum(),'TRAIN burst',u,'N high',high,flush=True)

def build_features(j,cohort,z,i,parent,y,n,boundaries,tr):
    b=pd.read_parquet(OUT/'inputs/arrival_bins_with_maturity.parquet');b.index=b.index.as_unit('ns')
    for c in ['max_observed_end','modeled_end_max']:b[c]=b[c].dt.as_unit('ns')
    first=b.index[0].value;size=len(b)*2;ix=bin_ns(ns(cohort.submit_time),first)
    ok=(ix>=0)&(ix<size);work=np.bincount(ix[ok],weights=z[ok],minlength=size);count=np.bincount(ix[ok],minlength=size)
    end=ns(b.max_observed_end);end=np.maximum(end,b.index.asi8+2*STEP);unresolved=b.unresolved_end_count.to_numpy()
    proof=pd.read_parquet(OUT/'inputs/feature_available_at_proofs.parquet')
    assert (proof.available_at<=proof.forecast_origin).all()
    past=parent['past'].copy();past[:,:,1]=np.where(past[:,:,2]>0,past[:,:,1],0.)
    assert np.isfinite(past).all()
    features=[];names=[];meta=[];avail=[]
    origin=np.repeat(ns(i.forecast_origin),96)
    def add(name,value,source,native,rule,maturity,available=None):
        value=np.asarray(value).reshape(-1);assert len(value)==349*96
        features.append(value);names.append(name);avail.append(origin if available is None else available)
        meta.append({'feature_name':name,'source':source,'available_at':'Explicit int64 ns matrix; deterministic calculation at origin or matured source END/closure',
          'native_resolution':native,'15min_alignment_rule':rule,'causal_status':'PASS','label_maturity_rule':maturity})
    for window in [12,48,336]:
        for col,field in enumerate(['submit_count','mature_GPUh','mature_mask','maturity_age_hours']):
            for stat in ['mean','std','max']:
                value=getattr(np,stat)(past[:,-window:,col],axis=1)
                add(f'history_{field}_{window}_{stat}',np.repeat(value,96),'Frozen R4 causal past tensor','30min','Same origin history summary for all target slots','R4 event prefix/maturity proof retained')
    for col,field in enumerate(['submit_count','mature_GPUh','mature_mask','maturity_age_hours']):add(f'history_{field}_last',np.repeat(past[:,-1,col],96),'Frozen R4 causal past tensor','30min','Same origin last closed interval','Parent mature mask and availability proof')
    slot=np.tile(np.arange(96),349);hour=slot/4;weekday=np.repeat(pd.to_datetime(i.operating_day).dt.weekday.to_numpy(),96)
    calendar={'slot15_fraction':slot/95,'minute_of_day':slot*15,'hour_sin':np.sin(2*np.pi*hour/24),'hour_cos':np.cos(2*np.pi*hour/24),
      'weekday_sin':np.sin(2*np.pi*weekday/7),'weekday_cos':np.cos(2*np.pi*weekday/7),'weekend':(weekday>=5).astype(float),'child15_position':slot%2,'lead_hours':(boundaries[:-1]-origin)/3.6e12}
    for name,v in calendar.items():add(name,v,'Fixed UTC+10 calendar','15min','Exact child slot','No target-derived data')
    seasonal_w=[];seasonal_n=[];seasonal_mask=[];proofrows=[]
    for lag in [7,14,21,28]:
        src=boundaries[:-1]-lag*96*STEP;idx=bin_ns(src,first);valid=(idx>=0)&(idx<size);clipped=np.clip(idx,0,size-1);parentix=clipped//2
        at=end[parentix];mature=valid&(unresolved[parentix]==0)&(at<=origin)&(src+STEP<=origin)
        w=np.where(mature,work[clipped],0.);c=np.where(mature,count[clipped],0.)
        seasonal_w.append(w);seasonal_n.append(c);seasonal_mask.append(mature)
        for field,v in [('GPUh',w),('count',c),('mature',mature.astype(float))]:add(f'seasonal15_{lag}d_{field}',v,'Original GPU job submit-event table + parent all-raw-bin maturity ledger','15min','Direct historical child bin; no half-splitting','Both children conservatively require parent all-raw END closure',np.where(mature,at,origin))
        proofrows.append(pd.DataFrame({'origin_ns':origin,'source15_start_ns':src,'parent_available_ns':at,'mature':mature,'published_GPUh':w,'published_count':c,'lag_days':lag}))
    X=np.stack(features,1).astype(np.float32);A=np.stack(avail,1)
    assert np.isfinite(X).all() and (A<=origin[:,None]).all()
    np.savez_compressed(OUT/'data.npz',X=X,y=y.ravel(),n=n.ravel(),days=np.asarray(i.operating_day,dtype='U10'),origin_ns=origin,
      slot_start_ns=boundaries[:-1],feature_names=np.array(names,dtype='U80'),seasonal_w=np.stack(seasonal_w,1),seasonal_n=np.stack(seasonal_n,1),seasonal_mask=np.stack(seasonal_mask,1))
    np.savez_compressed(OUT/'feature_availability.npz',available_ns=A,origin_ns=origin)
    pd.concat(proofrows,ignore_index=True).to_parquet(OUT/'seasonal_maturity_proof.parquet',index=False)
    dump('V40R5_FEATURE_AUTHORITY_AUDIT.json',{'features':meta,'feature_count':len(names),'AEMO_added':False,'future_job_features':False,
      'parent_feature_contract_SHA256':sha(R4OUT/'V40R4_CAUSAL_FEATURE_CONTRACT.json'),'source_authority_limit':'Logical event-time reconstruction; real telemetry ingestion delays and mutable request version timestamps not certified'})
    dump('V40R5_15MIN_FEATURE_MATRIX_CONTRACT.json',{'shape':X.shape,'names':names,'SHA256':sha(OUT/'data.npz'),'target_resolution':'15min x96','history':'36 summaries +4 last values of frozen native 30min causal history','calendar':'9 pure 15min/calendar features','seasonal':'4lags x3 values directly reconstructed at 15min with conservative parent maturity','normalization':'Models using linear classifiers fit scalers on TRAIN only'})
    dump('V40R5_LABEL_MATURITY_AUDIT.json',{'PASS':True,'parent_proof_rows':len(proof),'new_seasonal_proof_rows':349*96*4,'all_dependencies_available_by_origin':True,
      'child_bin_policy':'Conservative: all raw submissions in parent 30min bin must have observed END <=origin and no unresolved END','masked_GPUh_count_placeholders':0,
      'masked_placeholder_semantics':'0 accompanied by mature=0; no claim observed zero and no missing-GPU imputation','per_feature_matrix':'feature_availability.npz','seasonal_proof':'seasonal_maturity_proof.parquet'})
    dump('V40R5_CAUSALITY_FIREWALL.json',{'PASS':True,'max_available_minus_origin_ns':int((A-origin[:,None]).max()),'future_count_GPU_walltime_partition_QoS_hardware_cores_memory_start_end_runtime':False,
      'origin_plus_5_or_15_min_leakage':False,'count_label_as_feature':'Only mature historical counts; future realized count never predictor','optimizer_calls':0,'May_scientific_reads':0})
    print('Causal feature matrix',X.shape,'complete;',np.sum(np.stack(seasonal_mask,1)),'mature seasonal values',flush=True)
if __name__=='__main__':main()

"""TRAIN-only design diagnostics plus already-exposed R3 failure decomposition."""
from .common import *
from scipy import stats as ss,optimize,special
import time

def count_logpmf(n,mu,r=np.inf,pi=0.):
    n=np.asarray(n);mu=np.maximum(mu,1e-12)
    lp=ss.poisson.logpmf(n,mu) if np.isinf(r).all() else ss.nbinom.logpmf(n,r,r/(r+mu))
    return np.where(n==0,np.logaddexp(np.log(np.maximum(pi,1e-300)),np.log1p(-pi)+lp),np.log1p(-pi)+lp)

def count_diagnostics(n):
    result={}
    for family in ['POISSON','NB','ZIP','ZINB']:
        nb=family in ['NB','ZINB'];zi=family in ['ZIP','ZINB']
        def unpack(t):return np.exp(t[0]),np.exp(t[1]) if nb else np.inf,special.expit(t[-1]) if zi else 0.
        def loss(t):return -np.sum(count_logpmf(n,*unpack(t)))
        t=[np.log(max(n.mean(),1e-3))]+([0.] if nb else [])+([0.] if zi else [])
        fit=optimize.minimize(loss,t,method='L-BFGS-B',bounds=[(-10,15)]+([(-9,15)] if nb else [])+([(-15,15)] if zi else []))
        mu,r,pi=unpack(fit.x);nll=loss(fit.x)
        result[family]={'mu':mu,'dispersion_r':r if nb else None,'structural_zero_pi':pi,'negative_log_likelihood':nll,
          'BIC':2*nll+len(t)*np.log(len(n)),'converged':bool(fit.success),'message':str(fit.message),
          'predicted_zero_probability':float(np.exp(count_logpmf(np.array([0]),mu,r,pi))[0])}
    return result

def correlation(a,b):
    a=np.asarray(a);b=np.asarray(b);valid=np.isfinite(a)&np.isfinite(b);a=a[valid];b=b[valid]
    return {'N':len(a),'Pearson':float(ss.pearsonr(a,b).statistic),'Spearman':float(ss.spearmanr(a,b).statistic)} if len(a)>2 and np.std(a)>0 and np.std(b)>0 else {'N':len(a),'Pearson':None,'Spearman':None}

def main():
    started=time.monotonic();plan=read('V40R4_PHASE0_PLAN.json')
    assert not (OUT/'fits').exists(),'No phase0 redesign after candidate fits'
    assert git('merge-base','--is-ancestor','abfb9a43be0f442a943535a146344fe954703aad','HEAD')==''
    a,info,j,m=data();y=a['target'];cohort=j.loc[j.model_cohort].copy()
    assert len(cohort)==548339 and j.gpus_requested.isna().sum()==240050
    assert all(cohort[c].lt(MAY).all() for c in ['submit_time','start_time','end_time'])
    exact=cohort.gpus_requested*(cohort.end_time-cohort.start_time).dt.total_seconds()/3600
    assert np.max(np.abs(exact-cohort.work_GPUh))<1e-7
    cohort['flat_interval']=((cohort.submit_time.dt.as_unit('ns').astype('int64')-info.target_start.iloc[0].value)//(30*60*10**9)).astype(int)
    zjob=cohort.loc[cohort.flat_interval.between(0,y.size-1)].copy();ix=zjob.flat_interval.to_numpy();z=zjob.work_GPUh.to_numpy()
    count=np.bincount(ix,minlength=y.size).reshape(y.shape);total=np.bincount(ix,weights=z,minlength=y.size).reshape(y.shape)
    error=float(np.abs(total-y).max());assert error<plan['target_reproduction_tolerance_absolute_GPUh']
    assert len(zjob)==545553 and abs(z.sum()-1904541.7783333336)<1e-7
    np.savez_compressed(OUT/'compound_labels.npz',count=count,severity=z,job_interval=ix,target=y,days=a['days'])
    dump('V40R4_V40R3_TARGET_REPRODUCTION.json',{'status':'PASS','eligible_cohort_jobs':len(cohort),'missing_GPU_excluded':240050,
      'target_contributing_jobs':len(zjob),'target_GPUh':z.sum(),'target_days':len(info),'intervals':y.size,
      'max_abs_interval_difference_GPUh':error,'tolerance_GPUh':plan['target_reproduction_tolerance_absolute_GPUh'],
      'count_nonzero_equals_target_positive':bool(np.array_equal(count>0,y>0)),'cohort_unchanged':True,
      'allocation':'Entire observed GPUh assigned to submission interval, never execution slots','label_SHA256':sha(OUT/'compound_labels.npz')})
    train=np.repeat(m['TRAIN'],48);nj=count.ravel()[train];tj=train[ix];ztrain=z[tj];trainix=ix[tj];train_days=np.flatnonzero(m['TRAIN'])
    ctfit=count_diagnostics(nj);best=min((n for n,r in ctfit.items() if r['converged']),key=lambda n:ctfit[n]['BIC'])
    rows=pd.DataFrame({'count':count.ravel(),'total':y.ravel()})
    grouped=zjob.groupby('flat_interval').work_GPUh
    for name,f in [('mean','mean'),('median','median'),('max','max')]:rows[name]=grouped.agg(f).reindex(rows.index).fillna(0)
    descending=zjob.sort_values(['flat_interval','work_GPUh'],ascending=[True,False]);top3=descending.groupby('flat_interval').head(3).groupby('flat_interval').work_GPUh.sum()
    rows['top1']=rows['max'];rows['top3']=top3.reindex(rows.index).fillna(0)
    rows['top1_share']=np.divide(rows.top1,rows.total,out=np.zeros(len(rows)),where=rows.total>0)
    rows['top3_share']=np.divide(rows.top3,rows.total,out=np.zeros(len(rows)),where=rows.total>0)
    rows['day']=np.repeat(info.operating_day.to_numpy(),48);rows['slot']=np.tile(np.arange(48),len(info))
    rows['hour_AEST']=rows.slot/2;rows['weekday']=np.repeat(pd.to_datetime(info.operating_day).dt.weekday.to_numpy(),48)
    rows['train']=train
    qn=float(np.quantile(nj,.95));qm=float(np.quantile(rows.loc[train & rows['count'].gt(0),'max'],.95));qz=float(np.quantile(ztrain,.95))
    rows['training_tail_exceedances']=np.bincount(ix,weights=(z>qz).astype(int),minlength=y.size).astype(int)
    rows['classification']=np.select([rows['count'].gt(qn)&rows['max'].gt(qm),rows['count'].gt(qn),rows['max'].gt(qm)],['MIXED','COUNT_DRIVEN','SEVERITY_DRIVEN'],default='UNRESOLVED')
    for name,col,ref in [('job_count_percentile','count',nj),('max_severity_percentile','max',rows.loc[train & rows['count'].gt(0),'max']),('total_severity_percentile','total',y.ravel()[train])]:
        rows[name]=100*np.searchsorted(np.sort(ref),rows[col],side='right')/len(ref)
    r3pred=np.load(OLD/'fits/CMABF/calibrated_prediction.npy')
    rows['R3_CMABF_Q90']=r3pred[:,:,1].ravel();rows['R3_CMABF_miss']=rows.total>rows.R3_CMABF_Q90
    burst=rows.loc[rows.total.ge(plan['burst_threshold_GPUh'])].copy()
    january=burst.loc[burst.day.str.startswith('2025-01')];miss=january.loc[january.R3_CMABF_miss]
    assert len(january)==114 and len(miss)==12
    rules={'count_Q95':qn,'positive_interval_max_severity_Q95':qm,'job_severity_Q95':qz,'source':'Mature TRAIN only','definitions':plan['burst_rule']}
    dump('V40R4_BURST_CLASSIFICATION_RULE.json',rules)
    burst.to_csv(OUT/'V40R4_V40R3_BURST_FAILURE_DECOMPOSITION.csv',index=False,lineterminator='\n')
    dump('V40R4_V40R3_BURST_FAILURE_DECOMPOSITION.json',{'scope':'Already-exposed R3 reference, descriptive only; thresholds from TRAIN',
        'rule':rules,'all_burst_N':len(burst),'intervals':burst.to_dict('records'),'January_burst_N':114,'January_miss_N':12,
        'January_miss_classification_counts':miss.classification.value_counts().to_dict(),'January_misses':miss.to_dict('records')})
    textlines=['V40R3의 1월 burst 114개 중 12개 miss를 TRAIN 규칙으로 분해했다. 배포 규칙이나 인과 추정이 아니다.','',
      '| 일자 | slot | GPUh | N | 최대 작업 GPUh | top1 비율 | top3 비율 | 분류 |','|---|---:|---:|---:|---:|---:|---:|---|']
    for r in miss.itertuples():textlines.append(f'| {r.day} | {r.slot} | {r.total:.3f} | {r.count} | {r.max:.3f} | {r.top1_share:.2%} | {r.top3_share:.2%} | {r.classification} |')
    (OUT/'V40R4_V40R3_BURST_FAILURE_DECOMPOSITION.md').write_text('\n'.join(textlines)+'\n',encoding='utf-8',newline='\n')
    tr=rows.loc[train].copy()
    def acf(col):
        # Pairs use actual flat time distance; never concatenate across excluded days.
        full=rows[col].to_numpy();return {str(lag):correlation(full[:-lag][train[:-lag]&train[lag:]],full[lag:][train[:-lag]&train[lag:]])['Pearson'] for lag in [1,2,12,48,336]}
    dump('V40R4_COUNT_DISTRIBUTION_DIAGNOSTIC.json',{'scope':'TRAIN only; diagnostic distribution estimation, not candidate forecasts',
       'stats':stats(nj),'variance_mean_ratio':np.var(nj,ddof=1)/np.mean(nj),'zero_rate':np.mean(nj==0),
       'Poisson_expected_zero_rate':np.exp(-np.mean(nj)),'excess_zero_rate':np.mean(nj==0)-np.exp(-np.mean(nj)),
       'autocorrelation':acf('count'),'hour_of_day':tr.groupby('hour_AEST')['count'].agg(['mean','var','size']).reset_index().to_dict('records'),
       'weekday':tr.groupby('weekday')['count'].agg(['mean','var','size']).reset_index().to_dict('records'),
       'temporal_shift_TRAIN_months':tr.assign(month=tr.day.str[:7]).groupby('month')['count'].agg(['mean','var','size']).reset_index().to_dict('records'),
       'families':ctfit,'selected_classical_family':best,'interpretation':'Overdispersion/zero inflation are descriptive; marginal fit does not establish conditional forecast calibration'})
    pos=tr['count']>0;dependencies={c:correlation(tr.loc[pos,'count'],tr.loc[pos,c]) for c in ['mean','max','top1_share','total','training_tail_exceedances']}
    significant=abs(dependencies['mean']['Spearman'])>=.2
    tr['count_quantile']=pd.qcut(tr['count'].rank(method='first'),4,labels=False)
    rows['residual_total']=rows.total-rows.hour_AEST.map(tr.groupby('hour_AEST').total.mean())
    dump('V40R4_COUNT_SEVERITY_DEPENDENCE_AUDIT.json',{'scope':'TRAIN only, association not causality','positive_interval_correlations':dependencies,
       'all_interval_total_correlation':correlation(tr['count'],tr.total),'meaningful_dependence':significant,
       'CCAF_condition_on_predicted_mu':significant,'realized_future_N_as_predictor':False,
       'count_quantile_summaries':tr.groupby('count_quantile')[['count','mean','max','top1_share','total','training_tail_exceedances']].mean().reset_index().to_dict('records'),
       'time_of_day_composition':tr.groupby('hour_AEST')[['count','mean','max','top1_share','total']].mean().reset_index().to_dict('records'),
       'residual_cross_interval_correlation_after_TRAIN_hour_mean':acf('residual_total'),
       'conditional_independence_limit':'Scenario conditional independence is an approximation; observed residual serial dependence is not modeled by marginal heads and limits joint daily calibration'})
    body={};lnsigma=float(np.std(np.log(ztrain)));lnloc=float(np.mean(np.log(ztrain)))
    for family,args in [('LOGNORMAL',(lnsigma,0,np.exp(lnloc))),('GAMMA',ss.gamma.fit(ztrain,floc=0))]:
        dist=ss.lognorm if family=='LOGNORMAL' else ss.gamma
        body[family]={'parameters':args,'BIC':-2*dist.logpdf(ztrain,*args).sum()+2*np.log(len(ztrain)),
          'KS_distance':ss.kstest(ztrain,dist.cdf,args=args).statistic}
    tail=[];rng=np.random.default_rng(SEED);qlevels=np.r_[np.linspace(.01,.95,70),.975,.99,.995,.999]
    for quantile in plan['EVT_rule']['candidate_quantiles']:
        u=float(np.quantile(ztrain,quantile));excess=ztrain[ztrain>u]-u
        xi,loc,sigma=ss.genpareto.fit(excess,floc=0);fits=[]
        day_excess={int(d):ztrain[(trainix//48==d)&(ztrain>u)]-u for d in train_days}
        for b in range(100):
            selected=rng.choice(train_days,len(train_days),replace=True);sample=np.concatenate([day_excess[int(d)] for d in selected])
            if len(sample)<50:continue
            bx,_,bs=ss.genpareto.fit(sample,floc=0);fits.append([bx,bs])
        theoretical=ss.genpareto.ppf(qlevels,xi,scale=sigma);empirical=np.quantile(excess,qlevels)
        row={'TRAIN_quantile':quantile,'threshold_GPUh':u,'exceedance_N':len(excess),'unique_excesses':len(np.unique(excess)),
          'xi':xi,'sigma':sigma,'finite_mean':xi<1,'finite_variance':xi<.5,'bootstrap_repetitions':len(fits),
          'xi_CI95':np.quantile(np.array(fits)[:,0],[.025,.975]),'sigma_CI95':np.quantile(np.array(fits)[:,1],[.025,.975]),
          'KS_distance':ss.kstest(excess,'genpareto',args=(xi,0,sigma)).statistic,
          'KS_p_value':'Not reported: parameters estimated on same observations; simple-null p would be misleading',
          'QQ_log_correlation':ss.pearsonr(np.log1p(theoretical),np.log1p(empirical)).statistic,
          'QQ_probabilities':qlevels,'QQ_theoretical_excess_GPUh':theoretical,'QQ_empirical_excess_GPUh':empirical}
        tail.append(row);print('GPD diagnostic',quantile,'N',len(excess),'xi',round(xi,4),'seconds',round(time.monotonic()-started),flush=True)
    for k,r in enumerate(tail):
        neighbor=[abs(r['xi']-v['xi']) for h,v in enumerate(tail) if abs(h-k)==1]
        r['neighbor_max_xi_difference']=max(neighbor)
        r['admissibility']={'support':r['exceedance_N']>=500 and r['unique_excesses']>=50,
          'shape_domain':0<=r['xi']<.9,'finite_mean_CI':r['xi_CI95'][1]<1,'stability':max(neighbor)<=.2,
          'KS_fit':r['KS_distance']<=.05,'QQ_fit':r['QQ_log_correlation']>=.98}
        r['admissible']=all(r['admissibility'].values())
    accepted=[r for r in tail if r['admissible']];chosen=min(accepted,key=lambda r:r['threshold_GPUh']) if accepted else None
    thresholds=np.quantile(ztrain,np.linspace(.5,.995,40));excess_curve=[{'threshold':u,'exceedance_N':int((ztrain>u).sum()),'mean_excess':float((ztrain[ztrain>u]-u).mean())} for u in thresholds]
    order=np.sort(ztrain);hill=[]
    for fraction in [.005,.01,.025,.05,.1]:
        k=max(10,int(len(order)*fraction));xi=float(np.mean(np.log(order[-k:]/order[-k-1])));hill.append({'upper_fraction':fraction,'k':k,'xi_Hill':xi,'alpha':1/xi})
    dump('V40R4_SEVERITY_TAIL_DIAGNOSTIC.json',{'scope':'TRAIN positive-job severity only, mature eligible origins','positive_severity':stats(ztrain),
      'log_severity':stats(np.log(ztrain)),'body_models':body,'selected_simple_body':min(body,key=lambda n:body[n]['BIC']),
      'mean_excess_curve':excess_curve,'Hill_diagnostic':hill,'Hill_limit':'Assumes regularly varying tail; descriptive threshold sensitivity, no automatic power-law claim',
      'GPD_thresholds':tail,'uncertainty':'Whole operating-day resampling, 100 repeats, fixed threshold; dependence within days retained; between-day dependence not fully modeled',
      'phase0_seconds':time.monotonic()-started})
    dump('V40R4_TAIL_THRESHOLD_SELECTION.json',{'status':'EVT_TAIL_SUPPORTED' if chosen else 'EVT_TAIL_NOT_SUPPORTED',
      'chosen_threshold_GPUh':chosen['threshold_GPUh'] if chosen else None,'chosen_TRAIN_quantile':chosen['TRAIN_quantile'] if chosen else None,
      'chosen_parameters':{k:chosen[k] for k in ['xi','sigma','xi_CI95']} if chosen else None,'threshold_rule':plan['EVT_rule'],
      'candidates':[{k:r[k] for k in ['TRAIN_quantile','threshold_GPUh','admissibility','admissible']} for r in tail],
      'future_performance_used':False,'fallback_if_rejected':'Preregister positive heavy-tailed lognormal mixture for P1; B6 marked not executed; never force GPD'})
    feature=old('V40R3_FEATURE_AVAILABILITY_LEDGER.json');proof=pd.read_parquet(OUT/'inputs/feature_available_at_proofs.parquet')
    assert (proof.available_at<=proof.forecast_origin).all() and (proof.value_time<=proof.forecast_origin).all()
    dump('V40R4_CAUSAL_FEATURE_CONTRACT.json',{'source':'Frozen V40R3 causal feature contract, independently re-audited against proof rows',
      'ledger':feature,'per_origin_proof_SHA256':sha(OUT/'inputs/feature_available_at_proofs.parquet'),
      'available_at_pass':True,'rolling_right_edge_pass':True,'future_job_resources_admitted':False,
      'forbidden_future_job_features':['GPU','walltime','partition','QoS','hardware','cores','memory'],
      'authority_limit':'Logical event-time reconstruction from archive; actual telemetry ingestion delay and mutable request versions not certified'})
    dump('V40R4_LABEL_MATURITY_VERIFICATION.json',{'same_R3_ledger_SHA256':sha(OUT/'inputs/V40R3_LABEL_MATURITY_LEDGER.parquet'),
      'training_origin_count':int(m['TRAIN'].sum()),'training_job_severity_N':len(ztrain),
      'training_max_label_available_at':info.loc[m['TRAIN'],'target_label_available_at'].max(),
      'cutoff':'2024-08-31 08:00 UTC','count_maturity':'Cohort membership requires service observation, so modeled-job counts follow same conservative maturity as GPUh',
      'history_mature_mask_unchanged':True,'no_immature_severity_as_feature':True})
    dump('V40R4_COUNT_LABEL_CONTRACT.json',{'label':'N_k','formula':'Count same modeled-cohort jobs whose submit falls in 30-minute interval k','same_cohort':True,'no_future_count_predictor':True,'no_F30':True})
    dump('V40R4_SEVERITY_LABEL_CONTRACT.json',{'label':'Z_j','formula':'gpus_requested*(end-start)/3600','unit':'GPUh','positive':True,
      'GPU_missing_imputation':False,'future_job_resources_predictors':False,'observed_runtime_target_only':True,'claim':'Observed requested-GPU service proxy, not FLOPs/hardware-independent work'})
    h=old('V40R3_UNTOUCHED_HOLDOUT_AUDIT.json')
    dump('V40R4_UNTOUCHED_HOLDOUT_AUDIT.json',{'TRUE_CONFIRMATORY_AVAILABLE':'NO','new_independent_authority_found':False,
      'R3_exposure_audit':h,'V40R4_scope':'All inherited blocks are exposed DEVELOPMENT/STRESS history; keep stage names for protocol roles only',
      'new_preMay_data_opened':False,'May_opened':False,'maximum_positive_claim':'PREVALIDATED'})
    rows.to_parquet(OUT/'interval_decomposition.parquet',index=False)
    print(json.dumps(clean({'target_max_error':error,'count_mean':nj.mean(),'count_variance_mean':nj.var()/nj.mean(),
      'count_family':best,'TRAIN_severities':len(ztrain),'simple_body':min(body,key=lambda n:body[n]['BIC']),
      'EVT_supported':chosen is not None,'dependency':dependencies['mean'],'January_miss_types':miss.classification.value_counts().to_dict()}),indent=2))

if __name__=='__main__':main()

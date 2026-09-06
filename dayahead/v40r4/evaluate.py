"""Final exposed comparison, enabled only by committed DEVELOPMENT comparator."""
from .common import *
from .train import load,NAMES,rank,raw_quantiles
from .models import load_params
from .distributions import scenarios,predictive_summary,take,severity_ppf,severity_cdf,severity_logpdf,nb_logpmf
from .metrics import *
from scipy import stats as ss,special

REPORT={'B0':'B0_ZERO','B1':'B1_SEASONAL','B2':'B2_HURDLE_LGBM','B3':'B3_TWEEDIE','B4':'B4_PARAMETRIC_COMPOUND','B5':'B5_ML_COMPOUND','P1':'CCAF'}
def component_metrics(p,a,m,reg):
    if p['kind'] not in ['LOGNORMAL','SPLICE']:
        return {'status':'NOT_APPLICABLE','reason':'Aggregate reference has no actual modeled-job count head; Tweedie latent jumps are not job counts'}, {'status':'NOT_APPLICABLE','reason':'Aggregate reference has no job severity head'}
    flat=np.flatnonzero(np.repeat(m['EXPOSED_EVALUATION'],48));pp=take(p,flat);n=a['count'].ravel()[flat];mu=pp['mu'];r=pp['r']
    zero=np.exp(nb_logpmf(np.zeros_like(n),mu,r));q90=ss.nbinom.ppf(.9,r,r/(r+mu));q95=ss.nbinom.ppf(.95,r,r/(r+mu));large=n>reg['count_large_threshold']
    cm={'MAE':float(np.abs(n-mu).mean()),'RMSE':float(np.sqrt(np.mean((n-mu)**2))),'bias':float((mu-n).mean()),
      'NB_deviance':float(np.mean(2*(special.xlogy(n,n/np.maximum(mu,1e-12))-(n+r)*np.log((n+r)/(mu+r))))),
      'mean_predictive_log_likelihood':float(nb_logpmf(n,mu,r).mean()),'actual_zero_rate':float((n==0).mean()),
      'predicted_zero_rate':float(zero.mean()),'zero_Brier':float(np.mean((zero-(n==0))**2)),
      'P90_coverage':float((n<=q90).mean()),'P95_coverage':float((n<=q95).mean()),
      'large_count_threshold_TRAIN':reg['count_large_threshold'],'large_count_N':int(large.sum()),
      'large_count_recall_using_predicted_P90':float((q90[large]>reg['count_large_threshold']).mean()) if large.any() else None}
    ix=a['job_interval'];mask=np.repeat(m['EXPOSED_EVALUATION'],48)[ix];z=a['severity'][mask];jp=take(p,ix[mask])
    q50=severity_ppf(.5,jp);q90s=severity_ppf(.9,jp);u=reg['severity_split_u_GPUh'];above=z>u
    f=severity_cdf(u,jp);tp=1-f;tq=severity_ppf(f+.9*(1-f),jp);top=z>=reg['severity_top1_TRAIN_threshold']
    sm={'N':len(z),'log_MAE':float(np.abs(np.log(z)-np.log(q50)).mean()),'median_absolute_log_error':float(np.median(np.abs(np.log(z)-np.log(q50)))),
      'Q50_pinball':float(pinball(z,q50,.5).mean()),'Q90_pinball':float(pinball(z,q90s,.9).mean()),'Q90_coverage':float((z<=q90s).mean()),
      'exceedance_observed_fraction':float(above.mean()),'exceedance_predicted_mean':float(tp.mean()),
      'exceedance_probability_calibration_error':float(abs(tp.mean()-above.mean())),'exceedance_Brier':float(np.mean((tp-above)**2)),
      'tail_conditional_Q90_pinball':float(pinball(z[above],tq[above],.9).mean()),'tail_conditional_Q90_coverage':float((z[above]<=tq[above]).mean()),
      'top1_percent_TRAIN_threshold_GPUh':reg['severity_top1_TRAIN_threshold'],'top1_severity_N':int(top.sum()),
      'top1_unconditional_Q90_coverage':float((z[top]<=q90s[top]).mean()),
      'mean_log_likelihood':float(severity_logpdf(z,jp).mean()),
      'tail_conditional_mean_log_likelihood':float((severity_logpdf(z,jp)[above]-np.log(tp[above])).mean()),
      'future_job_metadata_predictors':False}
    return cm,sm

def main():
    reg,prereg,a,info,m=load();path='dayahead/artifacts/v40r4_compound_gpuwork_arrival/V40R4_STRONGEST_BASELINE_SELECTION.json'
    committed=subprocess.check_output(['git','show','HEAD:'+path],cwd=ROOT)
    assert hashlib.sha256(committed).hexdigest()==sha(OUT/'V40R4_STRONGEST_BASELINE_SELECTION.json')
    baseline_commit=git('log','-1','--format=%H','--',path);frozen=read('V40R4_STRONGEST_BASELINE_SELECTION.json')
    mc=read('V40R4_MONTE_CARLO_CONVERGENCE.json')['models'];testdays=np.flatnonzero(m['EXPOSED_EVALUATION']);caldays=np.flatnonzero(m['CALIBRATION']);dates=info.operating_day.to_numpy()
    yt=a['target'][testdays];yc=a['target'][caldays];M=reg['scenario_count'];CDF=np.unique(np.r_[0,.001,.005,np.linspace(.01,.99,99),.995,.999,1.])
    results={};countresults={};severityresults={};cumulative={};calreports={};temporal={};finalq={};safety={}
    decomposition=pd.read_parquet(OUT/'interval_decomposition.parquet')
    for name in NAMES:
        directory=OUT/'fits'/name;p=load_params(directory/'selected_params.npz');fit=read(f'fits/{name}/result.json')
        rawcal=raw_quantiles(p,caldays,M);score=0. if name=='B0' else calibration(yc,rawcal[:,:,1])
        rawq=[];calq=[];rawcq=[];calcq=[];rawcdf=[];calcdf=[];moments=[]
        for day in testdays:
            draws=scenarios(p,np.arange(day*48,(day+1)*48),M,SEED+7919*int(day))
            transformed=draws.copy() if name=='B0' else calibrate(draws,score)
            rawq.append(predictive_summary(draws));calq.append(predictive_summary(transformed))
            rawcq.append(predictive_summary(np.cumsum(draws,axis=0)));calcq.append(predictive_summary(np.cumsum(transformed,axis=0)))
            rawcdf.append(np.quantile(draws,CDF,axis=1).T);calcdf.append(np.quantile(transformed,CDF,axis=1).T)
            moments.append(np.stack([draws.mean(1),draws.std(1),(draws==0).mean(1),draws.max(1)],-1))
        rawq=np.stack(rawq);calq=np.stack(calq);rawcq=np.stack(rawcq);calcq=np.stack(calcq)
        method=fit['selected']['method'];selected=rawq if method=='C0' else calq;selectedcq=rawcq if method=='C0' else calcq
        np.savez_compressed(directory/'exposed_distribution_summary.npz',days=dates[testdays],raw_q=rawq,C1_q=calq,
            raw_cumulative_q=rawcq,C1_cumulative_q=calcq,CDF_probabilities=CDF,raw_CDF_quantiles=np.stack(rawcdf),C1_CDF_quantiles=np.stack(calcdf),
            raw_moments=np.stack(moments),selected_q=selected,selected_cumulative_q=selectedcq)
        rawmet=aggregate(yt,rawq,reg['burst_GPUh']);calmet=aggregate(yt,calq,reg['burst_GPUh']);selectedmet=aggregate(yt,selected,reg['burst_GPUh'])
        selectedmet['cumulative_WAPE']=cumulative_metrics(yt,selectedcq)['WAPE']
        gate=gates(yt,selected,reg['burst_GPUh'],dates[testdays],raw=rawq if method=='C1' else None,MC_pass=mc[name]['convergence_pass'])
        bmask=yt>=reg['burst_GPUh'];mis=np.maximum(yt-selected[:,:,1],0);missindices=np.argwhere(bmask&(mis>0))
        classified=[]
        for d,k in missindices:
            flat=int(testdays[d]*48+k);row=decomposition.iloc[flat]
            classified.append({'day':dates[testdays][d],'slot':int(k),'actual_GPUh':float(yt[d,k]),'Q90_GPUh':float(selected[d,k,1]),
                'miss_GPUh':float(mis[d,k]),'N':int(row['count']),'max_severity_GPUh':float(row['max']),'classification':row.classification})
        countresults[name],severityresults[name]=component_metrics(p,a,m,reg)
        cumulative[name]={'selected':cumulative_metrics(yt,selectedcq),'C0':cumulative_metrics(yt,rawcq),'C1':cumulative_metrics(yt,calcq)}
        calreports[name]={'frozen_method':method,'C1_log_score':score,'calibration_origins':len(caldays),
           'score_population':'CALIBRATION positive intervals only; finite-sample 90% score quantile',
           'transformation':'T(z)=max(0,expm1(log1p(z)+s)) applied to entire aggregate CDF including Q50 and every scenario; raw compound sum untouched',
           'C0':rawmet,'C1':calmet,'C1_gate':gates(yt,calq,reg['burst_GPUh'],dates[testdays],raw=rawq,MC_pass=mc[name]['convergence_pass']),
           'evaluation_retuning':False,'global_additive_GPUh_margin':False}
        temporal[name]=gate['temporal'];finalq[name]=selected;results[name]=selectedmet;safety[name]=gate
        report={'candidate':name,'status':'EXPOSED_STRESS_EVALUATION','selected_development_pipeline':fit['selected'],
          'preregistration_commit':prereg,'strongest_baseline_commit':baseline_commit,'raw':rawmet,'calibrated':calmet,
          'selected':selectedmet,'calibration':calreports[name],'safety':gate,'count_metrics':countresults[name],
          'severity_metrics':severityresults[name],'cumulative':cumulative[name],
          'worst20_burst_misses':sorted(classified,key=lambda r:-r['miss_GPUh'])[:20],
          'all_missed_burst_classifications':classified,'miss_type_counts':pd.Series([r['classification'] for r in classified]).value_counts().to_dict(),
          'scenario_distribution_assumption':'Independent intervals and independent jobs conditional on causal shared context and predicted intensity; no fitted residual temporal copula'}
        dump(f'V40R4_{REPORT[name]}_REPORT.json',report)
        print('FINAL',name,method,'primary',round(selectedmet['primary'],6),'coverage',[round(selectedmet['probabilistic'][n]['coverage'],4) for n in ['overall','positive','burst']],'safe',gate['all_pass'],flush=True)
    base=frozen['strongest_baseline'];eligible=[n for n in NAMES if n!='P1' and safety[n]['all_pass']]
    if safety['P1']['all_pass']:
        boot=bootstrap(yt,finalq[base][:,:,1],finalq['P1'][:,:,1]);boot.update(status='EXECUTED_ON_EXPOSED_HISTORY',baseline=base)
        better=all(results['P1']['primary']<results[n]['primary'] for n in eligible)
        wins=boot['superiority'] and better
    else:boot={'status':'NOT_EXECUTED_CCAF_FAILED_SAFETY_OR_CALIBRATION','baseline':base,'delta':None,'CI95':None,'superiority':False};better=False;wins=False
    boot['baseline_commit']=baseline_commit;dump('V40R4_PAIRED_BOOTSTRAP_SUPERIORITY.json',boot)
    if wins:selected='P1';classification='V40R4_CCAF_PREVALIDATED'
    elif eligible:selected=min(eligible,key=lambda n:(*rank(results[n]),reg['simplicity_order'].index(n)));classification='V40R4_EXISTING_COMPOUND_MODEL_SELECTED'
    elif not any(s['all_pass'] for s in safety.values()):selected=None;classification='V40R4_COMPOUND_GPUWORK_SAFETY_FAIL'
    else:selected=None;classification='V40R4_CCAF_SUPERIORITY_NOT_ESTABLISHED'
    dump('V40R4_METHOD_SELECTION.json',{'classification':classification,'selected_model':selected,'CCAF_PASS':safety['P1']['all_pass'],
       'CCAF_superiority':wins,'CCAF_beats_all_eligible_benchmarks':better,'strongest_development_baseline':base,
       'EVT_supported':False,'untouched_confirmation':False,'no_post_evaluation_retuning':True,'selection_hierarchy':reg['selection_hierarchy']})
    dump('V40R4_MODEL_FREEZE.json',{'selected_model':selected,'classification':classification,'preregistration_commit':prereg,
       'params_SHA256':sha(OUT/'fits'/selected/'selected_params.npz') if selected else None,
       'calibration':calreports.get(selected),'production':False,'optimizer':False})
    for filename,value in [('COUNT_METRICS',countresults),('SEVERITY_METRICS',severityresults),('AGGREGATE_GPUH_METRICS',results),
       ('CALIBRATION_REPORT',calreports),('CUMULATIVE_ARRIVAL_METRICS',cumulative),('TEMPORAL_STABILITY_REPORT',temporal),('SAFETY_GATE_TABLE',safety)]:
        dump(f'V40R4_{filename}.json',{'models':value,'scope':'Exposed Dec/Jan/Feb stress blocks; selected pipelines frozen using DEVELOPMENT only'})
    dump('V40R4_BURST_METRICS.json',{'models':{n:{k:r[k] for k in ['missed_burst_GPUh','captured_burst_fraction','mean_burst_shortfall_GPUh']} for n,r in results.items()},'threshold_GPUh':reg['burst_GPUh'],'worst20_and_miss_types':'Individual candidate reports'})
    dump('V40R4_CONFIRMATORY_RESULT.json',{'status':'NOT_AVAILABLE_NOT_RUN','TRUE_CONFIRMATORY_AVAILABLE':'NO','maximum_positive_claim':'PREVALIDATED'})
    print(classification,selected)

if __name__=='__main__':main()

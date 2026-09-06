from .common import *
from .train import BASELINES,CLASSIFIERS,dates_for
from .metrics import *
from scipy import stats as ss

def compact(row):return {k:v for k,v in row.items() if not isinstance(v,(dict,list))}
def main():
    reg,pre=authority();a,i,m=data();f=read('V40R5_CAL_SELECTION_FREEZE.json');fpath='dayahead/artifacts/v40r5_15min_selective_burst_gpuwork/V40R5_CAL_SELECTION_FREEZE.json'
    committed=subprocess.check_output(['git','show','HEAD:'+fpath],cwd=ROOT);assert hashlib.sha256(committed).hexdigest()==sha(ROOT/fpath)
    for path,h in f['artifact_hashes'].items():assert sha(ROOT/path)==h,path
    selection_commit=git('log','-1','--format=%H','--',fpath);baseline=read('V40R5_DEVELOPMENT_BASELINE_FREEZE.json')['strongest_baseline']
    y=a['y'];u=reg['burst_threshold_GPUh'];days=dates_for(i);test=m['EXPOSED_EVALUATION'];yt=y[test];td=days[test]
    pred=np.load(OUT/'frozen_pipeline_predictions.npz');chosen=f['frozen_diagnostic_pipeline'];q=pred['body_selected'];safe=pred['selected_safe'];prob=pred['burst_probability']
    baselines={};basegates={}
    for name in BASELINES:
        b=np.load(OUT/'fits'/name/'selected_q.npy');metric=aggregate(yt,b[test,0],b[test,1],u);gate=safety(yt,b[test,0],b[test,1],u,td)
        r={'candidate':name,'selected_trial':read(f'fits/{name}/result.json')['selected']['trial'],'DEVELOPMENT_frozen':True,'EXPOSED_EVALUATION':metric,'safety':gate,'cumulative_reserve':cumulative_reserve(yt,b[test,1]),'CAL_metrics':aggregate(y[m['CALIBRATION']],b[m['CALIBRATION'],0],b[m['CALIBRATION'],1],u)}
        if name=='B3':
            trial=r['selected_trial'];sc=np.load(OUT/'fits/B3'/f'trial_{trial}_distribution.npz')['cumulative_q'][test].reshape(-1,96,2)
            actual=yt.reshape(-1,96).cumsum(1);r['true_scenario_cumulative_Q50_WAPE']=np.abs(actual-sc[:,:,0]).sum()/actual.sum();r['true_scenario_cumulative_horizon_crossing']=int((np.diff(sc,axis=1)<-1e-7).sum());r['scenario_semantics']='10,000 independent compound Poisson-Gamma draws, sum increments within scenario before cumulative quantiles'
        dump(f'V40R5_BASELINE_{name}_REPORT.json',r);baselines[name]=r;basegates[name]=gate
        print('Exposed baseline',name,metric['primary'],gate['all_pass'],flush=True)
    bodyrows=[];body={}
    for role in ['DEVELOPMENT','CALIBRATION','EXPOSED_EVALUATION']:
        ix=m[role];body[role]={}
        for name,key in [('BC0','body_raw'),('BC1','body_BC1')]:
            r=body_metrics(y[ix],pred[key][ix],u,days[ix]);body[role][name]=r
            v=r['metrics'];bodyrows.append({'role':role,'calibration':name,'oracle_BODY_N':v['N'],'Q90_coverage':v['coverage']['overall']['value'],'positive_Q90_coverage':v['coverage']['positive']['value'],
              'primary':v['primary'],'Q50_WAPE':v['point_q50']['WAPE'],'Q50_MAE':v['point_q50']['MAE'],'bias':v['point_q50']['bias'],'overprediction_GPUh':v['overprediction_GPUh'],'underprediction_GPUh':v['underprediction_GPUh'],'safety_PASS':r['all_pass']})
    dump('V40R5_BODY_MODEL_REPORT.json',{'model':'PB1','selected_calibration':chosen['body_calibration'],'roles':body,'selected_model':f['selected_model'],'oracle_body_not_used_as_inference_gate':True})
    pd.DataFrame(bodyrows).to_csv(OUT/'V40R5_BODY_METRICS.csv',index=False)
    count=np.load(OUT/'fits/N1/predictions.npz');high=reg['N_high'];countrows=[]
    for role in ['DEVELOPMENT','CALIBRATION','EXPOSED_EVALUATION']:
        ix=m[role];actual=a['n'][ix];large=actual>high
        for name in ['N0','N1']:
            p=count[name][ix];stats=point(actual,p[:,0]);stats.update(role=role,model=name,large_count_N=int(large.sum()),N_high=high,P90_coverage=float((actual<=p[:,1]).mean()),
              large_count_recall_using_P90=float((p[large,1]>high).mean()) if large.any() else None,large_count_PR_AUC=average_precision_score(large,p[:,2]),large_count_ROC_AUC=roc_auc_score(large,p[:,2]),probability_Brier=brier_score_loss(large,p[:,2]))
            if name=='N1':
                r=read('fits/N1/audit.json')['runs'][0]['dispersion_r'];stats['mean_NB_log_likelihood']=ss.nbinom.logpmf(actual,r,r/(r+p[:,0])).mean()
            countrows.append(stats)
    pd.DataFrame(countrows).to_csv(OUT/'V40R5_COUNT_RISK_METRICS.csv',index=False)
    dump('V40R5_COUNT_RISK_MODEL_REPORT.json',{'auxiliary_for_classifier':'N1','comparison':countrows,'TRAIN_stack_audit':read('fits/N1/audit.json'),'future_realized_N_predictor':False})
    classrows=[];classifiers={};sensitivity={}
    for name in CLASSIFIERS:
        p=np.load(OUT/'fits'/name/'selected_prob.npy');eta=f['eta'][name]['eta'];classifiers[name]={}
        for role in ['DEVELOPMENT','CALIBRATION','EXPOSED_EVALUATION']:
            ix=m[role];v=detector(y[ix],p[ix],eta,u);classifiers[name][role]=v;classrows.append({'role':role,'model':name,**compact(v)})
        sensitivity[name]=detector(yt,p[test],f['eta95_sensitivity'][name]['eta'],u)
    pd.DataFrame(classrows).to_csv(OUT/'V40R5_BURST_CLASSIFIER_METRICS.csv',index=False)
    dump('V40R5_BURST_CLASSIFIER_DIAGNOSTICS.json',{'models':classifiers,'eta95_sensitivity':sensitivity,'sensitivity_selection_effect':'NONE'})
    ev=aggregate(yt,q[test,0],safe[test],u);gate=safety(yt,q[test,0],safe[test],u,td);cum=cumulative_reserve(yt,safe[test])
    det=classifiers[chosen['classifier']]['EXPOSED_EVALUATION'];bodygate=body['EXPOSED_EVALUATION'][chosen['body_calibration']]['all_pass']
    all_pass=f['selected_model'] is not None and bodygate and det['gate_PASS'] and gate['all_pass']
    if not any(v['all_pass'] for v in f['body_CAL_audits'].values()) or not bodygate:classification='V40R5_BODY_FORECAST_INSUFFICIENT'
    elif not det['gate_PASS'] or not any(v['CAL_metrics']['gate_PASS'] for v in f['eta'].values()):classification='V40R5_BURST_DETECTION_FAIL'
    else:classification='V40R5_SELECTIVE_GPUWORK_SAFETY_FAIL'
    selected=None;boot={'status':'NOT_EXECUTED_SAFETY_FAIL','CI95':None,'superiority':False,'comparator':baseline,'selection_commit':selection_commit}
    if all_pass:
        b=np.load(OUT/'fits'/baseline/'selected_q.npy');boot={**block_bootstrap(yt,b[test,1],safe[test]),'status':'EXPOSED_PREVALIDATION_ONLY','comparator':baseline,'selection_commit':selection_commit}
        better=all(ev['primary']<v['EXPOSED_EVALUATION']['primary'] for name,v in baselines.items() if basegates[name]['all_pass'])
        if boot['superiority'] and better:selected=chosen['id'];classification='V40R5_15MIN_SELECTIVE_GPUWORK_PREVALIDATED'
        else:classification='V40R5_SELECTIVE_GPUWORK_SUPERIORITY_NOT_ESTABLISHED'
    dump('V40R5_SUPERIORITY_BOOTSTRAP.json',boot)
    dump('V40R5_HYBRID_METRICS.json',{'diagnostic_pipeline':chosen['id'],'selected_model':selected,'classification':classification,'metrics':ev,'safety':gate,'detector':det,
      'body_safety_PASS':bodygate,'cumulative_reserve':cum,'selected_safe_semantics':'Risk-triggered robust envelope or body Q90; NOT universally a calibrated Q90','selection_commit':selection_commit})
    dump('V40R5_TEMPORAL_STABILITY.json',{'hybrid':gate['temporal'],'baselines':{n:r['safety']['temporal'] for n,r in baselines.items()},'body':body,'CAL_combinations':f['combinations']})
    missed=(yt>u)&(yt>safe[test]);allbursts=yt>u;flat=np.flatnonzero(test);indices=np.flatnonzero(missed)
    missrows=pd.DataFrame({'operating_day':td[indices],'slot15':flat[indices]%96+1,'actual_GPUh':yt[indices],'safe_GPUh':safe[test][indices],
      'shortfall_GPUh':yt[indices]-safe[test][indices],'burst_probability':prob[test][indices],'burst_flag':pred['flag'][test][indices],
      'false_negative':~pred['flag'][test][indices],'actual_N_label_only':a['n'][test][indices]}).sort_values('shortfall_GPUh',ascending=False)
    missrows.to_csv(OUT/'V40R5_MISSED_BURST_REPORT.csv',index=False)
    # Detector misses and envelope shortfalls are distinct and separately retained.
    fn=(yt>u)&~pred['flag'][test];worst=np.flatnonzero(fn);worst=worst[np.argsort(-yt[worst])][:20]
    dump('V40R5_DETECTOR_WORST20_FALSE_NEGATIVES.json',{'rows':[{'day':td[k],'slot15':int(flat[k]%96+1),'actual_GPUh':yt[k],'probability':prob[test][k],'eta':chosen['eta']} for k in worst]})
    dump('V40R5_OVERRESERVATION_REPORT.json',{'overprediction_GPUh':ev['overprediction_GPUh'],'underprediction_GPUh':ev['underprediction_GPUh'],
      'flagged_fraction':pred['flag'][test].mean(),'false_positive_flag_fraction':np.mean(pred['flag'][test]&~allbursts),'safe_reserve_total_GPUh':safe[test].sum(),'actual_total_GPUh':yt.sum(),
      'reserve_to_actual_ratio':safe[test].sum()/yt.sum(),'monthly':gate['temporal']})
    for factor,label in [(2,'30MIN'),(4,'60MIN')]:
        yy=yt.reshape(-1,factor).sum(1);ssafe=safe[test].reshape(-1,factor).sum(1);qq=q[test,0].reshape(-1,factor).sum(1)
        dump(f'V40R5_{label}_SECONDARY_DIAGNOSTIC.json',{'source':'Direct sum of consecutive 15min outputs; not a new prediction or disaggregation','primary_resolution':False,
          'intervals':len(yy),'positive_normalized_pinball_score':positive_primary(yy,ssafe),'safe_point':point(yy,ssafe),'sum_body_medians_point_diagnostic':point(yy,qq),
          'coverage':float((yy<=ssafe).mean()),'semantics':'Aggregated reserve/envelope diagnostic, NOT true marginal Q90 at the coarser resolution','total_actual_GPUh':yy.sum(),'total_safe_GPUh':ssafe.sum()})
    # Proposal is explicitly marked unusable when scientific selection fails.
    axis=pd.read_parquet(OUT/'V40R5_15MIN_TARGET_RECONSTRUCTION.parquet').loc[test,['operating_day','slot15','slot_start_UTC','slot_end_UTC']].reset_index(drop=True)
    axis['slot_start_aest']=axis.pop('slot_start_UTC').dt.tz_convert(timezone(pd.Timedelta(hours=10)))
    axis['slot_end_aest']=axis.pop('slot_end_UTC').dt.tz_convert(timezone(pd.Timedelta(hours=10)))
    values={'body_q50_gpuh':q[test,0],'body_q90_gpuh':q[test,1],'predicted_count_mean':count['N1'][test,0],'predicted_large_count_probability':count['N1'][test,2],
      'burst_threshold_gpuh':u,'burst_probability':prob[test],'burst_eta':chosen['eta'],'burst_flag':pred['flag'][test],'robust_envelope_policy':chosen['envelope'],
      'robust_upper_gpuh':pred['robust_upper'][test],'selected_safe_gpuh':safe[test],'model_id':chosen['id'],'model_sha':sha(OUT/'V40R5_CAL_SELECTION_FREEZE.json'),
      'feature_sha':sha(OUT/'data.npz'),'target_sha':sha(OUT/'V40R5_15MIN_TARGET_RECONSTRUCTION.parquet'),'proposal_only':True,'scientifically_selected':selected is not None,'optimizer_use_allowed':False}
    for k,v in values.items():axis[k]=v
    axis.to_parquet(OUT/'V40R5_OPTIMIZER_INTERFACE_PROPOSAL.parquet',index=False)
    dump('V40R5_OPTIMIZER_INTERFACE_CONTRACT.json',{'fields':list(axis.columns),'rows':len(axis),'proposal_only':True,'optimizer_calls':0,'selected_model':selected,
      'failed_pipeline_rows':'Retained as explicitly rejected diagnostic examples, not deployment forecasts','future_concept_only':'Known pending workload + future reserve <= compute capacity; no synthetic jobs, placement, migration or timing implemented'})
    feasible={}
    for role in m:
        yy=y[m[role]];body_y=yy[yy<=u];zfrac=float((body_y==0).mean());feasible[role]={'body_zero_fraction':zfrac,'minimum_overall_coverage_if_positive_coverage_90':zfrac+(1-zfrac)*.9,'both_requested_body_bands_feasible':zfrac<=.5}
    dump('V40R5_BODY_GATE_FEASIBILITY_AUDIT.json',{'identity':'Nonnegative forecasts cover all exact zero labels: C_overall=z+(1-z)*C_positive','requested_gates_unchanged':True,'roles':feasible})
    dump('V40R5_MODEL_SELECTION.json',{'classification':classification,'selected_model':selected,'frozen_rejected_diagnostic_pipeline':chosen,'body_model':'PB1','classifier':chosen['classifier'],
      'burst_threshold_GPUh':u,'eta':chosen['eta'],'envelope':chosen['envelope'],'all_mandatory_PASS':bool(all_pass),'strongest_baseline':baseline,'superiority':boot['superiority'],
      'TRUE_CONFIRMATORY_AVAILABLE':'NO','optimizer_integration':False,'PRODUCTION_READY':False,'selection_commit':selection_commit,'no_post_evaluation_tuning':True})
    dump('V40R5_MODEL_FREEZE.json',{'selected_model':selected,'classification':classification,'diagnostic_pipeline':chosen['id'],'selection_commit':selection_commit,
      'frozen_prediction_SHA256':sha(OUT/'frozen_pipeline_predictions.npz'),'preregistration_commit':pre,'production':False,'optimizer':False})
    print('FINAL',classification,selected,'safe coverage',ev['coverage'],'primary',ev['primary'],flush=True)
if __name__=='__main__':main()

"""Single frozen exposed diagnostic evaluation; never reselect or recalibrate."""
from .common import *
from .models import *
from .metrics import *

def main():
    reg,freeze,commit=selection_authority()
    assert not (OUT/'V40R6_EXPOSED_RESULTS.json').exists(),'EXPOSED evaluation executes once'
    frame,arrays=data(); X=arrays['X']; y=frame.target_GPUh.to_numpy(); ix=np.flatnonzero(role_mask(frame,'EXPOSED_EVALUATION'))
    b,support=baseline(frame,arrays,ix); support.to_parquet(OUT/'exposed_baseline_maturity.parquet',index=False)
    q=np.zeros((len(ix),2)); raw=np.zeros_like(q); u=np.zeros(len(ix)); results={}
    crossing=read('QUANTILE_CROSSING_AUDIT'); day=read('DAY_CLUSTER_SAFETY_AUDIT'); months=read('MONTHLY_STABILITY_AUDIT')
    skills=read('HYPERPARAMETER_FREEZE')['skill_by_horizon']
    repro=read('REPRODUCIBILITY_AUDIT')
    for h in HORIZONS:
        loc=(frame.iloc[ix].horizon==h).to_numpy(); hi=ix[loc]; yy=y[hi]; days=frame.iloc[hi].day.to_numpy()
        pred,rr,ca=predict_pair(OUT/'fits/final',h,X[hi]); q[loc]=pred; raw[loc]=rr
        upperhat=calibrated(pred[:,1],freeze['calibration_deltas'][h]); u[loc]=upperhat
        crossing['audits'].append({'phase':'EXPOSED_EVALUATION','horizon':h,'config':freeze['selected_config'],**ca})
        repeat,_,_=predict_pair(OUT/'reproduction',h,X[hi]); repeat_upper=calibrated(repeat[:,1],freeze['calibration_deltas'][h])
        for name,aa,bb in [('Q50',repeat[:,0],pred[:,0]),('Q90',repeat[:,1],pred[:,1]),('calibrated_upper',repeat_upper,upperhat)]:
            diff=np.abs(aa-bb); assert diff.max()<=1e-10
            repro.setdefault('exposed_repeat_predictions',[]).append({'horizon':h,'output':name,'max_difference':diff.max(),'mean_difference':diff.mean()})
        hb=b[loc]; baseline_under=float(np.maximum(yy-hb[:,2],0).sum())
        anchor=freeze['TRAIN_Q95_anchors'][h]['TRAIN_Q95']; anchor_over=float(np.maximum(anchor-yy,0).sum())
        candidates={}
        for c,(q50,upperhat) in {'U0':(hb[:,1],hb[:,2]),'U1':(pred[:,0],pred[:,1]),'U2':(pred[:,0],u[loc])}.items():
            m=upper(yy,upperhat,days); mm=monthly(yy,q50,upperhat,days)
            gate=gates(m,mm,anchor_over,skills[h]['PASS'],baseline_under,c!='U0',True)
            candidates[c]={'central':central(yy,q50),'upper':m,'monthly':mm,'gates':gate}
            day['rows'] += [{'phase':'EXPOSED_EVALUATION','horizon':h,'candidate':c,**r} for r in m['day_clusters']]
            months['rows'] += [{'phase':'EXPOSED_EVALUATION','horizon':h,'candidate':c,**r} for r in mm]
        frozen=freeze['selected_candidates'][h]
        results[h]={'frozen_selected_candidate':frozen,'selected_pass':frozen!='NONE' and candidates[frozen]['gates']['PASS'],
            'candidates':candidates,'NONE_has_no_selected_forecast':True,'B0_central':central(yy,hb[:,0]),
            'TRAIN_Q95_anchor_over_GPUh':anchor_over,'baseline_under_GPUh':baseline_under}
    primary=all(results[h]['selected_pass'] for h in PRIMARY); full=all(v['selected_pass'] for v in results.values())
    baseline_only=primary and all(freeze['selected_candidates'][h]=='U0' for h in PRIMARY)
    if not primary: classification='V40R6_MULTI_HORIZON_GPUWORK_SAFETY_FAIL'
    elif baseline_only: classification='V40R6_SEASONAL_BASELINE_REMAINS_SELECTED'
    elif full: classification='V40R6_FULL_MULTI_HORIZON_GPUWORK_PREVALIDATED'
    else: classification='V40R6_PRIMARY_MULTI_HORIZON_GPUWORK_PREVALIDATED'
    np.savez_compressed(OUT/'exposed_predictions.npz',row_ids=ix,baseline=b,q=q,raw=raw,upper=u)
    dump('EXPOSED_RESULTS',{'classification':classification,'time_UTC':utc(),'selection_freeze_commit':commit,'scope':'EXPOSED DIAGNOSTIC EVIDENCE',
        'TRUE_CONFIRMATORY_AVAILABLE':'NO','primary_safety':primary,'full_multi_horizon_safety':full,'by_horizon':results,
        'selected_candidates_unchanged':freeze['selected_candidates'],'reselection':False,'recalibration':False,'post_freeze_refit':False,
        'optimizer_integration':'NO','production_ready':'NO','holds':HOLDS})
    dump('QUANTILE_CROSSING_AUDIT',crossing); dump('DAY_CLUSTER_SAFETY_AUDIT',day); dump('MONTHLY_STABILITY_AUDIT',months)
    dump('EXPOSED_REPRODUCIBILITY_AUDIT',{'rows':repro['exposed_repeat_predictions'],'PASS':True,'new_refits':0})
    metric_tables(frame,y)
    shape_diagnostic()
    interface(frame,ix,b,q,u,freeze,primary)
    if primary: bootstrap(frame,ix,b,q,u,freeze)
    else: dump('BOOTSTRAP_STATUS',{'status':'NOT_EXECUTED_SAFETY_FAIL','resampling_unit':'calendar day','draws':0})
    print(json.dumps(clean({'classification':classification,'primary':primary,'full':full,
        'frozen_candidates':freeze['selected_candidates'],'exposed_diagnostic_coverage':{h:{c:v['upper']['positive_coverage'] for c,v in r['candidates'].items()} for h,r in results.items()}}),indent=2),flush=True)

def metric_tables(frame,y):
    q50rows=[]; q90rows=[]; underrows=[]; overrows=[]
    selected=read('HYPERPARAMETER_FREEZE')['selected_config']
    d=np.load(OUT/'development_baselines.npz')
    phases=[('DEVELOPMENT',{'row_ids':d['row_ids'],'baseline':d['predictions'],'q':np.load(OUT/'fits'/selected/'development_q.npy')})]
    cp=np.load(OUT/'calibration_predictions.npz')
    for role in ['CAL_FIT','CAL_SELECT']:
        mask=(frame.iloc[cp['row_ids']].analysis_role==role).to_numpy()
        phases.append((role,{k:cp[k][mask] for k in cp.files}))
    phases.append(('EXPOSED_EVALUATION',np.load(OUT/'exposed_predictions.npz')))
    for role,p in phases:
        ix=p['row_ids']; b=p['baseline']; q=p['q']
        for h in HORIZONS:
            m=(frame.iloc[ix].horizon==h).to_numpy(); yy=y[ix][m]; dates=frame.iloc[ix[m]].day.to_numpy()
            for family,pred in [('B0',b[m,0]),('B1',b[m,1]),('B2',q[m,0])]:
                metrics=central(yy,pred)
                q50rows.append({'phase':role,'horizon':h,'family':family,**metrics['overall'],
                    **{'positive_'+k:v for k,v in metrics['positive'].items()},'H24_daily_total_error':h=='H24'})
            candidates={'U0':b[m,2],'U1':q[m,1]}
            if 'upper' in p: candidates['U2']=p['upper'][m]
            for candidate,pred in candidates.items():
                metrics=upper(yy,pred,dates)
                record={'phase':role,'horizon':h,'candidate':candidate,**{k:v for k,v in metrics.items() if k not in ['day_clusters','safe_actual_ratio']},
                    **{'safe_actual_ratio_'+k:v for k,v in metrics['safe_actual_ratio'].items()}}
                q90rows.append(record)
                underrows.append({k:v for k,v in record.items() if k in ['phase','horizon','candidate','under_GPUh','positive_under_GPUh']})
                overrows.append({k:v for k,v in record.items() if k in ['phase','horizon','candidate','over_GPUh','positive_over_GPUh','positive_WAPE']})
    csv('Q50_RESULTS',q50rows); csv('Q90_RESULTS',q90rows)
    dump('UNDERPREDICTION_AUDIT',{'rows':underrows,'unit':'GPUh over rolling windows; overlapping work counted repeatedly'})
    dump('OVERRESERVATION_AUDIT',{'rows':overrows,'catastrophic_positive_WAPE_threshold':3,'labels_clipped':False,'predictions_upper_clipped':False})

def shape_diagnostic():
    # Existing R5 DEV-selected full-target baseline central quantile only.
    saved=R5/'fits/B3/selected_q.npy'; q=np.load(saved)[:,0]
    a=np.load(R5/'data.npz'); ledger=pd.read_parquet(R5/'inputs/V40R3_LABEL_MATURITY_LEDGER.parquet')
    results={}
    for role in ['DEVELOPMENT','CALIBRATION','EXPOSED_EVALUATION']:
        ix=np.repeat(((ledger.role==role)&ledger.stage_maturity_eligible).to_numpy(),96)
        results[role]=central(a['y'][ix],q[ix])
    dump('15MIN_SHAPE_DIAGNOSTIC',{'status':'SHAPE_ONLY','source':'Frozen R5 DEV-selected B3 full-target Q50',
        'prediction_SHA256':sha(saved),'new_R6_family':False,'new_model_fits':0,'15MIN_SAFETY_FORECAST':False,
        'Q90_burst_safety_claim':False,'results':results})

def interface(frame,ix,b,q,u,freeze,primary):
    rows=[]; modelhash=hashlib.sha256(json.dumps(freeze['frozen_hashes'],sort_keys=True).encode()).hexdigest()
    if primary:
        sub=frame.iloc[ix]
        for d in sub.day.unique():
            row={'day':d,'issue_time':str(sub[sub.day==d].issue_time.iloc[0]),'window_start_slot':0,
                'proposal_only':True,'optimizer_use_allowed':False,'model_sha256':modelhash,'feature_contract_sha256':sha(OUT/'V40R6_FEATURE_CONTRACT.json')}
            for h in HORIZONS:
                loc=np.flatnonzero(((sub.day==d)&(sub.horizon==h)&(sub.window_start_slot==0)).to_numpy())[0]
                c=freeze['selected_candidates'][h]
                row[h+'_q50']=float(b[loc,1] if c=='U0' else q[loc,0]); row[h+'_q90']=float(b[loc,2] if c=='U0' else q[loc,1])
                row[h+'_upper']=None if c=='NONE' else float(b[loc,2] if c=='U0' else q[loc,1] if c=='U1' else u[loc])
                row['selected_candidate_'+h]=c; row['calibration_delta_'+h]=freeze['calibration_deltas'][h]
            rows.append(row)
    dump('OPTIMIZER_INTERFACE_PROPOSAL',{'recommended_rows':rows,'proposal_only':True,'optimizer_use_allowed':False,
        'window_semantics':'Prefix cumulative forecasts beginning at slot 0 for each historical exposed day; no synthetic future jobs',
        'service_work_mass_unit':'GPUh','not_instantaneous_GPU_occupancy_or_power':True,
        'future_equation_only':'B[t+1]=B[t]+A[t]-S[t]; S[t]=0.25*r[t] at 15min; not implemented',
        'primary_success':primary})

def bootstrap(frame,ix,b,q,u,freeze):
    rng=np.random.default_rng(SEED); rows=[]
    for h in PRIMARY:
        mask=(frame.iloc[ix].horizon==h).to_numpy(); hi=ix[mask]; yy=frame.iloc[hi].target_GPUh.to_numpy(); dates=frame.iloc[hi].day.to_numpy()
        c=freeze['selected_candidates'][h]; hb=b[mask]; hq=q[mask]; hu=u[mask]
        qsel=hb[:,1] if c=='U0' else hq[:,0]; usel=hb[:,2] if c=='U0' else hq[:,1] if c=='U1' else hu
        contributions=[]
        for day in np.unique(dates):
            m=dates==day; yday=yy[m]
            contributions.append([m.sum(),float((np.abs(qsel[m]-yday)-np.abs(hb[m,1]-yday)).sum()),
                float((pinball(yday,usel[m])-pinball(yday,hb[m,2])).sum()),
                float((np.maximum(yday-usel[m],0)-np.maximum(yday-hb[m,2],0)).sum()),
                float((np.maximum(usel[m]-yday,0)-np.maximum(hb[m,2]-yday,0)).sum())])
        a=np.asarray(contributions); draws=[]
        for _ in range(1000):
            sampled=a[rng.integers(len(a),size=len(a))].sum(0)
            draws.append([sampled[1]/sampled[0],sampled[2]/sampled[0],sampled[3],sampled[4]])
        vals=np.asarray(draws)
        for j,metric in enumerate(['Q50_MAE','Q90_pinball','under_GPUh','over_GPUh']):
            rows.append({'horizon':h,'metric':metric,'difference':'selected minus B1','percentile_95CI':np.quantile(vals[:,j],[.025,.975]),'mean':vals[:,j].mean()})
    dump('BOOTSTRAP_STATUS',{'status':'EXECUTED_PRIMARY_SAFETY_PASS','draws':1000,'seed':SEED,'unit':'calendar day',
        'overlapping_windows_independently_resampled':False,'rows':rows,'confirmatory':False})

if __name__=='__main__': main()

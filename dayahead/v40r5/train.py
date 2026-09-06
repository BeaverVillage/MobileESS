from .common import *
from .models import *
from .metrics import *
import argparse
BASELINES=['B0','B1','B2','B3']
CLASSIFIERS=['C0','C1','C2','C3']
def dates_for(i):return np.repeat(i.operating_day.to_numpy(),96)
def count_stage(a,i,m,directory):
    directory.mkdir(parents=True,exist_ok=True);high=read('V40R5_BURST_THRESHOLD_FREEZE.json')['N_high']
    cq,mean=seasonal(a['seasonal_n'],a['seasonal_mask']);v=a['seasonal_mask'];large=np.sum((a['seasonal_n']>high)&v,axis=1)/np.maximum(v.sum(1),1)
    n0=np.column_stack([mean,cq[:,1],large]);p,meta=fit_count(a['X'],a['n'],m['TRAIN'],high,directory)
    cross=p.copy();folds=[];runs=[meta];train_days=np.flatnonzero(m['TRAIN'].reshape(-1,96)[:,0])
    for fold,days in enumerate(np.array_split(train_days,5)):
        dest=np.concatenate([np.arange(day*96,(day+1)*96) for day in days]);cut=i.forecast_origin.iloc[days[0]]
        train=m['TRAIN']&np.repeat(i.target_label_available_at.le(cut).to_numpy(),96)&(a['origin_ns']<cut.value)
        if train.sum()<96*10:cross[dest]=n0[dest];used='N0 causal mature seasonal warm-up'
        else:
            pred,run=fit_count(a['X'],a['n'],train,high,directory,tag=f'fold_{fold}');cross[dest]=pred[dest];runs.append(run);used='N1 past-mature expanding fold'
        folds.append({'fold':fold,'first_day':i.operating_day.iloc[days[0]],'last_day':i.operating_day.iloc[days[-1]],'prediction_rows':len(dest),'training_rows':int(train.sum()),'fit_label_cutoff':cut,'method':used,
          'max_training_label_available_at':i.loc[train.reshape(-1,96)[:,0],'target_label_available_at'].max() if train.any() else None})
    np.savez_compressed(directory/'predictions.npz',N0=n0,N1=p,TRAIN_crossfit_N1=cross)
    return n0,p,cross,folds,runs
def model_rank(y,q,u,days):
    s=safety(y,q[:,0],q[:,1],u,days);v=aggregate(y,q[:,0],q[:,1],u)
    return (not s['all_pass'],v['primary'],v['missed_burst_GPUh'],v['overprediction_GPUh'])
def fit_stage():
    reg,c=authority();a,i,m=data();u=reg['burst_threshold_GPUh'];X=a['X'];y=a['y'];days=dates_for(i);dev=m['DEVELOPMENT'];runs=[]
    assert read('V40R5_PREFIT_TEST_REPORT.json')['failed']==0
    for name in BASELINES+['PB1']:
        directory=OUT/'fits'/name;directory.mkdir(parents=True,exist_ok=True)
        if (directory/'result.json').exists():runs.extend(read(f'fits/{name}/result.json')['runs']);continue
        choices=[];metadata=[]
        for trial in range(1 if name in ['B0','B1'] else 2):
            dump(f'fits/{name}/trial_{trial}_start.json',{'preregistration_commit':c,'UTC':datetime.now(timezone.utc),'seed':SEED})
            if name=='B0':q=np.zeros((len(y),2));meta={'candidate':name,'trial':0,'fit_time_seconds':0.,'prediction_time_seconds':0.,'parameter_fits':0}
            elif name=='B1':
                t=time.monotonic();q,_=seasonal(a['seasonal_w'],a['seasonal_mask']);meta={'candidate':name,'trial':0,'fit_time_seconds':0.,'prediction_time_seconds':time.monotonic()-t,'parameter_fits':0}
            else:q,meta=fit_forecaster(name,trial,X,y,m['TRAIN'],u,directory)
            np.save(directory/f'trial_{trial}_q.npy',q);metadata.append(meta)
            if name=='PB1':v=body_metrics(y[dev],q[dev],u,days[dev]);rank=(not v['all_pass'],v['metrics']['primary'],v['metrics']['overprediction_GPUh'])
            else:v=aggregate(y[dev],q[dev,0],q[dev,1],u);rank=model_rank(y[dev],q[dev],u,days[dev])
            choices.append({'trial':trial,'DEVELOPMENT_metrics':v,'rank':rank})
            print('Fit',name,trial,'DEV primary',v.get('primary',v.get('metrics',{}).get('primary')),flush=True)
        selected=min(choices,key=lambda x:x['rank']);np.save(directory/'selected_q.npy',np.load(directory/f'trial_{selected["trial"]}_q.npy'))
        dump(f'fits/{name}/result.json',{'selected':selected,'trials':choices,'runs':metadata,'preregistration_commit':c,'final_outcomes_read':False});runs.extend(metadata)
    basemetrics={n:read(f'fits/{n}/result.json')['selected'] for n in BASELINES};best=min(BASELINES,key=lambda n:basemetrics[n]['rank'])
    dump('V40R5_DEVELOPMENT_BASELINE_FREEZE.json',{'strongest_baseline':best,'pipelines':basemetrics,'calibration':'BC0 fixed for baseline registry','scope':'DEVELOPMENT only','before_CAL_hybrid_selection':True,'preregistration_commit':c})
    directory=OUT/'fits/N1'
    if not (directory/'audit.json').exists():
        n0,p,cross,folds,cruns=count_stage(a,i,m,directory);dump('fits/N1/audit.json',{'folds':folds,'runs':cruns,'TRAIN_classifier_count_features':'Causal expanding-fold prediction; N0 warm-up when fewer than10 mature days','future_realized_N_input':False})
    else:
        pred=np.load(directory/'predictions.npz');n0=pred['N0'];p=pred['N1'];cross=pred['TRAIN_crossfit_N1'];cruns=read('fits/N1/audit.json')['runs']
    runs.extend(cruns);cx=np.column_stack([X,np.log1p(cross[:,0]),cross[:,2]]).astype(np.float32);np.save(OUT/'classifier_X.npy',cx)
    for name in CLASSIFIERS:
        directory=OUT/'fits'/name;directory.mkdir(exist_ok=True)
        if (directory/'result.json').exists():runs.extend(read(f'fits/{name}/result.json')['runs']);continue
        choices=[];metadata=[]
        for trial in range(1 if name=='C0' else 2):
            dump(f'fits/{name}/trial_{trial}_start.json',{'preregistration_commit':c,'UTC':datetime.now(timezone.utc),'seed':SEED})
            p,meta=fit_classifier(name,trial,cx,y>u,m['TRAIN'],directory);v=detector(y[dev],p[dev],.5,u)
            choices.append({'trial':trial,'DEVELOPMENT_metrics_threshold_05_diagnostic_only':v,'rank':[-v['PR_AUC'],v['Brier'],trial]});metadata.append(meta)
        selected=min(choices,key=lambda r:r['rank']);np.save(directory/'selected_prob.npy',np.load(directory/f'trial_{selected["trial"]}_prob.npy'))
        dump(f'fits/{name}/result.json',{'selected':selected,'trials':choices,'runs':metadata,'eta_not_selected_on_DEVELOPMENT':True,'preregistration_commit':c});runs.extend(metadata)
        print('Classifier',name,'DEV PR AUC',-selected['rank'][0],flush=True)
    dump('V40R5_FIT_LEDGER.json',{'runs':runs,'all_fits_after_preregistration':c,'models':'15min refits only; no parent model weights imported'})

def calibration_stage():
    reg,c=authority();a,i,m=data();y=a['y'];u=reg['burst_threshold_GPUh'];cal=m['CALIBRATION'];days=dates_for(i)
    q=np.load(OUT/'fits/PB1/selected_q.npy');bodycal=cal&(y<=u);score=log_score(y[bodycal],q[bodycal,1]);bodies={'BC0':q,'BC1':calibrate_body(q,score,u)}
    audits={k:body_metrics(y[cal],v[cal],u,days[cal]) for k,v in bodies.items()}
    count=np.load(OUT/'fits/N1/predictions.npz');risk=count['TRAIN_crossfit_N1'][:,2]
    envelopes,er,paths=envelope_fit(y,risk,np.tile(np.arange(96),349),m['TRAIN'],cal,u)
    for k,v in er.items():dump(f'V40R5_ROBUST_ENVELOPE_{k}.json',v)
    eta={};sensitivity={};choices=[]
    for classifier in CLASSIFIERS:
        p=np.load(OUT/'fits'/classifier/'selected_prob.npy');eta[classifier]=choose_eta(y[cal],p[cal],u);sensitivity[classifier]=choose_eta(y[cal],p[cal],u,.95)
        for bc,qb in bodies.items():
            for envelope,upper in envelopes.items():
                safe=hybrid(qb,p,eta[classifier]['eta'],upper);g=safety(y[cal],qb[cal,0],safe[cal],u,days[cal]);v=aggregate(y[cal],qb[cal,0],safe[cal],u)
                passes=audits[bc]['all_pass'] and eta[classifier]['CAL_metrics']['gate_PASS'] and g['all_pass'] and er[envelope]['CAL_burst_N']>=30
                rank=[not audits[bc]['all_pass'],not eta[classifier]['CAL_metrics']['gate_PASS'],g['coverage']['positive']['gate']!='PASS',g['coverage']['burst']['gate']!='PASS',not g['all_pass'],v['primary'],v['missed_burst_GPUh'],v['overprediction_GPUh'],CLASSIFIERS.index(classifier),int(envelope[1]),bc]
                choices.append({'id':f'PB1_{bc}_{classifier}_{envelope}','body':'PB1','body_calibration':bc,'classifier':classifier,'envelope':envelope,'eta':eta[classifier]['eta'],'all_CAL_pass':bool(passes),'CAL_gate':g,'CAL_metrics':v,'rank':rank})
    eligible=[r for r in choices if r['all_CAL_pass']];frozen=min(eligible or choices,key=lambda r:r['rank'])
    selected=frozen['id'] if eligible else None
    p=np.load(OUT/'fits'/frozen['classifier']/'selected_prob.npy');b=bodies[frozen['body_calibration']];up=envelopes[frozen['envelope']];safe=hybrid(b,p,frozen['eta'],up)
    np.savez_compressed(OUT/'frozen_pipeline_predictions.npz',body_raw=q,body_selected=b,body_BC1=bodies['BC1'],burst_probability=p,robust_upper=up,selected_safe=safe,
      flag=p>=frozen['eta'],envelope_R0=envelopes['R0'],envelope_R1=envelopes['R1'],envelope_R2=envelopes['R2'],R2_path=paths)
    hashes={p.relative_to(ROOT).as_posix():sha(p) for p in (OUT/'fits').rglob('*') if p.is_file()}
    hashes[(OUT/'frozen_pipeline_predictions.npz').relative_to(ROOT).as_posix()]=sha(OUT/'frozen_pipeline_predictions.npz')
    dump('V40R5_CAL_SELECTION_FREEZE.json',{'selected_model':selected,'frozen_diagnostic_pipeline':frozen,'eligible_combinations':len(eligible),'combinations':choices,'artifact_hashes':hashes,
      'body_calibration_log_score':score,'body_CAL_audits':audits,'eta':eta,'eta95_sensitivity':sensitivity,'true_confirmation':False,'preregistration_commit':c,
      'selection_is_frozen':True,'final_exposed_diagnostics_permitted_if_no_selected_model':True,'no_favorable_promotion_if_body_or_detector_fails':True})
    dump('V40R5_ETA_SELECTION.json',{'source':'CALIBRATION ONLY','primary':eta,'95_percent_sensitivity_only':sensitivity,'chosen_diagnostic_classifier':frozen['classifier'],'selected_eta':frozen['eta'],'evaluation_tuning':False})
    dump('V40R5_BURST_CLASSIFIER_SELECTION.json',{'classifier':frozen['classifier'],'selected_model':selected,'CAL_detector':eta[frozen['classifier']]['CAL_metrics'],'model_trials':'DEVELOPMENT PR-AUC then Brier; eta CAL only','diagnostic_only':selected is None})
    dump('V40R5_ROBUST_ENVELOPE_SELECTION.json',{'envelope':frozen['envelope'],'pipeline':frozen['id'],'selected_model':selected,'CAL_combinations':[{k:r[k] for k in ['id','all_CAL_pass','CAL_metrics']} for r in choices]})
    print('CAL frozen',selected,'diagnostic',frozen['id'],'eta',frozen['eta'],'body passes',{k:v['all_pass'] for k,v in audits.items()},'eligible',len(eligible),flush=True)

def reproduce_stage():
    reg,c=authority();a,i,m=data();f=read('V40R5_CAL_SELECTION_FREEZE.json');chosen=f['frozen_diagnostic_pipeline'];directory=OUT/'reproduction';directory.mkdir(exist_ok=True)
    n0,n1,cross,folds,runs=count_stage(a,i,m,directory/'N1');oldcount=np.load(OUT/'fits/N1/predictions.npz')
    trial=read('fits/PB1/result.json')['selected']['trial'];q,meta=fit_forecaster('PB1',trial,a['X'],a['y'],m['TRAIN'],reg['burst_threshold_GPUh'],directory/'PB1',tag='repeat');runs.append(meta)
    cx=np.column_stack([a['X'],np.log1p(cross[:,0]),cross[:,2]]).astype(np.float32)
    classifier=chosen['classifier'];ct=read(f'fits/{classifier}/result.json')['selected']['trial'];p,meta=fit_classifier(classifier,ct,cx,a['y']>reg['burst_threshold_GPUh'],m['TRAIN'],directory/classifier,tag='repeat');runs.append(meta)
    first=np.load(OUT/'frozen_pipeline_predictions.npz');raw=q.copy()
    if chosen['body_calibration']=='BC1':q=calibrate_body(q,f['body_calibration_log_score'],reg['burst_threshold_GPUh'])
    envelopes,_,_=envelope_fit(a['y'],cross[:,2],np.tile(np.arange(96),349),m['TRAIN'],m['CALIBRATION'],reg['burst_threshold_GPUh'])
    safe=hybrid(q,p,chosen['eta'],envelopes[chosen['envelope']]);cal=m['CALIBRATION']
    differences={name:{'max':np.abs(a0-a1).max(),'mean':np.abs(a0-a1).mean()} for name,a0,a1 in [('count_full',oldcount['N1'],n1),('count_crossfit',oldcount['TRAIN_crossfit_N1'],cross),('body_raw',first['body_raw'],raw),('burst_probability',first['burst_probability'],p),('selected_safe',first['selected_safe'],safe)]}
    np.savez_compressed(directory/'pipeline_predictions.npz',body=q,probability=p,selected_safe=safe)
    dump('V40R5_REPRODUCIBILITY_AUDIT.json',{'role':'Independent same-seed rebuild of CAL-selected candidate, or frozen rejected diagnostic pipeline if selected_model NONE','pipeline':chosen['id'],
      'seed':SEED,'independent_rebuilds':1,'differences':differences,'CAL_primary_original':positive_primary(a['y'][cal],first['selected_safe'][cal]),'CAL_primary_repeat':positive_primary(a['y'][cal],safe[cal]),
      'all_comparisons_pass':all(v['max']<=1e-7 for v in differences.values()),'no_better_repeat_selection':True,'runs':runs,'parameters':'LightGBM model bytes checked in final artifact audit; sklearn/XGB prediction equality is primary repetition evidence'})
    print('Independent repeat differences',differences,flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['fit','calibrate','reproduce']);args=p.parse_args()
    {'fit':fit_stage,'calibrate':calibration_stage,'reproduce':reproduce_stage}[args.stage]()

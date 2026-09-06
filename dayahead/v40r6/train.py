from .common import *
from .models import *
from .metrics import *
import shutil
import sys

def fit():
    reg,pre=authority(); assert not (OUT/'fits').exists(),'Fit stage may run once only'
    frame,arrays=data(); X=arrays['X']; y=frame.target_GPUh.to_numpy(); dev=role_mask(frame,'DEVELOPMENT')
    devix=np.flatnonzero(dev); base,support=baseline(frame,arrays,devix)
    np.savez_compressed(OUT/'development_baselines.npz',row_ids=devix,predictions=base)
    support.to_parquet(OUT/'development_baseline_maturity.parquet',index=False)
    ledger=[]; scores=[]; crossings=[]
    for config in CONFIGS:
        devq=np.zeros((len(devix),2)); local_scores=[]
        for h in HORIZONS:
            tr=role_mask(frame,'TRAIN')&(frame.horizon==h).to_numpy(); de=dev&(frame.horizon==h).to_numpy()
            pair=[]
            for q in [.5,.9]:
                model,entry=fit_model(X[tr],y[tr],config,q,OUT/'fits'/config/f'{h}_Q{int(q*100)}.txt')
                ledger.append(entry); pair.append(inverse(model.predict(X[de])))
                print(f'Fit {config} {h} Q{int(q*100)}: {entry["seconds"]:.2f}s',flush=True)
            qhat,ca=repair(np.column_stack(pair)); crossings.append({'phase':'DEVELOPMENT','config':config,'horizon':h,**ca})
            loc=(frame.iloc[devix].horizon==h).to_numpy(); devq[loc]=qhat; yy=y[de]
            scale=max(float(np.mean(y[tr])),1e-12)
            for j,q in enumerate([.5,.9]):
                score={'config':config,'horizon':h,'quantile':q,'N':len(yy),'TRAIN_mean_normalizer':scale,
                    'DEVELOPMENT_pinball':float(pinball(yy,qhat[:,j],q).mean()),
                    'normalized_pinball':float(pinball(yy,qhat[:,j],q).mean()/scale),
                    'Q50_MAE':float(np.abs(yy-qhat[:,0]).mean())}
                scores.append(score); local_scores.append(score)
        np.save(OUT/'fits'/config/'development_q.npy',devq)
    df=pd.DataFrame(scores); csv('HYPERPARAMETER_RESULTS',scores)
    ranking=[]
    for simplicity,config in enumerate(CONFIGS):
        s=df[df.config==config]
        ranking.append({'config':config,'mean_normalized_pinball':s.normalized_pinball.mean(),
            'mean_Q90_normalized_pinball':s.loc[s['quantile']==.9,'normalized_pinball'].mean(),
            'mean_Q50_MAE':s.loc[s['quantile']==.5,'Q50_MAE'].mean(),'simplicity':simplicity})
    ranking.sort(key=lambda r:(r['mean_normalized_pinball'],r['mean_Q90_normalized_pinball'],r['mean_Q50_MAE'],r['simplicity']))
    selected=ranking[0]['config']; final=OUT/'fits/final'; final.mkdir(parents=True)
    for p in (OUT/'fits'/selected).glob('*.txt'): shutil.copyfile(p,final/p.name)
    qhat=np.load(OUT/'fits'/selected/'development_q.npy'); skills={}; devmetrics={}
    for h in HORIZONS:
        loc=(frame.iloc[devix].horizon==h).to_numpy(); yy=y[devix][loc]; pos=yy>0
        b1=base[loc,1:]; b2=qhat[loc]
        mae1=np.abs(yy-b1[:,0]).mean(); mae2=np.abs(yy-b2[:,0]).mean()
        pin1=pinball(yy[pos],b1[pos,1]).mean(); pin2=pinball(yy[pos],b2[pos,1]).mean()
        skills[h]={'Q50_MAE_B1':mae1,'Q50_MAE_B2':mae2,'positive_Q90_pinball_B1':pin1,'positive_Q90_pinball_B2':pin2,
            'PASS':bool(mae2<=mae1 and pin2<=pin1 and (mae2<mae1 or pin2<pin1))}
        devmetrics[h]={'B0':central(yy,base[loc,0]),'B1':central(yy,b1[:,0]),'B2':central(yy,b2[:,0])}
    dump('HYPERPARAMETER_FREEZE',{'selected_config':selected,'common_to_all_horizons':True,'selection_data':'DEVELOPMENT_ONLY',
        'ranking':ranking,'skill_by_horizon':skills,'no_CAL_or_EXPOSED_selection':True,'train_refit_on_DEV':False})
    dump('COMPUTE_LEDGER',{'fits':ledger,'fit_count':len(ledger),'optimizer_calls':0,'Gurobi_calls':0,'OpenDSS_calls':0,'Fresh_calls':0,
        'CPU_only':True,'threads':1,'seed':SEED,'model_families':['B0','B1','B2'],'timing_unit':'seconds','preregistration_commit':pre})
    dump('QUANTILE_CROSSING_AUDIT',{'audits':crossings})
    dump('B0_REPORT',{'family':'WEEKLY_SEASONAL_NAIVE','central_only':True,'ML_parameters_fitted':False,'DEVELOPMENT':{h:v['B0'] for h,v in devmetrics.items()}})
    dump('B1_REPORT',{'family':'SEASONAL_EMPIRICAL_QUANTILE','source':'causally mature TRAIN only','support_thresholds':[8,20,50,1],
        'DEVELOPMENT':{h:v['B1'] for h,v in devmetrics.items()}})
    dump('B2_REPORT',{'family':'LIGHTGBM_QUANTILE','target_transform':'log1p','config':selected,'skill':skills,
        'DEVELOPMENT':{h:v['B2'] for h,v in devmetrics.items()},'TRAIN_only_fit':True})
    print(json.dumps(clean({'ranking':ranking,'skill':skills}),indent=2),flush=True)

def select():
    authority(); assert not (OUT/'V40R6_SELECTION_FREEZE.json').exists(),'No reselection'
    frame,arrays=data(); X=arrays['X']; y=frame.target_GPUh.to_numpy()
    mask=role_mask(frame,'CAL_FIT')|role_mask(frame,'CAL_SELECT'); ix=np.flatnonzero(mask)
    base,support=baseline(frame,arrays,ix); support.to_parquet(OUT/'calibration_baseline_maturity.parquet',index=False)
    q=np.zeros((len(ix),2)); raw=np.zeros_like(q); upperhat=np.zeros(len(ix)); deltas={}; rows=[]; dayrows=[]; monthrows=[]
    crossing=read('QUANTILE_CROSSING_AUDIT'); hyper=read('HYPERPARAMETER_FREEZE'); selected={}; anchors={}; allgates={}
    for h in HORIZONS:
        loc=(frame.iloc[ix].horizon==h).to_numpy(); hi=ix[loc]
        pred,rr,ca=predict_pair(OUT/'fits/final',h,X[hi]); q[loc]=pred; raw[loc]=rr
        crossing['audits'].append({'phase':'CAL_FIT_CAL_SELECT','config':hyper['selected_config'],'horizon':h,**ca})
        cf=(frame.iloc[hi].analysis_role=='CAL_FIT').to_numpy()
        delta=calibrate(y[hi][cf],pred[cf,1]); deltas[h]={'delta':delta,'CAL_FIT_rows':int(cf.sum()),
            'CAL_FIT_days':sorted(frame.iloc[hi[cf]].day.unique()),'method':'empirical Q90 linear of log1p(y)-log1p(repaired Q90), lower bounded at zero'}
        up=calibrated(pred[:,1],delta); upperhat[loc]=up
        cs=(frame.iloc[hi].analysis_role=='CAL_SELECT').to_numpy(); si=hi[cs]; yy=y[si]; days=frame.iloc[si].day.to_numpy()
        tr=role_mask(frame,'TRAIN')&(frame.horizon==h).to_numpy(); anchor=float(np.quantile(y[tr],.95,method='linear'))
        anchor_over=float(np.maximum(anchor-yy,0).sum()); anchors[h]={'TRAIN_Q95':anchor,'TRAIN_N':int(tr.sum())}
        hbase=base[loc][cs]; results={}
        candidates={'U0':(hbase[:,1],hbase[:,2]),'U1':(pred[cs,0],pred[cs,1]),'U2':(pred[cs,0],up[cs])}
        for candidate,(q50,u) in candidates.items():
            m=upper(yy,u,days); months=monthly(yy,q50,u,days)
            gate=gates(m,months,anchor_over,hyper['skill_by_horizon'][h]['PASS'],is_B2=candidate!='U0')
            results[candidate]=gate
            rows.append({'horizon':h,'candidate':candidate,**{k:v for k,v in m.items() if k not in ['day_clusters','safe_actual_ratio']},
                'TRAIN_Q95_anchor_over_GPUh':anchor_over,'gate_PASS':gate['PASS'],'failure_reasons':'|'.join(gate['failure_reasons'])})
            dayrows += [{'phase':'CAL_SELECT','horizon':h,'candidate':candidate,**r} for r in m['day_clusters']]
            monthrows += [{'phase':'CAL_SELECT','horizon':h,'candidate':candidate,**r} for r in months]
        selected[h]=choose(results); allgates[h]=results
    np.savez_compressed(OUT/'calibration_predictions.npz',row_ids=ix,baseline=base,q=q,raw=raw,upper=upperhat)
    csv('CAL_SELECT_RESULTS',rows); dump('HORIZON_CALIBRATION',{'name':'HORIZON_SPECIFIC_LOG_RESIDUAL_UPPER_CALIBRATION',
        'scope':'CAL_FIT_ONLY','horizons':deltas,'one_delta_per_horizon':True,'guaranteed_exchangeable_conformal_coverage':False})
    dump('QUANTILE_CROSSING_AUDIT',crossing); dump('DAY_CLUSTER_SAFETY_AUDIT',{'rows':dayrows,'resampling_unit':'calendar day','overlap_warning':'Pooled sums double count work across overlapping windows'})
    dump('MONTHLY_STABILITY_AUDIT',{'rows':monthrows,'sufficient_support':'At least five positive calendar days','catastrophic_threshold':.8})
    reproduce(frame,arrays,ix,q,upperhat,deltas,hyper['selected_config'])
    hashes={p.relative_to(ROOT).as_posix():sha(p) for p in (OUT/'fits/final').glob('*.txt')}
    for name in ['features.npz','V40R6_FEATURE_CONTRACT.json','V40R6_HYPERPARAMETER_FREEZE.json','V40R6_HORIZON_CALIBRATION.json',
        'V40R6_CAL_SELECT_RESULTS.csv','calibration_predictions.npz','V40R6_REPRODUCIBILITY_AUDIT.json']:
        p=OUT/name; hashes[p.relative_to(ROOT).as_posix()]=sha(p)
    dump('SELECTION_FREEZE',{'time_UTC':utc(),'selected_config':hyper['selected_config'],'selected_candidates':selected,'gates':allgates,
        'calibration_deltas':{h:v['delta'] for h,v in deltas.items()},'TRAIN_Q95_anchors':anchors,
        'selection_scope':'CAL_SELECT_ONLY; DEVELOPMENT skill eligibility already frozen','frozen_hashes':hashes,
        'primary_horizons':PRIMARY,'secondary_horizons':SECONDARY,'primary_CAL_pass':all(selected[h]!='NONE' for h in PRIMARY),
        'full_CAL_pass':all(v!='NONE' for v in selected.values()),'exposed_evaluated':False,
        'NONE_diagnostic_rule':'Evaluate U0/U1/U2 after freeze as preregistered diagnostics; never replace NONE with an exposed winner',
        'optimizer_integration':'NO','TRUE_CONFIRMATORY_AVAILABLE':'NO'})
    print(json.dumps(clean({'selected_candidates':selected,'deltas':deltas,'gates':allgates}),indent=2),flush=True)

def reproduce(frame,arrays,ix,original_q,original_upper,deltas,config):
    ledger=read('COMPUTE_LEDGER'); y=frame.target_GPUh.to_numpy(); X=arrays['X']; results=[]
    for h in HORIZONS:
        tr=role_mask(frame,'TRAIN')&(frame.horizon==h).to_numpy(); loc=(frame.iloc[ix].horizon==h).to_numpy(); q=[]
        for alpha in [.5,.9]:
            model,entry=fit_model(X[tr],y[tr],config,alpha,OUT/'reproduction'/f'{h}_Q{int(alpha*100)}.txt')
            entry['purpose']='Independent same-seed repeat; no replicate selection'; ledger['fits'].append(entry)
            q.append(inverse(model.predict(X[ix[loc]])))
        qq,_=repair(np.column_stack(q)); u=calibrated(qq[:,1],deltas[h]['delta'])
        for name,a,b in [('Q50',qq[:,0],original_q[loc,0]),('Q90',qq[:,1],original_q[loc,1]),('calibrated_upper',u,original_upper[loc])]:
            diff=np.abs(a-b); results.append({'horizon':h,'output':name,'N':len(diff),'max_difference':diff.max(),'mean_difference':diff.mean()})
            assert diff.max()<=1e-10
    ledger['fit_count']=len(ledger['fits']); dump('COMPUTE_LEDGER',ledger)
    dump('REPRODUCIBILITY_AUDIT',{'independent_same_seed_refit_once':True,'scope':'CAL_FIT and CAL_SELECT; no EXPOSED before selection freeze',
        'no_repeat_selection':True,'rows':results,'PASS':True})

if __name__=='__main__':
    {'fit':fit,'select':select}[sys.argv[1]]()

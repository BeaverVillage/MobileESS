"""Paired blocked evaluation and fail-closed selection. Never reads April."""
import hashlib
import json
import pickle
import time
import subprocess
import numpy as np
import pandas as pd
from .contracts import OUT, SPLIT, SEED, CANDIDATES, SUPPORT, Q, FEATURES9, ENVELOPES
from .data import read_frame, train_mask, block_mask
from .firewall import ReadFirewall, sha, write
from .timestamp_firewall import assert_historical_population

def check_amendment_commit():
    receipt=json.loads((OUT/'V40J_AMENDMENT_01_COMMIT_RECEIPT.json').read_text())
    name='dayahead/artifacts/v40j_runtime_redesign/V40J_PREREGISTRATION_AMENDMENT_01.json'
    from .contracts import ROOT
    committed=subprocess.check_output(['git','show',receipt['commit']+':'+name],cwd=ROOT)
    if hashlib.sha256(committed).hexdigest()!=sha(OUT/'V40J_PREREGISTRATION_AMENDMENT_01.json'):
        raise RuntimeError('AMENDMENT_NOT_COMMITTED_OR_CHANGED')
    return receipt['commit']
from .methods import (CausalModel, raw_features, SupportGuard, ConditionalCalibration,
                      ceil_seconds, point_metrics, safety_metrics, envelope_durations)

def strata(frame,x,support=None):
    result={'overall':np.ones(len(frame),dtype=bool),'H100':x.hardware.to_numpy()=='H100',
            'standby':x.standby.to_numpy()==1}
    result['H100-standby']=result['H100']&result['standby']
    result['COMPLETED H100-standby']=result['H100-standby']&(frame.job_state.to_numpy()=='COMPLETED')
    for value in [3600,21600,86400,259200]:
        lo={3600:0,21600:3600,86400:21600,259200:86400}[value]
        result[f'wall_{lo}_{value}']=(x.requested_seconds.to_numpy()>lo)&(x.requested_seconds.to_numpy()<=value)
    result['wall_above_259200']=x.requested_seconds.to_numpy()>259200
    for value in sorted(x.num_gpus_req.unique()): result['GPU_'+str(value)]=x.num_gpus_req.to_numpy()==value
    for c in ['partition','qos']:
        for value in sorted(x[c].unique()): result[c+'_'+str(value)]=x[c].to_numpy()==value
    if support is not None:
        for value in ['STRONG_SUPPORT','SPARSE_SUPPORT','REGIME_MISMATCH','OUT_OF_SUPPORT']:
            result[value]=support.support_class.to_numpy()==value
    return result

def bootstrap(frame,baseline,pred):
    x=raw_features(frame)
    mask=strata(frame,x)['COMPLETED H100-standby']
    f=frame.loc[mask].copy()
    b=np.asarray(baseline)[mask]; p=np.asarray(pred)[mask]; y=f.runtime_seconds.to_numpy()
    if not len(y): return {'N':0,'PASS':False,'reason':'NO_COMPLETED_H100_STANDBY'}
    f['be']=y-b; f['pe']=y-p; f['bu']=(y>b).astype(int); f['pu']=(y>p).astype(int)
    d=f.groupby(f.submit_time.dt.strftime('%Y-%m-%d'))[['be','pe','bu','pu']].sum()
    n=f.groupby(f.submit_time.dt.strftime('%Y-%m-%d')).size().to_numpy()
    a=d.to_numpy()
    rng=np.random.default_rng(SEED)
    sample=rng.integers(0,len(d),size=(2000,len(d)))
    means=a[sample].sum(axis=1)/n[sample].sum(axis=1)[:,None]
    du=means[:,3]-means[:,2]
    db=np.abs(means[:,1])-np.abs(means[:,0])
    uc=np.quantile(du,[.025,.975]).tolist(); bc=np.quantile(db,[.025,.975]).tolist()
    return {'N':len(y),'days':len(d),'underprediction_difference_95CI':uc,'absolute_mean_bias_difference_95CI':bc,
            'baseline':point_metrics(y,b),'new':point_metrics(y,p),'PASS':bool(uc[1]<0 and bc[1]<0)}

def main():
    amendment_commit=check_amendment_commit()
    fw=ReadFirewall('candidate_evaluation').install()
    try:
        baseline=json.loads((OUT/'V40J_CURRENT_RUNTIME_BASELINE.json').read_text())
        assert baseline['status']=='PASS','BASELINE_REPRODUCTION_REQUIRED'
        registry=json.loads((OUT/'V40J_CANDIDATE_REGISTRY.json').read_text())
        assert registry['candidates']==CANDIDATES
        frame=read_frame(OUT/'DEVELOPMENT_GPU_ROWS.parquet')
        point_reports={}; variant_rows={}; baseline_parts=[]; validation_parts=[]
        fit_records=[]
        for fold in SPLIT['folds']:
            fid=fold['id']
            while not (OUT/f'C0_{fid}_FIT.json').exists():
                print('WAITING_FOR_EXACT_C0',fid,flush=True)
                time.sleep(30)
            train=frame.loc[train_mask(frame,fold['fit_before'])].copy()
            assert_historical_population(train,fold['fit_before'])
            cal=frame.loc[block_mask(frame,fold['calibration'],fold['validation'][0])].copy()
            val=frame.loc[block_mask(frame,fold['validation'],SPLIT['validation_label_deadline'])].copy()
            xtrain,xcal,xval=map(raw_features,[train,cal,val])
            ytrain,ycal,yval=[f.runtime_seconds.to_numpy() for f in [train,cal,val]]
            c0=read_frame(OUT/f'C0_{fid}.parquet').set_index('job_id').point
            base=c0.loc[val.job_id].to_numpy()
            basesafe=ceil_seconds(np.minimum(val.requested_seconds.to_numpy(),np.maximum(base+Q,900)))
            base_report=safety_metrics(yval,basesafe,val.num_gpus_req)
            point_reports.setdefault('C0',{})[fid]={k:point_metrics(yval[m],base[m]) for k,m in strata(val,xval).items()}
            baseline_parts.append(pd.DataFrame({'point':base,'safe':basesafe}))
            validation_parts.append(val)
            for entry in CANDIDATES:
                cid=entry['id']
                if cid in ['C0','C4']: continue
                print(fid,cid,'fit',len(train),'cal',len(cal),'validate',len(val),flush=True)
                model=pickle.loads((OUT/'models'/f'{fid}_{cid}.pkl').read_bytes())
                cp,vp=model.predict(xcal),model.predict(xval)
                crossing_before=0
                if cid=='C3_QUANTILE':
                    unrepaired=np.column_stack([m.predict(model.encode(xval)) for m in model.models])
                    crossing_before=int(np.any(np.diff(unrepaired,axis=1)<0,axis=1).sum())
                # Prediction repeat and serialization roundtrip check before accepting evidence.
                repeat=model.predict(xval)
                encoded=pickle.dumps(model,protocol=5)
                restored=pickle.loads(encoded).predict(xval)
                if vp.tobytes()!=repeat.tobytes() or vp.tobytes()!=restored.tobytes(): raise RuntimeError('MODEL_NONDETERMINISM')
                (OUT/'models'/f'{fid}_{cid}.pkl').write_bytes(encoded)
                fit_records.append({'fold':fid,'candidate':cid,'train_rows':len(train),'cal_rows':len(cal),'val_rows':len(val),
                   'max_train_end':str(train.end_time.max()),'model_sha256':hashlib.sha256(encoded).hexdigest(),
                   'prediction_sha256':hashlib.sha256(vp.tobytes()).hexdigest(),'repeat_and_reload_identical':True})
                fit_records[-1]['quantile_crossing_rows_before_repair']=crossing_before
                fit_records[-1]['quantile_crossing_rows_after_repair']=int(np.any(np.diff(vp,axis=1)<0,axis=1).sum())
                point_reports.setdefault(cid,{})[fid]={k:point_metrics(yval[m],vp[m,0]) for k,m in strata(val,xval).items()}
                for minimum in SUPPORT:
                    guard=SupportGuard(xtrain,minimum)
                    support=guard.predict(xval)
                    calibrator=ConditionalCalibration(minimum).fit(xcal,ycal,cp)
                    upper,fallback=calibrator.predict(xval,vp,support)
                    write(f'CALIBRATION_{fid}_{cid}_{minimum}.json',calibrator.json())
                    for rid,(hard,grid) in envelope_durations(upper[:,0],upper[:,1],upper[:,2]).items():
                        key=f'{cid}_N{minimum}_{rid}'
                        safe=grid
                        row=val[['job_id','submit_time','start_time','job_state','runtime_seconds','num_gpus_req','requested_seconds']].reset_index(drop=True).copy()
                        row['fold']=fid; row['point']=vp[:,0]; row['upper90']=upper[:,1];row['upper95']=upper[:,2]
                        row['safe']=safe;row['hard']=hard;row['baseline_point']=base;row['baseline_safe']=basesafe
                        for col in support: row[col]=support[col].to_numpy()
                        for col in fallback: row['fallback_'+col]=fallback[col].to_numpy()
                        for col in FEATURES9:
                            if col not in row: row[col]=val[col].to_numpy()
                        variant_rows.setdefault(key,[]).append(row)
                del model
        pooled=pd.concat(validation_parts,ignore_index=True)
        bpool=pd.concat(baseline_parts,ignore_index=True)
        point_reports['C0']['pooled']={k:point_metrics(pooled.runtime_seconds.to_numpy()[m],bpool.point.to_numpy()[m]) for k,m in strata(pooled,raw_features(pooled)).items()}
        comparisons=[]
        for key,parts in variant_rows.items():
            cid,n,rid=key.split('_N')[0],key.split('_N')[1].split('_')[0],key.rsplit('_',1)[1]
            minimum=int(n); row=pd.concat(parts,ignore_index=True)
            row.to_parquet(OUT/(key+'_validation.parquet'),index=False)
            x=raw_features(row); masks=strata(row,x,row)
            y=row.runtime_seconds.to_numpy(); gpu=row.num_gpus_req.to_numpy()
            anchors=(row.start_time.dt.as_unit('ns').astype('int64').to_numpy()/1e9)%300
            metrics=safety_metrics(y,row.safe,gpu,anchors)
            base=safety_metrics(y,row.baseline_safe,gpu,anchors)
            request=safety_metrics(y,ceil_seconds(row.requested_seconds),gpu,anchors)
            ptest=bootstrap(row,row.baseline_point,row.point)
            point_reports[cid]['pooled']={k:point_metrics(y[m],row.point.to_numpy()[m]) for k,m in masks.items()}
            point_reports[cid]['pooled_support_threshold']=minimum
            cov={}; failures=[]
            for fid in ['F1','F2','F3','pooled']:
                fm=np.ones(len(row),dtype=bool) if fid=='pooled' else row.fold.to_numpy()==fid
                for group in ['overall','H100','standby','H100-standby','COMPLETED H100-standby']:
                    m=fm&masks[group]
                    if m.sum()>=minimum or group=='overall':
                        value=safety_metrics(y[m],row.upper90.to_numpy()[m],gpu[m],anchors[m])
                        cov[fid+'/'+group]=value
                        if value.get('coverage',0)<.9: failures.append(fid+'/'+group)
            nominal_sufficient=bool(ptest['PASS'])
            coverage_pass=not failures
            gpu_pass=metrics['PREDICTED_FINISHED_BUT_ACTUALLY_ACTIVE_GPU_SLOTS']<base['PREDICTED_FINISHED_BUT_ACTUALLY_ACTIVE_GPU_SLOTS']
            conservation=metrics['overreserved_GPU_hours']<=request['overreserved_GPU_hours'] and metrics['reserved_GPU_hours']<request['reserved_GPU_hours']
            eligible=nominal_sufficient and coverage_pass and gpu_pass and conservation
            comparisons.append({'id':key,'candidate':cid,'minimum_support':minimum,'envelope':rid,
                'eligible':eligible,'gates':{'point':nominal_sufficient,'coverage':coverage_pass,'GPU':gpu_pass,'conservatism':conservation},
                'coverage_failures':failures,'metrics':metrics,'native_upper90_metrics':safety_metrics(y,row.upper90,gpu,anchors),
                'upper90_ceil_metrics':safety_metrics(y,ceil_seconds(row.upper90),gpu,anchors),
                'baseline':base,'requested_reference':request,
                'paired_point_bootstrap':ptest,'coverage_by_fold_critical_group':cov,
                'support_counts':row.support_class.value_counts().to_dict()})
        eligible=[r for r in comparisons if r['eligible']]
        check_amendment_commit()
        def rank(r):
            m=r['metrics']
            return (m['CRITICAL_SLOT_MISS_GPU_SLOTS'],-m['coverage'],m['overreserved_GPU_hours'],
                    r['paired_point_bootstrap']['new']['MAE_seconds'],r['id'])
        winner=min(eligible,key=rank) if eligible else None
        write('V40J_POINT_MODEL_COMPARISON.json',point_reports)
        write('V40J_QUANTILE_MODEL_COMPARISON.json',{'candidates':[r for r in comparisons if r['candidate']=='C3_QUANTILE']})
        write('V40J_MIXTURE_MODEL_COMPARISON.json',{'candidates':[r for r in comparisons if r['candidate']=='C2_MIXTURE'],'future_status_input':False})
        write('V40J_CONDITIONAL_CALIBRATION_REPORT.json',{'comparisons':comparisons})
        write('V40J_ROBUST_ENVELOPE_COMPARISON.json',{'formulas':ENVELOPES,'comparisons':comparisons,'full_optimizer_runs':0})
        write('V40J_MODEL_FIT_MANIFEST.json',fit_records)
        write('V40J_SELECTION_FREEZE.json',{'winner':winner,'eligible_count':len(eligible),
           'selection_data':'F1/F2/F3 only','April_payload_read_count':0,'shadow_can_change_winner':False,
           'status':'WINNER_FROZEN_FOR_SHADOW' if winner else 'NO_WINNER_HOLD',
           'amendment_commit':amendment_commit,
           'protocol_review_sha256':sha(OUT/'V40J_PREREGISTRATION_REVIEW.json')},immutable=True)
        print('SELECTION',winner['id'] if winner else 'NO_WINNER_HOLD',flush=True)
    finally: fw.close()

if __name__=='__main__':main()

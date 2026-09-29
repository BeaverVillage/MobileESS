"""CAL-only deterministic post-processing. Never train or change a frozen Runtime model."""
from common import *
import sys

def rolling_cal(cal,q):
    out=q[:,[0,3]].copy();days=cal.submit_time.dt.floor('D');audit=[]
    for day in sorted(days.unique()):
        eligible=cal.event & cal.end_time.lt(day) & cal.end_time.ge(day-pd.Timedelta(days=14))
        residual=cal.loc[eligible,'runtime_seconds'].to_numpy()-q[eligible,3]
        delta=0.
        if len(residual)>=200:
            k=min(int(np.ceil(.9*(len(residual)+1))),len(residual))-1
            delta=float(np.partition(residual,k)[k])
        out[days.eq(day)]=np.maximum(out[days.eq(day)]+delta,0)
        latest=cal.loc[eligible,'end_time'].max();assert pd.isna(latest) or latest<day
        audit.append(dict(day=str(day),residual_N=len(residual),delta=delta,max_source_end=str(latest),future_residual_reads=0))
    return out,audit

def choose_alpha(frame,grid):
    y=frame.runtime_seconds.to_numpy();q50=frame.q50.to_numpy();gap=frame.q90.to_numpy()-q50
    rows=[dict(alpha=float(a),N=len(frame),coverage=float((y<=q50+a*gap).mean()),TIME_RATIO_OP=float((q50+a*gap).sum()/y.sum())) for a in grid]
    eligible=[x for x in rows if x['coverage']>=.90]
    if eligible:chosen=min(eligible,key=lambda x:(x['TIME_RATIO_OP'],x['alpha']))
    else:chosen=min(rows,key=lambda x:(-x['coverage'],x['TIME_RATIO_OP'],x['alpha']))
    return chosen,rows,not bool(eligible)

def main():
    assert sha(ROOT/'PREREGISTRATION.json')==read(ROOT/'PREREGISTRATION_HASH.json')['sha256']
    assert not (ROOT/'ALPHA_FREEZE.json').exists()
    spec=read(ROOT/'PREREGISTRATION.json');sources=[];gridrows=[];choices=[];rolling=[];ca=[]
    sys.path.insert(0,str(V13))
    import model13
    # Fail closed if any imported training path is accidentally invoked.
    def forbidden(*args,**kwargs):raise AssertionError('NEW_TRAINING_FORBIDDEN')
    model13.fit=forbidden;model13.lgb.LGBMClassifier.fit=forbidden
    p=V13/'.local/CURRENT_STATE_FEATURES.parquet';sources.append(rec(p));regime=pd.read_parquet(p).set_index('job_id')
    for i in range(1,6):
        p=V9/'.local'/f'fold{i}/CAL.parquet';sources.append(rec(p));cal=pd.read_parquet(p);cal.job_id=cal.job_id.astype(str)
        fold=spec['folds'][i-1];assert ids(cal)==fold['membership']['CAL']
        cutoff=pd.Timestamp(fold['CAL_end_before']);assert cal.loc[cal.event,'end_time'].le(cutoff).all()
        assert cal.submit_time.ge(pd.Timestamp(fold['TRAIN_cutoff'])).all() and cal.submit_time.lt(cutoff).all()
        seen=[]
        for arm,src in ARMS.items():
            if arm.startswith('V9'):
                base,mode=src.split('__');p=V9/'.local'/f'fold{i}/{base}.npz';sources.append(rec(p));qraw=np.load(p)['cal_quantiles'];assert len(qraw)==len(cal)
                if mode=='ROLLING14':
                    q,audit=rolling_cal(cal,qraw);rolling.extend(dict(Model=arm,fold=i,**x) for x in audit)
                else:q=qraw[:,[0,3]]
            else:
                dest=V13/'FOLD_MODELS'/f'fold{i}/EXPANDING_S4'
                sources.extend(rec(dest/n) for n in ['model.json','hazard.txt'])
                model=model13.Hazard.load(dest);pre=model.meta['preprocessing'];assert pd.Timestamp(model.meta['fit_cutoff'])<=pd.Timestamp(fold['TRAIN_cutoff'])
                x=model13.matrix(cal,pre,regime,model.meta['columns']);par=model.parameters(x,threads=4)
                q=np.column_stack([model.inverse_logsf(par,np.log1p(-a)) for a in [.5,.9]])
                # Frozen inference parity against stored VALID outputs, no metric or alpha sweep.
                v=pd.read_parquet(V9/'.local'/f'fold{i}/VALID.parquet').iloc[:32]
                pval=model.parameters(model13.matrix(v,pre,regime,model.meta['columns']),threads=4)
                vq=np.column_stack([model.inverse_logsf(pval,np.log1p(-a)) for a in [.5,.9]])
                stored=np.load(V13/'.local'/f'fold{i}/EXPANDING_S4_quantiles.npz')['q'][:32]
                np.testing.assert_array_equal(vq,stored)
            assert np.isfinite(q).all() and (q>=0).all() and (q[:,1]>=q[:,0]).all()
            mask=cal.event.to_numpy(bool);f=cal.loc[mask,['job_id','submit_time','runtime_seconds']].reset_index(drop=True);f['q50']=q[mask,0];f['q90']=q[mask,1]
            f.to_parquet(LOCAL/f'{arm}_fold{i}_CAL.parquet',index=False);seen.append(ids(f))
            chosen,rows,unattainable=choose_alpha(f,spec['alpha_grid']);gridrows.extend(dict(Model=arm,fold=i,**x) for x in rows)
            choices.append(dict(Model=arm,fold=i,**chosen,CAL_90PCT_UNATTAINABLE=unattainable,CAL_membership=ids(f),CAL_cutoff=str(cutoff)))
        assert len(set(seen))==1
        ca.append(dict(fold=i,N=int(cal.event.sum()),membership=seen[0],latest_label_end=str(cal.loc[cal.event,'end_time'].max()),cutoff=str(cutoff),future_label_reads=0,V13_frozen_inference_parity=True))
        print(now(),'CAL_FROZEN',i,flush=True)
    csv('ALPHA_CALIBRATION_GRID.csv',gridrows);csv('ALPHA_SELECTION_BY_FOLD.csv',choices);csv('CAL_ROLLING_QUANTILE_AUDIT.csv',rolling)
    write('CAL_CAUSALITY_AUDIT.json',dict(PASS=True,folds=ca,training_calls=0,VALID_used_for_alpha=False,regime_source='Existing frozen V13 causal current-state ledger; no feature regeneration',inference_only=True,sources=sources))
    write('ALPHA_FREEZE.json',dict(time=now(),preregistration=rec(ROOT/'PREREGISTRATION.json'),selection=rec(ROOT/'ALPHA_SELECTION_BY_FOLD.csv'),grid=rec(ROOT/'ALPHA_CALIBRATION_GRID.csv'),all_candidate_folds=30,VALID_operational_metrics_evaluated=False))
if __name__=='__main__':main()

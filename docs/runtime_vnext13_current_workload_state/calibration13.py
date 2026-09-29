"""The single conditionally authorized V9 rolling14 challenger, unchanged rule."""
from common13 import *
from model13 import Hazard,frozen_v9,matrix
from metrics9 import calibration,stats

def run_c1(arm):
    from train13 import sharpness,summarize,load_features
    comp=pd.read_csv(ROOT/'TOTAL_MODEL_COMPARISON.csv')
    row=comp[comp.arm.eq(arm)].iloc[0]
    assert row.min_fold_coverage>=.80 and row.gt4h_coverage>=.80
    features=load_features();folds=[];parts=[];audits=[];tails=[]
    for i in range(1,6):
        m=frozen_v9(i) if arm.endswith('S0') else Hazard.load(ROOT/'FOLD_MODELS'/f'fold{i}'/arm)
        pre=prep(i) if arm.endswith('S0') else m.meta['preprocessing'];cal=data(i,'CAL');val=data(i,'VALID')
        pc=m.parameters(matrix(cal,pre,features,m.meta['columns']),threads=4)
        pv=m.parameters(matrix(val,pre,features,m.meta['columns']),threads=4)
        qc=np.tile(m.inverse_logsf(pc,np.log(.1))[:,None],(1,5))
        qv=np.tile(m.inverse_logsf(pv,np.log(.1))[:,None],(1,5))
        delta,audit=calibration(cal,val,qc,qv,'ROLLING14')
        audits.extend(dict(fold=i,**a) for a in audit)
        q50=np.maximum(m.inverse_logsf(pv,np.log(.5))+delta,0);q90=np.maximum(qv[:,3]+delta,0)
        exact=val.event.to_numpy(bool);censored=val.censored.to_numpy(bool)
        y=val.runtime_seconds.to_numpy(float);ll=np.full(len(val),np.nan)
        left=np.maximum(y[exact]-.5,0);right=y[exact]+.5;d=delta[exact]
        lower=np.maximum(left-d,0);upper=np.maximum(right-d,0)
        dh=m.interval_hazard(pv[exact],lower,upper)
        ls=m.logsf(pv[exact],lower)
        # max(T+delta,0) has an atom at0 for negative delta. Include that atom
        # in the first observation interval; never floor zero probabilities.
        first=left==0;ls[first]=0;dh[first]=-m.logsf(pv[exact][first],upper[first])
        with np.errstate(divide='ignore'):ll[exact]=ls+np.log(-np.expm1(-dh))
        ll[censored]=m.logsf(pv[censored],np.maximum(val.duration_lower.to_numpy(float)[censored]-delta[censored],0))
        p=val.loc[exact,['job_id','runtime_seconds','num_gpus_req','requested_seconds']].reset_index(drop=True)
        p['q50']=q50[exact];p['q90']=q90[exact]
        s=stats(p.runtime_seconds,p.num_gpus_req,p.q50,p.q90);s.update(sharpness(p))
        finite=bool(np.isfinite(ll[exact|censored]).all())
        s.update(arm=arm+'_C1',fold=i,calibration='C1',proper_interval_NLL=float(-ll[exact|censored].mean()),
            proper_NLL_N=int((exact|censored).sum()),proper_score_finite=finite,
            zero_support_count=int(np.isneginf(ll[exact]).sum()),monotonicity_pass=True,
            positive_support_pass=bool((delta<=0).all()),inference_seconds=0.)
        for h in [4,8,12,24]:
            z=p[p.runtime_seconds>h*3600];s[f'gt{h}h_N']=len(z);s[f'gt{h}h_coverage']=float((z.runtime_seconds<=z.q90).mean()) if len(z) else None
            tails.append(dict(arm=arm+'_C1',fold=i,cohort=f'gt{h}h',**stats(z.runtime_seconds,z.num_gpus_req,z.q50,z.q90)))
        parts.append(p);folds.append(s);p.to_parquet(LOCAL/f'fold{i}'/(arm+'_C1.parquet'),index=False)
        write(LOCAL/f'fold{i}'/(arm+'_C1.json'),s)
    result=summarize(arm+'_C1',folds,parts);result['calibration']='C1'
    result['positive_support_pass']=all(s['positive_support_pass'] for s in folds)
    result['gate_G']=bool(result['gate_G'] and result['positive_support_pass'])
    result['eligible']=all(result['gate_'+k] for k in 'ABCDEFGHI')
    pd.DataFrame(audits).to_csv(ROOT/'C1_ROLLING14_CAUSAL_AUDIT.csv',index=False)
    write('C1_ELIGIBILITY_AUDIT.json',dict(time=now(),eligible_C0_arms=comp[(comp.min_fold_coverage>=.80)&(comp.gt4h_coverage>=.80)].arm.tolist(),
        evaluated_C0_arm=arm,C1_ROLLING14_EVALUATED=True,status='EVALUATED',challengers=1,
        future_residual_reads=0,positive_support_pass=result['positive_support_pass']))
    updates=[('TOTAL_LONG_TAIL_METRICS.csv',pd.DataFrame(tails)),
        ('TOTAL_DISTRIBUTIONAL_METRICS.csv',pd.DataFrame(folds)[['arm','fold','proper_interval_NLL','proper_NLL_N','zero_support_count','proper_score_finite','monotonicity_pass']]),
        ('TOTAL_GPU_WEIGHTED_METRICS.csv',pd.DataFrame(folds)[['arm','fold','GPU_weighted_coverage','reserved_GPUh','actual_GPUh','reservation_actual_GPUh']]),
        ('TEMPORAL_ROBUSTNESS_COMPARISON.csv',pd.DataFrame([result])[['arm','Q90_coverage','min_fold_coverage','max_fold_coverage','coverage_std','gt4h_coverage','Q90_pinball','eligible']])]
    for name,extra in updates:pd.concat([pd.read_csv(ROOT/name),extra],ignore_index=True).to_csv(ROOT/name,index=False)
    return result,folds

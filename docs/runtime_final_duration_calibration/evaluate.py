"""Apply the already SHA-frozen CAL alpha once to the common VALID population."""
from common import *

def op_metrics(f):
    y=f.runtime_seconds.to_numpy();out=dict(OP_coverage=float((y<=f.t_op).mean()),TIME_RATIO_OP=float(f.t_op.sum()/y.sum()))
    for h in [4,12,24]:
        z=f[y>h*3600];out[f'GT{h}H_OP_coverage']=float((z.runtime_seconds<=z.t_op).mean()) if len(z) else None
    return out

def nondominated(frame):
    x=frame[['Q50_MAE_hours','OP_coverage','min_fold_OP_coverage','GT12H_OP_coverage','TIME_RATIO_OP']].to_numpy()*np.array([1,-1,-1,-1,1])
    return [not any(np.all(other<=row) and np.any(other<row) for other in x) for row in x]

def main():
    freeze=read(ROOT/'ALPHA_FREEZE.json');assert sha(ROOT/'ALPHA_SELECTION_BY_FOLD.csv')==freeze['selection']['sha256']
    assert sha(ROOT/'ALPHA_CALIBRATION_GRID.csv')==freeze['grid']['sha256'];assert sha(ROOT/'PREREGISTRATION.json')==freeze['preregistration']['sha256']
    choices=pd.read_csv(ROOT/'ALPHA_SELECTION_BY_FOLD.csv');raw=[];folds=[];tails=[];ratios=[];dist=[];summary=[];supp=[]
    published=pd.read_csv(V9/'MODEL_COMPARISON.csv').set_index('arm');pub13=pd.read_csv(V13/'TOTAL_MODEL_COMPARISON.csv').query("arm=='EXPANDING_S4' and calibration=='C0'").iloc[0]
    for arm in ARMS:
        parts=[];fr=[]
        for i in range(1,6):
            f=pd.read_parquet(LOCAL/f'{arm}_fold{i}_VALID.parquet');a=float(choices.query('Model==@arm and fold==@i').iloc[0].alpha)
            assert not any(c in f for c in ['gpu','num_gpus_req','num_nodes_req'])
            f['alpha']=a;f['t_op']=f.q50+a*(f.q90-f.q50)
            assert (f.t_op>=f.q50).all() and (f.t_op<=f.q90+1e-9).all()
            f.to_parquet(LOCAL/f'{arm}_fold{i}_OP.parquet',index=False);parts.append(f)
            r=dict(Model=arm,fold=i,**metrics(f));raw.append(r)
            s=dict(Model=arm,fold=i,alpha=a,**metrics(f),**op_metrics(f));fr.append(s);folds.append(s)
        f=pd.concat(parts,ignore_index=True);m=metrics(f);om=op_metrics(f)
        m['min_fold_Q90_coverage']=min(x['Q90_coverage'] for x in fr)
        pub=pub13 if arm.startswith('V13') else published.loc[ARMS[arm]]
        for key,oldkey in [('Q50_MAE_seconds','Q50_MAE'),('Q90_coverage','Q90_coverage'),('min_fold_Q90_coverage','min_fold_coverage'),('GT12H_Q90_coverage','gt12h_coverage')]:np.testing.assert_allclose(m[key],pub[oldkey],rtol=1e-12)
        raw.append(dict(Model=arm,fold='POOLED',**m,published_Q50_MAE_seconds=pub.Q50_MAE,published_Q90_coverage=pub.Q90_coverage,published_GT12H_Q90_coverage=pub.gt12h_coverage,published_min_fold_Q90_coverage=pub.min_fold_coverage,published_N=int(pub.N),raw_metric_reproduction=True))
        s=dict(Model=arm,role='PRIMARY' if arm in PRIMARY else 'LOW_RATIO_DIAGNOSTIC',**m,Selected_Alpha_by_fold=';'.join(f'{x["alpha"]:.2f}' for x in fr),**om,min_fold_OP_coverage=min(x['OP_coverage'] for x in fr),worst_fold=min(fr,key=lambda x:x['OP_coverage'])['fold'],CAL_90PCT_UNATTAINABLE_folds=int(choices.query('Model==@arm').CAL_90PCT_UNATTAINABLE.sum()))
        s['reliability_eligible']=arm in PRIMARY and s['OP_coverage']>=.90 and s['min_fold_OP_coverage']>=.90
        s['ratio_band']='BELOW_1P2' if s['TIME_RATIO_OP']<1.2 else 'BELOW_1P5' if s['TIME_RATIO_OP']<1.5 else 'BELOW_2P0' if s['TIME_RATIO_OP']<2 else 'AT_2P0' if s['TIME_RATIO_OP']==2 else 'ABOVE_2P0'
        s['raw_Q90_time_reduction_fraction']=1-s['TIME_RATIO_OP']/s['TIME_RATIO_Q90']
        for threshold,name in [(1.,'1p0'),(1.2,'1p2'),(1.5,'1p5'),(2.,'2p0')]:
            s[f'Q50_floor_le_{name}']='IMPOSSIBLE' if m['TIME_RATIO_Q50']>threshold else 'NOT_RULED_OUT_NOT_PROVEN'
        summary.append(s)
        for fold,z in [('POOLED',f)]+[(i,f[f.fold==i]) for i in range(1,6)]:
            ratios.append(dict(Model=arm,fold=fold,**{k:metrics(z)[k] for k in ['N','zero_runtime_N','actual_seconds','TIME_RATIO_Q50','TIME_RATIO_Q90']},TIME_RATIO_OP=op_metrics(z)['TIME_RATIO_OP']))
            for q in ['q50','q90']:
                r=(z.loc[z.runtime_seconds>0,q]/z.loc[z.runtime_seconds>0,'runtime_seconds']).to_numpy()
                dist.append(dict(Model=arm,fold=fold,quantile=q,N_positive=len(r),zero_runtime_N=int(z.runtime_seconds.eq(0).sum()),Q25=np.quantile(r,.25),median=np.median(r),Q75=np.quantile(r,.75),Q90=np.quantile(r,.9),mean_diagnostic_only=np.mean(r)))
            for h in [4,12,24]:
                zz=z[z.runtime_seconds>h*3600];tails.append(dict(Model=arm,fold=fold,threshold_hours=h,N=len(zz),raw_Q90_coverage=float((zz.runtime_seconds<=zz.q90).mean()),OP_coverage=float((zz.runtime_seconds<=zz.t_op).mean()),TIME_RATIO_OP=float(zz.t_op.sum()/zz.runtime_seconds.sum())))
        err=f.runtime_seconds-f.q90;supp.append(dict(Model=arm,Q50_pinball_seconds=float(abs(f.runtime_seconds-f.q50).mean()*.5),Q90_pinball_seconds=float(np.maximum(.9*err,-.1*err).mean()),selection_use=False))
    comp=pd.DataFrame(summary);comp['pareto_all_candidates']=nondominated(comp)
    comp['pareto_primary']=False;mask=comp.role.eq('PRIMARY');comp.loc[mask,'pareto_primary']=nondominated(comp[mask])
    eligible=comp[comp.reliability_eligible].sort_values(['TIME_RATIO_OP','Q50_MAE_hours','GT12H_OP_coverage','Model'],ascending=[True,True,False,True])
    selected='NONE' if eligible.empty else eligible.iloc[0].Model;comp['selected']=comp.Model.eq(selected)
    csv('RAW_RUNTIME_METRICS.csv',raw);csv('RUNTIME_TIME_RATIO_METRICS.csv',ratios);csv('PER_JOB_RATIO_DISTRIBUTION.csv',dist)
    csv('OPERATIONAL_DURATION_FOLD_METRICS.csv',folds);csv('LONG_RUNTIME_OPERATIONAL_METRICS.csv',tails);csv('SUPPLEMENTARY_PINBALL.csv',supp)
    comp.to_csv(ROOT/'FINAL_RUNTIME_MODEL_COMPARISON.csv',index=False)
    comp[['Model','role','Q50_MAE_hours','OP_coverage','min_fold_OP_coverage','GT12H_OP_coverage','TIME_RATIO_OP','pareto_all_candidates','pareto_primary','reliability_eligible','selected']].to_csv(ROOT/'RUNTIME_PARETO_FRONTIER.csv',index=False)
    write('FINAL_SELECTION_FREEZE.json',dict(time=now(),SELECTED_RUNTIME_MODEL=selected,SELECTED_RUNTIME_INTERFACE='NONE' if selected=='NONE' else 'CALIBRATED_OPERATIONAL_RUNTIME',SELECTED_ALPHA=None,
        rationale='No primary candidate reached nominal 90% operational coverage on every fold.' if selected=='NONE' else 'Lowest duration ratio among preregistered reliable candidates.',
        alpha_scope='Five independent CAL-frozen alphas per candidate; no untested average alpha, no final provider fit.',
        frontier=comp.loc[comp.pareto_primary,'Model'].tolist(),primary_rule=read(ROOT/'PREREGISTRATION.json')['model_selection'],
        evidence=[rec(ROOT/n) for n in ['ALPHA_FREEZE.json','FINAL_RUNTIME_MODEL_COMPARISON.csv','OPERATIONAL_DURATION_FOLD_METRICS.csv','RUNTIME_PARETO_FRONTIER.csv']]))
    print(comp[['Model','Q50_MAE_hours','TIME_RATIO_Q50','TIME_RATIO_Q90','Selected_Alpha_by_fold','OP_coverage','min_fold_OP_coverage','GT12H_OP_coverage','TIME_RATIO_OP','selected']].to_string(index=False),flush=True)
if __name__=='__main__':main()

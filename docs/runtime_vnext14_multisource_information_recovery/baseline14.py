"""Reload frozen S0/S4 and reproduce all VALID predictions; no model fitting."""
from common14 import *
sys.path.insert(0,str(V13))
import model13, train13, common13


def main():
    features=pd.read_parquet(V13/'.local/CURRENT_STATE_FEATURES.parquet').set_index('job_id')
    checks=[];summaries=[];allfold=[]
    reference=pd.read_csv(V13/'TOTAL_MODEL_COMPARISON.csv').set_index('arm')
    for arm,alias in [('EXPANDING_S0','J0_STATIC'),('EXPANDING_S4','J1_CURRENT_STATE')]:
        folds=[];parts=[]
        for i in range(1,6):
            f=common13.data(i,'VALID')
            model=model13.frozen_v9(i) if arm.endswith('S0') else model13.Hazard.load(V13/'FOLD_MODELS'/f'fold{i}'/arm)
            pre=common13.prep(i);cols=pre['columns'] if arm.endswith('S0') else model.meta['columns']
            x=model13.matrix(f,pre,features,cols)
            par=model.parameters(x,threads=4)
            q=np.column_stack([model.inverse_logsf(par,np.log1p(-p)) for p in [.5,.9]])
            saved=np.load(V13/'.local'/f'fold{i}'/(arm+'_quantiles.npz'))['q']
            assert np.array_equal(q,saved),(arm,i)
            if arm.endswith('S0'):
                assert np.array_equal(par,np.load(V9/'.local'/f'fold{i}/D1.npz')['val_parameters'])
            # Existing proper-score metrics and row predictions remain immutable.
            fr=read(V13/'.local'/f'fold{i}'/(arm+'.json'));folds.append(fr)
            part=pd.read_parquet(V13/'.local'/f'fold{i}'/(arm+'.parquet'));parts.append(part)
            assert np.array_equal(q[f.event.to_numpy(bool)],part[['q50','q90']].to_numpy())
            checks.append(dict(arm=arm,fold=i,VALID_N=len(f),all_VALID_quantiles_bit_identical=True,
                max_abs_error=0.,prediction_sha256=hashlib.sha256(q.tobytes()).hexdigest(),
                saved_predictions=record(V13/'.local'/f'fold{i}'/(arm+'_quantiles.npz'))))
            allfold.append(dict(fr,arm=alias,original_arm=arm,scope='FULL_V13_POPULATION',reused_frozen_baseline=True))
            print(now(),arm,'fold',i,'PARITY',len(f),flush=True)
        result=train13.summarize(arm,folds,parts)
        for key in ['Q90_coverage','min_fold_coverage','gt4h_coverage','gt12h_coverage','gt24h_coverage','Q90_pinball','proper_interval_NLL']:
            assert np.isclose(result[key],reference.loc[arm,key],rtol=1e-13,atol=0),(arm,key)
        summaries.append(dict(result,arm=alias,original_arm=arm,scope='FULL_V13_POPULATION',reused_frozen_baseline=True))
    write('V13_BASELINE_REPRODUCTION.json',dict(time=now(),PASS=True,V13_S0_REPRODUCED=True,V13_S4_REPRODUCED=True,
        no_fit=True,strict_tolerance='bit-identical all VALID q50/q90; pooled summary relative tolerance 1e-13',checks=checks,metrics=summaries))
    pd.DataFrame(summaries).to_csv(ROOT/'BASELINE_MODEL_COMPARISON.csv',index=False)
    pd.DataFrame(allfold).to_csv(ROOT/'BASELINE_FOLD_METRICS.csv',index=False)


if __name__=='__main__':main()

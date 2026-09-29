"""Section22 conditional follow-up of the preregistered SOFTWARE_STACK contrast."""
from common16 import *
from features16 import *
from train_native16 import metrics,check_freeze
from ablation16 import GROUPS,keep_columns
import pickle,lightgbm as lgb,gc,time

def main():
    check_freeze();t=pd.read_csv(ROOT/'RADDIT_NATIVE_MODEL_COMPARISON.csv').set_index('arm');r=t.loc['SOFTWARE_STACK'];b=t.loc['D0']
    assert (r.min_fold_coverage-b.min_fold_coverage>=.05 or r.gt4h_coverage-b.gt4h_coverage>=.05) and r.Q90_pinball/b.Q90_pinball<=1.05
    fp=ROOT/'STACK_ABLATION_EXECUTION_FREEZE.json'
    if not fp.exists():
        write(fp,dict(time=now(),before_any_stack_ablation_fit=True,candidate='SOFTWARE_STACK',reference='D0',
            scope='Conditional diagnostic extension after complete native results; original primary D1-D4 trigger unchanged',
            trigger='User section22: >=5pp min-fold OR >4h improvement and <=5% pinball degradation',
            gain_gt4h=float(r.gt4h_coverage-b.gt4h_coverage),pinball_ratio=float(r.Q90_pinball/b.Q90_pinball),
            A='Fit stack-only after removing four resources',E='Exact D0 columns; reuse frozen D0 predictions without refitting',
            B_C_D_F='NOT_APPLICABLE_GROUP_ABSENT',folds='Same full native three folds; no new cap or tuning',
            model_code=rec(Path(__file__)),omission_helper=rec(ROOT/'ablation16.py'),primary_selection_affected=False))
    assert rec(Path(__file__))==read(fp)['model_code']
    d=pd.read_parquet(LOCAL/'NATIVE_TABLE.parquet');fields=RESOURCE+IDENTITY+STACK+['submit_time'];folds=[];parts={'A':[],'E':[]}
    for fold in [1,2,3]:
        folder=LOCAL/f'native_fold{fold}';out=LOCAL/f'stack_ablation_fold{fold}';out.mkdir(exist_ok=True)
        roles=np.load(LOCAL/f'native_fold{fold}_roles.npz');tr=roles['TRAIN'];va=roles['VALID']
        with (folder/'adapter.pkl').open('rb') as stream:adapter=pickle.load(stream)
        x,names,cats=adapter.transform(d.iloc[tr][fields],'SOFTWARE_STACK');v,_,_=adapter.transform(d.iloc[va][fields],'SOFTWARE_STACK')
        for group in GROUPS:
            keep=keep_columns(names,group)
            if len(keep)==len(names):continue
            if group=='E':
                assert [names[i] for i in keep]==RESOURCE
                reference=read(folder/'D0.json');p=pd.read_parquet(folder/'D0.parquet')
                np.testing.assert_array_equal(x[:,keep].toarray(),d.iloc[tr][RESOURCE].to_numpy(np.float32))
                np.testing.assert_array_equal(v[:,keep].toarray(),d.iloc[va][RESOURCE].to_numpy(np.float32))
                write(str((out/'E.json').relative_to(ROOT)),dict(status='REUSED_EXACT_D0',fold=fold,group=group,
                    TRAIN_ids=ids(tr),VALID_ids=ids(va),predictions=reference['predictions'],models=reference['models'],exact_feature_matrix_parity=True))
            else:
                assert group=='A';rp=out/'A.json';pp=out/'A.parquet'
                if not rp.exists():
                    xx=x[:,keep];vv=v[:,keep];cc=[keep.index(i) for i in cats if i in keep];pred=[];models=[];start=time.perf_counter()
                    for q in [.5,.9]:
                        print('STACK_ABLATION',fold,group,q,flush=True)
                        model=lgb.LGBMRegressor(objective='quantile',alpha=q,**read(ROOT/'PREREGISTRATION.json')['lightgbm_parameters'])
                        model.fit(xx,d.iloc[tr].wallclock_used_sec.to_numpy(),categorical_feature=cc)
                        pred.append(np.maximum(model.predict(vv),0));mp=out/f'A_q{int(q*100)}.txt';model.booster_.save_model(str(mp));models.append(rec(mp));del model;gc.collect()
                    q50,q90=pred;q90=np.maximum(q50,q90);pd.DataFrame(dict(historic_row=va,Q50=q50,Q90=q90)).to_parquet(pp,index=False)
                    write(str(rp.relative_to(ROOT)),dict(fold=fold,group=group,status='COMPLETED',TRAIN_ids=ids(tr),VALID_ids=ids(va),
                        models=models,predictions=rec(pp),seconds=time.perf_counter()-start,metrics=metrics(d.iloc[va],q50,q90)))
                    del xx,vv
                p=pd.read_parquet(pp)
            parts[group].append(p);folds.append(dict(fold=fold,group=group,**metrics(d.iloc[va],p.Q50.to_numpy(),p.Q90.to_numpy())))
        del x,v,adapter;gc.collect()
    rows=[]
    for group in GROUPS:
        if group not in parts:rows.append(dict(group=group,status='NOT_APPLICABLE_GROUP_ABSENT'));continue
        p=pd.concat(parts[group],ignore_index=True)
        rows.append(dict(group=group,status='REUSED_EXACT_D0' if group=='E' else 'COMPLETED',
            **metrics(d.iloc[p.historic_row],p.Q50.to_numpy(),p.Q90.to_numpy()),min_fold_coverage=min(f['Q90_coverage'] for f in folds if f['group']==group)))
    pd.DataFrame(rows).to_csv(ROOT/'RADDIT_STACK_GROUPED_ABLATION.csv',index=False)
    pd.DataFrame(folds).to_csv(ROOT/'RADDIT_STACK_GROUPED_ABLATION_FOLD_METRICS.csv',index=False)
    print('STACK_ABLATION_COMPLETE',flush=True)

if __name__=='__main__':main()

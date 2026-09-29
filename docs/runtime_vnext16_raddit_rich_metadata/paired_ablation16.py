"""User section22 material-win follow-up on the separately fixed matched cohort."""
from common16 import *
from features16 import *
from train_native16 import metrics,check_freeze
from ablation16 import GROUPS,keep_columns
import lightgbm as lgb,gc,time

def main():
    check_freeze();table=pd.read_csv(ROOT/'RADDIT_EMBEDDING_MODEL_COMPARISON.csv').set_index('arm')
    base=table.loc['EMB_D0'];rich=table.loc['EMB_D2']
    gain_min=rich.min_fold_coverage-base.min_fold_coverage;gain_tail=rich.gt4h_coverage-base.gt4h_coverage;ratio=rich.Q90_pinball/base.Q90_pinball
    assert (gain_min>=.05 or gain_tail>=.05) and ratio<=1.05
    if not (ROOT/'PAIRED_ABLATION_EXECUTION_FREEZE.json').exists():
        write('PAIRED_ABLATION_EXECUTION_FREEZE.json',dict(time=now(),before_any_paired_ablation_fit=True,
            trigger='User section22: any candidate >=+5pp min-fold OR >4h, with <=5% pinball degradation',
            cohort='Same three predeclared unique-mapped embedding cohorts; TRAIN100000 cap and exact fixed samples',
            candidate='EMB_D2',reference='EMB_D0',delta_min_fold=float(gain_min),delta_gt4h=float(gain_tail),pinball_ratio=float(ratio),
            groups=GROUPS,parameters='Unchanged PREREGISTRATION LightGBM settings',F='NOT_APPLICABLE_NO_NEIGHBORS',
            status='Conditional diagnostic scope extension after paired-cohort results; not an unseen pre-result registration',
            original_preregistration_scope='Primary full-population D1-D4 ablation trigger remains unchanged',
            primary_native_selection_affected=False,Runtime_selection_affected=False,model_code=rec(ROOT/'paired_ablation16.py'),
            omission_helper=rec(ROOT/'ablation16.py'),paired_comparison=rec(ROOT/'RADDIT_EMBEDDING_MODEL_COMPARISON.csv')))
    freeze=read(ROOT/'PAIRED_ABLATION_EXECUTION_FREEZE.json');assert sha(ROOT/'paired_ablation16.py')==freeze['model_code']['sha256']
    d=pd.read_parquet(LOCAL/'NATIVE_TABLE.parquet');mapping=pd.read_parquet(LOCAL/'EMBEDDING_KESTREL_PROXY.parquet')
    mapped=mapping.loc[mapping.status.eq('RESEARCH_PROXY_CROSSWALK'),'historic_row'].to_numpy()
    fields=RESOURCE+IDENTITY+STACK+['submit_time'];folds=[];parts={g:[] for g in GROUPS}
    for fold in [1,2,3]:
        roles=np.load(LOCAL/f'native_fold{fold}_roles.npz');tr=np.intersect1d(roles['TRAIN'],mapped);va=np.intersect1d(roles['VALID'],mapped)
        if len(tr)>100000:tr=np.sort(np.random.default_rng(1601+fold).choice(tr,100000,replace=False))
        cohort=read(LOCAL/f'embedding_fold{fold}/COHORT.json');assert ids(tr)==cohort['TRAIN_ids'] and ids(va)==cohort['VALID_ids']
        adapter=NativeAdapter().fit(d.iloc[tr][fields]);x,names,cats=adapter.transform(d.iloc[tr][fields],'EMB_D2');v,_,_=adapter.transform(d.iloc[va][fields],'EMB_D2')
        out=LOCAL/f'paired_ablation_fold{fold}';out.mkdir(exist_ok=True)
        for group in GROUPS:
            keep=keep_columns(names,group)
            if len(keep)==len(names):continue
            rp=out/(group+'.json');pp=out/(group+'.parquet')
            if not rp.exists():
                xx=x[:,keep];vv=v[:,keep];cc=[keep.index(i) for i in cats if i in keep];pred=[];models=[];start=time.perf_counter()
                for q in [.5,.9]:
                    print('PAIRED_ABLATION',fold,group,q,flush=True)
                    model=lgb.LGBMRegressor(objective='quantile',alpha=q,**read(ROOT/'PREREGISTRATION.json')['lightgbm_parameters'])
                    model.fit(xx,d.iloc[tr].wallclock_used_sec.to_numpy(),categorical_feature=cc)
                    pred.append(np.maximum(model.predict(vv),0));mp=out/f'{group}_q{int(q*100)}.txt';model.booster_.save_model(str(mp));models.append(rec(mp))
                    del model;gc.collect()
                q50,q90=pred;q90=np.maximum(q50,q90);pd.DataFrame(dict(historic_row=va,Q50=q50,Q90=q90)).to_parquet(pp,index=False)
                write(str(rp.relative_to(ROOT)),dict(time=now(),fold=fold,group=group,status='COMPLETED',TRAIN_ids=ids(tr),VALID_ids=ids(va),
                    TRAIN_N=len(tr),VALID_N=len(va),removed=[names[i] for i in range(len(names)) if i not in keep],
                    metrics=metrics(d.iloc[va],q50,q90),models=models,predictions=rec(pp),seconds=time.perf_counter()-start))
                del xx,vv
            r=read(rp);folds.append(dict(fold=fold,group=group,**r['metrics']));parts[group].append(pd.read_parquet(pp))
        del x,v,adapter;gc.collect()
    summary=[]
    for group,p in parts.items():
        if not p:summary.append(dict(group=group,status='NOT_APPLICABLE_NO_NEIGHBOR_CHANNEL'));continue
        p=pd.concat(p,ignore_index=True);m=metrics(d.iloc[p.historic_row],p.Q50.to_numpy(),p.Q90.to_numpy())
        summary.append(dict(group=group,status='COMPLETED',**m,min_fold_coverage=min(r['Q90_coverage'] for r in folds if r['group']==group),
            diagnostic_scope='Matched-cohort conditional follow-up; not primary full-population model selection'))
    pd.DataFrame(summary).to_csv(ROOT/'RADDIT_PAIRED_GROUPED_ABLATION.csv',index=False)
    pd.DataFrame(folds).to_csv(ROOT/'RADDIT_PAIRED_GROUPED_ABLATION_FOLD_METRICS.csv',index=False)
    print('PAIRED_ABLATION_COMPLETE',flush=True)

if __name__=='__main__':main()

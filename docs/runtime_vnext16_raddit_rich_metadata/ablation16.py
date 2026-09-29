"""Only the preregistered material-benefit trigger authorizes these group omissions."""
from common16 import *
from features16 import *
from train_native16 import metrics,check_freeze
import pickle,lightgbm as lgb,gc,time

GROUPS={'A':RESOURCE,'B':['qos','partition'],'C':['user','account'],
    'D':['name','script','submit_line','job_type'],'E':STACK,'F':['neighbor']}

def keep_columns(names,group):
    remove=GROUPS[group]
    def keep(n):
        # Remove all channels derived from omitted information, including pair frequencies.
        if any(n==p or n.startswith(p+'_') for p in remove):return False
        if n.endswith('_train_cooccurrence') and any(('_'+p+'_') in ('_'+n) for p in remove):return False
        # D4 neighbor retrieval/ranking uses every A-E source: omit its dependent statistics too.
        if group!='F' and n.startswith('neighbor_'):return False
        return True
    return [i for i,n in enumerate(names) if keep(n)]

def main():
    check_freeze();verdict=read(ROOT/'RADDIT_INFORMATION_VALUE_VERDICT.json');rows=[];folds=[]
    if not verdict['ablation_authorized']:
        for group in GROUPS:rows.append(dict(group=group,status='NOT_RUN_NO_MATERIAL_WIN'))
        pd.DataFrame(rows).to_csv(ROOT/'RADDIT_GROUPED_ABLATION.csv',index=False);return
    arm=verdict['ablation_arm'];d=pd.read_parquet(LOCAL/'NATIVE_TABLE.parquet');preds={g:[] for g in GROUPS}
    for fold in [1,2,3]:
        folder=LOCAL/f'native_fold{fold}';out=LOCAL/f'ablation_fold{fold}';out.mkdir(exist_ok=True)
        with (folder/'adapter.pkl').open('rb') as f:adapter=pickle.load(f)
        roles=np.load(LOCAL/f'native_fold{fold}_roles.npz');tr=roles['TRAIN'];va=roles['VALID']
        fields=RESOURCE+IDENTITY+STACK+['submit_time']
        x,names,cats=adapter.transform(d.iloc[tr][fields],arm,np.load(folder/'TRAIN_neighbor_features.npy',mmap_mode='r') if arm=='D4' else None)
        v,_,_=adapter.transform(d.iloc[va][fields],arm,np.load(folder/'VALID_neighbor_features.npy',mmap_mode='r') if arm=='D4' else None)
        for group in GROUPS:
            keep=keep_columns(names,group)
            if len(keep)==len(names):continue
            ppath=out/(group+'.parquet');rpath=out/(group+'.json')
            if not rpath.exists():
                xx=x[:,keep];vv=v[:,keep];cc=[keep.index(i) for i in cats if i in keep];pred=[];start=time.perf_counter()
                for q in [.5,.9]:
                    print('ABLATION_FIT',fold,arm,group,q,len(keep),flush=True)
                    model=lgb.LGBMRegressor(objective='quantile',alpha=q,**read(ROOT/'PREREGISTRATION.json')['lightgbm_parameters'])
                    model.fit(xx,d.iloc[tr].wallclock_used_sec.to_numpy(float),categorical_feature=cc)
                    pred.append(np.maximum(model.predict(vv),0));model.booster_.save_model(str(out/f'{group}_q{int(q*100)}.txt'))
                    del model;gc.collect()
                q50,q90=pred;q90=np.maximum(q50,q90)
                pd.DataFrame(dict(historic_row=va,Q50=q50,Q90=q90)).to_parquet(ppath,index=False)
                write(str(rpath.relative_to(ROOT)),dict(arm=arm,group=group,fold=fold,status='COMPLETED',removed=[names[i] for i in range(len(names)) if i not in keep],
                    retained=len(keep),seconds=time.perf_counter()-start,metrics=metrics(d.iloc[va],q50,q90),predictions=rec(ppath)))
                del xx,vv;gc.collect()
            p=pd.read_parquet(ppath);preds[group].append(p);folds.append(dict(arm=arm,group=group,fold=fold,**metrics(d.iloc[va],p.Q50.to_numpy(),p.Q90.to_numpy())))
        del x,v,adapter;gc.collect()
    for group,parts in preds.items():
        if not parts:rows.append(dict(arm=arm,group=group,status='NOT_APPLICABLE_GROUP_ABSENT'));continue
        p=pd.concat(parts,ignore_index=True)
        rows.append(dict(arm=arm,group=group,status='COMPLETED',**metrics(d.iloc[p.historic_row],p.Q50.to_numpy(),p.Q90.to_numpy()),
            min_fold_coverage=min(r['Q90_coverage'] for r in folds if r['group']==group)))
    pd.DataFrame(rows).to_csv(ROOT/'RADDIT_GROUPED_ABLATION.csv',index=False)
    pd.DataFrame(folds).to_csv(ROOT/'RADDIT_GROUPED_ABLATION_FOLD_METRICS.csv',index=False)
    print('ABLATIONS_COMPLETE',arm,flush=True)

if __name__=='__main__':main()

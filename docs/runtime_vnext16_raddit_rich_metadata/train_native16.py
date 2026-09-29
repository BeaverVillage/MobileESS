from common16 import *
from features16 import *
from neighbors16 import *
import lightgbm as lgb
import gc,pickle,time

def pinball(y,p,q=.9):return float(np.mean(np.maximum(q*(y-p),(q-1)*(y-p))))

def metrics(d,q50,q90):
    y=d.wallclock_used_sec.to_numpy(float);w=d.nodes_req.to_numpy(float);req=d.wallclock_req_sec.to_numpy(float)
    short=y<3600
    out=dict(N=len(y),Q90_coverage=float(np.mean(y<=q90)),Q90_pinball=pinball(y,q90),Q50_MAE=float(np.mean(np.abs(y-q50))),
        reservation_actual_seconds=float(q90.sum()/y.sum()),reservation_actual_nodeh=float((q90*w).sum()/(y*w).sum()),
        reservation_to_requested_nodeh=float((q90*w).sum()/(req*w).sum()),short_job_N=int(short.sum()),
        short_job_reservation_actual_nodeh=float((q90[short]*w[short]).sum()/(y[short]*w[short]).sum()),
        invalid_support_N=int(np.sum(~np.isfinite(q90)|~np.isfinite(q50)|(q50<0)|(q90<q50))))
    for h in [4,8,12,24]:
        ix=y>h*3600;out[f'gt{h}h_N']=int(ix.sum());out[f'gt{h}h_coverage']=float(np.mean(y[ix]<=q90[ix])) if ix.any() else None
    return out

def check_freeze():
    r=read(ROOT/'PREREGISTRATION_HASH.json')
    for p,h in r['files'].items():assert sha(ROOT/p)==h,p

def make_neighbors(d,adapter,tr,va,folder):
    outputs={};fields=list(RESOURCE+IDENTITY+STACK+['submit_time'])
    pool=d.iloc[tr];pc=adapter.codes(pool);pr=adapter.resources(pool)
    end=pool.end_time.astype('datetime64[us, UTC]').astype('int64').to_numpy()
    index=CompletedNeighborIndex(tr,end,pc,pr,pool.wallclock_used_sec.to_numpy(float),[stack_similarity(adapter.maps[c]) for c in STACK])
    audit={}
    for role,rows in [('TRAIN',tr),('VALID',va)]:
        fp=folder/f'{role}_neighbor_features.npy';ip=folder/f'{role}_neighbor_ids.npy'
        features=np.lib.format.open_memmap(fp,mode='w+',dtype=np.float32,shape=(len(rows),18))
        neighbors=np.lib.format.open_memmap(ip,mode='w+',dtype=np.int32,shape=(len(rows),64))
        empty=0;minimum_margin=None
        for start in range(0,len(rows),8192):
            stop=min(start+8192,len(rows));q=d.iloc[rows[start:stop]]
            submit=q.submit_time.astype('datetime64[us, UTC]').astype('int64').to_numpy()
            f,ix=index.query(submit,adapter.codes(q),adapter.resources(q));features[start:stop]=f;neighbors[start:stop]=ix
            empty+=int(np.sum(ix[:,0]<0))
            valid=ix>=0
            end_all=d.end_time.astype('datetime64[us, UTC]').astype('int64').to_numpy() if start==0 else end_all
            margins=submit[:,None]-end_all[np.maximum(ix,0)]
            if valid.any():
                margin=int(margins[valid].min());assert margin>0
                minimum_margin=margin if minimum_margin is None else min(margin,minimum_margin)
            if start%131072==0:print('NEIGHBORS',folder.name,role,start,len(rows),flush=True)
        features.flush();neighbors.flush();outputs[role]=np.load(fp,mmap_mode='r')
        audit[role]=dict(N=len(rows),empty_pool_queries=empty,minimum_completion_margin_us=minimum_margin,temporal_violations=0,
            neighbor_ids=rec(ip),features=rec(fp),pool='TRAIN_ONLY')
        del features,neighbors
    write(str(folder.relative_to(ROOT)/'NEIGHBOR_AUDIT.json'),audit)
    return outputs

def fit_arm(d,train,valid,adapter,arm,folder,neighbors=None,train_data=None,extra_train=None,extra_valid=None):
    receipt=folder/(arm+'.json')
    if receipt.exists():return read(receipt)
    start=time.perf_counter();td=d.iloc[train] if train_data is None else train_data;vd=d.iloc[valid]
    fields=RESOURCE+IDENTITY+STACK+['submit_time']
    base='EMB_D0' if arm=='D_EMB_DIAGNOSTIC_ONLY' else arm
    x,names,cats=adapter.transform(td[fields],base,None if neighbors is None else neighbors['TRAIN'])
    v,vnames,vcats=adapter.transform(vd[fields],base,None if neighbors is None else neighbors['VALID'])
    if extra_train is not None:
        x=sparse.hstack([x,sparse.csr_matrix(extra_train)],format='csr',dtype=np.float32)
        v=sparse.hstack([v,sparse.csr_matrix(extra_valid)],format='csr',dtype=np.float32)
        names += ['public_stored_coordinate_'+str(i) for i in range(extra_train.shape[1])]
    y=td.wallclock_used_sec.to_numpy(float);pred=[];models=[]
    params=read(ROOT/'PREREGISTRATION.json')['lightgbm_parameters']
    for q in [.5,.9]:
        print('FIT',folder.name,arm,q,'TRAIN',len(train),'VALID',len(valid),'FEATURES',len(names),flush=True)
        model=lgb.LGBMRegressor(objective='quantile',alpha=q,**params)
        model.fit(x,y,categorical_feature=cats,feature_name=names)
        p=np.maximum(model.predict(v),0);pred.append(p)
        path=folder/f'{arm}_q{int(q*100)}.txt';model.booster_.save_model(str(path));models.append(rec(path))
        del model;gc.collect()
    q50,q90=pred;q90=np.maximum(q90,q50)
    out=pd.DataFrame(dict(historic_row=valid,Q50=q50,Q90=q90));path=folder/(arm+'.parquet');out.to_parquet(path,index=False)
    result=dict(arm=arm,fold=int(folder.name[-1]),status='COMPLETED',started_utc=None,finished_utc=now(),seconds=time.perf_counter()-start,
        TRAIN_N=len(train),VALID_N=len(valid),TRAIN_ids=ids(train),VALID_ids=ids(valid),features=len(names),categorical_features=[names[i] for i in cats],
        metrics=metrics(vd,q50,q90),predictions=rec(path),models=models,diagnostic_only=True)
    write(str(receipt.relative_to(ROOT)),result)
    print('RESULT',arm,folder.name,result['metrics'],flush=True)
    del x,v;gc.collect();return result

def main(fold):
    check_freeze();d=pd.read_parquet(LOCAL/'NATIVE_TABLE.parquet')
    roles=np.load(LOCAL/f'native_fold{fold}_roles.npz');tr=roles['TRAIN'];va=roles['VALID']
    folder=LOCAL/f'native_fold{fold}';folder.mkdir(exist_ok=True)
    fields=RESOURCE+IDENTITY+STACK+['submit_time'];adapter=NativeAdapter().fit(d.iloc[tr][fields])
    with (folder/'adapter.pkl').open('wb') as f:pickle.dump(adapter,f,protocol=5)
    for arm in ['D0','D1','D2','D3']:
        fit_arm(d,tr,va,adapter,arm,folder)
    neigh=make_neighbors(d,adapter,tr,va,folder)
    fit_arm(d,tr,va,adapter,'D4',folder,neighbors=neigh)
    for arm in ['IDENTITY_ONLY','SOFTWARE_STACK']:fit_arm(d,tr,va,adapter,arm,folder)
    shuffled=shuffle_identity_within_days(d.iloc[tr].reset_index(drop=True))
    s_adapter=NativeAdapter().fit(shuffled[fields]);fit_arm(d,tr,va,s_adapter,'NEG_SHUFFLE',folder,train_data=shuffled)
    # Bijective stable random IDs preserve the categorical design EXACTLY, not destroy identity signal.
    renamed=stable_random_rename(d[fields]);a2=NativeAdapter().fit(renamed.iloc[tr])
    identical=True
    for rows in [tr,va]:
        a=adapter.transform(d.iloc[rows][fields],'D2')[0];b=a2.transform(renamed.iloc[rows],'D2')[0]
        identical &= a.shape==b.shape and np.array_equal(a.indptr,b.indptr) and np.array_equal(a.indices,b.indices) and np.array_equal(a.data,b.data,equal_nan=True)
    assert identical
    write(str((folder/'RANDOM_STABLE_ID_CONTROL.json').relative_to(ROOT)),dict(fold=fold,exact_design_matrix_equal=True,
        prediction_equal_by_same_frozen_model=True,full_TRAIN_and_VALID_checked=True,cardinality_preserved=True,
        interpretation='Bijective renaming is an identity-invariance control. It cannot disprove identity information; no additional model fit is needed.'))
    print('FOLD_COMPLETE',fold,flush=True)

if __name__=='__main__':main(int(sys.argv[1]))

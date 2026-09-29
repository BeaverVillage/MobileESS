from common16 import *
from train_native16 import check_freeze,fit_arm,metrics
from features16 import *
import pyarrow.parquet as pq
import lightgbm as lgb
import gc,time,pickle

def extract():
    check_freeze();layout=read(ROOT/'EMBEDDING_LAYOUT_AUDIT.json');n=sum(r['rows'] for r in layout['chunks'])
    path=LOCAL/'PUBLIC_STORED_COORDINATES.npy'
    if (ROOT/'EMBEDDING_EXTRACTION_RECEIPT.json').exists():
        assert rec(path)==read(ROOT/'EMBEDDING_EXTRACTION_RECEIPT.json')['output'];return
    arr=np.lib.format.open_memmap(path,mode='w+',dtype=np.int8,shape=(n,4096))
    offset=0;lo=127;hi=-128;chunks=[]
    for i,r in enumerate(layout['chunks']):
        p=Path(r['path']);f=pq.ParquetFile(p)
        submit=f.read(columns=['submit_time']).column(0).to_pandas()
        assert submit.max()<pd.Timestamp('2025-04-01')
        before=offset
        for batch in f.iter_batches(batch_size=256,columns=['enc_embedding_int8']):
            a=batch.column(0);assert a.null_count==0
            lengths=np.diff(a.offsets.to_numpy());assert np.all(lengths==4096)
            values=a.values.to_numpy(zero_copy_only=False).reshape(len(a),4096)
            assert np.isfinite(values).all() and values.min()>=-128 and values.max()<=127
            lo=min(lo,int(values.min()));hi=max(hi,int(values.max()))
            arr[offset:offset+len(a)]=values.astype(np.int8);offset+=len(a)
        chunks.append(dict(chunk=i,rows=offset-before,submit_min=str(submit.min()),submit_max=str(submit.max())))
        print('EMBEDDING_EXTRACTED',i,offset,flush=True)
        arr.flush();gc.collect()
    assert offset==n
    write('EMBEDDING_EXTRACTION_RECEIPT.json',dict(time=now(),N=n,dimensions=4096,dtype='int8',minimum=lo,maximum=hi,
        transform='NONE: direct stored coordinates; exact integer validation before narrowing dtype',output=rec(path),chunks=chunks,May_2025_payload_opened=False))

def run(fold):
    check_freeze();d=pd.read_parquet(LOCAL/'NATIVE_TABLE.parquet')
    mapping=pd.read_parquet(LOCAL/'EMBEDDING_KESTREL_PROXY.parquet')
    mapping=mapping.loc[mapping.status.eq('RESEARCH_PROXY_CROSSWALK')]
    lookup=mapping.set_index('historic_row').embedding_global_row
    roles=np.load(LOCAL/f'native_fold{fold}_roles.npz')
    tr=np.intersect1d(roles['TRAIN'],lookup.index);va=np.intersect1d(roles['VALID'],lookup.index)
    rng=np.random.default_rng(1601+fold)
    if len(tr)>100000:tr=np.sort(rng.choice(tr,100000,replace=False))
    assert len(tr)>0 and len(va)>0
    folder=LOCAL/f'embedding_fold{fold}';folder.mkdir(exist_ok=True)
    fields=RESOURCE+IDENTITY+STACK+['submit_time'];adapter=NativeAdapter().fit(d.iloc[tr][fields])
    write(str((folder/'COHORT.json').relative_to(ROOT)),dict(fold=fold,TRAIN_N=len(tr),VALID_N=len(va),TRAIN_ids=ids(tr),VALID_ids=ids(va),
        both_crosswalk_levels_unique=True,TRAIN_cap=100000,production_selectable=False))
    for arm in ['EMB_D0','EMB_D2']:fit_arm(d,tr,va,adapter,arm,folder)
    path=folder/'D_EMB_DIAGNOSTIC_ONLY.json'
    if path.exists():return
    vectors=np.load(LOCAL/'PUBLIC_STORED_COORDINATES.npy',mmap_mode='r')
    ti=lookup.loc[tr].to_numpy(np.int64);vi=lookup.loc[va].to_numpy(np.int64)
    x=np.empty((len(tr),4100),np.float32);x[:,:4]=d.iloc[tr][RESOURCE].to_numpy(np.float32);x[:,4:]=vectors[ti]
    y=d.iloc[tr].wallclock_used_sec.to_numpy(float);pred=[];models=[];start=time.perf_counter()
    for q in [.5,.9]:
        print('EMB_FIT',fold,q,len(tr),len(va),flush=True)
        model=lgb.LGBMRegressor(objective='quantile',alpha=q,**read(ROOT/'PREREGISTRATION.json')['lightgbm_parameters'])
        model.fit(x,y);p=np.empty(len(va),float)
        for a in range(0,len(va),4096):
            b=min(a+4096,len(va));v=np.empty((b-a,4100),np.float32)
            v[:,:4]=d.iloc[va[a:b]][RESOURCE].to_numpy(np.float32);v[:,4:]=vectors[vi[a:b]]
            p[a:b]=np.maximum(model.predict(v),0)
        pred.append(p);mp=folder/f'D_EMB_DIAGNOSTIC_ONLY_q{int(q*100)}.txt';model.booster_.save_model(str(mp));models.append(rec(mp))
        del model;gc.collect()
    q50,q90=pred;q90=np.maximum(q50,q90)
    pp=folder/'D_EMB_DIAGNOSTIC_ONLY.parquet';pd.DataFrame(dict(historic_row=va,Q50=q50,Q90=q90)).to_parquet(pp,index=False)
    result=dict(arm='D_EMB_DIAGNOSTIC_ONLY',fold=fold,TRAIN_N=len(tr),VALID_N=len(va),TRAIN_ids=ids(tr),VALID_ids=ids(va),
        metrics=metrics(d.iloc[va],q50,q90),seconds=time.perf_counter()-start,features=4100,diagnostic_only=True,
        production_selectable=False,status='COMPLETED',models=models,predictions=rec(pp))
    write(str(path.relative_to(ROOT)),result);print('EMB_RESULT',result['metrics'],flush=True)

if __name__=='__main__':extract() if sys.argv[1]=='extract' else run(int(sys.argv[1]))

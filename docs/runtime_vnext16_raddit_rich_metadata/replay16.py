"""Fresh-process checks on frozen diagnostic models; no training."""
from common16 import *
from features16 import *
from neighbors16 import *
import pickle,lightgbm as lgb

def main(requested=None):
    d=pd.read_parquet(LOCAL/'NATIVE_TABLE.parquet');fields=RESOURCE+IDENTITY+STACK+['submit_time'];checks=[]
    for fold in (requested or [1,2,3]):
        folder=LOCAL/f'native_fold{fold}'
        saved=LOCAL/f'REPLAY_FOLD{fold}.json'
        if saved.exists() and read(saved).get('replay_code_sha256')==sha(Path(__file__)):
            checks.append(read(saved));continue
        if saved.exists() and not (LOCAL/f'REPLAY_FOLD{fold}_INITIAL.json').exists():
            (LOCAL/f'REPLAY_FOLD{fold}_INITIAL.json').write_bytes(saved.read_bytes())
        with (folder/'adapter.pkl').open('rb') as f:adapter=pickle.load(f)
        roles=np.load(LOCAL/f'native_fold{fold}_roles.npz');tr=roles['TRAIN'];va=roles['VALID']
        chosen=va[np.linspace(0,len(va)-1,24,dtype=int)];query=d.iloc[chosen][fields]
        x,n,c=adapter.transform(query,'D2')
        q50=lgb.Booster(model_file=str(folder/'D2_q50.txt')).predict(x,num_threads=1)
        model=lgb.Booster(model_file=str(folder/'D2_q90.txt'));q90=np.maximum(np.maximum(model.predict(x,num_threads=1),0),np.maximum(q50,0))
        frozen=pd.read_parquet(folder/'D2.parquet').set_index('historic_row').loc[chosen]
        np.testing.assert_allclose(np.maximum(q50,0),frozen.Q50,rtol=1e-12,atol=1e-9)
        np.testing.assert_allclose(q90,frozen.Q90,rtol=1e-12,atol=1e-9)
        # Later rows and their metadata are irrelevant to the frozen adapter/current query.
        later=d.iloc[va[-32:]][fields].copy();later['user']='POISON_FUTURE_USER';later['script']='POISON_FUTURE_SCRIPT'
        later['submit_time']=query.submit_time.max()+pd.Timedelta(days=1)
        later['wallclock_req_sec']=1e12
        future_table=pd.concat([query,later],ignore_index=True)
        xp,_,_=adapter.transform(future_table.iloc[:len(query)],'D2')
        np.testing.assert_array_equal(x.toarray(),xp.toarray())
        np.testing.assert_array_equal(model.predict(x,num_threads=1),model.predict(xp,num_threads=1))
        permutation=np.random.default_rng(1601).permutation(len(query))
        xx,_,_=adapter.transform(query.iloc[permutation],'D2')
        np.testing.assert_array_equal(model.predict(xx,num_threads=1),model.predict(x,num_threads=1)[permutation])
        unseen=query.iloc[:1].copy();unseen['user']='UNSEEN_USER';unseen['script']='UNSEEN_SCRIPT'
        ux,_,_=adapter.transform(unseen,'D2');assert np.isfinite(model.predict(ux)).all()
        # Rebuild the TRAIN-only index and verify saved neighbor IDs/statistics on real VALID queries.
        p=d.iloc[tr]
        index=CompletedNeighborIndex(tr,p.end_time.astype('datetime64[us, UTC]').astype('int64').to_numpy(),
            adapter.codes(p),adapter.resources(p),p.wallclock_used_sec.to_numpy(),[stack_similarity(adapter.maps[c]) for c in STACK])
        nf,ni=index.query(query.submit_time.astype('datetime64[us, UTC]').astype('int64').to_numpy(),adapter.codes(query),adapter.resources(query))
        pos=np.searchsorted(va,chosen)
        np.testing.assert_array_equal(ni,np.load(folder/'VALID_neighbor_ids.npy',mmap_mode='r')[pos])
        np.testing.assert_array_equal(nf,np.load(folder/'VALID_neighbor_features.npy',mmap_mode='r')[pos])
        checks.append(dict(fold=fold,N=len(query),replay_code_sha256=sha(Path(__file__)),fresh_process_model_prediction_parity=True,permutation_parity=True,
            future_metadata_prediction_unchanged=True,unseen_diagnostic_inference_finite=True,neighbor_ids_and_features_exact_replay=True))
        write(str(saved.relative_to(ROOT)),checks[-1])
        print('REPLAY',fold,flush=True)
    if not all((LOCAL/f'REPLAY_FOLD{i}.json').exists() for i in [1,2,3]):return
    checks=[read(LOCAL/f'REPLAY_FOLD{i}.json') for i in [1,2,3]]
    write('NATIVE_ADAPTER_REPLAY_AUDIT.json',dict(time=now(),PASS=True,checks=checks,scope='Research diagnostic adapter only; not V42 production authority',
        V42_provider_callability_claim=False,online_refits=0,raw_strings_sent_to_optimizer=False))

if __name__=='__main__':main([int(x) for x in sys.argv[1:]] or None)

from common16 import *
from bridge16 import metadata,RichCategoryAdapter,CompletedNeighborIndex
sys.path.insert(0,str(V13))
import common13,model13,lightgbm as lgb,pickle

def main(requested=None):
    assert read(ROOT/'RADDIT_INFORMATION_VALUE_VERDICT.json')['deployable_bridge_authorized']
    source=pd.read_parquet(V15/'.local/GPU_SUBMISSION_METADATA.parquet').set_index('id')
    state=pd.read_parquet(V13/'.local/CURRENT_STATE_FEATURES.parquet').set_index('job_id');checks=[]
    for fold in (requested or range(1,6)):
        receipt_path=LOCAL/f'BRIDGE_REPLAY_FOLD{fold}.json'
        if receipt_path.exists():
            prior=read(receipt_path);assert prior['code']==rec(Path(__file__))
            checks.extend(prior['checks']);continue
        folder=LOCAL/f'runtime_fold{fold}';va=common13.data(fold,'VALID');tr=common13.data(fold,'TRAIN');pre=common13.prep(fold)
        adapter=RichCategoryAdapter.load(folder/'rich_adapter.json')
        mv=metadata(source,va);cv=adapter.transform(mv)
        cols=model13.columns('EXPANDING_S4',pre['columns'],state.columns);x=model13.matrix(va,pre,state,cols)
        b=pd.concat([x,cv],axis=1);ix=np.linspace(0,len(va)-1,32,dtype=int)
        # Reconstruct the completed TRAIN index independently in this fresh process.
        ct=adapter.transform(metadata(source,tr));audit=read(folder/'NEIGHBOR_AUDIT.json')
        fields=['num_nodes_req','num_cores_req','requested_memory_mib','requested_seconds','num_gpus_req']
        def resource(f):return np.nan_to_num((np.log1p(np.maximum(f[fields].to_numpy(float),0))-np.array(audit['normalization_center']))/np.array(audit['normalization_scale'])).astype(np.float32)
        def codes(c):
            out=np.full((len(c),10),-1,np.int32);out[:,0]=c.rich_user;out[:,7]=c.rich_submit_line;return out
        completed=np.flatnonzero(tr.event.to_numpy(bool));end=tr.end_time.astype('datetime64[us, UTC]').astype('int64').to_numpy()
        ni=CompletedNeighborIndex(completed,end[completed],codes(ct)[completed],resource(tr)[completed],tr.runtime_seconds.to_numpy()[completed],[np.zeros((1,1)),np.zeros((1,1))])
        nf,neighbors=ni.query(va.iloc[ix].submit_time.astype('datetime64[us, UTC]').astype('int64').to_numpy(),codes(cv.iloc[ix]),resource(va.iloc[ix]))
        np.testing.assert_array_equal(neighbors,np.load(folder/'VALID_neighbor_ids.npy',mmap_mode='r')[ix])
        np.testing.assert_array_equal(nf,np.load(folder/'VALID_neighbor_features.npy',mmap_mode='r')[ix])
        del ni
        for j in ix:
            row=va.iloc[j];receipt=dict(submit_time=str(row.submit_time),observed_time=str(row.submit_time),namespace='kestrel-job-anon-v1',metadata=mv.iloc[j].to_dict())
            np.testing.assert_array_equal(adapter.record(receipt,row.submit_time),cv.iloc[[j]])
        for arm in ['R16-A','R16-B','R16-C']:
            bb=b
            if arm=='R16-C':bb=pd.concat([b,pd.DataFrame(np.load(folder/'VALID_neighbor_features.npy'),columns=[f'rich_neighbor_{i}' for i in range(18)])],axis=1)
            if arm=='R16-B':
                q50=np.maximum(lgb.Booster(model_file=str(folder/f'{arm}_q50.txt')).predict(bb.iloc[ix].to_numpy(),num_threads=1),0)
                q90=np.maximum(lgb.Booster(model_file=str(folder/f'{arm}_q90.txt')).predict(bb.iloc[ix].to_numpy(),num_threads=1),q50)
                q=np.column_stack([q50,q90])
                unseen=bb.iloc[[ix[0]]].copy();unseen['rich_user']=-1;unseen['rich_submit_line']=-1
                raw=[float(lgb.Booster(model_file=str(folder/f'{arm}_q{a}.txt')).predict(unseen.to_numpy(),num_threads=1)[0]) for a in [50,90]]
                assert np.isfinite(raw).all()
            else:
                model=model13.Hazard.load(folder/arm);assert model.meta['rich_adapter_sha256']==sha(folder/'rich_adapter.json')
                par=model.parameters(bb.iloc[ix],threads=1);q=np.column_stack([model.inverse_logsf(par,np.log1p(-p)) for p in [.5,.9]])
                unseen=bb.iloc[[ix[0]]].copy();unseen['rich_user']=-1;unseen['rich_submit_line']=-1
                up=model.parameters(unseen,threads=1)
                uq=np.column_stack([model.inverse_logsf(up,np.log1p(-p)) for p in [.5,.9]])
                assert np.isfinite(uq).all() and (uq>=0).all() and uq[0,1]>=uq[0,0]
            expected=np.load(folder/(arm+'_quantiles.npz'))['q'][ix]
            np.testing.assert_allclose(q,expected,rtol=1e-12,atol=1e-9)
            checks.append(dict(fold=fold,arm=arm,N=len(ix),frozen_prediction_replay=True,receipt_adapter_parity=True))
        end=tr.end_time.astype('datetime64[us, UTC]').astype('int64').to_numpy()
        for role,f in [('TRAIN',tr),('VALID',va)]:
            ids=np.load(folder/f'{role}_neighbor_ids.npy',mmap_mode='r');submit=f.submit_time.astype('datetime64[us, UTC]').astype('int64').to_numpy()
            for start in range(0,len(f),8192):
                stop=min(start+8192,len(f));ni=ids[start:stop];valid=ni>=0
                assert tr.event.to_numpy()[np.maximum(ni,0)][valid].all()
                assert ((submit[start:stop,None]-end[np.maximum(ni,0)])[valid]>0).all()
        write(str(receipt_path.relative_to(ROOT)),dict(time=now(),PASS=True,code=rec(Path(__file__)),fold=fold,
            checks=[c for c in checks if c['fold']==fold],all_neighbor_pool_and_completion_checks=True,sampled_neighbor_rebuild=True))
        print('BRIDGE_REPLAY',fold,flush=True)
    if not all((LOCAL/f'BRIDGE_REPLAY_FOLD{i}.json').exists() for i in range(1,6)):return
    receipts=[read(LOCAL/f'BRIDGE_REPLAY_FOLD{i}.json') for i in range(1,6)]
    assert all(r['PASS'] and r['code']==rec(Path(__file__)) for r in receipts)
    checks=[c for r in receipts for c in r['checks']]
    write('RUNTIME_BRIDGE_REPLAY_AUDIT.json',dict(time=now(),PASS=True,checks=checks,all_neighbor_pool_and_completion_checks=True,
        sampled_neighbor_ids_and_features_rebuilt=True,replay_code=rec(Path(__file__)),
        new_metadata_whitelist=['user','submit_line'],future_outcome_rejection_tests='test_bridge16.py',
        scope='Frozen research predictor and accepted-receipt interface; not attestation of an operational namespace/capture service',
        V42_operational_provider_implemented=False,baseline_state_causality=rec(V13/'CURRENT_STATE_CAUSALITY_AUDIT.json'),baseline_state_replay=rec(V13/'CURRENT_STATE_REPLAY_AUDIT.json')))

if __name__=='__main__':main([int(x) for x in sys.argv[1:]] or None)

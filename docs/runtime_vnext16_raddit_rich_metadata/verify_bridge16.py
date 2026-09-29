"""Read-only independent recomputation of all completed GPU bridge predictions."""
from common16 import *
sys.path.insert(0,str(V13))
import common13,train13

def verify():
    freeze=read(ROOT/'RUNTIME_BRIDGE_EXECUTION_FREEZE.json')
    assert rec(ROOT/'bridge16.py')==freeze['model_code']
    assert rec(ROOT/'semantic_payload_v2_candidate.py')==freeze['payload_code']
    replay=read(ROOT/'RUNTIME_BRIDGE_REPLAY_AUDIT.json');assert replay['PASS'] and len(replay['checks'])==15
    assert replay['replay_code']==rec(ROOT/'bridge_replay16.py')
    for fold in range(1,6):
        receipt=read(LOCAL/f'BRIDGE_REPLAY_FOLD{fold}.json')
        assert receipt['PASS'] and receipt['code']==replay['replay_code']
    table=pd.read_csv(ROOT/'RUNTIME_V16_MODEL_COMPARISON.csv').set_index('arm')
    foldtable=pd.read_csv(ROOT/'RUNTIME_V16_FOLD_METRICS.csv').set_index(['arm','fold'])
    inputs=read(V15/'RUNTIME_INPUT_RECEIPT.json')['memberships']
    total=0;rows=0;files=0
    for arm in ['R16-A','R16-B','R16-C']:
        parts=[];coverages=[]
        for fold in range(1,6):
            folder=LOCAL/f'runtime_fold{fold}';r=read(folder/(arm+'.json'))
            tr=common13.data(fold,'TRAIN');va=common13.data(fold,'VALID');event=va.event.to_numpy(bool)
            for role,data in [('TRAIN',tr),('VALID',va)]:
                assert r[role+'_membership']==common13.ids(data)==inputs[f'{fold}_{role}']['membership']
            for artifact in r['artifacts']:
                assert rec(Path(artifact['path']))==artifact;files+=1
            p=pd.read_parquet(folder/(arm+'.parquet'));q=np.load(folder/(arm+'_quantiles.npz'))['q']
            assert q.shape==(len(va),2) and np.isfinite(q).all() and (q>=0).all() and (q[:,1]>=q[:,0]).all()
            np.testing.assert_array_equal(p.job_id,va.loc[event,'job_id'])
            np.testing.assert_array_equal(p[['q50','q90']],q[event])
            for col in ['runtime_seconds','num_gpus_req','requested_seconds']:
                np.testing.assert_array_equal(p[col],va.loc[event,col])
            m=train13.stats(p.runtime_seconds,p.num_gpus_req,p.q50,p.q90);m.update(train13.sharpness(p))
            for h in [4,8,12,24]:
                z=p[p.runtime_seconds>h*3600];m[f'gt{h}h_N']=len(z);m[f'gt{h}h_coverage']=float((z.runtime_seconds<=z.q90).mean())
            for key,val in m.items():
                assert np.isclose(val,r[key],rtol=1e-12,atol=1e-9,equal_nan=True),(arm,fold,key)
                assert np.isclose(val,foldtable.loc[(arm,fold),key],rtol=1e-12,atol=1e-9,equal_nan=True)
            if arm=='R16-B':
                assert r['proper_interval_NLL'] is None and r['zero_support_count'] is None
                assert not r['proper_score_finite'] and r['actual_TRAIN_exact_label_N']==int(tr.event.sum())
            else:assert r['proper_score_finite'] and np.isfinite(r['proper_interval_NLL']) and r['zero_support_count']==0
            coverages.append(m['Q90_coverage']);parts.append(p);total+=1;rows+=len(va)
        p=pd.concat(parts,ignore_index=True);m=train13.stats(p.runtime_seconds,p.num_gpus_req,p.q50,p.q90)
        m['min_fold_coverage']=min(coverages)
        for h in [4,8,12,24]:
            z=p[p.runtime_seconds>h*3600];m[f'gt{h}h_N']=len(z);m[f'gt{h}h_coverage']=float((z.runtime_seconds<=z.q90).mean())
        for key,val in m.items():assert np.isclose(val,table.loc[arm,key],rtol=1e-12,atol=1e-9,equal_nan=True),(arm,key)
        r=table.loc[arm]
        expected=[.88<=m['Q90_coverage']<=.92,m['min_fold_coverage']>=.85,m['gt4h_coverage']>=.85,
            m['gt12h_N']<100 or m['gt12h_coverage']>=.80,m['gt24h_N']<100 or m['gt24h_coverage']>=.70,
            r.reservation_to_W0<=.8,arm!='R16-B',arm!='R16-B',True]
        assert [bool(r['gate_'+g]) for g in 'ABCDEFGHI']==[bool(v) for v in expected]
        assert bool(r.eligible)==all(expected)
    result=dict(PASS=True,arm_folds=total,all_VALID_quantile_rows=rows,artifact_receipts_checked=files,
        exact_previous_memberships=True,full_quantile_support_checked=True,metrics_and_safety_gates_recomputed=True,
        fresh_process_replay=rec(ROOT/'RUNTIME_BRIDGE_REPLAY_AUDIT.json'))
    write('RUNTIME_BRIDGE_VERIFICATION.json',result)
    return result

if __name__=='__main__':print(verify(),flush=True)

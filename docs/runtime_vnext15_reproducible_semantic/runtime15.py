"""Frozen V13 hazard architecture, two semantic challengers, no model-family search."""
from common15 import *
sys.path.insert(0,str(REPO));sys.path.insert(0,str(V13))
import model13,train13,common13
from v42.semantic_adapter import SemanticFeatureAdapter,historical_payload,SubmissionSemanticRecord
import time,gc

def guard():
    freeze=read(ROOT/'PREREGISTRATION_HASH.json')
    assert sha(ROOT/'PREREGISTRATION.json')==freeze['sha256']
    for p,h in read(ROOT/'PREREGISTRATION.json')['implementation_sha256'].items():assert sha(REPO/p)==h,p

def one(i,source,regime):
    folder=LOCAL/f'runtime_fold{i}';folder.mkdir(exist_ok=True)
    tr=common13.data(i,'TRAIN');va=common13.data(i,'VALID');pre=common13.prep(i)
    members=read(ROOT/'RUNTIME_INPUT_RECEIPT.json')['memberships']
    for role,d in [('TRAIN',tr),('VALID',va)]:assert common13.ids(d)==members[f'{i}_{role}']['membership']
    assert tr.loc[tr.event,'end_time'].lt(pd.Timestamp(pre['fit_cutoff'])).all()
    train_payload=[historical_payload(r) for r in source.loc[tr.job_id].to_dict('records')]
    valid_payload=[historical_payload(r) for r in source.loc[va.job_id].to_dict('records')]
    bundle=folder/'adapter'
    if (bundle/'adapter.json').exists():adapter=SemanticFeatureAdapter.load(bundle)
    else:
        print(now(),'SVD_FIT',i,len(tr),flush=True)
        adapter=SemanticFeatureAdapter().fit(train_payload,training_receipt=dict(TRAIN_ONLY=True,
            membership_sha256=common13.ids(tr),fit_cutoff=pre['fit_cutoff'],fold=i,rows=len(tr),label_input=False))
        adapter.save(bundle)
    st,rt=adapter.transform(train_payload);sv,rv=adapter.transform(valid_payload)
    loaded=SemanticFeatureAdapter.load(bundle)
    perm=np.random.default_rng(1401).permutation(min(len(va),64));test_payload=[valid_payload[j] for j in perm]
    np.testing.assert_array_equal(loaded.transform(test_payload)[0],sv[perm])
    for j in perm[:8]:
        record=SubmissionSemanticRecord('parity-'+str(j),str(va.iloc[j].submit_time),str(va.iloc[j].submit_time),valid_payload[j])
        numeric=adapter.transform_record(record,record.submit_time)
        np.testing.assert_array_equal(numeric.sem,sv[j]);np.testing.assert_array_equal(numeric.recurrence,rv[j])
    write(folder/'SEMANTIC_FOLD_PARITY.json',dict(PASS=True,fold=i,TRAIN_N=len(tr),VALID_N=len(va),
        TRAIN_membership=common13.ids(tr),VALID_membership=common13.ids(va),bundle=adapter.bundle_sha256,
        persisted_transform_bitwise=True,shuffled_transform_bitwise=True,historical_event_bitwise=True,
        SVD_TRAIN_only=True,recurrence_TRAIN_only=True,optional_missing_policy='FIELD_MISSING',
        direct_semantic_shape=list(sv.shape),recurrence_features=adapter.recurrence_names))
    cols=model13.columns('EXPANDING_S4',pre['columns'],regime.columns)
    xt=model13.matrix(tr,pre,regime,cols);xv=model13.matrix(va,pre,regime,cols)
    for arm in ['R1','R2']:
        result=folder/(arm+'.json')
        if result.exists() and (folder/(arm+'.parquet')).exists():continue
        rn=adapter.recurrence_names
        a=pd.concat([xt,pd.DataFrame(rt,columns=rn)],axis=1)
        b=pd.concat([xv,pd.DataFrame(rv,columns=rn)],axis=1)
        if arm=='R2':
            sn=[f'sem_{j:02}' for j in range(32)]
            a=pd.concat([a,pd.DataFrame(st,columns=sn)],axis=1);b=pd.concat([b,pd.DataFrame(sv,columns=sn)],axis=1)
        dest=folder/arm
        print(now(),'HAZARD_FIT',i,arm,len(tr),len(a.columns),flush=True)
        if (dest/'model.json').exists():model=model13.Hazard.load(dest)
        else:
            model=model13.fit(tr,a,pre,arm)
            model.meta.update(semantic_feature_version='SEM_COOCCUR32_V1',semantic_bundle_sha256=adapter.bundle_sha256,semantic_whitelist=list(adapter.whitelist),research_only=True)
            model.save(dest)
        del a;gc.collect()
        start=time.perf_counter();par=model.parameters(b,threads=4);seconds=time.perf_counter()-start
        s,p,q=train13.evaluate(model,par,va)
        s.update(fold=i,arm=arm,calibration='C0',training_seconds=model.meta['training_seconds'],inference_seconds=seconds,
                 TRAIN_N=len(tr),VALID_N=len(va),features=len(b.columns),semantic_bundle_sha256=adapter.bundle_sha256)
        p.to_parquet(folder/(arm+'.parquet'),index=False);np.savez_compressed(folder/(arm+'_quantiles.npz'),q=q)
        write(result,s)
        print(now(),'DONE',i,arm,'Q90',s['Q90_coverage'],'gt4h',s['gt4h_coverage'],flush=True)
        del model,b,par;gc.collect()
    del xt,xv,train_payload,valid_payload,st,sv,rt,rv,adapter,loaded;gc.collect()

def collect():
    summaries=[];folds=[];tails=[];sharp=[];baseline_receipts=[]
    for arm in ['R0','R1','R2']:
        fs=[];parts=[]
        for i in range(1,6):
            directory=V13/'.local'/f'fold{i}' if arm=='R0' else LOCAL/f'runtime_fold{i}'
            name='EXPANDING_S4' if arm=='R0' else arm
            s=read(directory/(name+'.json'));p=pd.read_parquet(directory/(name+'.parquet'))
            s.update(arm=arm,calibration='C0');fs.append(s);parts.append(p);folds.append(s)
            if arm=='R0':baseline_receipts.extend([rec(directory/(name+'.json')),rec(directory/(name+'.parquet')),rec(directory/(name+'_quantiles.npz'))])
            for hours in [4,8,12,24]:
                z=p[p.runtime_seconds>hours*3600]
                tails.append(dict(arm=arm,fold=i,threshold_hours=hours,**train13.stats(z.runtime_seconds,z.num_gpus_req,z.q50,z.q90)))
            sharp.append(dict(arm=arm,fold=i,**train13.sharpness(p)))
        pooled=train13.summarize(arm,fs,parts)
        pooled['gate_I']=pooled['gate_I'] and read(ROOT/'RUNTIME_SEMANTIC_CAUSALITY_AUDIT.json')['PASS']
        pooled['eligible']=all(pooled[f'gate_{c}'] for c in 'ABCDEFGHI')
        summaries.append(pooled)
    frame=pd.DataFrame(summaries);base=frame.iloc[0]
    original=pd.read_csv(V13/'TOTAL_MODEL_COMPARISON.csv').query("arm=='EXPANDING_S4' and calibration=='C0'").iloc[0]
    for key in ['Q90_coverage','Q90_pinball','min_fold_coverage','gt4h_coverage','reservation_actual_GPUh','proper_interval_NLL']:
        assert np.isclose(base[key],original[key],rtol=1e-13,atol=1e-12),key
    frame['delta_min_fold_vs_R0']=frame.min_fold_coverage-base.min_fold_coverage
    frame['delta_gt4h_vs_R0']=frame.gt4h_coverage-base.gt4h_coverage
    frame['pinball_relative_vs_R0']=frame.Q90_pinball/base.Q90_pinball-1
    frame['material_benefit']=((frame.delta_min_fold_vs_R0>=.05)|(frame.delta_gt4h_vs_R0>=.05))&(frame.pinball_relative_vs_R0<=.05)
    frame.to_csv(ROOT/'RUNTIME_MODEL_COMPARISON.csv',index=False)
    pd.DataFrame(folds).to_csv(ROOT/'RUNTIME_FOLD_METRICS.csv',index=False)
    pd.DataFrame(tails).to_csv(ROOT/'RUNTIME_LONG_TAIL_METRICS.csv',index=False)
    pd.DataFrame(sharp).to_csv(ROOT/'RUNTIME_SHARPNESS_METRICS.csv',index=False)
    write('R0_BASELINE_REPRODUCTION.json',dict(PASS=True,model_refits=0,scope='Reused verified exact V13 S4 predictions; independently recomputed summaries',checks=baseline_receipts))
    valid=frame[frame.eligible].sort_values(read(V13/'EXPERIMENT_PROTOCOL.json')['ranking'])
    selected=None if valid.empty else valid.iloc[0].arm
    write('RUNTIME_SELECTION_FREEZE.json',dict(time=now(),selected=selected,all_safety_gates_pass=bool(selected),
        R3='NOT_APPLICABLE_NO_TEXT_CHANNEL',broad_ablation='NOT_RUN_NO_MATERIAL_BENEFIT' if not frame.iloc[1:].material_benefit.any() else 'NOT_RUN_OPTIONAL_R1_R2_CONTRAST_ALREADY_AVAILABLE',
        material_benefit_arms=frame.loc[frame.material_benefit,'arm'].tolist(),
        new_hazard_fits=10,new_historical_SVD_fits=5,April_used=False,May_opened=False,
        source_version_scope='Immutable submission identity/command concepts; no archive ingestion-time certification',
        comparison=rec(ROOT/'RUNTIME_MODEL_COMPARISON.csv')))
    print('RUNTIME_COMPLETE',selected,flush=True)

def main():
    guard()
    source=pd.read_parquet(LOCAL/'GPU_SUBMISSION_METADATA.parquet').set_index('id')
    regime=pd.read_parquet(V13/'.local/CURRENT_STATE_FEATURES.parquet').set_index('job_id')
    for i in range(1,6):one(i,source,regime)
    collect()
if __name__=='__main__':main()

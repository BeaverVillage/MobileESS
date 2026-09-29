"""Fresh-process, no-fit future-input checks against completed research fold models."""
from common15 import *
sys.path.insert(0,str(REPO));sys.path.insert(0,str(V13))
import common13,model13
from dataclasses import replace
from v42.semantic_adapter import *
from v42.semantic_integration import require_selected_model

def main():
    fold=1;folder=LOCAL/'runtime_fold1';adapter=SemanticFeatureAdapter.load(folder/'adapter')
    source=pd.read_parquet(LOCAL/'GPU_SUBMISSION_METADATA.parquet').set_index('id')
    train=common13.data(fold,'TRAIN');valid=common13.data(fold,'VALID');pre=common13.prep(fold)
    known=historical_payload(source.loc[train.job_id.iloc[0]].to_dict())
    cases=dict(A_known=known,B_unseen_identity=replace(known,user='unseen-fixture-user',submit_line='unseen-fixture-command'),
        C_missing=SubmissionSemanticPayload(partition='gpu',qos='normal'),
        D_new_account=replace(known,account='unseen-fixture-account'),
        E_unicode=SubmissionSemanticPayload(user='사용자',submit_line='실행 --옵션 ⚙',identity_namespace='future-site-v1'))
    payload=list(cases.values());sem,recurrence=adapter.transform(payload)
    regime=pd.read_parquet(V13/'.local/CURRENT_STATE_FEATURES.parquet').set_index('job_id')
    results=[];before=adapter.bundle_sha256
    for arm in ['R1','R2']:
        model=model13.Hazard.load(folder/arm);assert model.meta['semantic_bundle_sha256']==adapter.bundle_sha256
        cols=model.meta['columns'];basecols=[c for c in cols if not c.startswith(('sem_','rec_'))]
        # Fixed synthetic state fixture using existing causal numeric feature shape.
        # No outcome columns are supplied to the submission semantic adapter.
        candidates=model13.matrix(valid,pre,regime,basecols)
        complete=np.flatnonzero(np.isfinite(candidates.to_numpy()).all(axis=1))
        assert len(complete)>0
        fixture_row=int(complete[0]);base=candidates.iloc[[fixture_row]].reset_index(drop=True)
        x=pd.concat([base]*len(payload),ignore_index=True)
        for j,n in enumerate(adapter.recurrence_names):x[n]=recurrence[:,j]
        if arm=='R2':
            for j in range(32):x[f'sem_{j:02}']=sem[:,j]
        x=x[cols];rates=model.parameters(x,threads=1)
        q=np.column_stack([model.inverse_logsf(rates,np.log1p(-p)) for p in [.5,.9]])
        assert np.isfinite(x.to_numpy()).all() and np.isfinite(q).all() and (q[:,1]>=q[:,0]).all()
        for j,(name,p) in enumerate(cases.items()):
            record=SubmissionSemanticRecord('synthetic-'+name,'2099-01-01T00:00:00Z','2099-01-01T00:00:00Z',p)
            numeric=adapter.transform_record(record,record.submit_time)
            np.testing.assert_array_equal(numeric.sem,sem[j])
            results.append(dict(arm=arm,case=name,features_finite=True,Q50=float(q[j,0]),Q90=float(q[j,1]),
                semantic_support_level=numeric.support_level,online_refit=False,deployable_prediction=False,
                new_account_handling='Accepted optional payload, excluded by frozen whitelist' if name=='D_new_account' else None))
        try:require_selected_model({'ENABLE_SUBMISSION_SEMANTICS':True},'RUNTIME')
        except ValueError:pass
        else:raise AssertionError('Validation bypass')
    assert adapter.bundle_sha256==before
    np.testing.assert_array_equal(sem[0],sem[3])
    write('NEW_JOB_CALLABILITY_TEST.json',dict(time=now(),PASS=True,NEW_JOB_SEMANTIC_CALLABLE=True,
        historical_models_refit=0,fresh_process=True,diagnostic_fold=1,research_predictions_finite=True,
        no_operational_provider_authorization=True,missing_optional_rejected=False,
        cases=results,bundle_sha256=adapter.bundle_sha256,
        state_scope='Synthetic scenario reusing first complete numeric causal state fixture, selected by feature missingness only; no outcome-based choice or imputation',
        fixture_VALID_row=fixture_row,
        namespace_scope='Unseen real-input namespace transforms without error; matching private archive anonymous identities is not claimed'))
    print('CALLABILITY PASS',len(results),flush=True)
if __name__=='__main__':main()

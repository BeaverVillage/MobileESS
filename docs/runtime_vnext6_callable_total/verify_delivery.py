"""Cross-artifact verification; never retrains or repairs a frozen scientific result."""
from paths import *
import sys,hashlib,subprocess,ast
import numpy as np,pandas as pd

REQUIRED=['RUNTIME_EXISTING_MODEL_INVENTORY.json','RUNTIME_LINEAGE_AUDIT.md','EXPERIMENT_PROTOCOL.json','DATA_SPLIT_AND_MATURITY.json','FEATURE_CONTRACT.json','FEATURE_CAUSALITY_AUDIT.json',
 'TRAIN_BACKEND_BENCHMARK.csv','TRAIN_BACKEND_SELECTION.json','MODEL_COMPARISON.csv','STRATIFIED_METRICS.csv','GPU_WEIGHTED_METRICS.csv','PAIRED_UNCERTAINTY.csv','MODEL_SELECTION_FREEZE.json',
 'NEW_JOB_CALLABLE_TEST.json','PROVIDER_REPRODUCIBILITY_TEST.json','INFERENCE_LATENCY.json','CHECKPOINT_SUBTRACTION_DIAGNOSTIC.csv','OVERRUN_AUDIT.csv','APRIL_LOCKED_RUNTIME_METRICS.csv',
 'APRIL_WALLTIME_VS_ML_QUEUE_REPLAY.csv','FINAL_REVIEW_KO.md','FINAL_VERDICT.json','RUNTIME_LABEL_MATURITY_AUDIT.parquet','REQUEST_VERSION_AUTHORITY_AUDIT.json']
def main():
    for name in REQUIRED:assert (ROOT/name).exists(),name
    for p in ROOT.rglob('*.py'):ast.parse(p.read_text(encoding='utf-8-sig'))
    freeze=read(ROOT/'PROVIDER_BUNDLE_FREEZE.json')
    for r in freeze['files']:assert sha(ROOT/r['relative'])==r['sha256'],'PROVIDER_DRIFT '+r['relative']
    selection=read(ROOT/'MODEL_SELECTION_FREEZE.json')
    for r in selection['sources']+[selection['protocol'],selection['feature_contract']]:assert sha(r['path'])==r['sha256'],'SELECTION_CODE_DRIFT'
    assert pd.Timestamp(selection['time'])<pd.Timestamp(freeze['time'])
    assert read(ROOT/'APRIL_OPEN_RECEIPT.json')['freeze']['sha256']==sha(ROOT/'PROVIDER_BUNDLE_FREEZE.json')
    f=pd.read_parquet(ROOT/'PREAPRIL_JOBS.parquet');audit=pd.read_parquet(ROOT/'RUNTIME_LABEL_MATURITY_AUDIT.parquet');tr=f[f.role=='TRAIN']
    assert tr.end_time.lt(pd.Timestamp('2025-03-14T08:00Z')).all() and (tr.runtime_seconds>=0).all()
    assert np.array_equal(audit.eligible_for_fit,f.role.eq('TRAIN')) and tr.job_id.is_unique
    assert hashlib.sha256(('\n'.join(sorted(tr.job_id))+'\n').encode()).hexdigest()==selection['membership']['TRAIN']['membership']
    proof=pd.read_parquet(ROOT/'ROW_FEATURE_AVAILABILITY_PROOF.parquet');assert (proof.constant_bias==1).all() and (proof.request_fields_used==0).all()
    assert read(ROOT/'FEATURE_CONTRACT.json')['input_predictors']==[]
    assert read(ROOT/'REQUEST_VERSION_AUTHORITY_AUDIT.json')['UNVERIFIED_REQUEST_FEATURE_COUNT']==9
    # Independent arithmetic cross-check of locked inference and published aggregate.
    sys.path.insert(0,str(ROOT/'RUNTIME_PROVIDER'));from provider import RuntimeProvider,running_proxy
    p=RuntimeProvider(allow_research=True);g=pd.read_parquet(ROOT/'APRIL_JOBS.parquet');g=g[g.label_valid];pred=p.predict_array(len(g));metrics=pd.read_csv(ROOT/'APRIL_LOCKED_RUNTIME_METRICS.csv').set_index('model').loc['STRICT_SELECTED']
    assert abs(metrics.Q90_coverage-np.mean(g.runtime_seconds.to_numpy()<=pred[:,1]))<1e-12
    assert abs(metrics.overrun_GPUh-np.sum(g.num_gpus_req*np.maximum(g.runtime_seconds-pred[:,1],0))/3600)<1e-8
    assert read(ROOT/'APRIL_W0_REPRODUCTION.json')['PASS']
    assert read(ROOT/'NEW_JOB_CALLABLE_TEST.json')['PASS'] and read(ROOT/'PROVIDER_REPRODUCIBILITY_TEST.json')['PASS']
    assert read(ROOT/'FINAL_REFIT_RECEIPT.json')['fit_count']==2
    flags=read(ROOT/'FINAL_VERDICT.json')['flags']
    for k in ['RUNTIME_PROVIDER_READY_FOR_V42','STRICT_CAUSAL_RUNTIME_PROVIDER_READY','TOTAL_RUNTIME_Q90_GATE_PASS','OPTIMIZER_INTEGRATION_PERFORMED','APRIL_USED_FOR_SELECTION','MAY_USED_FOR_SELECTION']:assert flags[k] is False
    assert flags['MUTABLE_REQUEST_FEATURE_COUNT']==7 and flags['UNVERIFIED_REQUEST_FEATURE_COUNT']==9
    assert not p.contract['optimizer_use_allowed']
    for e in [0,55986,55987,200000]:
        r=running_proxy(55987,e,True);assert r['retain_GPU'] and r['remaining_runtime_proxy_seconds']>=0 and not r['future_end_read']
    report=(ROOT/'FINAL_REVIEW_KO.md').read_text(encoding='utf-8');assert all(f'### {i}. ' in report for i in range(1,22))
    checked=0
    for r in read(ROOT/'LINEAGE_SOURCE_HASHES.json')['files']:
        assert sha(r['path'])==r['sha256'],'PRIOR_EVIDENCE_DRIFT '+r['path'];checked+=1
    result=dict(PASS=True,required_artifacts=len(REQUIRED),previous_files_unchanged=checked,frozen_bundle_files=len(freeze['files']),training_rows=len(tr),row_feature_proof=len(proof),
      new_training_feature_reads=0,April_model_repair=False,selected_readiness_false_verified=True,final_21_questions=True)
    if '--manifest' in sys.argv:
        write('DELIVERY_VALIDATION.json',result)
        paths=sorted(p for p in ROOT.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.name!='DELIVERY_MANIFEST.json')
        write('DELIVERY_MANIFEST.json',dict(scope='docs/runtime_vnext6_callable_total only',base_commit=BASE_SHA,files=[dict(relative=str(p.relative_to(ROOT)),bytes=p.stat().st_size,sha256=sha(p)) for p in paths],
          files_N=len(paths),validation=record(ROOT/'DELIVERY_VALIDATION.json'),bundle_freeze_sha256=sha(ROOT/'PROVIDER_BUNDLE_FREEZE.json'),source_archives_external_readonly=True))
    if (ROOT/'DELIVERY_MANIFEST.json').exists():
        manifest=read(ROOT/'DELIVERY_MANIFEST.json')
        for r in manifest['files']:assert sha(ROOT/r['relative'])==r['sha256'],'DELIVERY_HASH_DRIFT '+r['relative']
        result['delivery_files_checked']=len(manifest['files'])
    print(__import__('json').dumps(result),flush=True)
if __name__=='__main__':main()

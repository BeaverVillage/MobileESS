from common8 import *
from features8 import engineer,FORBIDDEN
from model8 import Predictor
from metrics8 import uncertainty
import pandas as pd,numpy as np,shutil,sys,importlib.util,time

def main():
    sel=read(ROOT/'PRELIMINARY_SELECTION.json');assert (ROOT/'SELECTED_ABLATION_RECEIPT.json').exists()
    pp=read(ROOT/'PREPROCESSING.json');data=roles(pd.read_parquet(ROOT/'PREAPRIL_JOBS.parquet'));model=Predictor.load(ROOT/'DEVELOPMENT_MODELS'/sel['selected']);bundle=ROOT/'RUNTIME_PROVIDER';bundle.mkdir()
    shutil.copytree(ROOT/'DEVELOPMENT_MODELS'/sel['selected'],bundle/'model')
    for src,dst in [('features8.py','features8.py'),('model8.py','model8.py'),('provider_source.py','provider.py')]:shutil.copyfile(ROOT/src,bundle/dst)
    write('RUNTIME_PROVIDER/preprocessing.json',pp)
    contract=read(ROOT/'RESEARCH_TRACE_RUNTIME_FEATURE_CONTRACT.json');contract['selected_features']=model.meta['columns'];contract['RESEARCH_TRACE_FEATURE_COUNT']=len(model.meta['columns'])
    write('RUNTIME_PROVIDER/feature_contract.json',contract)
    write('RUNTIME_PROVIDER/runtime_contract.json',dict(model_version='runtime-vnext8-trace-total-v1',feature_contract_version=contract['version'],provenance_mode='Kestrel_trace_proxy',
      selected=sel['selected'],target=read(ROOT/'EXPERIMENT_PROTOCOL.json')['target'],calibration_delta_seconds=sel['delta'],calibration=sel['calibration'],
      research_only=True,production_certified=False,STRICT_CAUSAL_RUNTIME_PROVIDER_READY=False,REQUEST_VERSION_AUTHORITY_FOUND=False,
      preApril_predictive_gate_pass=sel['score'][0]==0,diagnostic_candidate_only=sel['score'][0]!=0,train_cutoff='2025-03-14T08:00Z',logical_freeze='2025-03-31T08:00Z',
      no_walltime_cap=True,online_refit_required=False,remaining_model=False))
    integrity=[dict(relative=p.relative_to(bundle).as_posix(),bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(bundle.rglob('*')) if p.is_file()]
    write('RUNTIME_PROVIDER/BUNDLE_INTEGRITY.json',dict(files=integrity,created_at=now()))
    spec=importlib.util.spec_from_file_location('runtime8_provider',bundle/'provider.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    provider=mod.RuntimeProvider(bundle,allow_research=True);inputs=provider.input_columns
    g=data['DEV'];records=g[inputs].to_dict('records');expected=pd.read_parquet(ROOT/'DEV_PREDICTIONS.parquet').set_index('job_id').loc[g.job_id,['SELECTED_CALIBRATED_Q50','SELECTED_CALIBRATED_Q90']].to_numpy()
    prediction=provider.predict_batch(records);err=float(np.max(np.abs(prediction-expected)));assert err<1e-8
    job=dict(records[0],job_id='NEW_RUNTIME8_JOB_NOT_IN_TRACE_928');a=provider.predict_total(job);job['job_id']='ANOTHER_NEVER_SEEN_ID';b=provider.predict_total(job);assert a==b
    rejects=[]
    for key in sorted(FORBIDDEN):
        try:provider.predict_total(dict(job,**{key:1}))
        except ValueError:rejects.append(key)
    assert len(rejects)==len(FORBIDDEN)
    before=sha(bundle/'preprocessing.json');unknown=dict(job,account='__NEW_ACCOUNT__',qos='__NEW_QOS__',partition='__NEW_PARTITION__');u=provider.predict_total(unknown);assert sha(bundle/'preprocessing.json')==before
    try:mod.RuntimeProvider(bundle)
    except PermissionError:optin=True
    else:optin=False
    assert optin and all(np.isfinite([a['q50_seconds'],a['q90_seconds'],u['q50_seconds'],u['q90_seconds']]))
    latency={}
    for n in [1,10,100,1000]:
        sample=[records[i%len(records)] for i in range(n)]
        for _ in range(5):provider.predict_batch(sample)
        times=[]
        for _ in range(100 if n==1 else 20):
            start=time.perf_counter();provider.predict_batch(sample);times.append((time.perf_counter()-start)*1000)
        latency[str(n)]=dict(repeats=len(times),p50_ms=float(np.median(times)),p95_ms=float(np.quantile(times,.95)),p99_ms=float(np.quantile(times,.99)),max_ms=float(max(times)),CPU_only=True)
    write('INFERENCE_LATENCY.json',dict(batches=latency,provider_load_excluded=True,warm_latency=True,no_refit=True))
    write('NEW_JOB_CALLABLE_TEST.json',dict(PASS=True,new_ids_not_looked_up=True,prediction_example=a,unknown_example=u,exact_serialization_max_abs_seconds=err,
      rejected_outcome_keys=rejects,category_mapping_unchanged=True,research_optin_required=optin,CPU_inference=True))
    over=[]
    for plan,elapsed,running in [(3600,1800,True),(3600,3600,True),(3600,7200,True),(3600,7200,False),(0,0,True)]:
        r=mod.running_proxy(plan,elapsed,running);assert r['retain_GPU']==running and not r['terminate_job'] and r['migration_recommendation']=='STAY'
        assert r['reservation_extend_seconds']==(900 if running and elapsed>=plan else 0);over.append(dict(plan=plan,elapsed=elapsed,running=running,**r))
    write('OVERRUN_CONTRACT_TEST.json',dict(PASS=True,cases=over,no_prediction_forced_completion=True))
    cis=[]
    for role in ['DEV','CAL_VALID']:
        pr=pd.read_parquet(ROOT/f'{role}_PREDICTIONS.parquet');f=data[role];p=pr[['SELECTED_CALIBRATED_Q50','SELECTED_CALIBRATED_Q90']].to_numpy();b0=pr[['B0_Q50','B0_Q90']].to_numpy()
        cis+=uncertainty(f,p,b0,role)
    pd.DataFrame(cis).to_csv(ROOT/'PAIRED_UNCERTAINTY.csv',index=False)
    selected_dec=sel['decisions'][sel['selected']+'_'+sel['calibration']]
    write('MODEL_SELECTION_FREEZE.json',dict(time=now(),selected_diagnostic_candidate=sel['selected'],selected_qualified_model=sel['score'][0]==0,
      calibration=sel['calibration'],delta_seconds=sel['delta'],selection_rationale='Preregistered lexicographic failed-gates/pinball/reservation/complexity ranking; if no eligible model, one frozen diagnostic candidate only',
      gate_results=selected_dec,all_candidates=record(ROOT/'PRELIMINARY_SELECTION.json'),no_gate_relaxation=True,train_membership=read(ROOT/'DATA_SPLIT_AND_MATURITY.json'),
      protocol=record(ROOT/'EXPERIMENT_PROTOCOL.json'),model_metadata=model.meta,compute=read(ROOT/'COMPUTE_BACKEND_SELECTION.json'),
      no_further_fit_or_selection=True,April_opened=False,May_opened=False,source_code=[record(ROOT/p) for p in ['features8.py','model8.py','train8.py','metrics8.py','provider_source.py','benchmark_selected8.py']]))
    write('FEATURE_CONTRACT_FREEZE.json',dict(time=now(),selected_features=model.meta['columns'],feature_count=len(model.meta['columns']),STRICT_CAUSAL_FEATURE_COUNT=0,
      files=[record(ROOT/p) for p in ['EXPERIMENT_PROTOCOL.json','RESEARCH_TRACE_RUNTIME_FEATURE_CONTRACT.json','PREPROCESSING.json','features8.py','RAW_FEATURE_INVENTORY.csv','IDENTITY_SUPPORT_SCREEN.csv','RUNTIME_PROVIDER/feature_contract.json']],
      PR78_unchanged=True,April_opened=False,May_opened=False))
    files=[dict(relative=p.relative_to(ROOT).as_posix(),bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(bundle.rglob('*')) if p.is_file() and '__pycache__' not in p.parts]
    write('PROVIDER_BUNDLE_FREEZE.json',dict(time=now(),files=files,selection_freeze=record(ROOT/'MODEL_SELECTION_FREEZE.json'),feature_freeze=record(ROOT/'FEATURE_CONTRACT_FREEZE.json'),
      no_April_payload_opened=True,no_May_payload_opened=True,model_modifications_after_freeze_allowed=False,research_only=True,strict_ready=False))
    print('FROZEN',sel['selected'],'qualified',sel['score'][0]==0,'latency',latency['1'],flush=True)
if __name__=='__main__':main()

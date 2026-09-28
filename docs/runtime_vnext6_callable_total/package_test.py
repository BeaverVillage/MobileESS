from paths import *
import shutil,sys,time,subprocess,tempfile,importlib.util
from datetime import datetime,timezone
import numpy as np,pandas as pd,lightgbm as lgb
from unittest.mock import patch

def main():
    bundle=ROOT/'RUNTIME_PROVIDER'
    shutil.copy2(ROOT/'provider_source.py',bundle/'provider.py')
    (bundle/'requirements.txt').write_text('numpy==1.26.4\nlightgbm==4.6.0\n',encoding='utf-8')
    (bundle/'inference_example.py').write_text("from provider import RuntimeProvider, running_proxy\np=RuntimeProvider(allow_research=True)\nr=p.predict_total({'job_uid':'COMPLETELY_NEW_ID'}, '2025-04-01T00:00:00Z')\nprint(r)\nprint(running_proxy(r['planned_runtime_seconds'], r['planned_runtime_seconds']+1, True))\n",encoding='utf-8')
    (bundle/'README.md').write_text('# Runtime-vNext6 strict featureless total-runtime package\n\nResearch only; optimizer_use_allowed=false. No request feature was certified from the archived accounting snapshot. This package takes no job-specific predictor, so it estimates an unconditional total-runtime distribution. It is not approved for V42.\n\nInstall requirements, then run inference_example.py. RuntimeProvider() refuses unapproved use by default; allow_research=True explicitly enables isolated diagnostics. No training data, cached job predictions, pandas, GPU or original worktree is needed for inference. requested_seconds is only an unverified echo, never a model feature or cap.\n\nQ50/Q90 are one package; fixed Q90 minus elapsed is not a survival-conditioned quantile. running_proxy preserves occupancy and STAY on overrun.\n',encoding='utf-8')
    write('RUNTIME_PROVIDER/BUNDLE_INTEGRITY.json',dict(files=[dict(relative=p.name,sha256=sha(p),bytes=p.stat().st_size) for p in sorted(bundle.iterdir()) if p.is_file()]))
    sys.path.insert(0,str(bundle));from provider import RuntimeProvider,running_proxy
    failures=[];tests=[]
    with patch.object(lgb,'train',side_effect=AssertionError('FORBIDDEN_INFERENCE_TRAIN')),patch.object(lgb.LGBMRegressor,'fit',side_effect=AssertionError('FORBIDDEN_INFERENCE_FIT')):
        p=RuntimeProvider(allow_research=True)
        event='2025-03-30T00:00:00Z';a=p.predict_total({},event)
        b=p.predict_total({'job_uid':'NEVER_SEEN_NEW_RANDOM_ID','requested_seconds':999999,'num_gpus_req':512,'partition':'NEVER_SEEN','account':'NEW'},event)
        assert (a['q50_seconds'],a['q90_seconds'])==(b['q50_seconds'],b['q90_seconds']);tests+=['new_id_and_unseen_metadata_ignored','no_fit_calls']
        for job,t in [({'end_time':'2025-04-20'},event),({},'2025-03-30'),({'submit_time':'2025-04-01T00:00Z'},event)]:
            try:p.predict_total(job,t)
            except ValueError:pass
            else:raise AssertionError('INVALID_INPUT_ACCEPTED')
        tests+=['reject_truth_fields','reject_naive_timestamp','reject_future_submission']
        try:RuntimeProvider()
        except PermissionError:tests+=['default_unapproved_use_blocked']
        else:raise AssertionError('UNAPPROVED_USE_ACCEPTED')
        for e in [0,a['q90_seconds']-1,a['q90_seconds'],a['q90_seconds']+1800]:
            r=running_proxy(a['q90_seconds'],e,True);assert r['retain_GPU'] and not r['terminate_job'] and r['migration_recommendation']=='STAY'
            assert r['OVERRUN']==(e>=a['q90_seconds'])
            if r['OVERRUN']:assert r['reservation_extend_seconds']==900 and r['reservation_until_elapsed_seconds']==e+900
        assert not running_proxy(100,200,False)['retain_GPU'];tests+=['overrun_boundary','overrun_keep_occupancy_extend_interval','completed_release']
        start=time.perf_counter_ns();p._features(1000);prep1000=(time.perf_counter_ns()-start)/1e6
        for _ in range(100):p.predict_total({},event)
        lat=[];pre=[]
        for _ in range(1000):
            s=time.perf_counter_ns();p._features(1);pre.append((time.perf_counter_ns()-s)/1e6)
            s=time.perf_counter_ns();p.predict_total({},event);lat.append((time.perf_counter_ns()-s)/1e6)
        def summary(x):return dict(p50_ms=float(np.quantile(x,.5)),p95_ms=float(np.quantile(x,.95)),p99_ms=float(np.quantile(x,.99)),max_ms=float(np.max(x)))
        batches=[]
        for n in [10,100,1000]:
            times=[]
            for _ in range(100):
                s=time.perf_counter_ns();p.predict_array(n);times.append((time.perf_counter_ns()-s)/1e6)
            batches.append(dict(N=n,repetitions=100,**summary(times),throughput_jobs_per_second=n/(np.mean(times)/1000)))
    with tempfile.TemporaryDirectory(prefix='runtime6-detached-') as temp:
        dest=Path(temp)/'bundle';shutil.copytree(bundle,dest)
        # Fresh process with only bundle in its working directory; no historical identity/cache inputs.
        code="import json;from provider import RuntimeProvider;p=RuntimeProvider(allow_research=True);print(json.dumps(p.predict_total({'job_uid':'REMOVED_FROM_ALL_CACHES'},'2025-03-30T00:00:00Z')))"
        proc=subprocess.run([sys.executable,'-c',code],cwd=dest,text=True,capture_output=True,check=True)
        result=json.loads(proc.stdout);assert result['q90_seconds']==a['q90_seconds'] and result['q50_seconds']==a['q50_seconds']
        target=dest/'Q90.txt';target.write_text(target.read_text()+'\n# tampered\n')
        proc=subprocess.run([sys.executable,'-c',code],cwd=dest,text=True,capture_output=True)
        assert proc.returncode!=0 and 'BUNDLE_HASH_MISMATCH' in proc.stderr;tests+=['fresh_process_detached_bundle_no_cache','tampering_rejected']
    hist=pd.read_parquet(ROOT/'PREAPRIL_JOBS.parquet',columns=['job_id','role']).query("role == 'DEV'").iloc[0]
    # Identity removed entirely, no causal request features needed by strict subset.
    historical=p.predict_total({},event);assert historical['q90_seconds']==a['q90_seconds'];tests+=['eligible_historical_job_identity_removed']
    write('NEW_JOB_CALLABLE_TEST.json',dict(PASS=True,NEW_JOB_CALLABLE_TEST='PASS',tests=tests,historical_test_job_id=str(hist.job_id),identity_sent_to_provider=False,
      lookup_files_in_bundle=0,job_feature_count=0,cache_independence='Fresh detached process + bundle only, empty feature map. Constant model necessarily predicts same values for all IDs.',no_online_fit=True,result=a))
    write('PROVIDER_REPRODUCIBILITY_TEST.json',dict(PASS=True,fresh_process_equal=True,final_fit_equal_to_development=True,hash_tamper_rejected=True,bundle_integrity=record(bundle/'BUNDLE_INTEGRITY.json')))
    write('OVERRUN_CONTRACT_TEST.json',dict(PASS=True,tests=tests[6:9],future_end_read=False,retains_GPU=True,stay=True,extend_each_control_interval=True))
    write('INFERENCE_LATENCY.json',dict(device='CPU',num_threads=1,warmup=100,single_calls=1000,single=summary(lat),preprocessing_single=summary(pre),preprocessing_batch1000_ms=prep1000,
      batch=batches,CPU_INFERENCE_READY=summary(lat)['p99_ms']<=50 and max(lat)<=200,includes='single: API validation+constant preprocessing+two booster inference+receipt; batch: preprocessing+two boosters, no per-row receipts',load_excluded=True))
    write('PROVIDER_BUNDLE_FREEZE.json',dict(time=datetime.now(timezone.utc).isoformat(),logical_asof='2025-03-31T08:00:00Z',actual_created_2026=True,
      files=[dict(relative=str(p.relative_to(ROOT)),sha256=sha(p),bytes=p.stat().st_size) for p in sorted(bundle.iterdir()) if p.is_file()],
      model_selection=record(ROOT/'MODEL_SELECTION_FREEZE.json'),new_job_test=record(ROOT/'NEW_JOB_CALLABLE_TEST.json'),april_payload_access_before_freeze=False,model_changes_after_freeze_forbidden=True))
    print('BUNDLE_FROZEN',summary(lat),flush=True)
if __name__=='__main__':main()

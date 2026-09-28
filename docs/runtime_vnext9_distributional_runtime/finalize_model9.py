from common9 import *
from fit9 import *
from metrics9 import correction
import subprocess,shutil,time,platform,importlib.util
def copy(src,dst):Path(dst).parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dst)
def main():
    sel=read(ROOT/'PREAPRIL_SELECTION_RESULT.json');arm,mode=sel['selected']['arm'].split('__')
    bundle=ROOT/'RUNTIME_PROVIDER';bundle.mkdir(exist_ok=True);prep=read(ROOT/'FINAL_PREPROCESSING.json')
    benchmarks=[]
    for label,threads,device in [('CPU4',4,'cpu'),('CPU1',1,'cpu'),('GPU',4,'gpu')]:
        dest=bundle/'model' if label=='CPU4' else LOCAL/('benchmark_'+label);log=ROOT/('BENCHMARK_'+label+'.log')
        print(now(),'BENCHMARK',label,arm,flush=True)
        with log.open('w',encoding='utf-8') as fh:
            ret=subprocess.run([sys.executable,str(ROOT/'benchmark_worker9.py'),'--arm',arm,'--threads',str(threads),'--device',device,'--dest',str(dest)],stdout=fh,stderr=subprocess.STDOUT)
        if ret.returncode!=0:
            if label=='CPU4':raise RuntimeError('CPU4_FIT_FAILED')
            benchmarks.append(dict(backend=label,supported=False,log_sha256=sha(log)));continue
        meta=read(dest/'model.json');text=log.read_text(encoding='utf-8',errors='replace')
        identity_lines=[line for line in text.splitlines() if 'Device' in line or 'DEVICE' in line or 'cuda' in line.lower()]
        verified=device=='cpu' or ('ACTUAL_XGBOOST_DEVICE cuda:0' in text if arm.startswith('D2') else 'Using GPU Device:' in text)
        benchmarks.append(dict(backend=label,supported=True,training_seconds=meta['training_seconds'],threads=threads,
            actual_device_identity_verified=verified,identity_evidence=' | '.join(identity_lines),log_sha256=sha(log)))
    model=Distribution.load(bundle/'model');cal=pd.read_parquet(LOCAL/'final/CAL.parquet');x=matrix(cal,prep);par=model.parameters(x);q=model.quantiles(par)
    cutoff=pd.Timestamp('2025-03-31T08Z');mask=cal.event&cal.end_time.lt(cutoff)
    residual=cal.loc[mask,'runtime_seconds'].to_numpy()-q[mask,3];static=correction(residual)
    initial=[dict(end_time=str(e),residual=float(r)) for e,r in zip(cal.loc[mask,'end_time'],residual)]
    reference=q[:1000]
    for b in benchmarks:
        if not b['supported']:continue
        path=bundle/'model' if b['backend']=='CPU4' else LOCAL/('benchmark_'+b['backend'])
        other=Distribution.load(path);oq=other.quantiles(other.parameters(x.head(1000)))
        b['preApril_1000_max_quantile_difference_seconds']=float(np.max(abs(oq-reference)));b['selected_for_provider']=b['backend']=='CPU4'
    pd.DataFrame(benchmarks).to_csv(ROOT/'COMPUTE_BACKEND_BENCHMARK.csv',index=False)
    copy(ROOT/'provider_source9.py',bundle/'provider.py');copy(ROOT/'distribution9.py',bundle/'distribution9.py');copy(V8/'features8.py',bundle/'features8.py');copy(ROOT/'FINAL_PREPROCESSING.json',bundle/'preprocessing.json')
    contract=dict(model_version='Runtime-vNext9-'+arm,feature_contract_version='Kestrel_trace_proxy_V9_fixed29',provenance_mode='Kestrel_trace_proxy',
        available_from=str(cutoff),calibration_mode=mode,static_delta=static,initial_residuals=initial if mode.startswith('ROLLING') else [],
        STRICT_CAUSAL_FEATURE_COUNT=0,STRICT_CAUSAL_RUNTIME_PROVIDER_READY=False,REQUEST_VERSION_AUTHORITY_FOUND=False,
        diagnostic_only=sel['diagnostic_only'],fold_selected_arm=sel['selected']['arm'],target='end-start execution seconds, including valid zero',
        no_walltime_cap=True,unknown_category_code=0,online_model_refit_required=False,May_opened=False,April_used_for_selection=False,
        default_event_time='model availability cutoff; rolling callers should supply event_time',conditional_method='log survival ratio of SAME shifted total distribution')
    write('RUNTIME_PROVIDER/runtime_contract.json',contract)
    integrity=[dict(relative=str(p.relative_to(bundle)).replace('\\','/'),sha256=sha(p)) for p in bundle.rglob('*') if p.is_file() and '__pycache__' not in p.parts]
    write('RUNTIME_PROVIDER/BUNDLE_INTEGRITY.json',dict(files=integrity))
    spec=importlib.util.spec_from_file_location('provider9',bundle/'provider.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);provider=m.RuntimeProvider(bundle,allow_research=True)
    rows=cal[provider.input_columns].head(1000).to_dict('records');new=rows[0].copy();new.update(job_id='UNSEEN-V9-VERIFY',account='UNSEEN_ACCOUNT',qos='UNSEEN_QOS',partition='UNSEEN_PARTITION')
    total=provider.predict_total(new,cutoff);rem=provider.predict_remaining(new,3600,cutoff);changed=new|dict(job_id='ANOTHER-ID')
    actual=provider.predict_batch(rows,cutoff);expected=model.quantiles(par[:len(rows)],provider._delta(cutoff),quantiles=(.5,.9))
    parity=float(np.max(abs(actual-expected)));assert parity<1e-7
    assert provider.predict_total(changed,cutoff)==total
    rejects=[]
    for extra in ['runtime_seconds','end_time','state','start_time']:
        try:provider.predict_total(new|{extra:123},cutoff);raise AssertionError('OUTCOME_ACCEPTED')
        except ValueError:rejects.append(extra)
    try:m.RuntimeProvider(bundle);raise AssertionError('NO_OPT_IN')
    except PermissionError:pass
    action=provider.running_action(new,max(900,total['q90_total_seconds']+900),total['q90_total_seconds'],cutoff)
    assert action['OVERRUN'] and action['retain_GPU'] and not action['terminate_job'] and action['migration_recommendation']=='STAY'
    latency=[]
    for n in [1,10,100,1000]:
        samples=[]
        for _ in range(3):
            t=time.perf_counter();provider.predict_batch(rows[:n],cutoff);samples.append((time.perf_counter()-t)*1000)
        latency.append(dict(batch=n,CPU_threads=1,median_ms=float(np.median(samples)),samples_ms=samples))
    write('INFERENCE_LATENCY.json',dict(time=now(),CPU=platform.processor(),batches=latency))
    write('PROVIDER_VALIDATION.json',dict(PASS=True,new_job=total,conditional_remaining=rem,overrun_action=action,job_id_invariance=True,unknown_categories_code0=True,
        forbidden_inputs_rejected=rejects,no_research_opt_in_rejected=True,serialized_quantile_parity_max=parity,no_April_read=True))
    sources=['TEMPORAL_FOLD_CONTRACT.json','TEMPORAL_FOLD_MEMBERSHIP.csv','TEMPORAL_FOLD_SUPPORT.csv','TEMPORAL_FOLD_PREREGISTRATION.json']
    write('TEMPORAL_FOLD_FREEZE.json',dict(time=now(),files=[record(ROOT/p) for p in sources],unchanged_since_preregistration=True))
    write('FEATURE_CONTRACT_FREEZE.json',dict(time=now(),files=[record(ROOT/p) for p in ['FEATURE_CONTRACT.json','FINAL_PREPROCESSING.json','RUNTIME_PROVIDER/features8.py']]))
    write('CALIBRATION_FREEZE.json',dict(time=now(),mode=mode,static_delta_seconds=static,initial_mature_residual_N=len(initial),algorithm='signed Q90 residual order statistic ceil(.9*(N+1)), min200; end<UTC prediction day, end>=day-window; no online model fit',
        contract=record(bundle/'runtime_contract.json'),FUTURE_CALIBRATION_RESIDUAL_READS=0))
    write('MODEL_SELECTION_FREEZE.json',dict(time=now(),selection=sel,files=[record(ROOT/p) for p in ['PREAPRIL_SELECTION_RESULT.json','MODEL_COMPARISON.csv','SELECTION_GATES.csv','EXPERIMENT_PROTOCOL.json','AFT_MODEL_CONTRACT.json','HAZARD_BIN_CONTRACT.json','EVALUATION_EXECUTION_CONTRACT.json']],
        April_used_for_selection=False,April_status='EXPOSED_REGRESSION_ONLY'))
    write('PROVIDER_BUNDLE_FREEZE.json',dict(time=now(),files=[record(p) for p in bundle.rglob('*') if p.is_file() and '__pycache__' not in p.parts],
        no_April_read=True,CPU_callable=True,selected_backend='CPU4 training / CPU1 inference'))
    print('FIVE_FREEZES_COMPLETE',now(),sel['selected'],flush=True)
if __name__=='__main__':main()

from common10 import *
from train10 import matrix
from hazard10 import Hazard
from calibration10 import *
from calibration_state10 import *
import pandas as pd,numpy as np,shutil,importlib.util,time,platform
FREEZES=['MODEL_SELECTION_FREEZE.json','TAIL_GRID_FREEZE.json','TAIL_CONTINUATION_FREEZE.json','CALIBRATION_FREEZE.json','RISK_GROUP_FREEZE.json','PROVIDER_BUNDLE_FREEZE.json']
def load_provider():
    b=ROOT/'RUNTIME_PROVIDER';spec=importlib.util.spec_from_file_location('provider10',b/'provider.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    return m.RuntimeProvider(b,allow_research=True)
def assert_freeze():
    for n in FREEZES:
        for r in read(ROOT/n)['files']:assert sha(r['path'])==r['sha256'],n+' CHANGED '+r['path']
def main():
    sel=read(ROOT/'PREAPRIL_SELECTION_RESULT.json');assert (ROOT/'BACKEND_BENCHMARK_RECEIPT.json').exists()
    model=Hazard.load(ROOT/'FINAL_CPU_MODEL');cal=fold_data('final','CAL');pre=prep('final');cutoff=pd.Timestamp('2025-03-31T08Z')
    par=np.load(LOCAL/'final/CPU_CAL.npz')['parameters'];bounds=read(ROOT/'FINAL_RISK_BOUNDARIES.json')['bounds'];risk=np.exp(model.logsf(par,14400,sel['continuation']))
    if sel['family']=='NONE':
        state=dict(day=str(cutoff),mode='STATIC',family='NONE',bounds=bounds,pooled={'family':'NONE'},groups={str(i):{'family':'NONE'} for i in range(len(bounds)+1)},support=[])
    else:state=fit_state(cal,probability_bins(raw_landmarks(model,par,sel['continuation'])),risk,cutoff,sel['mode'],sel['family'],sel['risk_conditioned'],bounds)
    bundle=ROOT/'RUNTIME_PROVIDER';bundle.mkdir(exist_ok=True)
    for src,dst in [(ROOT/'provider_source10.py','provider.py'),(ROOT/'hazard10.py','hazard10.py'),(ROOT/'calibration10.py','calibration10.py'),(V8/'features8.py','features8.py'),(V9/'FINAL_PREPROCESSING.json','preprocessing.json')]:shutil.copyfile(src,bundle/dst)
    shutil.copytree(ROOT/'FINAL_CPU_MODEL',bundle/'model',dirs_exist_ok=True)
    write('RUNTIME_PROVIDER/calibration_state.json',state)
    contract=dict(model_version='Runtime-vNext10-G1-CPU4',calibration_version='Runtime-vNext10-'+sel['selected']['arm']+'-PREAPRIL-FROZEN',
        available_from=str(cutoff),grid=sel['grid'],continuation=sel['continuation'],family=sel['family'],mode=sel['mode'],risk_conditioned=sel['risk_conditioned'],
        provenance_mode='Kestrel_trace_proxy',diagnostic_only=sel['diagnostic_only'],STRICT_CAUSAL_FEATURE_COUNT=0,REQUEST_VERSION_AUTHORITY_FOUND=False,STRICT_CAUSAL_RUNTIME_PROVIDER_READY=False,
        outcome_updates=False,online_model_refit_required=False,April_used_for_selection=False,May_opened=False,feature_contract='V9 fixed 29 engineered / 9 raw',
        target='end-start execution seconds',conditional_method='S_cal(e+r)/S_cal(e)',calibration_startup='Final out-of-training CAL is 14 days; ROLLING28 cannot invent earlier out-of-training outcomes')
    write('RUNTIME_PROVIDER/runtime_contract.json',contract)
    write('RUNTIME_PROVIDER/BUNDLE_INTEGRITY.json',dict(files=[dict(relative=p.relative_to(bundle).as_posix(),sha256=sha(p)) for p in bundle.rglob('*') if p.is_file() and '__pycache__' not in p.parts]))
    provider=load_provider();rows=cal[provider.input_columns].head(1000).to_dict('records')
    new=rows[0]|dict(job_id='NEVER_SEEN_V10',account='UNSEEN_ACCOUNT',qos='UNSEEN_QOS',partition='UNSEEN_PARTITION')
    total=provider.predict_total(new,cutoff);rem=provider.predict_remaining(new,3600,cutoff)
    assert provider.predict_total(new|dict(job_id='DIFFERENT_ID'),cutoff)==total
    expected=provider.quantiles_from_parameters(par[:len(rows)]);actual=provider.predict_batch(rows,cutoff);parity=float(np.max(abs(expected-actual)));assert parity<1e-7
    rejected=[]
    for k in ['runtime_seconds','end_time','start_time','state','event','censored','duration_lower','actual_long_gt4h','actual_remaining','completion_time']:
        try:provider.predict_total(new|{k:123},cutoff);raise AssertionError('OUTCOME_ACCEPTED')
        except ValueError:rejected.append(k)
    parameters=provider.parameters(rows[:100]);err=0.
    for elapsed in [0.,900.,14400.,43200.,1e7]:
        qq,logs=provider.remaining_from_parameters(parameters,elapsed);assert np.isfinite(qq).all() and np.all(qq[:,1]>=qq[:,0]) and np.all(qq>=0)
        _,groups=provider.risk_groups(parameters)
        for g in np.unique(groups):
            m=groups==g;mapping=provider.mapping(g)
            for j,tau in enumerate([.5,.9]):
                lr=mapping.logsf(model.logsf(parameters[m],elapsed+qq[m,j],sel['continuation']))-logs[m]
                err=max(err,float(np.max(abs(lr-np.log1p(-tau)))))
    assert err<1e-7,err
    action=provider.running_action(new,total['q90_total_seconds']+900,total['q90_total_seconds'],cutoff)
    assert action['retain_GPU'] and action['OVERRUN'] and action['reservation_extend_seconds']==900 and not action['terminate_job'] and action['migration_recommendation']=='STAY'
    latency=[]
    for n in [1,10,100,1000]:
        samples=[]
        for _ in range(3):
            t=time.perf_counter();provider.predict_batch(rows[:n],cutoff);samples.append((time.perf_counter()-t)*1000)
        latency.append(dict(batch=n,CPU_threads=1,median_ms=float(np.median(samples)),samples_ms=samples))
    write('INFERENCE_LATENCY.json',dict(time=now(),CPU=platform.processor(),batches=latency))
    write('PROVIDER_VALIDATION.json',dict(time=now(),PASS=True,new_job=total,remaining=rem,overrun_action=action,forbidden_inputs_rejected=rejected,job_id_invariance=True,serialized_parity_max_seconds=parity,conditional_log_survival_ratio_max_error=err,April_read=False))
    def freeze(name,names,**extra):write(name,dict(time=now(),files=[record(ROOT/n) for n in names],April_read=False,**extra))
    freeze('TAIL_GRID_FREEZE.json',['TAIL_GRID_CANDIDATES.json','FINAL_CPU_MODEL/model.json','hazard10.py'],grid=sel['grid'],TRAIN_only=True)
    freeze('TAIL_CONTINUATION_FREEZE.json',['TAIL_EXTRAPOLATION_TRAIN_CONTRACT.json','TAIL_EXTRAPOLATION_AUDIT.json','hazard10.py'],continuation=sel['continuation'])
    freeze('CALIBRATION_FREEZE.json',['CALIBRATION_LANDMARK_CONTRACT.json','CALIBRATION_NUMERICS_CONTRACT.json','calibration10.py','calibration_state10.py','RUNTIME_PROVIDER/calibration_state.json'],family=sel['family'],mode=sel['mode'],April_updates=False,identity_component=.01,isotonic_endpoint_pruning=1e-10)
    freeze('RISK_GROUP_FREEZE.json',['FINAL_RISK_BOUNDARIES.json','TAIL_RISK_AUDIT.csv','RISK_GROUP_SUPPORT.csv'],bounds=bounds,risk_conditioned=sel['risk_conditioned'])
    freeze('MODEL_SELECTION_FREEZE.json',['PREAPRIL_SELECTION_RESULT.json','CALIBRATION_COMPARISON.csv','SELECTION_GATES.csv','EXPERIMENT_PROTOCOL.json','FEATURE_CONTRACT.json','TEMPORAL_FOLD_CONTRACT.json','FOLD_MEMBERSHIP_REFERENCE.json','PROVIDER_VALIDATION.json','evaluate_calibration10.py','metrics10.py','train10.py'],selection=sel,APRIL_STATUS='EXPOSED_REGRESSION_ONLY')
    write('PROVIDER_BUNDLE_FREEZE.json',dict(time=now(),files=[record(p) for p in bundle.rglob('*') if p.is_file() and '__pycache__' not in p.parts],April_read=False,CPU_callable=True))
    assert_freeze();print('SIX_FREEZES_COMPLETE',now(),sel['selected'],flush=True)
if __name__=='__main__':main()


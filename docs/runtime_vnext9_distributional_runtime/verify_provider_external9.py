"""Fresh-process, standalone bundle validation; no training-module import."""
from pathlib import Path
import sys,json,hashlib
import numpy as np
root=Path(__file__).resolve().parent;bundle=root/'RUNTIME_PROVIDER';sys.path.insert(0,str(bundle))
from provider import RuntimeProvider
p=RuntimeProvider(bundle,allow_research=True)
job=dict(job_id='NEW-NOT-IN-TRACE',num_gpus_req=4,num_nodes_req=1,num_cores_req=32,requested_memory_mib=262144,requested_seconds=14400,array_index=None,qos='UNKNOWN-QOS',partition='UNKNOWN-PARTITION',account='UNKNOWN-ACCOUNT')
event='2025-04-02T00:00:00Z';before=p.predict_total(job,event)
p.observe_completed(job|dict(submit_time='2025-04-01T00:00:00Z'),3600,'2025-04-03T00:00:00Z')
assert p.predict_total(job,event)==before,'FUTURE_OBSERVER_LEAK'
assert p.predict_total(job|dict(job_id='OTHER-NEW-ID'),event)==before
rejected=[]
for field in ['runtime_seconds','actual_end','end_time','state','event','censored','duration_lower','duration_upper','label_valid']:
    try:p.predict_total(job|{field:1},event);raise AssertionError(field)
    except ValueError:rejected.append(field)
for elapsed in [-1,float('nan'),float('inf')]:
    try:p.predict_remaining(job,elapsed,event);raise AssertionError('elapsed')
    except ValueError:pass
try:p.observe_completed(job|dict(submit_time='2024-01-01T00:00:00Z'),3600,'2025-04-04T00:00:00Z');raise AssertionError('TRAIN residual')
except ValueError:pass
errors=[]
for e in [0,1800,14400,86400,1e9]:
    r=p.predict_remaining(job,e,event);assert 0<=r['q50_remaining_seconds']<=r['q90_remaining_seconds'] and np.isfinite(r['q90_remaining_seconds'])
    par=p.parameters([job]);d=p._delta(p._time(event));ls=p.model.logsf(par,e-d)
    for tau,key in [(.5,'q50_remaining_seconds'),(.9,'q90_remaining_seconds')]:
        ratio=np.exp(p.model.logsf(par,e+r[key]-d)-ls)[0];errors.append(float(abs(ratio-(1-tau))))
assert max(errors)<1e-6
for f in json.loads((bundle/'BUNDLE_INTEGRITY.json').read_text())['files']:assert hashlib.sha256((bundle/f['relative']).read_bytes()).hexdigest()==f['sha256']
result=dict(PASS=True,fresh_process_bundle_only=True,unseen_job_callable=True,new_ID_invariance=True,unknown_category_support=True,
    future_observer_state_masked=True,in_training_residual_rejected=True,forbidden_inputs_rejected=rejected,invalid_elapsed_rejected=True,
    max_survival_ratio_error=max(errors),extreme_elapsed_seconds=1e9,no_model_refit=True,provider_bytes_unchanged=True)
(root/'STANDALONE_PROVIDER_VALIDATION.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print('STANDALONE_PROVIDER_PASS',result)

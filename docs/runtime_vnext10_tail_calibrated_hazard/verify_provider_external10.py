"""Bundle-only fresh-process test; never imports study or training modules."""
from pathlib import Path
import sys,json,hashlib
import numpy as np
root=Path(__file__).resolve().parent;bundle=root/'RUNTIME_PROVIDER';sys.path.insert(0,str(bundle))
from provider import RuntimeProvider
p=RuntimeProvider(bundle,allow_research=True)
job=dict(job_id='NEW-NOT-IN-TRACE',num_gpus_req=4,num_nodes_req=1,num_cores_req=32,requested_memory_mib=262144,requested_seconds=14400,array_index=None,qos='UNKNOWN-QOS',partition='UNKNOWN-PARTITION',account='UNKNOWN-ACCOUNT')
event='2025-04-02T00:00:00Z';before=p.predict_total(job,event)
assert p.predict_total(job|dict(job_id='OTHER-NEW-ID'),event)==before
assert p.predict_total(job,'2025-04-30T00:00:00Z')==before
assert not hasattr(p,'observe_completed')
try:RuntimeProvider(bundle);raise AssertionError('RESEARCH_OPT_IN')
except PermissionError:pass
rejected=[]
for field in ['runtime_seconds','actual_end','end_time','state','event','censored','duration_lower','duration_upper','label_valid','actual_long_gt4h']:
    try:p.predict_total(job|{field:1},event);raise AssertionError(field)
    except ValueError:rejected.append(field)
for elapsed in [-1,float('nan'),float('inf')]:
    try:p.predict_remaining(job,elapsed,event);raise AssertionError('elapsed')
    except ValueError:pass
for wrong in ['2025-01-01T00:00:00Z','2025-04-02T00:00:00']:
    try:p.predict_total(job,wrong);raise AssertionError('time')
    except ValueError:pass
try:p.predict_total(job|dict(submit_time='2025-04-03T00:00:00Z'),event);raise AssertionError('future submission')
except ValueError:pass
errors=[];par=p.parameters([job]);_,groups=p.risk_groups(par);mapping=p.mapping(groups[0])
for e in [0,1800,14400,86400,1e9]:
    r=p.predict_remaining(job,e,event);assert 0<=r['q50_remaining_seconds']<=r['q90_remaining_seconds'] and np.isfinite(r['q90_remaining_seconds'])
    ls=mapping.logsf(p.model.logsf(par,e,p.continuation))
    for tau,key in [(.5,'q50_remaining_seconds'),(.9,'q90_remaining_seconds')]:
        ratio=np.exp(mapping.logsf(p.model.logsf(par,e+r[key],p.continuation))-ls)[0];errors.append(float(abs(ratio-(1-tau))))
assert max(errors)<1e-6
for f in json.loads((bundle/'BUNDLE_INTEGRITY.json').read_text())['files']:assert hashlib.sha256((bundle/f['relative']).read_bytes()).hexdigest()==f['sha256']
result=dict(PASS=True,fresh_process_bundle_only=True,unseen_job_callable=True,new_ID_invariance=True,unknown_category_support=True,
    frozen_calendar_invariance=True,no_outcome_update_API=True,forbidden_inputs_rejected=rejected,invalid_elapsed_rejected=True,invalid_event_time_rejected=True,
    max_survival_ratio_error=max(errors),extreme_elapsed_seconds=1e9,no_model_refit=True,provider_bytes_unchanged=True,April_payload_read=False)
with (root/'STANDALONE_PROVIDER_VALIDATION.json').open('x',encoding='utf-8') as f:json.dump(result,f,indent=2)
print('STANDALONE_PROVIDER_PASS',result)


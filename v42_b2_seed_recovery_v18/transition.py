"""A new restart journal, sealed against stopped prior attempts and source SHA."""
from pathlib import Path
from copy import deepcopy
import argparse
from .common import read, atomic, record, digest, now, ROOT, sha, same_process
from .policy import VERSION, MANIFEST, source_files, MODEL_FIELDS


def prepare(root, *, code_commit):
    root = Path(root).resolve()
    if not (root/'HOLD_V13.json').exists() or (root/MANIFEST).exists():
        raise PermissionError('V18_STOPPED_PREVIOUS_AND_NEW_MANIFEST_REQUIRED')
    old = read(root/'CONTINUATION_V17_MANIFEST.json')
    cp = read(root/'CHECKPOINT_V17.json')
    may01=read(root/'dates/B2/2025-05-01/attempts/seed_policy_v17_01/RESULT.json')
    if cp.get('workers') or same_process(may01.get('worker',{})):
        raise PermissionError('V18_NEVER_INTERRUPT_OR_REDISPATCH_ACTIVE_V17_MAY01')
    if any(same_process(a['worker']) for a in read(root/'ACTIVES_V13.json')['workers'].values()):
        raise PermissionError('V18_PREVIOUS_NATIVE_WORKERS_STILL_RUNNING')
    priors, models = {}, {}
    for day in ('2025-05-01','2025-05-02','2025-05-03'):
        attempt = root/'dates/B2'/day/'attempts'/('seed_policy_v17_01' if day=='2025-05-01' else 'mess_build_v13_01')
        ledger = read(attempt/'NATIVE_RUNTIME_LEDGER.json'); result = read(attempt/'RESULT.json')
        if ledger['inflight'] is not None or any(c.get('runtime_unavailable') for c in ledger['calls']):
            raise PermissionError('V18_PREVIOUS_NATIVE_RUNTIME_QUARANTINE')
        priors[day] = dict(ledger=record(attempt/'NATIVE_RUNTIME_LEDGER.json'),
            result=record(attempt/'RESULT.json'),request=record(attempt/'request.json'),Native_Runtime=ledger['measured_Native_Runtime'])
        identity = read(attempt/'output/SCIENTIFIC_CASE_IDENTITY.json')
        models[day] = {k:identity[k] for k in MODEL_FIELDS}
    b1 = {k:record(v['result']) for k,v in cp['dates'].items() if v['arm']=='B1'}
    if len(b1)!=31 or any(v['status']!='PASS' for v in cp['dates'].values() if v['arm']=='B1'):
        raise PermissionError('V18_ALL_COMPLETED_B1_PRESERVATION_REQUIRED')
    sources = source_files()
    from v42_b2_start_recovery_v13.source_authority import original_sources
    doc = dict(schema=VERSION,run_id=old['run_id'],user_authorized=True,UTC=now(),
        source_commit=code_commit,previous_manifest=record(root/'CONTINUATION_V17_MANIFEST.json'),
        prior_checkpoint=record(root/'CHECKPOINT_V17.json'),inherited_B1_results=b1,
        input_folders=old['input_folders'],
        builder_original_sources=original_sources(root),prior_attempts=priors,model_identity=models,
        implementation=dict(version=old['implementation']['version'],sources=sources),
        execution_sources=sources,execution_SHA=digest(sources),seed_MIPGap=.03,seed_requested_seconds=900,
        native_budget_seconds=5400,target_gap=.03,Threads=1,P2_calls=0,
        canary_days=['2025-05-02','2025-05-03'],protected_May01_result=record(root/'dates/B2/2025-05-01/attempts/seed_policy_v17_01/RESULT.json'),
        resume_requires='VALID_INITIAL_FULL_UB_AND_EXACT_LB_AND_ADAPTIVE_ENTRY',
        stationary_dispatch_seed=True,stationary_dispatch_requested_seconds=120,
        historical_bound_point_reuse=False,date_native_runtime_reset=False)
    atomic(root/MANIFEST,doc)
    from .policy import verify_manifest
    verify_manifest(root/MANIFEST)
    dates = deepcopy(cp['dates'])
    for name,row in dates.items():
        if row['arm']=='B2' and row['day']!='2025-05-01':
            row.update(status='CANARY_PENDING' if row['day'] in doc['canary_days'] else 'HELD_FOR_CANARY',
                prior_attempt=priors.get(row['day']),current_attempt=None)
    atomic(root/'CHECKPOINT_V18.json',dict(schema=VERSION,run_id=doc['run_id'],state='CANARY_READY',
        dates=dates,prior_checkpoint=doc['prior_checkpoint'],UTC=now(),workers={}))
    return doc


if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('root');p.add_argument('--code-commit',required=True)
    a=p.parse_args();doc=prepare(a.root,code_commit=a.code_commit)
    print(doc['execution_SHA'])

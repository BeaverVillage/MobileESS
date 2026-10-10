"""Create a new production journal without changing prior results or clocks."""
from copy import deepcopy
from pathlib import Path
import argparse
from v42_b2_seed_recovery_v19.common import read, atomic, record, sha, digest, now, ROOT, same_process
from v42_b2_seed_recovery_v19.policy import VERSION, MANIFEST, source_files, verify_manifest, prior_runtime

DAYS = tuple(f'2025-05-{i:02d}' for i in range(1,32))

def prepare(root, commit):
    root=Path(root).resolve()
    if (root/'AUTONOMOUS_MANIFEST.json').exists() or (root/MANIFEST).exists():
        raise PermissionError('EXISTING_PRODUCTION_JOURNAL_NEVER_RESET')
    old=read(root/'CONTINUATION_V18_MANIFEST.json')
    previous=read(root/'CHECKPOINT_V18.json')
    if any(same_process(read(v['result']).get('worker',{})) for v in previous['dates'].values() if v.get('result')):
        raise PermissionError('PREVIOUS_WORKERS_STILL_ALIVE')
    b1={k:record(v['result']) for k,v in previous['dates'].items() if v['arm']=='B1'}
    if len(b1)!=31 or any(v['status']!='PASS' for v in previous['dates'].values() if v['arm']=='B1'):
        raise PermissionError('B1_31_PASS_REQUIRED')
    sources=source_files()
    # May02/03 remain terminal UNKNOWN quarantine; their budgets are not reset.
    priors={'2025-05-01':deepcopy(old['prior_attempts']['2025-05-01'])}
    prior_runtime(priors['2025-05-01'],root=root,day='2025-05-01')
    doc=dict(schema=VERSION,run_id=old['run_id'],user_authorized=True,UTC=now(),
        source_commit=commit,previous_manifest=record(root/'CONTINUATION_V18_MANIFEST.json'),
        inherited_B1_results=b1,builder_original_sources=old['builder_original_sources'],
        implementation=dict(version=old['implementation']['version'],sources=sources),
        execution_sources=sources,execution_SHA=digest(sources),seed_MIPGap=.03,seed_requested_seconds=300,
        native_budget_seconds=5400,target_gap=.03,Threads=1,P2_calls=0,prior_attempts=priors,
        input_folders=old['input_folders'],model_identity=old['model_identity'],
        canary_days=[],attempt_id='seed_policy_v19_01',initialization_native_limit_seconds=5400.,
        benchmark_initialization_only=False,campaign_runtime_reset=False,date_native_runtime_reset=False,
        historical_bound_point_reuse=False,preserved_quarantine=record(root/'QUARANTINE_V18_DATES.json'))
    atomic(root/MANIFEST,doc)
    verify_manifest(root/MANIFEST)
    dates={}
    for key,row in previous['dates'].items():
        dates[key]={k:deepcopy(row[k]) for k in ('arm','day','status','result','result_SHA','Native_Runtime','source_SHA') if k in row}
        if row['arm']=='B2' and row['day'] not in ('2025-05-02','2025-05-03'):
            dates[key].update(status='PENDING',attempt_count=0)
    for day in DAYS: dates['B3/'+day]=dict(arm='B3',day=day,status='PENDING',attempt_count=0)
    manifest=dict(schema='V42_AUTONOMOUS_V1',run_id=doc['run_id'],code_root=str(ROOT),
        campaign_root=str(root),source_commit=commit,UTC=now(),B2_workers=3,B3_workers=1,
        B2_manifest=record(root/MANIFEST),previous_checkpoint=record(root/'CHECKPOINT_V18.json'),
        B1_results=b1,B2_source_SHA=doc['execution_SHA'],B3_first_day='2025-05-01',
        B2_failures_do_not_block_B3=True,no_resource_limits_added=True)
    atomic(root/'AUTONOMOUS_MANIFEST.json',manifest)
    atomic(root/'SUPERVISOR_STATE.json',dict(schema='V42_AUTONOMOUS_V1',run_id=doc['run_id'],
        state='B2_RUNNING',dates=dates,workers={},parallel_workers=3,UTC=now(),transition_history=[]))
    return manifest

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root');p.add_argument('--commit',required=True)
    a=p.parse_args();print(prepare(a.root,a.commit)['B2_source_SHA'])

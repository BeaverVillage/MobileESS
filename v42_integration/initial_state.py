"""Issue-only initializer inputs and verified application to all four Arms."""
from datetime import datetime
from pathlib import Path
from .initialization import InitialRunningJob,initialize_running,load_initialization,replay_capacity
from .pr79_reference import CONTRACT,digest as episode_digest
from .m_engine import file_record


def prepare_initialization(folder, output, *, prior_verified_pins=None, source_assessment=None, budget=None):
    """Private realized service/completion and electrical outcomes are unread."""
    import json
    folder=Path(folder)
    names=('NATIVE_INPUT_TEMPLATE_B1.json','PLANNING_INPUT_BUNDLE.json')
    native,plan=[json.loads((folder/name).read_text(encoding='utf-8-sig')) for name in names]
    receipts=[file_record(folder/name) for name in names]
    issue=datetime.fromisoformat(plan['issue_time']).timestamp()
    observed={r['job_uid']:r for r in plan['known_population']}
    running=[r for r in native['known_population'] if r['state']=='RUNNING']
    fixed={r['job_uid']:r['current_site_if_running'] for r in running if r['current_site_if_running'] is not None}
    jobs=[]
    for row in running:
        uid=row['job_uid'];p=observed[uid]
        submit=datetime.fromisoformat(row['submit_time']).timestamp()
        start=issue-float(row['elapsed_seconds'])
        if p['elapsed_seconds']!=row['elapsed_seconds'] or p['GPU_gang']!=row['GPU_gang']:
            raise ValueError('INITIAL_ISSUE_OBSERVATION_SOURCE_DRIFT')
        episode=episode_digest(dict(contract=CONTRACT,uid=uid,submit=int(submit),attempt=None))
        jobs.append(InitialRunningJob(uid,episode,submit,start,int(row['GPU_gang']),
            tuple(p['compatible_sites']),receipts[0]['sha256'],receipts[1]['sha256'],
            gpu_type=p.get('gpu_type'),qos=row['cohort'].split('|')[0]))
    pins=prior_verified_pins or {}
    for value in pins.values():
        source=value['source_receipt']
        if not any(r['sha256']==source['sha256'] for r in receipts):receipts.append(source)
    return initialize_running(jobs,plan['capacities'],plan['rack_compatibility'],fixed,
        issue_seconds=issue,source_receipts=receipts,site_gpu_types=None,
        prior_verified_pins=pins,source_assessment=source_assessment or {},budget=budget,
        expected_counts=dict(running=254,fixed=210,unassigned=44,unassigned_GPU=59,total_GPU=468),output=output)


def verified_initial_sites(path, native, plan):
    policy=load_initialization(path)
    issue=datetime.fromisoformat(plan['issue_time']).timestamp()
    if policy['inputs']['issue_seconds']!=issue:raise ValueError('INITIALIZATION_ISSUE_CASE_DRIFT')
    original={r['job_uid']:r for r in native['known_population'] if r['state']=='RUNNING'}
    if set(policy['mapping'])!=set(original) or len(original)!=254:
        raise ValueError('INITIALIZATION_COMPLETE_RUNNING_POPULATION_REQUIRED')
    typed={r['uid']:r for r in policy['inputs']['jobs']}
    current={r['job_uid']:r for r in plan['known_population']}
    for uid,row in original.items():
        job=typed[uid]
        if (tuple(job['compatible_sites'])!=tuple(current[uid]['compatible_sites'])
                or job.get('gpu_type')!=current[uid].get('gpu_type')):
            raise ValueError('INITIALIZATION_CURRENT_COMPATIBILITY_CONTRACT_DRIFT')
        if (job['gpu']!=row['GPU_gang'] or job['known_start_seconds']!=issue-row['elapsed_seconds']
                or job['submit_seconds']!=datetime.fromisoformat(row['submit_time']).timestamp()):
            raise ValueError('INITIALIZATION_OBSERVED_JOB_EPISODE_DRIFT')
        if row['current_site_if_running'] is not None and policy['mapping'][uid]!=row['current_site_if_running']:
            raise ValueError('FROZEN_210_RUNNING_SITE_CHANGED')
    replay=replay_capacity([InitialRunningJob(**dict(r,compatible_sites=tuple(r['compatible_sites']))) for r in typed.values()],
        policy['mapping'],plan['capacities'],plan['rack_compatibility'],issue_seconds=issue)
    if not replay['PASS']:raise ValueError('INITIALIZATION_PHYSICAL_CAPACITY_NOT_VALIDATED')
    return policy

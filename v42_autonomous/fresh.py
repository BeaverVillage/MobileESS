"""Create a separately authorized campaign; never reset an existing journal."""
from copy import deepcopy
from pathlib import Path
import argparse
from v42_b2_seed_recovery_v19.common import read, atomic, record, sha, now, ROOT

DAYS = tuple(f'2025-05-{i:02d}' for i in range(1, 32))


def prepare(root, origin, deployment, code_root, commit):
    root, origin, code_root = map(lambda p: Path(p).resolve(), (root, origin, code_root))
    deployment = Path(deployment).resolve()
    if root.exists() and any(root.iterdir()):
        raise PermissionError('FRESH_CAMPAIGN_DESTINATION_MUST_BE_EMPTY')
    prior = read(deployment)
    b1 = deepcopy(prior['inherited_B1_results'])
    if set(b1) != {'B1/' + day for day in DAYS}:
        raise PermissionError('B1_ALL_31_REQUIRED')
    for receipt in b1.values():
        if record(receipt['path']) != receipt or read(receipt['path'])['status'] != 'PASS':
            raise PermissionError('B1_RESULT_AUTHORITY_DRIFT')
    for name, expected in prior['execution_sources'].items():
        if sha(code_root / name) != expected:
            raise PermissionError('IMMUTABLE_DEPLOYMENT_DRIFT:' + name)
    run_id = 'may2025_b2_b3_fresh_' + now().replace('-', '').replace(':', '').replace('.', '_')
    authorization = dict(schema='V42_EXPLICIT_FRESH_RESTART', UTC=now(),
        user_instruction='5월 B2 B3 캠페인 처음부터 다시 시작해야지.',
        new_campaign_root=str(root), prior_campaign_root=str(origin),
        prior_deployment=record(deployment),
        stop_receipt=record(origin / 'USER_FRESH_RESTART_STOP_RECEIPT.json'),
        prior_results_and_native_ledgers_preserved=True,
        prior_unknown_runtime_remains_unknown=True,
        fresh_B2_and_B3_dates=list(DAYS), prior_B2_and_B3_results_inherited=False)
    doc = deepcopy(prior)
    for key in ('previous_manifest', 'prior_attempts', 'preserved_quarantine'):
        doc.pop(key, None)
    doc.update(run_id=run_id, UTC=now(), source_commit=prior['source_commit'],
        prior_attempts={}, attempt_id='fresh_b2_v21_01', attempt_ids=['fresh_b2_v21_01'],
        user_authorized=True, fresh_campaign=True, inherited_B1_results=b1,
        new_campaign_native_budget_seconds=5400, seed_requested_seconds=300,
        target_gap=.03, P2_calls=0, Threads=1, initialization_native_limit_seconds=5400,
        canary_days=[], benchmark_initialization_only=False,
        campaign_runtime_reset=False, date_native_runtime_reset=False)
    root.mkdir(parents=True, exist_ok=True)
    atomic(root / 'USER_FRESH_RESTART_AUTHORIZATION.json', authorization)
    manifest_path = root / 'B2_FRESH_DEPLOYMENT_MANIFEST.json'
    atomic(manifest_path, doc)
    dates = {'B1/' + day: dict(arm='B1', day=day, status='PASS',
        result=b1['B1/' + day]['path'], result_SHA=b1['B1/' + day]['sha256'],
        Native_Runtime=read(b1['B1/' + day]['path']).get('Native_Runtime')) for day in DAYS}
    for arm in ('B2', 'B3'):
        for day in DAYS:
            dates[arm + '/' + day] = dict(arm=arm, day=day, status='PENDING', attempt_count=0)
    manifest = dict(schema='V42_AUTONOMOUS_V1', run_id=run_id,
        campaign_root=str(root), code_root=str(ROOT), source_commit=commit, UTC=now(),
        origin_campaign_root=str(origin), B1_campaign_root=str(origin), B1_results=b1,
        B2_workers=3, B3_workers=1, B2_manifest=record(manifest_path),
        B2_worker_module='v42_autonomous_b2.worker', B2_deployment_manifest=str(manifest_path),
        B2_code_root=str(code_root), B2_source_commit=prior['source_commit'],
        B2_source_SHA=doc['execution_SHA'], B3_first_day=DAYS[0],
        B2_failures_do_not_block_B3=True, no_resource_limits_added=True,
        fresh_restart_authorization=record(root / 'USER_FRESH_RESTART_AUTHORIZATION.json'))
    atomic(root / 'AUTONOMOUS_MANIFEST.json', manifest)
    atomic(root / 'SUPERVISOR_STATE.json', dict(schema='V42_AUTONOMOUS_V1',
        run_id=run_id, state='B2_RUNNING', dates=dates, workers={}, parallel_workers=3,
        UTC=now(), transition_history=[]))
    return manifest


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    for name in ('root', 'origin', 'deployment', 'code_root', 'commit'):
        p.add_argument(name)
    a = p.parse_args()
    print(prepare(a.root, a.origin, a.deployment, a.code_root, a.commit)['run_id'])

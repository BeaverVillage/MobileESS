"""New journal, preserving all prior successes, failure receipts and Native clocks."""
from copy import deepcopy
from pathlib import Path
import shutil
from .common import atomic, read, sha, now, same_process
from .policy import RETRY_DATES, ATTEMPT, VERSION


def save_checkpoint(root, checkpoint):
    root = Path(root)
    path = root / 'CHECKPOINT_V12.json'
    if path.is_file():
        previous = root / 'CHECKPOINT_V12_PREVIOUS.json'
        shutil.copyfile(path, previous)
        atomic(root / 'CHECKPOINT_V12_PREVIOUS_SHA.json', dict(sha256=sha(previous)))
    checkpoint['updated_UTC'] = now()
    atomic(path, checkpoint)


def initialize_checkpoint(root, manifest):
    from v42_b2_start_recovery_v11.coordinator import read_actives, TERMINAL
    root = Path(root).resolve()
    if sha(manifest['base_checkpoint']['path']) != manifest['base_checkpoint']['sha256']:
        raise PermissionError('V12_SOURCE_HANDOFF_CHECKPOINT_SHA_DRIFT')
    checkpoint = deepcopy(read(manifest['base_checkpoint']['path']))
    if any(same_process(a.get('worker', {})) for a in read_actives(root).values()):
        raise PermissionError('V12_RECOVERY_REQUIRES_NO_RUNNING_PREVIOUS_WORKER')
    if (RETRY_DATES or len(checkpoint['dates']) != 62
            or any(r['status'] != 'PASS' or r.get('attempts') != 1
                   for r in checkpoint['dates'].values() if r['arm'] == 'B1')
            or any(r['status'] != 'PENDING' or r.get('attempts', 0) != 0
                   for r in checkpoint['dates'].values() if r['arm'] == 'B2')):
        raise PermissionError('V12_REQUIRES_ALL_31_B1_PASS_AND_ALL_B2_UNSTARTED')
    # No date rows are reset, and no previous point, bound or clock is adopted.
    checkpoint.pop('inherited_result_verification', None)
    checkpoint.update(state='READY', version=VERSION, original_checkpoint=manifest['base_checkpoint'],
        authorized_recovery_dates=list(RETRY_DATES), last_error=None)
    atomic(root / 'ACTIVES_V12.json', dict(schema='V42_MAY_ACTIVE_WORKER_SLOTS_V2',
        run_id=manifest['run_id'], workers={}, updated_UTC=now()))
    save_checkpoint(root, checkpoint)
    return checkpoint


def validate_inherited_request(root, manifest, request):
    root = Path(root).resolve()
    name = request.get('arm', '') + '/' + request.get('day', '')
    row = read(manifest['base_checkpoint']['path'])['dates'].get(name, {})
    sealed = manifest.get('inherited_request_receipts', {}).get(name)
    if (not row.get('request') or not sealed
            or Path(row['request']).resolve() != Path(request['result']).parent / 'request.json'
            or row.get('status') != 'PASS' or row.get('attempts') != 1
            or request.get('arm') != 'B1'):
        raise PermissionError('V12_ONLY_EXACT_COMPLETED_INHERITED_B1_REQUEST_ALLOWED')
    from .common import record
    path = Path(row['request']).resolve()
    if record(path) != sealed or request != read(path):
        raise PermissionError('V12_IMMUTABLE_INHERITED_REQUEST_DRIFT')
    expected_input = Path(manifest['input_folders'][name]).resolve()
    old_manifest = Path(request['manifest']).resolve()
    if (request.get('run_id') != manifest['run_id'] or Path(request['root']).resolve() != root
            or Path(request['input_folder']).resolve() != expected_input
            or old_manifest.parent != root or request['manifest_SHA'] != sha(old_manifest)
            or request.get('Threads') != 1 or request.get('P2_calls') != 0
            or request.get('native_budget_seconds') != 5400
            or request.get('wall_budget_seconds') is not None or request.get('target_gap') != .005):
        raise PermissionError('V12_INHERITED_REQUEST_IDENTITY_OR_POLICY_DRIFT')
    # load_manifest verified the entire V10 scientific/source chain once.
    # This sealed completed-history path never authorizes a Native entry.
    # The coordinator still independently hashes every result artifact.
    return None

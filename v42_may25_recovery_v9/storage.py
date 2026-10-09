"""New journal, preserving all prior successes, failure receipts and Native clocks."""
from copy import deepcopy
from pathlib import Path
import shutil
from .common import atomic, read, sha, now, same_process
from .policy import RETRY_DATES, ATTEMPT, VERSION


def save_checkpoint(root, checkpoint):
    root = Path(root)
    path = root / 'CHECKPOINT_V9.json'
    if path.is_file():
        previous = root / 'CHECKPOINT_V9_PREVIOUS.json'
        shutil.copyfile(path, previous)
        atomic(root / 'CHECKPOINT_V9_PREVIOUS_SHA.json', dict(sha256=sha(previous)))
    checkpoint['updated_UTC'] = now()
    atomic(path, checkpoint)


def initialize_checkpoint(root, manifest):
    from v42_may_mess_build_v7.coordinator import read_actives, TERMINAL
    root = Path(root).resolve()
    if sha(manifest['base_checkpoint']['path']) != manifest['base_checkpoint']['sha256']:
        raise PermissionError('V9_SOURCE_HANDOFF_CHECKPOINT_SHA_DRIFT')
    checkpoint = deepcopy(read(manifest['base_checkpoint']['path']))
    if any(same_process(a.get('worker', {})) for a in read_actives(root).values()):
        raise PermissionError('V9_RECOVERY_REQUIRES_NO_RUNNING_PREVIOUS_WORKER')
    stop = read(manifest['may26_stop']['path'])
    if (len(stop['workers']) != 1 or stop['workers'][0]['day'] != '2025-05-26'
            or not stop['workers'][0]['worker_dead'] or same_process(stop['workers'][0]['worker'])):
        raise PermissionError('V9_MAY26_EXPLICIT_STOP_NOT_CONFIRMED')
    originals = {}
    for day in RETRY_DATES:
        name = 'B1/' + day
        row = checkpoint['dates'][name]
        allowed = TERMINAL | ({'RUNNING'} if day == '2025-05-26' else set())
        if row['status'] not in allowed or row['status'] == 'PASS' or row.get('attempts') != 1:
            raise PermissionError('V9_RECOVERY_ONLY_FOR_EXPLICIT_FAILED_OR_INTERRUPTED_DATE:' + name)
        if day == '2025-05-26':
            command = stop['workers'][0]['worker']['command']
            if Path(command[-1]).resolve() != Path(row['request']).resolve():
                raise PermissionError('V9_STOP_RECEIPT_REQUEST_DRIFT')
        originals[name] = deepcopy(row)
        checkpoint['dates'][name] = dict(arm='B1', day=day, status='PENDING', attempts=0,
            original_attempt=deepcopy(row), authorized_attempt_id=ATTEMPT)
    for row in checkpoint['dates'].values():
        for current in (row, row.get('original_attempt', {})):
            if 'summary' in current:
                current['summary'] = {k: v for k, v in current['summary'].items() if k != 'files'}
    atomic(root / 'ORIGINAL_FAILED_INTERRUPTED_ATTEMPTS_V9.json', dict(run_id=manifest['run_id'], dates=originals, UTC=now()))
    checkpoint.update(state='READY', version=VERSION, original_checkpoint=manifest['base_checkpoint'],
        authorized_recovery_dates=list(RETRY_DATES), last_error=None)
    atomic(root / 'ACTIVES_V9.json', dict(schema='V42_MAY_ACTIVE_WORKER_SLOTS_V2',
        run_id=manifest['run_id'], workers={}, updated_UTC=now()))
    save_checkpoint(root, checkpoint)
    return checkpoint


def validate_inherited_request(root, manifest, request):
    from v42_may_mess_build_v7.coordinator import validate_request as validate_previous
    root = Path(root).resolve()
    name = request.get('arm', '') + '/' + request.get('day', '')
    row = read(manifest['base_checkpoint']['path'])['dates'].get(name, {})
    if (name in {'B1/' + day for day in RETRY_DATES} or not row.get('request')
            or Path(row['request']).resolve() != Path(request['result']).parent / 'request.json'
            or row.get('status') == 'PENDING' or request.get('arm') != 'B1'):
        raise PermissionError('V9_ONLY_EXACT_COMPLETED_INHERITED_B1_REQUEST_ALLOWED')
    return validate_previous(root, read(root / 'CONTINUATION_V7R2_MANIFEST.json'), request)

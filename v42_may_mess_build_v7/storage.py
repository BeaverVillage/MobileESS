"""Copy the transition checkpoint without resetting any date or Native clock."""
from copy import deepcopy
from pathlib import Path
import shutil
from .common import atomic, read, sha, now


def save_checkpoint(root, checkpoint):
    root = Path(root)
    path = root / 'CHECKPOINT_V7.json'
    if path.is_file():
        previous = root / 'CHECKPOINT_V7_PREVIOUS.json'
        shutil.copyfile(path, previous)
        atomic(root / 'CHECKPOINT_V7_PREVIOUS_SHA.json', dict(sha256=sha(previous)))
    checkpoint['updated_UTC'] = now()
    atomic(path, checkpoint)


def initialize_checkpoint(root, manifest):
    from v42_may_build_v6.coordinator import read_actives
    root = Path(root).resolve()
    if sha(manifest['base_checkpoint']['path']) != manifest['base_checkpoint']['sha256']:
        raise PermissionError('V7_SOURCE_HANDOFF_CHECKPOINT_SHA_DRIFT')
    checkpoint = deepcopy(read(manifest['base_checkpoint']['path']))
    if any(a['arm'] != 'B1' for a in read_actives(root).values()):
        raise PermissionError('V7_HANDOFF_CANNOT_REPLACE_RUNNING_B2_WORKERS')
    checkpoint.update(state='READY', version=manifest['implementation']['version'],
                      original_checkpoint=manifest['base_checkpoint'], authorized_recovery_dates=[])
    for row in checkpoint['dates'].values():
        if 'summary' in row:
            row['summary'] = {k: v for k, v in row['summary'].items() if k != 'files'}
    atomic(root / 'ACTIVES_V7.json', dict(schema='V42_MAY_ACTIVE_WORKER_SLOTS_V2',
           run_id=manifest['run_id'], workers=read_actives(root), updated_UTC=now()))
    save_checkpoint(root, checkpoint)
    return checkpoint


def validate_inherited_request(root, manifest, request):
    from v42_may_build_v6.coordinator import validate_request as validate_previous
    root = Path(root).resolve()
    boundary = read(manifest['base_checkpoint']['path'])
    name = request.get('arm', '') + '/' + request.get('day', '')
    row = boundary['dates'].get(name, {})
    if (not row.get('request') or Path(row['request']).resolve() != Path(request['result']).parent / 'request.json'
            or row.get('status') == 'PENDING' or request.get('arm') != 'B1'):
        raise PermissionError('V7_ONLY_EXACT_STARTED_INHERITED_B1_REQUEST_ALLOWED')
    return validate_previous(root, read(root / 'CONTINUATION_V6_MANIFEST.json'), request)

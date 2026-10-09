"""V5 journal does not overwrite the original checkpoint or failed attempts."""
from copy import deepcopy
from pathlib import Path
import shutil
from .common import atomic, read, sha, now, record
from .policy import RETRY_DATES


def save_checkpoint(root, checkpoint):
    path=Path(root)/'CHECKPOINT_V5.json'
    if path.is_file():
        previous=Path(root)/'CHECKPOINT_V5_PREVIOUS.json'
        shutil.copyfile(path, previous)
        atomic(Path(root)/'CHECKPOINT_V5_PREVIOUS_SHA.json',dict(sha256=sha(previous)))
    checkpoint['updated_UTC']=now()
    atomic(path,checkpoint)


def initialize_checkpoint(root, manifest):
    from v42_may_campaign_native90.coordinator import TERMINAL, read_actives
    root=Path(root)
    checkpoint=deepcopy(read(manifest['base_checkpoint']['path']))
    if sha(manifest['base_checkpoint']['path']) != manifest['base_checkpoint']['sha256']:
        raise PermissionError('ORIGINAL_CHECKPOINT_BOUNDARY_SHA_DRIFT')
    originals={}
    for day in RETRY_DATES:
        name='B1/'+day;row=checkpoint['dates'][name]
        if row['status'] not in TERMINAL or row['status']=='PASS' or row.get('attempts')!=1:
            raise PermissionError('RECOVERY_ONLY_FOR_EXPLICIT_FAILED_DATE:'+name)
        originals[name]=deepcopy(row)
        checkpoint['dates'][name]=dict(arm='B1',day=day,status='PENDING',attempts=0,
            original_attempt=deepcopy(row),authorized_attempt_id='recovery_v5_01')
    # Terminal RESULT files remain the immutable authority. Thousands of
    # transitive file receipts need not be copied into each monitor response.
    for row in checkpoint['dates'].values():
        if 'summary' in row:
            row['summary']={k:v for k,v in row['summary'].items() if k!='files'}
        original=row.get('original_attempt')
        if original and 'summary' in original:
            original['summary']={k:v for k,v in original['summary'].items() if k!='files'}
    atomic(root/'ORIGINAL_FAILED_ATTEMPTS_V5.json',dict(run_id=manifest['run_id'],dates=originals,UTC=now()))
    checkpoint.update(state='READY',version=manifest['implementation']['version'],
        original_checkpoint=manifest['base_checkpoint'],authorized_recovery_dates=list(RETRY_DATES),last_error=None)
    persisted=read_actives(root)
    atomic(root/'ACTIVES_V5.json',dict(schema='V42_MAY_ACTIVE_WORKER_SLOTS_V2',run_id=manifest['run_id'],workers=persisted,updated_UTC=now()))
    save_checkpoint(root,checkpoint)
    return checkpoint


def validate_inherited_request(root, manifest, request):
    from v42_may_campaign_native90.coordinator import validate_request
    base=read(Path(root)/'CAMPAIGN_MANIFEST.json')
    cp=read(manifest['base_checkpoint']['path'])
    name=request.get('arm','')+'/'+request.get('day','')
    row=cp['dates'].get(name,{})
    if (name in {'B1/'+day for day in RETRY_DATES}
            or not row.get('request') or Path(row['request']).resolve()!=Path(request['result']).parent/'request.json'):
        raise PermissionError('V5_ONLY_EXACT_INHERITED_REQUEST_ALLOWED')
    return validate_request(root,base,request)

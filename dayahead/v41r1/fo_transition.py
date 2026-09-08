"""Preserve superseded attempts and adopt only explicitly accepted frozen bytes."""
from pathlib import Path
import shutil
from datetime import datetime,timezone
from dayahead.paper_analysis.storage import read,write_json
from dayahead.v41.preflight import ROOT,record
from dayahead.v41.data import RUNTIME
from dayahead.v41.reserve import require
from .fo_release import EVIDENCE,verify


def preserve_request():
    original=RUNTIME/'rev/bounded_compute_20260907T032537Z/PRESERVATION.json'
    request=Path('C:/Users/kjw39/.codex/attachments/c1e018fc-84f0-4029-b6d2-f007b8e67db6/pasted-text.txt')
    target=EVIDENCE/'USER_FULL_MAY_F_AND_O_REQUEST.txt'
    if not target.exists():shutil.copyfile(request,target)
    old=read(original)
    for attempt in old['attempts']:
        for ref in attempt['artifacts']:require(record(ref['path'])==ref,'OLD_ATTEMPT_BYTES_CHANGED')
    path=EVIDENCE/'SUPERSEDED_MONOLITHIC_ATTEMPTS.json'
    if not path.exists():write_json(path,dict(status='PRESERVED',classification='SUPERSEDED_BY_FIX_AND_OPTIMIZE_COMPUTE_STRATEGY',
        original_preservation=record(original),request=record(target),attempts=old['attempts'],
        original_classification_receipt_preserved=True,completed_B0_count=len(old['completed']),scientific_failure=False))


def transition():
    from dayahead.v41.scientific_archive import copy_atomic,verify_manifest
    from .campaign_run import verify_phase,provision_unit_storage
    from dayahead.v41 import campaign
    release=verify();state_path=RUNTIME/'campaign_state.json';state=read(state_path)
    require(state['status'].startswith(('PAUSED','READY')),'TRANSITION_REQUIRES_STOPPED_CAMPAIGN')
    archive=RUNTIME/'rev/fix_and_optimize'/release['scientific_commit'];archive.mkdir(parents=True,exist_ok=True)
    if not (archive/'STATE_BEFORE.json').exists():write_json(archive/'STATE_BEFORE.json',state)
    source=Path(release['acceptance_unit']);target=provision_unit_storage('2025-05-04','B1')
    for phase in ('dayahead','actual'):verify_phase(source/phase/(phase.upper()+'_RECEIPT.json'),release)
    verify_manifest(source/'UNIT_SCIENTIFIC_MANIFEST.json')
    if not (target/'actual/ACTUAL_RECEIPT.json').exists():
        for path in sorted(source.rglob('*')):
            if path.is_file():
                destination=target/path.relative_to(source)
                require(not destination.exists() or record(destination)['sha256']==record(path)['sha256'],'ACCEPTANCE_ADOPTION_WOULD_OVERWRITE_DIFFERENT_BYTES')
                copy_atomic(path,destination)
    for phase in ('dayahead','actual'):verify_phase(target/phase/(phase.upper()+'_RECEIPT.json'),release)
    unit=dict(status='COMPLETE',day='2025-05-04',policy='B1',scientific_commit=release['scientific_commit'],
        dayahead=record(target/'dayahead/DAYAHEAD_RECEIPT.json'),actual=record(target/'actual/ACTUAL_RECEIPT.json'),
        scientific_manifest=record(target/'UNIT_SCIENTIFIC_MANIFEST.json'),completed_at=datetime.now(timezone.utc).isoformat(),
        exact_acceptance_reuse=release['acceptance'],original_phase_commits_and_hashes_preserved=True)
    if not (target/'UNIT_RECEIPT.json').exists():write_json(target/'UNIT_RECEIPT.json',unit)
    row=state['units']['2025-05-04/B1'];row.update(status='COMPLETE',phase=None,worker_pid=None,
        dayahead_receipt=unit['dayahead'],actual_receipt=unit['actual'],unit_receipt=record(target/'UNIT_RECEIPT.json'))
    for row in state['units'].values():
        for key in ('dayahead_receipt','actual_receipt'):
            if row.get(key):verify_phase(row[key]['path'],release)
        if row['status']!='COMPLETE':row.update(status='PENDING',worker_pid=None,phase=None)
    state.update(scientific_commit=release['scientific_commit'],status='READY_AFTER_FIX_AND_OPTIMIZE_ACCEPTANCE',pid=None,
        prior_scientific_commit=state['scientific_commit'],compute_release=record(RUNTIME/'FULL_MAY_FROZEN_RELEASE.json'))
    write_json(state_path,state)
    for name in ('campaign_progress.json','campaign_heartbeat.json'):
        path=RUNTIME/name;value=read(path);value.update(status=state['status'],scientific_commit=state['scientific_commit'],
            timestamp=datetime.now(timezone.utc).isoformat(),completed_policy_days=sum(r['status']=='COMPLETE' for r in state['units'].values()))
        write_json(path,value)
    stop=RUNTIME/'STOP_REQUESTED.json'
    if stop.exists():
        copy_atomic(stop,archive/'STOP_REQUEST_RESOLVED.json');stop.unlink()
    write_json(archive/'TRANSITION.json',dict(status='PASS',state=record(state_path),release=record(RUNTIME/'FULL_MAY_FROZEN_RELEASE.json'),
        completed_B0_preserved=4,May04_B1_acceptance_adopted=True,parallel_days=4,threads_per_day=4))


if __name__=='__main__':
    import sys
    preserve_request() if sys.argv[1]=='preserve' else transition()

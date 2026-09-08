"""Evidence-bound recovery from a transient Windows campaign-state writer lock."""
from datetime import datetime, timezone
from pathlib import Path
import shutil
import time

import psutil

from dayahead.paper_analysis.storage import read
from dayahead.v39l.infrastructure import durable_atomic_json as write_json
from dayahead.v41.data import RUNTIME
from dayahead.v41.execution import science
from dayahead.v41.preflight import ROOT, OUT, record
from dayahead.v41.reserve import require


REVISION = RUNTIME / 'rev/runtime_write_lock_20260907'
AUTHORITY = OUT / 'RUNTIME_WRITE_LOCK_REPAIR_AUTHORITY.json'
OOM_AUTHORITY = OUT / 'HOST_OOM_NODEFILE_SPILL_RECOVERY.json'
SPILL_ROOT = Path('D:/MobileESS_v41r1_nodefiles')


def now():
    return datetime.now(timezone.utc).isoformat()


def _matching_processes(token):
    rows = []
    for process in psutil.process_iter(['pid', 'cmdline']):
        command = process.info['cmdline'] or []
        if token in command:
            rows.append(dict(pid=process.pid, command=command))
    return rows


def preserve():
    """Freeze failure evidence while already-running B1 phases finish independently."""
    require(not _matching_processes('dayahead.v41r1.campaign_run'), 'CAMPAIGN_MANAGER_STILL_RUNNING')
    state_path = RUNTIME / 'campaign_state.json'
    state = read(state_path)
    require(state['status'] == 'RUNNING', 'UNEXPECTED_PRE_RECOVERY_STATE')
    supervisor_log = ROOT / 'logs/v41r1_migration/full_may_supervisor.log'
    text = supervisor_log.read_text(encoding='utf-8', errors='replace')
    require('Exception in thread Thread-1 (heartbeat)' in text and
            "PermissionError: [WinError 5]" in text and
            "campaign_state.json" in text, 'WRITE_LOCK_FAILURE_NOT_PROVEN')
    workers = _matching_processes('dayahead.v41.execution')
    require(len(workers) == 4 and all(any(value in row['command'] for value in ('2025-05-01', '2025-05-02',
        '2025-05-03', '2025-05-04')) for row in workers), 'UNEXPECTED_SURVIVING_WORKER')
    REVISION.mkdir(parents=True, exist_ok=True)
    write_json(REVISION / 'CAMPAIGN_STATE_AT_FAILURE.json', state)
    prior_release = read(RUNTIME / 'FULL_MAY_FROZEN_RELEASE.json')
    write_json(REVISION / 'FROZEN_RELEASE_AT_FAILURE.json', prior_release)
    failure = dict(status='CONFIRMED_NON_SCIENTIFIC_RUNTIME_DEFECT', detected_at=now(),
        defect='Transient Windows reader lock caused os.replace PermissionError and terminated only the heartbeat thread',
        scientific_source_before=prior_release['science'], scientific_source_now=science(),
        scientific_source_unchanged=prior_release['science'] == science(),
        manager_stopped=True, surviving_phase_workers=workers,
        supervisor_log=record(supervisor_log), stop_request=record(RUNTIME / 'STOP_REQUESTED.json'),
        recovery='Install the previously tested durable_atomic_json retry writer in manager and watchdog; '
                 'adopt only recursively verified completed B1 DayAhead receipts')
    require(failure['scientific_source_unchanged'], 'SCIENTIFIC_SOURCE_CHANGED_DURING_RUNTIME_REPAIR')
    write_json(REVISION / 'FAILURE_EVIDENCE.json', failure)
    write_json(AUTHORITY, failure)
    state.update(status='PAUSED_FOR_RUNTIME_WRITE_LOCK_REPAIR', pid=None, updated_at=now(),
        runtime_failure=record(REVISION / 'FAILURE_EVIDENCE.json'))
    write_json(state_path, state)
    print('RUNTIME_WRITE_LOCK_PRESERVED', len(workers), flush=True)


def preserve_oom():
    """Preserve the four incomplete B1 attempts and attest the D-drive spill repair."""
    require(not _matching_processes('dayahead.v41r1.campaign_run'), 'CAMPAIGN_MANAGER_STILL_RUNNING')
    require(not _matching_processes('dayahead.v41.execution'), 'PHASE_WORKER_STILL_RUNNING')
    state_path = RUNTIME / 'campaign_state.json'
    state = read(state_path)
    require(state['status'] == 'PAUSED_FOR_RUNTIME_WRITE_LOCK_REPAIR', 'RUNTIME_REPAIR_STATE_NOT_PAUSED')
    oom_log = ROOT / 'logs/v41r1_migration/full_may/2025-05-03/B1/dayahead.log'
    text = oom_log.read_text(encoding='utf-8', errors='replace')
    require('gurobipy._exception.GurobiError: Out of memory' in text, 'HOST_OOM_NOT_PROVEN')
    archives = []
    links = []
    for day_number in range(1, 32):
        day = f'2025-05-{day_number:02}'
        for policy in ('B1', 'B3'):
            link = RUNTIME / day / policy / 'dayahead/optimization/solver_passes/gurobi_nodefiles'
            target = SPILL_ROOT / day / policy
            require(link.is_dir() and link.resolve() == target.resolve(), 'NODEFILE_SPILL_JUNCTION_INVALID')
            links.append(dict(day=day, policy=policy, link=str(link), target=str(target)))
        if day_number <= 4:
            archive = RUNTIME / 'interrupted' / (day + '_B1_dayahead_host_oom_20260907_1041')
            require(archive.is_dir() and not (archive / 'DAYAHEAD_RECEIPT.json').exists(),
                    'OOM_ARCHIVE_NOT_INCOMPLETE')
            archives.append(dict(day=day, policy='B1', archive=str(archive)))
            row = state['units'][day + '/B1']
            row.update(status='PENDING', phase=None, worker_pid=None,
                superseded_runtime_attempt=dict(classification='HOST_OOM_DURING_REGISTERED_3PCT_SEARCH',
                    archive=str(archive), scientific_result=False, reusable=False,
                    recovery='RERUN_FROM_DAYAHEAD_WITH_D_DRIVE_NODEFILE_JUNCTION'))
            row.pop('dayahead_receipt', None)
            row.pop('actual_receipt', None)
    value = dict(status='PASS', classification='NON_SCIENTIFIC_HOST_RESOURCE_FAILURE', detected_at=now(),
        failure='GurobiError: Out of memory during May 3 B1 P2 registered 3% search',
        scientific_source_unchanged=read(REVISION / 'FROZEN_RELEASE_AT_FAILURE.json')['science'] == science(),
        stopped_all_surviving_phase_workers=True, incomplete_attempts_preserved=archives,
        nodefile_start_GB=.5, spill_root=str(SPILL_ROOT), spill_drive='D: local NVMe SSD',
        spill_free_bytes=shutil.disk_usage(SPILL_ROOT).free, junctions=links,
        mathematical_model='UNCHANGED', physical_constraints='UNCHANGED', objectives='UNCHANGED',
        registered_B1_B3_gap='UNCHANGED_AT_3PCT', parallel_day_workers=4, solver_threads_per_day=4,
        oom_log=record(oom_log))
    require(value['scientific_source_unchanged'], 'SCIENTIFIC_SOURCE_CHANGED_DURING_OOM_REPAIR')
    write_json(REVISION / 'HOST_OOM_EVIDENCE.json', value)
    write_json(OOM_AUTHORITY, value)
    state.update(updated_at=now(), host_oom_recovery=record(REVISION / 'HOST_OOM_EVIDENCE.json'))
    write_json(state_path, state)
    print('HOST_OOM_PRESERVED_AND_D_SPILL_ATTESTED', len(archives), len(links), flush=True)


def transition():
    """Adopt verified completed phases and bind the paused state to the repaired release."""
    require(not _matching_processes('dayahead.v41r1.campaign_run'), 'CAMPAIGN_MANAGER_STILL_RUNNING')
    require(not _matching_processes('dayahead.v41.execution'), 'PHASE_WORKER_STILL_RUNNING')
    from .campaign_prepare import verify_release
    from .campaign_run import verify_phase
    frozen = verify_release()
    require(read(AUTHORITY)['scientific_source_unchanged'], 'RUNTIME_REPAIR_AUTHORITY_FAILED')
    state_path = RUNTIME / 'campaign_state.json'
    state = read(state_path)
    require(state['status'] == 'PAUSED_FOR_RUNTIME_WRITE_LOCK_REPAIR', 'RUNTIME_REPAIR_STATE_NOT_PAUSED')
    adopted = []
    for row in state['units'].values():
        if row['status'] == 'COMPLETE':
            for phase in ('dayahead', 'actual'):
                verify_phase(row[phase + '_receipt']['path'], frozen)
            continue
        if row['status'] not in ('DAYAHEAD_RUNNING', 'ACTUAL_RUNNING'):
            continue
        phase = row['phase']
        receipt_path = RUNTIME / row['day'] / row['policy'] / phase / (phase.upper() + '_RECEIPT.json')
        verify_phase(receipt_path, frozen)
        row[phase + '_receipt'] = record(receipt_path)
        row.update(status='DAYAHEAD_DONE' if phase == 'dayahead' else 'ACTUAL_DONE', worker_pid=None,
            runtime_recovery='REUSED_COMPLETE_PHASE_AFTER_RECURSIVE_READBACK')
        adopted.append(dict(day=row['day'], policy=row['policy'], phase=phase, receipt=record(receipt_path)))
    if adopted:
        require(len(adopted) == 4 and all(row['policy'] == 'B1' and row['phase'] == 'dayahead' for row in adopted),
                'UNEXPECTED_RUNTIME_RECOVERY_ADOPTION_SET')
    else:
        oom = read(OOM_AUTHORITY)
        require(oom['status'] == 'PASS' and oom['scientific_source_unchanged'] and
                len(oom['incomplete_attempts_preserved']) == 4 and len(oom['junctions']) == 62,
                'HOST_OOM_RECOVERY_NOT_ATTESTED')
    previous_errors = state.pop('errors', [])
    state.update(scientific_commit=frozen['scientific_commit'], status='READY_AFTER_RUNTIME_WRITE_LOCK_REPAIR',
        pid=None, errors=[], updated_at=now(), runtime_recovery_adopted=adopted,
        superseded_errors=previous_errors, repaired_release=record(RUNTIME / 'FULL_MAY_FROZEN_RELEASE.json'))
    stop = RUNTIME / 'STOP_REQUESTED.json'
    stop_value = read(stop)
    stop_value.update(cleared_at=now(), cleared_by='VERIFIED_RUNTIME_WRITE_LOCK_REPAIR_TRANSITION')
    write_json(REVISION / 'STOP_REQUESTED_DURING_FAILURE.json', stop_value)
    stop.unlink()
    write_json(REVISION / 'CAMPAIGN_STATE_AFTER_REPAIR.json', state)
    write_json(state_path, state)
    print('RUNTIME_WRITE_LOCK_TRANSITION_PASS', frozen['scientific_commit'], len(adopted), flush=True)


if __name__ == '__main__':
    import sys
    {'preserve': preserve, 'preserve_oom': preserve_oom, 'transition': transition}[sys.argv[1]]()

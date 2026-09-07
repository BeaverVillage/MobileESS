"""Preserve the user's superseded compute attempts before a solver revision."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import psutil
from dayahead.v39l.infrastructure import durable_atomic_json as write_json
from dayahead.v41.data import RUNTIME
from dayahead.v41.preflight import ROOT, record

CLASSIFICATION = 'SUPERSEDED_BY_BOUNDED_COMPUTE_SOLVE_STRATEGY'


def preserve():
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out = RUNTIME / 'rev' / ('bounded_compute_' + stamp)
    out.mkdir(parents=True, exist_ok=False)
    state_path = RUNTIME / 'campaign_state.json'
    state = json.loads(state_path.read_text(encoding='utf-8'))
    write_json(out / 'CAMPAIGN_STATE_BEFORE.json', state)
    request = Path('C:/Users/kjw39/.codex/attachments/baf8460b-8a5c-42a0-af03-dcf18f717183/pasted-text.txt')
    shutil.copyfile(request, out / 'USER_REQUEST.txt')
    write_json(RUNTIME / 'STOP_REQUESTED.json', dict(requested_at=stamp, mode=CLASSIFICATION,
        requested_by='EXPLICIT_USER_BOUNDED_COMPUTE_REVISION', preservation=str(out)))
    workers = []
    managers = []
    for p in psutil.process_iter(['pid', 'cmdline']):
        cmd = p.info['cmdline'] or []
        if ('dayahead.v41r1.campaign_run' in cmd or 'dayahead.v41.execution' in cmd) and Path(p.cwd()).resolve() == ROOT.resolve():
            (managers if 'dayahead.v41r1.campaign_run' in cmd else workers).append(p)
    write_json(out / 'STOPPED_PROCESSES.json', [dict(pid=p.pid, command=p.cmdline()) for p in managers + workers])
    # Stop dispatch before phase workers so no next day can be started.
    for group in (managers, workers):
        for p in group:
            p.terminate()
        _, alive = psutil.wait_procs(group, timeout=15)
        if alive:
            raise RuntimeError('USER_REVISION_PROCESS_STOP_INCOMPLETE')
    attempts = []
    completed = []
    for row in state['units'].values():
        if row['status'] == 'COMPLETE':
            completed.append(dict(day=row['day'], policy=row['policy'], receipts={k:v for k,v in row.items() if k.endswith('_receipt')}))
            continue
        if row['status'] not in ('DAYAHEAD_RUNNING', 'ACTUAL_RUNNING', 'FAILED'):
            continue
        phase = row.get('phase') or 'dayahead'
        folder = RUNTIME / row['day'] / row['policy'] / phase
        if (folder / (phase.upper() + '_RECEIPT.json')).exists():
            # A worker that completed before termination retains its original path.
            continue
        destination = RUNTIME / 'interrupted' / (row['day'] + '_' + row['policy'] + '_' + stamp + '_bounded')
        folder.resolve().relative_to(RUNTIME.resolve())
        destination.resolve().relative_to(RUNTIME.resolve())
        if folder.exists():
            destination.parent.mkdir(parents=True, exist_ok=True)
            folder.rename(destination)
        log = Path(row['log']) if row.get('log') else None
        refs = []
        for name in ('A0/SOLVER.log', 'A0/SOLVER_STAGES.json', 'A0/PRIMARY_MODEL.mps.gz', 'DAYAHEAD_STARTED.json'):
            if (destination / name).is_file():
                refs.append(record(destination / name))
        if log and log.is_file():
            copied = out / (row['day'] + '_' + row['policy'] + '_' + phase + '.log')
            shutil.copyfile(log, copied)
            refs.append(record(copied))
        attempt = dict(day=row['day'], policy=row['policy'], classification=CLASSIFICATION,
            scientific_failure=False, artifacts=refs, preserved_directory=str(destination),
            unsaved_in_memory_search_tree_reusable=False)
        attempts.append(attempt)
        row.update(status='PENDING', worker_pid=None, phase=None, superseded_compute_attempt=attempt)
        row.pop('error', None)
    state.update(status='PAUSED_FOR_BOUNDED_COMPUTE_REVISION', pid=None, updated_at=stamp)
    write_json(state_path, state)
    for name in ('campaign_progress.json', 'campaign_heartbeat.json'):
        path = RUNTIME / name
        if path.exists():
            value = json.loads(path.read_text(encoding='utf-8'))
            write_json(out / ('BEFORE_' + name), value)
            value.pop('STATUS',None)
            value.update(status=state['status'], timestamp=datetime.now(timezone.utc).isoformat())
            write_json(path, value)
    value = dict(status='PRESERVED', classification=CLASSIFICATION, completed=completed,
        attempts=attempts, historical_memory_failure_attempts='PRESERVED_UNMODIFIED_IN_INTERRUPTED',
        request=record(out/'USER_REQUEST.txt'), parallel_days=4, threads_per_day=4)
    write_json(out / 'PRESERVATION.json', value)
    print(json.dumps(dict(preservation=str(out), completed=len(completed), attempts=len(attempts))))


if __name__ == '__main__':
    preserve()

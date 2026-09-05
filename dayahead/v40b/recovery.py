"""Resume certified dates and adopt live workers after an infrastructure repair."""
import ast
from contextlib import contextmanager
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import uuid

from .common import CASES, DAYS, REPO, ROOT, read, write, sha, now_utc
from .supervision import inventory, reject_duplicates, verify_freeze, TOKENS
from dayahead.v39l.infrastructure import current_process_identity, identity_matches, write_exclusive_json

REPAIR = ROOT / 'repairs/02_windows_baseline_path'
SHORT_PASS = 'V40B'
OLD_PASS = 'MAY_2025_V40A_BASELINES'


def completed_case(day, case, method_sha):
    path = ROOT / 'days' / day / case / 'CASE_CERTIFICATE.json'
    if not path.exists():
        return None
    cert = read(path)
    if (cert.get('status'), cert.get('day'), cert.get('case')) != ('PASS', day, case):
        raise RuntimeError('INVALID_COMPLETED_CASE:' + day + ':' + case)
    if case == 'B3':
        if cert.get('method_SHA') != method_sha or cert.get('full_route_search_passes') != 1 or cert.get('second_route_search') != 0:
            raise RuntimeError('COMPLETED_B3_METHOD_MISMATCH')
        for name, expected in cert['files'].items():
            if sha(path.parent / name) != expected:
                raise RuntimeError('COMPLETED_B3_FILE_DRIFT:' + name)
    else:
        from .reuse import validate_case_files
        if sha(Path(cert['checkpoint'])) != cert['checkpoint_SHA']:
            raise RuntimeError('COMPLETED_BASELINE_CHECKPOINT_DRIFT')
        validate_case_files(day, case, Path(cert['checkpoint']), Path(cert['case_root']))
    return {'status': 'COMPLETE_NEW_V40A', 'certificate': str(path), 'certificate_SHA': sha(path)}


def certified_day(day, method_sha):
    path = ROOT / 'days' / day / 'DAY_CERTIFICATE.json'
    if not path.exists():
        return None
    cert = read(path)
    if cert.get('status') != 'PASS' or cert.get('day') != day or cert.get('method_SHA') != method_sha or set(cert.get('cases', {})) != set(CASES):
        raise RuntimeError('INVALID_DAY_CERTIFICATE:' + day)
    for case, item in cert['cases'].items():
        expected = 'COMPLETE_NEW_V40A' if case == 'B3' else None
        if item['status'] not in ('REUSE_CERTIFIED', 'COMPLETE_NEW_V40A') or (expected and item['status'] != expected):
            raise RuntimeError('INVALID_DAY_CASE_STATUS:' + day + ':' + case)
        if sha(Path(item['certificate'])) != item['certificate_SHA']:
            raise RuntimeError('DAY_CASE_CERTIFICATE_DRIFT:' + day + ':' + case)
        child = read(Path(item['certificate']))
        if (child.get('status'), child.get('day'), child.get('case')) != ('PASS', day, case):
            raise RuntimeError('DAY_CASE_IDENTITY:' + day + ':' + case)
        if case == 'B3' and child.get('method_SHA') != method_sha:
            raise RuntimeError('DAY_B3_METHOD_DRIFT:' + day)
    return cert


def is_path_failure(failure):
    if 'FileNotFoundError' not in failure.get('error', ''):
        return False
    trace = failure.get('traceback', '')
    try:
        path = ast.literal_eval(trace.splitlines()[-1].split('directory: ', 1)[1])
    except (ValueError, SyntaxError, IndexError):
        return False
    return len(path) >= 260 and OLD_PASS in path and 'RESTRICTED_VALUES.csv.tmp' in path and 'run_missing' in trace


def extended_path(path):
    path = Path(path).absolute()
    return Path('\\\\?\\' + str(path)) if os.name == 'nt' and not str(path).startswith('\\\\?\\') else path


def copy_baseline_cache(day):
    """Copy only this stopped day's beam prefix; preserve bytes and full SHA keys."""
    cache = REPO / 'dayahead/cache/v37_may_locked_final'
    rows = []
    for source in sorted((cache / OLD_PASS / 'beam').glob('*/' + day + '/B2')):
        target = cache / SHORT_PASS / 'beam' / source.relative_to(cache / OLD_PASS / 'beam')
        for src in extended_path(source).rglob('*'):
            if not src.is_file():
                continue
            dst = target / src.relative_to(extended_path(source))
            expected = sha(src)
            if dst.exists():
                if sha(dst) != expected:
                    raise RuntimeError('CACHE_COPY_COLLISION:' + str(dst))
            else:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(src, dst)
            if sha(dst) != expected:
                raise RuntimeError('CACHE_COPY_HASH_MISMATCH')
            rows.append({'source': str(src), 'target': str(dst), 'sha256': expected})
    write(REPAIR / 'cache_copy' / (day + '.json'), {'status': 'PASS', 'day': day, 'files': rows})
    return rows


def prepare_retry(day):
    failure = ROOT / 'days' / day / 'FAILURE.json'
    if not failure.exists() or not is_path_failure(read(failure)):
        return False
    archive = REPAIR / 'failed_attempts' / day
    if archive.exists():
        return False
    archive.mkdir(parents=True)
    for path in (failure, ROOT / 'status' / (day + '.json'), ROOT / 'logs' / (day + '.log'), ROOT / 'days' / day / 'CASE_COMPLETION.json'):
        if path.exists():
            shutil.copyfile(path, archive / path.name)
    copy_baseline_cache(day)
    failure.unlink()  # Its exact bytes now live in failed_attempts/day/FAILURE.json.
    return True


@contextmanager
def adopted_instance():
    own = current_process_identity()
    records = inventory()
    reject_duplicates(records, own['pid'])
    snapshot = read(REPAIR / 'PRE_REPAIR_SNAPSHOT.json')
    known = {r['pid']: r for r in snapshot['processes'] if '--day' in r.get('cmdline', [])}
    for worker in records['workers']:
        old = known.get(worker['pid'])
        if old is None or abs(old['create_time'] - __import__('datetime').datetime.fromisoformat(worker['creation_time_utc']).timestamp()) > 2:
            raise RuntimeError('UNRECOGNIZED_LIVE_WORKER')
    lock = ROOT / 'CAMPAIGN_INSTANCE.json'
    if lock.exists():
        previous = read(lock)
        if any(identity_matches(previous, r) for r in records['orchestrators']):
            raise RuntimeError('LIVE_INSTANCE_LOCK')
        lock.rename(REPAIR / ('PREVIOUS_INSTANCE_' + str(time.time_ns()) + '.json'))
    own.update(token=uuid.uuid4().hex, command_match_tokens=list(TOKENS))
    write_exclusive_json(lock, own)
    try:
        yield own, records['workers']
    finally:
        if lock.exists() and read(lock).get('token') == own['token']:
            lock.unlink()


def available_slots(active):
    return max(0, 4 - len(active))


def orchestrate_recovery():
    method, execution = verify_freeze()
    repair = read(REPAIR / 'CHANGE_IMPACT_AUDIT.json')
    if repair.get('status') != 'PASS' or repair['execution_SHA'] != execution['execution_SHA'] or repair['method_SHA'] != method['method_SHA']:
        raise RuntimeError('REPAIR_NOT_SEALED')
    with adopted_instance() as (own, workers):
        active = {r['day']: {'identity': {**r, 'command_match_tokens': ['run_v40b_campaign.py', '--day', r['day']]}, 'process': None, 'log': None, 'adopted': True} for r in workers}
        if len(active) > 4:
            raise RuntimeError('TOO_MANY_LIVE_DAY_WORKERS')
        rows = read(ROOT / 'V40B_MAY_EXECUTION_MATRIX.json')['rows']
        complete, failed, pending = {}, [], []
        for day in DAYS:
            if day in active:
                continue
            cert = certified_day(day, method['method_SHA'])
            if cert:
                complete[day] = cert
            elif (ROOT / 'days' / day / 'FAILURE.json').exists():
                (pending if prepare_retry(day) else failed).append(day)
            else:
                pending.append(day)
        write(REPAIR / 'ADOPTION_RECEIPT.json', {'status': 'PASS', 'time_utc': now_utc(), 'orchestrator': own, 'adopted_workers': workers, 'preserved_days': sorted(complete), 'queued_days': pending})
        sequence = 0
        while pending or active:
            live = inventory()
            reject_duplicates(live, own['pid'])
            for day, worker in list(active.items()):
                process = worker['process']
                running = process.poll() is None if process else any(identity_matches(worker['identity'], r) for r in live['workers'])
                if running:
                    continue
                cert = certified_day(day, method['method_SHA'])
                if cert and (process is None or process.returncode == 0):
                    complete[day] = cert
                elif worker['adopted'] and prepare_retry(day):
                    pending.insert(0, day)
                else:
                    failed.append(day)
                if worker['log']:
                    worker['log'].close()
                del active[day]
            for _ in range(min(available_slots(active), len(pending))):
                day = pending.pop(0)
                log_path = ROOT / 'logs' / (day + '.log')
                log_path.parent.mkdir(parents=True, exist_ok=True)
                log = log_path.open('ab', buffering=0)
                process = subprocess.Popen([sys.executable, '-u', str(REPO / 'dayahead/tools/run_v40b_campaign.py'), '--day', day], cwd=REPO, stdout=log, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
                active[day] = {'process': process, 'identity': {'pid': process.pid}, 'log': log, 'adopted': False}
            for row in rows:
                day, case = row['day'], row['case']
                partial = ROOT / 'days' / day / 'CASE_COMPLETION.json'
                cases = complete[day]['cases'] if day in complete else read(partial).get('cases', {}) if partial.exists() else {}
                if case in cases:
                    row.update(cases[case])
                elif day in failed:
                    row['status'] = 'FAILED'
                elif row['status'] == 'FAILED':
                    row['status'] = 'RUN_REQUIRED'
            from .reuse import write_matrix
            write_matrix(rows)
            sequence += 1
            now = now_utc()
            pids = {day: w['identity']['pid'] for day, w in active.items()}
            write(ROOT / 'V40A_MAY_PROGRESS.json', {'status': 'RUNNING' if active else 'FAIL' if failed else 'PASS', 'orchestrator_pid': own['pid'], 'orchestrator_parent_pid': own['parent_pid'], 'orchestrator_creation_time_utc': own['creation_time_utc'], 'orchestrator_command_match_tokens': list(TOKENS), 'heartbeat_timestamp_utc': now, 'last_update': now, 'heartbeat_sequence': sequence, 'method_SHA': method['method_SHA'], 'execution_SHA': execution['execution_SHA'], 'total_days': 31, 'completed_days': sorted(complete), 'failed_days': sorted(set(failed)), 'running_days': list(active), 'worker_PIDs': pids, 'active_worker_PIDs': list(pids.values()), 'recovery': 'WINDOWS_PATH_REPAIR_02'})
            if pending or active:
                time.sleep(10)
        passed = len(complete) == 31 and not failed
        write(ROOT / 'CAMPAIGN_COMPLETION.json', {'status': 'PASS' if passed else 'FAIL', 'completed_days': sorted(complete), 'failed_days': sorted(set(failed)), 'case_count': sum(r['status'] in ('REUSE_CERTIFIED', 'COMPLETE_NEW_V40A') for r in rows), 'new_B3_count': sum(r['case'] == 'B3' and r['status'] == 'COMPLETE_NEW_V40A' for r in rows)})

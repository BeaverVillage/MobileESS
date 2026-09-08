"""Four-day production supervisor, atomic state, lock, receipts and heartbeats."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import uuid

from dayahead.paper_analysis.storage import read, write_json
from .data import RUNTIME
from .preflight import ROOT, OUT, record
from .reserve import require

DAYS = tuple(f'2025-05-{d:02}' for d in range(1, 32))
POLICIES = ('B0', 'B1', 'B2', 'B3')
LOGS = ROOT / 'logs/v41_may_campaign'
WORKERS = 4  # Preserved V40B production max_parallel_day_workers.


def now(): return datetime.now(timezone.utc).isoformat()


@contextmanager
def campaign_lock(root=RUNTIME):
    import msvcrt
    root.mkdir(parents=True, exist_ok=True)
    stream = (root / 'campaign.lock').open('a+b')
    stream.seek(0); stream.write(b'0'); stream.flush(); stream.seek(0)
    try:
        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        stream.close(); raise RuntimeError('V41_CAMPAIGN_ALREADY_RUNNING')
    try:
        yield
    finally:
        stream.seek(0); msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1); stream.close()


def verify_receipt(path, frozen=None):
    receipt = read(path)
    require(receipt.get('schema')=='V41_PHASE_RECEIPT_V1','LEGACY_PHASE_RECEIPT_FORBIDDEN')
    require(receipt['status'] == 'COMPLETE', 'INCOMPLETE_PHASE_RECEIPT')
    if frozen:
        if receipt['scientific_commit'] != frozen['scientific_commit'] or receipt['science']['manifest_SHA'] != frozen['science']['manifest_SHA']:
            require(Path(path).name=='DAYAHEAD_RECEIPT.json' and receipt.get('day')==DAYS[0] and receipt.get('policy')=='B0',
                    'MIXED_SCIENTIFIC_COMMIT')
            from .retention import validate
            validate(receipt,frozen['science'])
    for entry in receipt['files'].values():
        require(record(entry['path']) == entry, 'PHASE_RECEIPT_HASH_DRIFT')
    if 'day_ahead' in receipt:
        require(record(receipt['day_ahead']['path']) == receipt['day_ahead'], 'ACTUAL_DAYAHEAD_BINDING_DRIFT')
    from .scientific_archive import verify_manifest
    require('scientific_manifest' in receipt['files'],'COMPLETE_WITHOUT_SCIENTIFIC_PERSISTENCE')
    verify_manifest(Path(path).parent/'SCIENTIFIC_MANIFEST.json')
    if 'day_ahead' in receipt:
        verify_manifest(Path(path).parent.parent/'UNIT_SCIENTIFIC_MANIFEST.json')
    return receipt


def frozen_identity():
    from .execution import science, commit
    receipt = read(OUT / 'V41_FINAL_INTERFACE_FREEZE_COMMIT_RECEIPT.json')
    require(receipt['scientific_commit'] == commit(), 'CAMPAIGN_HEAD_DIFFERS_FROM_FROZEN_COMMIT')
    require(receipt['science'] == science(), 'CAMPAIGN_SCIENTIFIC_SOURCE_DIRTY')
    freeze = read(OUT / 'V41_FINAL_INTERFACE_FREEZE.json')
    require(record(OUT / 'V41_FINAL_INTERFACE_FREEZE.json') == receipt['freeze'], 'FINAL_INTERFACE_FREEZE_DRIFT')
    from dayahead.v40h.identity import verify_manifest
    verify_manifest(freeze['complete_scientific_source_manifest'])
    propagation = read(OUT / 'V41_MAY_CAMPAIGN_PROPAGATION_AUDIT.json')
    require(propagation['PASS'] == propagation['TOTAL'] == 124 and propagation['FAIL'] == 0,
            'FULL_MAY_PROPAGATION_NOT_124_OF_124')
    require(freeze['pilot_status'] == 'PASS', 'PILOT_NOT_PASSED')
    p0=read(OUT/'V41_LEGACY_P0_01_07_CLOSURE_AUDIT.json')
    require(p0['status']=='PASS' and p0['PASS']==7 and p0['FAIL']==0 and
            all(r['status']=='PASS' for r in p0['items']),'LEGACY_P0_CLOSURE_GATE_FAILED')
    require(p0['source_manifest']==science(),'LEGACY_P0_AUDIT_SOURCE_CHANGED')
    return receipt


class Supervisor:
    def __init__(self, frozen):
        self.frozen = frozen; self.lock = threading.RLock(); self.done = threading.Event(); self.stop = threading.Event()
        self.sha = frozen['scientific_commit']; self.state_path = RUNTIME / 'campaign_state.json'
        if self.state_path.exists():
            self.state = read(self.state_path)
            require(self.state['scientific_commit'] == self.sha, 'EXISTING_CAMPAIGN_DIFFERENT_COMMIT')
        else:
            self.state = dict(schema='V41_CAMPAIGN_STATE_V1', scientific_commit=self.sha,
                created_at=now(), units={f'{d}/{p}': dict(day=d, policy=p, status='PENDING') for d in DAYS for p in POLICIES})
        self.state.update(pid=os.getpid(), restarted_at=now(), status='RUNNING')
        self.save()

    def save(self):
        with self.lock:
            self.state['updated_at'] = now(); write_json(self.state_path, self.state)
            rows = list(self.state['units'].values())
            complete = sum(r['status'] == 'COMPLETE' for r in rows)
            failed = sum(r['status'] == 'FAILED' for r in rows)
            da_done = sum(bool(r.get('dayahead_receipt')) for r in rows)
            actual_done = sum(bool(r.get('actual_receipt')) for r in rows)
            progress = dict(timestamp=now(), PID=os.getpid(), scientific_commit=self.sha, status=self.state['status'],
                completed_policy_days=complete, completed_DayAhead_phases=da_done, completed_Actual_phases=actual_done,
                failed_units=failed, remaining_units=124-complete-failed, total_policy_days=124,
                current=[{k: r.get(k) for k in ('day', 'policy', 'phase', 'worker_pid', 'status')}
                         for r in rows if r['status'] in ('DAYAHEAD_RUNNING', 'ACTUAL_RUNNING')],
                last_completed_receipt=self.state.get('last_completed_receipt'))
            write_json(RUNTIME / 'campaign_progress.json', progress)
            write_json(RUNTIME / 'campaign_heartbeat.json', progress)

    def heartbeat(self):
        while not self.done.wait(5):
            if (RUNTIME / 'STOP_REQUESTED.json').exists(): self.stop.set()
            self.save()

    def phase(self, row, phase):
        day, policy = row['day'], row['policy']; folder = RUNTIME / day / policy / phase
        if phase=='dayahead' and day==DAYS[0] and policy=='B0' and not folder.exists():
            # Explicit latest user amendment preserves this exact valid freeze.
            # Copy bytes without claiming a new DayAhead generation or commit.
            source=RUNTIME/'pilot'/day/policy/'dayahead'
            retained=read(source/'DAYAHEAD_RECEIPT.json')
            from .retention import validate
            validate(retained,self.frozen['science'])
            from .scientific_archive import verify_manifest,copy_atomic,document
            verify_manifest(source/'SCIENTIFIC_MANIFEST.json')
            for original in sorted(source.rglob('*')):
                if original.is_file(): copy_atomic(original,folder/original.relative_to(source))
            copy_atomic(source/'authority/COMMON_INPUT_IDENTITY.json',RUNTIME/day/'COMMON_INPUT_IDENTITY.json')
            document(folder.parent/'RETAINED_DAYAHEAD_ADOPTION.json',dict(
                authorization='Final Actual rack-dispatch amendment: preserve valid B0 DayAhead without rerun',
                original_receipt=record(source/'DAYAHEAD_RECEIPT.json'),original_producer_commit=retained['scientific_commit'],
                current_campaign_commit=self.sha,DayAhead_rerun=False,bytes_modified=False))
        receipt_path = folder / (phase.upper() + '_RECEIPT.json')
        if receipt_path.exists():
            stored=read(receipt_path)
            if stored['scientific_commit']!=self.sha or stored['science']!=self.frozen['science']:
                require(phase=='dayahead' and day==DAYS[0] and policy=='B0' and
                        stored.get('day')==DAYS[0] and stored.get('policy')=='B0','CANNOT_RESUME_DIFFERENT_SCIENCE')
                from .retention import validate
                validate(stored,self.frozen['science'])
            try:
                verify_receipt(receipt_path, self.frozen)
            except (ValueError,FileNotFoundError,OSError) as error:
                archive=RUNTIME/'interrupted'/(day+'_'+policy+'_invalid_'+uuid.uuid4().hex[:8])
                archive.resolve().relative_to(RUNTIME.resolve()); archive.mkdir(parents=True)
                paths=[folder]
                if phase=='dayahead': paths.append(RUNTIME/day/policy/'actual')
                paths.extend(RUNTIME/day/policy/name for name in ('UNIT_SCIENTIFIC_MANIFEST.json','UNIT_RECEIPT.json'))
                for target in paths:
                    target.resolve().relative_to((RUNTIME/day/policy).resolve())
                    if target.exists(): target.rename(archive/target.name)
                write_json(archive/'INVALIDATION.json',dict(reason=repr(error),scientific_commit=self.sha,
                    earliest_affected_phase=phase,descendant_Actual_invalidated=phase=='dayahead',completed_data_preserved=True))
                with self.lock:
                    row.pop(phase+'_receipt',None)
                    if phase=='dayahead': row.pop('actual_receipt',None)
                    row['invalidation']=record(archive/'INVALIDATION.json'); self.save()
            else:
                with self.lock: row[phase + '_receipt'] = record(receipt_path); self.save()
                return
        # A surviving worker after supervisor failure must finish before a
        # replacement can start. The command tag prevents PID-reuse adoption.
        import psutil
        matches = []
        for proc in psutil.process_iter(['pid', 'cmdline']):
            cmd = proc.info['cmdline'] or []
            if all(token in cmd for token in ('dayahead.v41.execution', day, policy, phase, self.sha)):
                matches.append(proc)
        require(len(matches) <= 1, 'DUPLICATE_PHASE_WORKERS')
        if matches:
            proc = matches[0]
            with self.lock: row.update(status=phase.upper() + '_RUNNING', phase=phase, worker_pid=proc.pid); self.save()
            while proc.is_running(): time.sleep(1)
            verify_receipt(receipt_path, self.frozen)
        else:
            frozen_identity()
            if folder.exists():
                # No COMPLETE receipt, no live worker: preserve the interrupted
                # attempt and rerun this phase under the identical science.
                destination = RUNTIME / 'interrupted' / (day + '_' + policy + '_' + phase + '_' + uuid.uuid4().hex[:8])
                folder.resolve().relative_to(RUNTIME.resolve()); destination.resolve().relative_to(RUNTIME.resolve())
                destination.parent.mkdir(parents=True, exist_ok=True); folder.rename(destination)
            log = LOGS / day / policy / (phase + '.log'); log.parent.mkdir(parents=True, exist_ok=True)
            command = [sys.executable, '-u', '-m', 'dayahead.v41.execution', '--day', day, '--policy', policy,
                       '--phase', phase, '--campaign-sha', self.sha]
            with log.open('a', encoding='utf-8') as stream:
                proc = subprocess.Popen(command, cwd=ROOT, stdin=subprocess.DEVNULL, stdout=stream, stderr=subprocess.STDOUT)
                with self.lock: row.update(status=phase.upper() + '_RUNNING', phase=phase, worker_pid=proc.pid, log=str(log)); self.save()
                code = proc.wait()
            require(code == 0, 'PHASE_PROCESS_FAILED:' + str(log))
            verify_receipt(receipt_path, self.frozen)
        with self.lock:
            row[phase + '_receipt'] = record(receipt_path)
            row.update(status='DAYAHEAD_DONE' if phase == 'dayahead' else 'ACTUAL_DONE', worker_pid=None)
            self.save()

    def day(self, day):
        # OpenDSS generation changes CWD internally; run in its own process.
        if self.stop.is_set(): return
        log = LOGS / day / 'electrical.log'; log.parent.mkdir(parents=True, exist_ok=True)
        row=self.state['units'][day+'/B0']
        try:
            import psutil
            matches=[p for p in psutil.process_iter(['cmdline']) if all(x in (p.info['cmdline'] or []) for x in ('dayahead.v41.electrical',day))]
            require(len(matches)<=1,'DUPLICATE_ELECTRICAL_WORKERS')
            if matches:
                proc=matches[0]
                with self.lock: row.update(status='DAYAHEAD_RUNNING',phase='ELECTRICAL_GENERATION',worker_pid=proc.pid); self.save()
                proc.wait()
                from .electrical import load
                context=load(day); context.electrical.voltage.close(); context.electrical.current.close()
            else:
                run=RUNTIME/'e'/day.replace('-','')
                if run.exists() and not (run/'V41_ELECTRICAL_CERTIFICATE.json').exists():
                    destination=RUNTIME/'interrupted'/('electrical_'+day+'_'+uuid.uuid4().hex[:8])
                    run.resolve().relative_to(RUNTIME.resolve()); destination.resolve().relative_to(RUNTIME.resolve())
                    destination.parent.mkdir(parents=True,exist_ok=True); run.rename(destination)
                with log.open('a', encoding='utf-8') as stream:
                    proc=subprocess.Popen([sys.executable,'-u','-m','dayahead.v41.electrical',day],cwd=ROOT,
                        stdin=subprocess.DEVNULL,stdout=stream,stderr=subprocess.STDOUT)
                    with self.lock: row.update(status='DAYAHEAD_RUNNING',phase='ELECTRICAL_GENERATION',worker_pid=proc.pid); self.save()
                    code=proc.wait()
                require(code==0,'DAY_ELECTRICAL_GENERATION_FAILED:'+day)
        except Exception as error:
            with self.lock: row.update(status='FAILED',error=repr(error)); self.save()
            self.stop.set(); raise
        for policy in POLICIES:
            if self.stop.is_set(): return
            row = self.state['units'][day + '/' + policy]
            try:
                for phase in ('dayahead', 'actual'):
                    if self.stop.is_set(): return
                    self.phase(row, phase)
                unit = dict(status='COMPLETE', day=day, policy=policy, scientific_commit=self.sha,
                    dayahead=row['dayahead_receipt'], actual=row['actual_receipt'], completed_at=now(),
                    scientific_manifest=record(RUNTIME/day/policy/'UNIT_SCIENTIFIC_MANIFEST.json'))
                path = RUNTIME / day / policy / 'UNIT_RECEIPT.json'
                if path.exists():
                    old = read(path)
                    require(old['dayahead'] == unit['dayahead'] and old['actual'] == unit['actual'], 'COMPLETE_UNIT_DRIFT')
                else: write_json(path, unit)
                with self.lock:
                    row.update(status='COMPLETE', phase=None, unit_receipt=record(path))
                    self.state['last_completed_receipt'] = record(path); self.save()
            except Exception as error:
                with self.lock: row.update(status='FAILED', error=repr(error)); self.save()
                self.stop.set(); raise

    def run(self):
        t = threading.Thread(target=self.heartbeat, daemon=True); t.start()
        errors = []
        try:
            with ThreadPoolExecutor(max_workers=WORKERS) as pool:
                futures = {pool.submit(self.day, day): day for day in DAYS}
                for future in as_completed(futures):
                    try: future.result()
                    except Exception as e:
                        errors.append({'day': futures[future], 'error': repr(e)}); self.stop.set()
            with self.lock:
                self.state['errors'] = errors
                self.state['status'] = 'FAILED' if errors else 'PAUSED' if self.stop.is_set() else 'COMPLETE'
                self.save()
        finally:
            self.done.set(); t.join(timeout=6)
        require(not errors, 'CAMPAIGN_FAILED_SEE_STATE')


def pilot():
    env = dict(os.environ, V41_PILOT='1')
    for policy in ('B0', 'B1'):
        for phase in ('dayahead', 'actual'):
            log = LOGS / 'pilot' / (policy + '_' + phase + '.log'); log.parent.mkdir(parents=True, exist_ok=True)
            with log.open('a', encoding='utf-8') as stream:
                code = subprocess.call([sys.executable, '-u', '-m', 'dayahead.v41.execution', '--day', DAYS[0],
                    '--policy', policy, '--phase', phase], cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT)
            require(code == 0, 'PILOT_PHASE_FAILED:' + str(log))
            print('PILOT', policy, phase, 'COMPLETE', flush=True)


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--mode', choices=['both'], default='both')
    parser.add_argument('--pilot', action='store_true'); parser.add_argument('--status', action='store_true')
    parser.add_argument('--stop', action='store_true')
    parser.add_argument('--resume', action='store_true')
    args = parser.parse_args()
    if args.status:
        print(json.dumps(read(RUNTIME / 'campaign_progress.json'), ensure_ascii=False, indent=2)); return
    if args.stop:
        write_json(RUNTIME / 'STOP_REQUESTED.json', {'requested_at': now(), 'mode': 'FINISH_CURRENT_PHASE'}); return
    if args.resume:
        with campaign_lock():
            frozen_identity()
            stop=RUNTIME/'STOP_REQUESTED.json'
            if stop.exists():
                receipt=read(stop); receipt['resumed_at']=now()
                write_json(RUNTIME/'LAST_STOP_AND_RESUME.json',receipt); stop.unlink()
        from .detached import launch
        launch(); return
    if args.pilot:
        pilot(); return
    with campaign_lock():
        require(not (RUNTIME / 'STOP_REQUESTED.json').exists(), 'STOP_REQUEST_STILL_PRESENT')
        frozen = frozen_identity()
        write_json(RUNTIME / 'campaign_pid.json', dict(pid=os.getpid(), started_at=now(), scientific_commit=frozen['scientific_commit']))
        Supervisor(frozen).run()


if __name__ == '__main__': main()

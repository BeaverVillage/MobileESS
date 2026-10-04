"""Serialized atomic transitions, immutable receipts, and crash recovery."""
import copy
import json
import os
import threading
import time
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from v42_campaign.authority import canonical, digest, file_sha
from .config import STAGE_VERSION

TRANSITIONS = {
    'NOT_RUN': {'READY', 'BLOCKED'},
    'READY': {'RUNNING', 'BLOCKED', 'NOT_RUN'},
    'RUNNING': {'PASS', 'FAIL', 'INTERRUPTED'},
    'PASS': {'NOT_RUN'},
    'FAIL': {'READY', 'NOT_RUN'},
    'INTERRUPTED': {'READY', 'PASS', 'NOT_RUN', 'BLOCKED'},
    'BLOCKED': {'NOT_RUN'},
}


def now():
    return datetime.now(timezone.utc).isoformat()


def atomic(path, value, *, immutable=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with temporary.open('xb') as handle:
            handle.write(canonical(value))
            handle.flush()
            os.fsync(handle.fileno())
        if immutable:
            os.link(temporary, path)
        else:
            # Windows scanners can briefly deny replace even after all our handles
            # close. Retry the same atomic operation; never fall back to truncation.
            for attempt in range(8):
                try:
                    os.replace(temporary, path)
                    break
                except PermissionError:
                    if attempt == 7:
                        raise
                    time.sleep(.01 * (attempt + 1))
    finally:
        temporary.unlink(missing_ok=True)


class CoordinatorLock:
    """OS releases this advisory lock on process death, including machine restart."""
    def __init__(self, path):
        self.handle = Path(path).open('a+b')
        try:
            if os.fstat(self.handle.fileno()).st_size == 0:
                self.handle.write(b'0')
                self.handle.flush()
            self.handle.seek(0)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, BlockingIOError):
            self.handle.close()
            raise RuntimeError('CAMPAIGN_COORDINATOR_ALREADY_ACTIVE')

    def close(self):
        if self.handle.closed:
            return
        self.handle.seek(0)
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        self.handle.close()


class Ledger:
    def __init__(self, root, plan, *, input_sha, stage_version=STAGE_VERSION):
        if not isinstance(input_sha, str) or len(input_sha) != 64 or any(c not in '0123456789abcdef' for c in input_sha):
            raise ValueError('Explicit SHA256 input authority required')
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = CoordinatorLock(self.root / 'COORDINATOR.lock')
        self.mutex = threading.RLock()
        self.plan = plan
        self.nodes = {n['id']: n for n in plan['nodes']}
        self.path = self.root / 'CAMPAIGN_STATE.json'
        self.identity = dict(scientific_sha=plan['scientific_sha'], input_sha=input_sha,
                             stage_version=stage_version, plan_sha=digest(plan), mode='MOCK_ONLY')
        try:
            if self.path.exists():
                self.state = json.loads(self.path.read_text(encoding='utf8'))
                if self.state.get('schema_version') != 1 or set(self.state['stages']) != set(self.nodes):
                    raise ValueError('Checkpoint topology/schema mismatch; use a new campaign root')
                if self.state.get('production_calls') != dict(optimizer=0, Actual=0, Fresh_AC=0):
                    raise ValueError('Mock checkpoint contains production execution')
                for sid, row in self.state['stages'].items():
                    if row.get('status') not in TRANSITIONS:
                        raise ValueError('Invalid checkpoint status')
                    node = self.nodes[sid]
                    if any(row.get(k) != node[k] for k in ('arm', 'day', 'loop', 'stage')):
                        raise ValueError('Checkpoint stage/day/arm/loop identity mismatch')
                    if type(row.get('retry_count')) is not int or not 0 <= row['retry_count'] <= 10:
                        raise ValueError('Invalid persisted retry count')
                    if not isinstance(row.get('timestamps'), dict):
                        raise ValueError('Invalid checkpoint timestamps')
                self.recover()
            else:
                self.state = dict(schema_version=1, identity=self.identity, revision=0,
                                  production_calls=dict(optimizer=0, Actual=0, Fresh_AC=0),
                                  stages={sid: self.blank(n) for sid, n in self.nodes.items()},
                                  transitions=[], campaign_status='NOT_RUN')
                self.save()
        except BaseException:
            self.lock.close()
            raise

    def blank(self, node):
        return dict(status='NOT_RUN', arm=node['arm'], day=node['day'], loop=node['loop'],
                    stage=node['stage'], scientific_sha=self.identity['scientific_sha'],
                    input_sha=None, output_sha=None, stage_version=self.identity['stage_version'],
                    timestamps={'created': now()}, worker=None, failure_reason=None,
                    failure_kind=None, retry_count=0, receipt_path=None)

    def close(self):
        self.lock.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def save(self):
        self.state['identity'] = self.identity
        self.state['revision'] += 1
        atomic(self.path, self.state)

    def transition(self, sid, status, **fields):
        with self.mutex:
            row = self.state['stages'][sid]
            old = row['status']
            if status not in TRANSITIONS[old]:
                raise ValueError(f'Invalid transition {old}->{status}')
            row.update(fields, status=status)
            row['timestamps'][status] = now()
            self.state['transitions'].append(dict(id=sid, old=old, new=status, timestamp=now()))
            self.save()

    def input_digest(self, sid):
        node = self.nodes[sid]
        # Control gates contribute completion only, never Actual values/hashes.
        planning = {dep: self.state['stages'][dep]['output_sha'] for dep in node['Planning_dependencies']}
        if node['planning'] or node['stage'] == 'PLANNING_FREEZE':
            data = planning
        else:
            data = {dep: self.state['stages'][dep]['output_sha'] for dep in node['required_pass']}
        return digest(dict(external_input_sha=self.identity['input_sha'], day=node['day'],
                           arm=node['arm'], loop=node['loop'], data_dependencies=data))

    def expected(self, sid):
        node = self.nodes[sid]
        return dict(**self.identity, day=node['day'], arm=node['arm'], loop=node['loop'],
                    stage=node['stage'], id=sid, stage_input_sha=self.input_digest(sid))

    def receipt_path(self, sid):
        node = self.nodes[sid]
        # Identity directory means stale generations never overwrite an accepted artifact.
        return self.root / node['artifact_destination'] / digest(self.expected(sid)) / 'PASS.json'

    def read_receipt(self, sid):
        path = self.receipt_path(sid)
        if not path.exists():
            return None
        if not path.resolve().is_relative_to(self.root):
            raise ValueError('Receipt outside campaign root')
        try:
            receipt = json.loads(path.read_text(encoding='utf8'))
            if (receipt['identity'] != self.expected(sid) or receipt['status'] != 'PASS'
                    or receipt['synthetic_only'] is not True
                    or receipt['output_sha'] != digest(receipt['payload'])):
                return None
            expected_phase = ('PLANNING' if self.nodes[sid]['planning'] or
                              self.nodes[sid]['stage'] == 'PLANNING_FREEZE' else self.nodes[sid]['stage'])
            if receipt['payload'].get('producer_phase') != expected_phase:
                return None
            return receipt
        except (ValueError, KeyError, TypeError):
            return None

    def pass_fields(self, sid, receipt):
        return dict(scientific_sha=self.identity['scientific_sha'],
                    stage_version=self.identity['stage_version'], input_sha=self.input_digest(sid),
                    output_sha=receipt['output_sha'], receipt_sha=file_sha(self.receipt_path(sid)),
                    receipt_path=self.receipt_path(sid).relative_to(self.root).as_posix(),
                    failure_reason=None, failure_kind=None)

    def recover(self):
        changed = self.state['identity'] != self.identity
        invalid = set()
        for sid, node in self.nodes.items():
            row = self.state['stages'][sid]
            stale = changed or bool(set(node['required_pass']) & invalid)
            receipt = None if changed else self.read_receipt(sid)
            receipt_mismatch = False
            if row['status'] == 'PASS':
                if (receipt is None or row.get('output_sha') != receipt['output_sha']
                        or row.get('receipt_sha') != file_sha(self.receipt_path(sid))):
                    stale = True
                    receipt_mismatch = True
            if stale:
                invalid.add(sid)
                # A corrupt current-generation receipt must not block safe rerun.
                # Preserve its bytes in quarantine; never overwrite accepted output.
                current_path = self.receipt_path(sid)
                if not changed and current_path.exists() and (receipt_mismatch or self.read_receipt(sid) is None):
                    quarantine = self.root / 'quarantine' / (digest(sid) + '.' + uuid.uuid4().hex + '.json')
                    quarantine.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(current_path, quarantine)
                if row['status'] == 'RUNNING':
                    self.transition(sid, 'INTERRUPTED', failure_reason='ORPHAN_RUNNING')
                if row['status'] != 'NOT_RUN':
                    self.transition(sid, 'NOT_RUN', failure_reason='STALE_RECEIPT_OR_DEPENDENCY')
                # Retry budget belongs to this identity; stale identities start anew.
                row.update(retry_count=0, input_sha=None, output_sha=None, receipt_path=None,
                           scientific_sha=self.identity['scientific_sha'], stage_version=self.identity['stage_version'])
            elif row['status'] in ('RUNNING', 'INTERRUPTED'):
                if row['status'] == 'RUNNING':
                    self.transition(sid, 'INTERRUPTED', failure_reason='ORPHAN_RUNNING')
                if receipt and self.dependencies_pass(sid):
                    self.transition(sid, 'PASS', **self.pass_fields(sid, receipt))
                elif self.dependencies_pass(sid):
                    self.transition(sid, 'READY', failure_reason='RESTART_UNFINISHED_STAGE')
        self.save()

    def dependencies_pass(self, sid):
        return all(self.state['stages'][dep]['status'] == 'PASS' for dep in self.nodes[sid]['required_pass'])

    def begin(self, sid, worker):
        with self.mutex:
            if not self.dependencies_pass(sid):
                raise ValueError('Required dependency not PASS')
            row = self.state['stages'][sid]
            if row['status'] == 'PASS':
                receipt = self.read_receipt(sid)
                if (receipt is None or row.get('output_sha') != receipt['output_sha']
                        or row.get('receipt_sha') != file_sha(self.receipt_path(sid))):
                    raise ValueError('PASS receipt became stale; reopen ledger to invalidate descendants')
                return False
            if row['status'] in ('NOT_RUN', 'INTERRUPTED'):
                self.transition(sid, 'READY')
            if row['status'] != 'READY':
                raise ValueError('Stage is not runnable')
            # Publication-before-checkpoint crash can leave a valid unindexed receipt.
            receipt = self.read_receipt(sid)
            self.transition(sid, 'RUNNING', worker=worker, input_sha=self.input_digest(sid))
            if receipt:
                self.transition(sid, 'PASS', **self.pass_fields(sid, receipt))
                return False
            return True

    def publish(self, sid, payload):
        with self.mutex:
            if self.state['stages'][sid]['status'] != 'RUNNING':
                raise ValueError('Publication requires RUNNING')
            expected_phase = ('PLANNING' if self.nodes[sid]['planning'] or
                              self.nodes[sid]['stage'] == 'PLANNING_FREEZE' else self.nodes[sid]['stage'])
            if payload.get('producer_phase') != expected_phase or payload.get('synthetic_only') is not True:
                raise ValueError('Mock acceptance requires synthetic output with matching producer phase')
            receipt = dict(status='PASS', identity=self.expected(sid), payload=copy.deepcopy(payload),
                           output_sha=digest(payload), synthetic_only=True, accepted_at=now())
            path = self.receipt_path(sid)
            if path.exists():
                previous = self.read_receipt(sid)
                if previous is None or previous['output_sha'] != receipt['output_sha']:
                    raise ValueError('Conflicting immutable artifact; explicit repair required')
                return previous
            atomic(path, receipt, immutable=True)
            return receipt

    def finish(self, sid, payload):
        with self.mutex:
            receipt = self.publish(sid, payload)
            self.transition(sid, 'PASS', **self.pass_fields(sid, receipt))

    def block_downstream(self, sid, reason):
        with self.mutex:
            blocked = {sid}
            for target, node in self.nodes.items():
                if set(node['required_pass']) & blocked:
                    blocked.add(target)
                    if self.state['stages'][target]['status'] in ('NOT_RUN', 'READY', 'INTERRUPTED'):
                        self.transition(target, 'BLOCKED', failure_reason=reason)

    def summary(self):
        return dict(status_counts=dict(Counter(r['status'] for r in self.state['stages'].values())),
                    groups={g: dict(Counter(self.state['stages'][n['id']]['status'] for n in self.plan['nodes']
                                           if n['group'] == g)) for g in self.plan['main_order'] + self.plan['convergence_order']},
                    campaign_status=self.state['campaign_status'], production_calls=self.state['production_calls'])

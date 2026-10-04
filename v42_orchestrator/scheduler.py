"""Deterministic dynamic day queues, strict arm barriers, and bounded retry."""
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

from .config import Config
from .ledger import atomic
from .mock import MockAdapter, ScientificFailure, TransientFailure
from .resources import Resources, ResourceStop


class Scheduler:
    def __init__(self, ledger, config=Config(), *, adapter=None, resources=None):
        self.ledger, self.config = ledger, config
        self.adapter = adapter if adapter is not None else MockAdapter()
        # Reject arbitrary execution callbacks; real execution is a separate future capability.
        if type(self.adapter) is not MockAdapter:
            config.production_guard()
        self.resources = resources if resources is not None else Resources(config)
        if self.resources.config != config:
            raise ValueError('Resource configuration mismatch')
        self.stop = threading.Event()
        self.mutex = threading.Lock()
        self.active = Counter()
        self.peak_days = Counter()
        self.events = []
        self.scheduled_days = []

    def execute(self, node):
        sid = node['id']
        if self.stop.is_set():
            return False
        worker = threading.current_thread().name
        if not self.ledger.begin(sid, worker):
            return True
        while True:
            try:
                deps = (node['Planning_dependencies'] if node['planning'] or node['stage'] == 'PLANNING_FREEZE'
                        else node['required_pass'])
                payloads = {dep: self.ledger.read_receipt(dep)['payload'] for dep in deps}
                payload = self.adapter.execute(node, payloads, self.resources, self.config)
                self.ledger.finish(sid, payload)
                return True
            except TransientFailure as error:
                row = self.ledger.state['stages'][sid]
                self.ledger.transition(sid, 'FAIL', failure_kind='INFRASTRUCTURE_TRANSIENT', failure_reason=str(error))
                if row['retry_count'] >= self.config.MAX_TRANSIENT_RETRIES:
                    self.ledger.block_downstream(sid, 'TRANSIENT_RETRIES_EXHAUSTED')
                    return False
                self.ledger.transition(sid, 'READY', retry_count=row['retry_count'] + 1)
                self.ledger.begin(sid, worker)
            except ScientificFailure as error:
                self.ledger.transition(sid, 'FAIL', failure_kind='SCIENTIFIC_HARD_FAILURE', failure_reason=str(error))
                self.ledger.block_downstream(sid, str(error))
                return False
            except ResourceStop as error:
                self.stop.set()
                self.ledger.transition(sid, 'INTERRUPTED', failure_kind='RESOURCE_GUARD', failure_reason=str(error))
                return False
            except BaseException as error:
                self.stop.set()
                self.ledger.transition(sid, 'INTERRUPTED', failure_kind='WORKER_OR_COORDINATOR_CRASH',
                                       failure_reason=f'{type(error).__name__}: {error}')
                raise

    def day(self, group, day):
        arm = group.split('_')[0]
        if self.stop.is_set():
            return False
        with self.mutex:
            self.active[arm] += 1
            self.peak_days[arm] = max(self.peak_days[arm], self.active[arm])
            self.events.append(dict(group=group, day=day, event='START', active=self.active[arm]))
        try:
            for node in self.ledger.plan['nodes']:
                if node['group'] == group and node['day'] == day:
                    if not self.execute(node):
                        return False
            return True
        finally:
            with self.mutex:
                self.active[arm] -= 1
                self.events.append(dict(group=group, day=day, event='END', active=self.active[arm]))

    def pending_days(self, group):
        nodes = [n for n in self.ledger.plan['nodes'] if n['group'] == group]
        return [day for day in self.ledger.plan['days'] if any(
            self.ledger.state['stages'][n['id']]['status'] != 'PASS' for n in nodes if n['day'] == day)]

    def run(self):
        self.ledger.state['campaign_status'] = 'RUNNING'
        self.ledger.save()
        try:
            for group in self.ledger.plan['main_order'] + self.ledger.plan['convergence_order']:
                nodes = [n for n in self.ledger.plan['nodes'] if n['group'] == group]
                pending = self.pending_days(group)
                if any(self.ledger.state['stages'][n['id']]['status'] in ('FAIL', 'BLOCKED') for n in nodes):
                    break
                first = [n for n in nodes if n['stage'] == nodes[0]['stage']]
                if any(not self.ledger.dependencies_pass(n['id']) for n in first):
                    break
                self.scheduled_days.extend((group, day) for day in pending)
                with ThreadPoolExecutor(max_workers=self.config.day_workers(group.split('_')[0]),
                                        thread_name_prefix=group) as executor:
                    results = list(executor.map(lambda day: self.day(group, day), pending))
                if not all(results) or self.stop.is_set():
                    break
                if group == 'B3_L1':
                    if not self.execute(self.ledger.nodes['MAIN_MAY_CAMPAIGN_COMPLETE']):
                        break
        finally:
            rows = self.ledger.state['stages'].values()
            status = 'PASS' if all(r['status'] == 'PASS' for r in rows) else (
                'INTERRUPTED' if self.stop.is_set() else 'BLOCKED')
            self.ledger.state['campaign_status'] = status
            self.ledger.save()
            atomic(self.ledger.root / 'CAMPAIGN_SUMMARY.json', self.ledger.summary())
        return self.ledger.summary()

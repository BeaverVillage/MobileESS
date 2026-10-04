"""Sleep-only backend. No solver, OpenDSS, subprocess, or production adapter."""
import copy
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from .dag import planning_inputs
from v42_campaign.state import detector


class ScientificFailure(RuntimeError):
    pass


class TransientFailure(RuntimeError):
    pass


class WorkerCrash(BaseException):
    pass


class MockAdapter:
    def __init__(self, delay=.002, failures=None, detection=None, synchronize_B2_workers=None):
        self.delay, self.failures = delay, dict(failures or {})
        self.detection = detection
        self.lock = threading.Lock()
        self.calls = []
        self.contexts = {}
        self.pricing_tasks = []
        self.b2_barrier = threading.Barrier(synchronize_B2_workers) if synchronize_B2_workers else None

    def execute(self, node, payloads, resources, config):
        with self.lock:
            self.calls.append(node['id'])
            failure = self.failures.pop(node['id'], None)
        if failure:
            raise failure
        if node['planning'] or node['stage'] == 'PLANNING_FREEZE':
            payloads = planning_inputs(node, payloads)
        with self.lock:
            self.contexts[node['id']] = copy.deepcopy(payloads)
        resources.admit()
        if node['arm'] == 'B2' and node['stage'] == 'M1' and self.b2_barrier:
            self.b2_barrier.wait(timeout=10)
        inner_barrier = threading.Barrier(config.slots(node)) if self.b2_barrier and config.slots(node) else None
        def solve(index):
            with resources.solve_slot(f"{node['id']}/pricing{index}"):
                with self.lock:
                    self.pricing_tasks.append(dict(id=node['id'], index=index))
                if inner_barrier:
                    inner_barrier.wait(timeout=10)
                time.sleep(self.delay)
        slots = config.slots(node)
        if slots:
            with ThreadPoolExecutor(max_workers=slots) as executor:
                list(executor.map(solve, range(slots)))
        else:
            time.sleep(self.delay)
        resources.admit()
        phase = 'PLANNING' if node['planning'] or node['stage'] == 'PLANNING_FREEZE' else node['stage']
        detected = (detector(self.detection[:node['loop']]) if self.detection and
                    node['loop'] and node['stage'] == 'PLANNING_FREEZE' else None)
        return dict(producer_phase=phase, synthetic_only=True, id=node['id'],
                    previous_planning=sorted(payloads), detector=detected,
                    free_decisions=node.get('free_decisions', []))

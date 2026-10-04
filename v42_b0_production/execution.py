"""PR146 dynamic B0 queues with native isolation, bounded restart and stop."""
import copy
import json
import os
import subprocess
import sys
import threading
import time
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

from v42_campaign.authority import digest, file_sha
from v42_orchestrator.ledger import Ledger, atomic
from v42_orchestrator.mock import MockAdapter, ScientificFailure, TransientFailure
from v42_orchestrator.resources import Resources, ResourceStop
from v42_orchestrator.scheduler import Scheduler
from .authority import ROOT, DOC, read, record, b0_plan
from .config import B0Config, VERSION
from .telemetry import LiveTelemetry


def producer_phase(node):
    return 'PLANNING' if node['planning'] or node['stage'] == 'PLANNING_FREEZE' else node['stage']


class B0Ledger(Ledger):
    synthetic_only = False

    def __init__(self, root, plan, authority):
        self.authority = authority
        if any(n['arm'] != 'B0' for n in plan['nodes']):
            raise PermissionError('Production ledger is B0 only')
        path = Path(root) / 'CAMPAIGN_STATE.json'
        if path.exists() and read(path)['identity']['mode'] != 'B0_PRODUCTION':
            raise PermissionError('New production identity cannot reuse mock/historical checkpoint')
        super().__init__(root, plan, input_sha=authority['input_sha'], stage_version=VERSION)
        counters = self.state['production_calls']
        for key in ('B0_PLANNING', 'B1', 'B2', 'B3', 'M1', 'Branch_and_Price', 'Gurobi_optimize'):
            counters.setdefault(key, 0)
        self.save()

    def make_identity(self, plan, input_sha, stage_version):
        return dict(super().make_identity(plan, input_sha, stage_version), mode='B0_PRODUCTION',
                    run_id=self.authority['run_id'], checker_SHA=self.authority['checker_SHA'])

    def validate_counters(self, counters):
        return (isinstance(counters, dict) and
                all(type(v) is int and v >= 0 for v in counters.values()) and
                all(counters.get(k, 0) == 0 for k in ('optimizer', 'B1', 'B2', 'B3', 'M1',
                                                     'Branch_and_Price', 'Gurobi_optimize')))

    def validate_payload(self, node, payload):
        if (node['arm'] != 'B0' or payload.get('synthetic_only') is not False
                or payload.get('producer_phase') != producer_phase(node)
                or payload.get('run_id') != self.authority['run_id']
                or payload.get('day') != node['day'] or payload.get('stage') != node['stage']
                or payload.get('checker_SHA') != self.authority['checker_SHA']
                or payload.get('validated') is not True or payload.get('complete') is not True):
            return False
        for row in payload.get('output_files', []):
            path = Path(row['path']).resolve()
            if not path.is_relative_to(self.root) or not path.is_file() or file_sha(path) != row['sha256']:
                return False
        if not payload.get('output_files'):
            return False
        metrics = payload.get('metrics', {})
        if node['stage'] in ('B0_PLANNING', 'PLANNING_FREEZE'):
            frozen = read(Path(payload['folder']) / 'PLANNING_FREEZE.json')
            if (not frozen.get('no_Actual_read') or frozen.get('optimizer_calls') != 0
                    or not frozen.get('source_parameter_integrity') or not frozen.get('capacitors_fixed_ON')
                    or frozen.get('CapControl_count') != 0
                    or frozen.get('transformer_current_authority_sha256') != self.authority['checker_SHA']
                    or metrics.get('capacity_violations') != 0):
                return False
        elif node['stage'] == 'ACTUAL':
            if not metrics.get('IT_recomputed_from_actual_occupancy') or metrics.get('DayAhead_power_arrays_copied') is not False:
                return False
        elif node['stage'] == 'FRESH_AC':
            if (not metrics.get('converged') or metrics.get('converged_slots') != 96
                    or not metrics.get('workload_PQ_identity') or not metrics.get('parameter_integrity')
                    or not metrics.get('all_RegControls_enabled') or metrics.get('CapControl_count') != 0
                    or not metrics.get('fixed_capacitors_all_ON') or metrics.get('MESS_PQ') != 0
                    or metrics.get('Actual_P_repair') != 0 or metrics.get('Actual_Q_repair') != 0
                    or metrics.get('Actual_global_reoptimization') != 0
                    or metrics.get('Actual_Planning_tap_replay') is not False
                    or metrics.get('transformer_current_authority_sha256') != self.authority['checker_SHA']):
                return False
        if node['stage'] == 'VALIDATION_FREEZE':
            return payload['metrics'].get('scientific_PASS') is True
        return True


class B0Adapter:
    def __init__(self, ledger, authority, live):
        self.ledger, self.authority, self.live = ledger, authority, live
        self.config = B0Config(**authority['config'])
        self.config.authorize('B0')
        self.native_calls = []
        self.lock = threading.Lock()

    def payload(self, node, folder, output_files, metrics):
        return dict(producer_phase=producer_phase(node), synthetic_only=False,
            run_id=self.authority['run_id'], day=node['day'], arm='B0', stage=node['stage'],
            checker_SHA=self.authority['checker_SHA'], folder=str(folder), output_files=output_files,
            metrics=metrics, validated=True, complete=True)

    def accepted(self, day, stage):
        receipt = self.ledger.read_receipt(f'B0/{day}/{stage}')
        if receipt is None:
            raise ScientificFailure('Accepted B0 input receipt invalid')
        return receipt['payload']

    def native(self, request, resources):
        stage = request['stage']
        day = request.get('day')
        if stage != 'TRUTH_PREPARATION':
            self.config.authorize('B0', stage)
            base = self.ledger.receipt_path(f'B0/{day}/{stage}').parent
        else:
            base = self.ledger.root / 'truth_attempts'
        base.mkdir(parents=True, exist_ok=True)
        attempt = base / ('attempt-' + uuid.uuid4().hex[:8])
        attempt.mkdir()
        request.update(run_root=str(self.ledger.root), arm='B0', run_id=self.authority['run_id'],
                       output=str(attempt / 'native'), result=str(attempt / 'RESULT.json'))
        atomic(attempt / 'REQUEST.json', request)
        if stage in ('B0_PLANNING', 'ACTUAL', 'FRESH_AC'):
            key = {'B0_PLANNING': 'B0_PLANNING', 'ACTUAL': 'Actual', 'FRESH_AC': 'Fresh_AC'}[stage]
            with self.ledger.mutex:
                self.ledger.state['production_calls'][key] += 1
                self.ledger.save()
        process = None
        with resources.solve_slot(f'B0/{day}/{stage}'):
            with (attempt / 'NATIVE.log').open('w', encoding='utf8', newline='\n') as log:
                process = subprocess.Popen([sys.executable, '-X', 'utf8', '-m', 'v42_b0_production.worker',
                    str(attempt / 'REQUEST.json')], cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
                self.live.register(process.pid, day or 'SHARED_ACTUAL_TRUTH', stage)
                try:
                    while process.poll() is None:
                        resources.admit()
                        time.sleep(.25)
                    resources.admit()
                except ResourceStop:
                    # Hard resource guard cancels this task's own native worker only.
                    if process.poll() is None:
                        process.terminate()
                        process.wait(timeout=10)
                    raise
                finally:
                    self.live.unregister(process.pid)
        result_path = Path(request['result'])
        if not result_path.exists():
            raise TransientFailure(f'Native worker exit {process.returncode} without result: {attempt}')
        result = read(result_path)
        with self.lock:
            self.native_calls.append(dict(day=day, stage=stage, PID=process.pid,
                status=result['status'], runtime_seconds=result.get('runtime_seconds'), attempt=str(attempt)))
        if result['status'] != 'COMPUTED':
            kind = result.get('error_type')
            reason = result.get('reason', '')
            if kind == 'MemoryError':
                raise ResourceStop('OOM/MemoryError in own B0 native process')
            if kind in ('OSError', 'PermissionError', 'FileNotFoundError') and ('[Errno' in reason or '[WinError' in reason):
                raise TransientFailure(f'{kind}: {reason}')
            if kind == 'GurobiError' and 'license' in reason.lower():
                raise TransientFailure('Temporary native license failure: ' + reason)
            raise ScientificFailure(f'{kind}: {reason}; native result {result_path}')
        if any(result.get(k) != 0 for k in ('Gurobi_optimize_calls', 'M1_calls', 'B1_calls',
                                           'B2_calls', 'B3_calls', 'Branch_and_Price_calls')):
            raise ScientificFailure('Forbidden non-B0 or optimization execution')
        return result

    def truth(self, resources):
        path = self.ledger.root / 'ACTUAL_TRUTH_RECEIPT.json'
        target = self.ledger.root / 'actual_truth'
        if path.exists():
            receipt = read(path)
            if receipt['run_id'] != self.authority['run_id'] or any(
                file_sha(row['path']) != row['sha256'] for row in receipt['output_files']):
                raise ScientificFailure('Private Actual truth receipt drift')
            return
        if target.exists():
            # Reconcile a crash after exclusive directory publication but before receipt.
            for candidate in (self.ledger.root / 'truth_attempts').glob('attempt-*/RESULT.json'):
                previous = read(candidate)
                if previous.get('run_id') != self.authority['run_id'] or previous.get('status') != 'COMPUTED':
                    continue
                rows = [record(target / Path(r['path']).name) for r in previous['output_files']]
                if all(a['sha256'] == b['sha256'] for a, b in zip(rows, previous['output_files'])):
                    atomic(path, dict(run_id=self.authority['run_id'], raw_reconstruction=True,
                        all_31_new_Planning_frozen=True, reconciled_after_crash=True,
                        output_files=rows, metrics=previous['metrics']))
                    return
            raise ScientificFailure('Unaccepted private truth directory cannot be reconciled')
        result = self.native(dict(stage='TRUTH_PREPARATION', day=None, accepted_inputs=[]), resources)
        if target.exists():
            raise ScientificFailure('Unaccepted private truth directory exists')
        # Move only this task's newly produced directory into its deterministic run root.
        source = Path(result['folder']).resolve()
        if not source.is_relative_to(self.ledger.root) or not target.resolve().is_relative_to(self.ledger.root):
            raise PermissionError('Truth directory outside run root')
        os.replace(source, target)
        rows = [record(p) for p in target.iterdir() if p.is_file()]
        atomic(path, dict(run_id=self.authority['run_id'], raw_reconstruction=True,
                         all_31_new_Planning_frozen=True, output_files=rows, metrics=result['metrics']))

    def execute(self, node, payloads, resources, config):
        self.config.authorize(node['arm'], node['stage'])
        day, stage = node['day'], node['stage']
        resources.admit()
        if stage == 'PLANNING_FREEZE':
            planning = self.accepted(day, 'B0_PLANNING')
            frozen = read(Path(planning['folder']) / 'PLANNING_FREEZE.json')
            if not frozen['no_Actual_read'] or frozen['optimizer_calls'] != 0:
                raise ScientificFailure('B0 Planning/Actual firewall failure')
            return self.payload(node, planning['folder'], planning['output_files'],
                                dict(planning['metrics'], Planning_freeze_verified=True))
        if stage == 'VALIDATION_FREEZE':
            plan = self.accepted(day, 'PLANNING_FREEZE')
            actual = self.accepted(day, 'ACTUAL')
            fresh = self.accepted(day, 'FRESH_AC')
            metrics = dict(fresh['metrics'])
            violations = {k: metrics[k] for k in ('voltage_violations', 'line_current_violations',
                'transformer_current_violations', 'transformer_kVA_violations')}
            violations['Planning_voltage_violations'] = plan['metrics']['Planning_voltage_violations']
            passed = all(v == 0 for v in violations.values()) and metrics['converged_slots'] == 96
            summary = dict(metrics, violations=violations, scientific_PASS=passed,
                           Planning_metrics=plan['metrics'], Actual_metrics=actual['metrics'])
            destination = self.ledger.receipt_path(node['id']).parent / 'PHYSICAL_VALIDATION.json'
            if not destination.exists():
                atomic(destination, summary, immutable=True)
            elif read(destination) != summary:
                raise ScientificFailure('Immutable physical validation conflict')
            if not passed:
                raise ScientificFailure('B0 physical violation: ' + json.dumps(violations, sort_keys=True))
            return self.payload(node, fresh['folder'], [record(destination), *fresh['output_files']], summary)
        planning = self.accepted(day, 'PLANNING_FREEZE') if stage in ('ACTUAL', 'FRESH_AC') else None
        actual = self.accepted(day, 'ACTUAL') if stage == 'FRESH_AC' else None
        inputs = ([] if planning is None else planning['output_files']) + ([] if actual is None else actual['output_files'])
        result = self.native(dict(stage=stage, day=day, accepted_inputs=inputs,
            planning_folder=None if planning is None else planning['folder'],
            actual_folder=None if actual is None else actual['folder']), resources)
        return self.payload(node, result['folder'], result['output_files'], result['metrics'])


class B0Scheduler(Scheduler):
    def __init__(self, ledger, config, adapter, live):
        config.authorize('B0')
        if type(adapter) is not B0Adapter or any(n['arm'] != 'B0' for n in ledger.plan['nodes']):
            raise PermissionError('Reviewed B0-only adapter and DAG required')
        # Keep the global PR146 production guard unchanged. This subclass owns
        # exactly one reviewed B0 adapter; arbitrary callbacks remain forbidden.
        super().__init__(ledger, config, adapter=MockAdapter(), resources=Resources(config, live.get))
        self.adapter, self.live = adapter, live
        self.phase = None
        self.selected_workers = 4
        self.downgrades = []
        self.admission_pauses = []
        self.peak_solver_slots = 0

    def day(self, group, day):
        if self.stop.is_set():
            return False
        while self.live.foreign:
            if self.stop.is_set():
                return False
            try:
                self.resources.admit()
            except ResourceStop:
                self.stop.set()
                return False
            self.admission_pauses.append(dict(day=day, reason='unrelated full-scale native solve active',
                                             observed=copy.deepcopy(self.live.foreign)))
            time.sleep(1)
        try:
            self.resources.admit()
        except ResourceStop as error:
            self.stop.set()
            return False
        with self.mutex:
            self.active['B0'] += 1
            self.peak_days['B0'] = max(self.peak_days['B0'], self.active['B0'])
            self.events.append(dict(group='B0', day=day, event='START', phase=self.phase,
                                    active=self.active['B0'], elapsed_s=time.monotonic()-self.live.started))
        try:
            stages = ('B0_PLANNING', 'PLANNING_FREEZE') if self.phase == 'PLANNING' else ('ACTUAL', 'FRESH_AC', 'VALIDATION_FREEZE')
            for stage in stages:
                node = self.ledger.nodes[f'B0/{day}/{stage}']
                if self.ledger.state['stages'][node['id']]['status'] in ('FAIL', 'BLOCKED'):
                    return False
                if not self.execute(node):
                    return False
            return True
        finally:
            with self.mutex:
                self.active['B0'] -= 1
                self.events.append(dict(group='B0', day=day, event='END', phase=self.phase,
                                        active=self.active['B0'], elapsed_s=time.monotonic()-self.live.started))

    def phase_queue(self, phase):
        self.phase = phase
        stages = ('B0_PLANNING', 'PLANNING_FREEZE') if phase == 'PLANNING' else ('ACTUAL', 'FRESH_AC', 'VALIDATION_FREEZE')
        while True:
            pending = [day for day in self.ledger.plan['days'] if any(self.ledger.state['stages'][f'B0/{day}/{s}']['status']
                not in ('PASS', 'FAIL', 'BLOCKED') for s in stages) and not any(
                    self.ledger.state['stages'][f'B0/{day}/{s}']['status'] in ('FAIL', 'BLOCKED') for s in stages)]
            if not pending:
                break
            self.scheduled_days.extend(('B0', d) for d in pending)
            with ThreadPoolExecutor(max_workers=self.selected_workers, thread_name_prefix=f'B0_{phase}') as pool:
                list(pool.map(lambda day: self.day('B0', day), pending))
            self.peak_solver_slots = max(self.peak_solver_slots, self.resources.peak)
            if not self.stop.is_set():
                break
            reason = self.resources.stopped or 'NATIVE_RESOURCE_FAILURE'
            event = dict(from_workers=self.selected_workers, to_workers=max(1, self.selected_workers-1),
                         reason=reason, measured=copy.deepcopy(self.live.samples[-1]))
            self.live.guard_events.append(event)
            if self.selected_workers == 1:
                break
            self.selected_workers -= 1
            self.downgrades.append(event)
            # Wait for current hard conditions to recover; never use an old 8-GiB gate.
            while True:
                resources = Resources(self.config, self.live.get)
                try:
                    resources.admit()
                    break
                except ResourceStop:
                    time.sleep(1)
            self.resources = resources
            self.stop.clear()

    def run(self):
        self.ledger.state['campaign_status'] = 'RUNNING'
        self.ledger.save()
        started = time.monotonic()
        try:
            self.phase_queue('PLANNING')
            freezes = [self.ledger.state['stages'][f'B0/{d}/PLANNING_FREEZE']['status'] for d in self.ledger.plan['days']]
            if all(s == 'PASS' for s in freezes):
                self.adapter.truth(self.resources)
                self.phase_queue('ACTUAL')
        finally:
            for sid, row in self.ledger.state['stages'].items():
                if row['status'] == 'RUNNING':
                    self.ledger.transition(sid, 'INTERRUPTED', failure_reason='COORDINATOR_END_WITH_UNFINISHED_STAGE')
                elif row['status'] in ('NOT_RUN', 'READY'):
                    self.ledger.transition(sid, 'BLOCKED', failure_reason='B0_CAMPAIGN_HARD_STOP_OR_REQUIRED_DEPENDENCY')
            status = 'PASS' if all(r['status'] == 'PASS' for r in self.ledger.state['stages'].values()) else (
                'INTERRUPTED' if any(r['status'] == 'INTERRUPTED' for r in self.ledger.state['stages'].values()) else 'BLOCKED')
            self.ledger.state['campaign_status'] = status
            self.ledger.save()
            atomic(self.ledger.root / 'EXECUTION_RECEIPT.json', dict(run_id=self.adapter.authority['run_id'],
                wall_seconds=time.monotonic()-started, selected_workers=self.selected_workers,
                peak_day_workers=dict(self.peak_days), events=self.events, downgrades=self.downgrades,
                admission_pauses=self.admission_pauses, native_calls=self.adapter.native_calls,
                global_solver_peak=max(self.peak_solver_slots, self.resources.peak), production_calls=self.ledger.state['production_calls'],
                AUTO_ADVANCE_TO_B1=False, STOP_AFTER_B0=True))
        return self.ledger.summary()


def run(root):
    root = Path(root).resolve()
    authority = read(root / 'AUTHORITY.json')
    config = B0Config(**authority['config'])
    config.authorize('B0')
    # Frozen execution-source and input bytes are checked before any day admission.
    for row in authority['source_files']:
        if not Path(row['path']).is_file() or file_sha(row['path']) != row['sha256']:
            raise PermissionError('Frozen source/input identity failure: ' + row['path'])
    live = LiveTelemetry(root, config)
    live.start()
    try:
        with B0Ledger(root, b0_plan(), authority) as ledger:
            adapter = B0Adapter(ledger, authority, live)
            scheduler = B0Scheduler(ledger, config, adapter, live)
            summary = scheduler.run()
    finally:
        live.close()
        atomic(root / 'B0_RESOURCE_SUMMARY.json', live.summary())
    print(json.dumps(summary))
    return summary

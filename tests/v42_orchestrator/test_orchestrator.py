"""Bounded sleep-only tests. No production or native scientific imports."""
import copy
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from dataclasses import asdict, replace
from pathlib import Path

from v42_campaign.authority import digest
from v42_orchestrator.config import Config
from v42_orchestrator.dag import build_dag, load_dates, planning_inputs, select_results
from v42_orchestrator.ledger import Ledger, atomic, TRANSITIONS
from v42_orchestrator.mock import MockAdapter, ScientificFailure, TransientFailure, WorkerCrash
from v42_orchestrator.resources import Resources, ResourceStop, Telemetry
from v42_orchestrator.scheduler import Scheduler

EVIDENCE = {}
INPUT = digest('synthetic input only')


def synthetic_pass(ledger, node):
    if ledger.begin(node['id'], 'fixture'):
        phase = 'PLANNING' if node['planning'] or node['stage'] == 'PLANNING_FREEZE' else node['stage']
        ledger.finish(node['id'], dict(producer_phase=phase, synthetic_only=True, id=node['id']))


class OrchestratorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.days = load_dates()
        self.plan = build_dag(fixture_days=self.days[:4])

    def tearDown(self):
        self.temp.cleanup()

    def ledger(self, plan=None, **kwargs):
        return Ledger(self.root, plan or self.plan, input_sha=kwargs.pop('input_sha', INPUT), **kwargs)

    def test_dates_and_stage_count(self):
        plan = build_dag()
        self.assertEqual(len(plan['days']), 31)
        self.assertEqual(len(plan['nodes']), 3 * 31 * 5 + 4 * 31 * 8 + 1)
        self.assertEqual(len({n['artifact_destination'] for n in plan['nodes']}), 1458)
        self.assertTrue(all(n['execution_status'] == 'NOT_RUN' for n in plan['nodes']))
        self.assertEqual(plan['nodes'][0]['stage'], 'B0_PLANNING')
        for arm, stages in [('B0', ['B0_PLANNING']), ('B1', ['A1']), ('B2', ['M1']),
                            ('B3_L1', ['A1', 'M1', 'A2', 'M2'])]:
            self.assertEqual([n['stage'] for n in plan['nodes'] if n['group'] == arm and
                              n['day'] == self.days[0] and n['planning']], stages)
        for days in [list(reversed(self.days)), self.days[:-1], [self.days[0]] * 31]:
            path = self.root / 'invalid_dates.json'
            atomic(path, dict(days=list(days)))
            with self.assertRaises(ValueError):
                load_dates(path)

    def test_resource_config_and_environment(self):
        previous = os.environ.get('B2_INNER_PRICING')
        os.environ['B2_INNER_PRICING'] = '16'
        try:
            self.assertEqual(Config().B2_INNER_PRICING, 1)
        finally:
            if previous is None:
                del os.environ['B2_INNER_PRICING']
            else:
                os.environ['B2_INNER_PRICING'] = previous
        for values in [dict(B3_DAY_WORKERS=4), dict(B2_INNER_PRICING=4), dict(GUROBI_THREADS=4),
                       dict(GLOBAL_SOLVER_SLOTS=0), dict(RAM_FLOOR_GIB=.5), dict(MAX_TRANSIENT_RETRIES=-1)]:
            with self.assertRaises(ValueError):
                Config(**values)
        self.assertEqual(Config(GLOBAL_SOLVER_SLOTS=2).GLOBAL_SOLVER_SLOTS, 2)

    def test_mock_concurrency_and_no_oversubscription(self):
        config = Config()
        backend = MockAdapter(delay=.05, synchronize_B2_workers=4)
        with self.ledger() as ledger:
            scheduler = Scheduler(ledger, config, adapter=backend)
            summary = scheduler.run()
            self.assertEqual(summary['campaign_status'], 'PASS')
            self.assertEqual(dict(scheduler.peak_days), dict(B0=4, B1=1, B2=4, B3=1))
            self.assertLessEqual(scheduler.resources.peak, 4)
            self.assertEqual(scheduler.resources.active, 0)
            for group in self.plan['main_order'] + self.plan['convergence_order']:
                starts = [e['day'] for e in scheduler.events if e['group'] == group and e['event'] == 'START']
                self.assertEqual(set(starts), set(self.days[:4]))
            acquired = [e for e in scheduler.resources.events if e['action'] == 'acquire']
            b2 = [e for e in acquired if e['owner'].startswith('B2/')]
            b3 = [e for e in acquired if e['owner'].startswith('B3_') and '/M' in e['owner']]
            self.assertEqual(len(b2), 4)
            self.assertEqual({e['owner'].rsplit('pricing', 1)[1] for e in b2}, {'0'})
            self.assertEqual({e['owner'].rsplit('pricing', 1)[1] for e in b3}, {'0', '1', '2', '3'})
            self.assertEqual(max(e['active'] for e in b2), 4)
            self.assertEqual(max(e['active'] for e in b3), 4)
            # Each arm/loop barrier precedes all starts in the next group.
            order = self.plan['main_order'] + self.plan['convergence_order']
            for a, b in zip(order, order[1:]):
                last_a = max(i for i, e in enumerate(scheduler.events) if e['group'] == a)
                first_b = min(i for i, e in enumerate(scheduler.events) if e['group'] == b)
                self.assertLess(last_a, first_b)
            EVIDENCE['MAY_MOCK_CONCURRENCY_TEST.json'] = dict(PASS=True, fixture_days=4,
                peak_day_workers=dict(scheduler.peak_days), dynamic_queue=True, arm_overlap=False,
                mock_stage_calls=len(backend.calls), all_stages_pass=True)
            EVIDENCE['MAY_NO_OVERSUBSCRIPTION_TEST.json'] = dict(PASS=True,
                B2_peak_global_slots=max(e['active'] for e in b2), B2_inner_tasks_per_day=1,
                B3_peak_global_slots=max(e['active'] for e in b3), B3_inner_tasks_per_M_stage=4,
                global_peak=scheduler.resources.peak, slots_released=True, nested_16_way=False)

    def test_reduced_global_capacity(self):
        config = Config(GLOBAL_SOLVER_SLOTS=2)
        plan = build_dag(config, fixture_days=self.days[:2])
        with self.ledger(plan) as ledger:
            scheduler = Scheduler(ledger, config, adapter=MockAdapter(delay=.001))
            self.assertEqual(scheduler.run()['campaign_status'], 'PASS')
            self.assertLessEqual(scheduler.resources.peak, 2)

    def test_firewall_and_convergence_detector(self):
        backend = MockAdapter(delay=0, detection=('a', 'b', 'a', 'a'))
        plan = build_dag(fixture_days=self.days[:1])
        with self.ledger(plan) as ledger:
            self.assertEqual(Scheduler(ledger, adapter=backend).run()['campaign_status'], 'PASS')
            for loop in range(1, 5):
                self.assertIn(f'B3_L{loop}/{self.days[0]}/M2', backend.calls)
            self.assertTrue(ledger.read_receipt(f'B3_L3/{self.days[0]}/PLANNING_FREEZE')['payload']['detector']['TWO_CYCLE'])
            self.assertTrue(ledger.read_receipt(f'B3_L4/{self.days[0]}/PLANNING_FREEZE')['payload']['detector']['EXACT_FIXED_POINT'])
            for node in plan['nodes']:
                if node['planning'] or node['stage'] == 'PLANNING_FREEZE':
                    inputs = backend.contexts[node['id']]
                    self.assertEqual(set(inputs), set(node['Planning_dependencies']))
                    self.assertTrue(all(p['producer_phase'] == 'PLANNING' for p in inputs.values()))
                    forged = dict(inputs, ACTUAL=dict(producer_phase='ACTUAL'))
                    with self.assertRaises(PermissionError):
                        planning_inputs(node, forged)
                    if inputs:
                        bad = copy.deepcopy(inputs)
                        bad[next(iter(bad))]['producer_phase'] = 'ACTUAL'
                        with self.assertRaises(PermissionError):
                            planning_inputs(node, bad)
            next_node = ledger.nodes[f'B3_L2/{self.days[0]}/A1']
            before = ledger.input_digest(next_node['id'])
            ledger.state['stages'][f'B3_L1/{self.days[0]}/ACTUAL']['output_sha'] = digest('poisoned Actual')
            self.assertEqual(ledger.input_digest(next_node['id']), before)
            for node in plan['nodes']:
                if node['stage'] == 'M2':
                    self.assertEqual(set(node['free_decisions']),
                        {'MESS.route', 'MESS.movement', 'MESS.P', 'MESS.Q', 'MESS.SOC'})
            EVIDENCE['MAY_PLANNING_ACTUAL_FIREWALL_TEST.json'] = dict(PASS=True,
                declared_planning_only=True, adversarial_Actual_inputs_rejected=True,
                Actual_SHA_does_not_change_next_Planning_SHA=True, M2_all_MESS_decisions_free=True,
                fixed_point_and_two_cycle_observed_mock=True, L4_completed=True,
                scope='Mock broker and DAG data provenance; future native adapters require audited I/O')

    def test_main_result_selection_and_barrier(self):
        results = {g: {'label': g} for g in self.plan['main_order'] + self.plan['convergence_order']}
        self.assertEqual(list(select_results(results)), ['B0', 'B1', 'B2', 'B3_L1'])
        self.assertEqual(list(select_results(results, convergence=True)), ['B3_L2', 'B3_L3', 'B3_L4'])
        with self.assertRaises(ValueError):
            select_results({'B3_L4': 'cannot substitute for L1'})
        node = next(n for n in self.plan['nodes'] if n['group'] == 'B3_L2')
        with self.ledger() as ledger:
            with self.assertRaises(ValueError):
                ledger.begin(node['id'], 'illegal')
        self.assertEqual(node['control_dependencies'], ['MAIN_MAY_CAMPAIGN_COMPLETE'])
        self.assertTrue(all(n['arm'] == 'B3' for n in self.plan['nodes'] if n['phase'] == 'CONVERGENCE'))
        EVIDENCE['MAY_MAIN_VS_CONVERGENCE_RESULT_TEST.json'] = dict(PASS=True,
            main=list(select_results(results)), convergence=list(select_results(results, convergence=True)),
            L2_blocked_before_main_complete=True, B0_B1_B2_not_repeated=True)

    def test_partial_31_day_resume(self):
        plan = build_dag()
        with self.ledger(plan) as ledger:
            for node in plan['nodes']:
                if node['group'] == 'B0' and node['day'] in self.days[:8]:
                    synthetic_pass(ledger, node)
            for day in self.days[8:10]:
                ledger.begin(f'B0/{day}/B0_PLANNING', 'lost-worker')
            ledger.transition(f'B0/{self.days[9]}/B0_PLANNING', 'INTERRUPTED')
            pass_paths = {sid: ledger.receipt_path(sid).read_bytes() for sid, row in ledger.state['stages'].items()
                          if row['status'] == 'PASS'}
        with self.ledger(plan) as resumed:
            pending = Scheduler(resumed).pending_days('B0')
            self.assertEqual(pending, list(self.days[8:]))
            self.assertEqual(resumed.state['stages'][f'B0/{self.days[8]}/B0_PLANNING']['status'], 'READY')
            for sid, content in pass_paths.items():
                self.assertEqual(resumed.receipt_path(sid).read_bytes(), content)
            for node in plan['nodes']:
                if node['group'] == 'B0' and node['day'] in self.days[8:]:
                    synthetic_pass(resumed, node)
            b1 = f'B1/{self.days[0]}/A1'
            self.assertTrue(resumed.begin(b1, 'fixture'))
            resumed.transition(b1, 'INTERRUPTED')
        EVIDENCE['partial_resume'] = dict(days_1_to_8_preserved=True, unfinished_days=pending,
            orphan_RUNNING_to_INTERRUPTED_to_READY=True, all_B0_PASS_unlocks_B1=True)

    def test_idempotent_rerun_and_stale_identity(self):
        plan = build_dag(fixture_days=self.days[:1])
        backend = MockAdapter(delay=0)
        with self.ledger(plan) as ledger:
            Scheduler(ledger, adapter=backend).run()
            artifacts = {sid: ledger.receipt_path(sid).read_bytes() for sid in ledger.nodes}
        replay = MockAdapter(delay=0)
        with self.ledger(plan) as ledger:
            self.assertEqual(Scheduler(ledger, adapter=replay).run()['campaign_status'], 'PASS')
            self.assertEqual(replay.calls, [])
            for sid, content in artifacts.items():
                self.assertEqual(ledger.receipt_path(sid).read_bytes(), content)
        with self.ledger(plan, input_sha=digest('changed input')) as ledger:
            self.assertTrue(all(r['status'] == 'NOT_RUN' for r in ledger.state['stages'].values()))
            self.assertEqual(Scheduler(ledger, adapter=MockAdapter(delay=0)).run()['campaign_status'], 'PASS')
        with self.ledger(plan, input_sha=digest('changed input'), stage_version='changed-v2') as ledger:
            self.assertTrue(all(r['status'] == 'NOT_RUN' for r in ledger.state['stages'].values()))
        EVIDENCE['MAY_IDEMPOTENCY_TEST.json'] = dict(PASS=True, rerun_mock_calls=0,
            accepted_artifact_bytes_preserved=True, input_SHA_change_invalidates=True,
            stage_version_change_invalidates=True)

    def test_corrupt_receipt_and_descendants_invalidate(self):
        plan = build_dag(fixture_days=self.days[:1])
        with self.ledger(plan) as ledger:
            Scheduler(ledger, adapter=MockAdapter(delay=0)).run()
            sid = f'B0/{self.days[0]}/ACTUAL'
            ledger.receipt_path(sid).write_text('{broken', encoding='utf8')
        with self.ledger(plan) as ledger:
            self.assertEqual(ledger.state['stages'][sid]['status'], 'NOT_RUN')
            self.assertEqual(ledger.state['stages'][f'B1/{self.days[0]}/A1']['status'], 'NOT_RUN')
            self.assertEqual(ledger.state['stages'][f'B0/{self.days[0]}/PLANNING_FREEZE']['status'], 'PASS')
            self.assertEqual(Scheduler(ledger, adapter=MockAdapter(delay=0)).run()['campaign_status'], 'PASS')
            self.assertEqual(len(list((self.root / 'quarantine').glob('*.json'))), 1)

    def test_crash_between_publication_and_checkpoint(self):
        sid = self.plan['nodes'][0]['id']
        with self.ledger() as ledger:
            ledger.begin(sid, 'crashed-worker')
            ledger.publish(sid, dict(producer_phase='PLANNING', synthetic_only=True))
            accepted = ledger.receipt_path(sid).read_bytes()
        with self.ledger() as ledger:
            self.assertEqual(ledger.state['stages'][sid]['status'], 'PASS')
            self.assertFalse(ledger.begin(sid, 'restart'))
            self.assertEqual(ledger.receipt_path(sid).read_bytes(), accepted)
        EVIDENCE['publication_crash'] = dict(valid_receipt_reconciled_to_PASS=True, duplicate_publication=False)

    def test_actual_coordinator_process_death_and_machine_restart(self):
        code = "\n".join([
            'import os,sys',
            'from v42_orchestrator.dag import build_dag,load_dates',
            'from v42_orchestrator.ledger import Ledger',
            f'l=Ledger(sys.argv[1],build_dag(fixture_days=load_dates()[:4]),input_sha={INPUT!r})',
            "l.begin(l.plan['nodes'][0]['id'],'terminated-coordinator')",
            'os._exit(23)',
        ])
        result = subprocess.run([sys.executable, '-c', code, str(self.root)], capture_output=True)
        self.assertEqual(result.returncode, 23, result.stderr)
        with self.ledger() as ledger:
            self.assertEqual(ledger.state['stages'][self.plan['nodes'][0]['id']]['status'], 'READY')
            self.assertEqual(Scheduler(ledger, adapter=MockAdapter(delay=0)).run()['campaign_status'], 'PASS')
        EVIDENCE['process_death'] = dict(child_exit_code=23, OS_lock_released=True,
            persisted_checkpoint_loaded_in_new_process=True, restart_completed=True,
            machine_restart_simulation='Fresh process and discarded in-memory worker/token state')

    def test_worker_crash_and_restart(self):
        sid = self.plan['nodes'][0]['id']
        with self.ledger() as ledger:
            scheduler = Scheduler(ledger, adapter=MockAdapter(failures={sid: WorkerCrash('worker crash')}))
            with self.assertRaises(WorkerCrash):
                scheduler.run()
            self.assertEqual(ledger.state['stages'][sid]['status'], 'INTERRUPTED')
            self.assertEqual(scheduler.resources.active, 0)
        with self.ledger() as ledger:
            self.assertEqual(Scheduler(ledger, adapter=MockAdapter(delay=0)).run()['campaign_status'], 'PASS')
        EVIDENCE['worker_crash'] = dict(interrupted=True, restart_completed=True, tokens_released=True)

    def test_state_machine_and_coordinator_exclusion(self):
        with self.ledger() as ledger:
            with self.assertRaises(ValueError):
                ledger.transition(self.plan['nodes'][0]['id'], 'PASS')
            with self.assertRaises(RuntimeError):
                self.ledger()
            self.assertEqual(set(TRANSITIONS), {'NOT_RUN', 'READY', 'RUNNING', 'PASS', 'FAIL', 'INTERRUPTED', 'BLOCKED'})

    def test_checkpoint_schema_matches_real_state(self):
        from datetime import datetime
        schema_path = Path(__file__).resolve().parents[2] / 'docs/v42_may_campaign_orchestrator/MAY_CHECKPOINT_SCHEMA.json'
        schema = json.loads(schema_path.read_text(encoding='utf8'))
        with self.ledger() as ledger:
            synthetic_pass(ledger, self.plan['nodes'][0])
            self.assertEqual(set(ledger.state), set(schema['required']))
            self.assertEqual(ledger.state['schema_version'], schema['properties']['schema_version']['const'])
            self.assertEqual(ledger.state['production_calls'], schema['properties']['production_calls']['const'])
            self.assertEqual(set(ledger.state['identity']), set(schema['$defs']['identity']['required']))
            stage = schema['$defs']['stage']
            for row in ledger.state['stages'].values():
                self.assertTrue(set(stage['required']) <= set(row) <= set(stage['properties']))
                self.assertIn(row['status'], stage['properties']['status']['enum'])
                self.assertIn(row['arm'], stage['properties']['arm']['enum'])
                self.assertIn(row['loop'], stage['properties']['loop']['enum'])
                self.assertIsInstance(row['retry_count'], int)
                self.assertTrue(0 <= row['retry_count'] <= 10)
                for key in ('scientific_sha', 'input_sha', 'output_sha', 'receipt_sha'):
                    if row.get(key) is not None:
                        self.assertRegex(row[key], schema['$defs']['sha']['pattern'])
                for value in row['timestamps'].values():
                    self.assertIsNotNone(datetime.fromisoformat(value).tzinfo)

    def test_fixed_point_before_L4_does_not_stop(self):
        plan = build_dag(fixture_days=self.days[:1])
        with self.ledger(plan) as ledger:
            backend = MockAdapter(delay=0, detection=('a', 'a', 'a', 'a'))
            self.assertEqual(Scheduler(ledger, adapter=backend).run()['campaign_status'], 'PASS')
            self.assertTrue(ledger.read_receipt(f'B3_L2/{self.days[0]}/PLANNING_FREEZE')['payload']['detector']['EXACT_FIXED_POINT'])
            self.assertIn(f'B3_L4/{self.days[0]}/VALIDATION_FREEZE', backend.calls)

    def test_scientific_SHA_change_and_receipt_identity_fields(self):
        sid = self.plan['nodes'][0]['id']
        with self.ledger() as ledger:
            synthetic_pass(ledger, self.plan['nodes'][0])
            expected = ledger.expected(sid)
            self.assertEqual(expected['day'], self.days[0])
            self.assertEqual(expected['arm'], 'B0')
            self.assertIsNone(expected['loop'])
            self.assertEqual(expected['stage'], 'B0_PLANNING')
            path = ledger.receipt_path(sid)
            original = json.loads(path.read_text(encoding='utf8'))
            for key in ['scientific_sha', 'input_sha', 'stage_version', 'day', 'arm', 'loop']:
                corrupt = copy.deepcopy(original)
                corrupt['identity'][key] = 'different'
                atomic(path, corrupt)
                self.assertIsNone(ledger.read_receipt(sid))
            atomic(path, original)
        changed = copy.deepcopy(self.plan)
        changed['scientific_sha'] = digest('future accepted scientific authority')
        with self.ledger(changed) as ledger:
            self.assertTrue(all(r['status'] == 'NOT_RUN' for r in ledger.state['stages'].values()))
            synthetic_pass(ledger, changed['nodes'][0])

    def test_atomic_replace_retries_without_truncation(self):
        from unittest.mock import patch
        import v42_orchestrator.ledger as module
        original_replace = module.os.replace
        path = self.root / 'atomic.json'
        atomic(path, {'old': True})
        calls = []
        def intermittent(source, target):
            calls.append(1)
            if len(calls) <= 2:
                self.assertEqual(json.loads(path.read_text()), {'old': True})
                raise PermissionError('mock Windows sharing denial')
            return original_replace(source, target)
        with patch.object(module.os, 'replace', side_effect=intermittent):
            atomic(path, {'new': True})
        self.assertEqual(len(calls), 3)
        self.assertEqual(json.loads(path.read_text()), {'new': True})

    def test_scientific_failure_blocks_required_downstream(self):
        sid = self.plan['nodes'][0]['id']
        with self.ledger() as ledger:
            backend = MockAdapter(delay=0, failures={sid: ScientificFailure('certificate fail')})
            self.assertEqual(Scheduler(ledger, adapter=backend).run()['campaign_status'], 'BLOCKED')
            self.assertEqual(backend.calls.count(sid), 1)
            self.assertEqual(ledger.state['stages'][sid]['status'], 'FAIL')
            self.assertTrue(all(r['status'] == 'BLOCKED' for key, r in ledger.state['stages'].items()
                                if key.startswith('B1/')))

    def test_retry_is_bounded_and_explicit(self):
        sid = self.plan['nodes'][0]['id']
        with self.ledger() as ledger:
            backend = MockAdapter(delay=0, failures={sid: TransientFailure('temporary filesystem error')})
            self.assertEqual(Scheduler(ledger, adapter=backend).run()['campaign_status'], 'PASS')
            self.assertEqual(backend.calls.count(sid), 2)
            self.assertEqual(ledger.state['stages'][sid]['retry_count'], 1)
        other = self.root / 'no_retry'
        with Ledger(other, self.plan, input_sha=INPUT) as ledger:
            config = Config(MAX_TRANSIENT_RETRIES=0)
            backend = MockAdapter(delay=0, failures={sid: TransientFailure('temporary error')})
            self.assertEqual(Scheduler(ledger, config, adapter=backend).run()['campaign_status'], 'BLOCKED')
            self.assertEqual(backend.calls.count(sid), 1)

    def test_memory_admission_and_active_stop(self):
        for telemetry in [Telemetry(available_gib=.99), Telemetry(commit_percent=95), Telemetry(oom=True),
                          Telemetry(sustained_catastrophic_paging=True), Telemetry(solver_failure=True),
                          Telemetry(license_failure=True), Telemetry(available_gib=float('nan'))]:
            with self.subTest(telemetry=telemetry):
                resources = Resources(telemetry=lambda: telemetry)
                with self.assertRaises(ResourceStop):
                    with resources.solve_slot('blocked'):
                        self.fail('Unsafe solve admitted')
                self.assertEqual(resources.active, 0)
        state = [Telemetry(available_gib=1)]
        resources = Resources(telemetry=lambda: state[0])
        with self.assertRaises(ResourceStop):
            with resources.solve_slot('active'):
                state[0] = Telemetry(commit_percent=96)
        self.assertEqual(resources.active, 0)
        with self.ledger() as ledger:
            scheduler = Scheduler(ledger, resources=Resources(telemetry=lambda: Telemetry(oom=True)))
            self.assertEqual(scheduler.run()['campaign_status'], 'INTERRUPTED')
            self.assertFalse(any(r['status'] == 'PASS' for r in ledger.state['stages'].values()))
        EVIDENCE['memory_admission'] = dict(mock_only=True, one_GiB_boundary_accepted=True,
            RAM_OOM_commit_paging_solver_license_and_unknown_guard_PASS=True,
            active_guard_releases_tokens=True, unsafe_campaign_interrupted=True)

    def test_production_guard_and_no_execution(self):
        for config in [Config(), Config(ENABLE_PRODUCTION=True)]:
            with self.assertRaises(PermissionError):
                config.production_guard()
            with self.ledger() as ledger:
                with self.assertRaises(PermissionError):
                    Scheduler(ledger, config, adapter=lambda: self.fail('production called'))
        self.assertFalse(any(name.startswith(('gurobipy', 'opendssdirect', 'dss')) for name in sys.modules))
        EVIDENCE['MAY_PRODUCTION_GUARD_TEST.json'] = dict(PASS=True,
            ENABLE_PRODUCTION_DEFAULT=False, arbitrary_adapter_rejected=True,
            enable_true_still_requires_future_adapter=True, native_modules_imported=False)

    def test_checkpoint_rejects_wrong_day_retry_and_production(self):
        with self.ledger() as ledger:
            saved = copy.deepcopy(ledger.state)
        corruptions = [lambda value: value['production_calls'].update(optimizer=1),
                       lambda value: value['stages'][self.plan['nodes'][0]['id']].update(day='2025-05-02'),
                       lambda value: value['stages'][self.plan['nodes'][0]['id']].update(retry_count=-1)]
        for corrupt in corruptions:
            invalid = copy.deepcopy(saved)
            corrupt(invalid)
            atomic(self.root / 'CAMPAIGN_STATE.json', invalid)
            with self.assertRaises(ValueError):
                self.ledger()
        atomic(self.root / 'CAMPAIGN_STATE.json', saved)

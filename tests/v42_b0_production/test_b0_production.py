"""No native scientific calls: authorization, DAG, receipt and telemetry gates."""
import ast
import copy
import inspect
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from v42_campaign.authority import digest
from v42_orchestrator.ledger import atomic
from v42_orchestrator.config import Config
from v42_b0_production.config import B0Config, explicit_config, STAGES
from v42_b0_production.authority import b0_plan, load_dates
from v42_b0_production.execution import B0Ledger, B0Scheduler, B0Adapter
from v42_b0_production.telemetry import is_heavy_command
from v42_b0_production.worker import all_planning_frozen


class ProductionGates(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.plan = b0_plan()
        self.authority = dict(run_id='UNIT_ONLY', input_sha=digest('test input'), checker_SHA=digest('checker'),
                              days=list(load_dates()), config=explicit_config().__dict__)

    def tearDown(self):
        self.temp.cleanup()

    def test_defaults_and_scope_guards(self):
        with self.assertRaises(PermissionError):
            B0Config().authorize('B0')
        with self.assertRaises(PermissionError):
            Config(ENABLE_PRODUCTION=True).production_guard()
        config = explicit_config()
        config.authorize('B0')
        for arm in ('B1', 'B2', 'B3'):
            with self.assertRaises(PermissionError):
                config.authorize(arm)
        for stage in ('A1', 'M1', 'A2', 'M2', 'MAIN_COMPLETE'):
            with self.assertRaises(PermissionError):
                config.authorize('B0', stage)
        for value in ('ENABLE_B1_PRODUCTION', 'ENABLE_B2_PRODUCTION', 'ENABLE_B3_PRODUCTION', 'AUTO_ADVANCE_TO_B1'):
            with self.assertRaises(ValueError):
                replace(config, **{value: True})

    def test_full_B0_only_DAG_and_global_freeze(self):
        self.assertEqual(len(self.plan['nodes']), 155)
        self.assertEqual(self.plan['main_order'], ['B0'])
        self.assertEqual(self.plan['convergence_order'], [])
        self.assertFalse(self.plan['AUTO_ADVANCE_TO_B1'])
        for day in self.plan['days']:
            nodes = [n for n in self.plan['nodes'] if n['day'] == day]
            self.assertEqual(tuple(n['stage'] for n in nodes), STAGES)
            self.assertEqual(len(nodes[2]['required_pass']), 31)
            self.assertTrue(all(s.endswith('/PLANNING_FREEZE') for s in nodes[2]['required_pass']))
        self.assertEqual(len({n['artifact_destination'] for n in self.plan['nodes']}), 155)

    def test_production_mode_cannot_reuse_mock_or_other_arm(self):
        from v42_orchestrator.ledger import Ledger
        with Ledger(self.root, self.plan, input_sha=self.authority['input_sha']):
            pass
        with self.assertRaises(PermissionError):
            B0Ledger(self.root, self.plan, self.authority)
        invalid = copy.deepcopy(self.plan)
        invalid['nodes'][0]['arm'] = 'B1'
        with self.assertRaises(PermissionError):
            B0Ledger(self.root, invalid, self.authority)

    def test_production_receipt_rejects_synthetic(self):
        with B0Ledger(self.root, self.plan, self.authority) as ledger:
            node = self.plan['nodes'][0]
            ledger.begin(node['id'], 'unit-test')
            with self.assertRaises(ValueError):
                ledger.publish(node['id'], dict(producer_phase='PLANNING', synthetic_only=True))
            self.assertFalse(ledger.validate_counters(dict(optimizer=0, Actual=0, Fresh_AC=0, B1=1)))

    def test_Actual_truth_waits_for_all_new_freezes(self):
        atomic(self.root / 'CAMPAIGN_STATE.json', dict(identity={'mode': 'MOCK_ONLY'}, stages={}))
        with self.assertRaises(PermissionError):
            all_planning_frozen(self.root, self.authority)
        atomic(self.root / 'CAMPAIGN_STATE.json', dict(identity={'mode': 'B0_PRODUCTION'},
              stages={f'B0/{d}/PLANNING_FREEZE': dict(status='NOT_RUN') for d in self.plan['days']}))
        with self.assertRaises(PermissionError):
            all_planning_frozen(self.root, self.authority)

    def test_foreign_process_classifier_allows_nonheavy(self):
        self.assertFalse(is_heavy_command(['python', '-m', 'unittest'], 10*2**30, ['gurobi120.dll'], 10))
        self.assertFalse(is_heavy_command(['python', '-m', 'v42_arc_floor.finalize'], 2**30, ['gurobi120.dll'], 10))
        self.assertFalse(is_heavy_command(['python', '-m', 'v42_dw_accelerated.base'], 2**30, ['gurobi120.dll'], 10))
        self.assertTrue(is_heavy_command(['python', '-m', 'v42_dw_accelerated.run'], 2**30, ['gurobi120.dll'], 10))
        self.assertFalse(is_heavy_command(['python', '-m', 'v42_orchestrator', 'mock'], 2**30, [], 10))
        self.assertTrue(is_heavy_command(['python', '-m', 'v42_arc_floor.run'], 2**30, ['gurobi120.dll'], 10))
        self.assertFalse(is_heavy_command(['python', '-m', 'v42_arc_floor.run'], 2**30, ['gurobi120.dll'], 0))

    def test_native_slot_loop_science_is_not_edited(self):
        import v42_regcontrol.runner as source
        from v42_holdout.actual import adapted_day
        original = ast.parse(inspect.getsource(source.run_day))
        original_loop = next(n for n in ast.walk(original) if isinstance(n, ast.For) and ast.unparse(n.iter) == 'range(96)')
        adapted = adapted_day()
        self.assertIn('run_day', adapted.__name__)
        self.assertTrue(any(isinstance(n, ast.Call) and ast.unparse(n.func) == 'session.solve_next' for n in ast.walk(original_loop)))


if __name__ == '__main__':
    unittest.main()

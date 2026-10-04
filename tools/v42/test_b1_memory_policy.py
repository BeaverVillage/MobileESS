"""No solver calls: operational guard removal and original admission semantics."""
import importlib.util
from pathlib import Path
import threading
import tempfile
import hashlib
import json
from types import SimpleNamespace
import unittest

spec = importlib.util.spec_from_file_location('policy', Path(__file__).with_name('run_b1_without_memory_guard.py'))
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)


class PolicyTests(unittest.TestCase):
    def campaign(self, foreign):
        class Base:
            def enforce_guard(self, row):
                raise AssertionError('Original memory cancellation invoked')
        campaign = policy.policy_campaign(Base)()
        campaign.telemetry = SimpleNamespace(lock=threading.RLock(), samples=[dict(
            available_GiB=0, commit_percent=100, catastrophic_sustained_paging=True,
            foreign_heavy=foreign)])
        return campaign

    def test_memory_pressure_does_not_block_or_cancel(self):
        campaign = self.campaign([])
        self.assertEqual(campaign.resource_state(), 'SAFE')
        self.assertFalse(campaign.enforce_guard({'worker': {'PID': 123}}))

    def test_foreign_heavy_admission_remains(self):
        campaign = self.campaign([{'PID': 456}])
        self.assertEqual(campaign.resource_state(), 'WAIT_RESOURCE')
        self.assertFalse(campaign.enforce_guard({}))

    def test_policy_is_bound_to_run_and_exact_entrypoint(self):
        freeze = dict(run_id='B1_202505_test', scientific_SHA='science', Git_SHA='frozen')
        source = Path(policy.__file__).resolve()
        value = dict(run_id=freeze['run_id'], scientific_SHA=freeze['scientific_SHA'],
                     frozen_Git_SHA=freeze['Git_SHA'], memory_guard_enabled=False,
                     foreign_heavy_admission_enabled=True, entrypoint=str(source),
                     entrypoint_SHA256=hashlib.sha256(source.read_bytes()).hexdigest())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'B1_OPERATIONAL_POLICY.json'
            path.write_text(json.dumps(value), encoding='utf-8')
            self.assertEqual(policy.validate_policy(root, freeze), value)
            for key, wrong in [('run_id', 'another'), ('entrypoint_SHA256', 'drift'),
                               ('memory_guard_enabled', True)]:
                path.write_text(json.dumps(dict(value, **{key: wrong})), encoding='utf-8')
                with self.assertRaises(PermissionError):
                    policy.validate_policy(root, freeze)


if __name__ == '__main__':
    unittest.main()

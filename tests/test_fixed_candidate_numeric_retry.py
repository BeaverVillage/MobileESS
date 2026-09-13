"""Exercise retry control flow without importing frozen data or a solver license."""
import ast
from pathlib import Path
from types import SimpleNamespace
import time
import unittest


SOURCE = Path(__file__).resolve().parents[1] / 'dayahead/tools/run_v35r3e_r1_beam.py'
STALL = 'V35R3_FIXED_CERTIFICATE_STALLED:test'


class RetryTests(unittest.TestCase):
    def execute(self, outcomes):
        self.items, self.calls = [], []
        def build(**kwargs):
            model = SimpleNamespace(Params=SimpleNamespace(), resets=0, disposed=False)
            def reset():
                model.resets += 1
            def dispose():
                model.disposed = True
            model.reset, model.dispose = reset, dispose
            item = SimpleNamespace(model=model, added_line_states={(73, 11420)},
                                   added_voltage_states=set(),
                                   added_transformer_current_states=set(),
                                   added_transformer_kva_states=set())
            self.items.append(item)
            return item
        def solve(item, **kwargs):
            self.calls.append(item)
            outcome = outcomes[len(self.calls)-1]
            if outcome:
                raise RuntimeError(outcome)
            return {'rho': 0.8}, {'exact_optimality_certificate': True}
        tree = ast.parse(SOURCE.read_text(encoding='utf-8'))
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == '_solve_item')
        module = ast.Module(body=[ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0), function], type_ignores=[])
        ast.fix_missing_locations(module)
        ns = dict(time=time, build_fixed_candidate_model=build,
                  solve_fixed_candidate_certified=solve, _row=lambda *args: {})
        exec(compile(module, str(SOURCE), 'exec'), ns)
        return ns['_solve_item']('B2', object(), None, (), (), {}, {}, set(), set(), set(), set())

    def test_first_success_has_no_retry(self):
        result = self.execute([None])
        self.assertEqual(result[3]['attempts'], 1)
        self.assertEqual(self.items[0].model.resets, 0)

    def test_existing_retry_success_is_unchanged(self):
        result = self.execute([STALL, None])
        self.assertEqual(result[3]['attempts'], 2)
        self.assertEqual(self.items[1].model.resets, 0)

    def test_strict_retry_resets_same_model_and_preserves_cuts(self):
        result = self.execute([STALL, STALL, None])
        self.assertEqual(result[3]['attempts'], 3)
        self.assertIs(self.calls[1], self.calls[2])
        model = self.items[1].model
        self.assertEqual(model.resets, 1)
        for name in ('FeasibilityTol', 'OptimalityTol', 'IntFeasTol'):
            self.assertEqual(getattr(model.Params, name), 1e-9)
        self.assertEqual(result[4]['line'], {(73, 11420)})
        self.assertTrue(all(item.model.disposed for item in self.items))

    def test_unrelated_failure_does_not_retry(self):
        with self.assertRaisesRegex(RuntimeError, 'STATUS:3'):
            self.execute(['STATUS:3'])
        self.assertEqual(len(self.calls), 1)
        self.assertTrue(self.items[0].model.disposed)

    def test_unrelated_second_failure_does_not_strict_retry(self):
        with self.assertRaisesRegex(RuntimeError, 'ROUND_LIMIT'):
            self.execute([STALL, 'ROUND_LIMIT'])
        self.assertEqual(len(self.calls), 2)
        self.assertTrue(all(item.model.disposed for item in self.items))

    def test_strict_failure_propagates_and_disposes(self):
        with self.assertRaisesRegex(RuntimeError, 'CERTIFICATE_STALLED'):
            self.execute([STALL, STALL, STALL])
        self.assertEqual(len(self.calls), 3)
        self.assertTrue(all(item.model.disposed for item in self.items))


if __name__ == '__main__':
    unittest.main()

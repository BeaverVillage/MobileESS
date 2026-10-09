"""Stdlib-only tests. No original scientific module is imported or built."""
import ast
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import types
import unittest
from dataclasses import dataclass, asdict
from unittest.mock import patch

from ieee8500_v42_original.hold import ExecutionHold, STATUS, receipt
from ieee8500_v42_original.source_links import call_original, ENTRY_POINTS
from ieee8500_v42_original.__main__ import main
from v42_b3_joint.contracts import MESSDecision

ROOT = Path(__file__).resolve().parents[1]
BASE = '23c3643681e38c8b3cf16f2d02686a78c4570cc7'


def source(path, original=False):
    if original:
        return subprocess.check_output(['git', 'show', f'{BASE}:{path}'], cwd=ROOT).decode('utf8')
    return (ROOT / path).read_text(encoding='utf8')


def extracted(path, name, namespace, original=False):
    tree = ast.parse(source(path, original))
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
    exec(compile(ast.Module(body=[node], type_ignores=[]), path, 'exec'), namespace)
    return namespace[name]


def decision(n):
    rows = lambda slots, value: tuple((value,) * slots for _ in range(n))
    return dict(routes=(('STA01',),) * n, location=rows(96, 'STA01'),
                charge_p=rows(96, 0.), discharge_p=rows(96, 0.), q=rows(96, 0.),
                soc=rows(97, 1140.), move_energy=rows(96, 0.),
                initial_final_json=json.dumps({'initial': [], 'final': []}),
                variables_json=json.dumps({key: [] for key in
                                           ('movement', 'charge_mode', 'route', 'P', 'Q', 'SOC')}))


class HoldTests(unittest.TestCase):
    def test_all_original_calls_deny_before_import(self):
        with patch('ieee8500_v42_original.source_links.import_module', side_effect=AssertionError('IMPORT')) as loader:
            for component in (*ENTRY_POINTS, 'UNKNOWN', 'B0', 'WORKER', 'COORDINATOR'):
                with self.subTest(component=component), self.assertRaisesRegex(ExecutionHold, STATUS):
                    call_original(component)
            loader.assert_not_called()

    def test_environment_and_flags_cannot_release(self):
        with patch.dict(os.environ, {'IEEE8500_APPROVED': '1', 'IEEE123_CAMPAIGN_COMPLETED': '1'}):
            import ieee8500_v42_original.hold as hold
            with patch.object(hold, 'execution_authorized', True, create=True):
                with self.assertRaises(ExecutionHold):
                    hold.require_execution_approval('NATIVE_OPTIMIZE')

    def test_cli_has_no_execution_dispatch(self):
        for args in (['B0'], ['B1'], ['B2'], ['B3'], ['worker'], ['coordinator'], ['fresh']):
            with self.assertRaises(ExecutionHold):
                main(args)
        self.assertFalse(receipt()['automatic_resume'])

    def test_dss_constructors_gate_before_context_or_output(self):
        for path, name in (('ieee8500_v42/ac.py', 'IEEE8500AC'),
                           ('ieee8500_v42_balanced/engine.py', 'OriginalCase'),
                           ('ieee8500_v42_high/engine.py', 'HighEngine')):
            tree = ast.parse(source(path))
            cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == name)
            init = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == '__init__')
            self.assertIsInstance(init.body[0], ast.ImportFrom)
            self.assertEqual(init.body[0].module, 'ieee8500_v42_original.hold')
            self.assertEqual(init.body[1].value.func.id, 'require_execution_approval')
            namespace = {}
            exec(compile(ast.Module(body=[init], type_ignores=[]), path, 'exec'), namespace)
            # Every default argument exists before compilation; no DSS module is supplied.
            args = [object()] + [None] * (len(init.args.args) - 1)
            with self.assertRaises(ExecutionHold):
                namespace['__init__'](*args)

    def test_source_link_symbols_exist_without_imports(self):
        for module, symbol in ENTRY_POINTS.values():
            path = module.replace('.', '/') + '.py'
            tree = ast.parse(source(path))
            names = {n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
            self.assertIn(symbol, names, path)


class DTOTests(unittest.TestCase):
    def test_four_dto_serialization_unchanged_from_pr191(self):
        text = subprocess.check_output(['git', 'show',
            '40b6f94dcd80e470f93c73b7479fdd2d9d91c3f2:v42_b3_joint/contracts.py'], cwd=ROOT).decode('utf8')
        old = types.ModuleType('v42_b3_joint._four_contract_fixture')
        old.__package__ = 'v42_b3_joint'
        with patch.dict(sys.modules, {old.__name__: old}):
            exec(compile(text, 'PR191:contracts.py', 'exec'), vars(old))
            before, after = old.MESSDecision(**decision(4)), MESSDecision(**decision(4))
        self.assertEqual(before.to_dict(), after.to_dict())
        self.assertEqual(before.sha, after.sha)

    def test_six_dto_shapes_and_rejection(self):
        d = MESSDecision(**decision(6))
        self.assertEqual((len(d.soc), len(d.soc[0])), (6, 97))
        self.assertEqual((len(d.q), len(d.q[0])), (6, 96))
        broken = decision(6); broken['q'] = decision(4)['q']
        with self.assertRaises(ValueError):
            MESSDecision(**broken)


@dataclass(frozen=True)
class MockBattery:
    minimum: float
    maximum: float
    initial: float
    terminal: float
    p_limit: float
    pcs_kva: float
    eta_charge: float
    eta_discharge: float
    dt_hours: float = .25

    def validate(self):
        pass


@dataclass(frozen=True)
class MockArc:
    route_id: str
    source: str
    destination: str
    depart: int
    arrive: int
    connect: int
    energy_kwh: float
    authority_sha256: str


class MockPath:
    def __init__(self, value):
        self.value = value

    def is_file(self):
        return True

    def read_bytes(self):
        return self.value


class InputTests(unittest.TestCase):
    def loader(self, n, original=False):
        def require(condition, message):
            if not condition:
                raise ValueError(message)
        names = [f'{role}{i:02d}' for role in ('IDC', 'STA') for i in range(1, 13)]
        table = {'service_ids': names, 'routes': [dict(traffic_forecast_sha='b' * 64,
            origin_service_id='STA01', destination_service_id='STA02', departure_slot_15=0,
            travel_slots_15min=1, connection_ready_slots_15min=2, energy_safe_kwh=1.)]}
        raw = gzip.compress(json.dumps(table).encode(), mtime=0)
        digest = lambda v: hashlib.sha256(json.dumps(v, sort_keys=True).encode()).hexdigest()
        namespace = dict(Path=MockPath, require=require, sha=lambda p: hashlib.sha256(p.read_bytes()).hexdigest(),
            json=json, gzip=gzip, Battery=MockBattery, RouteArc=MockArc, asdict=asdict, digest=digest)
        from collections import Counter
        namespace['Counter'] = Counter
        bundle = dict(route_table=dict(path=raw, sha256=hashlib.sha256(raw).hexdigest()),
            traffic_forecast_sha='b' * 64, initial_MESS_sites={f'MESS{i:02d}': 'STA01' for i in range(1, n + 1)},
            battery=asdict(MockBattery(660, 1620, 1140, 1140, 450, 600, .95, .95)))
        function = extracted('v42_bootstrap/m1.py', 'native_inputs', namespace, original)
        return function(bundle)

    def test_four_loader_exact_mock_receipt_and_arcs(self):
        self.assertEqual(self.loader(4, original=True), self.loader(4))

    def test_six_loader_keeps_route_domain(self):
        four, six = self.loader(4), self.loader(6)
        self.assertEqual(four[0], six[0])
        self.assertEqual(four[2:4], six[2:4])
        self.assertEqual(len(six[1]), 6)
        with self.assertRaises(ValueError):
            self.loader(0)


class MockArray:
    def __init__(self, rows):
        self.rows = rows

    def __getitem__(self, key):
        return self.rows[key[0]][key[1]] if isinstance(key, tuple) else self.rows[key]

    def __setitem__(self, key, value):
        self.rows[key[0]][key[1]] = value

    def tolist(self):
        return self.rows


class MockNumpy:
    @staticmethod
    def zeros(shape):
        return MockArray([[0.] * shape[1] for _ in range(shape[0])])

    @staticmethod
    def zeros_like(array):
        return MockNumpy.zeros((len(array.rows), len(array.rows[0])))

    @staticmethod
    def asarray(rows):
        return rows

    @staticmethod
    def savez_compressed(*args, **kwargs):
        pass


class PlanSerializationTests(unittest.TestCase):
    def plan(self, n, original=False):
        initial = {f'MESS{i:02d}': 'STA01' for i in range(1, n + 1)}
        arcs = [('STA01', t, 'STA01', t + 1, None) for t in range(96)]
        values = {}
        for unit in initial:
            values.update({f'arc[{unit},{k}]': 1. for k in range(96)})
            values.update({f'SOC[{unit},{t}]': 1140. for t in range(97)})
            for family, value in (('Pch', 1.), ('Pdis', 2.), ('Q', -.5)):
                values.update({f'{family}[{unit},STA01,{t}]': value for t in range(96)})
        case = types.SimpleNamespace(lift=lambda point: point, original_d={'names': list(values)},
            graph=(['STA01'], initial, arcs, None, None), case_sha='a' * 64,
            bundle={'day': '2025-05-01'}, output=Path('MOCK_OUTPUT_NOT_WRITTEN'))
        function = extracted('v42_may_campaign_native90/m_stage.py', '_plan',
                             dict(np=MockNumpy, atomic=lambda *args: None), original)
        return function(case, list(values.values()))

    def test_four_plan_matches_original_serialization(self):
        self.assertEqual(self.plan(4, original=True), self.plan(4))

    def test_six_plan_preserves_each_existing_vehicle(self):
        four, six = self.plan(4), self.plan(6)
        self.assertEqual(len(six['unit_ids']), 6)
        for field in ('P_kw', 'Q_kvar', 'SOC_kwh', 'locations'):
            self.assertEqual([row[:4] for row in six[field]], four[field])
        self.assertEqual(len(six['SOC_kwh']), 97)

    def test_no_scientific_packages_imported_by_this_suite(self):
        self.assertFalse({'gurobipy', 'opendssdirect', 'numpy', 'scipy'} & set(sys.modules))


if __name__ == '__main__':
    unittest.main()

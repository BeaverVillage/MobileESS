"""Small marked source fixtures only; no solver, source model or grid imports."""
from copy import deepcopy
import ast
from dataclasses import dataclass
import hashlib
import math
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

from v42_b2_build_optimization.builder import (
    AdmittedSourceGateway, FakeSourceGateway, VersionedB2BuildPort, VERSION)
from v42_b2_build_optimization.build_runtime import BuildProfile, PHASES
from v42_b2_build_optimization.source_port import instrument_builder
from v42_b2_build_optimization.scalar_math import original_pcs_math_scope


FIXTURE_SOURCE = '''def build_case(payload, request, progress=None):
    from v42_bootstrap.m1 import native_inputs
    bundle = payload["bundle"]
    sites, initial, routes, battery, receipt = native_inputs(bundle)
    graph = (sites, initial, routes, battery, receipt)
    coefficients = np.asarray([[1., -2.], [3., 4.]], dtype=float)
    captured = []
    pcs = pcs_fixture()
    A = coefficients.copy()
    d = {"rhs": np.asarray([5., 6.]), "types": np.asarray(["B", "C"])}
    captured.append(A)
    compact = Compact(A, d)
    presolve = Presolve(compact.A, compact.d)
    B, e = presolve.run()
    try:
        proof = verify_transport(compact, presolve)
    except Exception:
        raise
    return SimpleNamespace(original_A=A, original_d=d, A=B, d=e, graph=graph,
        compact=compact, presolve=presolve, proof=proof, pcs_rows=pcs)
'''


@dataclass(frozen=True)
class FixtureRoute:
    source: str
    destination: str
    depart: int
    connect: int
    energy_kwh: float


@dataclass(frozen=True)
class FixtureBattery:
    capacity: float
    minimum: float


class FixtureCompact:
    def __init__(self, A, d):
        self.original_A = A
        self.A = A.copy()
        self.d = {key: value.copy() for key, value in d.items()}


class FixturePresolve:
    def __init__(self, A, d):
        self.A, self.d = A, d

    def run(self):
        return self.A.copy(), {key: value.copy() for key, value in self.d.items()}


class FixtureLinearExpression:
    def __init__(self, values):
        self.values = dict(values)

    def __rmul__(self, scalar):
        return FixtureLinearExpression({key: scalar * value for key, value in self.values.items()})

    def __add__(self, other):
        values = dict(self.values)
        for key, value in other.values.items():
            values[key] = values.get(key, 0.) + value
        return FixtureLinearExpression(values)

    def __le__(self, other):
        return (tuple((key, value.hex()) for key, value in sorted(self.values.items())),
            tuple((key, value.hex()) for key, value in sorted(other.values.items())))


class FixtureConstraintRecorder:
    def __init__(self):
        self.rows = []

    def addConstr(self, value, *, name):
        self.rows.append((name, value))


class B2BuildOptimizationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.route_file = self.root / "routes.json"
        self.route_file.write_bytes(b'{"routes":[["s1","s2",0,1]]}')
        self.source_file = self.root / "m_model.py"
        self.source_file.write_text(FIXTURE_SOURCE, encoding="utf-8")
        self.input_file = self.root / "m1.py"
        self.input_file.write_text("# Marked immutable route fixture\n", encoding="utf-8")
        self.native_input_calls = 0
        self.verifier_calls = 0
        self.bootstrap = ModuleType("v42_bootstrap.m1")
        self.bootstrap.__b3_fake__ = True
        self.bootstrap.__file__ = str(self.input_file)
        def native_inputs(bundle):
            self.native_input_calls += 1
            return ("s1", "s2"), {"unit1": "s1"}, (
                FixtureRoute("s1", "s2", 0, 1, 2.),), FixtureBattery(100., 10.), {
                "route_sha": bundle["route_table"]["sha256"], "PASS": True}
        self.bootstrap.native_inputs = native_inputs
        self.model = ModuleType("v42_may_campaign_native90.m_model")
        self.model.__b3_fake__ = True
        self.model.__file__ = str(self.source_file)
        self.model.np, self.model.SimpleNamespace = np, SimpleNamespace
        self.model.Compact, self.model.Presolve = FixtureCompact, FixturePresolve
        original_pcs = Path(__file__).resolve().parents[1] / "v42_native" / "mess.py"
        self.native_mess = ModuleType("v42_native.mess")
        self.native_mess.__b3_fake__ = True
        self.native_mess.__file__ = str(original_pcs)
        self.native_mess.cos, self.native_mess.sin, self.native_mess.pi = math.cos, math.sin, math.pi
        self.native_mess.FACES = 16
        def require(value, message):
            if not value:
                raise ValueError(message)
        self.native_mess.require = require
        pcs_definition = [node for node in ast.parse(original_pcs.read_text(encoding="utf-8-sig")).body
            if isinstance(node, ast.FunctionDef) and node.name == "pcs_rows"]
        exec(compile(ast.Module(pcs_definition, type_ignores=[]), str(original_pcs), "exec"), vars(self.native_mess))
        def pcs_fixture():
            recorder = FixtureConstraintRecorder()
            for _ in range(3):
                self.native_mess.pcs_rows(recorder, FixtureLinearExpression({"p": 1.}),
                    FixtureLinearExpression({"q": 1.}), FixtureLinearExpression({"connected": 1.}), 100.)
            return recorder.rows
        self.model.pcs_fixture = pcs_fixture
        self.model.verify_transport = lambda compact, presolve: {
            "PASS": np.array_equal(compact.A, presolve.A), "evidence_kind": "FAKE_SOURCE_TEST"}
        def verify_case(case):
            self.verifier_calls += 1
            return {"PASS": np.array_equal(case.original_A, case.A)
                and all(np.array_equal(case.original_d[key], case.d[key]) for key in case.d),
                "evidence_kind": "FAKE_SOURCE_TEST", "fresh_case_verified": True}
        self.model.verify_case = verify_case
        exec(compile(FIXTURE_SOURCE, str(self.source_file), "exec"), vars(self.model))
        self.gateway = FakeSourceGateway({"v42_bootstrap.m1": self.bootstrap,
            "v42_may_campaign_native90.m_model": self.model, "v42_native.mess": self.native_mess}, {
            "v42_bootstrap/m1.py": self.input_file,
            "v42_may_campaign_native90/m_model.py": self.source_file,
            "v42_native/mess.py": original_pcs})
        self.request = dict(day="2026-05-01", run_id="FIXTURE_B2", arm="B2", Threads=1,
            P2_calls=0, native_budget_seconds=5400, wall_budget_seconds=None, target_gap=.03,
            output=str(self.root / "output"))
        self.payload = dict(bundle=dict(day=self.request["day"], route_table=dict(
            path=str(self.route_file), sha256=self.sha(self.route_file)),
            electrical_certificate={"sha256": "e" * 64}, traffic_forecast_sha="f" * 64),
            identity=dict(day=self.request["day"], arm="B2", AIDC_optimization_calls=0,
                B0_B1_schedule_result_reads=0, fixed_AIDC_sha="a" * 64))

    @staticmethod
    def sha(path):
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()

    def port(self):
        return VersionedB2BuildPort(self.request, self.gateway)

    def test_source_baseline_and_optimized_full_compact_c3a_match(self):
        parent = ModuleType("v42_bootstrap")
        parent.__path__ = []
        with patch.dict(sys.modules, {"v42_bootstrap": parent, "v42_bootstrap.m1": self.bootstrap}):
            baseline = self.model.build_case(self.payload, self.request)
        optimized = self.port().build(self.payload)
        np.testing.assert_array_equal(baseline.original_A, optimized.original_A)
        np.testing.assert_array_equal(baseline.A, optimized.A)
        for key in baseline.d:
            np.testing.assert_array_equal(baseline.d[key], optimized.d[key])
        self.assertEqual(baseline.graph, optimized.graph)
        self.assertEqual(baseline.pcs_rows, optimized.pcs_rows)
        self.assertEqual(optimized.proof["evidence_kind"], "FAKE_SOURCE_TEST")

    def test_reuses_only_immutable_inputs_and_rebuilds_every_case(self):
        port = self.port()
        first, second = port.build(self.payload), port.build(self.payload)
        self.assertEqual(self.native_input_calls, 1)
        self.assertEqual(self.verifier_calls, 2)
        self.assertIsNot(first, second)
        self.assertIsNot(first.original_A, second.original_A)
        self.assertIsNot(first.A, second.A)
        self.assertEqual(port.last_receipt["input_cache"]["hits"], 1)
        self.assertEqual(port.last_receipt["input_cache"]["cached_matrices"], 0)
        self.assertEqual(port.last_receipt["input_cache"]["cached_solver_models"], 0)

    def test_mutable_initial_state_is_detached_on_cache_hits(self):
        port = self.port()
        first = port.build(self.payload)
        first.graph[1]["unit1"] = "changed"
        first.graph[4]["PASS"] = False
        second = port.build(self.payload)
        self.assertEqual(second.graph[1]["unit1"], "s1")
        self.assertTrue(second.graph[4]["PASS"])

    def test_worker_cache_is_not_shared(self):
        self.port().build(self.payload)
        self.port().build(self.payload)
        self.assertEqual(self.native_input_calls, 2)

    def test_profile_measures_all_build_phases_without_speedup_claim(self):
        port = self.port()
        port.build(self.payload)
        receipt = port.last_receipt
        self.assertEqual(set(receipt["profile"]["seconds"]), set(PHASES))
        self.assertEqual(receipt["profile"]["unmeasured_phases"], [])
        self.assertEqual(receipt["profile"]["mode"], "FIXTURE_OPTIMIZED")
        self.assertEqual(receipt["real_performance_comparison"], "NOT_RUN")
        self.assertFalse(receipt["production_worker_started"])
        self.assertFalse(receipt["source_version_transition_by_this_module"])

    def test_first_build_scalar_math_calls_drop_and_coefficients_stay_exact(self):
        original_function = self.native_mess.pcs_rows
        port = self.port()
        case = port.build(self.payload)
        self.assertEqual(len(case.pcs_rows), 48)
        scalar = port.last_receipt["original_PCS_scalar_math"]
        self.assertEqual(scalar["calls"]["requests"], {"cos": 96, "sin": 48})
        self.assertEqual(scalar["calls"]["original_math_evaluations"], {"cos": 17, "sin": 16})
        self.assertTrue(scalar["source_proof"]["source_AST_and_bytecode_preserved"])
        self.assertTrue(scalar["source_proof"]["function_restored"])
        self.assertIs(self.native_mess.pcs_rows, original_function)
        self.assertIs(self.native_mess.cos, math.cos)
        self.assertIs(self.native_mess.sin, math.sin)

    def test_private_pcs_scope_restores_original_function_on_failure(self):
        original_function = self.native_mess.pcs_rows
        with self.assertRaisesRegex(RuntimeError, "fixture failed"):
            with original_pcs_math_scope(self.native_mess, self.native_mess.__file__,
                    self.sha(self.native_mess.__file__)) as (memo, proof):
                self.assertIsNot(self.native_mess.pcs_rows, original_function)
                memo.cos(math.pi / 16)
                raise RuntimeError("fixture failed")
        self.assertIs(self.native_mess.pcs_rows, original_function)
        self.assertTrue(proof["function_restored"])

    def test_scalar_cache_resets_for_every_new_build(self):
        port = self.port()
        port.build(self.payload)
        first = deepcopy(port.last_receipt["original_PCS_scalar_math"]["calls"])
        port.build(self.payload)
        self.assertEqual(first, port.last_receipt["original_PCS_scalar_math"]["calls"])
        self.assertEqual(first["cache_scope"], "ONE_SOURCE_MODEL_BUILD")

    def test_fake_gateway_cannot_promote_receipt_to_real_source(self):
        self.gateway.evidence_kind = "SOURCE"
        port = self.port()
        port.build(self.payload)
        self.assertEqual(port.last_receipt["evidence_kind"], "FAKE_SOURCE_TEST")
        self.assertEqual(port.last_receipt["profile"]["mode"], "FIXTURE_OPTIMIZED")

    def test_input_fixed_date_and_worker_drift_are_rejected(self):
        port = self.port()
        port.build(self.payload)
        changed = deepcopy(self.payload)
        changed["bundle"]["traffic_forecast_sha"] = "b" * 64
        with self.assertRaisesRegex(ValueError, "CACHE_DRIFT"):
            port.build(changed)
        changed = deepcopy(self.payload)
        changed["identity"]["fixed_AIDC_sha"] = "c" * 64
        with self.assertRaisesRegex(ValueError, "CACHE_DRIFT"):
            port.build(changed)
        changed = deepcopy(self.payload)
        changed["bundle"]["day"] = "2026-05-02"
        with self.assertRaisesRegex(ValueError, "DATE_DRIFT"):
            port.build(changed)
        with patch("v42_b2_build_optimization.builder.os.getpid", return_value=999999):
            with self.assertRaisesRegex(ValueError, "CACHE_DRIFT"):
                port.build(self.payload)

    def test_source_and_route_file_drift_are_rejected(self):
        port = self.port()
        port.build(self.payload)
        self.route_file.write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "ROUTE_FILE_SHA_DRIFT"):
            port.build(self.payload)
        self.route_file.write_bytes(b'{"routes":[["s1","s2",0,1]]}')
        self.source_file.write_text(FIXTURE_SOURCE + "\n# changed\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "CACHE_DRIFT"):
            port.build(self.payload)

    def test_original_builder_ast_is_preserved_without_executing_it(self):
        original = Path(__file__).resolve().parents[1] / "v42_may_campaign_native90" / "m_model.py"
        function, proof = instrument_builder(original, {}, lambda value: value,
            BuildProfile("a" * 64, "FIXTURE_OPTIMIZED"), self.sha(original))
        self.assertTrue(callable(function))
        self.assertTrue(proof["source_statements_preserved"])
        self.assertTrue(proof["FULL_Compact_C3A_builds_preserved"])
        self.assertFalse(proof["numeric_constants_changed"])

    def test_source_sha_guard_precedes_source_compilation(self):
        with self.assertRaisesRegex(ValueError, "SOURCE_SHA_DRIFT"):
            instrument_builder(self.source_file, {}, None,
                BuildProfile("a" * 64, "FIXTURE_OPTIMIZED"), "0" * 64)

    def test_default_gateway_denies_before_imports_and_outputs(self):
        with patch.dict(sys.modules, {"v42_may_campaign_native90.execution": None}):
            with self.assertRaisesRegex(ValueError, "OFFICIAL_WORKER_SCOPE_REQUIRED"):
                VersionedB2BuildPort(self.request)
        self.assertFalse(Path(self.request["output"]).exists())

    def test_existing_worker_version_cannot_hot_switch(self):
        execution = SimpleNamespace(current=lambda: dict(request=dict(self.request),
            manifest=dict(run_id=self.request["run_id"], implementation=dict(version="MAY23_BUILD_EFFICIENCY_V6"))))
        with patch.dict(sys.modules, {"v42_may_campaign_native90.execution": execution}):
            with self.assertRaisesRegex(ValueError, "NEW_SOURCE_VERSION_NOT_AUTHORIZED"):
                AdmittedSourceGateway(self.request).admit()

    def test_real_modules_and_arbitrary_gateway_are_forbidden(self):
        with self.assertRaisesRegex(ValueError, "MARKED_FAKE_MODULES_REQUIRED"):
            FakeSourceGateway({"real": SimpleNamespace()}, {})
        with self.assertRaisesRegex(ValueError, "TYPED_SOURCE_GATEWAY_REQUIRED"):
            VersionedB2BuildPort(self.request, SimpleNamespace(admit=lambda: None))

    def test_independent_fixed_aidc_and_native_policy_are_retained(self):
        for field, value in (("Threads", True), ("Threads", 2), ("P2_calls", 1),
                ("native_budget_seconds", 1), ("wall_budget_seconds", 600)):
            request = dict(self.request, **{field: value})
            with self.assertRaisesRegex(ValueError, "NATIVE_POLICY_DRIFT"):
                VersionedB2BuildPort(request, self.gateway)
        payload = deepcopy(self.payload)
        payload["identity"]["AIDC_optimization_calls"] = 1
        with self.assertRaisesRegex(ValueError, "INDEPENDENT_FIXED_AIDC_REQUIRED"):
            self.port().build(payload)
        self.assertEqual(VERSION, "B2_BUILD_INPUT_REUSE_V7_20261009")


if __name__ == "__main__":
    unittest.main()

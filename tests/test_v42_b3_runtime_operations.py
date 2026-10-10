"""Sequential small source-body tests; no real model, solver or engine import."""
import ast
from contextlib import contextmanager
from dataclasses import dataclass, replace
import hashlib
import json
import math
from pathlib import Path
import sys
import tempfile
from time import perf_counter, process_time
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

from v42_b3_joint.contracts import canonical, digest, require, StageRequest
from v42_b3_joint.dry_run import fixture_authority, fixture_aidc, fixture_mess
from v42_b3_joint.budget import MockClock
from v42_b3_joint.native_ledger import SourceStageLedger
from v42_b3_joint.operations_bridge import (SourceOperationsBridge, _native_digest, _slots,
    _source_aidc_state, _require_expected_aidc_state, OriginalOperationsBackend, SOURCE_COMPANIONS)
from v42_b3_joint.operations_bridge import _verify_completed_source_records
from v42_b3_joint.source_runtime import RealStageContext, FakeSourceRegistry, SourceRegistry, SourceStageOutput

ROOT = Path(__file__).resolve().parents[1]


def write_once(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        stream.write(canonical(value))


def fake_source_module(name, relative, namespace):
    """Compile small pure source definitions after removing import statements.

    Inline guarded API imports are routed by the registry factory. The original
    DateBudget/native Planning/Actual method bodies remain the test subject.
    """
    module = ModuleType(name)
    module.__dict__.update(namespace)
    module.__file__ = str(ROOT / relative)
    module.__package__ = name.rsplit(".", 1)[0]
    module.__b3_fake__ = True
    tree = ast.parse((ROOT / relative).read_text(encoding="utf-8-sig"))
    tree.body = [node for node in tree.body if not isinstance(node, (ast.Import, ast.ImportFrom))]
    # Freeze/Actual guard imports are lexical routing inputs; never import an
    # active execution module in this safe source fixture.
    def denied(*args, **kwargs):
        raise PermissionError("UNROUTED_SOURCE_GUARD")
    module.__dict__["_test_imports"] = {"require_action_authorized": denied}
    class Imports(ast.NodeTransformer):
        def visit_ImportFrom(self, node):
            if not all((alias.asname or alias.name) == "require_action_authorized" for alias in node.names):
                return node
            return ast.copy_location(ast.Assign([ast.Name("require_action_authorized", ast.Store())],
                ast.Subscript(ast.Name("_test_imports", ast.Load()), ast.Constant("require_action_authorized"), ast.Load())), node)
    exec(compile(ast.fix_missing_locations(Imports().visit(tree)), str(ROOT / relative), "exec"), module.__dict__)
    def rebind(symbol, target, routing):
        from types import FunctionType
        globals_ = dict(target.__globals__)
        globals_.update(routing.get("globals") or {})
        globals_["_test_imports"] = dict(module.__dict__["_test_imports"], **(routing.get("import_replacements") or {}))
        function = FunctionType(target.__code__, globals_, target.__name__, target.__defaults__, target.__closure__)
        function.__kwdefaults__ = target.__kwdefaults__
        return function
    module.__b3_rebind__ = rebind
    return module


def runtime_registry():
    @contextmanager
    def denied_scope(*args, **kwargs):
        raise PermissionError("UNROUTED_NATIVE_SCOPE")
        yield
    budget = fake_source_module("v42_may_campaign_native90.budget", "v42_may_campaign_native90/budget.py",
        dict(contextmanager=contextmanager, Path=Path, perf_counter=perf_counter,
             process_time=process_time, math=math, atomic=write_once, now=lambda: "FAKE_TEST",
             d_path=Path, native_scope=denied_scope, guard=lambda model: None))
    m_budget = fake_source_module("v42_b3_joint.m_budget", "v42_b3_joint/m_budget.py",
        dict(math=math, importlib=__import__("importlib")))
    return FakeSourceRegistry({budget.__name__: budget, m_budget.__name__: m_budget})


def operation_registry():
    from copy import deepcopy
    from typing import Protocol
    planning = fake_source_module("v42_native.planning", "v42_native/planning.py",
        dict(dataclass=dataclass, json=json, Path=Path, digest=_native_digest, require=require, write_once=write_once))
    actual = fake_source_module("v42_native.actual", "v42_native/actual.py",
        dict(dataclass=dataclass, isfinite=math.isfinite, deepcopy=deepcopy, Path=Path, Protocol=Protocol,
             require=require, digest=_native_digest, write_once=write_once,
             FrozenDayAheadPlan=planning.FrozenDayAheadPlan, require_sha=planning.require_sha,
             ACTUAL_LOWER_PU=.95, ACTUAL_UPPER_PU=1.05))
    operations = ModuleType("v42_may_campaign_native90.operations")
    operations.__b3_fake__ = True
    operations.np = np
    operations.calls = []
    def freeze(request, accepted, mess, output):
        operations.calls.append(("freeze", request["arm"]))
        write_once(Path(output) / "V42_DAYAHEAD_DECISION_FREEZE.json", {"accepted": accepted, "mess": mess})
        return {"PASS": True}
    def sources(request, output):
        operations.calls.append(("actual_sources", request["arm"]))
        return output
    def materialize(request, planning, source, output):
        operations.calls.append(("actual", request["arm"]))
        return {"PASS": True}
    def fresh(request, planning, actual_folder, source_folder, output):
        operations.calls.append(("fresh", request["arm"]))
        return {"PASS": True, "converged": True, "summary": dict(voltage_violations=0,
            line_current_violations=0, transformer_current_violations=0, transformer_kVA_violations=0)}
    operations.freeze_planning, operations.actual_sources, operations.actual, operations.fresh = freeze, sources, materialize, fresh
    operations.__b3_rebind__ = lambda symbol, target, routing: target
    return FakeSourceRegistry({planning.__name__: planning, actual.__name__: actual, operations.__name__: operations})


class FakeModel:
    def __init__(self, runtime, *, fail=False):
        self.Params = SimpleNamespace(Threads=1)
        self.Runtime, self.Work, self.Status, self.SolCount, self.ObjBound = runtime, 0., 2, 1, 0.
        self.calls, self.fail = 0, fail
    def optimize(self, callback):
        self.calls += 1
        if self.fail:
            raise RuntimeError("FAKE_NATIVE_FAILURE")


class SourceRuntimeOperationsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="b3-runtime-test-")
        self.root = Path(self.temp.name)
        self.authority = fixture_authority()
        self.aidc = fixture_aidc()
        self.mess = fixture_mess()
        self.fake_gp = ModuleType("gurobipy")
        self.fake_gp.GurobiError = type("FakeGurobiError", (Exception,), {})
        self.fake_gp.GRB = SimpleNamespace(Callback=SimpleNamespace(POLLING=0, RUNTIME=1))
        self.gp_patch = patch.dict(sys.modules, {"gurobipy": self.fake_gp})
        self.gp_patch.start()
    def tearDown(self):
        self.gp_patch.stop()
        self.temp.cleanup()
    def context(self, registry, stage="A1", folder=None, authority=None):
        authority = authority or self.authority
        request = StageRequest(stage, authority, self.aidc if stage.startswith("M") else None,
            self.mess if stage == "A2" else None)
        return RealStageContext(request, self.root / "INPUT", self.root / (folder or stage),
            canonical({"day": authority.day}), registry, SimpleNamespace(), {}, authority.source_sha, "FAKE_B3_ONLY")

    def test_real_ledger_guard_before_resolve_or_output(self):
        registry = SourceRegistry()
        # Real output authorization is checked by context as well as ledger.
        context = replace(self.context(runtime_registry()), source_registry=registry,
            output=ROOT / "runtime" / "b3" / "GUARD_TEST_NOT_CREATED")
        with self.assertRaises(PermissionError):
            SourceStageLedger(context)
        self.assertEqual(registry.audit, [])
        self.assertFalse(context.output.exists())

    def test_source_budget_counts_runtime_and_preserves_policy(self):
        ledger = SourceStageLedger(self.context(runtime_registry()))
        model = FakeModel(3.)
        ledger.native_optimize(model, requested_seconds=1)
        self.assertEqual(ledger.used(), 3.)
        self.assertEqual(model.Params.TimeLimit, 5400.)
        self.assertEqual(model.Params.Threads, 1)
        self.assertEqual(ledger.receipt()["evidence_kind"], "FAKE_SOURCE_TEST")

    def test_m_requested_calls_share_1800_native_budget_and_preserve_overshoot(self):
        context = self.context(runtime_registry(), stage="M1")
        ledger = SourceStageLedger(context)
        first = FakeModel(1200.)
        ledger.native_optimize(first, track="M_START", requested_seconds=1200.)
        second = FakeModel(600.125)
        receipt = ledger.native_optimize(second, track="M_U4", requested_seconds=900.)
        self.assertEqual((first.Params.TimeLimit, second.Params.TimeLimit), (1200., 600.))
        self.assertEqual(ledger.used(), 1800.125)
        self.assertEqual(receipt["cumulative_budget_excess_seconds"], .125)
        resumed = SourceStageLedger(context)
        self.assertEqual(resumed.receipt()["native_budget_excess_seconds"], .125)
        denied = FakeModel(1.)
        with self.assertRaises(TimeoutError):
            resumed.native_optimize(denied, track="M_U4", requested_seconds=1.)
        self.assertEqual(denied.calls, 0)

    def test_m_failed_call_is_durable_and_nonfinite_bound_is_unknown(self):
        context = self.context(runtime_registry(), stage="M2")
        ledger = SourceStageLedger(context)
        model = FakeModel(7., fail=True)
        model.ObjBound = float("inf")
        with self.assertRaisesRegex(RuntimeError, "FAKE_NATIVE_FAILURE"):
            ledger.native_optimize(model, track="M_U4", requested_seconds=10.)
        document = json.loads(ledger.path.read_text())
        self.assertEqual(document["measured_Native_Runtime"], 7.)
        self.assertIsNone(document["calls"][0]["Native_BestBd"])
        self.assertEqual(SourceStageLedger(context).remaining(), 1793.)

    def test_m_polling_does_not_read_unsupported_callback_runtime(self):
        ledger = SourceStageLedger(self.context(runtime_registry(), stage="M1"))
        model = FakeModel(2.)
        def unsupported(code):
            self.fail("POLLING must not query runtime")
        model.cbGet = unsupported
        model.optimize = lambda callback: callback(model, self.fake_gp.GRB.Callback.POLLING)
        events = []
        ledger.native_optimize(model, track="M_U4", requested_seconds=5.,
            callback=lambda m, where: events.append(where))
        self.assertEqual(events, [self.fake_gp.GRB.Callback.POLLING])
        self.assertEqual(ledger.used(), 2.)

    def test_m_unknown_runtime_survives_restart_as_quarantine(self):
        context = self.context(runtime_registry(), stage="M2")
        ledger = SourceStageLedger(context)
        with self.assertRaisesRegex(RuntimeError, "RUNTIME_UNAVAILABLE"):
            ledger.native_optimize(FakeModel(float("nan")), track="M_U4", requested_seconds=1.)
        resumed = SourceStageLedger(context)
        self.assertTrue(resumed.receipt()["quarantined"])
        denied = FakeModel(1.)
        with self.assertRaisesRegex(RuntimeError, "QUARANTINE"):
            resumed.native_optimize(denied, track="M_U4", requested_seconds=1.)
        self.assertEqual(denied.calls, 0)

    def test_failed_source_optimize_runtime_is_charged(self):
        ledger = SourceStageLedger(self.context(runtime_registry()))
        with self.assertRaisesRegex(RuntimeError, "FAKE_NATIVE_FAILURE"):
            ledger.native_optimize(FakeModel(7., fail=True))
        self.assertEqual(ledger.used(), 7.)
        self.assertEqual(ledger.calls[0]["status"], "FAILED")

    def test_unknown_runtime_quarantines_and_survives_restart(self):
        context = self.context(runtime_registry())
        ledger = SourceStageLedger(context)
        with self.assertRaisesRegex(RuntimeError, "RUNTIME_UNAVAILABLE"):
            ledger.native_optimize(FakeModel(None))
        resumed = SourceStageLedger(context)
        denied = FakeModel(1.)
        with self.assertRaisesRegex(RuntimeError, "UNMEASURED_RUNTIME"):
            resumed.native_optimize(denied)
        self.assertEqual(denied.calls, 0)
        self.assertTrue(resumed.receipt()["quarantined"])

    def test_all_four_source_ledgers_independent(self):
        registry = runtime_registry()
        ledgers = [SourceStageLedger(self.context(registry, stage)) for stage in ("A1", "M1", "A2", "M2")]
        ledgers[0].native_optimize(FakeModel(10.))
        self.assertEqual([ledger.remaining() for ledger in ledgers], [5390., 1800., 5400., 1800.])

    def test_restart_keeps_runtime_and_next_limit(self):
        context = self.context(runtime_registry())
        ledger = SourceStageLedger(context)
        ledger.native_optimize(FakeModel(9.))
        resumed = SourceStageLedger(context)
        next_model = FakeModel(2.)
        resumed.native_optimize(next_model)
        self.assertEqual(next_model.Params.TimeLimit, 5391.)
        self.assertEqual(resumed.used(), 11.)

    def test_restart_identity_cannot_relabel_stage(self):
        registry = runtime_registry()
        SourceStageLedger(self.context(registry))
        with self.assertRaisesRegex(ValueError, "RESTART_IDENTITY_DRIFT"):
            SourceStageLedger(self.context(registry, stage="A2", folder="A1"))

    def test_interrupted_inflight_never_reset_or_retried(self):
        context = self.context(runtime_registry())
        ledger = SourceStageLedger(context)
        ledger.budget.inflight = {"status": "IN_FLIGHT"}
        ledger.budget.persist()
        resumed = SourceStageLedger(context)
        with self.assertRaisesRegex(ValueError, "INTERRUPTED"):
            resumed.native_optimize(FakeModel(1.))
        self.assertTrue(resumed.receipt()["quarantined"])

    def test_p2_denied_without_fake_optimize(self):
        ledger = SourceStageLedger(self.context(runtime_registry()))
        model = FakeModel(1.)
        with self.assertRaisesRegex(ValueError, "P2"):
            ledger.native_optimize(model, component="P2")
        self.assertEqual(model.calls, 0)

    def test_original_m_hybrid_track_labels_admitted(self):
        ledger = SourceStageLedger(self.context(runtime_registry(), stage="M2"))
        for track in ("M_SEED", "M_LB", "UB", "LB", "PRICING", "RMP"):
            ledger.native_optimize(FakeModel(1.), track=track)
        self.assertEqual(ledger.used(), 6.)

    def test_source_guard_rejects_boolean_threads(self):
        ledger = SourceStageLedger(self.context(runtime_registry()))
        model = FakeModel(1.)
        model.Params.Threads = True
        with self.assertRaisesRegex(ValueError, "THREADS_ONE"):
            ledger._guard(model)

    def test_non_native_cost_does_not_consume_budget(self):
        clock = MockClock()
        ledger = SourceStageLedger(self.context(runtime_registry()), clock=clock)
        with ledger.cost("model_preparation", "FAKE_MATRIX_ONLY"):
            clock.advance(6000.)
        self.assertEqual(ledger.used(), 0.)
        self.assertEqual(ledger.remaining(), 5400.)

    def stage_outputs(self):
        source_variables = json.loads(self.mess.variables_json)
        source_variables.update(movement={"fake_arc": 1}, charge_mode={"fake_mode": 1})
        mess = replace(self.mess, variables_json=canonical(source_variables))
        aidc_jobs = json.loads(self.aidc.jobs_json)
        aidc_jobs["known_job_actions"] = {"FAKE_UID": {"slot": 1, "synthetic_only": True}}
        aidc_jobs["unknown_arrival_policy"]["authority_sha"] = digest({"fake_causal_policy": True})
        aidc = replace(self.aidc, jobs_json=canonical(aidc_jobs))
        requests = (StageRequest("A1", self.authority), StageRequest("M1", self.authority, fixed_aidc=aidc),
            StageRequest("A2", self.authority, fixed_mess=mess), StageRequest("M2", self.authority, fixed_aidc=aidc))
        planning = dict(sites=list(self.authority.pcc_ids), time_axis=list(range(96)),
            PCC_P_kw=_slots(aidc.pcc_p), PCC_Q_kvar=_slots(aidc.pcc_q), IT_kw=_slots(aidc.it_power),
            GPU=[[1.] * 12 for _ in range(96)])
        mess_plan = dict(P_kw=[[-.1] * 4 for _ in range(96)], Q_kvar=_slots(mess.q),
            SOC_kwh=_slots(mess.soc), locations=_slots(mess.location),
            unit_ids=list(self.authority.mess_ids), routes=[{"synthetic_only": True}])
        packet = dict(planning_arrays=planning, selected_jobs=aidc_jobs["known_job_actions"],
            accepted_source={"path": "FAKE_SOURCE", "sha256": digest({"fake_file": True})}, mess_plan=mess_plan)
        outputs = tuple(SourceStageOutput(request, {}, aidc, None if request.stage == "A1" else mess,
            digest({"fake_model": request.stage}), {"synthetic_only": True}, {"synthetic_only": True},
            packet, canonical({"synthetic_only": True}), "FAKE_SOURCE_TEST") for request in requests)
        return requests, outputs

    def frozen(self, registry=None):
        registry = registry or operation_registry()
        requests, outputs = self.stage_outputs()
        context = replace(self.context(registry, stage="M2"), request=requests[-1])
        bridge = SourceOperationsBridge(context)
        frozen = bridge.freeze(requests, outputs, verify_stage=lambda request, output: True)
        return bridge, frozen, requests, outputs

    def test_source_freeze_uses_final_a2_m2_and_original_native_freeze(self):
        bridge, frozen, requests, outputs = self.frozen()
        self.assertTrue(frozen.verify())
        self.assertEqual(frozen.document["aidc_sha"], outputs[2].aidc.sha)
        self.assertEqual(frozen.document["mess_sha"], outputs[3].mess.sha)
        self.assertEqual(frozen.native_freeze.plan["source_stage_order"], ["A1", "M1", "A2", "M2"])
        self.assertEqual(bridge.registry.resolve("v42_may_campaign_native90.operations").calls, [("freeze", "B3")])

    def test_source_freeze_restart_revalidates_all_stages_and_native_plan(self):
        bridge, frozen, requests, outputs = self.frozen()
        checked = []
        loaded = bridge.load_freeze(lambda request, output: checked.append(request.stage), requests, outputs)
        self.assertEqual(checked, ["A1", "M1", "A2", "M2"])
        self.assertEqual(loaded.sha, frozen.sha)
        self.assertEqual(loaded.native_freeze.plan_sha, frozen.native_freeze.plan_sha)
        self.assertTrue(loaded.verify())
        self.assertEqual(bridge.registry.resolve("v42_may_campaign_native90.operations").calls, [("freeze", "B3")])

    def test_source_freeze_resume_rejects_each_consumed_companion_mutation(self):
        for relative in SOURCE_COMPANIONS:
            with self.subTest(companion=relative):
                registry = operation_registry()
                requests, outputs = self.stage_outputs()
                context = replace(self.context(registry, stage="M2", folder="M2_" + relative.split("/")[-1]),
                    request=requests[-1])
                bridge = SourceOperationsBridge(context)
                frozen = bridge.freeze(requests, outputs, verify_stage=lambda request, output: True)
                path = frozen.output / relative
                # Appended bytes leave the saved stage outputs and native plan
                # untouched, precisely the former resume integrity hole.
                with path.open("ab") as stream:
                    stream.write(b"CORRUPTED_COMPANION")
                with self.assertRaisesRegex(ValueError, "COMPANION_BYTES_OR_SHA_DRIFT"):
                    bridge.load_freeze(lambda request, output: True, requests, outputs)

    def test_source_actual_rejects_companion_drift_before_reservation_or_calls(self):
        bridge, frozen, _, _ = self.frozen()
        with (frozen.output / SOURCE_COMPANIONS[0]).open("ab") as stream:
            stream.write(b"CHANGED")
        with self.assertRaisesRegex(ValueError, "COMPANION_BYTES_OR_SHA_DRIFT"):
            bridge.actual(frozen, {"load": [], "pv": [], "aidc_state": {}})
        self.assertFalse((frozen.output / "NATIVE_ACTUAL").exists())
        self.assertEqual(bridge.registry.resolve("v42_may_campaign_native90.operations").calls, [("freeze", "B3")])

    def test_source_fresh_rechecks_companions_before_backend_call(self):
        bridge, frozen, _, _ = self.frozen()
        backend = OriginalOperationsBackend(bridge, frozen)
        backend.source_folder = frozen.output / "ACTUAL_SOURCE"
        with (frozen.output / SOURCE_COMPANIONS[1]).open("ab") as stream:
            stream.write(b"CHANGED")
        with self.assertRaisesRegex(ValueError, "COMPANION_BYTES_OR_SHA_DRIFT"):
            backend.fresh_ac({})
        self.assertEqual(bridge.registry.resolve("v42_may_campaign_native90.operations").calls, [("freeze", "B3")])

    def completed_source_artifacts(self):
        output = self.root / "PURE_SAVED_SOURCE_RECORDS"
        paths = ("ACTUAL/ACTUAL_FIXED_REPLAY_RECEIPT.json", "FRESH/FRESH_RESULT.json",
            "FRESH/RAW_CONTROL_LOG.json", "FRESH/RAW_PHYSICAL_INPUT_LOG.json")
        records = {}
        for relative in paths:
            path = output / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'{"source_fixture":"original"}')
            records[relative] = {"path": str(path.resolve()), "bytes": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        physical = {"aidc_state": {"source_receipt_record": records[paths[0]]}}
        ac = dict(receipt=records[paths[1]], control_log=records[paths[2]], physical_input_log=records[paths[3]])
        return output, paths, physical, ac

    def test_completed_source_validation_rehashes_all_four_cited_artifacts(self):
        output, paths, physical, ac = self.completed_source_artifacts()
        _verify_completed_source_records(output, physical, ac)
        for relative in paths:
            with self.subTest(artifact=relative):
                path = output / relative
                original = path.read_bytes()
                # Same length preserves metadata size while changing raw bytes.
                path.write_bytes(original.replace(b"original", b"modified"))
                with self.assertRaisesRegex(ValueError, "RAW_SHA_DRIFT"):
                    _verify_completed_source_records(output, physical, ac)
                path.write_bytes(original)

    def test_completed_source_validation_rejects_record_path_rebinding(self):
        output, paths, physical, ac = self.completed_source_artifacts()
        changed = json.loads(canonical(ac))
        changed["receipt"]["path"] = str(self.root / "unrelated_same_name.json")
        with self.assertRaisesRegex(ValueError, "PATH_OR_RAW_SHA_DRIFT"):
            _verify_completed_source_records(output, physical, changed)

    def test_source_freeze_restart_rejects_relabelled_final_decision(self):
        bridge, frozen, requests, outputs = self.frozen()
        path = frozen.output / "B3_SOURCE_FREEZE.json"
        document = json.loads(path.read_text(encoding="utf-8"))
        document["aidc_sha"] = "0" * 64
        path.write_text(canonical(document), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "FREEZE_COMPONENT_DRIFT"):
            bridge.load_freeze(lambda request, output: True, requests, outputs)

    def test_actual_aidc_state_is_bound_to_original_fixed_source_receipt(self):
        bridge, frozen, _, _ = self.frozen()
        expected = bridge.expected_aidc_state(frozen)
        receipt = dict(PASS=True, policy="V39E_FROZEN_DA_FIXED_REPLAY", Actual_reoptimization=0,
            local_PQ_repair=0, global_PQ_repair=0,
            Actual_workload_semantics="fixed accepted Planning power/service trajectory; no rescheduling from retrospective outcomes")
        _require_expected_aidc_state(expected, json.loads(canonical(expected)))
        state = _source_aidc_state(expected, receipt, {"path": "FAKE_RECEIPT", "sha256": "f" * 64})
        self.assertEqual(state["source_receipt"], receipt)
        self.assertEqual(state["known_job_actions"], frozen.native_freeze.plan["known_job_actions"])
        self.assertEqual(state["aidc_decision_sha"], frozen.document["aidc_sha"])
        self.assertEqual(state["source_semantics"], "V39E_FROZEN_DA_FIXED_REPLAY")
        self.assertFalse(state["caller_workload_state_used_as_source_authority"])
        with self.assertRaisesRegex(ValueError, "AIDC_STATE_DRIFT"):
            _require_expected_aidc_state(expected, {"arbitrary_observed_workload": True})

    def test_actual_aidc_state_rejects_non_original_repair_or_policy_receipt(self):
        expected = {"aidc_schedule": {}, "known_job_actions": {}}
        receipt = dict(PASS=True, policy="V39E_FROZEN_DA_FIXED_REPLAY", Actual_reoptimization=0,
            local_PQ_repair=0, global_PQ_repair=0)
        for changed in ({"PASS": False}, {"policy": "arbitrary"},
                {"Actual_reoptimization": 1}, {"local_PQ_repair": 1}, {"global_PQ_repair": 1}):
            with self.assertRaisesRegex(ValueError, "AIDC_STATE_AUTHORITY_REQUIRED"):
                _source_aidc_state(expected, dict(receipt, **changed), {"sha256": "f" * 64})

    def test_source_freeze_refuses_wrong_decision_chain(self):
        registry = operation_registry()
        requests, outputs = self.stage_outputs()
        requests = list(requests)
        requests[3] = replace(requests[3], fixed_aidc=fixture_aidc(99))
        outputs = list(outputs)
        outputs[3] = replace(outputs[3], request=requests[3])
        bridge = SourceOperationsBridge(self.context(registry, stage="M2"))
        with self.assertRaisesRegex(ValueError, "FIXED_CHAIN"):
            bridge.freeze(requests, outputs, verify_stage=lambda request, output: True)
        self.assertFalse((bridge.context.output / "OPERATIONS").exists())

    def test_fake_stage_receipt_never_promoted_into_source_freeze(self):
        registry = operation_registry()
        requests, outputs = self.stage_outputs()
        outputs = [replace(out, evidence_kind="SOURCE") for out in outputs]
        bridge = SourceOperationsBridge(self.context(registry, stage="M2"))
        with self.assertRaisesRegex(ValueError, "REAL_PROMOTION"):
            bridge.freeze(requests, outputs, verify_stage=lambda request, output: True)

    def test_original_actual_and_fresh_source_calls_fake_science_not_promoted(self):
        bridge, frozen, _, _ = self.frozen()
        result = bridge.actual(frozen, {"load": [1.] * 96, "pv": [0.] * 96, "aidc_state": {"observed": True}})
        self.assertFalse(result["scientific_certified"])
        self.assertFalse(result["result"]["PASS"])
        self.assertEqual(result["result"]["fresh_ac_calls"], 1)
        calls = bridge.registry.resolve("v42_may_campaign_native90.operations").calls
        self.assertEqual([call[0] for call in calls], ["freeze", "actual_sources", "actual", "fresh"])

    def test_native_actual_rejects_schedule_mutation_before_fresh(self):
        bridge, frozen, _, _ = self.frozen()
        class MutatingBackend:
            authority_sha = bridge.context.request.authority.grid_sha
            calls = 0
            def reconstruct_physical(self, schedule, realized):
                schedule["known_job_actions"]["FAKE_UID"]["slot"] = 99
                return {}
            def fresh_ac(self, physical):
                self.calls += 1
        backend = MutatingBackend()
        with self.assertRaisesRegex(ValueError, "FROZEN_PLAN_CHANGED"):
            bridge.actual(frozen, {"load": [], "pv": [], "aidc_state": {}}, backend=backend)
        self.assertEqual(backend.calls, 0)

    def test_injected_backend_grid_sha_must_match(self):
        bridge, frozen, _, _ = self.frozen()
        with self.assertRaisesRegex(ValueError, "GRID_AUTHORITY_DRIFT"):
            bridge.actual(frozen, {"load": [], "pv": [], "aidc_state": {}},
                backend=SimpleNamespace(authority_sha=digest({"other_feeder": 8500})))

    def test_source_freeze_original_schema_not_overwritten(self):
        bridge, frozen, requests, outputs = self.frozen()
        before = frozen.sha
        with self.assertRaisesRegex(ValueError, "NEVER_OVERWRITTEN"):
            bridge.freeze(requests, outputs, verify_stage=lambda request, output: True)
        self.assertEqual(before, frozen.sha)


if __name__ == "__main__":
    unittest.main()

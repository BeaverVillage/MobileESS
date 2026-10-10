import ast
from dataclasses import replace
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from v42_b3_joint.build_runtime import BuildIdentity, BuildProfile, ImmutableInputCache, compare_profiles
from v42_b3_joint.contracts import canonical, digest
from v42_b3_joint.dry_run import fixture_authority, fixture_aidc, fixture_mess
from v42_b3_joint.source_runtime import RealStageContext, SourceRegistry, FakeSourceRegistry, SourceStageOutput
from v42_b3_joint.source_coordinator import SourceCoordinator, output_document, output_from_document, verify_output
from v42_b3_joint.source_guard import SourceGuardAliases


class FixtureLedger:
    def __init__(self, context):
        self.context = context
        context.output.mkdir(parents=True, exist_ok=True)

    def receipt(self):
        return {**self.context.identity, "evidence_kind": "FAKE_SOURCE_TEST", "Threads": 1,
                "P2_calls": 0, "native_limit_seconds": 5400, "wall_limit_seconds": None,
                "quarantined": False, "measured_native_runtime": 0, "native_call_count": 0}

    def sealed_receipt(self):
        return canonical(self.receipt())


class FixtureBridge:
    def __init__(self):
        self.executions, self.verifications, self.fail, self.corrupt = [], [], None, False

    def execute(self, context, ledger, progress=None):
        stage = context.request.stage
        self.executions.append(stage)
        if stage == self.fail:
            raise ValueError("FIXTURE_SOURCE_FAILURE")
        output = SourceStageOutput(context.request, {}, context.request.fixed_aidc or fixture_aidc(1 if stage == "A1" else 2),
            None if stage == "A1" else context.request.fixed_mess or fixture_mess(1 if stage == "M1" else 2),
            digest(context.identity), {}, {}, {"synthetic_fixture_only": True}, ledger.sealed_receipt(), "FAKE_SOURCE_TEST")
        proof = self.verify(context, output)
        return replace(output, physical_evidence=proof["physical"], global_evidence=proof["global"])

    def verify(self, context, output):
        self.verifications.append(context.request.stage)
        if self.corrupt:
            raise ValueError("FIXTURE_INDEPENDENT_REPLAY_FAILURE")
        verifier = digest("TEST_CALLBACK_NO_SCIENTIFIC_PROOF")
        physical = {**output.identity, "original_integer_physical_verified": True,
                    "replay_sha": digest(output.decision_sha), "verifier_source_sha": verifier}
        bounds = {**output.identity, "original_global_bound_verified": True, "exact_LB": "1", "exact_UB": "1",
                  "bound_scope": "STAGE_FIXED_INPUT_GLOBAL", "global_domain_sha": context.request.authority.physical_domain_sha,
                  "verifier_source_sha": verifier, "joint_global_optimality_claim": False}
        return {"PASS": True, "physical": physical, "global": bounds, "original_model_sha": output.model_sha,
                "evidence_kind": "FAKE_SOURCE_TEST"}


class CoordinatorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.root = self.base / "output"
        self.authority = fixture_authority()
        self.registry = FakeSourceRegistry()
        self.grid = object()
        self.bridge = FixtureBridge()

    def coordinator(self, registry=None):
        def factory(request, packets, path):
            return RealStageContext(request, self.base / "input", path,
                canonical({"day": request.authority.day}), registry or self.registry, self.grid, packets,
                request.authority.source_sha, "SOURCE_FIXTURE")
        return SourceCoordinator(self.root, factory, self.bridge, self.bridge, ledger_factory=FixtureLedger)

    def test_sequential_full_fixed_chain_and_serialization(self):
        result = self.coordinator().run(self.authority)
        self.assertEqual(self.bridge.executions, ["A1", "M1", "A2", "M2"])
        a1, m1, a2, m2 = result["outputs"]
        self.assertEqual(m1.aidc, a1.aidc)
        self.assertEqual(a2.mess, m1.mess)
        self.assertEqual(m2.aidc, a2.aidc)
        self.assertEqual(output_from_document(output_document(m2)).sha, m2.sha)
        self.assertEqual(result["evidence_kind"], "FAKE_SOURCE_TEST")

    def test_resume_reruns_each_independent_source_verifier_without_execution(self):
        first = self.coordinator().run(self.authority)
        old = len(self.bridge.verifications)
        second = self.coordinator().run(self.authority)
        self.assertEqual(len(self.bridge.executions), 4)
        self.assertEqual(len(self.bridge.verifications) - old, 4)
        self.assertEqual([o.sha for o in first["outputs"]], [o.sha for o in second["outputs"]])

    def test_resume_rejects_invalid_source_replay(self):
        self.coordinator().run(self.authority)
        self.bridge.corrupt = True
        with self.assertRaisesRegex(ValueError, "INDEPENDENT_REPLAY"):
            self.coordinator().run(self.authority)
        state = json.loads((self.root / "B3_SOURCE_CHECKPOINT.json").read_text())
        self.assertEqual(state["status"], "QUARANTINED")

    def test_independent_acceptance_rejects_measured_budget_overshoot_without_reset(self):
        coordinator = self.coordinator()
        output = coordinator.run(self.authority)["outputs"][0]
        context, ledger = coordinator.contexts["A1"], coordinator.ledgers["A1"]
        measured = dict(ledger.receipt(), measured_native_runtime=5400)
        ledger.receipt = lambda: dict(measured)
        at_limit = replace(output, ledger_receipt=canonical(measured))
        verify_output(context, at_limit, self.bridge, ledger)
        measured["measured_native_runtime"] = 5400.25
        overshoot = replace(output, ledger_receipt=canonical(measured))
        before = len(self.bridge.verifications)
        with self.assertRaisesRegex(ValueError, "SOURCE_LEDGER_NOT_ACCEPTED"):
            verify_output(context, overshoot, self.bridge, ledger)
        self.assertEqual(ledger.receipt()["measured_native_runtime"], 5400.25)
        self.assertEqual(len(self.bridge.verifications), before)

    def test_incomplete_stage_never_resets_or_advances(self):
        self.bridge.fail = "M1"
        with self.assertRaisesRegex(ValueError, "SOURCE_FAILURE"):
            self.coordinator().run(self.authority)
        state = json.loads((self.root / "B3_SOURCE_CHECKPOINT.json").read_text())
        self.assertEqual(state["completed"], ["A1"])
        self.assertEqual(state["inflight"], "M1")
        with self.assertRaisesRegex(ValueError, "QUARANTINE"):
            self.coordinator().run(self.authority)
        self.assertEqual(self.bridge.executions, ["A1", "M1"])

    def test_tampered_completed_output_rejected_before_next_stage(self):
        self.coordinator().run(self.authority)
        path = self.root / "A1" / "B3_SOURCE_STAGE_OUTPUT.json"
        doc = json.loads(path.read_text())
        doc["source_packet"]["synthetic_fixture_only"] = False
        path.write_text(canonical(doc))
        with self.assertRaisesRegex(ValueError, "PERSISTENCE_SHA_DRIFT"):
            self.coordinator().run(self.authority)

    def test_real_gate_before_output(self):
        # Actual context requires the isolated production runtime location.
        from v42_b3_joint.contracts import StageRequest
        root = Path(__file__).resolve().parents[1] / "runtime" / "b3" / "gate_only_fixture"
        registry = SourceRegistry()
        def factory(req, packets, path):
            return RealStageContext(req, self.base / "input", path, canonical({"day": req.authority.day}),
                registry, object(), packets, req.authority.source_sha, "CLOSED_GATE")
        coordinator = SourceCoordinator(root, factory, self.bridge, self.bridge)
        with self.assertRaises(PermissionError):
            coordinator.run(self.authority)
        self.assertFalse(root.exists())


class BuildRuntimeTests(unittest.TestCase):
    def identity(self, worker="W1", day="2025-05-23", fixed="M1"):
        return BuildIdentity(worker, day, digest("inputs"), digest("source"), digest("domain"), digest("grid"), digest(fixed))

    def test_cache_hits_reverify_inputs_and_do_not_share_mutable_values(self):
        identity = self.identity()
        cache = ImmutableInputCache(identity)
        calls = []
        data = [1, [2, 3]]
        def verify():
            calls.append("verify")
            return {"PASS": True, "input_sha": identity.input_sha}
        first = cache.get(identity, "route_indices", identity.input_sha, lambda: data, verify)
        data[1].append(4)
        second = cache.get(identity, "route_indices", identity.input_sha, lambda: self.fail("duplicate build"), verify)
        self.assertEqual(first, (1, (2, 3)))
        self.assertIs(first, second)
        self.assertEqual(calls, ["verify", "verify"])
        self.assertEqual(cache.receipt()["hits"], 1)

    def test_worker_date_and_fixed_inputs_cannot_share(self):
        identity = self.identity()
        cache = ImmutableInputCache(identity)
        for other in (self.identity(worker="W2"), self.identity(day="2025-05-24"), self.identity(fixed="M2")):
            with self.assertRaisesRegex(ValueError, "DRIFT"):
                cache.get(other, "routes", identity.input_sha, lambda: (), lambda: {})

    def test_cached_source_models_forbidden(self):
        identity = self.identity()
        cache = ImmutableInputCache(identity)
        with self.assertRaisesRegex(ValueError, "IMMUTABLE_INPUTS"):
            cache.get(identity, "Model", identity.input_sha, lambda: SimpleNamespace(Model=True),
                      lambda: {"PASS": True, "input_sha": identity.input_sha})

    def test_equal_scope_profiles_and_mismatched_scope_rejected(self):
        ticks = iter([0., 4., 4., 6.])
        old = BuildProfile(digest("scope"), "FIXTURE_BASELINE", clock=lambda: next(ticks))
        new = BuildProfile(digest("scope"), "FIXTURE_OPTIMIZED", clock=lambda: next(ticks))
        with old.phase("total_preparation"):
            pass
        with new.phase("total_preparation"):
            pass
        comparison = compare_profiles(old.receipt(), new.receipt())
        self.assertEqual(comparison["phases"]["total_preparation"]["speedup"], 2)
        self.assertEqual(comparison["evidence_kind"], "FIXTURE")
        changed = dict(new.receipt(), scope_sha=digest("different"))
        with self.assertRaisesRegex(ValueError, "SCOPE_DRIFT"):
            compare_profiles(old.receipt(), changed)


class SourceRouterTests(unittest.TestCase):
    def test_original_backstop_requires_exact_ledgered_model_and_restores_new_aliases(self):
        from v42_b3_joint.contracts import StageRequest
        with tempfile.TemporaryDirectory() as directory:
            authority = fixture_authority()
            registry = FakeSourceRegistry()
            context = RealStageContext(StageRequest("A1", authority), Path(directory) / "input",
                Path(directory) / "output", canonical({"day": authority.day}), registry, object(), {},
                authority.source_sha, "GUARD_FIXTURE")
            def old(*args, **kwargs):
                raise PermissionError("ORIGINAL_TEST_GUARD")
            def old_authorize(*args, **kwargs):
                return old(*args, **kwargs)
            def old_tag(*args, **kwargs):
                return old(*args, **kwargs)
            execution = SimpleNamespace(require_action_authorized=old_authorize, guard_model_optimize=old,
                tag_model_for_day=old_tag, day_from_authority=lambda value: value.get("day"))
            model = SimpleNamespace(Params=SimpleNamespace(Threads=1))
            other = SimpleNamespace(Params=SimpleNamespace(Threads=1))
            with registry.execution_scope(context):
                aliases = SourceGuardAliases(context, execution)
                aliases.route(execution)
                loaded_after = SimpleNamespace(tag_model_for_day=execution.tag_model_for_day,
                    imported_guard=execution.guard_model_optimize)
                aliases.route(loaded_after)
                execution.tag_model_for_day(model, {"day": authority.day})
                with self.assertRaisesRegex(ValueError, "LEDGERED"):
                    execution.guard_model_optimize(model)
                with registry.native_scope(model, "P1", "A"):
                    execution.guard_model_optimize(model)
                    with self.assertRaisesRegex(ValueError, "LEDGERED"):
                        execution.guard_model_optimize(other)
                aliases.restore()
                self.assertIs(execution.guard_model_optimize, old)
                self.assertIs(loaded_after.imported_guard, old)
                self.assertIs(loaded_after.tag_model_for_day, old_tag)

    def test_late_transitive_alias_is_restored_when_source_raises(self):
        import sys
        from types import ModuleType
        from unittest.mock import patch
        from v42_b3_joint.source_guard import compatibility_scope
        from v42_b3_joint.contracts import StageRequest
        with tempfile.TemporaryDirectory() as directory:
            authority = fixture_authority()
            def authorize(*args, **kwargs):
                pass
            def guard(*args, **kwargs):
                pass
            def tag(*args, **kwargs):
                pass
            execution = SimpleNamespace(__b3_fake__=True, require_action_authorized=authorize,
                guard_model_optimize=guard, tag_model_for_day=tag,
                day_from_authority=lambda value: value.get("day"))
            registry = FakeSourceRegistry({"v42_a_stage_domain_v2.execution": execution})
            context = RealStageContext(StageRequest("A1", authority), Path(directory) / "input",
                Path(directory) / "output", canonical({"day": authority.day}), registry, object(), {},
                authority.source_sha, "LATE_ALIAS")
            loaded_after = ModuleType("v42_fixture_delayed")
            with patch.dict(sys.modules), registry.execution_scope(context):
                with self.assertRaisesRegex(ValueError, "SOURCE_EXCEPTION"):
                    with compatibility_scope(context):
                        loaded_after.tag_model = execution.tag_model_for_day
                        sys.modules[loaded_after.__name__] = loaded_after
                        raise ValueError("SOURCE_EXCEPTION")
                self.assertIs(loaded_after.tag_model, tag)
                self.assertIs(execution.tag_model_for_day, tag)

    def test_original_input_packets_bind_semantic_bundle_and_raw_sha(self):
        from v42_b3_joint.source_runtime import source_input_identity
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder / "NATIVE_INPUT.json").write_text(canonical({"day": "2025-05-23", "authority": "fixture"}))
            (folder / "WINDOWS.json").write_text(canonical({"WINDOWS": "fixture"}))
            first = source_input_identity(folder)
            self.assertEqual(first["bundle"]["day"], "2025-05-23")
            (folder / "WINDOWS.json").write_text(canonical({"WINDOWS": "drift"}))
            second = source_input_identity(folder)
            self.assertNotEqual(first["input_sha"], second["input_sha"])

    def test_real_ast_routing_retains_source_calculations_and_import_aliases(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            folder = root / "v42_fixture"
            folder.mkdir()
            path = folder / "model.py"
            path.write_text('def build(x):\n from anywhere import authority as GridAuthority\n return "M1", GridAuthority(), 7*x + 3\n')
            module = SimpleNamespace(__b3_fake__=True)
            registry = FakeSourceRegistry({"v42_fixture.model": module}, root=root)
            result = SourceRegistry.rebind(registry, "v42_fixture.model", "build",
                literal_replacements={"M1": "M2"}, import_replacements={"GridAuthority": lambda: "A2-fixed"})
            self.assertEqual(result(5), ("M2", "A2-fixed", 38))
            self.assertFalse(registry.audit[-1]["numeric_scientific_constants_changed"])
            with self.assertRaisesRegex(ValueError, "NUMERIC"):
                SourceRegistry.rebind(registry, "v42_fixture.model", "build", literal_replacements={7: 8})

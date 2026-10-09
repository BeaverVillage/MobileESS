"""Admission and reuse integrity regressions; these do not claim a real canary."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import json
import pickle
import gzip
import unittest
from unittest.mock import patch

from v42_b3_joint.contracts import canonical, digest
from v42_b3_joint.policy import require_production_authorization
from v42_autonomous_b3.admission import (checked, record, validate_request, verify_qualification,
                                        execution_permit, source_seal, validate_seal, qualification_status,
                                        scientific_run_id, publish_qualification)
from v42_autonomous_b3.reuse import compare_original_identity, graph_compiler_equivalence, GRAPH_CACHE_COMPILERS, B1A1ReuseBridge
from v42_autonomous_b3.ledger import prior_prefix
from v42_autonomous_b3.worker import b1_origin, original_domain_sha
from v42_autonomous_b3.diagnostic import native_zero_diagnostic
from v42_autonomous_b3.accounting import collect_native_accounting
from v42_a_stage_domain_v2 import AUTHORITY as ORIGINAL_DOMAIN_AUTHORITY


class AdmissionTests(unittest.TestCase):
    def scoped_request(self, root, day="2025-05-02"):
        for name in ("v42_b3_joint/source_coordinator.py", "v42_autonomous_b3/worker.py"):
            path = root / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text("original")
        return dict(arm="B3", day=day, worker_slot=1, code_root=str(root),
                    output=str(root / "runtime/b3" / day / "attempt"), campaign_root=str(root / "campaign"),
                    attempt_id="a", run_id="campaign", canary=True), source_seal(root)

    def test_boolean_flags_do_not_open_gate(self):
        import v42_b3_joint.policy as policy
        before = policy.B3_NATIVE_EXECUTION_AUTHORIZED
        try:
            policy.B3_NATIVE_EXECUTION_AUTHORIZED = True
            with self.assertRaisesRegex(PermissionError, "PRODUCTION_NOT_AUTHORIZED"):
                require_production_authorization("NATIVE")
        finally:
            policy.B3_NATIVE_EXECUTION_AUTHORIZED = before

    def test_exactly_one_worker_and_isolated_attempt_required(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            request = dict(arm="B3", day="2025-05-01", worker_slot=1, code_root=str(root),
                           output=str(root / "runtime/b3/day/attempt"), campaign_root=str(root / "campaign"),
                           attempt_id="a", run_id="r")
            validate_request(request)
            for slot in (0, 2, True, "1"):
                with self.assertRaises(ValueError):
                    validate_request(dict(request, worker_slot=slot))
            with self.assertRaises(ValueError):
                validate_request(dict(request, output=str(root / "campaign/dates/B1")))

    def test_source_and_historical_result_receipts_detect_tamper(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            for name in ("v42_b3_joint/source_coordinator.py", "v42_autonomous_b3/worker.py"):
                path = root / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text("original")
            seal = source_seal(root)
            validate_seal(seal, root)
            path = root / "v42_autonomous_b3/worker.py"
            receipt = record(path)
            path.write_text("modified")
            with self.assertRaisesRegex(ValueError, "SEALED_FILE_SHA_DRIFT"):
                checked(receipt)
            with self.assertRaisesRegex(ValueError, "SOURCE_SEAL_FILE_DRIFT"):
                validate_seal(seal, root)

    def test_fake_and_incomplete_canary_cannot_promote(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "qualification.json"
            document = dict(schema="B3_REAL_CANARY_QUALIFICATION_V1", source_sha=digest("s"),
                            day="2025-05-01", worker_count=1, evidence_kind="FAKE_SOURCE_TEST")
            path.write_text(canonical(document))
            with self.assertRaisesRegex(ValueError, "REAL_SOURCE_MATCHED"):
                verify_qualification(path, digest("s"))
            document.update(evidence_kind="SOURCE", canary_output=folder, artifacts=[])
            (Path(folder) / "B3_SOURCE_CHECKPOINT.json").write_text(canonical({
                "status": "STAGES_COMPLETE", "inflight": None, "completed": ["A1", "M1", "A2", "M2"]}))
            path.write_text(canonical(document))
            with self.assertRaisesRegex(ValueError, "FULL_PIPELINE_INCOMPLETE"):
                verify_qualification(path, digest("s"))

    def test_failed_first_canary_allows_next_scoped_date_without_promotion(self):
        with TemporaryDirectory() as folder:
            root = Path(folder); request, seal = self.scoped_request(root)
            previous = root / "may01_failed"; previous.mkdir()
            (previous / "B3_SOURCE_CHECKPOINT.json").write_text(canonical(dict(status="FAILED")))
            qualification = root / "qualification.json"
            qualification.write_text(canonical(dict(schema="B3_REAL_CANARY_QUALIFICATION_V1",
                source_sha=seal["source_sha"], day="2025-05-01", worker_count=1, evidence_kind="SOURCE",
                canary_output=str(previous), artifacts=[])))
            status = qualification_status(qualification, seal["source_sha"], seal=seal, code_root=root)
            self.assertEqual(status["status"], "INVALID_DAY_EVIDENCE")
            self.assertFalse(status["qualified"])
            with execution_permit(request, seal) as permit:
                self.assertEqual(permit.day, "2025-05-02")
                self.assertEqual(permit.mode, "USER_AUTHORIZED_REAL_CANARY")
            with execution_permit(dict(request, day="2025-05-31"), seal) as permit:
                self.assertEqual(permit.day, "2025-05-31")
            with self.assertRaisesRegex(ValueError, "FULL_PIPELINE_INCOMPLETE"):
                with execution_permit(dict(request, canary=False, qualification=str(qualification)), seal):
                    pass
            self.assertEqual(qualification_status(None, seal["source_sha"])["status"], "ABSENT")
            (root / "v42_autonomous_b3/worker.py").write_text("corrupt")
            status = qualification_status(qualification, seal["source_sha"], seal=seal, code_root=root)
            self.assertEqual(status["status"], "GLOBAL_SOURCE_INTEGRITY_FAILURE")
            self.assertTrue(status["global_source_block"])
            with self.assertRaisesRegex(ValueError, "SOURCE_SEAL_FILE_DRIFT"):
                with execution_permit(request, seal):
                    pass

    def test_source_mismatch_and_fake_later_day_qualification_never_promote(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "qualification.json"
            path.write_text(canonical(dict(source_sha=digest("old_source"))))
            self.assertEqual(qualification_status(path, digest("new_source"))["status"], "SOURCE_MISMATCH")
            path.write_text(canonical(dict(schema="B3_REAL_CANARY_QUALIFICATION_V1", source_sha=digest("new_source"),
                day="2025-05-21", qualified_day="2025-05-21", worker_count=1, evidence_kind="FAKE_SOURCE_TEST")))
            self.assertEqual(qualification_status(path, digest("new_source"))["status"], "INVALID_DAY_EVIDENCE")

    def test_publication_binds_completed_checkpoint_day_then_runs_verifier(self):
        # Tests publication plumbing only; a mocked verifier does not prove a
        # real SOURCE canary, and this temporary artifact is never promoted.
        with TemporaryDirectory() as folder:
            root = Path(folder); pipeline = root / "pipeline"; pipeline.mkdir()
            (pipeline / "B3_SOURCE_CHECKPOINT.json").write_text(canonical(dict(identity=dict(day="2025-05-23"))))
            for name in ("B3_SOURCE_ACTUAL_RESULT.json", "B3_SOURCE_VALIDATION.json"):
                (pipeline / name).write_text("{}")
            for stage in ("A1", "M1", "A2", "M2"):
                (pipeline / stage).mkdir(); (pipeline / stage / "B3_SOURCE_STAGE_OUTPUT.json").write_text("{}")
            def verify(path, source):
                document = json.loads(Path(path).read_text())
                self.assertEqual(document["qualified_day"], "2025-05-23")
                self.assertEqual(document["day"], "2025-05-23")
                return document
            with patch("v42_autonomous_b3.admission.verify_qualification", side_effect=verify) as verifier:
                receipt = publish_qualification(pipeline, digest("source"), root / "qualification.json")
                self.assertEqual(verifier.call_count, 1)
                checked(receipt)

    def test_scientific_run_alias_preserves_valid_ids_and_binds_transport_identity(self):
        self.assertEqual(scientific_run_id(dict(run_id="valid_run-01")), "valid_run-01")
        original = "may2025_b2_b3_fresh_20261009T172421_999933+0000"
        alias = scientific_run_id(dict(run_id=original))
        self.assertRegex(alias, r"^[A-Za-z0-9_-]{1,100}$")
        self.assertNotEqual(alias, scientific_run_id(dict(run_id=original.replace("+", ":"))))
        self.assertEqual(scientific_run_id(dict(run_id=original, scientific_run_id=alias)), alias)
        with self.assertRaisesRegex(ValueError, "SCIENTIFIC_RUN_ID_BINDING_DRIFT"):
            scientific_run_id(dict(run_id=original, scientific_run_id="arbitrary_other_campaign"))


class OriginalIdentityTests(unittest.TestCase):
    def state(self, matrix="original", domain="complete", runtime="CC4-original"):
        return {"reference": SimpleNamespace(fingerprint=lambda: digest(matrix)),
                "compact": SimpleNamespace(fingerprint=lambda: digest(matrix)),
                "domains": {"job": SimpleNamespace(sha=digest(domain))},
                "data": ({"day": "2025-05-01", "runtime": runtime}, {"job": object()})}

    def test_exact_original_problem_accepts_without_new_optimize(self):
        receipt = {"verification": {"reference_snapshot_sha256": digest("original")}}
        evidence = compare_original_identity(self.state(), self.state(), receipt, digest)
        self.assertTrue(evidence["PASS"])
        self.assertTrue(evidence["full_integer_domain_preserved"])

    def test_matrix_domain_objective_and_runtime_mismatches_block_reuse(self):
        receipt = {"verification": {"reference_snapshot_sha256": digest("original")}}
        for fresh in (self.state(matrix="weakened"), self.state(domain="pruned"), self.state(runtime="changed")):
            with self.assertRaises(ValueError):
                compare_original_identity(fresh, self.state(), receipt, digest)


class B1OriginTests(unittest.TestCase):
    def test_new_campaign_follows_sealed_original_receipts_across_attempts(self):
        with TemporaryDirectory() as folder:
            root = Path(folder); old = root / "old"; new = root / "restart"
            b1 = old / "source/May19/output"; inputs = old / "inputs"; final_path = old / "later_attempt/RESULT.json"
            for path in (b1, inputs, final_path.parent, new):
                path.mkdir(parents=True, exist_ok=True)
            for name in ("NATIVE_INPUT.json", "WINDOWS.json"):
                (inputs / name).write_text("{}")
            freeze = dict(PASS=True, arm="B1", day="2025-05-19", inputs={
                name: record(inputs / name) for name in ("NATIVE_INPUT.json", "WINDOWS.json")})
            (b1 / "A_NATIVE_SOURCE_FREEZE.json").write_text(canonical(freeze))
            (b1 / "A_RESULT.json").write_text(canonical(dict(PASS=True, accepted=True)))
            extra = ("A_PREPARE_RECEIPT.json", "STATIC/CAMPAIGN_INITIAL_STATE.pkl.gz", "STATIC/DATA/DATA.pkl",
                     "STATIC/DOMAIN/2025-05-19/PHYSICAL_DOMAIN_CACHE.json", "STATIC/DOMAIN/2025-05-19/PHYSICAL_DOMAIN_CACHE.pkl.gz")
            for name in extra:
                path = b1 / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text("{}")
            final = dict(PASS=True, status="PASS", identity=dict(arm="B1", day="2025-05-19"),
                         files=[record(b1 / name) for name in ("A_NATIVE_SOURCE_FREEZE.json", "A_RESULT.json", *extra)])
            final_path.write_text(canonical(final))
            manifest = dict(origin_campaign_root=str(old), B1_results={"B1/2025-05-19": record(final_path)})
            (new / "AUTONOMOUS_MANIFEST.json").write_text(canonical(manifest))
            request = dict(campaign_root=str(new), day="2025-05-19")
            self.assertEqual(b1_origin(request), (b1.resolve(), inputs.resolve()))
            (b1 / "A_RESULT.json").write_text(canonical(dict(PASS=True, accepted=False)))
            with self.assertRaisesRegex(ValueError, "SEALED_FILE_SHA_DRIFT"):
                b1_origin(request)

    def test_domain_authority_expands_all_members_not_only_representatives(self):
        with TemporaryDirectory() as folder:
            b1 = Path(folder); domain = b1 / "STATIC/DOMAIN/2025-05-01"
            domain.mkdir(parents=True)
            roster = dict(a=digest("domain-a"), b=digest("domain-a"), c=digest("domain-c"))
            expected = digest(roster)
            data = ({}, dict(a=1, b=2, c=3), {}, {}, None, None, None,
                    dict(classes=dict(first=["a", "b"], second=["c"]), physical_domain_hash=expected))
            path = domain / "DATA.pkl"; path.write_bytes(pickle.dumps(data))
            receipt = dict(PASS=True, day="2025-05-01", scientific_candidates_removed=0,
                           jobs=3, representatives=2,
                           complete_domain_hashes=dict(a=roster["a"], c=roster["c"]), frozen_DATA=record(path))
            (domain / "PHYSICAL_DOMAIN_CACHE.json").write_text(canonical(receipt))
            self.assertEqual(original_domain_sha(b1, "2025-05-01"), expected)
            # Real original DATA is frozen before that metadata is added.
            old_data = (*data[:7], dict(classes=data[7]["classes"]))
            path.write_bytes(pickle.dumps(old_data))
            receipt["frozen_DATA"] = record(path)
            (domain / "PHYSICAL_DOMAIN_CACHE.json").write_text(canonical(receipt))
            initial_path = b1 / "STATIC/CAMPAIGN_INITIAL_STATE.pkl.gz"
            active_data = (dict(data[0], aidc_domain_authority=ORIGINAL_DOMAIN_AUTHORITY), *data[1:])
            with gzip.open(initial_path, "wb") as stream:
                pickle.dump(dict(data=active_data, domains={uid: SimpleNamespace(sha=sha) for uid, sha in roster.items()}), stream)
            preparation = dict(PASS=True, day="2025-05-01", arm="B1", Native_calls=0, state=record(initial_path))
            (b1 / "A_PREPARE_RECEIPT.json").write_text(canonical(preparation))
            self.assertEqual(original_domain_sha(b1, "2025-05-01"), expected)
            corrupted_data = (*active_data[:7], dict(data[7], physical_domain_hash=digest("different")))
            with gzip.open(initial_path, "wb") as stream:
                pickle.dump(dict(data=corrupted_data, domains={uid: SimpleNamespace(sha=sha) for uid, sha in roster.items()}), stream)
            preparation["state"] = record(initial_path)
            (b1 / "A_PREPARE_RECEIPT.json").write_text(canonical(preparation))
            with self.assertRaisesRegex(ValueError, "SCIENTIFIC_HASH_DRIFT"):
                original_domain_sha(b1, "2025-05-01")


class DiagnosticTests(unittest.TestCase):
    def test_all_native_entry_blocked_during_entire_diagnostic(self):
        class Model:
            def optimize(self):
                raise AssertionError("unguarded optimizer reached")
        def read_model(path):
            return Model()
        gp = SimpleNamespace(Model=Model, read=read_model)
        with patch.dict("sys.modules", gurobipy=gp):
            with native_zero_diagnostic():
                with self.assertRaisesRegex(PermissionError, "NATIVE_ZERO_PREPARE"):
                    gp.Model().optimize()
                with self.assertRaisesRegex(PermissionError, "UNGUARDED_MODEL_LOAD_FORBIDDEN"):
                    gp.read("old.mps")
                with self.assertRaisesRegex(PermissionError, "ALL_NATIVE_ENTRY_FORBIDDEN"):
                    require_production_authorization("NATIVE_OPTIMIZE")
            self.assertIs(gp.Model, Model)
            self.assertIs(gp.read, read_model)


class GraphCompilerTests(unittest.TestCase):
    def registry(self, root):
        for relative in GRAPH_CACHE_COMPILERS:
            path = root / relative; path.parent.mkdir(parents=True, exist_ok=True); path.write_text(relative)
        return SimpleNamespace(root=root, source_manifest={name: record(root / name)["sha256"] for name in GRAPH_CACHE_COMPILERS})

    def test_exact_blob_equivalence_admits_graphs_without_native(self):
        with TemporaryDirectory() as folder:
            registry = self.registry(Path(folder))
            with patch("v42_autonomous_b3.reuse.subprocess.check_output", side_effect=lambda command, **kw:
                       (registry.root / command[-1].split(":", 1)[1]).read_bytes()):
                proof = graph_compiler_equivalence(registry, "a" * 40)
            self.assertTrue(proof["PASS"])
            self.assertEqual(proof["Native_calls"], 0)
            self.assertEqual(len(proof["compiler_files"]), 8)

    def test_unproven_graph_cache_rebuilds_and_current_source_corruption_blocks(self):
        with TemporaryDirectory() as folder:
            registry = self.registry(Path(folder))
            with patch("v42_autonomous_b3.reuse.subprocess.check_output", return_value=b"different compiler"):
                proof = graph_compiler_equivalence(registry, "a" * 40)
            self.assertFalse(proof["PASS"])
            self.assertTrue(proof["fresh_original_graphs_required"])
            context = SimpleNamespace(source_registry=registry, output=Path(folder),
                request=SimpleNamespace(authority=SimpleNamespace(day="2025-05-01")), producer_source_sha=digest("source"))
            bridge = B1A1ReuseBridge(Path(folder) / "b1")
            with patch.object(bridge, "_cache_packet", return_value=dict(origin_commit="a" * 40)), \
                 patch("v42_autonomous_b3.reuse.graph_compiler_equivalence", return_value=proof):
                self.assertFalse(bridge._seed_input_cache(context, {}, object(), Path(folder)))
            document = json.loads((Path(folder) / "B1_GRAPH_COMPILER_EQUIVALENCE.json").read_text())
            self.assertFalse(document["graph_cache_reused"])
            self.assertEqual(document["Native_calls"], 0)
            (registry.root / GRAPH_CACHE_COMPILERS[0]).write_text("corrupt current source")
            with self.assertRaisesRegex(ValueError, "SOURCE_FILE_SHA_DRIFT"):
                graph_compiler_equivalence(registry, "a" * 40)


class PriorNativeTests(unittest.TestCase):
    def context(self, root):
        return SimpleNamespace(output=root / "new/A1", request=SimpleNamespace(stage="M1",
            authority=SimpleNamespace(day="2025-05-01", input_sha=digest("input"))))

    def attempt(self, root, name, calls, *, inflight=None):
        attempt = root / name
        stage = attempt / "PIPELINE/M1"
        stage.mkdir(parents=True)
        identity = dict(stage="M1", day="2025-05-01", input_sha=digest("input"), native_limit_seconds=5400)
        (stage / "NATIVE_RUNTIME_LEDGER_IDENTITY.json").write_text(canonical(identity))
        document = dict(calls=calls, inflight=inflight,
                        measured_Native_Runtime=sum(row.get("Native_Runtime") or 0 for row in calls))
        (stage / "NATIVE_RUNTIME_LEDGER.json").write_text(canonical(document))
        return attempt

    def test_prior_cumulative_prefix_is_counted_once(self):
        with TemporaryDirectory() as folder:
            root = Path(folder); first = {"Native_Runtime": 12., "runtime_unavailable": False}
            second = {"Native_Runtime": 9., "runtime_unavailable": False}
            a = self.attempt(root, "a", [first]); b = self.attempt(root, "b", [first, second])
            calls, receipts = prior_prefix(self.context(root), [a, b])
            self.assertEqual(sum(row["Native_Runtime"] for row in calls), 21.)
            self.assertEqual(len(receipts), 4)

    def test_unknown_runtime_and_disjoint_attempts_do_not_become_zero(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            a = self.attempt(root, "a", [{"Native_Runtime": None, "runtime_unavailable": True}])
            with self.assertRaisesRegex(ValueError, "UNKNOWN_NATIVE_RUNTIME_QUARANTINE"):
                prior_prefix(self.context(root), [a])
            b = self.attempt(root, "b", [{"Native_Runtime": 1., "runtime_unavailable": False}])
            c = self.attempt(root, "c", [{"Native_Runtime": 2., "runtime_unavailable": False}])
            with self.assertRaisesRegex(ValueError, "DISJOINT_NATIVE_ATTEMPTS"):
                prior_prefix(self.context(root), [b, c])


class FailureAccountingTests(unittest.TestCase):
    identity = dict(run_id="r", day="2025-05-01", source_SHA=digest("source"))

    def ledger(self, pipeline, stage, seconds, *, inflight=None):
        folder = pipeline / stage; folder.mkdir(parents=True)
        (folder / "NATIVE_RUNTIME_LEDGER_IDENTITY.json").write_text(canonical(dict(
            run_id="r", day="2025-05-01", stage=stage, source_sha=digest("source"), input_sha=digest("input"), native_limit_seconds=5400)))
        document = dict(Native_ceiling_seconds=5400, budget_basis="MEASURED_NATIVE_RUNTIME_ONLY",
                        measured_Native_Runtime=seconds, inflight=inflight,
                        calls=[dict(Native_Runtime=seconds, entered_native=True, runtime_unavailable=False)])
        (folder / "NATIVE_RUNTIME_LEDGER.json").write_text(canonical(document))

    def test_failed_run_preserves_measured_stage_budget_not_total_budget(self):
        with TemporaryDirectory() as folder:
            pipeline = Path(folder)
            self.ledger(pipeline, "M1", 4000.)
            self.ledger(pipeline, "A2", 3000.)
            result = collect_native_accounting(pipeline, self.identity)
            self.assertEqual(result["Native_Runtime"], 7000.)
            self.assertEqual(result["stage_native_runtime"]["M1"], 4000.)
            self.assertEqual(result["stage_native_accounting"]["A1"], "NOT_ENTERED")
            self.assertEqual(result["stage_native_accounting"]["M1"], "MEASURED")
            self.assertEqual(result["stage_native_calls"]["A2"], 1)
            checked(result["stage_native_ledger_receipts"]["M1"])

    def test_retry_failed_before_stage_does_not_erase_prior_stage_cost(self):
        with TemporaryDirectory() as folder:
            root = Path(folder); old = root / "old/PIPELINE"; new = root / "new/PIPELINE"
            self.ledger(old, "M1", 4100.)
            result = collect_native_accounting(new, self.identity, [old.parent])
            self.assertEqual(result["Native_Runtime"], 4100.)
            self.assertEqual(result["stage_native_accounting"]["M1"], "MEASURED")
            self.assertEqual(Path(result["stage_native_ledger_receipts"]["M1"]["path"]).parent, old / "M1")
            self.ledger(new, "M1", 12.)
            result = collect_native_accounting(new, self.identity, [old.parent])
            self.assertIsNone(result["Native_Runtime"])
            self.assertEqual(result["stage_native_accounting"]["M1"], "UNKNOWN")

    def test_interrupted_or_missing_accounting_is_unknown_never_zero(self):
        with TemporaryDirectory() as folder:
            pipeline = Path(folder)
            self.ledger(pipeline, "M1", 12., inflight=dict(component="P1"))
            result = collect_native_accounting(pipeline, self.identity)
            self.assertIsNone(result["Native_Runtime"])
            self.assertIsNone(result["stage_native_runtime"]["M1"])
            self.assertEqual(result["stage_native_accounting"]["M1"], "UNKNOWN")
            (pipeline / "M1/NATIVE_RUNTIME_LEDGER.json").unlink()
            result = collect_native_accounting(pipeline, self.identity)
            self.assertEqual(result["native_runtime_state"], "UNKNOWN")


if __name__ == "__main__":
    unittest.main()

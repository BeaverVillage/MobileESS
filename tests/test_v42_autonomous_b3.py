"""Admission and reuse integrity regressions; these do not claim a real canary."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import json
import pickle
import unittest
from unittest.mock import patch

from v42_b3_joint.contracts import canonical, digest
from v42_b3_joint.policy import require_production_authorization
from v42_autonomous_b3.admission import (checked, record, validate_request, verify_qualification,
                                        execution_permit, source_seal, validate_seal)
from v42_autonomous_b3.reuse import compare_original_identity
from v42_autonomous_b3.ledger import prior_prefix
from v42_autonomous_b3.worker import b1_origin, original_domain_sha
from v42_autonomous_b3.diagnostic import native_zero_diagnostic


class AdmissionTests(unittest.TestCase):
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
            final = dict(PASS=True, status="PASS", identity=dict(arm="B1", day="2025-05-19"),
                         files=[record(b1 / name) for name in ("A_NATIVE_SOURCE_FREEZE.json", "A_RESULT.json")])
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
                           complete_domain_hashes=dict(a=roster["a"], c=roster["c"]), frozen_DATA=record(path))
            (domain / "PHYSICAL_DOMAIN_CACHE.json").write_text(canonical(receipt))
            self.assertEqual(original_domain_sha(b1, "2025-05-01"), expected)


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


if __name__ == "__main__":
    unittest.main()

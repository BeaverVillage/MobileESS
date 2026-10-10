"""May precision admission tests using a fake solver and original budget AST.

These tests do not build or solve an AIDC/MESS model. FAKE_SOURCE_TEST receipts
exercise parameter wiring, guards and persistence; they are no scientific PASS.
"""
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

from v42_b3_joint.contracts import canonical, digest, StageRequest
from v42_b3_joint.dry_run import fixture_authority, fixture_aidc, fixture_mess
from v42_b3_joint.native_ledger import SourceStageLedger
from v42_b3_joint.numerical_policy import (apply_native_precision,
    assert_native_precision, bind_apply_precision, policy_sha, required_settings,
    verify_settings_receipt)
from v42_b3_joint.source_runtime import RealStageContext, SourceRegistry
from test_v42_b3_runtime_operations import runtime_registry


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_VERSION = "B3_MAY_PRECISION_ORIGINAL_ROWS_V1"
EXPECTED_PRECISION = {"FeasibilityTol": 1e-9, "OptimalityTol": 1e-9,
                      "NumericFocus": 3, "ScaleFlag": 2}
ALL_COMPONENTS = ("P1", "ORIGINAL_P1", "PHASE_I", "INTEGER_CONTROL",
    "NODE_LP", "LOCAL_PRICING", "FEASIBILITY_LP", "FEASIBILITY_MIP", "LP_DUAL",
    "UB", "PRICING", "RMP")
ORIGINAL_PARAMETERS = dict(Threads=1, TimeLimit=3600., Method=2, NodeMethod=1,
    MIPGap=.005, IntFeasTol=1e-5, Heuristics=.05, Cuts=-1, Seed=17, Presolve=2,
    Crossover=-1, MIPFocus=1, FeasibilityTol=1e-6, OptimalityTol=1e-6,
    NumericFocus=0, ScaleFlag=-1)
ENTRY_EVIDENCE = []  # Detached FAKE_SOURCE_TEST observations for the report.


class RecordingModel:
    """Only a parameter recorder; optimize performs no numerical computation."""
    def __init__(self, runtime=1.25, *, parameters=None, entry_hook=None):
        self.Params = SimpleNamespace(**dict(ORIGINAL_PARAMETERS, **(parameters or {})))
        self.Runtime, self.Work, self.Status, self.SolCount, self.ObjBound = runtime, 0., 2, 1, 0.
        self.parameter_writes, self.entries = [], []
        self.entry_hook = entry_hook
        # Sentinels detect accidental model-definition mutation by the adapter.
        self.original_rows, self.objective, self.integrality, self.pricing = (object() for _ in range(4))

    def setParam(self, name, value):
        self.parameter_writes.append((name, value))
        setattr(self.Params, name, value)

    def optimize(self, callback):
        if self.entry_hook is not None:
            self.entry_hook(self)
        self.entries.append(dict(parameters=deepcopy(vars(self.Params)),
            receipt=deepcopy(getattr(self, "_v42_b3_numerical_receipt", None))))


class B3NumericalPolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="b3-precision-fake-")
        self.root = Path(self.temp.name)
        self.fake_gp = ModuleType("gurobipy")
        self.fake_gp.GurobiError = type("FakeGurobiError", (Exception,), {})
        self.fake_gp.GRB = SimpleNamespace(Callback=SimpleNamespace(POLLING=0, RUNTIME=1))
        self.gp_patch = patch.dict(sys.modules, {"gurobipy": self.fake_gp})
        self.gp_patch.start()

    def tearDown(self):
        self.gp_patch.stop()
        self.temp.cleanup()

    def context(self, stage="A1", day="2025-05-25", *, registry=None, suffix=""):
        authority = fixture_authority(day)
        request = StageRequest(stage, authority,
            fixture_aidc() if stage.startswith("M") else None,
            fixture_mess() if stage == "A2" else None)
        return RealStageContext(request, self.root / "INPUT",
            self.root / day / (stage + suffix), canonical({"day": day}),
            registry or runtime_registry(), SimpleNamespace(), {}, authority.source_sha,
            "FAKE_B3_PRECISION_ONLY")

    def apply(self, model, stage="A1", component="PHASE_I", day="2025-05-25"):
        return apply_native_precision(model, day=day, stage=stage, component=component,
            evidence_kind="FAKE_SOURCE_TEST")

    def test_all_31_days_four_stages_at_original_native_entry(self):
        """124 independent original DateBudget entries see the effective values."""
        budget_source = ROOT / "v42_may_campaign_native90" / "budget.py"
        before_source_sha = hashlib.sha256(budget_source.read_bytes()).hexdigest()
        ENTRY_EVIDENCE.clear()
        seen = set()
        for number in range(1, 32):
            day = f"2025-05-{number:02d}"
            for stage in ("A1", "M1", "A2", "M2"):
                component = "PHASE_I" if stage.startswith("A") else "P1"
                with self.subTest(day=day, stage=stage):
                    context = self.context(stage, day)
                    ledger = SourceStageLedger(context)
                    captured_rows = []
                    def capture_entry(model):
                        context.source_registry.guard(model)
                        saved = json.loads(ledger.path.read_text(encoding="utf-8-sig"))
                        captured_rows.append(deepcopy(saved["inflight"]))
                    model = RecordingModel(entry_hook=capture_entry)
                    ledger.native_optimize(model, component=component, track=stage,
                        label="FAKE_ENTRY_PARAMETER_CAPTURE", requested_seconds=.5)
                    self.assertEqual(len(model.entries), 1)
                    entry = model.entries[0]
                    expected = dict(EXPECTED_PRECISION)
                    if stage.startswith("A"):
                        expected["Presolve"] = 0
                    for name, value in expected.items():
                        self.assertEqual(entry["parameters"][name], value)
                    for name, value in ORIGINAL_PARAMETERS.items():
                        if name not in expected and name != "TimeLimit":
                            self.assertEqual(entry["parameters"][name], value)
                    self.assertEqual(entry["parameters"]["TimeLimit"], .5)
                    self.assertEqual(entry["parameters"]["Threads"], 1)
                    receipt = ledger.receipt()
                    self.assertEqual(receipt["evidence_kind"], "FAKE_SOURCE_TEST")
                    self.assertEqual(receipt["numerical_policy_version"], EXPECTED_VERSION)
                    self.assertEqual(receipt["numerical_policy_sha"], policy_sha())
                    self.assertEqual(receipt["native_call_count"], 1)
                    self.assertEqual(receipt["measured_native_runtime"], 1.25)
                    self.assertEqual(receipt["remaining_seconds"], 5398.75)
                    row = receipt["calls"][0]
                    metadata = row["b3_numerical_policy"]
                    self.assertEqual(metadata, entry["receipt"])
                    self.assertEqual(metadata, captured_rows[0]["b3_numerical_policy"])
                    self.assertEqual(metadata["overrides"], expected)
                    self.assertEqual(metadata["version"], EXPECTED_VERSION)
                    self.assertEqual((metadata["day"], metadata["stage"], metadata["component"]),
                        (day, stage, component))
                    self.assertTrue(metadata["original_method_unchanged"])
                    self.assertTrue(metadata["scientific_acceptance_tolerance_unchanged"])
                    self.assertTrue(metadata["built_in_heuristics_active"])
                    self.assertEqual(metadata["heuristics_parameter"], .05)
                    self.assertFalse(metadata["heuristics_changed"])
                    self.assertFalse(metadata["scientific_certified"])
                    self.assertTrue(assert_native_precision(model, metadata,
                        day=day, stage=stage, component=component))
                    sidecar = json.loads(ledger.identity_path.read_text(encoding="utf-8-sig"))
                    self.assertEqual(sidecar["numerical_policy_version"], EXPECTED_VERSION)
                    self.assertEqual(sidecar["numerical_policy_sha"], policy_sha())
                    ENTRY_EVIDENCE.append(dict(day=day, stage=stage, component=component,
                        evidence_kind="FAKE_SOURCE_TEST", effective_parameters=metadata["effective_parameters"],
                        overrides=metadata["overrides"], metadata_content_sha=metadata["content_sha"],
                        native_limit_seconds=.5, P2_calls=0, scientific_certified=False))
                    seen.add((day, stage))
        self.assertEqual(len(seen), 124)
        self.assertEqual(hashlib.sha256(budget_source.read_bytes()).hexdigest(), before_source_sha)

    def test_component_selection_preserves_other_a_native_parameters(self):
        for stage in ("A1", "A2", "M1", "M2"):
            for component in ALL_COMPONENTS:
                with self.subTest(stage=stage, component=component):
                    model = RecordingModel()
                    before = vars(model.Params).copy()
                    receipt = self.apply(model, stage, component)
                    enabled = stage.startswith("M") or component in ("PHASE_I", "ORIGINAL_P1")
                    expected = dict(EXPECTED_PRECISION) if enabled else {}
                    if stage.startswith("A") and component == "PHASE_I":
                        expected["Presolve"] = 0
                    self.assertEqual(required_settings("2025-05-25", stage, component), expected)
                    self.assertEqual(receipt["overrides"], expected)
                    self.assertEqual(dict(model.parameter_writes), expected)
                    self.assertEqual(vars(model.Params), dict(before, **expected))
                    self.assertEqual(receipt["numerical_precision_override"], enabled)
                    self.assertEqual(receipt["solver_policy_unchanged"], not enabled)

    def test_other_a_components_and_original_p1_through_original_budget(self):
        for stage in ("A1", "A2"):
            for component in ("ORIGINAL_P1", "INTEGER_CONTROL", "LOCAL_PRICING", "LP_DUAL", "P1"):
                with self.subTest(stage=stage, component=component):
                    ledger = SourceStageLedger(self.context(stage, suffix="-" + component))
                    model = RecordingModel()
                    ledger.native_optimize(model, component=component, track=stage)
                    expected = EXPECTED_PRECISION if component == "ORIGINAL_P1" else {}
                    self.assertEqual(ledger.receipt()["calls"][0]["b3_numerical_policy"]["overrides"], expected)
                    self.assertEqual(model.entries[0]["parameters"]["Presolve"], 2)
                    self.assertEqual(model.entries[0]["parameters"]["Method"], 2)
                    self.assertEqual(model.entries[0]["parameters"]["Heuristics"], .05)
                    for name in EXPECTED_PRECISION:
                        self.assertEqual(model.entries[0]["parameters"][name],
                            expected.get(name, ORIGINAL_PARAMETERS[name]))

    def test_all_m_components_keep_original_presolve_method_and_heuristics(self):
        for stage in ("M1", "M2"):
            for component in ALL_COMPONENTS:
                with self.subTest(stage=stage, component=component):
                    ledger = SourceStageLedger(self.context(stage, suffix="-" + component))
                    model = RecordingModel(parameters={"Method": 1, "Presolve": 1, "MIPGap": .03})
                    ledger.native_optimize(model, component=component, track="M_LB")
                    actual = model.entries[0]["parameters"]
                    for name, value in EXPECTED_PRECISION.items():
                        self.assertEqual(actual[name], value)
                    self.assertEqual((actual["Method"], actual["Presolve"], actual["Heuristics"],
                        actual["MIPGap"], actual["IntFeasTol"]), (1, 1, .05, .03, 1e-5))

    def test_adapter_preserves_original_rows_objective_and_integrality(self):
        model = RecordingModel()
        sentinels = tuple(getattr(model, name) for name in
            ("original_rows", "objective", "integrality", "pricing"))
        receipt = self.apply(model, "M2", "P1")
        for name, sentinel in zip(("original_rows", "objective", "integrality", "pricing"), sentinels):
            self.assertIs(getattr(model, name), sentinel)
        for name in ("Method", "NodeMethod", "MIPGap", "IntFeasTol", "Heuristics",
                     "Cuts", "Seed", "Presolve", "Crossover", "MIPFocus"):
            self.assertEqual(receipt["protected_parameters"][name], ORIGINAL_PARAMETERS[name])
        self.assertEqual(set(dict(model.parameter_writes)), set(EXPECTED_PRECISION))

    def test_wrong_phase_i_method_denied_before_parameter_mutation(self):
        for method in (-1, 0, 1, True):
            with self.subTest(method=method):
                model = RecordingModel(parameters={"Method": method})
                with self.assertRaisesRegex(ValueError, "ORIGINAL_METHOD_TWO_REQUIRED"):
                    self.apply(model)
                self.assertEqual(model.parameter_writes, [])
                self.assertEqual(model.entries, [])

    def test_wrong_phase_i_method_denied_before_original_native_entry(self):
        ledger = SourceStageLedger(self.context())
        model = RecordingModel(runtime=99., parameters={"Method": 1})
        with self.assertRaisesRegex(ValueError, "ORIGINAL_METHOD_TWO_REQUIRED"):
            ledger.native_optimize(model, component="PHASE_I", track="A1")
        self.assertEqual(model.entries, [])
        self.assertEqual(ledger.used(), 0.)
        self.assertEqual(ledger.calls, [])
        self.assertEqual(ledger.admission_failures[0]["entered_native"], False)
        self.assertEqual(ledger.admission_failures[0]["Native_Runtime"], 0.)

    def test_exact_may_day_stage_component_domain_before_mutation(self):
        bad = [("2025-04-30", "M1", "P1"), ("2025-06-01", "M2", "P1"),
            ("2026-05-25", "A1", "PHASE_I"), ("2025-05-32", "M1", "P1"),
            ("2025-5-25", "M1", "P1"), ("2025-05-25", "M3", "P1"),
            ("2025-05-25", "ACTUAL", "P1"), ("2025-05-25", "A2", "P2"),
            ("2025-05-25", "M1", "UNKNOWN")]
        for day, stage, component in bad:
            with self.subTest(day=day, stage=stage, component=component):
                model = RecordingModel()
                before = vars(model.Params).copy()
                with self.assertRaises(ValueError):
                    self.apply(model, stage, component, day)
                self.assertEqual(vars(model.Params), before)
                self.assertEqual(model.parameter_writes, [])

    def test_receipt_content_seal_detects_coherent_protected_setting_edit(self):
        model = RecordingModel()
        receipt = self.apply(model, "M1", "P1")
        self.assertEqual(receipt["content_sha"], digest({key: value for key, value in receipt.items()
            if key != "content_sha"}))
        edited = deepcopy(receipt)
        model.Params.Heuristics = .9
        edited["effective_parameters"]["Heuristics"] = .9
        edited["protected_parameters"]["Heuristics"] = .9
        edited["heuristics_parameter"] = .9
        with self.assertRaisesRegex(ValueError, "RECEIPT_CONTENT_DRIFT"):
            assert_native_precision(model, edited, day="2025-05-25", stage="M1", component="P1")

    def test_rehashed_false_receipt_metadata_rejected(self):
        model = RecordingModel()
        receipt = self.apply(model, "M2", "P1")
        for name, value in (("scientific_certified", True), ("heuristics_changed", True),
                            ("built_in_heuristics_active", False), ("original_method_unchanged", False)):
            with self.subTest(field=name):
                edited = deepcopy(receipt)
                edited[name] = value
                edited["content_sha"] = digest({key: item for key, item in edited.items()
                    if key != "content_sha"})
                with self.assertRaisesRegex(ValueError, "RECEIPT_METADATA_DRIFT"):
                    verify_settings_receipt(edited, day="2025-05-25", stage="M2", component="P1")

    def test_receipt_cannot_cross_date_stage_component_or_version(self):
        model = RecordingModel()
        receipt = self.apply(model, "A1", "PHASE_I")
        for day, stage, component in (("2025-05-24", "A1", "PHASE_I"),
            ("2025-05-25", "A2", "PHASE_I"), ("2025-05-25", "A1", "ORIGINAL_P1")):
            with self.subTest(day=day, stage=stage, component=component):
                with self.assertRaisesRegex(ValueError, "POLICY_IDENTITY_DRIFT"):
                    assert_native_precision(model, receipt, day=day, stage=stage, component=component)
        for name, value in (("version", "UNVERSIONED"), ("policy_sha", "0" * 64)):
            edited = deepcopy(receipt)
            edited[name] = value
            edited["content_sha"] = digest({key: item for key, item in edited.items() if key != "content_sha"})
            with self.assertRaisesRegex(ValueError, "POLICY_IDENTITY_DRIFT"):
                assert_native_precision(model, edited, day="2025-05-25", stage="A1", component="PHASE_I")

    def test_current_override_and_protected_parameter_drift_rejected(self):
        for name, value in (("FeasibilityTol", 1e-6), ("NumericFocus", 0),
                            ("Heuristics", 0.), ("Method", 1), ("MIPGap", .5), ("Presolve", 2)):
            with self.subTest(field=name):
                model = RecordingModel()
                receipt = self.apply(model)
                setattr(model.Params, name, value)
                with self.assertRaisesRegex(ValueError, "NATIVE_ENTRY_SETTINGS_DRIFT"):
                    assert_native_precision(model, receipt, day="2025-05-25", stage="A1", component="PHASE_I")

    def test_parameter_drift_between_receipt_and_guard_denied_without_native_charge(self):
        ledger = SourceStageLedger(self.context("M1"))
        model = RecordingModel(runtime=90.)
        original_apply = apply_native_precision
        def drift_after_apply(*args, **kwargs):
            receipt = original_apply(*args, **kwargs)
            args[0].Params.Heuristics = 0.
            return receipt
        with patch("v42_b3_joint.native_ledger.apply_native_precision", side_effect=drift_after_apply):
            with self.assertRaisesRegex(ValueError, "NATIVE_ENTRY_SETTINGS_DRIFT"):
                ledger.native_optimize(model, component="P1", track="M1")
        self.assertEqual(model.entries, [])
        self.assertEqual(ledger.used(), 0.)
        self.assertEqual(ledger.calls, [])
        self.assertEqual(ledger.admission_failures[0]["Native_Runtime"], 0.)

    def test_readback_and_unrelated_setter_side_effects_rejected(self):
        class IgnoresPrecision(RecordingModel):
            def setParam(self, name, value):
                self.parameter_writes.append((name, value))
        class AltersMethod(RecordingModel):
            def setParam(self, name, value):
                super().setParam(name, value)
                self.Params.Method = 0
        with self.assertRaisesRegex(ValueError, "PARAMETER_READBACK_DRIFT"):
            self.apply(IgnoresPrecision(), "M1", "P1")
        with self.assertRaisesRegex(ValueError, "ORIGINAL_PARAMETER_CHANGED"):
            self.apply(AltersMethod(), "M1", "P1")

    def test_source_requires_real_setparam_and_fake_fallback_remains_labelled(self):
        model = SimpleNamespace(Params=SimpleNamespace(**ORIGINAL_PARAMETERS))
        with self.assertRaisesRegex(ValueError, "SOURCE_MODEL_SET_PARAM_REQUIRED"):
            apply_native_precision(model, day="2025-05-25", stage="M1", component="P1")
        receipt = self.apply(model, "M1", "P1")
        self.assertFalse(receipt["scientific_certified"])
        for name, value in EXPECTED_PRECISION.items():
            self.assertEqual(getattr(model.Params, name), value)
        with self.assertRaisesRegex(ValueError, "EVIDENCE_KIND_REQUIRED"):
            apply_native_precision(RecordingModel(), day="2025-05-25", stage="M1", component="P1",
                evidence_kind="MOCK")

    def test_bound_original_apply_runs_first_without_disabling_heuristics(self):
        calls = []
        policy, gp = object(), object()
        def original_apply(model, received_policy, received_gp):
            calls.append((received_policy, received_gp))
            model.setParam("Method", 2)
            model.setParam("Presolve", 2)
            model.setParam("Heuristics", .05)
            model.setParam("IntFeasTol", 1e-5)
            return vars(model.Params).copy()
        bound = bind_apply_precision(original_apply, stage="A2", evidence_kind="FAKE_SOURCE_TEST")
        model = RecordingModel(parameters={"Heuristics": 0.})
        effective = bound(model, policy, gp, day="2025-05-25", component="PHASE_I")
        self.assertEqual(calls, [(policy, gp)])
        self.assertEqual(model.parameter_writes[:4],
            [("Method", 2), ("Presolve", 2), ("Heuristics", .05), ("IntFeasTol", 1e-5)])
        self.assertEqual(effective["Presolve"], 0)
        self.assertEqual(effective["Method"], 2)
        self.assertEqual(effective["Heuristics"], .05)
        self.assertEqual(bound.last_receipt["protected_parameters"]["Heuristics"], .05)
        self.assertTrue(bound.last_receipt["built_in_heuristics_active"])

    def test_constructor_infinite_timelimit_not_misreported_as_native_budget(self):
        model = RecordingModel(parameters={"TimeLimit": float("inf")})
        receipt = self.apply(model, "M2", "P1")
        self.assertNotIn("TimeLimit", receipt["effective_parameters"])
        self.assertNotIn("TimeLimit", receipt["protected_parameters"])
        canonical(receipt)  # The constructor receipt remains JSON serializable.
        ledger = SourceStageLedger(self.context("M2"))
        ledger.native_optimize(model, component="P1", track="M2")
        self.assertEqual(model.entries[0]["receipt"]["effective_parameters"]["TimeLimit"], 5400.)

    def test_p2_and_model_date_drift_cannot_enter_native(self):
        ledger = SourceStageLedger(self.context("M1"))
        model = RecordingModel(runtime=10.)
        with self.assertRaisesRegex(ValueError, "P2_NATIVE_FORBIDDEN"):
            ledger.native_optimize(model, component="P2", track="M1")
        self.assertEqual(model.parameter_writes, [])
        model._v42_a_stage_day = "2025-05-24"
        with self.assertRaisesRegex(ValueError, "MODEL_DATE_DRIFT"):
            ledger.native_optimize(model, component="P1", track="M1")
        self.assertEqual(model.entries, [])
        self.assertEqual(ledger.used(), 0.)
        self.assertEqual(ledger.calls, [])
        self.assertEqual(ledger.admission_failures[0]["Native_Runtime"], 0.)

    def test_resume_preserves_precision_identity_and_remaining_native_limit(self):
        context = self.context("A2")
        ledger = SourceStageLedger(context)
        ledger.native_optimize(RecordingModel(runtime=4.), component="PHASE_I", track="A2")
        resumed = SourceStageLedger(context)
        model = RecordingModel(runtime=2.)
        resumed.native_optimize(model, component="PHASE_I", track="A2")
        receipt = resumed.receipt()
        self.assertEqual(model.entries[0]["parameters"]["TimeLimit"], 5396.)
        self.assertEqual(receipt["measured_native_runtime"], 6.)
        self.assertEqual(receipt["remaining_seconds"], 5394.)
        self.assertEqual(receipt["native_call_count"], 2)
        self.assertEqual(receipt["calls"][1]["b3_numerical_policy"]["effective_parameters"]["TimeLimit"], 5396.)

    def test_resume_rejects_numerical_sidecar_version_or_policy_sha_drift(self):
        for name, value in (("numerical_policy_version", "OLD_POLICY"), ("numerical_policy_sha", "0" * 64)):
            with self.subTest(field=name):
                context = self.context("M2", suffix="-" + name)
                ledger = SourceStageLedger(context)
                identity = json.loads(ledger.identity_path.read_text(encoding="utf-8-sig"))
                identity[name] = value
                ledger.identity_path.write_text(canonical(identity), encoding="utf-8")
                before = ledger.path.read_bytes()
                with self.assertRaisesRegex(ValueError, "RESTART_IDENTITY_DRIFT"):
                    SourceStageLedger(context)
                self.assertEqual(ledger.path.read_bytes(), before)

    def test_resume_rejects_missing_or_tampered_call_precision_receipt(self):
        for tamper in ("missing", "edited", "rehashed_limit"):
            with self.subTest(tamper=tamper):
                context = self.context("M1", suffix="-" + tamper)
                ledger = SourceStageLedger(context)
                ledger.native_optimize(RecordingModel(), component="P1", track="M1")
                document = json.loads(ledger.path.read_text(encoding="utf-8-sig"))
                row = document["calls"][0]
                if tamper == "missing":
                    del row["b3_numerical_policy"]
                elif tamper == "edited":
                    row["b3_numerical_policy"]["effective_parameters"]["ScaleFlag"] = 0
                else:
                    receipt = row["b3_numerical_policy"]
                    receipt["effective_parameters"]["TimeLimit"] = 123.
                    receipt["protected_parameters"]["TimeLimit"] = 123.
                    receipt["content_sha"] = digest({key: value for key, value in receipt.items() if key != "content_sha"})
                ledger.path.write_text(canonical(document), encoding="utf-8")
                before = ledger.path.read_bytes()
                with self.assertRaises(ValueError):
                    SourceStageLedger(context)
                self.assertEqual(ledger.path.read_bytes(), before)

    def test_precision_receipt_does_not_open_closed_source_production(self):
        model = RecordingModel()
        apply_native_precision(model, day="2025-05-25", stage="M1", component="P1")
        registry = SourceRegistry()
        context = replace(self.context("M1"), source_registry=registry,
            output=ROOT / "runtime" / "b3" / ("PRECISION_GUARD_" + self.root.name))
        with patch.dict("os.environ", {"B3_NATIVE_EXECUTION_AUTHORIZED": "1"}), \
             patch("v42_b3_joint.policy.B3_NATIVE_EXECUTION_AUTHORIZED", True):
            with self.assertRaisesRegex(PermissionError, "PRODUCTION_NOT_AUTHORIZED"):
                SourceStageLedger(context)
        self.assertEqual(registry.audit, [])
        self.assertFalse(context.output.exists())
        self.assertEqual(model.entries, [])


if __name__ == "__main__":
    unittest.main()

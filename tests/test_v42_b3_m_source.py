"""Tiny fake SOURCE routing tests, never physical/scientific M results."""
from contextlib import nullcontext
from dataclasses import dataclass, replace
import ast
import hashlib
import json
import math
from pathlib import Path
from types import ModuleType, SimpleNamespace
import unittest

from v42_b3_joint.contracts import StageRequest, canonical, digest
from v42_b3_joint.dry_run import fixture_aidc, fixture_authority
from v42_b3_joint.m_source import MSourceBridge, fixed_aidc_payload
from v42_b3_joint.source_runtime import FakeSourceRegistry, RealStageContext, SourceRegistry
from v42_b3_joint.scalar_math import original_pcs_math_scope, OriginalScalarMathMemo


def fake_module(**attributes):
    return SimpleNamespace(__b3_fake__=True, **attributes)


class FakeLedger:
    def __init__(self, context):
        self.context, self.stage = context, context.request.stage

    def sealed_receipt(self):
        return canonical({"evidence_kind": "FAKE_SOURCE_TEST", "real_native_calls": 0, "Threads": 1})

    def cost(self, *args, **kwargs):
        return nullcontext()


class FakeGrid:
    def __init__(self, authority):
        self.authority = authority
        self.seen = []

    def validate(self, stage, authority, **kwargs):
        if authority != self.authority:
            raise ValueError("FAKE_GRID_AUTHORITY_DRIFT")
        self.seen.append(("validate", stage))
        return True

    def coefficients(self, bundle, day):
        names = ["aidc_load_kw[" + site + "]" for site in self.authority.pcc_ids]
        names += ["mess_p_kw[STATION0]", "mess_q_kvar[STATION0]"]
        return [SimpleNamespace(control_names=names, slot=t) for t in range(96)]

    def thermal_rows_expected(self, bundle):
        return 96

    def physical_scope(self, stage, bundle):
        self.seen.append(("physical_scope", stage))
        return nullcontext()

    def make_native_authority(self, stage, bundle, coefficients):
        self.seen.append(("make_native_authority", stage))
        return {"FAKE_SOURCE_TEST": True, "stage": stage}

    def transformer_wrapper(self, stage, builder, thermal):
        return builder


class ScalarFixtureExpression:
    """Pure coefficient recorder; no native variables or model are created."""
    def __init__(self, values):
        self.values = dict(values)

    def __rmul__(self, scalar):
        return ScalarFixtureExpression({name: scalar * value for name, value in self.values.items()})

    def __add__(self, other):
        values = dict(self.values)
        for name, value in other.values.items():
            values[name] = values.get(name, 0.) + value
        return ScalarFixtureExpression(values)

    def __le__(self, other):
        return (tuple((name, value.hex()) for name, value in sorted(self.values.items())),
                tuple((name, value.hex()) for name, value in sorted(other.values.items())))


class ScalarFixtureRecorder:
    def __init__(self):
        self.rows = []

    def addConstr(self, row, *, name):
        self.rows.append((name, row))


def pure_original_pcs_fixture():
    """Compile ONLY the original pure pcs_rows function, with fake operands."""
    source = Path(__file__).resolve().parents[1] / "v42_native" / "mess.py"
    raw = source.read_bytes()
    definition = [node for node in ast.parse(raw.decode("utf-8-sig")).body
                  if isinstance(node, ast.FunctionDef) and node.name == "pcs_rows"]
    module = ModuleType("b3_pure_pcs_source_fixture")
    module.__b3_fake__, module.__file__ = True, str(source)
    module.cos, module.sin, module.pi, module.FACES = math.cos, math.sin, math.pi, 16
    def checked(condition, message):
        if not condition:
            raise ValueError(message)
    module.require = checked
    exec(compile(ast.Module(definition, type_ignores=[]), str(source), "exec"), vars(module))
    return module, source, hashlib.sha256(raw).hexdigest()


class SourceFixture:
    """Source APIs are pure test doubles; fake model is a dictionary axis."""

    def __init__(self, stage="M1", marker=1):
        self.authority = fixture_authority()
        self.aidc = fixture_aidc(marker)
        self.request = StageRequest(stage, self.authority, fixed_aidc=self.aidc)
        self.grid = FakeGrid(self.authority)
        self.events = []
        self.virtual_files = {}
        self.warm_feasible = True
        self.strict_pass = True
        self.bound = "97/100"
        self.source_stage_routing = None
        self.last_case = None
        self.native_input_calls = 0
        initial = {unit: "STATION0" for unit in self.authority.mess_ids}
        @dataclass(frozen=True)
        class FakeBattery:
            initial: float = .5
            terminal: float = .5
            def validate(obj):
                return None
        self.native_tuple = (("STATION0",), initial, (), FakeBattery(), {})

        def native_inputs(bundle):
            self.native_input_calls += 1
            return self.native_tuple

        class Compact:
            def __init__(obj, *args):
                obj.A, obj.d = "FAKE_C3A", {}

            def forward(obj, point):
                return point

        class Presolve:
            def __init__(obj, *args):
                obj.A, obj.d = "FAKE_C3A", {}

            def run(obj):
                return obj.A, obj.d

            def forward(obj, point):
                return point

        def atomic(path, value):
            self.virtual_files[str(path)] = value

        def read(path):
            return self.virtual_files.get(str(path), {})

        def strict(case, path, evidence):
            self.events.append(("independent_strict_UB", case.identity["input_identity"]["stage"]))
            return {"PASS": self.strict_pass, "exact_Global_UB": "1", "case_sha": case.case_sha,
                    "point_vector_sha256": digest(case.point),
                    "strict_raw_C3A_and_FULL_integer_and_binary_pattern_exact": True,
                    "FAKE_SOURCE_TEST": True}

        def bound(A, data, dual, *, case_sha):
            self.events.append(("independent_exact_LB", case_sha))
            return {"PASS": True, "exact_bound": self.bound, "case_sha": case_sha,
                    "FAKE_SOURCE_TEST": True}

        def verify_case(case):
            self.events.append(("independent_transport", case.case_sha))
            return {"PASS": True, "FAKE_SOURCE_TEST": True}

        def model_factory(symbol, target, routing):
            if symbol != "build_case":
                return target
            self.source_stage_routing = routing
            def build(payload, request, progress):
                construction_stage = routing["literal_replacements"]["M1"]
                self.events.append(("FULL_SOURCE_BUILD", construction_stage, payload["identity"]["producer_stage"]))
                imports = routing["import_replacements"]
                coefficients = imports["original_coefficients_for_day"](None, None, request["day"])
                imports["GridAuthority"]()
                with imports["physical_authority"]():
                    pass
                compact = imports["Compact"](None, None, None, None, 96)
                presolve = imports["Presolve"](compact.A, compact.d)
                A, data = presolve.run()
                graph = (self.native_tuple[0], initial,
                         [("STATION0", t, "STATION0", t + 1, None) for t in range(96)], self.native_tuple[3], {})
                identity = {"arm": "B3", "input_identity": payload["identity"],
                            "original_matrix_sha": digest({"FAKE_MATRIX": construction_stage,
                                                           "fixed": request["fixed_input_sha"]}),
                            "original_domain_sha": digest({"FAKE_DOMAIN": construction_stage}),
                            "transport_authority": {"FAKE_SOURCE_TEST": True},
                            "transport": {"PASS": True, "FAKE_SOURCE_TEST": True}}
                case_sha = digest(identity)
                values = {"rho_max": 1.0}
                for unit in self.authority.mess_ids:
                    for t in range(96):
                        values[f"arc[{unit},{t}]"] = 1.0
                        values[f"charge_mode[{unit},{t}]"] = 0.0
                        values[f"Pch[{unit},STATION0,{t}]"] = 0.0
                        values[f"Pdis[{unit},STATION0,{t}]"] = 0.0
                        values[f"Q[{unit},STATION0,{t}]"] = 0.0
                    for t in range(97):
                        values[f"SOC[{unit},{t}]"] = .5
                for t in range(96):
                    values[f"injection_P[STATION0,{t}]"] = 0.0
                    values[f"injection_Q[STATION0,{t}]"] = 0.0
                anchor = {"controls": [list(row) + [0.0, 0.0] for row in payload["planning"]["PCC_P_kw"]]}
                plan = {"values": values, "chosen_arcs": {u: list(range(96)) for u in initial},
                        "initial_sites": initial, "unit_ids": list(self.authority.mess_ids), "mode": "MILP",
                        "locations": [["STATION0"] * 4 for _ in range(96)],
                        "P_kw": [[0.0] * 4 for _ in range(96)], "Q_kvar": [[0.0] * 4 for _ in range(96)],
                        "SOC_kwh": [[.5] * 4 for _ in range(97)], "routes": []}
                case = SimpleNamespace(identity=identity, case_sha=case_sha, graph=graph,
                                       coefficients=coefficients, anchor=anchor, planning=payload["planning"],
                                       original_d={"names": list(values)}, original_A="FAKE_FULL",
                                       A=A, d=data, compact=compact, presolve=presolve,
                                       output=Path(request["output"]), point=[0.0], fake_plan=plan)
                self.last_case = case
                return case
            return build

        def stage_factory(symbol, target, routing):
            if symbol != "run":
                return target
            def run(request, ledger, progress):
                self.events.append(("SOURCE_HYBRID", request["stage"], request["arm"]))
                case = routing["globals"]["prepare"](request, progress)
                self.virtual_files[str(case.output / "BEST_EXACT_ORIGINAL_DUAL.json")] = {}
                return {"accepted": True, "P2_calls": 0, "mess": case.fake_plan,
                        "exact_Global_LB": self.bound, "exact_Global_UB": "1",
                        "FAKE_SOURCE_TEST": True}
            return run

        def optimize_case(case, ledger, progress=None, **kwargs):
            from fractions import Fraction
            from v42_b3_joint.policy import COMMON_MESS_VERSION
            stage = ledger.context.request.stage
            self.events.append(("SOURCE_HYBRID", stage, "B3"))
            self.virtual_files[str(case.output / "BEST_EXACT_ORIGINAL_DUAL.json")] = {}
            gap = None if self.bound is None else Fraction(1) - Fraction(self.bound)
            return dict(accepted=True, feasible_accepted=True, PASS=True, P2_calls=0,
                engine_version=COMMON_MESS_VERSION, scientific_case_sha=case.case_sha,
                global_gap_certified=gap is not None and gap <= Fraction(3, 100),
                certified_gap=float(gap) if gap is not None else None,
                exact_gap=str(gap) if gap is not None else None,
                exact_Global_LB=self.bound, exact_Global_UB="1", mess=case.fake_plan,
                FAKE_SOURCE_TEST=True), case.point

        def reconstruct(A, data, names, values):
            self.events.append(("M1_NEW_A2_ORIGINAL_RECONSTRUCTION", len(names)))
            return [0.0], {"PASS": self.warm_feasible, "FAKE_SOURCE_TEST": True}

        class FakeArchive:
            files = ["names"]
            def __enter__(archive):
                return archive
            def __exit__(archive, *args):
                return False
            def __getitem__(archive, name):
                return list(self.last_case.original_d[name])

        def restored_case(*args):
            fields = ("A", "d", "original_A", "original_d", "point", "graph", "case_sha", "identity",
                      "compact", "presolve", "bundle", "anchor", "planning", "coefficients", "output")
            self.events.append(("RESTORE_ORIGINAL_CASE_WITHOUT_MODEL",))
            return SimpleNamespace(**dict(zip(fields, args)), fake_plan=self.last_case.fake_plan)

        modules = {
            "v42_common_mess.engine": fake_module(optimize_case=optimize_case),
            "v42_may_campaign_native90.m_model": fake_module(build_case=lambda: None, verify_case=verify_case,
                verify_transport=lambda *args: {"PASS": True, "FAKE_SOURCE_TEST": True}, __b3_rebind__=model_factory,
                np=SimpleNamespace(savez_compressed=lambda *args, **kwargs: None,
                                   load=lambda *args, **kwargs: FakeArchive()),
                sparse=SimpleNamespace(load_npz=lambda *args: "FAKE_FULL"), CampaignMCase=restored_case),
            "v42_may_campaign_native90.m_stage": fake_module(run=lambda: None, _seed_integer=lambda *args: None,
                _fresh_lp_dual=lambda *args: None, _plan=lambda case, point: case.fake_plan,
                stationary_candidate=lambda case: ([0.0], {"PASS": True, "FAKE_SOURCE_TEST": True}),
                __b3_rebind__=stage_factory),
            "v42_supercompact.formulation": fake_module(Compact=Compact),
            "v42_supercompact.presolve": fake_module(Presolve=Presolve),
            "v42_bootstrap.m1": fake_module(native_inputs=native_inputs),
            "v42_native.mess": fake_module(Battery=FakeBattery),
            "v42_pr134_b1.common": fake_module(atomic=atomic, read=read,
                                              sha=lambda path: digest({"FAKE_ROUTE_BYTES": 1})),
            "v42_m1_hybrid.final_verify": fake_module(_strict_ub=strict),
            "v42_m1_research.check_lb": fake_module(check_rational_dual_certificate=bound),
            "v42_m1_research.check_ub": fake_module(vector_sha=lambda point: digest(point)),
            "v42_integrated.start": fake_module(PRIMARY=("arc", "SOC", "charge_mode", "Pch", "Pdis", "Q", "rho_max"),
                                                 reconstruct=reconstruct),
        }
        self.registry = FakeSourceRegistry(modules)
        arrays = {"sites": list(self.authority.pcc_ids),
                  "PCC_P_kw": [list(row) for row in zip(*self.aidc.pcc_p)],
                  "PCC_Q_kvar": [list(row) for row in zip(*self.aidc.pcc_q)],
                  "IT_kw": [list(row) for row in zip(*self.aidc.it_power)],
                  "GPU": [[1.0] * 12 for _ in range(96)], "known_GPU": [[1.0] * 12 for _ in range(96)]}
        upstream = {"source_stage": "A1" if stage == "M1" else "A2",
                    "authority_sha": self.authority.sha, "decision_sha": self.aidc.sha,
                    "original_model_sha": digest({"FAKE_A_MODEL": marker}), "planning_arrays": arrays,
                    "selected_jobs": json.loads(self.aidc.jobs_json)["known_job_actions"],
                    "gpu_runtime_state": json.loads(self.aidc.gpu_runtime_json),
                    "physical_source_evidence": {"PASS": True, "FAKE_SOURCE_TEST": True}}
        self.context = RealStageContext(self.request, Path("D:/b3_fake_inputs"),
            Path("D:/MobileESS_v42_B3_prep/runtime/b3/FAKE_M_SOURCE/" + stage),
            canonical({"day": self.authority.day, "initial_MESS_sites": initial}),
            self.registry, self.grid, {"fixed_aidc": upstream}, self.authority.source_sha, "FAKE_M_SOURCE")


class RealMSourceRoutingTests(unittest.TestCase):
    def test_original_pcs_scalar_memo_preserves_source_coefficient_bits_on_first_build(self):
        module, source, sha = pure_original_pcs_fixture()
        original = module.pcs_rows
        def rows():
            recorder = ScalarFixtureRecorder()
            for _ in range(3):
                module.pcs_rows(recorder, ScalarFixtureExpression({"p": 1.}),
                    ScalarFixtureExpression({"q": 1.}), ScalarFixtureExpression({"connected": 1.}), 100.)
            return recorder.rows
        baseline = rows()
        with original_pcs_math_scope(module, source, sha) as (memo, proof):
            self.assertIs(module.pcs_rows.__code__, original.__code__)
            optimized = rows()
        self.assertEqual(optimized, baseline)
        self.assertIs(module.pcs_rows, original)
        self.assertIs(module.cos, math.cos)
        self.assertIs(module.sin, math.sin)
        self.assertTrue(proof["function_restored"])
        receipt = memo.receipt()
        self.assertEqual(receipt["requests"], {"cos": 96, "sin": 48})
        self.assertEqual(receipt["original_math_evaluations"], {"cos": 17, "sin": 16})
        self.assertEqual(receipt["real_performance_comparison"], "NOT_RUN")

    def test_original_pcs_scalar_scope_restores_on_exception_and_rejects_source_drift(self):
        module, source, sha = pure_original_pcs_fixture()
        original = module.pcs_rows
        with self.assertRaisesRegex(RuntimeError, "fixture construction failed"):
            with original_pcs_math_scope(module, source, sha):
                raise RuntimeError("fixture construction failed")
        self.assertIs(module.pcs_rows, original)
        with self.assertRaisesRegex(ValueError, "PCS_SOURCE_SHA_DRIFT"):
            with original_pcs_math_scope(module, source, "0" * 64):
                self.fail("Source drift was admitted")
        self.assertIs(module.pcs_rows, original)

    def test_scalar_memo_is_build_private_and_signed_zero_keys_remain_exact(self):
        first, second = OriginalScalarMathMemo(math.cos, math.sin), OriginalScalarMathMemo(math.cos, math.sin)
        first.cos(0.0); first.cos(-0.0); first.cos(0.0)
        second.cos(0.0)
        self.assertEqual(first.receipt()["original_math_evaluations"]["cos"], 2)
        self.assertEqual(first.receipt()["hits"]["cos"], 1)
        self.assertEqual(second.receipt()["original_math_evaluations"]["cos"], 1)
        with self.assertRaises(ValueError):
            first.cos(True)

    def test_wrong_stage_or_context_ledger_is_rejected_before_source_resolution(self):
        fixture = SourceFixture("M2")
        wrong_context = SourceFixture("M1")
        for ledger in (FakeLedger(wrong_context.context), FakeLedger(fixture.context)):
            if ledger.context is fixture.context:
                ledger.stage = "M1"
            with self.subTest(stage=ledger.stage), self.assertRaisesRegex(ValueError, "STAGE_LEDGER_DRIFT"):
                MSourceBridge().execute(fixture.context, ledger)
            self.assertEqual(fixture.registry.audit, [])
            self.assertEqual(fixture.events, [])

    def test_m1_and_m2_route_stage_before_original_full_construction(self):
        for stage in ("M1", "M2"):
            fixture = SourceFixture(stage)
            output = MSourceBridge().execute(fixture.context, FakeLedger(fixture.context))
            self.assertIn(("FULL_SOURCE_BUILD", stage, "A1" if stage == "M1" else "A2"), fixture.events)
            self.assertIn(("SOURCE_HYBRID", stage, "B3"), fixture.events)
            self.assertEqual(fixture.source_stage_routing["attribute_replacements"]["Stage.M1"], "Stage." + stage)
            self.assertEqual(fixture.source_stage_routing["expression_replacements"]["120 * 96"], "_b3_expected_thermal_rows")
            self.assertEqual(output.aidc.sha, fixture.aidc.sha)
            self.assertEqual(output.source_packet["B2_FCFS_producer_calls"], 0)
            self.assertEqual(output.evidence_kind, "FAKE_SOURCE_TEST")
            self.assertEqual(output.global_evidence["evidence_kind"], "FAKE_SOURCE_TEST")

    def test_optimized_a2_anchor_creates_own_m2_original_model_identity(self):
        first, second = SourceFixture("M1", 1), SourceFixture("M2", 2)
        m1 = MSourceBridge().execute(first.context, FakeLedger(first.context))
        m2 = MSourceBridge().execute(second.context, FakeLedger(second.context))
        self.assertNotEqual(m1.model_sha, m2.model_sha)
        self.assertNotEqual(m1.request.fixed_input_sha, m2.request.fixed_input_sha)
        self.assertEqual(m2.source_packet["full_aidc_decision_sha"], second.aidc.sha)

    def test_q_it_jobs_and_runtime_source_materialization_drift_is_rejected(self):
        for family in ("PCC_Q_kvar", "IT_kw", "selected_jobs", "gpu_runtime_state"):
            fixture = SourceFixture()
            packet = fixture.context.source_packets["fixed_aidc"]
            if family in ("PCC_Q_kvar", "IT_kw"):
                packet["planning_arrays"][family][0][0] += 1
            else:
                packet[family] = {"unauthorized_change": True}
            with self.subTest(family=family), self.assertRaises(ValueError):
                fixed_aidc_payload(fixture.context)
            self.assertEqual(fixture.events, [])

    def test_missing_original_a_physics_and_wrong_producer_stage_fail(self):
        for field, value in (("physical_source_evidence", {"PASS": False}),
                             ("source_stage", "A1"), ("decision_sha", digest({"old": 1}))):
            fixture = SourceFixture("M2")
            fixture.context.source_packets["fixed_aidc"][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                fixed_aidc_payload(fixture.context)

    def test_full_mess_dto_and_original_grid_helper_values_are_retained(self):
        fixture = SourceFixture("M2")
        output = MSourceBridge().execute(fixture.context, FakeLedger(fixture.context))
        self.assertEqual(len(output.mess.routes), 4)
        self.assertEqual((len(output.mess.soc), len(output.mess.soc[0])), (4, 97))
        variables = json.loads(output.mess.variables_json)
        self.assertTrue({"movement", "charge_mode", "route", "P", "Q", "SOC", "original_values"} <= set(variables))
        self.assertIn("injection_P[STATION0,0]", output.source_packet["values"])
        self.assertEqual(output.source_packet["controls"][0][-2:], [0.0, 0.0])
        self.assertEqual(output.source_packet["optimized_families"], ["arc", "charge_mode", "Pch", "Pdis", "Q", "SOC", "rho_max"])

    def test_verify_replays_transport_global_lb_and_literal_integer_ub(self):
        fixture = SourceFixture()
        bridge = MSourceBridge()
        output = bridge.execute(fixture.context, FakeLedger(fixture.context))
        before = len(fixture.events)
        proof = bridge.verify(fixture.context, output)
        self.assertTrue(proof["PASS"])
        fresh = fixture.events[before:]
        self.assertTrue(any(row[0] == "independent_transport" for row in fresh))
        self.assertTrue(any(row[0] == "independent_exact_LB" for row in fresh))
        self.assertTrue(any(row[0] == "independent_strict_UB" for row in fresh))
        self.assertIs(output.global_evidence["joint_global_optimality_claim"], False)

    def test_source_global_bound_drift_and_physical_failure_fail_closed(self):
        fixture = SourceFixture()
        bridge = MSourceBridge()
        output = bridge.execute(fixture.context, FakeLedger(fixture.context))
        fixture.bound = "0"
        with self.assertRaises(ValueError):
            bridge.verify(fixture.context, output)
        fixture.bound, fixture.strict_pass = "97/100", False
        with self.assertRaises(ValueError):
            bridge.verify(fixture.context, output)

    def test_feasible_m_stage_with_unknown_lb_can_advance_without_global_claim(self):
        fixture = SourceFixture()
        fixture.bound = None
        bridge = MSourceBridge()
        output = bridge.execute(fixture.context, FakeLedger(fixture.context))
        self.assertTrue(output.source_result["feasible_accepted"])
        self.assertFalse(output.global_evidence["global_gap_certified"])
        self.assertFalse(output.global_evidence["original_global_bound_verified"])
        self.assertIsNone(output.global_evidence["exact_LB"])
        self.assertIsNone(output.source_packet["dual_path"])
        proof = bridge.verify(fixture.context, output)
        self.assertTrue(proof["physical"]["original_integer_physical_verified"])
        self.assertEqual(proof["global"]["certification_status"], "UNKNOWN")
        forged = dict(output.source_result, global_gap_certified=True)
        with self.assertRaisesRegex(ValueError, "UNKNOWN_LB"):
            bridge.verify(fixture.context, replace(output, source_result=forged))

    def test_physically_feasible_gap_above_three_percent_is_uncertified(self):
        fixture = SourceFixture()
        fixture.bound = "1/2"
        output = MSourceBridge().execute(fixture.context, FakeLedger(fixture.context))
        self.assertTrue(output.source_result["feasible_accepted"])
        self.assertEqual(output.source_result["exact_gap"], "1/2")
        self.assertFalse(output.global_evidence["global_gap_certified"])
        self.assertEqual(output.global_evidence["certification_status"], "GAP_NOT_CERTIFIED")

    def test_m1_candidate_is_independently_checked_under_new_a2_case(self):
        first = SourceFixture("M1")
        m1 = MSourceBridge().execute(first.context, FakeLedger(first.context))
        second = SourceFixture("M2", 2)
        second.context.source_packets["warm_mess"] = m1.source_packet
        output = MSourceBridge().execute(second.context, FakeLedger(second.context))
        self.assertTrue(any(row[0] == "M1_NEW_A2_ORIGINAL_RECONSTRUCTION" for row in second.events))
        receipt = second.virtual_files[str(second.context.output / "B3_WARM_START_ADMISSION.json")]
        self.assertTrue(receipt["PASS"])
        self.assertIs(receipt["old_LB_UB_Runtime_transferred"], False)
        self.assertEqual(receipt["new_fixed_A2_sha"], second.aidc.sha)
        self.assertEqual(output.source_packet["source_stage"], "M2")

    def test_m1_candidate_infeasible_under_a2_is_rejected_without_bound_transfer(self):
        first, second = SourceFixture("M1"), SourceFixture("M2", 2)
        m1 = MSourceBridge().execute(first.context, FakeLedger(first.context))
        second.context.source_packets["warm_mess"] = m1.source_packet
        second.warm_feasible = False
        MSourceBridge().execute(second.context, FakeLedger(second.context))
        receipt = second.virtual_files[str(second.context.output / "B3_WARM_START_ADMISSION.json")]
        self.assertIs(receipt["PASS"], False)
        self.assertEqual(receipt["status"], "REJECTED_UNDER_NEW_A2_ANCHOR")
        self.assertIs(receipt["old_LB_UB_Runtime_transferred"], False)

    def test_independent_replay_rejects_different_fixed_aidc_and_model_hash(self):
        fixture = SourceFixture()
        bridge = MSourceBridge()
        output = bridge.execute(fixture.context, FakeLedger(fixture.context))
        for changed in (replace(output, aidc=fixture_aidc(2)), replace(output, model_sha=digest({"wrong_model": 1}))):
            with self.subTest(changed=changed.model_sha), self.assertRaises(ValueError):
                bridge.verify(fixture.context, changed)

    def test_independent_replay_binds_full_upstream_source_anchor_and_materialized_arrays(self):
        fixture = SourceFixture()
        bridge = MSourceBridge()
        output = bridge.execute(fixture.context, FakeLedger(fixture.context))
        for field in ("planning_arrays", "selected_jobs", "upstream_original_A_model_sha"):
            packet = json.loads(canonical(output.source_packet))
            if field == "planning_arrays":
                packet[field]["PCC_Q_kvar"][0][0] += 1
            else:
                packet[field] = {"drift": True} if field == "selected_jobs" else digest({"other_A_model": 1})
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "UPSTREAM_A_SOURCE_ANCHOR_DRIFT"):
                bridge.verify(fixture.context, replace(output, source_packet=packet))
        fixture.context.source_packets["fixed_aidc"]["original_model_sha"] = digest({"new_source_model_same_DTO": 1})
        with self.assertRaisesRegex(ValueError, "UPSTREAM_A_SOURCE_ANCHOR_DRIFT"):
            bridge.verify(fixture.context, output)

    def test_resume_reconstructs_source_transport_without_an_original_model_build(self):
        fixture = SourceFixture()
        bridge = MSourceBridge()
        output = bridge.execute(fixture.context, FakeLedger(fixture.context))
        before = len([row for row in fixture.events if row[0] == "FULL_SOURCE_BUILD"])
        restarted = MSourceBridge()
        proof = restarted.verify(fixture.context, output)
        self.assertTrue(proof["PASS"])
        self.assertIn(("RESTORE_ORIGINAL_CASE_WITHOUT_MODEL",), fixture.events)
        self.assertEqual(len([row for row in fixture.events if row[0] == "FULL_SOURCE_BUILD"]), before)

    def test_resume_certificate_artifacts_cannot_escape_own_stage_output(self):
        fixture = SourceFixture()
        bridge = MSourceBridge()
        output = bridge.execute(fixture.context, FakeLedger(fixture.context))
        packet = dict(output.source_packet, raw_point_path="D:/MobileESS_v42/runtime/B2/historical.npz")
        with self.assertRaises(ValueError):
            bridge.verify(fixture.context, replace(output, source_packet=packet))

    def test_a2_source_control_and_full_plan_packets_are_tied_to_replayed_raw_point(self):
        fixture = SourceFixture()
        bridge = MSourceBridge()
        output = bridge.execute(fixture.context, FakeLedger(fixture.context))
        for field in ("controls", "mess_plan"):
            packet = json.loads(canonical(output.source_packet))
            if field == "controls":
                packet[field][0][-1] = 1.0
            else:
                packet[field]["values"]["injection_Q[STATION0,0]"] = 1.0
            with self.subTest(field=field), self.assertRaises(ValueError):
                bridge.verify(fixture.context, replace(output, source_packet=packet))

    def test_real_registry_gate_denies_before_any_source_model_import(self):
        fixture = SourceFixture()
        real = SourceRegistry()
        context = replace(fixture.context, source_registry=real,
                          output=Path(__file__).resolve().parents[1] / "runtime/b3/FAKE_M_SOURCE/M1")
        with self.assertRaises(PermissionError):
            MSourceBridge().execute(context, FakeLedger(context))
        self.assertEqual(real.audit, [])

    def test_worker_local_route_input_cache_reuses_source_objects_but_builds_new_full_case(self):
        fixture = SourceFixture()
        bundle = dict(fixture.context.original_bundle,
                      route_table={"path": "D:/b3_fake_inputs/FAKE_ROUTES", "sha256": digest({"FAKE_ROUTE_BYTES": 1})},
                      battery={"initial": .5, "terminal": .5})
        context = replace(fixture.context, original_bundle_json=canonical(bundle))
        bridge = MSourceBridge()
        first = bridge.execute(context, FakeLedger(context))
        second = bridge.execute(context, FakeLedger(context))
        self.assertEqual(fixture.native_input_calls, 1)
        self.assertEqual(first.model_sha, second.model_sha)
        self.assertEqual(first.mess.sha, second.mess.sha)
        self.assertEqual(len([event for event in fixture.events if event[0] == "FULL_SOURCE_BUILD"]), 2)
        receipt = second.source_packet["immutable_route_input_cache"][0]
        self.assertEqual((receipt["hits"], receipt["misses"]), (1, 1))
        self.assertEqual(receipt["cached_matrices"], 0)
        self.assertEqual(receipt["cached_solver_models"], 0)
        self.assertEqual(receipt["cached_bounds_or_ledgers"], 0)

    def test_route_source_sha_is_rechecked_before_every_cache_hit(self):
        fixture = SourceFixture()
        bundle = dict(fixture.context.original_bundle,
                      route_table={"path": "D:/b3_fake_inputs/FAKE_ROUTES", "sha256": digest({"FAKE_ROUTE_BYTES": 1})},
                      battery={"initial": .5, "terminal": .5})
        context = replace(fixture.context, original_bundle_json=canonical(bundle))
        bridge = MSourceBridge()
        bridge.execute(context, FakeLedger(context))
        fixture.registry.modules["v42_pr134_b1.common"].sha = lambda path: digest({"MODIFIED_SOURCE_BYTES": 1})
        with self.assertRaisesRegex(ValueError, "CACHED_ROUTE_SOURCE_SHA_DRIFT"):
            bridge.execute(context, FakeLedger(context))
        self.assertEqual(fixture.native_input_calls, 1)


if __name__ == "__main__":
    unittest.main()

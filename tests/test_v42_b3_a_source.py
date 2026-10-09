"""Tiny source-registry tests. No Gurobi, native build or real input is used."""
from contextlib import contextmanager
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import ast
import json
import unittest

from v42_b3_joint.a_source import (ASourceBridge, BuildProfile, A_SOURCE, _BOUND_MODULES,
    _restore_source_globals, _scientific, _native_numerical_artifact)
from v42_b3_joint.contracts import Authority, MESSDecision, StageRequest, canonical, digest
from v42_b3_joint.grid_binding import InjectionAuthority, fold_fixed_affine_rows
from v42_b3_joint.model_mapping import verify_fixed_mess_packet
from v42_b3_joint.numerical_policy import (VERSION as NUMERICAL_VERSION,
    bind_apply_precision, apply_native_precision)
from v42_b3_joint.source_runtime import FakeSourceRegistry, RealStageContext, SourceRegistry, jsonable


def authority():
    return Authority("2025-05-23", *(digest(name) for name in
        ("input", "grid", "pcc", "domain", "forecast", "runtime", "source")),
        "2025-05-22T18:00:00+09:00", "2025-05-22T17:00:00+09:00",
        tuple(f"idc{i:02}" for i in range(12)), tuple(f"M{i}" for i in range(4)))


def module(**values):
    return SimpleNamespace(__b3_fake__=True, **values)


@dataclass(frozen=True)
class Battery:
    initial: float = 10.
    terminal: float = 10.


def fixed_packet(a):
    units, sites = a.mess_ids, a.pcc_ids
    arrays = [[0.] * 4 for _ in range(96)]
    locations = [[sites[i] for i in range(4)] for _ in range(96)]
    soc = [[10.] * 4 for _ in range(97)]
    names = [f"aidc_load_kw[{s}]" for s in sites]
    names += [f"mess_p_kw[{s}]" for s in sites] + [f"mess_q_kvar[{s}]" for s in sites]
    controls = [[1.] * 12 + [-1.5] * 12 + [2.25] * 12 for _ in range(96)]
    arcs = [(s, t, s, t + 1, None) for s in sites for t in range(96)]
    chosen = {unit: list(range(index * 96, (index + 1) * 96)) for index, unit in enumerate(units)}
    values = {f"injection_P[{s},{t}]": -1.5 for s in sites for t in range(96)}
    values.update({f"injection_Q[{s},{t}]": 2.25 for s in sites for t in range(96)})
    variables = {"movement": [], "charge_mode": [[0.] * 96 for _ in units], "route": chosen,
                 "P": {"Pch": [[0.] * 96 for _ in units], "Pdis": [[0.] * 96 for _ in units]},
                 "Q": arrays, "SOC": soc, "original_values": values}
    decision = MESSDecision(tuple(tuple(str(k) for k in chosen[u]) for u in units),
        tuple(tuple(row[i] for row in locations) for i in range(4)),
        tuple(tuple(row[i] for row in arrays) for i in range(4)),
        tuple(tuple(row[i] for row in arrays) for i in range(4)),
        tuple(tuple(row[i] for row in arrays) for i in range(4)),
        tuple(tuple(row[i] for row in soc) for i in range(4)),
        canonical({"initial": [10.] * 4, "final": [10.] * 4}),
        tuple(tuple(row[i] for row in arrays) for i in range(4)), canonical(variables))
    initial, battery, receipt = dict(zip(units, sites)), Battery(), {"source": "FIXTURE_NATIVE_INPUTS"}
    graph = jsonable((sites, initial, arcs, battery, receipt))
    plan = {"unit_ids": list(units), "locations": locations, "Pch_kw": arrays, "Pdis_kw": arrays,
            "Q_kvar": arrays, "P_kw": arrays, "SOC_kwh": soc, "move_energy_kwh": arrays,
            "routes": [], "chosen_arcs": chosen, "values": values, "charge_mode": arrays,
            "initial_sites": initial, "mode": "MILP"}
    packet = {"source_stage": "M1", "authority_sha": a.sha, "decision_sha": decision.sha,
              "original_model_sha": digest("FIXTURE_M_FULL"), "physical_source_evidence": {"PASS": True},
              "mess_plan": plan, "graph": graph, "graph_sha": digest(graph),
              "values": values, "chosen_arcs": chosen, "initial_sites": initial, "mode": "MILP",
              "control_names": names, "controls": controls}
    return decision, packet, (sites, initial, (), battery, receipt)


class SourceGrid:
    """API fixture only. Its tiny affine row is explicitly not grid physics."""
    def __init__(self, a, names):
        self.authority = a
        self.coefficient = tuple(SimpleNamespace(slot=t, control_names=tuple(names),
                                                coefficient_sha256=digest(("FIXTURE", t))) for t in range(96))
        self.rows = []
    def validate(self, stage, a, **kwargs):
        if a.sha != self.authority.sha:
            raise ValueError("FIXTURE_GRID_AUTHORITY_DRIFT")
        return True
    def coefficients(self, bundle, day):
        return self.coefficient
    def stage_enum(self, stage):
        return stage
    def fixed_site_injections(self, packet, decision, coefficients):
        return InjectionAuthority.fixed_site_injections(self, packet, decision, coefficients)
    def _api(self, name):
        if name != "load_power":
            raise ValueError(name)
        return lambda bundle: ({"day": bundle["day"]}, {}, 0., 1.)
    def make_native_authority(self, *args):
        return {"FIXTURE": True, "stage": args[0]}
    def grid_builder(self, stage):
        return lambda *args: None


class SourceBridgeTests(unittest.TestCase):
    def test_production_admission_precedes_every_source_resolve(self):
        a = authority()
        class ForbiddenRegistry(SourceRegistry):
            def resolve(self, name):
                raise AssertionError("SOURCE_IMPORT_REACHED")
        registry = ForbiddenRegistry()
        output = Path(__file__).resolve().parents[1] / "runtime/b3/closed_a_test"
        context = RealStageContext(StageRequest("A1", a), output.parent / "inputs", output,
                                  canonical({"day": a.day}), registry, object(), {}, a.source_sha, "closed")
        with self.assertRaisesRegex(PermissionError, "PRODUCTION"):
            ASourceBridge().execute(context, object())
        with self.assertRaisesRegex(PermissionError, "PRODUCTION"):
            ASourceBridge().verify(context, object())

    def test_source_files_have_no_top_level_solver_or_original_import(self):
        root = Path(__file__).resolve().parents[1]
        for name in ("a_source.py", "grid_binding.py", "model_mapping.py"):
            tree = ast.parse((root / "v42_b3_joint" / name).read_text(encoding="utf-8-sig"))
            for node in tree.body:
                if isinstance(node, ast.Import):
                    self.assertFalse(any(alias.name.startswith(("gurobipy", "v42_")) for alias in node.names))
                if isinstance(node, ast.ImportFrom) and not node.level:
                    self.assertFalse((node.module or "").startswith(("gurobipy", "v42_")))

    def test_nonzero_fixed_p_and_q_preserve_all_original_affine_rows(self):
        rows = [{"aidc": 3., "P": 2., "Q": -4.}, {"Q": 7.}, {"aidc": -1., "P": 5.}]
        bounds = [11., 6., -2.]
        folded, rhs = fold_fixed_affine_rows(rows, bounds, {"P": -1.5, "Q": 2.25})
        self.assertEqual(folded, ({"aidc": Fraction(3)}, {}, {"aidc": Fraction(-1)}))
        self.assertEqual(rhs, (Fraction(23), Fraction(-39, 4), Fraction(11, 2)))
        for original, bound, free, changed in zip(rows, bounds, folded, rhs):
            for aidc in (-2., 0., 5.):
                left = sum(Fraction(v) * Fraction({"aidc": aidc, "P": -1.5, "Q": 2.25}[k]) for k, v in original.items())
                right = sum(v * Fraction(aidc) for v in free.values())
                self.assertEqual(left - Fraction(bound), right - changed)

    def test_source_m_packet_graph_and_route_conventions(self):
        a = authority()
        decision, packet, native = fixed_packet(a)
        calls = []
        modules = {
            "v42_bootstrap.m1": module(native_inputs=lambda bundle: native),
            "v42_native.mess": module(validate=lambda *args: (calls.append("native.validate") or {"PASS": True})),
            "v42_bootstrap.attribution": module(supplemental_physical=lambda *args:
                (calls.append("source.supplemental") or {"charge_mode_and_connection_PASS": True})),
        }
        registry = FakeSourceRegistry(modules)
        with TemporaryDirectory() as temp:
            context = RealStageContext(StageRequest("A2", a, fixed_mess=decision), Path(temp) / "inputs",
                Path(temp) / "output", canonical({"day": a.day}), registry, object(),
                {"fixed_mess": packet}, a.source_sha, "A2fixture")
            self.assertTrue(verify_fixed_mess_packet(context, packet))
            proof = ASourceBridge()._verify_fixed_native(context, packet)
            self.assertEqual(proof["graph_sha"], packet["graph_sha"])
            self.assertEqual(calls, ["native.validate", "source.supplemental"])
            packet["controls"][3][12] += 1
            with self.assertRaisesRegex(ValueError, "HELPER_CONTROL_DRIFT"):
                ASourceBridge()._verify_fixed_native(context, packet)

    def test_a1_then_a2_source_binding_uses_new_fixed_grid_and_restores_hooks(self):
        a = authority()
        decision, packet, native_inputs = fixed_packet(a)
        modules = {name: module(sentinel=object()) for name in _BOUND_MODULES}
        modules["v42_a_stage_domain_v2.domain"].AUTHORITY = "FIXTURE_ORIGINAL_COMPLETE_DOMAIN"
        modules["v42_bootstrap.m1"] = module(native_inputs=lambda bundle: native_inputs)
        modules["v42_native.mess"] = module(validate=lambda *args: {"PASS": True})
        modules["v42_bootstrap.attribution"] = module(supplemental_physical=lambda *args: {"charge_mode_and_connection_PASS": True})
        grid = SourceGrid(a, packet["control_names"])
        events = []
        def bind(bundle, inputs, output):
            modules["v42_root.common"].sentinel = "TEMPORARY_BOUND_OUTPUT"
            return modules["v42_root.data"], modules["v42_root.native"], grid.coefficient, {}, 0., 1.
        modules["v42_pr134_b1.native"].bind = bind
        def root_build(context, data, kind):
            raise AssertionError("REBOUND_SOURCE_BUILD_REQUIRED")
        modules["v42_root.native"].build = root_build
        modules["v42_boundary.model"].planning_grid = lambda *a, **k: None
        modules["v42_compact.native"].grid = lambda *a, **k: None
        def factory(symbol, target, routing):
            globals_map = routing.get("globals", {})
            if symbol == "build":
                return lambda context, data, kind: globals_map["grid"](None, data, {}, {})
            if symbol == "planning_grid":
                return lambda *args, **kwargs: ("SOURCE_A1", {}, [[0.]] * 96)
            if symbol == "grid":
                def compact(model, bundle, known, risk, p, q, *, stage):
                    events.append((stage, p, q))
                    if stage == "A1":
                        self.assertIsNone(p); self.assertIsNone(q)
                    else:
                        self.assertEqual(p[a.pcc_ids[0], 0], -1.5)
                        self.assertEqual(q[a.pcc_ids[0], 0], 2.25)
                    return stage, p, q
                return compact
            return target
        for name in ("v42_root.native", "v42_boundary.model", "v42_compact.native"):
            modules[name].__b3_rebind__ = factory
        registry = FakeSourceRegistry(modules)
        saved = modules["v42_root.common"].sentinel
        with TemporaryDirectory() as temp:
            for stage in ("A1", "A2"):
                request = StageRequest(stage, a, fixed_mess=decision if stage == "A2" else None)
                context = RealStageContext(request, Path(temp) / "inputs", Path(temp) / stage,
                    canonical({"day": a.day}), registry, grid,
                    {"fixed_mess": packet} if stage == "A2" else {}, a.source_sha, stage)
                with registry.execution_scope(context), _restore_source_globals(registry):
                    binder, _ = ASourceBridge()._binding(context, BuildProfile(stage))
                    result = binder(context.original_bundle, context.input_folder, context.output / "SOURCE/STATIC")
                    active = dict(context.original_bundle, aidc_domain_authority="FIXTURE_ORIGINAL_COMPLETE_DOMAIN")
                    result[1].build(None, active, "F2-CRA")
                    # A2 physical replay also calls original bind with DATA[0]
                    # carrying the source-owned complete-domain authority tag.
                    binder(active, context.input_folder, context.output / "SOURCE/REPLAY")
                    with self.assertRaisesRegex(ValueError, "GRID_BUNDLE_DRIFT"):
                        result[1].build(None, dict(active, added_scientific_field=True), "F2-CRA")
                    self.assertEqual(modules["v42_root.common"].sentinel, "TEMPORARY_BOUND_OUTPUT")
                self.assertIs(modules["v42_root.common"].sentinel, saved)
        self.assertEqual([row[0] for row in events], ["A1", "A2"])
        rebindings = [row for row in registry.audit if row["action"] == "REBIND"]
        # Each stage binds its construction and independent physical replay
        # separately. Both bindings must route a new same-day source grid.
        self.assertEqual(sum(row["symbol"] == "grid" for row in rebindings), 4)

    def test_exception_restores_every_stage_source_global(self):
        modules = {name: module(sentinel=object()) for name in _BOUND_MODULES}
        registry = FakeSourceRegistry(modules)
        before = {name: value.sentinel for name, value in modules.items()}
        with self.assertRaisesRegex(RuntimeError, "FIXTURE_FAILURE"):
            with _restore_source_globals(registry):
                for value in modules.values():
                    value.sentinel = "CORRUPTED"
                    value.temporary_hook = True
                raise RuntimeError("FIXTURE_FAILURE")
        for name, value in modules.items():
            self.assertIs(value.sentinel, before[name])
            self.assertFalse(hasattr(value, "temporary_hook"))

    def test_original_planning_replay_keeps_fixed_mess_and_checks_controls(self):
        a = authority()
        decision, packet, _ = fixed_packet(a)
        grid = SourceGrid(a, packet["control_names"])
        archives, calls = {}, []
        class Archive:
            def __init__(self, path):
                self.values = archives[str(path)]
                self.files = list(self.values)
            def __getitem__(self, key):
                return self.values[key]
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
        def original_planning(state, replay, power, output):
            calls.append(replay["controls"])
            path = Path(output) / "PLANNING_PHYSICAL.npz"
            archives[str(path)] = {"PCC_P_kw": [[1.] * 12 for _ in range(96)],
                "MESS_P_kw": [[0.] * 4 for _ in range(96)], "MESS_Q_kvar": [[0.] * 4 for _ in range(96)]}
            return {"path": str(path)}
        def save(path, **values):
            archives[str(path)] = values
        source = module(_planning=original_planning,
            np=SimpleNamespace(load=Archive, asarray=lambda value: value, savez_compressed=save),
            record=lambda path: {"path": str(path)})
        registry = FakeSourceRegistry({A_SOURCE: source})
        with TemporaryDirectory() as temp:
            context = RealStageContext(StageRequest("A2", a, fixed_mess=decision), Path(temp) / "inputs",
                Path(temp) / "output", canonical({"day": a.day}), registry, grid,
                {"fixed_mess": packet}, a.source_sha, "planning")
            materialize = ASourceBridge()._planning(context, source)
            replay = {"controls": packet["controls"]}
            receipt = materialize({}, replay, {"coeff": grid.coefficient}, context.output)
            self.assertTrue(all(row[12:] == [0.] * 24 for row in calls[0]))
            self.assertEqual(archives[receipt["path"]]["MESS_P_kw"], packet["mess_plan"]["P_kw"])
            self.assertEqual(archives[receipt["path"]]["MESS_Q_kvar"], packet["mess_plan"]["Q_kvar"])
            self.assertEqual(replay["controls"][0][12], -1.5)
            changed = json.loads(json.dumps(replay))
            changed["controls"][0][12] += 1.
            with self.assertRaisesRegex(ValueError, "P_CONTROL_DRIFT"):
                materialize({}, changed, {"coeff": grid.coefficient}, context.output)

    def test_verifier_hash_removes_only_known_original_timing_fields(self):
        original = {"validation_seconds": 4.5, "physical": {"P1_rho": 1., "grid_violation": 0.}, "exact_LB": "999/1000"}
        changed = dict(original, validation_seconds=999.)
        self.assertEqual(digest(_scientific(original)), digest(_scientific(changed)))
        changed["physical"] = {"P1_rho": 1., "grid_violation": .01}
        self.assertNotEqual(digest(_scientific(original)), digest(_scientific(changed)))

    def test_profiles_measure_preparation_separately_from_native_elapsed_time(self):
        values = iter((0., 1., 3., 4., 6.))
        profile = BuildProfile("A1", clock=lambda: next(values))
        with profile.measure("total_model_preparation"):
            pass
        with profile.measure("model_equivalence_verification"):
            pass
        receipt = profile.receipt()
        self.assertEqual(receipt["total_model_preparation_seconds"], 2.)
        self.assertEqual(receipt["model_equivalence_verification"], 2.)
        self.assertIsNone(receipt["speedup_ratio"])
        self.assertEqual(receipt["large_May01_May23_comparison"], "NOT_RUN")

    def test_all_may_a_stages_precision_and_source_artifact_metadata(self):
        original = dict(Threads=1, Method=2, Seed=20260929, MIPGap=.005, Presolve=-1,
            Cuts=-1, Heuristics=.05, NumericFocus=0, FeasibilityTol=1e-6, OptimalityTol=1e-6,
            IntFeasTol=1e-5, NodeMethod=1, MIPFocus=3, Crossover=-1)
        calls = []
        class Model:
            def __init__(self):
                self.Params = SimpleNamespace(TimeLimit=float("inf"), ScaleFlag=-1)
            def setParam(self, name, value):
                setattr(self.Params, name, value)
        def source_apply(model, policy, gp):
            calls.append(policy)
            for name, value in policy.items():
                model.setParam(name, value)
            return {name: getattr(model.Params, name) for name in policy}
        for stage in ("A1", "A2"):
            for day_number in range(1, 32):
                day = f"2025-05-{day_number:02d}"
                context = SimpleNamespace(request=SimpleNamespace(stage=stage, authority=SimpleNamespace(day=day)))
                precision = bind_apply_precision(source_apply, stage=stage, evidence_kind="FAKE_SOURCE_TEST")
                for component in ("PHASE_I", "ORIGINAL_P1", "LOCAL_PRICING", "INTEGER_CONTROL"):
                    with self.subTest(stage=stage, day=day, component=component):
                        model = Model()
                        effective = precision(model, original, object(), day=day, component=component)
                        enabled = component in ("PHASE_I", "ORIGINAL_P1")
                        self.assertEqual(model.Params.FeasibilityTol, 1e-9 if enabled else 1e-6)
                        self.assertEqual(model.Params.OptimalityTol, 1e-9 if enabled else 1e-6)
                        self.assertEqual(model.Params.NumericFocus, 3 if enabled else 0)
                        self.assertEqual(model.Params.ScaleFlag, 2 if enabled else -1)
                        self.assertEqual(model.Params.Presolve, 0 if component == "PHASE_I" else -1)
                        self.assertEqual(model.Params.Method, 2)
                        self.assertEqual(model.Params.Heuristics, .05)
                        self.assertEqual(model.Params.IntFeasTol, 1e-5)
                        stale = {"component": component, "numerical_precision_override": False,
                                 "solver_policy_unchanged": True, "effective": effective, "TimeLimit": 5400}
                        parameters = _native_numerical_artifact(context, precision, "SOLVER_PARAMETERS.json", stale)
                        identity = _native_numerical_artifact(context, precision, "MODEL_IDENTITY.json",
                            {key: value for key, value in stale.items() if key != "effective"})
                        for artifact in (parameters, identity):
                            self.assertEqual(artifact["numerical_policy_version"], NUMERICAL_VERSION)
                            self.assertEqual(artifact["numerical_precision_override"], enabled)
                            self.assertEqual(artifact["solver_policy_unchanged"], not enabled)
                            self.assertEqual(artifact["phase_I_original_rows"], component == "PHASE_I")
                            self.assertEqual(artifact["numerical_policy"]["built_in_heuristics_active"], True)
                            self.assertTrue(artifact["scientific_acceptance_tolerance_unchanged"])
                            self.assertNotIn("TimeLimit", artifact["numerical_policy"]["protected_parameters_at_source_application"])
                            canonical(artifact)  # Original Infinity default cannot leak into a sealed packet.
                        changed = dict(stale, effective=dict(effective, FeasibilityTol=1e-6))
                        if enabled:
                            with self.assertRaisesRegex(ValueError, "PERSISTED_NUMERICAL_SETTINGS_DRIFT"):
                                _native_numerical_artifact(context, precision, "SOLVER_PARAMETERS.json", changed)
        self.assertEqual(len(calls), 31 * 2 * 4)

    def test_source_preflight_and_actual_settings_guard_are_separate(self):
        a = authority()
        class Model:
            def __init__(self):
                self.Params = SimpleNamespace(Threads=1, Method=2, TimeLimit=float("inf"),
                    FeasibilityTol=1e-6, OptimalityTol=1e-6, NumericFocus=0, ScaleFlag=-1,
                    Presolve=-1, Heuristics=.05)
            def setParam(self, name, value):
                setattr(self.Params, name, value)
        def original_apply(model, policy, gp):
            return {name: getattr(model.Params, name) for name in policy}
        registry, model = FakeSourceRegistry(), Model()
        precision = bind_apply_precision(original_apply, stage="A1", evidence_kind="FAKE_SOURCE_TEST")
        with TemporaryDirectory() as temp:
            context = RealStageContext(StageRequest("A1", a), Path(temp) / "inputs", Path(temp) / "output",
                canonical({"day": a.day}), registry, object(), {}, a.source_sha, "preflight")
            precision(model, {"Method": 2, "Threads": 1}, object(), day=a.day, component="PHASE_I")
            self.assertFalse(hasattr(model, "_v42_b3_numerical_receipt"))
            with registry.execution_scope(context), registry.native_scope(model, "PHASE_I", "A"):
                registry.source_model_guard(model)
                # A preflight annotation cannot substitute for the ledger's
                # actual finite-TimeLimit entry receipt.
                model._v42_b3_numerical_receipt = {"source_preflight_only": True}
                with self.assertRaisesRegex(ValueError, "RECEIPT_CONTENT_DRIFT"):
                    registry.guard(model)
                model.setParam("TimeLimit", 5400.)
                model._v42_b3_numerical_receipt = apply_native_precision(model,
                    day=a.day, stage="A1", component="PHASE_I", evidence_kind="FAKE_SOURCE_TEST")
                registry.guard(model)
                model.setParam("FeasibilityTol", 1e-6)
                with self.assertRaisesRegex(ValueError, "ENTRY_SETTINGS_DRIFT"):
                    registry.guard(model)

    def test_v6_contexts_and_fresh_stage_grid_are_actual_source_links(self):
        root = Path(__file__).resolve().parents[1]
        tree = ast.parse((root / "v42_may_build_v6/a_stage.py").read_text(encoding="utf-8-sig"))
        prepare = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "prepare")
        calls = {ast.unparse(node.func) for node in ast.walk(prepare) if isinstance(node, ast.Call)}
        self.assertTrue({"checkpoint_memo", "construction_checks", "interval_projection"} <= calls)
        self.assertEqual(A_SOURCE, "v42_may_build_v6.a_stage")
        bridge = (root / "v42_b3_joint/a_source.py").read_text(encoding="utf-8-sig")
        self.assertIn('"v42_compact.native", "grid"', bridge)
        self.assertIn('"v42_a_stage_canary.pricing", "full_pricing"', bridge)
        self.assertIn('"v42_a_stage_practical/integer_model.py", "restore_types"', bridge)
        self.assertIn('"v42_a_stage_domain_v2/solver_policy.py", "apply_policy"', bridge)
        self.assertIn('"apply_precision": apply_precision', bridge)
        self.assertIn('guard=registry.source_model_guard', bridge)


if __name__ == "__main__":
    unittest.main()

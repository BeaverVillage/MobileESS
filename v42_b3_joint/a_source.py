"""Executable B3 A1/A2 routing of the original V6 complete A-stage.

The registry admits before imports. The unchanged source owns candidate
generation, graph construction, pricing, integer recovery and physical proof.
Routing changes only stage/date/output/budget/grid anchors. Production admission
is deliberately closed; an explicitly marked source fixture can exercise this
same orchestration without importing a solver.
"""
from contextlib import contextmanager
from fractions import Fraction
from pathlib import Path
from threading import RLock
from time import perf_counter
from types import SimpleNamespace
import gzip
import hashlib
import json
import pickle
import sys

from .contracts import canonical, digest, require, require_sha
from .model_mapping import aidc_from_source, verify_fixed_mess_packet, verify_planning_arrays
from .numerical_policy import (VERSION as NUMERICAL_VERSION, bind_apply_precision,
                               required_settings, settings_metadata, verify_settings_receipt)
from .source_runtime import SourceStageOutput, jsonable
from .state_io import LoadedSourceState, load_source_state


A_SOURCE = "v42_may_build_v6.a_stage"
_stage_lock = RLock()
_BOUND_MODULES = ("v42_pr134_b1.native", "v42_root.common", "v42_root.data", "v42_root.native",
    "v42_boundary.model", "v42_temporal.native", "v42_exact.validation", "v42_may01.prepare",
    "v42_compact.native", "v42_a_stage_domain_v2.domain", "v42_exact.support")


class BuildProfile:
    """Measurements have equal scopes; no large-model speedup is presumed."""
    def __init__(self, stage, clock=perf_counter):
        self.stage, self.clock, self.started = stage, clock, clock()
        self.samples = []
        self.preparing = False

    @contextmanager
    def measure(self, scope):
        start = self.clock()
        old_preparing = self.preparing
        if scope == "total_model_preparation":
            self.preparing = True
        try:
            yield
        finally:
            self.samples.append({"scope": scope, "seconds": self.clock() - start})
            self.preparing = old_preparing

    @contextmanager
    def input_binding(self):
        if self.preparing:
            with self.measure("original_input_preparation"):
                yield
        else:
            yield

    def receipt(self):
        totals = {key: sum(row["seconds"] for row in self.samples if row["scope"] == key)
                  for key in ("original_input_preparation", "physical_domain_generation", "graph_construction",
                              "original_full_model_construction", "compact_generation", "model_equivalence_verification")}
        return {"stage": self.stage, "source_algorithm": "MAY23_BUILD_EFFICIENCY_V6",
                "measurements": self.samples, **totals,
                "total_model_preparation_seconds": sum(row["seconds"] for row in self.samples
                                                        if row["scope"] == "total_model_preparation"),
                "comparison_requires_equal_scope": True, "large_May01_May23_comparison": "NOT_RUN",
                "speedup_ratio": None}

    def source_observer(self, root):
        path = Path(root) / "BUILD_STAGE_TIMES.json"
        if not path.is_file():
            return
        rows = json.loads(path.read_text(encoding="utf-8-sig"))["stage_costs"]
        scopes = {"fresh_DATA": "original_input_preparation",
                  "physical_domain/checkpoint_records": "physical_domain_generation",
                  "load_current_date_physical_cache/full_domain_hash": "physical_domain_generation",
                  "complete_compact_class_assembly": "compact_generation"}
        for row in rows:
            if row["function"] in scopes:
                self.samples.append({"scope": scopes[row["function"]], "seconds": row["wall_seconds"],
                                     "source_function": row["function"]})
        graph = sum(row["wall_seconds"] for row in rows if row["function"] == "prepare_fast_active/active_graph")
        domain = sum(row["wall_seconds"] for row in rows if row["function"] == "physical_domain/checkpoint_records")
        if graph:
            self.samples.append({"scope": "graph_construction", "seconds": max(0., graph - domain),
                                 "source_function": "prepare_fast_active/active_graph minus nested physical_domain"})


def _scientific(value):
    """Remove only original verifier timing fields from repeated proof hashes."""
    if isinstance(value, dict):
        return {key: _scientific(item) for key, item in value.items()
                if key not in {"validation_seconds", "pricing_wall_seconds", "validation_wall_seconds", "check_wall_seconds"}}
    if isinstance(value, list):
        return [_scientific(item) for item in value]
    return value


def _native_numerical_artifact(context, apply_precision, name, value):
    """Replace the source's May11 annotation with the effective B3 policy.

    This receipt describes source policy application before the ledger admits
    Native. The ledger owns the final actual entry snapshot and TimeLimit.
    """
    if name not in ("MODEL_IDENTITY.json", "SOLVER_PARAMETERS.json"):
        return value
    component = value.get("component")
    receipt = apply_precision.last_receipt
    day, stage = context.request.authority.day, context.request.stage
    require(isinstance(receipt, dict) and receipt.get("day") == day and
            receipt.get("stage") == stage and receipt.get("component") == component and
            receipt.get("version") == NUMERICAL_VERSION,
            "A_SOURCE_NUMERICAL_APPLICATION_RECEIPT_DRIFT")
    verify_settings_receipt(receipt, day=day, stage=stage, component=component)
    overrides = required_settings(day, stage, component)
    require(receipt["overrides"] == overrides, "A_SOURCE_NUMERICAL_OVERRIDE_DRIFT")
    # At source apply_policy, TimeLimit can still be the native Infinity
    # default. Its finite effective value is written by the original source
    # separately and authoritatively captured by the ledger at admission.
    effective = dict(value.get("effective", {key: parameter for key, parameter in
        receipt["effective_parameters"].items() if key != "TimeLimit"}))
    require(all(effective.get(key) == parameter for key, parameter in overrides.items()),
            "A_SOURCE_PERSISTED_NUMERICAL_SETTINGS_DRIFT")
    if stage.startswith("A") and component == "PHASE_I":
        require(effective.get("Method") == 2, "A_SOURCE_PHASE_I_ORIGINAL_METHOD_TWO_REQUIRED")
    metadata = settings_metadata(day, stage, component, effective)
    metadata["effective_settings_scope"] = "SOURCE_POLICY_APPLICATION_BEFORE_NATIVE_ADMISSION"
    metadata["Native_entry_authority"] = "B3_SOURCE_STAGE_LEDGER_ACTUAL_PARAMETER_READBACK"
    metadata["protected_parameters_at_source_application"] = {key: parameter for key, parameter in
        receipt["protected_parameters"].items() if key != "TimeLimit"}
    return dict(value, numerical_policy_version=NUMERICAL_VERSION,
        numerical_policy_sha=metadata["policy_sha"], numerical_policy=metadata,
        numerical_policy_source_receipt=json.loads(canonical(receipt)),
        effective_solver_parameters=effective,
        numerical_precision_override=metadata["numerical_precision_override"],
        solver_policy_unchanged=metadata["solver_policy_unchanged"],
        phase_I_original_rows=metadata["phase_I_original_rows"],
        scientific_acceptance_tolerance_unchanged=True)


def _receipt(path):
    path = Path(path).resolve()
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "bytes": path.stat().st_size}


def _checked(receipt, root):
    path = Path(receipt["path"]).resolve()
    require(path.is_relative_to(Path(root).resolve()), "A_SOURCE_ARTIFACT_OUTPUT_ESCAPE")
    require(_receipt(path) == receipt, "A_SOURCE_SAVED_ARTIFACT_SHA_DRIFT")
    return path


@contextmanager
def _restore_source_globals(registry):
    """Protect scoped original V6/bind hooks across A1/A2 and exceptions."""
    with _stage_lock:
        modules = [registry.resolve(name) for name in _BOUND_MODULES]
        saved = [(module, dict(vars(module))) for module in modules]
        source_search_path = list(sys.path)
        function_globals = []
        for module, namespace in saved:
            for value in namespace.values():
                if callable(value) and hasattr(value, "__globals__"):
                    globals_map = value.__globals__
                    if globals_map is not vars(module):
                        function_globals.append((globals_map, dict(globals_map)))
        try:
            yield
        finally:
            for globals_map, namespace in function_globals:
                globals_map.clear()
                globals_map.update(namespace)
            for module, namespace in reversed(saved):
                vars(module).clear()
                vars(module).update(namespace)
            sys.path[:] = source_search_path
            require(all(set(vars(module)) == set(namespace) and
                        all(vars(module)[key] is value for key, value in namespace.items())
                        for module, namespace in saved), "A_STAGE_SOURCE_GLOBAL_RESTORATION_FAILED")


class ASourceBridge:
    def _paths(self, context, request):
        require(request["stage"] == context.request.stage and request["arm"] == "B3" and
                request["day"] == context.request.authority.day and
                Path(request["input_folder"]).resolve() == context.input_folder and
                Path(request["output"]).resolve() == context.output / "SOURCE", "A_SOURCE_REQUEST_IDENTITY_DRIFT")
        return request["day"], context.input_folder, context.output / "SOURCE"

    def _request(self, context):
        request = {"stage": context.request.stage, "arm": "B3", "day": context.request.authority.day,
                "input_folder": str(context.input_folder), "output": str(context.output / "SOURCE"),
                "root": str(context.source_registry.root), "B3_request_sha": context.request.request_sha,
                "B3_fixed_input_sha": context.request.fixed_input_sha}
        cache = self._cache_packet(context)
        if cache is not None:
            request["_current_date_physical_cache"] = cache["output"]
        return request

    @staticmethod
    def _cache_packet(context):
        packet = context.source_packets.get("physical_input_cache")
        if packet is None and context.request.stage == "A2":
            packet = context.source_packets.get("a1", {}).get("physical_input_cache")
        return packet

    def _source_digest(self, context, symbols):
        manifest = context.source_registry.source_manifest
        if context.source_registry.evidence_kind == "FAKE_SOURCE_TEST":
            return digest({"FAKE_SOURCE_TEST_APIS": list(symbols)})
        values = {path: manifest.get(path) for path in symbols}
        for value in values.values():
            require_sha(value)
        return digest(values)

    def _domain_authority(self, context, state):
        """The shared authority is the source's COMPLETE A domain roster SHA."""
        domain_roster = {uid: domain.sha for uid, domain in sorted(state["domains"].items())}
        expected = state["data"][7].get("physical_domain_hash")
        if context.source_registry.evidence_kind == "FAKE_SOURCE_TEST" and expected is None:
            # A tiny API fixture can omit the expensive physical producer, but
            # its evidence stays explicitly FAKE_SOURCE_TEST everywhere.
            return digest({"FAKE_SOURCE_TEST_DOMAIN_ROSTER": domain_roster})
        actual = context.source_registry.callable("v42_a_stage_domain_v2/domain.py", "digest")(domain_roster)
        require(actual == expected, "A_SOURCE_COMPLETE_PHYSICAL_DOMAIN_ROSTER_SHA_DRIFT")
        if context.source_registry.evidence_kind == "SOURCE":
            require(expected == context.request.authority.physical_domain_sha,
                    "A_SOURCE_ORIGINAL_PHYSICAL_DOMAIN_AUTHORITY_SHA_DRIFT")
        return actual

    def _binding(self, context, profile, *, verification=False):
        registry, grid, bundle = context.source_registry, context.grid_authority, context.original_bundle
        stage, day = context.request.stage, context.request.authority.day
        grid.validate(stage, context.request.authority, bundle=bundle)
        source_domain_authority = getattr(registry.resolve("v42_a_stage_domain_v2.domain"), "AUTHORITY", None)
        active_bundle = dict(bundle, aidc_domain_authority=source_domain_authority) if source_domain_authority else None
        def same_source_bundle(value):
            # Original prepare_fast_active adds its own scientific authority
            # tag to DATA[0]. Permit exactly that original source metadata;
            # all input scientific fields must remain byte-semantically equal.
            return value == bundle or active_bundle is not None and value == active_bundle
        original = registry.callable("v42_pr134_b1/native.py", "bind")
        coefficient = grid.coefficients(bundle, day)
        fixed_packet = context.source_packets.get("fixed_mess")
        p = q = None
        if stage == "A2":
            verify_fixed_mess_packet(context, fixed_packet)
            self._verify_fixed_native(context, fixed_packet)
            p, q = grid.fixed_site_injections(fixed_packet, context.request.fixed_mess, coefficient)

        def bind(actual_bundle, inputs, output):
            require(same_source_bundle(actual_bundle) and Path(inputs).resolve() == context.input_folder,
                    "A_SOURCE_BOUND_INPUT_IDENTITY_DRIFT")
            require(Path(output).resolve().is_relative_to(context.output), "A_SOURCE_BIND_OUTPUT_ESCAPE")
            Path(output).mkdir(parents=True, exist_ok=True)
            with profile.input_binding():
                answer = original(actual_bundle, inputs, output)
            require(tuple(c.coefficient_sha256 for c in answer[2]) ==
                    tuple(c.coefficient_sha256 for c in coefficient), "A_SOURCE_INJECTED_COEFFICIENT_DRIFT")
            boundary = registry.resolve("v42_boundary.model")
            temporal = registry.resolve("v42_temporal.native")
            source_power = grid._api("load_power")
            certificate, power, idle, swing = source_power(actual_bundle)
            # The original date binder already replaced its coefficient loader.
            # All new lower boundaries receive the same independently checked
            # same-day coefficients, including the standalone A2 source API.
            loaders = {"load_power": lambda _: (certificate, power, idle, swing),
                       "native_coefficients": lambda _: coefficient,
                       "GridAuthority": lambda *a, **k: grid.make_native_authority(stage, bundle, coefficient),
                       "add_grid": grid.grid_builder(stage)}
            boundary_grid = registry.rebind("v42_boundary.model", "planning_grid",
                globals={**loaders, "OLD": Path(output)},
                literal_replacements={"2025-05-01T00:00:00+10:00": day + "T00:00:00+10:00"})
            compact_grid = registry.rebind("v42_compact.native", "grid",
                globals={"OLD": Path(output), "frozen_a1_grid": boundary_grid},
                import_replacements=loaders,
                literal_replacements={"2025-05-01T00:00:00+10:00": day + "T00:00:00+10:00"})

            def stage_grid(model, source_bundle, known, risk, **ignored):
                require(same_source_bundle(source_bundle), "A_SOURCE_GRID_BUNDLE_DRIFT")
                return compact_grid(model, source_bundle, known, risk, p, q, stage=grid.stage_enum(stage))

            build = registry.rebind("v42_root.native", "build", globals={"grid": stage_grid})
            native = SimpleNamespace(**vars(answer[1]))
            def measured_build(*a, **k):
                with profile.measure("original_full_model_construction"):
                    return build(*a, **k)
            native.build = measured_build
            return answer[0], native, coefficient, power, idle, swing
        return bind, coefficient

    def _verify_fixed_native(self, context, packet):
        registry = context.source_registry
        native_inputs = registry.callable("v42_bootstrap/m1.py", "native_inputs")
        sites, initial, routes, battery, receipt = native_inputs(context.original_bundle)
        arcs = [(site, t, site, t + 1, None) for site in sites for t in range(96)]
        arcs += [(route.source, route.depart, route.destination, route.connect, route) for route in dict.fromkeys(routes)]
        graph = jsonable((sites, initial, arcs, battery, receipt))
        require(digest(graph) == packet["graph_sha"] and graph == jsonable(packet["graph"]),
                "A2_FIXED_MESS_ORIGINAL_GRAPH_REPLAY_DRIFT")
        native_plan = {key: packet[key] for key in ("values", "chosen_arcs", "initial_sites", "mode")}
        require(native_plan["initial_sites"] == initial and native_plan["mode"] == "MILP", "A2_FIXED_MESS_NATIVE_INITIAL_MODE_DRIFT")
        proof = registry.callable("v42_native/mess.py", "validate")(native_plan, sites, routes, battery, 96)
        extra = registry.callable("v42_bootstrap/attribution.py", "supplemental_physical")(native_plan, sites, battery)
        require(proof.get("PASS") is True and extra.get("charge_mode_and_connection_PASS") is True,
                "A2_FIXED_MESS_ORIGINAL_INTEGER_PHYSICAL_REPLAY_FAILED")
        for t, row in enumerate(packet["controls"]):
            for name, value in zip(packet["control_names"], row):
                if name.startswith(("mess_p_kw[", "mess_q_kvar[")):
                    site = name.split("[", 1)[1][:-1]
                    prefix = "injection_P" if name.startswith("mess_p_kw[") else "injection_Q"
                    require(value == native_plan["values"][f"{prefix}[{site},{t}]"],
                            "A2_FIXED_MESS_ORIGINAL_HELPER_CONTROL_DRIFT")
        return {"native": jsonable(proof), "supplemental": jsonable(extra), "graph_sha": packet["graph_sha"]}

    def _physical(self, context, bind, state, inputs, output):
        registry, grid, stage = context.source_registry, context.grid_authority, context.request.stage
        power = {}
        def routed_bind(bundle, ignored_inputs, ignored_output):
            answer = bind(bundle, inputs, Path(output) / "STATIC/PHYSICAL_REPLAY")
            power.update(coeff=answer[2], power=answer[3], idle=answer[4], swing=answer[5])
            return answer
        coefficient = grid.coefficients(context.original_bundle, context.request.authority.day)
        check = registry.rebind("v42_exact.validation", "check",
            import_replacements={"load_power": grid._api("load_power"), "native_coefficients": lambda _: coefficient},
            literal_replacements={"2025-05-01T00:00:00+10:00": context.request.authority.day + "T00:00:00+10:00"})
        certify = registry.rebind("v42_pr134_sc.snapshot", "certify",
            attribute_replacements={"Stage.A1": "Stage." + stage},
            import_replacements={"check": check, "grid_audit": lambda c, x, rho: grid.audit(stage, c, x, rho)})
        source_physical = registry.resolve("v42_a_stage_acceptance.physical")
        directory = registry.resolve("v42_may_campaign_native90.a_routing").DayDirectory
        init = registry.rebind("v42_a_stage_acceptance.physical", "Physical.__init__",
            globals={"ROOT": registry.root, "STATIC": directory(context.request.authority.day, Path(output) / "STATIC"),
                     "bind": routed_bind})
        verify = registry.rebind("v42_a_stage_acceptance.physical", "Physical.verify",
            globals={"certify": certify, "physical_authority": lambda: grid.physical_scope(stage, context.original_bundle)})
        physical = type("B3SourcePhysical", (source_physical.Physical,), {"__init__": init, "verify": verify})
        return physical, power

    def _domain_cache(self, context, request, fresh_data, check=lambda: None, progress=None):
        packet = self._cache_packet(context)
        if packet is None:
            return None
        registry = context.source_registry
        require(packet["day"] == context.request.authority.day and packet["authority_sha"] == context.request.authority.sha
                and packet["producer_source_sha"] == context.producer_source_sha,
                "A_PHYSICAL_CACHE_SAME_DAY_SOURCE_AUTHORITY_REQUIRED")
        source = Path(packet["output"]).resolve()
        require(source != context.output and not source.is_relative_to(Path("D:/MobileESS_v42").resolve()),
                "A_PHYSICAL_CACHE_ACTIVE_OR_CURRENT_OUTPUT_FORBIDDEN")
        for receipt in packet["protected_receipts"]:
            _checked(receipt, source)
        semantic = registry.callable("v42_may_build_v6/a_cache.py", "_semantic_data")
        data_path = _checked(packet["DATA"], source)
        with data_path.open("rb") as stream:
            old_data = pickle.load(stream)
        require(semantic(old_data) == semantic(fresh_data), "A_PHYSICAL_CACHE_JOB_RESOURCE_BOUNDARY_GRAPH_DRIFT")
        load = registry.callable("v42_a_stage_domain_v2/fast_census.py", "load_physical_cache")
        domains = load(request["day"], old_data, data_path, source / "STATIC/DOMAIN")
        domain_hash = registry.callable("v42_may_build_v6/build_reuse.py", "domain_hash")
        require(set(domains) == set(fresh_data[1]), "A_PHYSICAL_CACHE_FULL_JOB_POPULATION_DRIFT")
        for uid, domain in domains.items():
            check()
            require(domain.cache.r == fresh_data[3] and domain.duration == fresh_data[1][uid].service_slots
                    and domain_hash(fresh_data[1][uid], fresh_data[2][uid], domain) == domain.sha,
                    "A_PHYSICAL_CACHE_INDEPENDENT_COMPLETE_DOMAIN_HASH_DRIFT")
        for receipt in packet["protected_receipts"]:
            _checked(receipt, source)
        # Original complete domain objects only; graph/model/RHS/dual/point/clock
        # are never returned from this cache boundary.
        return domains

    def _seed_input_cache(self, context, request, source_data_module, base):
        packet = self._cache_packet(context)
        if packet is None:
            return False
        registry = context.source_registry
        def admitted(actual_request, actual_source):
            source = Path(actual_source).resolve()
            require(source == Path(packet["output"]).resolve() and source != context.output and
                    not source.is_relative_to(Path("D:/MobileESS_v42").resolve()),
                    "A_INPUT_CACHE_SOURCE_ISOLATION_DRIFT")
            require(packet["day"] == context.request.authority.day and
                    packet["authority_sha"] == context.request.authority.sha and
                    packet["producer_source_sha"] == context.producer_source_sha,
                    "A_INPUT_CACHE_SAME_DAY_SOURCE_AUTHORITY_REQUIRED")
            for receipt in packet["protected_receipts"]:
                _checked(receipt, source)
            for name, receipt in packet["inputs"].items():
                require(name in {"NATIVE_INPUT.json", "WINDOWS.json"} and
                        _receipt(context.input_folder / name)["sha256"] == receipt["sha256"],
                        "A_INPUT_CACHE_ORIGINAL_INPUT_SHA_DRIFT")
            return {"DATA": packet["DATA"]}
        # Original V6 re-reads load_native, compares all jobs/resources/bounds
        # and independently regenerates scientific class signatures before
        # seeding only DATA graphs. No model or optimization state is admitted.
        seed = registry.rebind("v42_may_build_v6.input_cache", "seed_input_cache",
            globals={"verify_cache_authority": admitted})
        return seed(request, source_data_module, base)

    def _configure(self, context, ledger, progress, profile):
        registry = context.source_registry
        source = registry.resolve(A_SOURCE)
        apply_precision = bind_apply_precision(
            registry.callable("v42_a_stage_domain_v2/solver_policy.py", "apply_policy"),
            stage=context.request.stage, evidence_kind=registry.evidence_kind)
        def atomic(path, value):
            destination = Path(path).resolve()
            require(destination.is_relative_to(context.output / "SOURCE"), "A_SOURCE_ARTIFACT_WRITE_ESCAPE")
            if isinstance(value, dict):
                value = dict(value)
                if "arm" in value:
                    value["arm"] = "B3"
                if "all_MESS_PQ_zero" in value:
                    value["all_MESS_PQ_zero"] = context.request.stage == "A1"
                if destination.name in {"A1_FREEZE.json", "B1_P1_FREEZE.json", "A_RESULT.json"}:
                    value.update(stage=context.request.stage, request_sha=context.request.request_sha,
                                 fixed_input_sha=context.request.fixed_input_sha,
                                 fixed_MESS_decision_sha=context.request.fixed_mess.sha if context.request.fixed_mess else None)
                value = _native_numerical_artifact(context, apply_precision, destination.name, value)
            return source.atomic(destination, value)
        bind, coefficient = self._binding(context, profile)
        verify_case = registry.rebind(A_SOURCE, "verify_case", literal_replacements={"B1": "B3"})
        inherited = registry.resolve("v42_a_stage_canary.prepare")
        inherited_copy = SimpleNamespace(**vars(inherited))
        inherited_copy.prepare = registry.rebind("v42_a_stage_canary.prepare", "prepare", globals={
            "physical_authority": lambda: context.grid_authority.physical_scope(context.request.stage, context.original_bundle),
            "all_transformer_rows": lambda builder: builder})
        prepare_core = registry.rebind(A_SOURCE, "_prepare",
            globals={"_paths": lambda request: self._paths(context, request), "REPOSITORY": registry.root,
                     "verify_case": verify_case, "atomic": atomic}, literal_replacements={"B1": "B3"},
            import_replacements={"bind": bind, "inherited": inherited_copy,
                "seed_input_cache": lambda request, data_module, base:
                    self._seed_input_cache(context, request, data_module, base),
                "load_current_date_physical_cache": lambda request, fresh, check=lambda: None, progress=None:
                    self._domain_cache(context, request, fresh, check, progress)})
        prepare_original = registry.rebind(A_SOURCE, "prepare", globals={"_prepare": prepare_core})
        def prepare(request, callback=None):
            with profile.measure("total_model_preparation"):
                answer = prepare_original(request, callback)
            profile.source_observer(request["output"])
            return answer
        native = registry.rebind(A_SOURCE, "_native",
            globals={"_paths": lambda request: self._paths(context, request), "REPOSITORY": registry.root, "atomic": atomic},
            literal_replacements={"B1": "B3"},
            import_replacements={"execution": SimpleNamespace(native_scope=registry.native_scope, guard=registry.source_model_guard),
                                 "apply_precision": apply_precision})
        planning = self._planning(context, source)
        run = registry.rebind(A_SOURCE, "run", globals={
            "_paths": lambda request: self._paths(context, request), "prepare": prepare, "_native": native,
            "_physical": lambda state, inputs, output: self._physical(context, bind, state, inputs, output),
            "_planning": planning, "atomic": atomic},
            literal_replacements={"B1": "B3", "A1_P1_ONLY_ACCEPTED": context.request.stage + "_P1_ONLY_ACCEPTED"})
        return source, run, bind, verify_case, coefficient

    def _planning(self, context, source):
        """Call the source materializer, retaining the complete fixed MESS."""
        planning_original = context.source_registry.callable(A_SOURCE.replace(".", "/") + ".py", "_planning")
        def planning(state, replay, power, output):
            actual = replay
            if context.request.stage == "A2":
                p, q = context.grid_authority.fixed_site_injections(context.source_packets["fixed_mess"],
                    context.request.fixed_mess, power["coeff"])
                # Validate full fixed source controls BEFORE selecting the
                # AIDC-only view needed by the source B1 array materializer.
                controls = []
                for t, (c, row) in enumerate(zip(power["coeff"], replay["controls"])):
                    for name, value in zip(c.control_names, row):
                        if name.startswith("mess_p_kw["):
                            require(value == p[name[len("mess_p_kw["):-1], t], "A2_FIXED_MESS_P_CONTROL_DRIFT")
                        elif name.startswith("mess_q_kvar["):
                            require(value == q[name[len("mess_q_kvar["):-1], t], "A2_FIXED_MESS_Q_CONTROL_DRIFT")
                    controls.append([value if name.startswith("aidc_load_kw[") else 0.
                                     for name, value in zip(c.control_names, row)])
                actual = dict(replay, controls=controls)
            receipt = planning_original(state, actual, power, output)
            if context.request.stage == "A2":
                np = source.np
                path = Path(receipt["path"])
                with np.load(path) as archive:
                    arrays = {key: archive[key].copy() for key in archive.files}
                fixed = context.source_packets["fixed_mess"]["mess_plan"]
                arrays.update(MESS_P_kw=np.asarray(fixed["P_kw"]), MESS_Q_kvar=np.asarray(fixed["Q_kvar"]))
                np.savez_compressed(path, **arrays)
                receipt = source.record(path)
            return receipt
        return planning

    def _proof_receipts(self, context, source, output, pricing_receipt):
        """Seal every file read by the independent saved global proof replay."""
        pricing = Path(pricing_receipt["path"]).resolve()
        round_folder, main_folder = pricing.parent, pricing.parent.parent
        paths = {output / "BLOCK_PRICING_ORACLE_VERIFICATION.json",
                 output / "P1_FULL_DOMAIN_BOUND_CERTIFICATE.json",
                 output / "ORIGINAL_INTEGER_TYPE_RESTORATION.json",
                 output / "P1/INTEGER_CONTROL/MODEL_IDENTITY.json",
                 output / "A_NATIVE_CALLS.json", pricing}
        for call in source.read(output / "A_NATIVE_CALLS.json")["calls"]:
            folder = Path(call["folder"])
            paths.update(folder / name for name in ("MODEL_IDENTITY.json", "SOLVER_PARAMETERS.json"))
        roster = source.read(output / "BLOCK_PRICING_ORACLE_VERIFICATION.json")["records"]
        for entry in roster:
            paths.add(Path(entry["external_full_block_cache"]["path"]))
        folders = [main_folder]
        block_folder = context.source_registry.callable("v42_a_stage_phase1/runner.py", "block_folder")
        folders += [block_folder(round_folder, entry["class_id"]) for entry in roster]
        for folder in folders:
            path = folder / "NATIVE_RESULT.json"
            if not path.is_file():
                continue  # Source analytically prices a block with zero columns.
            paths.add(path)
            result = source.read(path)
            paths.update(Path(result[key]["path"]) for key in ("model_identity", "raw_attributes"))
        require(all(path.resolve().is_relative_to(output.resolve()) for path in paths),
                "A_SOURCE_GLOBAL_PROOF_ARTIFACT_ESCAPE")
        return [_receipt(path) for path in sorted(paths, key=lambda value: str(value).casefold())]

    def execute(self, context, ledger, progress=None):
        # This must precede even resolving V6; a production call cannot open a
        # license, mutate a source global or construct an output model.
        context.source_registry.admit(context, "A_STAGE")
        context.verify_identity()
        require(context.request.stage in ("A1", "A2"), "A_SOURCE_STAGE_REQUIRED")
        require(ledger.context is context and ledger.stage == context.request.stage, "A_SOURCE_STAGE_LEDGER_DRIFT")
        profile = BuildProfile(context.request.stage)
        with context.source_registry.execution_scope(context), _restore_source_globals(context.source_registry):
            source, run, bind, verify_case, coefficient = self._configure(context, ledger, progress, profile)
            raw_result = run(self._request(context), ledger, progress)
            require(raw_result.get("PASS") is True and raw_result.get("accepted") is True,
                    "A_SOURCE_ORIGINAL_P1_NOT_CERTIFIED:" + str(raw_result.get("classification")))
            raw_result = dict(raw_result, stage=context.request.stage, arm="B3",
                              all_MESS_PQ_zero=context.request.stage == "A1")
            output = context.output / "SOURCE"
            state_path = output / "STATIC/P1_CLOSED_STATE.pkl.gz"
            closed = _receipt(state_path)
            loaded = load_source_state(closed, output, _checked)
            state = loaded.state
            domain_sha = self._domain_authority(context, state)
            point_receipt = raw_result["incumbent"]["point"]
            replay = source.read(_checked(raw_result["incumbent"]["physical"], output))
            identity = source.read(output / "P1/INTEGER_CONTROL/MODEL_IDENTITY.json")
            with source.np.load(_checked(raw_result["planning"], output)) as archive:
                planning = {key: jsonable(archive[key]) for key in archive.files}
            planning["time_axis"] = list(range(96))
            aidc = aidc_from_source(context, planning, replay, state)
            model_sha = identity["original_snapshot_sha256"]
            packet = {"source_stage": context.request.stage, "authority_sha": context.request.authority.sha,
                "decision_sha": aidc.sha, "original_model_sha": model_sha,
                "planning_arrays": planning, "selected_jobs": jsonable(replay["selected_jobs"]),
                "unknown_arrival_policy": json.loads(aidc.jobs_json)["unknown_arrival_policy"],
                "gpu_runtime_state": json.loads(aidc.gpu_runtime_json),
                "aidc_schedule": json.loads(aidc.variables_json),
                "grid_anchor": {"grid_sha": context.request.authority.grid_sha,
                    "pcc_mapping_sha": context.request.authority.pcc_mapping_sha,
                    "control_names": list(coefficient[0].control_names), "controls": jsonable(replay["controls"])},
                "source_output": str(output), "closed_state": closed, "point": point_receipt,
                "planning": raw_result["planning"], "accepted_source": raw_result["freeze"],
                "complete_domain_hashes": {uid: domain.sha for uid, domain in state["domains"].items()},
                "original_complete_domain_sha": domain_sha,
                "numerical_policy_version": NUMERICAL_VERSION,
                "physical_domain_sha_basis": "ORIGINAL_DATA_7_PHYSICAL_DOMAIN_HASH_COMPLETE_AIDC_ROSTER",
                "global_bound": _receipt(output / "P1_FULL_DOMAIN_BOUND_CERTIFICATE.json"),
                "pricing_result": source.read(output / "P1_RESULT.json")["full_pricing"],
                "build_profile": profile.receipt(), "source_registry_routes": jsonable(context.source_registry.audit)}
            packet["proof_input_receipts"] = self._proof_receipts(context, source, output, packet["pricing_result"])
            cache_root = output / "STATIC/DOMAIN" / context.request.authority.day
            cache_receipt = cache_root / "PHYSICAL_DOMAIN_CACHE.json"
            if cache_receipt.is_file():
                cache_doc = source.read(cache_receipt)
                protected = [_receipt(cache_receipt), cache_doc["cache"], cache_doc["frozen_DATA"]]
                packet["physical_input_cache"] = {"day": context.request.authority.day,
                    "authority_sha": context.request.authority.sha, "producer_source_sha": context.producer_source_sha,
                    "output": str(output), "DATA": cache_doc["frozen_DATA"], "protected_receipts": protected,
                    "inputs": state["_campaign"]["input_receipts"],
                    "allowed_reuse": "COMPLETE_JOB_RESOURCE_BOUNDARY_PHYSICAL_DOMAIN_ONLY",
                    "grid_matrix_rhs_point_bound_clock_reused": False}
            output_object = SourceStageOutput(context.request, jsonable(raw_result), aidc, context.request.fixed_mess,
                model_sha, {}, {}, packet, ledger.sealed_receipt(), context.source_registry.evidence_kind)
            del state
            with profile.measure("model_equivalence_verification"):
                proof = self._verify_admitted(context, output_object, loaded_state=loaded)
            packet["build_profile"] = profile.receipt()
            packet["physical_source_evidence"] = proof["physical_evidence"]
            return SourceStageOutput(context.request, jsonable(raw_result), aidc, context.request.fixed_mess,
                model_sha, proof["physical_evidence"], proof["global_evidence"], packet,
                ledger.sealed_receipt(), context.source_registry.evidence_kind)

    def _recorded_pricing(self, context, output, state):
        registry = context.source_registry
        source_root = Path(output.source_packet["source_output"])
        source = registry.resolve(A_SOURCE)
        priced_path = _checked(output.source_packet["pricing_result"], source_root)
        round_folder = priced_path.parent
        main_folder = round_folder.parent

        class RecordedNative:
            def remaining(self):
                return 1.
            def solve(self, snapshot, folder, component):
                require(component == "LOCAL_PRICING", "A_PROOF_NATIVE_EXECUTION_FORBIDDEN")
                folder = Path(folder)
                require(folder.is_relative_to(source_root), "A_PROOF_LOCAL_PRICING_PATH_ESCAPE")
                result = source.read(folder / "NATIVE_RESULT.json")
                identity = source.read(_checked(result["model_identity"], source_root))
                require(identity["original_snapshot_sha256"] == snapshot.fingerprint(),
                        "A_PROOF_LOCAL_PRICED_MODEL_SHA_DRIFT")
                with source.np.load(_checked(result["raw_attributes"], source_root)) as archive:
                    raw = {key: archive[key].copy() for key in archive.files}
                return result, raw

        raw_result = source.read(main_folder / "NATIVE_RESULT.json")
        identity = source.read(_checked(raw_result["model_identity"], source_root))
        require(identity["original_snapshot_sha256"] == state["compact"].fingerprint(),
                "A_PROOF_FINAL_P1_MODEL_SHA_DRIFT")
        with source.np.load(_checked(raw_result["raw_attributes"], source_root)) as archive:
            raw = {key: archive[key].copy() for key in archive.files}
        inspect = registry.callable("v42_may_replay_v3/replay.py", "inspect")(state["compact"], raw)
        require(inspect.get("PASS") is True, "A_PROOF_FINAL_P1_PRIMAL_DUAL_REPLAY_FAILED")
        partition = registry.callable("v42_a_stage_compact_rowgen/assembly.py", "partition")
        local, owned = partition(state["compact"], state["metas"], state["grows"])
        # Replays the same original exact rational global/local dual certificate
        # computation. Its native.solve boundary reads source raw receipts only.
        full = registry.rebind("v42_a_stage_canary.pricing", "full_pricing",
            globals={"HISTORY": source_root, "atomic": lambda path, value: None, "print": lambda *a, **k: None})
        priced, negative = full(RecordedNative(), state["compact"], None, raw, None, state["data"],
            state["domains"], state["ledger"], state["axes"], state["n"], state["grows"],
            local, owned, round_folder)
        require(priced.get("PASS") is True and not negative and priced.get("no_negative_omitted_block_certified") is True
                and priced.get("complete_STAY_and_migration_coverage") is True,
                "A_PROOF_ORIGINAL_COMPLETE_GLOBAL_PRICING_FAILED")
        return priced

    def _verify_numerical_artifacts(self, context, output):
        """Check all source settings receipts, separately from scientific proof."""
        packet = output.source_packet
        require(packet.get("numerical_policy_version") == NUMERICAL_VERSION,
                "A_SOURCE_NUMERICAL_POLICY_VERSION_DRIFT")
        source = context.source_registry.resolve(A_SOURCE)
        root = Path(packet["source_output"])
        calls = source.read(root / "A_NATIVE_CALLS.json")["calls"]
        require(len(calls) == output.source_result["native_calls"], "A_SOURCE_NUMERICAL_CALL_AXIS_DRIFT")
        records = []
        for call in calls:
            component, folder = call["component"], Path(call["folder"]).resolve()
            require(folder.is_relative_to(root.resolve()), "A_SOURCE_NUMERICAL_ARTIFACT_ESCAPE")
            overrides = required_settings(context.request.authority.day, context.request.stage, component)
            parameters = source.read(folder / "SOLVER_PARAMETERS.json")
            for name in ("MODEL_IDENTITY.json", "SOLVER_PARAMETERS.json"):
                document = source.read(folder / name)
                metadata = document["numerical_policy"]
                effective = document["effective_solver_parameters"]
                source_receipt = document["numerical_policy_source_receipt"]
                verify_settings_receipt(source_receipt, day=context.request.authority.day,
                    stage=context.request.stage, component=component)
                expected = settings_metadata(context.request.authority.day, context.request.stage, component, effective)
                require(document.get("component") == component and
                        document.get("numerical_policy_version") == NUMERICAL_VERSION and
                        document.get("numerical_policy_sha") == expected["policy_sha"] and
                        all(metadata.get(key) == value for key, value in expected.items()) and
                        document.get("numerical_precision_override") is bool(overrides) and
                        document.get("solver_policy_unchanged") is (not bool(overrides)) and
                        document.get("scientific_acceptance_tolerance_unchanged") is True and
                        all(effective.get(key) == value for key, value in overrides.items()),
                        "A_SOURCE_NUMERICAL_SETTINGS_RECEIPT_DRIFT")
                if component == "PHASE_I":
                    require(effective.get("Method") == 2, "A_SOURCE_PHASE_I_ORIGINAL_METHOD_TWO_REQUIRED")
            require(parameters["effective"] == parameters["effective_solver_parameters"],
                    "A_SOURCE_ORIGINAL_EFFECTIVE_NUMERICAL_SETTINGS_DRIFT")
            identity = source.read(folder / "MODEL_IDENTITY.json")
            require(parameters["numerical_policy_source_receipt"] == identity["numerical_policy_source_receipt"],
                    "A_SOURCE_NUMERICAL_SOURCE_APPLICATION_CHANGED")
            records.append({"component": component, "folder": str(folder),
                "settings_sha": digest(parameters), "overrides": overrides})
        return {"version": NUMERICAL_VERSION, "records_sha": digest(records),
                "source_settings_records": len(records), "Native_entry_settings_authority": "B3_SOURCE_STAGE_LEDGER"}

    def _verify_admitted(self, context, output, *, loaded_state=None):
        require(output.request == context.request and output.evidence_kind == context.source_registry.evidence_kind,
                "A_SOURCE_VERIFIER_REQUEST_EVIDENCE_DRIFT")
        packet = output.source_packet
        source_root = self._verification_root(context, output)
        for receipt in packet["proof_input_receipts"]:
            _checked(receipt, source_root)
        numerical = self._verify_numerical_artifacts(context, output)
        require(packet["source_stage"] == context.request.stage and
                packet["authority_sha"] == context.request.authority.sha and packet["decision_sha"] == output.aidc.sha and
                packet["original_model_sha"] == output.model_sha,
                "A_SOURCE_VERIFIER_HANDOFF_IDENTITY_DRIFT")
        verify_planning_arrays(packet["planning_arrays"], output.aidc, context.request.authority)
        registry = context.source_registry
        source = registry.resolve(A_SOURCE)
        if loaded_state is None:
            loaded_state = load_source_state(packet["closed_state"], source_root, _checked)
        require(isinstance(loaded_state, LoadedSourceState), "SOURCE_STATE_VERIFIED_LOAD_REQUIRED")
        state = loaded_state.take(packet["closed_state"], source_root, _checked)
        require(self._domain_authority(context, state) == packet["original_complete_domain_sha"],
                "A_SOURCE_VERIFIER_ORIGINAL_COMPLETE_DOMAIN_AUTHORITY_DRIFT")
        verify_case = self._verification_case(context, registry)
        static = verify_case(state)
        require(static.get("PASS") is True, "A_SOURCE_VERIFIER_COMPLETE_DOMAIN_OR_MODEL_FAILED")
        typed, types = registry.callable("v42_a_stage_practical/integer_model.py", "restore_types")(state, state["global_types"])
        require(typed.fingerprint() == output.model_sha and types.get("PASS") is True,
                "A_SOURCE_VERIFIER_ORIGINAL_INTEGER_MODEL_SHA_DRIFT")
        with source.np.load(_checked(packet["point"], source_root)) as archive:
            point = archive["X"].copy()
        rows = registry.callable("v42_a_stage_phase1/core.py", "primal_replay")(typed, point)
        integral = float(source.np.max(abs(point[typed.vtypes != "C"] - source.np.rint(point[typed.vtypes != "C"])), initial=0))
        require(rows.get("PASS") is True and integral <= 1e-5, "A_SOURCE_VERIFIER_ORIGINAL_INTEGER_POINT_FAILED")
        bind, coeff = self._binding(context, BuildProfile(context.request.stage), verification=True)
        require(packet["grid_anchor"]["grid_sha"] == context.request.authority.grid_sha and
                packet["grid_anchor"]["pcc_mapping_sha"] == context.request.authority.pcc_mapping_sha and
                tuple(packet["grid_anchor"]["control_names"]) == tuple(coeff[0].control_names),
                "A_SOURCE_VERIFIER_GRID_CONTROL_AUTHORITY_DRIFT")
        write_root = self._verification_write_root(context, output)
        Physical, power = self._physical(context, bind, state, context.input_folder, write_root)
        replay = Physical(state, typed).verify(point)
        require(replay.get("PASS") is True, "A_SOURCE_VERIFIER_INDEPENDENT_PHYSICAL_REPLAY_FAILED")
        require(jsonable(replay["selected_jobs"]) == packet["selected_jobs"] and
                jsonable(replay["controls"]) == packet["grid_anchor"]["controls"],
                "A_SOURCE_VERIFIER_SOURCE_DECISION_POINT_DRIFT")
        with source.np.load(_checked(packet["planning"], source_root)) as archive:
            saved_arrays = {key: jsonable(archive[key]) for key in archive.files}
        # Independently rematerialize the original planning arrays from the
        # reverified integer controls. A sealed saved file alone is not a
        # scientific proof of its PCC/IT/GPU contents.
        replay_folder = write_root / "STATIC/PLANNING_REPLAY"
        replay_folder.mkdir(parents=True, exist_ok=True)
        fresh_planning = self._planning(context, source)(state, replay, power, replay_folder)
        with source.np.load(_checked(fresh_planning, write_root)) as archive:
            recomputed_arrays = {key: jsonable(archive[key]) for key in archive.files}
        require(recomputed_arrays == saved_arrays, "A_SOURCE_VERIFIER_ORIGINAL_PLANNING_ARRAY_REPLAY_DRIFT")
        saved_arrays["time_axis"] = list(context.request.authority.slots)
        require(saved_arrays == packet["planning_arrays"] and
                aidc_from_source(context, saved_arrays, replay, state).sha == output.aidc.sha,
                "A_SOURCE_VERIFIER_FULL_DTO_RESOURCE_POLICY_DRIFT")
        require({uid: domain.sha for uid, domain in state["domains"].items()} == packet["complete_domain_hashes"],
                "A_SOURCE_VERIFIER_COMPLETE_DOMAIN_SHA_DRIFT")
        priced = self._recorded_pricing(context, output, state)
        objective = registry.callable("v42_a_stage_lexfull/runner.py", "objective_value")
        upper = Fraction(objective(typed, point, "rho"))
        lower = Fraction(priced["full_domain_phase1_lower_bound"])
        require(lower <= upper and str(lower) == output.source_result["exact_LB"] and
                str(upper) == output.source_result["exact_UB"], "A_SOURCE_VERIFIER_EXACT_GLOBAL_BOUND_DRIFT")
        require((upper - lower) / max(abs(upper), Fraction(1, 10**12)) <= Fraction("0.005"),
                "A_SOURCE_VERIFIER_EXACT_GLOBAL_GAP_TARGET_FAILED")
        verifier_sha = self._source_digest(context, ("v42_a_stage_acceptance/physical.py",
            "v42_pr134_sc/snapshot.py", "v42_exact/validation.py", "v42_a_stage_canary/pricing.py",
            "v42_a_stage_phase1/oracle.py", "v42_a_stage_lexfull/runner.py"))
        physical = {**output.identity, "PASS": True, "original_integer_physical_verified": True,
            "replay_sha": digest(_scientific(jsonable({"rows": rows, "integral": integral, "physical": replay}))),
            "verifier_source_sha": verifier_sha, "source_physical_replay": _scientific(jsonable(replay)),
            "evidence_kind": registry.evidence_kind,
            "fixed_MESS_independent_replay": self._verify_fixed_native(context, context.source_packets["fixed_mess"])
                if context.request.stage == "A2" else None}
        global_proof = {**output.identity, "PASS": True, "exact_LB": str(lower), "exact_UB": str(upper),
            "bound_scope": "STAGE_FIXED_INPUT_GLOBAL", "original_global_bound_verified": True,
            "verifier_source_sha": verifier_sha, "global_domain_sha": context.request.authority.physical_domain_sha,
            "source_complete_domain_sha": digest(packet["complete_domain_hashes"]),
            "complete_pricing_replay_sha": digest(_scientific(jsonable(priced))), "source_static_verification": jsonable(static),
            "source_original_integer_type_proof": jsonable(types), "joint_global_optimality_claim": False,
            "sealed_source_proof_inputs_sha": digest(packet["proof_input_receipts"]),
            "numerical_policy_receipts": numerical,
            "evidence_kind": registry.evidence_kind}
        for receipt in packet["proof_input_receipts"]:
            _checked(receipt, source_root)
        return {"PASS": True, **output.identity, "physical": physical, "global": global_proof,
                "physical_evidence": physical, "global_evidence": global_proof,
                "verifier_source_sha": verifier_sha, "evidence_kind": registry.evidence_kind}

    def _verification_root(self, context, output):
        root = Path(output.source_packet["source_output"]).resolve()
        require(root == context.output / "SOURCE", "A_SOURCE_VERIFIER_OUTPUT_DRIFT")
        return root

    def _verification_write_root(self, context, output):
        return context.output / "SOURCE"

    def _verification_case(self, context, registry):
        return registry.rebind(A_SOURCE, "verify_case", literal_replacements={"B1": "B3"})

    def verify(self, context, output):
        context.source_registry.admit(context, "A_INDEPENDENT_VERIFY")
        with context.source_registry.execution_scope(context), _restore_source_globals(context.source_registry):
            return self._verify_admitted(context, output)

"""Real M1/M2 construction and hybrid reuse behind the closed source gate.

The original FULL -> Compact -> C3A constructor and anytime hybrid functions
are rebound in an isolated namespace. Stage is routed before native.solve and
GridAuthority construction. The fixed input is the upstream optimized A result;
the B2 FCFS producer is never called. No source module is imported on import of
this file, and no physical equation or optimization algorithm is duplicated.
"""
from fractions import Fraction
from contextlib import contextmanager
import json
from pathlib import Path
from time import perf_counter

from .contracts import MESSDecision, canonical, digest, require, require_sha
from .source_runtime import RealStageContext, SourceStageOutput, jsonable
from .build_runtime import BuildIdentity, ImmutableInputCache
from .scalar_math import original_pcs_math_scope

MODEL_MODULE = "v42_may_campaign_native90.m_model"
STAGE_MODULE = "v42_may_campaign_native90.m_stage"
VERIFIER_FILES = ("v42_may_campaign_native90/m_model.py",
                  "v42_m1_hybrid/final_verify.py", "v42_m1_research/check_lb.py")


def _slot_rows(rows):
    return [list(column) for column in zip(*rows)]


def _plain(value):
    return json.loads(canonical(jsonable(value)))


def _scientific_replay(value):
    """Exclude source measurement timings from a repeatable replay identity."""
    if isinstance(value, dict):
        return {key: _scientific_replay(item) for key, item in value.items()
                if key not in {"validation_wall_seconds", "check_wall_seconds"}}
    if isinstance(value, list):
        return [_scientific_replay(item) for item in value]
    return value


def fixed_aidc_payload(context):
    """Bind the original A materializer's arrays to its entire frozen DTO."""
    require(isinstance(context, RealStageContext), "M_REAL_SOURCE_CONTEXT_REQUIRED")
    request = context.request
    require(request.stage in ("M1", "M2"), "M_SOURCE_STAGE_REQUIRED")
    upstream = context.source_packets.get("fixed_aidc")
    require(isinstance(upstream, dict), "OPTIMIZED_A_SOURCE_PACKET_REQUIRED")
    producer = "A1" if request.stage == "M1" else "A2"
    require(upstream.get("source_stage") == producer, "M_UPSTREAM_A_STAGE_DRIFT")
    require(upstream.get("authority_sha") == request.authority.sha
            and upstream.get("decision_sha") == request.fixed_aidc.sha,
            "M_FIXED_AIDC_SOURCE_IDENTITY_DRIFT")
    require_sha(upstream.get("original_model_sha"))
    evidence = upstream.get("physical_source_evidence", upstream.get("physical_evidence"))
    require(isinstance(evidence, dict) and evidence.get("PASS") is True,
            "M_ORIGINAL_A_PHYSICAL_REPLAY_REQUIRED")
    arrays = upstream.get("planning_arrays")
    require(isinstance(arrays, dict), "ORIGINAL_A_PLANNING_ARRAYS_REQUIRED")
    arrays = _plain(arrays)
    require(arrays.get("sites") == list(request.authority.pcc_ids), "M_SOURCE_PCC_MAPPING_DRIFT")
    for name, rows in (("PCC_P_kw", request.fixed_aidc.pcc_p),
                       ("PCC_Q_kvar", request.fixed_aidc.pcc_q),
                       ("IT_kw", request.fixed_aidc.it_power)):
        require(arrays.get(name) == _slot_rows(rows), "M_ORIGINAL_A_POWER_MATERIALIZATION_DRIFT:" + name)
    for name in ("GPU", "known_GPU"):
        values = arrays.get(name)
        require(isinstance(values, list) and len(values) == 96
                and all(isinstance(row, list) and len(row) == 12 for row in values),
                "M_ORIGINAL_GPU_OCCUPANCY_REQUIRED:" + name)
    selected = _plain(upstream.get("selected_jobs"))
    require(selected == json.loads(request.fixed_aidc.jobs_json)["known_job_actions"],
            "M_FIXED_JOB_PLACEMENT_MIGRATION_DRIFT")
    resource_state = upstream.get("gpu_runtime_state")
    require(resource_state is not None and _plain(resource_state) == json.loads(request.fixed_aidc.gpu_runtime_json),
            "M_FIXED_GPU_RUNTIME_CC4_STATE_DRIFT")
    identity = {**context.identity, "schema": "V42_B3_OPTIMIZED_A_TO_M_SOURCE_V1",
                "PASS": True, "producer_stage": producer,
                "producer_original_model_sha": upstream["original_model_sha"],
                "fixed_AIDC_decision_sha": request.fixed_aidc.sha,
                "selected_jobs_sha": digest(selected),
                "original_A_physical_evidence_sha": digest(_plain(evidence)),
                "physical_power_sha": digest(arrays),
                "time_axis": list(request.authority.slots),
                "B2_FCFS_producer_calls": 0, "AIDC_decision_variables": 0,
                "P2_calls": 0, "historical_bounds_or_runtime_reused": False}
    return {"bundle": context.original_bundle, "planning": arrays,
            "selected_jobs": selected, "identity": identity}


class MSourceBridge:
    """Stage-correct FULL construction, source hybrid and independent replay."""

    def __init__(self):
        self._cases = {}
        self._profiles = {}
        self._input_caches = {}
        self._scalar_receipts = {}

    @contextmanager
    def _phase(self, context, name):
        start = perf_counter()
        try:
            yield
        finally:
            rows = self._profiles.setdefault(self._key(context), {})
            rows[name] = rows.get(name, 0.0) + perf_counter() - start

    @staticmethod
    def _key(context):
        return (context.request.stage, context.request.request_sha, str(context.output))

    @staticmethod
    def _fingerprint(context, case):
        return digest({"stage": context.request.stage,
                       "fixed_input_sha": context.request.fixed_input_sha,
                       "FULL_matrix_sha": case.identity["original_matrix_sha"],
                       "FULL_domain_objective_axis_sha": case.identity["original_domain_sha"],
                       "transport_authority": _plain(case.identity["transport_authority"]),
                       "case_sha": case.case_sha})

    @staticmethod
    def _verifier_sha(context):
        registry = context.source_registry
        if registry.evidence_kind == "FAKE_SOURCE_TEST":
            return digest({"FAKE_SOURCE_TEST_only": list(VERIFIER_FILES)})
        hashes = {name: registry.source_manifest.get(name) for name in VERIFIER_FILES}
        for value in hashes.values():
            require_sha(value)
        return digest(hashes)

    def _native_inputs(self, context, producer):
        """Worker-local route objects only; original source SHA checked per hit.

        No FULL matrix, Compact object, point, dual, bound or native ledger can
        enter this cache. Changed stage/fixed A input uses a separate identity.
        """
        bundle, registry = context.original_bundle, context.source_registry
        if "route_table" not in bundle:
            # Tiny source doubles need no filesystem-backed route table.
            require(registry.evidence_kind == "FAKE_SOURCE_TEST", "M_ORIGINAL_ROUTE_TABLE_REQUIRED")
            return producer(bundle)
        authority = context.request.authority
        identity = BuildIdentity(context.run_id, authority.day, authority.input_sha,
                                 authority.source_sha, authority.physical_domain_sha,
                                 authority.grid_sha, context.request.fixed_input_sha)
        cache_key = digest({"identity": identity.__dict__, "output": str(context.output)})
        cache = self._input_caches.setdefault(cache_key, ImmutableInputCache(identity))
        route = bundle["route_table"]
        input_sha = digest({"bundle": bundle, "fixed_input_sha": context.request.fixed_input_sha})
        def verify_inputs():
            sha = registry.callable("v42_pr134_b1/common.py", "sha")
            require(sha(Path(route["path"])) == route["sha256"], "M_CACHED_ROUTE_SOURCE_SHA_DRIFT")
            battery = registry.resolve("v42_native.mess").Battery(**bundle["battery"])
            battery.validate()
            return {"PASS": True, "input_sha": input_sha, "route_sha": route["sha256"],
                    "source_battery_sha": digest(bundle["battery"]), "authority_sha": authority.sha}
        def produce():
            sites, initial, routes, battery, receipt = producer(bundle)
            return (tuple(sites), tuple(sorted(initial.items())), tuple(routes), battery,
                    canonical(_plain(receipt)))
        sites, initial, routes, battery, receipt = cache.get(identity, "ORIGINAL_ROUTE_TOPOLOGY_INPUTS",
                                                            input_sha, produce, verify_inputs)
        return sites, dict(initial), routes, battery, json.loads(receipt)

    def _construction(self, context, payload, progress):
        registry, grid = context.source_registry, context.grid_authority
        stage, bundle = context.request.stage, payload["bundle"]
        grid.validate(stage, context.request.authority, bundle=bundle)
        native_inputs = registry.callable("v42_bootstrap/m1.py", "native_inputs")
        with self._phase(context, "route_graph_input_seconds"):
            inputs = self._native_inputs(context, native_inputs)
        with self._phase(context, "grid_coefficients_seconds"):
            coefficients = grid.coefficients(bundle, context.request.authority.day)
        grid.validate(stage, context.request.authority, bundle=bundle, coefficients=coefficients)
        expected_rows = grid.thermal_rows_expected(bundle)
        require(type(expected_rows) is int and expected_rows > 0, "M_SOURCE_THERMAL_ROW_COUNT_REQUIRED")
        original_model = registry.resolve(MODEL_MODULE)
        source_compact = registry.resolve("v42_supercompact.formulation").Compact
        source_presolve = registry.resolve("v42_supercompact.presolve").Presolve
        bridge = self
        def compact(*args, **kwargs):
            with bridge._phase(context, "compact_seconds"):
                return source_compact(*args, **kwargs)
        class TimedPresolve(source_presolve):
            def run(self):
                with bridge._phase(context, "presolve_seconds"):
                    return super().run()
        def verify_transport(*args, **kwargs):
            with bridge._phase(context, "exact_transport_seconds"):
                return original_model.verify_transport(*args, **kwargs)
        def transformer_wrapper(builder, thermal):
            wrapped = grid.transformer_wrapper(stage, builder, thermal)
            def timed(*args, **kwargs):
                with bridge._phase(context, "grid_row_construction_seconds"):
                    return wrapped(*args, **kwargs)
            return timed
        imports = {
            "native_inputs": lambda ignored: inputs,
            "original_coefficients_for_day": lambda original, certificate, day: coefficients,
            "physical_authority": lambda: grid.physical_scope(stage, bundle),
            "GridAuthority": lambda *args, **kwargs: grid.make_native_authority(stage, bundle, coefficients),
            "all_transformer_rows": transformer_wrapper,
            "Compact": compact, "Presolve": TimedPresolve,
        }
        builder = registry.rebind(
            MODEL_MODULE, "build_case", import_replacements=imports,
            globals={"_b3_expected_thermal_rows": expected_rows, "_b3_site_count": len(inputs[0]),
                     "verify_transport": verify_transport},
            literal_replacements={"M1": stage, "M1-F3": stage + "-F3", "B2": "B3",
                                  "V42_CURRENT_DATE_B2_M_CASE_V1": "V42_CURRENT_DATE_B3_M_CASE_V1"},
            attribute_replacements={"Stage.M1": "Stage." + stage, "Stage.A1": "Stage." + stage},
            expression_replacements={"120 * 96": "_b3_expected_thermal_rows",
                                     "keyword:sites:24": "_b3_site_count"})
        return builder

    def _prepare(self, context, payload, ledger, progress):
        builder = self._construction(context, payload, progress)
        registry = context.source_registry
        source_request = {**context.identity, "output": str(context.output),
                          "input_folder": str(context.input_folder), "_budget": ledger}
        with self._phase(context, "full_model_and_transport_total_seconds"):
            if registry.evidence_kind == "SOURCE":
                native = registry.resolve("v42_native.mess")
                with original_pcs_math_scope(native, native.__file__,
                        registry.source_manifest.get("v42_native/mess.py")) as (memo, source_proof):
                    case = builder(payload, source_request, progress)
                self._scalar_receipts[self._key(context)] = {
                    "evidence_kind": "SOURCE", "memo": memo.receipt(), "source_proof": dict(source_proof)}
            else:
                case = builder(payload, source_request, progress)
                self._scalar_receipts[self._key(context)] = {
                    "evidence_kind": "FAKE_SOURCE_TEST", "status": "NOT_APPLIED_TO_FAKE_MODEL",
                    "real_performance_comparison": "NOT_RUN"}
        require(case.identity.get("arm") == "B3"
                and case.identity["input_identity"]["stage"] == context.request.stage,
                "M_ORIGINAL_CONSTRUCTION_STAGE_IDENTITY_DRIFT")
        registry.callable("v42_may_campaign_native90/m_model.py", "verify_case")(case)
        self._cases[self._key(context)] = case
        point = None
        candidate_evidence = {"PASS": False, "status": "NO_M1_CANDIDATE", "Native_optimize_calls": 0}
        if context.request.stage == "M2" and "warm_mess" in context.source_packets:
            point, candidate_evidence = self._warm_candidate(context, case)
        if point is None:
            point, stationary = registry.callable("v42_may_campaign_native90/m_stage.py", "stationary_candidate")(case)
        else:
            stationary = {"status": "NOT_USED_VALIDATED_M1_NEW_A2_ANCHOR"}
        atomic = registry.callable("v42_pr134_b1/common.py", "atomic")
        atomic(case.output / "B3_WARM_START_ADMISSION.json", candidate_evidence)
        atomic(case.output / "SAME_DAY_STATIONARY_CANDIDATE.json", stationary)
        case.point = point
        return case

    def _warm_candidate(self, context, case):
        """Reconstruct M1 primary variables in the NEW M2 FULL source matrix."""
        source = context.source_packets["warm_mess"]
        require(source.get("source_stage") == "M1"
                and source.get("authority_sha") == context.request.authority.sha,
                "M2_WARM_SOURCE_DATE_AUTHORITY_DRIFT")
        require(source.get("graph_sha") == digest(_plain(case.graph)), "M2_WARM_ORIGINAL_GRAPH_DRIFT")
        registry = context.source_registry
        original = registry.resolve("v42_integrated.start")
        values = source["mess_plan"]["values"]
        names = [str(name) for name in case.original_d["names"]
                 if str(name).split("[", 1)[0] in original.PRIMARY]
        require(all(name in values for name in names), "M2_WARM_PRIMARY_AXIS_INCOMPLETE")
        try:
            raw, reconstruction = original.reconstruct(case.original_A, case.original_d,
                                                       names, [values[name] for name in names])
            require(reconstruction.get("PASS") is True, "M2_WARM_NEW_FULL_MATRIX_INFEASIBLE")
            point = case.presolve.forward(case.compact.forward(raw))
            path = case.output / "M1_CANDIDATE_UNDER_NEW_A2_POINT.npz"
            registry.resolve(MODEL_MODULE).np.savez_compressed(path, point=point)
            strict = registry.callable("v42_m1_hybrid/final_verify.py", "_strict_ub")(case, path, {})
            require(strict.get("PASS") is True, "M2_WARM_NEW_ORIGINAL_PHYSICAL_INFEASIBLE")
            return point, {"PASS": True, "case_sha": case.case_sha,
                           "new_fixed_A2_sha": context.request.fixed_aidc.sha,
                           "original_integer_physical_replay": strict,
                           "old_LB_UB_Runtime_transferred": False, "Native_optimize_calls": 0}
        except ValueError as error:
            return None, {"PASS": False, "status": "REJECTED_UNDER_NEW_A2_ANCHOR",
                          "reason": str(error), "new_case_sha": case.case_sha,
                          "old_LB_UB_Runtime_transferred": False, "Native_optimize_calls": 0}

    @staticmethod
    def _mess_decision(context, case, plan):
        """Permute original source values into DTO axes; no battery/grid math."""
        units = tuple(plan["unit_ids"])
        require(units == tuple(context.request.authority.mess_ids), "M_ORIGINAL_UNIT_AXIS_DRIFT")
        locations = [list(column) for column in zip(*plan["locations"])]
        values, arcs = plan["values"], case.graph[2]
        charge, discharge, travel, modes, routes = [], [], [], [], []
        for index, unit in enumerate(units):
            selected = list(plan["chosen_arcs"][unit])
            routes.append(tuple(str(k) for k in selected))
            ch, dis, energy, mode = [], [], [0.0] * 96, []
            for t, site in enumerate(locations[index]):
                connected = any(arcs[k][0] == site and arcs[k][1] == t and arcs[k][-1] is None for k in selected)
                ch.append(values[f"Pch[{unit},{site},{t}]"] if connected else 0.0)
                dis.append(values[f"Pdis[{unit},{site},{t}]"] if connected else 0.0)
                mode.append(values[f"charge_mode[{unit},{t}]"])
            for k in selected:
                arc = arcs[k]
                if arc[-1] is not None:
                    require(energy[arc[1]] == 0, "MULTIPLE_ORIGINAL_MOVE_ARCS_SAME_DEPARTURE")
                    energy[arc[1]] = arc[-1].energy_kwh
            charge.append(ch); discharge.append(dis); travel.append(energy); modes.append(mode)
        soc = [list(column) for column in zip(*plan["SOC_kwh"])]
        variables = {"movement": plan["routes"], "charge_mode": modes,
                     "route": plan["chosen_arcs"], "P": {"Pch": charge, "Pdis": discharge},
                     "Q": plan["Q_kvar"], "SOC": plan["SOC_kwh"], "original_values": values,
                     "source_stage": context.request.stage, "full_source_values_sha": digest(values)}
        decision = MESSDecision(routes=routes, location=locations, charge_p=charge,
                                discharge_p=discharge, q=[list(column) for column in zip(*plan["Q_kvar"])],
                                soc=soc, initial_final_json=canonical({"initial": [row[0] for row in soc],
                                                                      "final": [row[-1] for row in soc],
                                                                      "initial_sites": plan["initial_sites"]}),
                                move_energy=travel, variables_json=canonical(variables))
        plan = dict(plan, Pch_kw=_slot_rows(decision.charge_p), Pdis_kw=_slot_rows(decision.discharge_p),
                    charge_mode=_slot_rows(modes), move_energy_kwh=_slot_rows(decision.move_energy))
        return decision, plan

    @staticmethod
    def _controls(case, plan):
        controls = []
        names = list(case.coefficients[0].control_names)
        for t, coefficients in enumerate(case.coefficients):
            require(list(coefficients.control_names) == names, "M_GRID_CONTROL_AXIS_DRIFT")
            row = []
            for i, name in enumerate(names):
                site = name.split("[", 1)[1][:-1]
                if name.startswith("aidc_load_kw"):
                    row.append(case.anchor["controls"][t][i])
                else:
                    family = "injection_P" if name.startswith("mess_p_kw") else "injection_Q" if name.startswith("mess_q_kvar") else None
                    require(family is not None, "M_ORIGINAL_GRID_CONTROL_FAMILY_REQUIRED")
                    key = f"{family}[{site},{t}]"
                    require(key in plan["values"], "M_ORIGINAL_GRID_HELPER_VALUE_MISSING")
                    row.append(plan["values"][key])
            controls.append(row)
        return names, controls

    def execute(self, context, ledger, progress=None, *, lb_rescue=None):
        registry = context.source_registry
        registry.admit(context, "M_SOURCE_MODEL_AND_HYBRID")
        require(getattr(ledger, "context", None) is context
                and getattr(ledger, "stage", None) == context.request.stage,
                "M_SOURCE_STAGE_LEDGER_DRIFT")
        with registry.execution_scope(context):
            if lb_rescue is not None:
                lb_rescue = registry.callable("v42_b3_joint/lb_research.py", "checked_factory")(
                    lb_rescue, context, registry)
            started = perf_counter()
            with self._phase(context, "input_preparation_seconds"):
                payload = fixed_aidc_payload(context)
            stage = context.request.stage
            prepare = lambda request, callback=None: self._prepare(context, payload, ledger, callback)
            routing = {"B2": "B3", "M_STAGE_RESULT.json": stage + "_STAGE_RESULT.json"}
            seed = registry.rebind(STAGE_MODULE, "_seed_integer", literal_replacements=routing)
            fresh = registry.rebind(STAGE_MODULE, "_fresh_lp_dual", literal_replacements=routing)
            plan = registry.rebind(STAGE_MODULE, "_plan", literal_replacements=routing)
            run = registry.rebind(STAGE_MODULE, "run", globals={"prepare": prepare, "_seed_integer": seed,
                                  "_fresh_lp_dual": fresh, "_plan": plan}, literal_replacements=routing)
            request = {**context.identity, "input_folder": str(context.input_folder), "output": str(context.output)}
            result = (run(request, ledger, progress) if lb_rescue is None else
                      run(request, ledger, progress, lb_rescue=lb_rescue))
            require(result.get("accepted") is True and type(result.get("P2_calls")) is int
                    and result["P2_calls"] == 0,
                    "M_SOURCE_RESULT_NOT_INDEPENDENTLY_ACCEPTED")
            case = self._cases[self._key(context)]
            result = dict(result, stage=stage, **{"fixed_input_sha": context.request.fixed_input_sha})
            decision, source_plan = self._mess_decision(context, case, result["mess"])
            names, controls = self._controls(case, source_plan)
            context.grid_authority.validate(stage, context.request.authority, bundle=context.original_bundle,
                                            coefficients=case.coefficients, controls=controls)
            model_sha = self._fingerprint(context, case)
            packet = {**context.identity, "source_stage": stage,
                      "authority_sha": context.request.authority.sha, "decision_sha": decision.sha,
                      "original_model_sha": model_sha, "case_sha": case.case_sha,
                      "full_aidc_decision_sha": context.request.fixed_aidc.sha,
                      "upstream_original_A_model_sha": payload["identity"]["producer_original_model_sha"],
                      "mess_plan": _plain(source_plan), "values": _plain(source_plan["values"]),
                      "chosen_arcs": _plain(source_plan["chosen_arcs"]),
                      "initial_sites": _plain(source_plan["initial_sites"]), "mode": "MILP",
                      "graph": _plain(case.graph), "graph_sha": digest(_plain(case.graph)),
                      "controls": controls, "control_names": names,
                      "planning_arrays": _plain(payload["planning"]),
                      "selected_jobs": payload["selected_jobs"],
                      "case_identity": _plain(case.identity), "anchor": _plain(case.anchor),
                      "raw_point": _plain(case.point),
                      "source_exact_LB": result["exact_Global_LB"], "source_exact_UB": result["exact_Global_UB"],
                      "raw_point_path": str(case.output / "BEST_STRICT_UB_POINT.npz"),
                      "dual_path": str(case.output / "BEST_EXACT_ORIGINAL_DUAL.json"),
                      "build_profile_seconds": dict(self._profiles.get(self._key(context), {})),
                      "original_pcs_scalar_math_memo": self._scalar_receipts[self._key(context)],
                      "immutable_route_input_cache": [cache.receipt() for cache in self._input_caches.values()],
                      "B2_FCFS_producer_calls": 0, "AIDC_decision_variables": 0,
                      "optimized_families": ["arc", "charge_mode", "Pch", "Pdis", "Q", "SOC", "rho_max"]}
            output = SourceStageOutput(context.request, _plain(result), context.request.fixed_aidc,
                                       decision, model_sha, {}, {}, packet, ledger.sealed_receipt(),
                                       evidence_kind=registry.evidence_kind)
            evidence = self.verify(context, output)
            from dataclasses import replace
            packet["physical_source_evidence"] = evidence["physical"]
            packet["stage_total_wall_seconds"] = perf_counter() - started
            return replace(output, physical_evidence=evidence["physical"], global_evidence=evidence["global"],
                           source_packet=packet)

    def _restore_case(self, context, packet):
        """Reload this B3 case and replay source static transport, without Model."""
        registry = context.source_registry
        model = registry.resolve(MODEL_MODULE)
        numeric, sparse = model.np, model.sparse
        native = registry.callable("v42_bootstrap/m1.py", "native_inputs")(context.original_bundle)
        sites, initial, routes, battery, receipt = native
        graph = (sites, initial, [(s, t, s, t + 1, None) for s in sites for t in range(96)]
                 + [(r.source, r.depart, r.destination, r.connect, r) for r in dict.fromkeys(routes)], battery, receipt)
        require(digest(_plain(graph)) == packet["graph_sha"], "M_RESTORED_ORIGINAL_GRAPH_DRIFT")
        A = sparse.load_npz(context.output / "FULL_A.npz")
        with numeric.load(context.output / "FULL_DATA.npz", allow_pickle=False) as archive:
            data = {key: archive[key].copy() for key in archive.files}
        compact = registry.resolve("v42_supercompact.formulation").Compact(A, data, graph[2], initial, 96)
        presolve = registry.resolve("v42_supercompact.presolve").Presolve(compact.A, compact.d)
        B, selected = presolve.run()
        proof = model.verify_transport(compact, presolve)
        require(_plain(proof) == packet["case_identity"]["transport"], "M_RESTORED_TRANSPORT_PROOF_DRIFT")
        coefficients = context.grid_authority.coefficients(context.original_bundle, context.request.authority.day)
        case = model.CampaignMCase(B, selected, A, data, packet["raw_point"], graph, packet["case_sha"],
                                  packet["case_identity"], compact, presolve, context.original_bundle,
                                  packet["anchor"], packet["planning_arrays"], coefficients, context.output)
        model.verify_case(case)
        self._cases[self._key(context)] = case
        return case

    def verify(self, context, output):
        registry = context.source_registry
        registry.admit(context, "M_INDEPENDENT_ORIGINAL_VERIFICATION")
        with registry.execution_scope(context):
            require(output.request == context.request and output.evidence_kind == registry.evidence_kind,
                    "M_SOURCE_OUTPUT_REQUEST_DRIFT")
            require(output.aidc.sha == context.request.fixed_aidc.sha,
                    "M_SOURCE_CHANGED_FULL_FIXED_AIDC")
            payload = fixed_aidc_payload(context)
            packet = output.source_packet
            require(packet["source_stage"] == context.request.stage and packet["authority_sha"] == context.request.authority.sha
                    and packet["fixed_input_sha"] == context.request.fixed_input_sha,
                    "M_SOURCE_PACKET_STAGE_AUTHORITY_DRIFT")
            case = self._cases.get(self._key(context)) or self._restore_case(context, packet)
            require(case.identity["input_identity"] == payload["identity"]
                    and packet["full_aidc_decision_sha"] == context.request.fixed_aidc.sha
                    and packet["upstream_original_A_model_sha"] == payload["identity"]["producer_original_model_sha"]
                    and _plain(case.planning) == payload["planning"] == packet["planning_arrays"]
                    and packet["selected_jobs"] == payload["selected_jobs"],
                    "M_INDEPENDENT_UPSTREAM_A_SOURCE_ANCHOR_DRIFT")
            require(self._fingerprint(context, case) == output.model_sha == packet["original_model_sha"],
                    "M_FULL_ORIGINAL_MODEL_SHA_DRIFT")
            proof = registry.callable("v42_may_campaign_native90/m_model.py", "verify_case")(case)
            require(proof.get("PASS") is True, "M_FULL_COMPACT_C3A_EQUIVALENCE_FAILED")
            point_path, dual_path = Path(packet["raw_point_path"]), Path(packet["dual_path"])
            require(point_path.resolve() == context.output / "BEST_STRICT_UB_POINT.npz"
                    and dual_path.resolve() == context.output / "BEST_EXACT_ORIGINAL_DUAL.json",
                    "M_INDEPENDENT_CERTIFICATE_PATH_ESCAPE")
            strict = registry.callable("v42_m1_hybrid/final_verify.py", "_strict_ub")(case, point_path, {})
            point_sha = registry.callable("v42_m1_research/check_ub.py", "vector_sha")(case.point)
            require(strict.get("point_vector_sha256") == point_sha
                    and _plain(case.point) == packet["raw_point"], "M_SOURCE_RAW_POINT_REPLAY_DRIFT")
            reader = registry.callable("v42_pr134_b1/common.py", "read")
            dual = reader(dual_path)
            exact = registry.callable("v42_m1_research/check_lb.py", "check_rational_dual_certificate")(
                case.A, case.d, dual, case_sha=case.case_sha)
            require(strict.get("PASS") is True and exact.get("PASS") is True,
                    "M_ORIGINAL_INTEGER_PHYSICAL_OR_GLOBAL_BOUND_FAILED")
            lower, upper = Fraction(exact["exact_bound"]), Fraction(strict["exact_Global_UB"])
            require(0 <= lower <= upper and (upper == 0 or (upper - lower) / upper <= Fraction(3, 100)),
                    "M_INDEPENDENT_EXACT_GLOBAL_GAP_NOT_ACCEPTED")
            require(str(lower) == packet["source_exact_LB"] and str(upper) == packet["source_exact_UB"],
                    "M_INDEPENDENT_FINAL_BOUND_DRIFT")
            original_plan = registry.rebind(STAGE_MODULE, "_plan", literal_replacements={"B2": "B3"})(case, case.point)
            mess, enhanced_plan = self._mess_decision(context, case, original_plan)
            require(mess.sha == output.mess.sha == packet["decision_sha"], "M_ORIGINAL_POINT_DECISION_REPLAY_DRIFT")
            names, controls = self._controls(case, enhanced_plan)
            require(_plain(enhanced_plan) == packet["mess_plan"]
                    and _plain(enhanced_plan["values"]) == packet["values"]
                    and _plain(enhanced_plan["chosen_arcs"]) == packet["chosen_arcs"]
                    and _plain(enhanced_plan["initial_sites"]) == packet["initial_sites"],
                    "M_FROZEN_SOURCE_PLAN_VALUE_DRIFT")
            require(names == packet["control_names"] and controls == packet["controls"],
                    "M_ORIGINAL_FULL_HELPER_CONTROL_REPLAY_DRIFT")
            context.grid_authority.validate(context.request.stage, context.request.authority,
                                            bundle=context.original_bundle,
                                            coefficients=case.coefficients, controls=controls)
            verifier_sha = self._verifier_sha(context)
            identity = output.identity
            physical = {**identity, "PASS": True, "original_integer_physical_verified": True,
                        "replay_sha": digest(_scientific_replay(_plain(strict))), "verifier_source_sha": verifier_sha,
                        "source_replay": _scientific_replay(_plain(strict)),
                        "transport": _scientific_replay(_plain(proof)),
                        "evidence_kind": registry.evidence_kind}
            global_evidence = {**identity, "PASS": True, "exact_LB": str(lower), "exact_UB": str(upper),
                               "bound_scope": "STAGE_FIXED_INPUT_GLOBAL",
                               "global_domain_sha": context.request.authority.physical_domain_sha,
                               "verifier_source_sha": verifier_sha, "original_global_bound_verified": True,
                               "source_weak_duality_certificate": _scientific_replay(_plain(exact)),
                               "joint_global_optimality_claim": False, "evidence_kind": registry.evidence_kind}
            return {"PASS": True, "physical": physical, "global": global_evidence,
                    "original_model_sha": output.model_sha, "evidence_kind": registry.evidence_kind}

"""Same-day B1 P1 A1 reuse with fresh original model/domain comparison.

Saved B1 integer points and exact pricing certificates are independently
replayed. All verifier output is written in the new B3 attempt. The original
B1 directories and their historical Native accounting remain read-only.
"""
from dataclasses import asdict, replace
from fractions import Fraction
from pathlib import Path
import gzip
import json
import pickle
import hashlib
import re
import subprocess

from v42_b3_joint.a_source import ASourceBridge, A_SOURCE, BuildProfile, _restore_source_globals, _scientific
from v42_b3_joint.contracts import canonical, digest, require
from v42_b3_joint.model_mapping import aidc_from_source
from v42_b3_joint.source_runtime import SourceStageOutput, jsonable
from .admission import read, record, checked

GRAPH_CACHE_COMPILERS = ("v42_root/data.py", "v42_root/common.py", "v42_exact/support.py", "v42_exact/common.py",
    "v42_compact/graph.py", "v42_compact/common.py", "v42_boundary/generator.py", "v42_job_capability.py")


def graph_compiler_equivalence(registry, producer_commit):
    """Admit cached graphs only from exact original compiler Git blobs."""
    require(isinstance(producer_commit, str) and re.fullmatch(r"[0-9a-f]{40}", producer_commit),
            "B1_ORIGINAL_GRAPH_COMPILER_COMMIT_REQUIRED")
    compilers = []
    for relative in GRAPH_CACHE_COMPILERS:
        current = record(registry.root / relative)
        require(current["sha256"] == registry.source_manifest[relative], "SOURCE_FILE_SHA_DRIFT:" + relative)
        try:
            blob = subprocess.check_output(["git", "-C", str(registry.root), "show", producer_commit + ":" + relative],
                                           stderr=subprocess.PIPE)
        except (subprocess.CalledProcessError, FileNotFoundError) as error:
            return {"PASS": False, "Native_calls": 0, "producer_commit": producer_commit,
                    "reason": "ORIGINAL_GRAPH_COMPILER_BLOB_UNAVAILABLE:" + type(error).__name__,
                    "compiler_files": compilers, "fresh_original_graphs_required": True}
        historical = hashlib.sha256(blob).hexdigest()
        if historical != current["sha256"]:
            return {"PASS": False, "Native_calls": 0, "producer_commit": producer_commit,
                    "reason": "ORIGINAL_GRAPH_COMPILER_BYTES_DIFFER:" + relative,
                    "compiler_files": compilers, "fresh_original_graphs_required": True}
        compilers.append({"relative": relative, "original_blob_sha256": historical,
                          "original_blob_bytes": len(blob), "current": current})
    return {"PASS": True, "Native_calls": 0, "producer_commit": producer_commit,
            "compiler_files": compilers, "fresh_original_graphs_required": False}


def compare_original_identity(fresh, old, prepare, domain_digest):
    """Compare original matrices, variable domains, objectives and every job."""
    left, right = fresh["reference"].fingerprint(), old["reference"].fingerprint()
    require(left == right == prepare["verification"]["reference_snapshot_sha256"],
            "B1_B3_A1_ORIGINAL_MATRIX_DOMAIN_OBJECTIVE_MISMATCH")
    fresh_domains = {uid: domain.sha for uid, domain in sorted(fresh["domains"].items())}
    old_domains = {uid: domain.sha for uid, domain in sorted(old["domains"].items())}
    require(fresh_domains == old_domains and
            set(fresh["data"][1]) == set(old["data"][1]) == set(fresh_domains),
            "B1_B3_A1_COMPLETE_JOB_SCHEDULING_DOMAIN_MISMATCH")
    require(fresh["data"][0] == old["data"][0], "B1_B3_A1_CAUSAL_BUNDLE_RUNTIME_CC4_MISMATCH")
    require(fresh["reference"].fingerprint() == fresh["compact"].fingerprint(),
            "B3_A1_ORIGINAL_FULL_COMPACT_EQUIVALENCE_REQUIRED")
    # The matrix fingerprint includes coefficients/RHS, bounds, all variable
    # types and every original objective. The complete domain roster includes
    # all omitted STAY/migration columns, beyond the active initial matrix.
    return {"PASS": True, "original_matrix_domain_objective_sha": left,
            "complete_domain_sha": domain_digest(fresh_domains),
            "job_population_sha": digest(sorted(fresh_domains)),
            "fresh_reference_compact_equal": fresh["reference"].fingerprint() == fresh["compact"].fingerprint(),
            "objective": "rho", "full_integer_domain_preserved": True,
            "bundle_and_runtime_CC4_equal": True}


class B1A1ReuseBridge(ASourceBridge):
    def __init__(self, b1_output, *, reuse_input_cache=True):
        self.b1_output = Path(b1_output).resolve()
        self.reuse_input_cache = reuse_input_cache

    def _cache_packet(self, context):
        if not self.reuse_input_cache:
            return None
        _, _, origin = self._verify_origin(context)
        receipt_path = self.b1_output / "STATIC/DOMAIN" / context.request.authority.day / "PHYSICAL_DOMAIN_CACHE.json"
        document = read(receipt_path)
        require(document.get("PASS") is True and document.get("scientific_candidates_removed") == 0,
                "B1_A1_COMPLETE_INPUT_CACHE_REQUIRED")
        # Path ownership remains the original B1 checkout. Each physical
        # membership compiler is independently byte-identical to current code.
        for receipt in document["producer_sources"]:
            old = checked(receipt)
            relative = old.name if old.name == "v42_job_capability.py" else "/".join(old.parts[-2:])
            current = context.source_registry.root / relative
            require(record(current)["sha256"] == receipt["sha256"] and
                    context.source_registry.source_manifest[relative] == receipt["sha256"],
                    "B1_A1_DOMAIN_COMPILER_SOURCE_MISMATCH:" + relative)
        return {"day": context.request.authority.day, "authority_sha": context.request.authority.sha,
                "producer_source_sha": context.producer_source_sha, "output": str(self.b1_output),
                "origin_commit": origin["git_head"],
                "DATA": document["frozen_DATA"], "producer_sources": document["producer_sources"],
                "inputs": read(self.b1_output / "A_NATIVE_SOURCE_FREEZE.json")["inputs"],
                "protected_receipts": [record(receipt_path), document["cache"], document["frozen_DATA"]]}

    def _seed_input_cache(self, context, request, source_data_module, base):
        packet = self._cache_packet(context)
        if packet is None:
            return False
        registry = context.source_registry
        proof = graph_compiler_equivalence(registry, packet["origin_commit"])
        proof.update(day=context.request.authority.day, source_sha=context.producer_source_sha,
                     graph_cache_reused=False)
        proof_path = context.output / "B1_GRAPH_COMPILER_EQUIVALENCE.json"
        proof_path.write_text(canonical(proof) + "\n", encoding="utf-8")
        if proof["PASS"] is not True:
            # DATA graphs are freshly reconstructed by the unchanged producer.
            # Complete physical-cache hashes and final full matrix/domain
            # comparison remain mandatory on this path.
            return False
        def admitted(actual_request, source):
            require(Path(source).resolve() == self.b1_output, "B1_A1_INPUT_CACHE_SOURCE_DRIFT")
            for receipt in packet["protected_receipts"]:
                checked(receipt, self.b1_output)
            for name, receipt in packet["inputs"].items():
                require(record(context.input_folder / name)["sha256"] == receipt["sha256"],
                        "B1_A1_INPUT_CACHE_SAME_DAY_BYTES_DRIFT")
            return {"DATA": packet["DATA"]}
        # Original seed_input_cache re-reads load_native(), compares every
        # Job/Boundary/Resource/Runtime field and independently recomputes class
        # signatures before copying input graphs. No model/point/dual is seeded.
        seed = registry.rebind("v42_may_build_v6.input_cache", "seed_input_cache",
                               globals={"verify_cache_authority": admitted})
        reused = seed(request, source_data_module, base)
        proof["graph_cache_reused"] = reused
        proof_path.write_text(canonical(proof) + "\n", encoding="utf-8")
        return reused

    def _domain_cache(self, context, request, fresh_data, check=lambda: None, progress=None):
        packet = self._cache_packet(context)
        if packet is None:
            return None
        registry = context.source_registry
        for receipt in packet["protected_receipts"]:
            checked(receipt, self.b1_output)
        with checked(packet["DATA"], self.b1_output).open("rb") as stream:
            old_data = pickle.load(stream)
        semantic = registry.callable("v42_may_build_v6/a_cache.py", "_semantic_data")
        require(semantic(old_data) == semantic(fresh_data), "B1_A1_INPUT_CACHE_FULL_SCIENTIFIC_VALUES_DRIFT")
        # Route only old provenance paths after checking identical compiler
        # bytes; load_physical_cache retains original resource/class/SHA checks.
        load = registry.rebind("v42_a_stage_domain_v2.fast_census", "load_physical_cache",
                              globals={"_producer_sources": lambda: packet["producer_sources"]})
        domains = load(request["day"], old_data, checked(packet["DATA"], self.b1_output),
                       self.b1_output / "STATIC/DOMAIN")
        original_hash = registry.callable("v42_may_build_v6/build_reuse.py", "domain_hash")
        require(set(domains) == set(fresh_data[1]), "B1_A1_INPUT_CACHE_COMPLETE_JOB_DOMAIN_AXIS")
        verified = {}
        for uid, domain in domains.items():
            check()
            require(domain.cache.r == fresh_data[3] and domain.duration == fresh_data[1][uid].service_slots,
                    "B1_A1_INPUT_CACHE_ORIGINAL_RESOURCE_DURATION_DRIFT")
            # Equivalent class members differ only by UID, excluded by the
            # original domain hash. Reuse the calculation after comparing all
            # domain-defining job/boundary fields for that representative.
            scientific_key = (id(domain), canonical({k: v for k, v in asdict(fresh_data[1][uid]).items() if k != "uid"}),
                              fresh_data[2][uid].latest_completion)
            if scientific_key not in verified:
                verified[scientific_key] = original_hash(fresh_data[1][uid], fresh_data[2][uid], domain)
            require(verified[scientific_key] == domain.sha, "B1_A1_INPUT_CACHE_COMPLETE_PHYSICAL_HASH_DRIFT")
        for receipt in packet["protected_receipts"]:
            checked(receipt, self.b1_output)
        cache_evidence = {"PASS": True, "day": context.request.authority.day,
            "complete_domains_verified": len(domains), "domain_defining_classes_verified": len(verified),
            "old_compiler_receipts": packet["producer_sources"], "protected_receipts": packet["protected_receipts"],
            "fresh_scientific_input_semantics": semantic(fresh_data), "Native_calls": 0,
            "old_points_bounds_models_loaded_as_input_cache": False}
        path = context.output / "B1_IMMUTABLE_INPUT_CACHE_VERIFICATION.json"
        path.write_text(canonical(cache_evidence) + "\n", encoding="utf-8")
        if progress:
            progress({"phase": "B1_IMMUTABLE_DOMAIN_CACHE_VERIFIED", "stage": "A1", "Native_calls": 0})
        return domains

    def _verify_origin(self, context, output=None):
        require(context.request.stage == "A1" and context.request.fixed_mess is None and
                context.request.fixed_aidc is None, "B1_REUSE_ONLY_IDENTICAL_A1_ALLOWED")
        root = self.b1_output
        require(root != context.output and not root.is_relative_to(context.output),
                "B1_REUSE_SOURCE_OUTPUT_SEPARATION_REQUIRED")
        result, freeze = read(root / "A_RESULT.json"), read(root / "B1_P1_FREEZE.json")
        day = context.request.authority.day
        require(result.get("PASS") is True and result.get("accepted") is True and
                result.get("day") == day and result.get("arm") == "B1" and
                freeze.get("PASS") is True and freeze.get("accepted") is True and
                freeze.get("day") == day and freeze.get("arm") == "B1" and
                freeze.get("A1_P1_ONLY_ACCEPTED") is True and freeze.get("P1_only") is True and
                freeze.get("P2_calls") == result.get("P2_calls") == 0 and
                freeze.get("MESS_optimization_calls") == result.get("MESS_optimization_calls") == 0 and
                freeze.get("all_MESS_PQ_zero") is result.get("all_MESS_PQ_zero") is True,
                "B1_ORIGINAL_SAME_DAY_P1_A1_FREEZE_REQUIRED")
        require(checked(result["freeze"], root) == root / "B1_P1_FREEZE.json",
                "B1_A1_ORIGINAL_FREEZE_PATH_DRIFT")
        for name in ("physical", "acceptance", "global_bound", "validated_original_integer_point", "planning"):
            checked(freeze[name], root)
        for name, receipt in freeze["scientific_input"].items():
            require(name in ("NATIVE_INPUT.json", "WINDOWS.json"), "B1_A1_INPUT_PACKET_AXIS")
            checked(receipt)
            require(record(context.input_folder / name)["sha256"] == receipt["sha256"],
                    "B1_B3_A1_INPUT_BYTES_MISMATCH:" + name)
        source = read(checked(freeze["source"], root))
        # Preserve the producing code identity; code upgrades are admitted by
        # the independent fresh model comparison, never relabelled as B1 code.
        require(source.get("PASS") is True and source.get("day") == day and source.get("arm") == "B1",
                "B1_A1_ORIGINAL_SOURCE_RECEIPT_REQUIRED")
        lower, upper = Fraction(result["exact_LB"]), Fraction(result["exact_UB"])
        require(0 <= lower <= upper and (upper == 0 or (upper - lower) / upper <= Fraction(1, 200)),
                "B1_A1_ORIGINAL_EXACT_GAP_NOT_ACCEPTED")
        if output is not None:
            reuse = output.source_packet["b1_reuse"]
            for receipt in reuse["origin_receipts"]:
                checked(receipt, root)
            require(reuse["day"] == day and reuse["source_result_sha"] == record(root / "A_RESULT.json")["sha256"] and
                    reuse["producer_commit"] == source["git_head"] and reuse["new_native_optimize_calls"] == 0 and
                    reuse["new_native_runtime_seconds"] == 0 and reuse["verified_reuse"] is True and
                    reuse["equivalence"]["PASS"] is True,
                    "B1_A1_REUSE_RECEIPT_IDENTITY_DRIFT")
            # Reload the fresh Native-zero comparison artifact at every handoff.
            equivalence = read(checked(reuse["equivalence_receipt"], context.output))
            require(equivalence == reuse["equivalence"], "B1_A1_FRESH_MODEL_EQUIVALENCE_RECEIPT_DRIFT")
            if reuse.get("graph_compiler_proof"):
                proof = read(checked(reuse["graph_compiler_proof"], context.output))
                require(proof["Native_calls"] == 0 and proof["source_sha"] == context.producer_source_sha and
                        proof["producer_commit"] == source["git_head"], "B1_GRAPH_COMPILER_RECEIPT_IDENTITY_DRIFT")
                if proof["graph_cache_reused"]:
                    require(proof["PASS"] is True and len(proof["compiler_files"]) == len(GRAPH_CACHE_COMPILERS),
                            "B1_GRAPH_COMPILER_CACHE_ADMISSION_REQUIRED")
                    for row in proof["compiler_files"]:
                        current = checked(row["current"], context.source_registry.root)
                        require(current == context.source_registry.root / row["relative"] and
                                row["current"]["sha256"] == row["original_blob_sha256"] ==
                                context.source_registry.source_manifest[row["relative"]],
                                "B1_GRAPH_COMPILER_SOURCE_HANDOFF_DRIFT")
        return result, freeze, source

    def execute(self, context, ledger, progress=None):
        registry = context.source_registry
        registry.admit(context, "B1_A1_REUSE_INDEPENDENT_ADMISSION")
        result, freeze, origin = self._verify_origin(context)
        profile = BuildProfile("A1")
        with registry.execution_scope(context), _restore_source_globals(registry):
            source, run, bind, verify_case, coefficients = self._configure(context, ledger, progress, profile)
            # The original prepare constructs the FULL reference and complete
            # physical domain under native_zero_scope; it never optimizes.
            if progress:
                progress({"phase": "A1_REUSE_FRESH_FULL_MODEL_COMPARISON", "stage": "A1", "Native_calls": 0})
            fresh = run.__globals__["prepare"](self._request(context), progress)
            closed = record(self.b1_output / "STATIC/P1_CLOSED_STATE.pkl.gz")
            with gzip.open(closed["path"], "rb") as stream:
                old = pickle.load(stream)
            domain_digest = registry.callable("v42_a_stage_domain_v2/domain.py", "digest")
            equivalence = compare_original_identity(fresh, old, read(self.b1_output / "A_PREPARE_RECEIPT.json"), domain_digest)
            require(equivalence["complete_domain_sha"] == context.request.authority.physical_domain_sha,
                    "B1_B3_A1_AUTHORITY_COMPLETE_DOMAIN_MISMATCH")
            require(ledger.receipt()["native_call_count"] == 0 and ledger.used() == 0,
                    "B3_REUSED_A1_NATIVE_OPTIMIZE_FORBIDDEN")
            eq_path = context.output / "B1_A1_MODEL_EQUIVALENCE.json"
            eq_path.write_text(canonical(equivalence) + "\n", encoding="utf-8")
            with source.np.load(checked(result["planning"], self.b1_output)) as archive:
                planning = {key: jsonable(archive[key]) for key in archive.files}
            planning["time_axis"] = list(context.request.authority.slots)
            replay = read(checked(result["incumbent"]["physical"], self.b1_output))
            decision = aidc_from_source(context, planning, replay, old)
            identity = read(self.b1_output / "P1/INTEGER_CONTROL/MODEL_IDENTITY.json")
            model_sha = identity["original_snapshot_sha256"]
            reuse = {"day": context.request.authority.day, "verified_reuse": True,
                     "producer_commit": origin["git_head"], "producer_source_receipt": record(self.b1_output / "A_NATIVE_SOURCE_FREEZE.json"),
                     "source_result_sha": record(self.b1_output / "A_RESULT.json")["sha256"],
                     "source_result": record(self.b1_output / "A_RESULT.json"),
                     "new_source_sha": context.producer_source_sha,
                     "new_native_optimize_calls": 0, "new_native_runtime_seconds": 0,
                     "historical_native_runtime_seconds": result["native_seconds"],
                     "historical_native_calls": result["native_calls"],
                     "historical_runtime_charged_to_B3": False,
                     "equivalence": equivalence, "equivalence_receipt": record(eq_path),
                     "origin_receipts": [record(self.b1_output / name) for name in
                         ("A_RESULT.json", "B1_P1_FREEZE.json", "A_PREPARE_RECEIPT.json", "A_NATIVE_SOURCE_FREEZE.json")]}
            graph_proof = context.output / "B1_GRAPH_COMPILER_EQUIVALENCE.json"
            if graph_proof.is_file():
                reuse["graph_compiler_proof"] = record(graph_proof)
            packet = {"source_stage": "A1", "authority_sha": context.request.authority.sha,
                      "decision_sha": decision.sha, "original_model_sha": model_sha,
                      "planning_arrays": planning, "selected_jobs": jsonable(replay["selected_jobs"]),
                      "unknown_arrival_policy": json.loads(decision.jobs_json)["unknown_arrival_policy"],
                      "gpu_runtime_state": json.loads(decision.gpu_runtime_json),
                      "aidc_schedule": json.loads(decision.variables_json),
                      "grid_anchor": {"grid_sha": context.request.authority.grid_sha,
                          "pcc_mapping_sha": context.request.authority.pcc_mapping_sha,
                          "control_names": list(coefficients[0].control_names), "controls": jsonable(replay["controls"])},
                      "source_output": str(self.b1_output), "closed_state": closed,
                      "point": result["incumbent"]["point"], "planning": result["planning"],
                      "accepted_source": result["freeze"],
                      "complete_domain_hashes": {uid: domain.sha for uid, domain in old["domains"].items()},
                      "original_complete_domain_sha": equivalence["complete_domain_sha"],
                      "global_bound": record(self.b1_output / "P1_FULL_DOMAIN_BOUND_CERTIFICATE.json"),
                      "pricing_result": read(self.b1_output / "P1_RESULT.json")["full_pricing"],
                      "b1_reuse": reuse, "build_profile": profile.receipt()}
            packet["proof_input_receipts"] = self._proof_receipts(context, source, self.b1_output, packet["pricing_result"])
            # A2 may reuse only the freshly verified B3 input/domain cache.
            fresh_root = context.output / "SOURCE"
            cache_path = fresh_root / "STATIC/DOMAIN" / context.request.authority.day / "PHYSICAL_DOMAIN_CACHE.json"
            if cache_path.is_file():
                cache = read(cache_path)
                packet["physical_input_cache"] = {"day": context.request.authority.day,
                    "authority_sha": context.request.authority.sha, "producer_source_sha": context.producer_source_sha,
                    "output": str(fresh_root), "DATA": cache["frozen_DATA"],
                    "protected_receipts": [record(cache_path), cache["cache"], cache["frozen_DATA"]],
                    "inputs": fresh["_campaign"]["input_receipts"],
                    "allowed_reuse": "COMPLETE_JOB_RESOURCE_BOUNDARY_PHYSICAL_DOMAIN_ONLY",
                    "grid_matrix_rhs_point_bound_clock_reused": False}
            current_result = dict(result, arm="B3", stage="A1", native_calls=0, native_seconds=0,
                                  verified_B1_A1_reuse=True)
            output = SourceStageOutput(context.request, jsonable(current_result), decision, None, model_sha,
                                       {}, {}, packet, ledger.sealed_receipt(), registry.evidence_kind)
            proof = self._verify_admitted(context, output)
            packet["physical_source_evidence"] = proof["physical"]
            receipt_path = context.output / "B1_A1_VERIFIED_REUSE.json"
            receipt_path.write_text(canonical(reuse) + "\n", encoding="utf-8")
            if progress:
                progress({"phase": "A1_B1_VERIFIED_REUSE_COMPLETE", "stage": "A1", "Native_calls": 0,
                          "UB": float(Fraction(result["exact_UB"])), "LB": float(Fraction(result["exact_LB"])),
                          "certified_gap": result["certified_gap"], "B3_A1_reused": True})
            return replace(output, physical_evidence=proof["physical"], global_evidence=proof["global"])

    def _verification_root(self, context, output):
        self._verify_origin(context, output)
        require(Path(output.source_packet["source_output"]).resolve() == self.b1_output,
                "B1_REUSE_ORIGINAL_SOURCE_ROOT_DRIFT")
        return self.b1_output

    def _verification_write_root(self, context, output):
        return context.output / "SOURCE"

    def _verification_case(self, context, registry):
        return registry.callable(A_SOURCE.replace(".", "/") + ".py", "verify_case")

    def _verify_numerical_artifacts(self, context, output):
        self._verify_origin(context, output)
        calls = read(self.b1_output / "A_NATIVE_CALLS.json")["calls"]
        require(len(calls) == output.source_packet["b1_reuse"]["historical_native_calls"],
                "B1_A1_HISTORICAL_NATIVE_CALL_AXIS_DRIFT")
        require(all(call["component"] in ("PHASE_I", "ORIGINAL_P1", "LOCAL_PRICING", "INTEGER_CONTROL")
                    for call in calls), "B1_A1_P2_HISTORICAL_NATIVE_FORBIDDEN")
        # Old numerical settings are retained verbatim. Independent exact rows,
        # integer/physical replay and exact bounds decide reuse acceptance.
        for call in calls:
            folder = Path(call["folder"]).resolve()
            require(folder.is_relative_to(self.b1_output), "B1_A1_NATIVE_ARTIFACT_PATH_ESCAPE")
            for name in ("MODEL_IDENTITY.json", "SOLVER_PARAMETERS.json"):
                require((folder / name).is_file(), "B1_A1_HISTORICAL_NATIVE_ARTIFACT_MISSING")
        return {"version": "B1_ORIGINAL_REUSED_WITH_EXACT_INDEPENDENT_REPLAY", "new_native_calls": 0,
                "historical_settings_sha": digest([record(Path(call["folder"]) / "SOLVER_PARAMETERS.json") for call in calls]),
                "historical_settings_relabelled_as_B3": False}

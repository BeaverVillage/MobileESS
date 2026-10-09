"""B2 per-worker source route reuse with the unchanged FULL/Compact/C3A builder.

The official campaign owner must admit this code in a new manifest/source
version at an unstarted worker boundary. Nothing activates or restarts workers.
"""
from dataclasses import asdict
import hashlib
import importlib
import json
import os
from pathlib import Path
import sys

from .build_runtime import BuildIdentity, ImmutableInputCache, BuildProfile
from .contracts import canonical, digest, require, require_sha
from .source_port import instrument_builder
from .scalar_math import original_pcs_math_scope

VERSION = "B2_BUILD_INPUT_REUSE_V7_20261009"


def _sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


class AdmittedSourceGateway:
    """Use the existing native campaign scope, with an explicit new version."""
    evidence_kind = "SOURCE"

    def __init__(self, request):
        self.request = request
        self.root = Path(__file__).resolve().parents[1]
        self.manifest = None

    def admit(self):
        # The authorizer must already be present in the official worker. This
        # check does not import a solver, execution package or source module.
        execution = sys.modules.get("v42_may_campaign_native90.execution")
        require(execution is not None, "B2_OFFICIAL_WORKER_SCOPE_REQUIRED")
        current = execution.current()
        persisted_request = {key: value for key, value in self.request.items() if key != "_budget"}
        require(isinstance(current, dict) and current.get("request") == persisted_request,
            "B2_OFFICIAL_WORKER_REQUEST_IDENTITY")
        manifest = current.get("manifest")
        require(isinstance(manifest, dict) and manifest.get("implementation", {}).get("version") == VERSION,
            "B2_NEW_SOURCE_VERSION_NOT_AUTHORIZED")
        request = self.request
        require(request.get("arm") == "B2" and request.get("run_id") == manifest.get("run_id")
            and type(request.get("Threads")) is int and request.get("Threads") == 1
            and type(request.get("P2_calls")) is int and request.get("P2_calls") == 0
            and request.get("native_budget_seconds") == 5400 and request.get("wall_budget_seconds") is None
            and request.get("target_gap") == .03, "B2_NATIVE90_POLICY_OR_IDENTITY_DRIFT")
        sources = manifest.get("implementation", {}).get("sources", {})
        for name in ("v42_b2_build_optimization/builder.py", "v42_b2_build_optimization/source_port.py",
                     "v42_b2_build_optimization/build_runtime.py", "v42_b2_build_optimization/contracts.py",
                     "v42_b2_build_optimization/scalar_math.py"):
            require(sources.get(name) == _sha(self.root / name), "B2_BUILD_VERSION_SOURCE_SHA_DRIFT:" + name)
        self.manifest = manifest
        execution.authorize(request["day"], "P1")

    def resolve(self, module):
        self.admit()
        relative = module.replace(".", "/") + ".py"
        expected = self.manifest["sources"].get(relative)
        require_sha(expected)
        require(_sha(self.root / relative) == expected, "B2_ORIGINAL_SOURCE_SHA_DRIFT:" + relative)
        result = importlib.import_module(module)
        require(Path(result.__file__).resolve() == (self.root / relative).resolve(),
            "B2_SOURCE_IMPORTED_FROM_OTHER_WORKTREE")
        return result

    def source_sha(self, relative):
        self.admit()
        expected = self.manifest["sources"].get(relative)
        require_sha(expected)
        require(_sha(self.root / relative) == expected, "B2_SOURCE_SHA_DRIFT")
        return expected


class FakeSourceGateway:
    """Explicit marked test modules; receipts can only be FAKE_SOURCE_TEST."""
    evidence_kind = "FAKE_SOURCE_TEST"

    def __init__(self, modules, sources):
        self.modules, self.sources = dict(modules), dict(sources)
        require(all(getattr(module, "__b3_fake__", False) is True
            for module in self.modules.values()), "B2_MARKED_FAKE_MODULES_REQUIRED")

    def admit(self):
        return None

    def resolve(self, module):
        require(module in self.modules and getattr(self.modules[module], "__b3_fake__", False) is True,
            "B2_REAL_MODULE_IN_FAKE_GATEWAY_FORBIDDEN")
        return self.modules[module]

    def source_sha(self, relative):
        path = self.sources[relative]
        return _sha(path)


class VersionedB2BuildPort:
    def __init__(self, request, gateway=None):
        self.request = dict(request)
        self.gateway = gateway or AdmittedSourceGateway(self.request)
        require(type(self.gateway) in (AdmittedSourceGateway, FakeSourceGateway),
            "B2_TYPED_SOURCE_GATEWAY_REQUIRED")
        self.gateway.admit()
        require(self.request.get("arm") == "B2", "B2_FIXED_AIDC_ARM_REQUIRED")
        require(type(self.request.get("Threads")) is int and self.request.get("Threads") == 1
            and type(self.request.get("P2_calls")) is int and self.request.get("P2_calls") == 0
            and self.request.get("native_budget_seconds") == 5400
            and self.request.get("wall_budget_seconds") is None, "B2_BUILD_NATIVE_POLICY_DRIFT")
        self.cache = None
        self.identity = None
        self.profile = None
        self.proofs = []

    def _identity(self, payload):
        bundle, fixed = payload["bundle"], payload["identity"]
        require(bundle["day"] == fixed["day"] == self.request["day"], "B2_BUILD_DATE_DRIFT")
        require(fixed.get("arm") == "B2" and fixed.get("AIDC_optimization_calls") == 0
            and fixed.get("B0_B1_schedule_result_reads") == 0,
            "B2_INDEPENDENT_FIXED_AIDC_REQUIRED")
        source = self.gateway.source_sha("v42_may_campaign_native90/m_model.py")
        return BuildIdentity(worker=str(os.getpid()) + ":" + self.request["run_id"],
            day=self.request["day"], input_sha=digest(bundle), source_sha=source,
            domain_sha=bundle["route_table"]["sha256"], grid_sha=bundle["electrical_certificate"]["sha256"],
            fixed_input_sha=digest(fixed))

    def _native_inputs(self, bundle):
        # The original constructor's output contains only sites, initial state,
        # RouteArc/Battery values and provenance. Mutable mappings are sealed as
        # JSON and detached on each hit; no model or matrix enters this cache.
        original = self.gateway.resolve("v42_bootstrap.m1").native_inputs
        input_sha = digest(bundle)
        source_sha = self.gateway.source_sha("v42_bootstrap/m1.py")
        def verify():
            self.gateway.admit()
            require(_sha(bundle["route_table"]["path"]) == bundle["route_table"]["sha256"],
                "B2_ORIGINAL_ROUTE_FILE_SHA_DRIFT")
            return dict(PASS=True, input_sha=input_sha, producer_source_sha=source_sha,
                route_sha=bundle["route_table"]["sha256"], forecast_sha=bundle["traffic_forecast_sha"])
        def produce():
            sites, initial, routes, battery, receipt = original(bundle)
            return tuple(sites), canonical(initial), tuple(routes), battery, canonical(receipt)
        with self.profile.phase("domain_or_route"):
            packed = self.cache.get(self.identity, "ORIGINAL_NATIVE_ROUTE_INPUTS", input_sha, produce, verify)
        return packed[0], json.loads(packed[1]), packed[2], packed[3], json.loads(packed[4])

    def build(self, payload, request=None, progress=None):
        self.gateway.admit()
        request = self.request if request is None else request
        require(request == self.request, "B2_BUILD_REQUEST_DRIFT")
        identity = self._identity(payload)
        if self.cache is None:
            self.identity, self.cache = identity, ImmutableInputCache(identity)
        require(identity == self.identity, "B2_WORKER_DATE_INPUT_CACHE_DRIFT")
        profile_scope = digest(asdict(identity))
        evidence_kind = "FAKE_SOURCE_TEST" if type(self.gateway) is FakeSourceGateway else "SOURCE"
        mode = "FIXTURE_OPTIMIZED" if evidence_kind == "FAKE_SOURCE_TEST" else "OPTIMIZED"
        self.profile = BuildProfile(profile_scope, mode)
        original = self.gateway.resolve("v42_may_campaign_native90.m_model")
        native_mess = self.gateway.resolve("v42_native.mess")
        pcs_source_sha = self.gateway.source_sha("v42_native/mess.py")
        original_path = Path(original.__file__)
        with self.profile.phase("total_preparation"):
            port, proof = instrument_builder(original_path, vars(original), self._native_inputs,
                self.profile, identity.source_sha)
            with original_pcs_math_scope(native_mess, native_mess.__file__, pcs_source_sha) as (memo, pcs_proof):
                case = port(payload, request, progress)
            # Recheck this fresh constructor's complete source transport state.
            # Neither historical PASS certificates nor matrices enter the cache.
            with self.profile.phase("equivalence"):
                verified = original.verify_case(case)
            require(verified.get("PASS") is True, "B2_ORIGINAL_TRANSPORT_REPLAY_FAILED")
        self.proofs.append(proof)
        # FULL, Compact/C3A and independent replay are verified by the original
        # code again. Its certificates/bounds are never cached or synthesized.
        self.last_receipt = dict(version=VERSION, identity=asdict(identity),
            profile=self.profile.receipt(), input_cache=self.cache.receipt(), source_ast_proof=proof,
            original_FULL_Compact_C3A_verifier=verified, evidence_kind=evidence_kind,
            original_PCS_scalar_math=dict(source_proof=pcs_proof, calls=memo.receipt()),
            Native_budget_seconds=5400, Threads=1, P2_calls=0, production_worker_started=False,
            real_performance_comparison="NOT_RUN", source_version_transition_by_this_module=False)
        return case


def build_case(payload, request, progress=None):
    """Official future-worker entrypoint; existing workers never hot-switch."""
    # Ownership stays with this call. An official worker may explicitly keep a
    # VersionedB2BuildPort instance for repeated same-identity input reuse.
    # No module-level mutable cache survives a model build.
    port = VersionedB2BuildPort(request)
    return port.build(payload, request, progress)

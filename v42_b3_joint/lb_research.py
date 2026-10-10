"""Optional B3 binding to the common, development-only dual search.

The original stage model, full fixed decision, source registry and Native
ledger retain authority. This module imports no Solver and grants no permit.
"""
from hashlib import sha256
from pathlib import Path
from weakref import WeakKeyDictionary
from collections import OrderedDict
from contextlib import contextmanager, ExitStack
from contextvars import ContextVar
from types import SimpleNamespace
from unittest.mock import patch

from .contracts import digest, require, require_sha

COMMON_MODULE = "v42_m1_anytime.dual_stabilization"
MODEL_MODULE = "v42_may_campaign_native90.m_model"
_RELATIVE = "v42_b3_joint/lb_research.py"
_ISSUED = WeakKeyDictionary()
_ACTIVE = ContextVar("b3_development_envelope", default=None)
BOX_MODULE = "v42_b2_seed_recovery_v18.certificate_box"
CHECK_MODULE = "v42_m1_research.check_lb"
BLOCK_MODULE = "v42_m1_hybrid.blocks"
_IDENTITY_FIELDS = ("stage", "day", "source_sha", "input_sha", "fixed_input_sha",
                    "case_sha", "matrix_sha", "domain_sha")


class _SourceFunctions:
    """Pin original source bytes, checkout, function objects and code objects."""
    def __init__(self, registry, module, symbols):
        self.registry, self.name = registry, module
        self.module = registry.resolve(module)
        self.relative = module.replace(".", "/") + ".py"
        self.path = Path(registry.root).resolve() / self.relative
        self.sha = registry.source_manifest.get(self.relative)
        require_sha(self.sha)
        self.functions = {name: getattr(self.module, name) for name in symbols}
        self.codes = {name: fn.__code__ for name, fn in self.functions.items()}
        self.verify()

    def verify(self, aliases=None):
        require(self.registry.resolve(self.name) is self.module
                and Path(self.module.__file__).resolve() == self.path
                and self.registry.source_manifest.get(self.relative) == self.sha
                and sha256(self.path.read_bytes()).hexdigest() == self.sha,
                "B3_ENVELOPE_ORIGINAL_SOURCE_DRIFT:" + self.relative)
        aliases = aliases or {}
        require(all(getattr(self.module, name) is aliases.get(name, fn) and fn.__code__ is self.codes[name]
                    for name, fn in self.functions.items()), "B3_ENVELOPE_ORIGINAL_DELEGATE_DRIFT")
        return self.functions


def _own_source(registry):
    path = Path(__file__).resolve()
    require(path == Path(registry.root).resolve() / _RELATIVE,
            "B3_LB_RESEARCH_ADAPTER_CHECKOUT_DRIFT")
    expected = registry.source_manifest.get(_RELATIVE)
    require_sha(expected)
    require(sha256(path.read_bytes()).hexdigest() == expected,
            "B3_LB_RESEARCH_ADAPTER_SOURCE_DRIFT")
    return expected


class _StageFactory:
    def __init__(self, context, registry):
        require(context.request.stage in ("M1", "M2"), "B3_LB_RESEARCH_M_STAGE_REQUIRED")
        require(context.source_registry is registry, "B3_LB_RESEARCH_REGISTRY_DRIFT")
        context.verify_identity()
        self.context, self.registry = context, registry
        self.identity = dict(context.identity)
        self.adapter_sha = _own_source(registry)
        self.envelopes = OrderedDict()
        self.original_box = None
        _ISSUED[self] = (context, registry, tuple(sorted(self.identity.items())), self.adapter_sha)

    def _case_identity(self, case):
        checked_factory(self, self.context, self.registry)
        context, registry = self.context, self.registry
        registry.admit(context, "LB_RESEARCH_CURRENT_CASE")
        model = registry.resolve(MODEL_MODULE)
        proof = model.verify_case(case)
        require(proof.get("PASS") is True, "B3_LB_RESEARCH_ORIGINAL_CASE_NOT_VERIFIED")
        # Resolve the source materializer too; a B2 payload is never admitted.
        bridge = registry.resolve("v42_b3_joint.m_source")
        payload = bridge.fixed_aidc_payload(context)
        require(case.identity.get("arm") == "B3"
                and case.identity.get("day", context.request.authority.day) == context.request.authority.day
                and case.identity.get("input_identity") == payload["identity"]
                and case.planning == payload["planning"],
                "B3_LB_RESEARCH_FIXED_FULL_AIDC_PAYLOAD_DRIFT")
        for key in ("selected_matrix_sha", "selected_domain_sha"):
            require_sha(case.identity.get(key))
        require_sha(case.case_sha)
        common = registry.resolve(COMMON_MODULE)
        identity = common.StageIdentity(
            stage="B3_" + context.request.stage,
            day=context.request.authority.day,
            source_sha=context.request.authority.source_sha,
            input_sha=context.request.authority.input_sha,
            fixed_input_sha=context.request.fixed_input_sha,
            case_sha=case.case_sha,
            matrix_sha=case.identity["selected_matrix_sha"],
            domain_sha=case.identity["selected_domain_sha"],
        )
        # A new pool is issued for this fixed stage/case. No prior stage search,
        # Native objective, point, bound or clock is imported by this adapter.
        return common, identity

    def envelope(self, case):
        common, identity = self._case_identity(case)
        key = identity.sha
        if key not in self.envelopes:
            if len(self.envelopes) >= 2:
                self.envelopes.popitem(last=False)
            self.envelopes[key] = _CaseEnvelope(self, case, common, identity)
        result = self.envelopes[key]
        require(result.case is case, "B3_ENVELOPE_FOREIGN_CASE_OBJECT")
        result.validate()
        return result

    def __call__(self, case, request):
        require(all(request.get(key) == value for key, value in self.identity.items()),
                "B3_LB_RESEARCH_INCOMING_STAGE_REQUEST_DRIFT")
        bound = self.envelope(case)
        common = self.registry.resolve(COMMON_MODULE)
        return common.DualSearch(bound.identity, finite_box=bound.provider)


class _CaseEnvelope:
    def __init__(self, factory, case, common, identity):
        self.factory, self.case, self.identity = factory, case, identity
        self.box = factory.original_box
        self.provider = common.ProvedEnvelope(identity, derive=self.derive,
                                              verify=self.verify, validate=self.validate)

    def validate(self):
        common, identity = self.factory._case_identity(self.case)
        require(identity == self.identity, "B3_ENVELOPE_STAGE_OR_FIXED_CASE_DRIFT")
        if self.box is not None:
            self.box.verify()

    def _box(self):
        if self.box is None:
            self.box = self.factory.original_box or _SourceFunctions(
                self.factory.registry, BOX_MODULE, ("derive", "verify"))
        return self.box.verify()

    def derive(self, A, d):
        return self._box()["derive"](A, d)

    def verify(self, A, d, lo, hi, proof):
        return self._box()["verify"](A, d, lo, hi, proof)

    def marker(self):
        return dict(schema="V42_B3_STAGE_LOCAL_PROVED_ENVELOPE_V1",
                    context_identity_sha=digest(self.factory.identity),
                    identity={key: getattr(self.identity, key) for key in _IDENTITY_FIELDS},
                    adapter_sha=self.factory.adapter_sha,
                    source_shas={module.replace(".", "/") + ".py":
                                 self.factory.registry.source_manifest.get(module.replace(".", "/") + ".py")
                                 for module in (COMMON_MODULE, BOX_MODULE, CHECK_MODULE, MODEL_MODULE, BLOCK_MODULE)})


class _CheckerScope:
    def __init__(self, factory):
        self.factory = factory
        registry = factory.registry
        factory.original_box = _SourceFunctions(registry, BOX_MODULE, ("derive", "verify"))
        self.checker = _SourceFunctions(registry, CHECK_MODULE,
                                       ("check_rational_dual_certificate", "_rational_bound"))
        self.original = self.checker.functions["check_rational_dual_certificate"]
        self.original_code = self.original.__code__
        self.locals = _SourceFunctions(registry, "v42_m1_hybrid.bound", ("local_exact_price_bound",))
        self.blocks = _SourceFunctions(registry, BLOCK_MODULE,
                                       ("matrix_sha", "build_blocks", "verify_decomposition"))
        self.check_alias, self.local_alias = self.check, self.local
        self.routed_modules, self.pricing = (), None

    def integrity(self):
        self.checker.verify({"check_rational_dual_certificate": self.check_alias})
        require(all(module.check_rational_dual_certificate is self.check_alias
                    for module in self.routed_modules)
                and self.pricing.local_exact_price_bound is self.local_alias,
                "B3_ENVELOPE_SCOPED_CHECKER_ALIAS_DRIFT")

    def _bound(self, A, d, case_sha):
        checked_factory(self.factory, self.factory.context, self.factory.registry)
        matches = [value for value in self.factory.envelopes.values()
                   if value.identity.case_sha == case_sha]
        require(len(matches) == 1, "B3_ENVELOPE_CURRENT_ISSUED_CASE_REQUIRED")
        result = matches[0]
        result.validate()
        # ProvedEnvelope independently stamps the supplied original A/d too.
        return result

    def check(self, A, d, dual, *, lower=None, upper=None, source_rows=None, case_sha=None):
        import numpy as np
        self.integrity()
        require(self.original.__code__ is self.original_code,
                "B3_ENVELOPE_ORIGINAL_CHECKER_CODE_DRIFT")
        value = self._bound(A, d, case_sha)
        # The common search can delegate its own proved certificate view back
        # through this scoped alias. Accept only this exact same-stage view.
        if lower is not None or upper is not None:
            lo, hi, _ = value.provider(A, d)
            for supplied, key, expected in ((lower, "lower", lo), (upper, "upper", hi)):
                require(supplied is None or any(np.asarray(supplied).dtype == np.asarray(view).dtype
                        and np.asarray(supplied).shape == np.asarray(view).shape
                        and np.asarray(supplied).tobytes() == np.asarray(view).tobytes()
                        for view in (d[key], expected)),
                        "B3_ENVELOPE_FOREIGN_CHECKER_BOX")
        return value.provider.check(A, d, dual, checker=self.original, case_sha=case_sha,
                                    source_rows=source_rows)

    def local(self, block, exact_objective, dual):
        import numpy as np
        self.integrity()
        original = self.locals.verify()["local_exact_price_bound"]
        if np.isfinite(block.d["lower"]).all() and np.isfinite(block.d["upper"]).all():
            return original(block, exact_objective, dual)
        require(block.unit == "NONUNIT", "B3_ENVELOPE_UNIT_STANDALONE_BOX_MUST_REMAIN_ORIGINAL")
        found = []
        functions = self.blocks.verify()
        for bound in self.factory.envelopes.values():
            case = bound.case
            decomp = functions["build_blocks"](case)
            functions["verify_decomposition"](case, decomp)
            candidate = decomp.nonunit_block
            if (np.array_equal(candidate.original_columns, block.original_columns)
                    and np.array_equal(candidate.original_rows, block.original_rows)
                    and functions["matrix_sha"](candidate.A) == functions["matrix_sha"](block.A)
                    and all(np.asarray(candidate.d[k]).dtype == np.asarray(block.d[k]).dtype
                            and np.asarray(candidate.d[k]).tobytes() == np.asarray(block.d[k]).tobytes()
                            for k in candidate.d)):
                found.append((bound, decomp))
        require(len(found) == 1, "B3_ENVELOPE_UNBOUND_NONUNIT_BLOCK")
        bound, decomp = found[0]
        lo, hi, proof = bound.provider(bound.case.A, bound.case.d)
        for unit in decomp.units.values():
            axis = unit.original_columns
            require(np.array_equal(lo[axis], unit.d["lower"])
                    and np.array_equal(hi[axis], unit.d["upper"]),
                    "B3_ENVELOPE_UNIT_ORIGINAL_STANDALONE_BOX_CHANGED")
        axis = block.original_columns
        proxy = SimpleNamespace(A=block.A, d=dict(block.d, lower=lo[axis], upper=hi[axis]))
        result = original(proxy, exact_objective, dual)
        return dict(result, certificate_scope="GLOBAL_ORIGINAL_FEASIBLE_NONUNIT_PROJECTION_ONLY",
                    stage_identity_sha=bound.identity.sha,
                    standalone_nonunit_domain_lower_bound_claimed=False,
                    standalone_nonunit_pricing_closure_claimed=False,
                    original_model_and_block_bounds_mutated=False,
                    authoritative_Global_LB_requires_full_original_signed_dual_check=True)


@contextmanager
def checker_scope(factory, context, registry):
    """Route exact original checker inputs only during this opt-in B3 stage."""
    checked_factory(factory, context, registry)
    require(_ACTIVE.get() is None, "B3_ENVELOPE_NESTED_STAGE_SCOPE_FORBIDDEN")
    scope = _CheckerScope(factory)
    modules = [registry.resolve(name) for name in
               (CHECK_MODULE, "v42_may_campaign_native90.m_stage", "v42_m1_hybrid.bound",
                "v42_m1_hybrid.verify", "v42_m1_research.lb")]
    pricing = registry.resolve("v42_m1_hybrid.pricing")
    scope.routed_modules, scope.pricing = modules, pricing
    token = _ACTIVE.set(scope)
    try:
        with ExitStack() as stack:
            for module in modules:
                require(module.check_rational_dual_certificate is scope.original,
                        "B3_ENVELOPE_FOREIGN_CHECKER_ALIAS")
                stack.enter_context(patch.object(module, "check_rational_dual_certificate", scope.check_alias))
            require(pricing.local_exact_price_bound is scope.locals.functions["local_exact_price_bound"],
                    "B3_ENVELOPE_FOREIGN_LOCAL_BOUND_ALIAS")
            stack.enter_context(patch.object(pricing, "local_exact_price_bound", scope.local_alias))
            yield scope
    finally:
        _ACTIVE.reset(token)


def envelope_marker(factory, case):
    return factory.envelope(case).marker()


def verify_certificate(context, case, dual, marker):
    """Recreate the proof after restore; never admit a saved envelope/cache."""
    registry = context.source_registry
    active = _ACTIVE.get()
    if active is not None:
        active.integrity()
    factory = active.factory if active is not None else factory_for_context(context, registry)
    checked_factory(factory, context, registry)
    bound = factory.envelope(case)
    require(marker == bound.marker(), "B3_ENVELOPE_SAVED_STAGE_IDENTITY_DRIFT")
    original = active.original if active is not None else registry.callable(
        "v42_m1_research/check_lb.py", "check_rational_dual_certificate")
    return bound.provider.check(case.A, case.d, dual, checker=original, case_sha=case.case_sha)


def checked_factory(factory, context, registry):
    require(type(factory) is _StageFactory and factory in _ISSUED,
            "B3_LB_RESEARCH_OWN_FACTORY_REQUIRED")
    issued_context, issued_registry, issued_identity, issued_sha = _ISSUED[factory]
    require(getattr(factory.__call__, "__self__", None) is factory
            and getattr(factory.__call__, "__func__", None) is _FACTORY_CALL
            and _FACTORY_CALL.__code__ is _FACTORY_CALL_CODE,
            "B3_LB_RESEARCH_FACTORY_DELEGATE_DRIFT")
    context.verify_identity()
    require(factory.context is context is issued_context and factory.registry is registry is issued_registry
            and context.source_registry is registry and factory.identity == context.identity
            and tuple(sorted(factory.identity.items())) == issued_identity
            and factory.adapter_sha == issued_sha
            and factory.adapter_sha == _own_source(registry),
            "B3_LB_RESEARCH_FACTORY_STAGE_OR_FIXED_INPUT_DRIFT")
    return factory


def factory_for_context(context, registry):
    """Create a lazy source-bound callable; no model, import or output here."""
    return _StageFactory(context, registry)


_FACTORY_CALL = _StageFactory.__call__
_FACTORY_CALL_CODE = _FACTORY_CALL.__code__

"""Optional B3 binding to the common, development-only dual search.

The original stage model, full fixed decision, source registry and Native
ledger retain authority. This module imports no Solver and grants no permit.
"""
from hashlib import sha256
from pathlib import Path
from weakref import WeakKeyDictionary

from .contracts import require, require_sha

COMMON_MODULE = "v42_m1_anytime.dual_stabilization"
MODEL_MODULE = "v42_may_campaign_native90.m_model"
_RELATIVE = "v42_b3_joint/lb_research.py"
_ISSUED = WeakKeyDictionary()


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
        _ISSUED[self] = (context, registry, tuple(sorted(self.identity.items())), self.adapter_sha)

    def __call__(self, case, request):
        checked_factory(self, self.context, self.registry)
        context, registry = self.context, self.registry
        require(all(request.get(key) == value for key, value in self.identity.items()),
                "B3_LB_RESEARCH_INCOMING_STAGE_REQUEST_DRIFT")
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
        return common.DualSearch(identity)


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

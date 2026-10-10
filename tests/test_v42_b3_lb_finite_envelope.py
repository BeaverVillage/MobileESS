"""Six tiny original-math/FakeSourceRegistry contracts; real B3 remains NOT_RUN.

Only pure source functions and a five-column CSR are used. No solver/model,
physical B3 case, saved B2 point, or persisted proof is admitted.
"""
import ast
import hashlib
from contextlib import nullcontext
from copy import deepcopy
from fractions import Fraction as F
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from scipy import sparse

from v42_b3_joint import lb_research as adapter, m_source
from v42_b3_joint.contracts import digest
from v42_b3_joint.source_runtime import SourceRegistry
from v42_m1_anytime import dual_stabilization as common
from v42_m1_hybrid import blocks, bound
from v42_m1_research import check_lb
from v42_b2_seed_recovery_v18 import certificate_box as box
from test_v42_b3_lb_research import _FIXTURE

ROOT = Path(__file__).resolve().parents[1]
RAW_CHECKER = check_lb.check_rational_dual_certificate


def numeric_fixture(stage="M1", marker=1, finite=False):
    value = _FIXTURE.SourceFixture(stage, marker)
    registry = value.registry

    def module(name, **attributes):
        path = ROOT / (name.replace(".", "/") + ".py")
        result = SimpleNamespace(__b3_fake__=True, __file__=str(path), **attributes)
        registry.modules[name] = result
        registry.source_manifest[path.relative_to(ROOT).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
        return result

    module(adapter.COMMON_MODULE, StageIdentity=common.StageIdentity,
           DualSearch=common.DualSearch, ProvedEnvelope=common.ProvedEnvelope)
    module(adapter.BOX_MODULE, derive=box.derive, verify=box.verify)
    module(adapter.CHECK_MODULE, check_rational_dual_certificate=RAW_CHECKER,
           _rational_bound=check_lb._rational_bound)
    module(adapter.BLOCK_MODULE, matrix_sha=blocks.matrix_sha,
           build_blocks=blocks.build_blocks, verify_decomposition=blocks.verify_decomposition)
    module("v42_m1_hybrid.bound", local_exact_price_bound=bound.local_exact_price_bound,
           check_rational_dual_certificate=RAW_CHECKER)
    module("v42_m1_hybrid.verify", check_rational_dual_certificate=RAW_CHECKER)
    module("v42_m1_hybrid.pricing", local_exact_price_bound=bound.local_exact_price_bound)
    module("v42_m1_research.lb", check_rational_dual_certificate=RAW_CHECKER)
    module("v42_b3_joint.m_source", fixed_aidc_payload=m_source.fixed_aidc_payload)
    module("v42_b3_joint.lb_research", checked_factory=adapter.checked_factory)
    namespace = {"hashlib": hashlib, "np": np}
    path = ROOT / "v42_may_campaign_native90/m_model.py"
    definition = next(node for node in ast.parse(path.read_text(encoding="utf-8-sig")).body
                      if isinstance(node, ast.FunctionDef) and node.name == "_domain_sha")
    exec(compile(ast.Module([definition], type_ignores=[]), str(path), "exec"), namespace)
    module(adapter.MODEL_MODULE, verify_case=lambda case: dict(PASS=True, FAKE_SOURCE_TEST=True),
           _domain_sha=namespace["_domain_sha"])
    module("v42_may_campaign_native90.m_stage", np=np,
           check_rational_dual_certificate=RAW_CHECKER)
    units = value.authority.mess_ids
    A = sparse.csr_matrix([[-1./3]*4 + [1.]])
    d = dict(names=np.asarray([f"SOC[{u},0]" for u in units] + ["helper"]),
             lower=np.asarray([0.]*4 + ([.1] if finite else [-np.inf])),
             upper=np.asarray([1.]*4 + ([2.] if finite else [np.inf])),
             types=np.asarray(["C"]*5), objective=np.asarray([0.]*4 + [1.]),
             constant=np.asarray(0.), rhs=np.asarray([.1]), sense=np.asarray(["="]),
             row_names=np.asarray(["helper_binding"]))
    payload = m_source.fixed_aidc_payload(value.context)
    identity = dict(arm="B3", day=value.authority.day, input_identity=payload["identity"],
                    selected_matrix_sha=blocks.matrix_sha(A),
                    selected_domain_sha=namespace["_domain_sha"](d))
    case = SimpleNamespace(A=A, d=d, identity=identity, case_sha=digest(identity),
                           planning=payload["planning"], bundle={"day": value.authority.day},
                           output=Path("FAKE_ONLY"))
    value.case = case
    value.factory = adapter.factory_for_context(value.context, registry)
    value.search = value.factory(case, value.context.identity)
    value.envelope = value.factory.envelope(case)
    return value


def scientific(certificate):
    return {key: value for key, value in certificate.items() if key != "check_wall_seconds"}


def test_unbounded_initial_original_checker_actual_ast_rebind_is_routed_and_restored():
    value = numeric_fixture()
    case, registry = value.case, value.registry
    with pytest.raises(ValueError, match="REQUIRES_FINITE"):
        RAW_CHECKER(case.A, case.d, {}, case_sha=case.case_sha)
    calls, writes = [], {}
    # This is a pure fixture object, never a real Native model/delegate.
    model = SimpleNamespace(Params=SimpleNamespace(Method=1),
                            getAttr=lambda name: (_ for _ in ()).throw(ValueError("FAKE_NO_PI")),
                            dispose=lambda: None)
    ledger = SimpleNamespace(cost=lambda *args: nullcontext(), remaining=lambda **kwargs: 5400.,
                             final_reserve=0., native_optimize=lambda *args, **kwargs: calls.append(kwargs))
    with registry.execution_scope(value.context), adapter.checker_scope(value.factory, value.context, registry):
        fresh = SourceRegistry.rebind(registry, "v42_may_campaign_native90.m_stage", "_fresh_lp_dual",
            globals={"_model": lambda *args, **kwargs: (model, {"FAKE_SOURCE_TEST": True}),
                     "atomic": lambda path, packet: writes.setdefault(path.name, packet)},
            import_replacements={"repair_affine_equality_duals": lambda *args: ({}, None)})
        dual, cert = fresh(case, ledger, None)
        assert dual == {} and cert["PASS"] and F(cert["exact_bound"]) == F(.1)
        assert calls[0]["requested_seconds"] == 300. and len(calls) == 1
        assert writes["INITIAL_EXACT_LB_CERTIFICATE.json"]["original_checker_byte_preserved"]
    assert registry.modules[adapter.CHECK_MODULE].check_rational_dual_certificate is RAW_CHECKER
    assert registry.modules["v42_may_campaign_native90.m_stage"].check_rational_dual_certificate is RAW_CHECKER
    assert next(row for row in reversed(registry.audit) if row["action"] == "REBIND")["numeric_scientific_constants_changed"] is False


def test_finite_original_box_preserves_original_checker_result_without_derive_or_verify():
    value = numeric_fixture(finite=True)
    original = RAW_CHECKER(value.case.A, value.case.d, {"0": "1/2"}, case_sha=value.case.case_sha)
    with adapter.checker_scope(value.factory, value.context, value.registry) as scope:
        cert = scope.check(value.case.A, value.case.d, {"0": "1/2"}, case_sha=value.case.case_sha)
    for key, item in scientific(original).items():
        assert cert[key] == item
    assert value.envelope.provider.derive_calls == value.envelope.provider.verify_calls == 0
    assert np.isfinite(value.case.d["lower"]).all()


def test_cache_is_current_instance_only_copy_safe_and_rejects_wrong_rounding_or_tamper():
    value = numeric_fixture()
    provider, case = value.envelope.provider, value.case
    lo, hi, proof = provider(case.A, case.d)
    saved_lo = lo.copy()
    lo[4] = 100.; proof["steps"][0]["lower"] = 100.
    again = provider(case.A, case.d)
    assert np.array_equal(again[0], saved_lo)
    assert provider.derive_calls == provider.verify_calls == 1 and provider.cache_hits == 1
    bad = deepcopy(again[2]); bad["steps"][0]["lower"] = np.nextafter(saved_lo[4], np.inf)
    with pytest.raises(ValueError, match="INWARD_ROUNDING"):
        box.verify(case.A, case.d, again[0], again[1], bad)
    assert np.isneginf(case.d["lower"][4]) and np.isposinf(case.d["upper"][4])
    provider._cache[2]["stage_identity_sha"] = "0"*64
    with pytest.raises(ValueError, match="CACHE_OR_STAGE"):
        provider(case.A, case.d)


def test_original_source_sha_and_helper_alias_drift_deny_without_mutating_originals():
    value = numeric_fixture()
    registry = value.registry
    with adapter.checker_scope(value.factory, value.context, registry) as scope:
        registry.modules[adapter.BOX_MODULE].verify = lambda *args: dict(PASS=True)
        with pytest.raises(ValueError, match="ORIGINAL_DELEGATE_DRIFT"):
            scope.check(value.case.A, value.case.d, {}, case_sha=value.case.case_sha)
    registry.modules[adapter.BOX_MODULE].verify = box.verify
    registry.source_manifest["v42_b2_seed_recovery_v18/certificate_box.py"] = "0"*64
    with pytest.raises(ValueError, match="ORIGINAL_SOURCE_DRIFT"):
        with adapter.checker_scope(value.factory, value.context, registry):
            pytest.fail("Source drift admitted")
    assert registry.modules[adapter.CHECK_MODULE].check_rational_dual_certificate is RAW_CHECKER


def test_m1_m2_fixed_input_isolation_and_final_restore_rederive_without_saved_cache():
    first, second = numeric_fixture("M1", 1), numeric_fixture("M2", 2)
    marker = adapter.envelope_marker(first.factory, first.case)
    with adapter.checker_scope(first.factory, first.context, first.registry):
        initial = adapter.verify_certificate(first.context, first.case, {}, marker)
    assert first.envelope.provider.derive_calls == first.envelope.provider.verify_calls == 1
    first.envelope.provider._cache[2]["PASS"] = False  # Old live proof cannot be admitted on restore.
    restored = adapter.verify_certificate(first.context, first.case, {}, marker)
    assert scientific(initial) == scientific(restored)
    assert first.search.identity.sha != second.search.identity.sha
    with pytest.raises(ValueError, match="SAVED_STAGE_IDENTITY_DRIFT"):
        adapter.verify_certificate(second.context, second.case, {}, marker)
    changed = deepcopy(marker); changed["identity"]["fixed_input_sha"] = "0"*64
    with pytest.raises(ValueError, match="SAVED_STAGE_IDENTITY_DRIFT"):
        adapter.verify_certificate(first.context, first.case, {}, changed)


def test_nonunit_original_projection_sum_equals_full_checker_unit_boxes_unchanged():
    value = numeric_fixture()
    case, registry = value.case, value.registry
    decomp = blocks.build_blocks(case)
    original = {key: item.copy() for key, item in case.d.items()}
    with adapter.checker_scope(value.factory, value.context, registry) as scope:
        local = registry.modules["v42_m1_hybrid.pricing"].local_exact_price_bound
        pieces = [local(unit, {}, {}) for unit in decomp.units.values()]
        nonunit = local(decomp.nonunit_block, {0: F(1)}, {})
        full = scope.check(case.A, case.d, {}, case_sha=case.case_sha)
        assert sum((F(p["exact_bound"]) for p in pieces), F(0)) + F(nonunit["exact_bound"]) == F(full["exact_bound"])
        assert nonunit["standalone_nonunit_domain_lower_bound_claimed"] is False
        assert nonunit["authoritative_Global_LB_requires_full_original_signed_dual_check"] is True
        bad = deepcopy(decomp.nonunit_block); bad.original_columns[0] = 0
        with pytest.raises(ValueError, match="UNBOUND_NONUNIT_BLOCK"):
            local(bad, {0: F(1)}, {})
        lo, hi, _ = value.envelope.provider(case.A, case.d)
        lo[4] = np.nextafter(lo[4], np.inf)
        with pytest.raises(ValueError, match="FOREIGN_CHECKER_BOX"):
            scope.check(case.A, case.d, {}, lower=lo, upper=hi, case_sha=case.case_sha)
    assert all(original[key].tobytes() == case.d[key].tobytes() for key in original)
    assert registry.modules["v42_m1_hybrid.pricing"].local_exact_price_bound is bound.local_exact_price_bound

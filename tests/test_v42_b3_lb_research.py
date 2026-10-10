"""Five tiny source-routing contracts; no Solver, model or real B3 replay."""
import hashlib
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from v42_b3_joint.contracts import digest
from v42_b3_joint import lb_research, m_source

_SPEC = importlib.util.spec_from_file_location(
    "b3_lb_research_original_source_fixture", Path(__file__).with_name("test_v42_b3_m_source.py"))
_FIXTURE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _FIXTURE
_SPEC.loader.exec_module(_FIXTURE)


def fixture(stage="M1", marker=1):
    value = _FIXTURE.SourceFixture(stage, marker)
    value.searches, value.routed_keywords = [], []
    registry = value.registry
    own = Path(lb_research.__file__).resolve()
    registry.source_manifest["v42_b3_joint/lb_research.py"] = hashlib.sha256(own.read_bytes()).hexdigest()
    registry.modules["v42_b3_joint.lb_research"] = _FIXTURE.fake_module(
        checked_factory=lb_research.checked_factory)
    registry.modules["v42_b3_joint.m_source"] = _FIXTURE.fake_module(
        fixed_aidc_payload=m_source.fixed_aidc_payload)

    def identity(**fields):
        return SimpleNamespace(**fields)

    def search(stage_identity):
        result = SimpleNamespace(identity=stage_identity, candidates=[])
        value.searches.append(result)
        return result

    registry.modules[lb_research.COMMON_MODULE] = _FIXTURE.fake_module(
        StageIdentity=identity, DualSearch=search)
    model = registry.modules[lb_research.MODEL_MODULE]
    original_model_factory = model.__b3_rebind__

    def build_factory(symbol, target, routing):
        original = original_model_factory(symbol, target, routing)
        if symbol != "build_case":
            return original
        def build(*args):
            case = original(*args)
            case.identity.update(day=value.authority.day,
                                 selected_matrix_sha=digest(("FAKE_C3A", stage, marker)),
                                 selected_domain_sha=digest(("FAKE_SELECTED_DOMAIN", stage, marker)))
            case.case_sha = digest(case.identity)
            return case
        return build

    model.__b3_rebind__ = build_factory
    stage_module = registry.modules[m_source.STAGE_MODULE]
    original_stage_factory = stage_module.__b3_rebind__

    def stage_factory(symbol, target, routing):
        if symbol != "run":
            return original_stage_factory(symbol, target, routing)
        def run(request, ledger, progress, **keywords):
            value.routed_keywords.append(dict(keywords))
            if not keywords:
                return original_stage_factory(symbol, target, routing)(request, ledger, progress)
            assert set(keywords) == {"lb_rescue"}
            original_prepare = routing["globals"]["prepare"]
            def prepare(*args):
                case = original_prepare(*args)
                keywords["lb_rescue"](case, request)
                return case
            routed = dict(routing, globals=dict(routing["globals"], prepare=prepare))
            return original_stage_factory(symbol, target, routed)(request, ledger, progress)
        return run

    stage_module.__b3_rebind__ = stage_factory
    return value


def execute(value, *, enabled=False):
    bridge = m_source.MSourceBridge()
    ledger = _FIXTURE.FakeLedger(value.context)
    args = dict(lb_rescue=lb_research.factory_for_context(value.context, value.registry)) if enabled else {}
    return bridge.execute(value.context, ledger, **args)


def test_default_none_routes_original_three_arguments_without_common_import_or_pool():
    from v42_b3_joint.adapters import inspect_source_links
    for stage in ("M1", "M2"):
        links = inspect_source_links(stage)
        assert links and all(link["status"] == "STATIC_SIGNATURE_PASS" and not link["source_executed"]
                             and link["native_calls"] == link["model_builds"] == 0 for link in links)
        common_run = next(link for link in links if link["file"] == "v42_may_campaign_native90/m_stage.py")
        assert common_run["signature"] == "(request, budget, progress, *, lb_rescue=None)"
    value = fixture()
    output = execute(value)
    assert value.routed_keywords == [{}] and value.searches == []
    assert not any(row.get("module") in (lb_research.COMMON_MODULE, "v42_b3_joint.lb_research")
                   for row in value.registry.audit)
    assert output.aidc == value.aidc
    assert output.evidence_kind == "FAKE_SOURCE_TEST"
    assert output.source_packet["B2_FCFS_producer_calls"] == 0


def test_live_rebound_bridge_passes_optin_factory_and_uses_selected_stage_identity():
    first, second = fixture("M1", 1), fixture("M2", 2)
    for value in (first, second):
        output = execute(value, enabled=True)
        assert len(value.routed_keywords) == len(value.searches) == 1
        bound = value.searches[0].identity
        assert bound.stage == "B3_" + value.request.stage
        assert bound.day == value.authority.day
        assert bound.source_sha == value.authority.source_sha
        assert bound.input_sha == value.authority.input_sha
        assert bound.fixed_input_sha == value.request.fixed_input_sha
        assert bound.case_sha == value.last_case.case_sha
        assert bound.matrix_sha == value.last_case.identity["selected_matrix_sha"]
        assert bound.domain_sha == value.last_case.identity["selected_domain_sha"]
        assert bound.matrix_sha != value.last_case.identity["original_matrix_sha"]
        assert output.aidc == value.request.fixed_aidc
        assert output.evidence_kind == "FAKE_SOURCE_TEST"
    assert first.searches[0] is not second.searches[0]
    assert first.searches[0].identity.fixed_input_sha != second.searches[0].identity.fixed_input_sha


def test_source_drift_and_foreign_stage_factory_cannot_issue_or_exchange_a_pool():
    first, second = fixture("M1", 1), fixture("M2", 2)
    issued = lb_research.factory_for_context(first.context, first.registry)
    with pytest.raises(ValueError, match="STAGE_OR_FIXED_INPUT_DRIFT"):
        lb_research.checked_factory(issued, second.context, second.registry)
    with pytest.raises(ValueError, match="OWN_FACTORY_REQUIRED"):
        lb_research.checked_factory(lambda *a: None, first.context, first.registry)
    second.registry.source_manifest["v42_b3_joint/lb_research.py"] = "0" * 64
    with pytest.raises(ValueError, match="SOURCE_DRIFT"):
        lb_research.factory_for_context(second.context, second.registry)
    assert first.searches == second.searches == []


def test_current_request_fixed_sha_and_issued_context_cannot_be_relabelled():
    value = fixture()
    execute(value)
    issued = lb_research.factory_for_context(value.context, value.registry)
    for key, wrong in (("stage", "M2"), ("day", "2025-05-02"), ("fixed_input_sha", "0" * 64)):
        with pytest.raises(ValueError, match="INCOMING_STAGE_REQUEST_DRIFT"):
            issued(value.last_case, dict(value.context.identity, **{key: wrong}))
    issued.identity["fixed_input_sha"] = "0" * 64
    with pytest.raises(ValueError, match="STAGE_OR_FIXED_INPUT_DRIFT"):
        lb_research.checked_factory(issued, value.context, value.registry)
    assert value.searches == []


def test_original_verification_and_entire_fixed_payload_precede_common_constructor():
    value = fixture()
    execute(value)
    issued = lb_research.factory_for_context(value.context, value.registry)
    model = value.registry.modules[lb_research.MODEL_MODULE]
    original = model.verify_case
    model.verify_case = lambda case: dict(PASS=False, FAKE_SOURCE_TEST=True)
    with value.registry.execution_scope(value.context):
        with pytest.raises(ValueError, match="ORIGINAL_CASE_NOT_VERIFIED"):
            issued(value.last_case, value.context.identity)
        model.verify_case = original
        value.last_case.planning = dict(value.last_case.planning, sites=["wrong"])
        with pytest.raises(ValueError, match="FIXED_FULL_AIDC_PAYLOAD_DRIFT"):
            issued(value.last_case, value.context.identity)
    assert value.searches == []

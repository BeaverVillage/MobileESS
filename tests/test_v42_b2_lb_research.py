"""Three tiny sealed-request routing contracts; no real case or Native solve."""
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from scipy import sparse

from v42_autonomous_b2 import lb_research, worker
from v42_b2_seed_recovery_v19 import worker as original_worker, m_stage as v19_stage
from v42_may_campaign_native90 import m_stage, m_model, inputs
from v42_may_campaign_native90.a_routing import rebound
from v42_b2_seed_recovery_v19.common import atomic, read, record, digest, sha
from v42_m1_hybrid.blocks import matrix_sha


def fixture(tmp_path):
    """Actual source/request seals; explicitly synthetic fixed arrays and case."""
    root = tmp_path / "FAKE_ROUTING_ONLY"
    folder = root / "inputs" / "2025-05-01"
    folder.mkdir(parents=True)
    day, attempt = "2025-05-01", "lb_research_fake_01"
    out = root / "dates/B2" / day / "attempts" / attempt / "output"
    planning = {"PCC_P_kw": np.array([[2., 3.]]), "PCC_Q_kvar": np.array([[0., 0.]])}
    np.savez_compressed(folder / "PLANNING_PHYSICAL.npz", **planning)
    bundle = dict(day=day, SYNTHETIC_ROUTING_ONLY=True)
    atomic(folder / "NATIVE_INPUT.json", bundle)
    input_identity = dict(PASS=True, day=day, arm="B2", SYNTHETIC_ROUTING_ONLY=True)
    atomic(folder / "B2_FIXED_AIDC.json", dict(identity=input_identity,
           physical=record(folder / "PLANNING_PHYSICAL.npz"), selected_jobs={}))
    execution = worker.sources()
    originals = {relative: sha(worker.ROOT / relative) for relative in
                 ("v42_m1_anytime/dual_stabilization.py", "v42_may_campaign_native90/m_model.py",
                  "v42_b2_seed_recovery_v18/certificate_box.py",
                  "v42_capacity/reference.py")}
    manifest = dict(schema="V42_AUTONOMOUS_B2_V20", run_id="FAKE_GATE_A_ROUTING",
                    execution_sources=execution, execution_SHA=digest(execution),
                    attempt_id=attempt, input_folders={day: str(folder)},
                    initialization_native_limit_seconds=5400, builder_original_sources=originals,
                    inherited_B1_results={}, prior_attempts={})
    manifest_path = root / "MANIFEST.json"
    atomic(manifest_path, manifest)
    request = dict(root=str(root), arm="B2", day=day, run_id=manifest["run_id"], worker_slot=1,
                   attempt_id=attempt, manifest=str(manifest_path), manifest_SHA=sha(manifest_path),
                   implementation_SHA=manifest["execution_SHA"], input_folder=str(folder),
                   Threads=1, P2_calls=0, target_gap=.03, native_budget_seconds=5400,
                   wall_budget_seconds=None)
    request.update({key: str(out.parent / name) for key, name in
                    (("output", "output"), ("result", "RESULT.json"),
                     ("progress", "progress.json"), ("error", "error.json"))})
    path = out.parent / "request.json"
    atomic(path, request)
    A = sparse.csr_matrix([[1., -1.]])
    d = dict(lower=np.array([0., -np.inf]), upper=np.array([3., np.inf]),
             rhs=np.array([0.]), sense=np.array(["="]), objective=np.array([0., 1.]), constant=0.,
             names=np.array(["primary", "helper"]), row_names=np.array(["helper_binding"]))
    identity = dict(arm="B2", day=day, input_identity=input_identity,
                    selected_matrix_sha=matrix_sha(A), selected_domain_sha=m_model._domain_sha(d))
    case = SimpleNamespace(identity=identity, case_sha=digest(identity), bundle=bundle,
                           planning=planning, output=out, A=A, d=d)
    assert worker.verify_request(request) == manifest
    assert not out.exists()
    return SimpleNamespace(path=path, request=request, manifest=manifest, folder=folder, case=case)


def test_default_run_keeps_original_route_and_no_research_admission(monkeypatch):
    seen = []
    before_run, before_inputs = m_stage.run, inputs.generate_b2
    def probe(path):
        assert DateBudget is worker.ReceiptDateBudget
        assert m_stage.run is before_run
        assert inputs.generate_b2.__code__ is before_inputs.__code__
        seen.append(path)
        return 17
    monkeypatch.setattr(original_worker, "run", probe)
    monkeypatch.setattr(lb_research, "stage_scope", lambda *a: pytest.fail("DEFAULT_ADMITTED_RESEARCH"))
    assert worker.run("D:/FAKE_GATE_A_UNREAD_REQUEST.json") == 17
    assert seen == ["D:/FAKE_GATE_A_UNREAD_REQUEST.json"]
    assert m_stage.run is before_run and inputs.generate_b2 is before_inputs


def test_live_worker_and_original_v19_v18_rebounds_retain_code_and_stage_factory(tmp_path, monkeypatch):
    value = fixture(tmp_path)
    factory = lb_research.factory_for_request(value.path)
    entered, searches = [], []
    def source_prepare(request, progress=None):
        entered.append("ORIGINAL_V19_PREPARE_ROUTE")
        return value.case
    # Marked pure stand-in at the heavy common run boundary. Its code/globals
    # are routed by the actual unchanged V19->V18 rebound implementation.
    def fake_common_run(request, budget, progress, *, lb_rescue=None):
        assert lb_rescue is factory
        case = prepare(request, progress)
        searches.append(lb_rescue(case, request))
        return dict(SYNTHETIC_ROUTING_ONLY=True)
    monkeypatch.setattr(v19_stage, "prepare", source_prepare)
    monkeypatch.setattr(m_stage, "run", fake_common_run)
    monkeypatch.setattr(m_model, "verify_case", lambda case: entered.append("FAKE_ORIGINAL_CASE_CHECK") or dict(PASS=True))
    before_inputs = inputs.generate_b2
    def probe(path):
        routed = m_stage.run
        assert routed is not fake_common_run and routed.__code__ is fake_common_run.__code__
        assert routed.__globals__ is fake_common_run.__globals__
        assert routed.__kwdefaults__["lb_rescue"] is factory
        assert fake_common_run.__kwdefaults__ == {"lb_rescue": None}
        result = v19_stage.run(read(path), object(), None)
        assert result == dict(SYNTHETIC_ROUTING_ONLY=True)
        return 0
    monkeypatch.setattr(original_worker, "run", probe)
    assert worker.run(value.path, lb_rescue=factory) == 0
    assert m_stage.run is fake_common_run and inputs.generate_b2 is before_inputs
    assert entered == ["ORIGINAL_V19_PREPARE_ROUTE", "FAKE_ORIGINAL_CASE_CHECK"]
    identity = searches[0].identity
    assert identity.stage == "B2_M" and identity.day == value.request["day"]
    assert identity.source_sha == value.request["implementation_SHA"]
    assert identity.input_sha == sha(value.folder / "NATIVE_INPUT.json")
    assert identity.fixed_input_sha == sha(value.folder / "B2_FIXED_AIDC.json")
    assert identity.case_sha == value.case.case_sha
    assert identity.matrix_sha == value.case.identity["selected_matrix_sha"]
    assert identity.domain_sha == value.case.identity["selected_domain_sha"]
    # The original derive+independent verify operate on a separate view only.
    lo, hi, proof = searches[0].finite_box(value.case.A, value.case.d)
    assert np.array_equal(lo, [0., 0.]) and np.array_equal(hi, [3., 3.])
    assert proof["independent_replay"]["all_original_feasible_points_contained"] is True
    assert np.isneginf(value.case.d["lower"][1]) and np.isposinf(value.case.d["upper"][1])
    assert not Path(value.request["output"]).exists()
    # Exception exits also restore both actual entry aliases.
    monkeypatch.setattr(original_worker, "run", lambda path: (_ for _ in ()).throw(ValueError("FAKE_EXIT")))
    with pytest.raises(ValueError, match="FAKE_EXIT"):
        worker.run(value.path, lb_rescue=factory)
    assert m_stage.run is fake_common_run and inputs.generate_b2 is before_inputs


def test_foreign_factory_and_source_request_fixed_payload_or_original_case_drift_fail_closed(tmp_path, monkeypatch):
    value = fixture(tmp_path)
    factory = lb_research.factory_for_request(value.path)
    before = m_stage.run
    with pytest.raises(PermissionError, match="OWN_FACTORY_REQUIRED"):
        worker.run(value.path, lb_rescue=lambda *a: None)
    assert m_stage.run is before
    with pytest.raises(PermissionError, match="CURRENT_STAGE_REQUEST_DRIFT"):
        factory(value.case, dict(value.request, day="2025-05-02"))
    monkeypatch.setattr(m_model, "verify_case", lambda case: dict(PASS=False))
    with pytest.raises(PermissionError, match="ORIGINAL_CASE_NOT_VERIFIED"):
        factory(value.case, value.request)
    monkeypatch.setattr(m_model, "verify_case", lambda case: dict(PASS=True))
    value.case.planning = dict(value.case.planning, PCC_P_kw=np.array([[2., 4.]]))
    with pytest.raises(PermissionError, match="ENTIRE_FIXED_PLANNING_DRIFT"):
        factory(value.case, value.request)
    atomic(value.folder / "B2_FIXED_AIDC.json", dict(PASS=False, SYNTHETIC_TAMPER=True))
    with pytest.raises(PermissionError, match="ISSUED_SOURCE_OR_INPUT_DRIFT"):
        lb_research.checked_factory(factory, value.path)
    # Tamper a separate test manifest only; original source bytes stay intact.
    second = fixture(tmp_path / "other")
    broken = dict(second.manifest, builder_original_sources=dict(second.manifest["builder_original_sources"],
                   **{"v42_m1_anytime/dual_stabilization.py": "0" * 64}))
    atomic(second.request["manifest"], broken)
    changed = dict(second.request, manifest_SHA=sha(second.request["manifest"]))
    atomic(second.path, changed)
    with pytest.raises(PermissionError, match="ORIGINAL_SCIENCE_SOURCE_DRIFT"):
        lb_research.factory_for_request(second.path)
    assert m_stage.run is before and not Path(value.request["output"]).exists()

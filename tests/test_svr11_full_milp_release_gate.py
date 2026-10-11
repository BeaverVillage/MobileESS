"""A candidate must never dispatch ahead of Forecast, drain or real proof."""
from pathlib import Path
import sys
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import prepare_svr11_epoch14 as release
from v42_pr134_b1.common import atomic,digest


@pytest.fixture
def candidate(tmp_path,monkeypatch):
    old=tmp_path/'old';root=tmp_path/'new';dev=tmp_path/'dev'
    monkeypatch.setattr(release,'OLD',old);monkeypatch.setattr(release,'ROOT',root)
    monkeypatch.setattr(release,'DEV',dev)
    sources={'v42_common_mess/engine.py':'new'}
    monkeypatch.setattr(release,'source_files',lambda:sources)
    monkeypatch.setattr(release,'sha',lambda path:'old')
    monkeypatch.setattr(release,'REVIEWED',set(sources))
    atomic(old/'CAMPAIGN_MANIFEST.json',dict(code_root=str(old/'code'),
        execution_sources={'v42_common_mess/engine.py':'old'}))
    atomic(dev/'SOURCE_SEAL.json',dict(sources=sources,source_SHA=digest(sources)))
    atomic(old/'MODEL_PRECOMPUTE_REQUEST.json',dict(campaign_resume_held_for_V2_schema_binding_repair=True))
    ledger=dict(dates={d:dict(status='PASS') for d in release.DAYS},counts=dict(PASS=31),active_workers=[])
    atomic(old/'MODEL_PRECOMPUTE_LEDGER.json',ledger)
    return old,root,dev,ledger


def test_incomplete_forecast_cannot_release(candidate):
    old,root,dev,ledger=candidate;ledger['dates']['2025-05-31']['status']='RUNNING'
    atomic(old/'MODEL_PRECOMPUTE_LEDGER.json',ledger)
    assert release.release() is False
    assert not (root/'CAMPAIGN_MANIFEST.json').exists()


def test_live_model_worker_must_exit_naturally(candidate,monkeypatch):
    old,root,dev,ledger=candidate;ledger['active_workers']=[dict(PID=123)]
    monkeypatch.setattr(release,'live',lambda peer:True)
    atomic(old/'MODEL_PRECOMPUTE_LEDGER.json',ledger)
    assert release.readiness()['reason']=='WAITING_MODEL_WORKERS_NATURAL_EXIT'
    assert not root.exists()


def test_missing_actual_milp_log_result_is_not_release(candidate):
    assert release.readiness()['reason']=='WAITING_REAL_FULL_MILP_VALIDATION'


def test_native_hold_must_not_be_cleared_to_force_release(candidate):
    old,root,dev,ledger=candidate
    atomic(old/'MODEL_PRECOMPUTE_REQUEST.json',dict(campaign_resume_held_for_V2_schema_binding_repair=False))
    with pytest.raises(PermissionError,match='POLICY_HOLD'):release.readiness()


def test_source_drift_is_global_block(candidate):
    old,root,dev,ledger=candidate
    atomic(dev/'SOURCE_SEAL.json',dict(sources={},source_SHA=digest({})))
    with pytest.raises(PermissionError,match='SCIENCE_DRIFT'):release.readiness()


def test_unvalidated_real_results_cannot_create_production_manifest(candidate):
    old,root,dev,ledger=candidate
    for day in ('2025-05-16','2025-05-18'):
        atomic(dev/'dates/B2'/day/'attempts/phase2_01/RESULT.json',dict(PASS=False))
    with pytest.raises(PermissionError,match='REAL_VALIDATION_INCOMPLETE'):release.release()
    assert not (root/'CAMPAIGN_MANIFEST.json').exists()
    assert not (root/'FULL_MILP_SUCCESSOR_READY.json').exists()

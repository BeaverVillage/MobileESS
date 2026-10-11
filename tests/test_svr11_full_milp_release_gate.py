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
    atomic(old/'CAMPAIGN_MANIFEST.json',dict(code_root=str(old/'code'),execution_SHA='origin',
        execution_sources={'v42_common_mess/engine.py':'old'}))
    atomic(dev/'SOURCE_SEAL.json',dict(sources=sources,source_SHA=digest(sources)))
    atomic(old/'MODEL_PRECOMPUTE_REQUEST.json',dict(campaign_resume_held_for_V2_schema_binding_repair=True))
    ledger=dict(dates={d:dict(status='PASS') for d in release.DAYS},counts=dict(PASS=31),active_workers=[])
    atomic(old/'MODEL_PRECOMPUTE_LEDGER.json',ledger)
    atomic(old/'MODEL_PRECOMPUTE_READY.json',dict(PASS=True,source_SHA='origin',
        successful_models=31,failed_models=0,Native_optimizer_calls=0,Actual_calls=0))
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


def test_final_coordinator_cannot_restart_old_monitor_during_transition(candidate,monkeypatch):
    old,root,dev,ledger=candidate
    atomic(old/'MODEL_PRECOMPUTE_PROCESS.json',dict(PID=456))
    monkeypatch.setattr(release,'live',lambda peer:True)
    assert release.readiness()['reason']=='WAITING_MODEL_COORDINATOR_FINAL_AUDIT_AND_EXIT'


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


def test_receipt_schema_adapter_retains_original_native_result(candidate,monkeypatch):
    from v42_pr134_b1.common import read,record
    from v42_svr11 import milp_release
    old,root,dev,ledger=candidate
    identity=dev/'MODEL_IDENTITY.json'
    atomic(identity,dict(memory_after=dict(RSS_bytes=5,private_bytes=6)))
    full=record(identity);thin={k:full[k] for k in ('path','sha256')}
    result=dev/'RESULT.json';atomic(result,dict(PASS=True,Native_Runtime=1800.5,initial_UB=.7,final_UB=.6,
        memory=dict(peak_RSS_bytes=5,peak_private_commit_bytes=6),
        Phase2_rows=[dict(original_model_identity=thin)]))
    before=record(result)
    monkeypatch.setattr(milp_release,'validate',lambda path,sources:record(path/'FULL_MILP_VALIDATION_RELEASE_CONTRACT.json'))
    state=dict(source_SHA='source',sources={},real_validation={'2025-05-16':before})
    release.validation_contract(state)
    fixed=read(dev/'normalized_receipts/2025-05-16.json')
    assert record(result)==before
    assert fixed['Native_Runtime']==1800.5 and fixed['initial_UB']==.7 and fixed['final_UB']==.6
    assert fixed['Phase2_rows'][0]['original_model_identity']==full
    assert fixed['receipt_schema_normalization']['original_result']==before


def test_actual_identity_sha_drift_is_not_normalized(candidate):
    from v42_pr134_b1.common import record
    old,root,dev,ledger=candidate
    identity=dev/'MODEL_IDENTITY.json';atomic(identity,dict(original_rows=3))
    full=record(identity);thin={k:full[k] for k in ('path','sha256')}
    result=dev/'RESULT.json';atomic(result,dict(PASS=True,Phase2_rows=[dict(original_model_identity=thin)]))
    before=record(result);atomic(identity,dict(original_rows=2))
    with pytest.raises(PermissionError,match='IDENTITY_SHA_OR_SCHEMA_DRIFT'):
        release.validation_contract(dict(source_SHA='source',sources={},real_validation={'2025-05-16':before}))
    assert record(result)==before

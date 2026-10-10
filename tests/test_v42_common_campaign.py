"""Formal production admission, immutable epoch and crash ownership checks."""
from pathlib import Path
import pytest

from v42_common_campaign import VERSION, DAYS
from v42_common_campaign import authority, controller
from v42_pr134_b1.common import atomic, digest, record


@pytest.fixture
def epoch(tmp_path, monkeypatch):
    monkeypatch.setattr(authority, "ROOT", tmp_path)
    source = tmp_path / "v42_tiny" / "source.py"
    source.parent.mkdir(); source.write_text("original = True\n", encoding="utf8")
    sources = {"v42_tiny/source.py": record(source)["sha256"]}
    preflight = tmp_path / "preflight.json"
    atomic(preflight, dict(PASS=True, source_SHA=digest(sources)))
    manifest = dict(schema="V42_COMMON_U4_QUALIFICATION_V1", algorithm_version=VERSION,
        code_root=str(tmp_path), native_M_limit_seconds=1800, A_gap_target=.005,
        Threads=1, P2_calls=0, execution_sources=sources, execution_SHA=digest(sources),
        input_folders={day:str(tmp_path / day) for day in DAYS}, B1_results={},
        preflight=record(preflight))
    path = tmp_path / authority.MANIFEST
    atomic(path, manifest)
    return path, manifest, source


def test_source_epoch_mutation_rejected_at_admission(epoch):
    path, _, source = epoch
    authority.verify_manifest(path)
    source.write_text("original = False\n", encoding="utf8")
    with pytest.raises(PermissionError, match="SOURCE_SHA_DRIFT"):
        authority.verify_manifest(path)


def test_fresh_execution_pass_cannot_qualify_a_physically_failed_canary(epoch):
    path, manifest, _ = epoch
    receipts = {}
    for arm in ("B2", "B3"):
        result = path.parent / (arm + "_result.json")
        atomic(result, dict(PASS=True, actual_ac_physical_pass=arm == "B2",
            source_SHA=manifest["execution_SHA"], identity=dict(arm=arm, day=DAYS[0])))
        receipts[arm] = record(result)
    atomic(path.parent / "COMMON_U4_CAMPAIGN_MANIFEST.json", dict(schema="V42_COMMON_U4_CAMPAIGN_V1",
        source_SHA=manifest["execution_SHA"], qualification_manifest=record(path), canaries=receipts))
    with pytest.raises(PermissionError, match="BOTH_REAL_E2E_CANARIES_REQUIRED:B3"):
        authority.verify_real_canary(receipts["B3"], "B3", manifest)


def test_missing_worker_result_is_not_reexecuted_with_reset_runtime(tmp_path, monkeypatch):
    request_path = tmp_path / "REQUEST.json"
    atomic(request_path, dict(root=str(tmp_path), result=str(tmp_path / "RESULT.json")))
    atomic(tmp_path / "PROCESS.json", dict(PID=-1))
    monkeypatch.setattr(controller, "same_process", lambda value:False)
    monkeypatch.setattr(controller, 'storage_admission', lambda root:10**12)
    with pytest.raises(PermissionError, match="INTERRUPTED_ATTEMPT_REQUIRES_MEASURED_RECOVERY"):
        controller.launch(request_path)


def test_prior_epoch_costs_and_results_are_preserved_without_relabeling(epoch, monkeypatch):
    path, manifest, _ = epoch
    manifest.update(source_commit='original-commit')
    atomic(path, manifest)
    attempt=path.parent/'dates/B2/2025-05-01/attempts/old'
    result=attempt/'RESULT.json'
    atomic(result,dict(source_SHA=manifest['execution_SHA'],status='ACTUAL_AC_FAILED',
        native_runtime_seconds=376.553,worker_wall_seconds=635.155))
    atomic(attempt/'REQUEST.json',dict(result=str(result),arm='B2',day='2025-05-01'))
    atomic(attempt/'NATIVE_RUNTIME_LEDGER.json',dict(measured_Native_Runtime=376.553))
    before=record(result)
    receipt,history=controller.previous_common_evidence(path.parent)
    assert receipt==record(path) and record(result)==before
    row=history['B2/2025-05-01'][0]
    assert row['result']==before and row['status']=='ACTUAL_AC_FAILED'
    assert row['native_runtime_seconds']==376.553


def test_prior_live_worker_blocks_new_epoch_before_runtime_can_be_reset(epoch, monkeypatch):
    path, manifest, _=epoch
    attempt=path.parent/'dates/B2/2025-05-02/attempts/old'
    atomic(attempt/'REQUEST.json',dict(result=str(attempt/'RESULT.json')))
    atomic(attempt/'PROCESS.json',dict(PID=123))
    monkeypatch.setattr(controller,'same_process',lambda owner:True)
    with pytest.raises(PermissionError,match='PRIOR_EPOCH_ACTIVE_WORKER'):
        controller.previous_common_evidence(path.parent)


def test_storage_shortage_blocks_dispatch_without_starting_native(tmp_path,monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr(controller.shutil,'disk_usage',lambda root:SimpleNamespace(free=4*1024**3-1))
    with pytest.raises(PermissionError,match='STORAGE_HEADROOM'):
        controller.storage_admission(tmp_path)


def test_pending_or_defective_control_audit_holds_production_but_not_canaries(epoch):
    path, manifest, _ = epoch
    manifest['common_control_audit_required'] = True
    baseline=path.parent/'preserved_canary.json'
    atomic(baseline,dict(source_SHA='original-source-sha',status='ACTUAL_AC_FAILED'))
    manifest['control_audit_baseline']=record(baseline)
    atomic(path, manifest)
    authority.verify_manifest(path)
    with pytest.raises(PermissionError, match='CONTROL_AUDIT_PENDING'):
        authority.verify_manifest(path, production=True)
    audit=path.parent/'audit.json'
    payload=dict(schema='V42_MAY01_COMMON_CONTROL_CAUSAL_AUDIT_V1',
        baseline_RESULT=record(baseline),baseline_source_SHA='original-source-sha',
        audit_complete=True,common_control_implementation_defect=True,
        same_Actual_factorial_full_PQ_bit_exact=True,regcontrol_count=7,
        original_control_settings_preserved=True,original_canary_evidence_preserved=True)
    atomic(audit,payload)
    status=path.parent/'COMMON_CONTROL_AUDIT_STATUS.json'
    row=dict(schema='COMMON_U4_CONTROL_AUDIT_STATUS_V1', source_SHA=manifest['execution_SHA'],
        status='FAIL',common_control_implementation_defect=True,audit=record(audit))
    atomic(status,row)
    with pytest.raises(PermissionError, match='CONTROL_AUDIT_DISPATCH_HELD'):
        authority.verify_manifest(path, production=True)
    row.update(status='PASS',common_control_implementation_defect=False)
    atomic(status,row)
    with pytest.raises(PermissionError,match='AUTHORITATIVE_VERDICT_REQUIRED'):
        authority.verify_control_audit(path.parent,manifest)
    payload['common_control_implementation_defect']=False
    atomic(audit,payload)
    row['audit']=record(audit)
    atomic(status,row)
    authority.verify_control_audit(path.parent,manifest)
    audit.write_text('changed',encoding='utf8')
    with pytest.raises(PermissionError,match='FILE_SHA_DRIFT'):
        authority.verify_control_audit(path.parent,manifest)

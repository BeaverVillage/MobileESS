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
    atomic(request_path, dict(result=str(tmp_path / "RESULT.json")))
    atomic(tmp_path / "PROCESS.json", dict(PID=-1))
    monkeypatch.setattr(controller, "same_process", lambda value:False)
    with pytest.raises(PermissionError, match="INTERRUPTED_ATTEMPT_REQUIRES_MEASURED_RECOVERY"):
        controller.launch(request_path)

"""V43 isolation must fail closed without changing inherited optimization."""
import os
from types import SimpleNamespace
import pytest
from v43 import golden
from v43.common import atomic, record, BASE

def test_source_drift_denies_golden_before_native(tmp_path,monkeypatch):
    source=tmp_path/'producer.py';source.write_bytes(b'original\n')
    freeze=dict(base_commit=BASE,Worker=1,Threads=1,sources=[record(source)],
        support=[],scientific_inputs=[],baseline_execution_sources=[])
    atomic(tmp_path/'V43_BASELINE_AND_SOURCE_FREEZE.json',freeze)
    monkeypatch.setattr(golden,'DOC',tmp_path)
    golden.verified_freeze()
    source.write_bytes(b'changed\n')
    with pytest.raises(ValueError,match='FROZEN_BYTES_DRIFT'):golden.verified_freeze()

@pytest.mark.parametrize('arm,day,threads',[('B2','2025-05-01',1),('B1','2025-05-02',1),('B1','2025-05-01',2)])
def test_golden_permit_cannot_expand_scope(arm,day,threads):
    with pytest.raises(PermissionError,match='GOLDEN_B1_MAY01_ONLY'):
        with golden.permit(dict(arm=arm,day=day,Threads=threads)):pass

def test_heavy_peer_rejected_and_monitor_allowed(monkeypatch):
    monitor=SimpleNamespace(pid=123,info=dict(name='python.exe',cmdline=['python','-m','v42_pr134_b1.host','monitor']))
    monkeypatch.setattr(golden.psutil,'process_iter',lambda *args:[monitor])
    golden.no_heavy_peer()
    peer=SimpleNamespace(pid=456,info=dict(name='python.exe',cmdline=['python','-m','v42_integration.worker']))
    monkeypatch.setattr(golden.psutil,'process_iter',lambda *args:[monitor,peer])
    with pytest.raises(PermissionError,match='HEAVY_WORKER_CONFLICT'):golden.no_heavy_peer()

def test_original_guard_still_requires_exact_model_scope():
    from v42_may_campaign_native90.execution import guard
    from v42_may_campaign import execution
    token=execution._active.set(dict(request=dict(day='2025-05-01',arm='B1'),worker_slot=None))
    try:
        with pytest.raises(PermissionError,match='NATIVE_MODEL_SCOPE_REQUIRED'):guard(object())
    finally:execution._active.reset(token)

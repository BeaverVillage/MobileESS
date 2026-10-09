from pathlib import Path
import pytest
from v42_may_campaign_native90 import maintenance as m
from v42_may_campaign_native90.common import exclusive_lock,LockBusy

def test_ten_minutes_only_requests_diagnosis():
    assert not m.needs_build_diagnosis(True,False,599,600,755)
    assert m.needs_build_diagnosis(True,False,600,600,755)
    assert m.needs_build_diagnosis(True,False,10,1200,755)
    assert not m.needs_build_diagnosis(True,True,900,1200,755)
    assert not m.needs_build_diagnosis(False,False,900,1200,755)

def test_overlapping_maintenance_cannot_enter(tmp_path,monkeypatch):
    entered=[]
    monkeypatch.setattr(m,'_audit',lambda *args:entered.append(args) or {'PASS':True})
    storage=tmp_path/'hourly_maintenance'
    with exclusive_lock(storage/'MAINTENANCE.lock'):
        with pytest.raises(LockBusy):m.run(tmp_path,True)
    assert entered==[]
    assert m.run(tmp_path)=={'PASS':True}

def test_no_worker_termination_or_date_retry_in_maintenance():
    import inspect
    source=inspect.getsource(m._audit)
    for forbidden in ('terminate(', 'kill(', 'stop_worker(', 'dispatch_date(', 'native_optimize('):
        assert forbidden not in source

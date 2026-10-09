import pytest
from v42_b2_seed_recovery_v19 import coordinator as co
from v42_b2_seed_recovery_v19.common import atomic

def test_new_benchmark_uses_distinct_attempt_and_never_overwrites_request(tmp_path,monkeypatch):
    day='2025-05-03'
    manifest=dict(run_id='new',input_folders={day:str(tmp_path/'input')},execution_SHA='new_SHA',attempt_id='seed_policy_v19_02')
    atomic(tmp_path/co.MANIFEST,manifest)
    monkeypatch.setattr(co,'verify_request',lambda request:manifest)
    path,request=co.request_for(tmp_path,manifest,day,1)
    assert request['attempt_id']=='seed_policy_v19_02'
    assert path.parent.name=='seed_policy_v19_02'
    before=path.read_bytes()
    with pytest.raises(PermissionError,match='NEVER_OVERWRITTEN'):co.request_for(tmp_path,manifest,day,1)
    assert path.read_bytes()==before

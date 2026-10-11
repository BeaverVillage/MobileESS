from tools import b1_only_v3 as ops

def test_date_failures_with_original_valueerrors_do_not_hold_campaign():
    for kind in ('PHYSICAL_FAILURE','TIME_LIMIT_NO_FEASIBLE','TIME_LIMIT_FEASIBLE_NOT_CERTIFIED','INCONCLUSIVE'):
        assert not ops.blocked_result({'PASS':False,'reason':kind,'scientific':{'classification':kind,'error':"ValueError('PCC_PHYSICAL_FAILURE')"}})
    assert not ops.blocked_result({'PASS':False,'reason':'ACTUAL:VOLTAGE_VIOLATION'})
    for reason in ('CONTROL_ACTIONS_INCOMPLETE','QOS_FAILURE','WAN_VIOLATION','AC_NONCONVERGENCE'):
        assert not ops.blocked_result({'PASS':False,'reason':"ValueError('"+reason+"')",'traceback':'saved original error'})

def test_input_and_implementation_failures_block_new_dates():
    for kind in ('INPUT_FAILURE','IMPLEMENTATION_FAILURE'):
        assert ops.blocked_result({'scientific':{'classification':kind}})
    assert ops.blocked_result({'source_global_integrity_block':True})
    assert ops.blocked_result({'scientific':{'classification':'PHYSICAL_FAILURE','error':'DATA_SHA_DRIFT'}})

def test_available_ram_and_commit_must_both_reserve_worker(monkeypatch,tmp_path):
    c=dict(RAM_floor_bytes=4,Commit_floor_bytes=6,worker_reservation_bytes=10,minimum_disk_free_bytes=1)
    monkeypatch.setattr(ops,'heavy_peers',lambda root:[])
    monkeypatch.setattr(ops,'memory',lambda:dict(RAM_available=14,Commit_available=15))
    assert not ops.admitted(tmp_path,{'admission':c})[0]
    monkeypatch.setattr(ops,'memory',lambda:dict(RAM_available=14,Commit_available=16))
    assert ops.admitted(tmp_path,{'admission':c})[0]
    monkeypatch.setattr(ops,'heavy_peers',lambda root:[{'PID':999}])
    assert not ops.admitted(tmp_path,{'admission':c})[0]

def test_forbidden_policy_never_gets_request(tmp_path):
    import pytest
    for policy in ('B0','B2','B3'):
        with pytest.raises(PermissionError):ops.request(tmp_path,{},dict(arm=policy,day=ops.DAYS[0]))

def test_summed_runtime_preserves_unknown_and_physical_failed_metrics(tmp_path):
    r=tmp_path/'RESULT.json';ops.atomic(r,dict(Native_Runtime=None,known_completed_Native_Runtime=12))
    ledger={'status':'RUNNING','dates':{'B1/'+ops.DAYS[0]:dict(arm='B1',day=ops.DAYS[0],status='FAIL',result=str(r),reason='VOLTAGE_VIOLATION',metrics={'environments':{'ACTUAL':{'maximum_line_loading':1.2}}})}}
    m=dict(run_id='test',execution_SHA='scientific',operations_SHA='ops',hardware={},scenario={},thermal={},input_receipts={})
    report=ops.reports(tmp_path,ledger,m)
    assert report['total_Native_Runtime'] is None
    assert report['total_known_Native_Runtime']==12
    assert report['maximum_Actual_line_loading']==1.2
    assert not report['all31_executed'] and not report['all31_PASS']

from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch
import pytest
from v44_recovery_r026f1 import current_ac_performance as performance


@pytest.mark.parametrize('arm',['B0','B1','B3'])
def test_installed_current_probe_uses_combined_scope_and_reports_reuse(arm,tmp_path):
    from v44.svr12 import SVR12CurrentAC
    from v44.common import read
    oracle=SimpleNamespace(arm=arm,_independent_fresh=False,
        _prefix_history_proofs=SimpleNamespace(slots={},bytes=0,hits=4,misses=2,evictions=0))
    rows=[{'P':[1]}];sentinel=object();entered=[]
    @contextmanager
    def combined(received,inputs,encoding):
        assert received is oracle and inputs is rows
        entered.append(True);yield {'historical_slots':1,'reused_control_calls':4}
    request={'case_root':str(tmp_path)}
    with patch.object(SVR12CurrentAC,'_probe',return_value=sentinel),patch.object(performance,'require_policy',return_value=True),patch.object(performance,'current_probe_scope',combined):
        token=performance._actual_request.set(request)
        try:
            with performance.install():assert SVR12CurrentAC._probe(oracle,rows) is sentinel
        finally:performance._actual_request.reset(token)
    receipt=read(tmp_path/'CURRENT_AC_R026F1_PERFORMANCE.json')
    assert entered==[True] and receipt['arm']==arm
    assert receipt['history_last_probe']['reused_control_calls']==4
    assert receipt['history_certificate_cache']['hits']==4
    assert receipt['skipped_current_or_history_solves']==0


def test_combined_current_scope_rejects_independent_fresh():
    with pytest.raises(PermissionError,match='CANNOT_WRAP_FRESH'):
        with performance.current_probe_scope(SimpleNamespace(_independent_fresh=True),[],None):pass


def test_combined_scope_nests_history_inside_live_readers():
    from v44_recovery_r026f1 import history
    calls=[];oracle=SimpleNamespace(_independent_fresh=False);rows=[];encoding=object()
    @contextmanager
    def live(received,owner):
        assert received is encoding and owner is oracle
        calls.append('live-start');yield;calls.append('live-end')
    @contextmanager
    def reused(owner,inputs):
        assert calls==['live-start'] and owner is oracle and inputs is rows
        calls.append('history-start');yield {'native_solves_removed':0};calls.append('history-end')
    with patch.object(performance,'live_read_scope',live),patch.object(history,'scope',reused):
        with performance.current_probe_scope(oracle,rows,encoding) as stats:
            assert stats=={'native_solves_removed':0}
    assert calls==['live-start','history-start','history-end','live-end']

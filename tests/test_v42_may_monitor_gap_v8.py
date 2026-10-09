"""No scientific models: Global certificates, tiny gaps and monitor isolation."""
from unittest.mock import patch
from pathlib import Path
import pytest
from v42_may_monitor_gap_v8.monitor import gap_info
from v42_may_monitor_gap_v8 import service


def row(**values):
    return dict(arm='B1',day='2025-05-24',target_gap=.005,phase='ORIGINAL_P1',progress={},**values)


def test_tiny_certificate_is_preserved_without_rounding_to_zero():
    info=gap_info(row(UB=.5934193363589247,independent_Global_LB=.5934193361794243,
                      Certified_Gap=3.024849437037461e-10))
    assert info['available'] and info['value']==3.024849437037461e-10
    assert info['source']=='CURRENT_DATE_INDEPENDENT_GLOBAL_CERTIFICATE'


def test_solver_zero_gap_is_never_a_global_certificate():
    info=gap_info(dict(row(),progress={'MIPGap':0.0}))
    assert not info['available'] and info['value'] is None and info['solver_gap']==0
    assert info['solver_gap_is_Global_certificate'] is False


def test_missing_incumbent_explains_wait():
    assert '유효 해' in gap_info(row(independent_Global_LB=.4))['reason']


def test_missing_independent_lower_bound_explains_wait():
    assert '하한' in gap_info(row(UB=.5))['reason']


def test_inconsistent_bounds_and_nonfinite_gap_cannot_display_pass():
    for value in (row(UB=.5,independent_Global_LB=.6,Certified_Gap=0),
                  row(UB=.5,independent_Global_LB=.4,Certified_Gap=float('nan')),
                  row(UB=.5,independent_Global_LB=.4,Certified_Gap=float('inf')),
                  row(UB=.5,independent_Global_LB=.4,Certified_Gap=-.1)):
        assert not gap_info(value)['available']


def test_exact_zero_certificate_is_distinct_from_missing_value():
    assert gap_info(row(UB=.5,independent_Global_LB=.5,Certified_Gap=0))['available']
    assert not gap_info(row(UB=.5,independent_Global_LB=.5))['available']


def test_worker_date_and_input_are_not_crossed():
    a=gap_info(dict(row(),input_SHA='DATE24'))
    b=gap_info(dict(row(),day='2025-05-25',input_SHA='DATE25'))
    assert (a['day'],a['input_SHA']) != (b['day'],b['input_SHA'])


def test_native_zero_xml_uses_separate_read_only_module():
    root=Path('D:/fixture')
    doc=service.definition(root,'monitor',python='C:/Python/python.exe',sid='FIXTURE')
    args=doc.find('.//{'+service.windows.NS+'}Arguments').text
    assert 'v42_may_monitor_gap_v8.host monitor' in args
    assert doc.find('.//{'+service.windows.NS+'}LogonType').text=='InteractiveToken'


def test_watchdog_does_not_restart_healthy_monitor(tmp_path):
    from v42_pr134_b1.common import atomic
    cmd=['PYTHON','-B','-X','utf8','-m','v42_may_monitor_gap_v8.host','monitor',str(tmp_path.resolve())]
    atomic(tmp_path/'MONITOR_PROCESS.json',dict(command=cmd))
    with patch.object(service,'verify',return_value={}),patch.object(service,'same_process',return_value=True),patch.object(
            service.windows,'run_task',side_effect=AssertionError('HEALTHY_MONITOR_RESTART')):
        service.watchdog(tmp_path)


def test_ui_has_prominent_current_gap_and_adaptive_percent_precision():
    source=Path(service.__file__).with_name('index.html').read_text(encoding='utf-8')
    assert 'id="current-gap"' in source and '현재 Global Gap · 독립 인증' in source
    assert 'p.toExponential(2)' in source
    assert "metric('current-gap',info?.value,'계산 대기',gapPct)" in source


def test_replacement_cannot_terminate_coordinator_or_worker(tmp_path):
    from v42_pr134_b1.common import atomic
    atomic(tmp_path/'MONITOR_PROCESS.json',dict(PID=123,command=[
        'PYTHON','-B','-X','utf8','-m','v42_may_mess_build_v7.host','coordinator',str(tmp_path.resolve())]))
    with patch.object(service,'verify',return_value={}),patch.object(service,'same_process',return_value=True),patch.object(
            service.psutil,'Process',side_effect=AssertionError('COORDINATOR_KILL')):
        with pytest.raises(PermissionError,match='EXACT_OWNED_READ_ONLY'):
            with service.monitor_scope(tmp_path):pass


def test_only_exact_read_only_monitor_can_be_replaced(tmp_path):
    from v42_pr134_b1.common import atomic,read
    atomic(tmp_path/'MONITOR_PROCESS.json',dict(PID=123,command=[
        'PYTHON','-B','-X','utf8','-m','v42_may_mess_build_v7.host','monitor',str(tmp_path.resolve())]))
    with patch.object(service,'verify',return_value={}),patch.object(service,'same_process',return_value=True),patch.object(
            service.psutil,'Process') as peer:
        with service.monitor_scope(tmp_path) as acquired:assert acquired
    peer.assert_called_once_with(123)
    peer.return_value.terminate.assert_called_once_with()
    assert read(tmp_path/'MONITOR_V7R2_BEFORE_GAP_V8.json')['worker_kills']==0


def test_completed_receipt_is_reported_without_waiting_for_coordinator(tmp_path):
    from v42_pr134_b1.common import atomic
    from v42_may_monitor_gap_v8.monitor import result_received
    identity=dict(run_id='fake',arm='B1',day='2025-05-24',attempt_id='test',algorithm_version='V6')
    atomic(tmp_path/'request.json',dict(identity,result=str(tmp_path/'RESULT.json')))
    atomic(tmp_path/'RESULT.json',dict(identity=identity,input_SHA='DATE24',status='PASS'))
    worker=dict(request=str(tmp_path/'request.json'),worker_alive=False,input_SHA='DATE24')
    assert result_received(worker)
    assert not result_received(dict(worker,worker_alive=True))
    assert not result_received(dict(worker,input_SHA=None))


def test_another_date_result_cannot_mark_current_worker_finished(tmp_path):
    from v42_pr134_b1.common import atomic
    from v42_may_monitor_gap_v8.monitor import result_received
    identity=dict(run_id='fake',arm='B1',day='2025-05-24',attempt_id='test',algorithm_version='V6')
    atomic(tmp_path/'request.json',dict(identity,result=str(tmp_path/'RESULT.json')))
    atomic(tmp_path/'RESULT.json',dict(identity=dict(identity,day='2025-05-23'),input_SHA='DATE23'))
    assert not result_received(dict(request=str(tmp_path/'request.json'),worker_alive=False,input_SHA='DATE24'))

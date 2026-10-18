import json
from pathlib import Path
import pytest
from v44_monitor_bounds import bounds as b


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value),encoding='utf-8')


def test_preparation_has_explanation_instead_of_fake_zero(tmp_path):
    value=b.a_bounds(tmp_path)
    assert value['UB'] is value['LB'] is None
    assert value['ub_text']==value['lb_text']=='모델 구성 중'


def test_lp_and_restricted_bound_never_become_integer_ub_or_global_lb(tmp_path):
    write(tmp_path/'OUTPUT/P1/S0/NATIVE_RESULT.json',dict(status=2,objective=.6,ObjBound=.6))
    value=b.a_bounds(tmp_path)
    assert value['P1_LP_objective']==.6
    assert value['UB'] is None and value['LB'] is None
    assert value['ub_text']=='정수해 검증 전'


def test_pricing_trace_rational_lb_is_displayed_before_final_result(tmp_path):
    write(tmp_path/'OUTPUT/P1_TRACE.json',dict(trajectory=[dict(objective=.6,valid_LB='1/2'),dict(objective=.55,valid_LB='2/5')]))
    value=b.a_bounds(tmp_path)
    assert value['LB']==.5 and value['UB'] is None and value['P1_LP_objective']==.55


def test_zero_bounds_and_gap_are_valid_not_missing(tmp_path):
    write(tmp_path/'RESULT.json',dict(FULL_feasible=True,independent_Global_LB_validated=True,UB=0,LB=0,certified_gap=0))
    value=b.a_bounds(tmp_path)
    assert value['UB']==value['LB']==0 and value['gap_text']=='0%'


def test_physical_failure_does_not_publish_raw_result_ub(tmp_path):
    write(tmp_path/'RESULT.json',dict(PASS=False,FULL_feasible=False,UB=.4,LB=.3))
    assert b.a_bounds(tmp_path)['UB'] is None


def test_callback_incumbent_is_available_without_final_result(tmp_path):
    write(tmp_path/'OUTPUT/VALIDATED_INTEGER_INCUMBENTS.json',dict(trajectory=[dict(PASS=True,
        original_integer_types_restored=True,physical={'path':'checked'},exact_UB='3/5',exact_LB='1/2',acceptance={'PASS':False})]))
    value=b.a_bounds(tmp_path)
    assert value['UB']==.6 and value['LB']==.5 and not value['gap_certified']


def test_tiny_nonzero_gap_never_rounds_to_zero():
    assert b.gap_text(3.3455315059607004e-10)=='3.346e-08%'


@pytest.mark.parametrize('value',[None,True,'NaN','inf','bad',1e100])
def test_invalid_numbers_do_not_leak_into_status(value):
    assert b.number(value) is None


def test_m_lower_result_works_before_joint_trace(tmp_path):
    write(tmp_path/'LOWER_STAGE_RESULT.json',dict(Global_LB=.35,Global_LB_valid=True))
    write(tmp_path/'UPPER_STAGE_RESULT.json',dict(FULL_validated=True,BEST_GLOBAL_UB=.55,restricted_ObjBound_diagnostic=.5))
    value=b.m_bounds(tmp_path)
    assert value['UB']==.55 and value['LB']==.35


def test_restricted_m_bound_is_not_promoted(tmp_path):
    write(tmp_path/'UPPER_STAGE_RESULT.json',dict(current_pool_ObjVal=.55,restricted_ObjBound_diagnostic=.5))
    value=b.m_bounds(tmp_path)
    assert value['UB'] is value['LB'] is None


def test_m_waiting_reasons_distinguish_upper_and_lower(tmp_path):
    write(tmp_path/'K48_NATIVE_LEDGER.json',{})
    value=b.m_bounds(tmp_path)
    assert value['ub_text']=='FULL 해 검증 대기' and value['lb_text']=='독립 K48 하한 계산 중'


def test_partial_global_trace_keeps_last_complete_record(tmp_path):
    path=tmp_path/'GLOBAL_CONTROL/GLOBAL_GAP_TRACE.jsonl';path.parent.mkdir()
    path.write_text(json.dumps(dict(Global_UB=.6,Global_LB=.4,FULL_feasible=True))+'\n{"partial":',encoding='utf-8')
    value=b.m_bounds(tmp_path)
    assert value['UB']==.6 and value['LB']==.4


def test_previous_stage_is_retained_and_current_stage_stays_separate(tmp_path):
    case=tmp_path/'2025-05-02/B3/attempt015';(case/'M2').mkdir(parents=True)
    previous=case.parent/'attempt014/M1';previous.mkdir(parents=True)
    write(previous/'RESULT.json',dict(FULL_feasible=True,Global_UB=.6))
    write(previous/'LOWER_STAGE_RESULT.json',dict(Global_LB=.4,Global_LB_valid=True))
    write(case/'RESTORED_COMPLETED_STAGES.json',dict(M1=dict(root=str(previous))))
    write(case/'A2/RESULT.json',dict(FULL_feasible=True,independent_Global_LB_validated=True,UB=.54,LB=.539,certified_gap=.0019))
    rows=b.stage_rows(case,'M2')
    assert [r['stage'] for r in rows]==['M1','A2','M2']
    assert rows[0]['attempt']=='attempt014' and rows[0]['status'].startswith('재사용')
    assert rows[1]['UB']==.54 and rows[2]['UB'] is None


def test_bound_order_failure_is_not_reported_as_zero_gap():
    value=b.finish(.4,.5,None,'UB','LB','pending',True)
    assert value['gap_text']=='검산 필요' and not value['gap_certified']


def test_cached_read_refreshes_when_file_changes(tmp_path):
    path=tmp_path/'RESULT.json';write(path,dict(FULL_feasible=True,UB=.6))
    assert b.a_bounds(tmp_path)['UB']==.6
    write(path,dict(FULL_feasible=True,UB=.55))
    assert b.a_bounds(tmp_path)['UB']==.55


def test_generated_monitor_javascript_is_valid_before_deployment(tmp_path):
    import importlib.util
    source=Path('D:/MobileESS_V44/runtime/v43_planning_svr12_actual_v1/campaign004/AUTONOMOUS_RECOVERY/MONITOR_BOUNDS_20261018T034351Z/monitor_binding.before.py')
    if not source.exists() or not Path('C:/Program Files/nodejs/node.exe').exists():pytest.skip('Windows live monitor fixture unavailable')
    path=Path(__file__).resolve().parents[1]/'validation_tools/update_monitor_bounds.py'
    spec=importlib.util.spec_from_file_location('monitor_bounds_update',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    html=module.validate_ui(module.transform(source.read_text(encoding='utf-8-sig')),tmp_path)
    assert 'bounds-history-body' in html and 'FULL UB' in html

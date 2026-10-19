import importlib.util,json
from pathlib import Path
import pytest

source=Path('D:/MobileESS_V43/development/monitor_partial/a_stage_details.py')
spec=importlib.util.spec_from_file_location('monitor_phi_display_under_test',source)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


@pytest.mark.parametrize('value,expected',[
    ('21657105152079683/9223372036854775808','0.002348068'),
    ('18466747487640960993/295147905179352825856','0.062567774'),
    ('1/1000000000000','1e-12'),('0','0'),('-1/1000000000000','-1e-12'),
    ('3/2','1.5'),('invalid','미확인'),(None,'미확인'),('NaN','미확인')])
def test_fraction_is_rendered_as_its_value(value,expected):
    assert module.phi_display(value)==expected


def test_tiny_nonzero_is_never_displayed_as_zero():
    assert module.phi_display('1/'+('1'+'0'*400))=='1e-400'


def test_live_phase_display_preserves_raw_and_does_not_claim_zero_pass(tmp_path):
    out=tmp_path/'OUTPUT';out.mkdir()
    path=out/'PHASE_I_TRACE.json'
    exact='21657105152079683/9223372036854775808'
    path.write_text(json.dumps({'trajectory':[{'solve':12,'exact_Phi':exact}]}),encoding='utf8')
    original=path.read_bytes()
    value=module.details(tmp_path,{},dict(calls=[]),dict(Native_completed_seconds=0,Native_inflight=False),False)
    line=next(line for line in value['lines'] if line.startswith('인공변수:'))
    assert 'Φ≈0.002348068' in line and '/' not in line
    assert '0 인증 대기' in line and 'PASS' not in line
    assert value['phase_I_zero_PASS'] is False and path.read_bytes()==original


def test_zero_primal_certificate_still_takes_precedence(tmp_path):
    out=tmp_path/'OUTPUT';out.mkdir()
    (out/'PHASE_I_TRACE.json').write_text(json.dumps({'trajectory':[{'solve':1,'exact_Phi':'1000000'}]}))
    (out/'PHASE_I_ZERO_CERTIFICATE.json').write_text(json.dumps({'PASS':True,'zero':{'replayed_phi':'1/1000000000000'}}))
    value=module.details(tmp_path,{},dict(calls=[]),dict(Native_completed_seconds=0,Native_inflight=False),False)
    assert value['phase_I_zero_PASS'] is True
    line=next(line for line in value['lines'] if line.startswith('인공변수:'))
    assert '0 검증 PASS' in line and '1000000' not in line


def test_resumed_stage_displays_inherited_native_budget_and_cumulative_wall(tmp_path):
    ledger=dict(calls=[],checkpoint_resume=True,wall_seconds=5592.,inherited_Native_seconds=723.613,
        Native_ceiling_seconds=5400.)
    result=module.details(tmp_path,{},ledger,dict(Native_completed_seconds=723.613,Native_inflight=False),False)
    assert result['stage_elapsed_seconds']>=5592.
    assert any('기존 Native 723.6초 승계' in line and '총 예산 5400초 유지' in line for line in result['lines'])

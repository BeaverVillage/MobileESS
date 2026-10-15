from copy import deepcopy
import json
import pytest
from v42_integration.release_campaign import may_dates,launch_gate,input_gate,run_serial,STAGES
from v42_integration.unified_contract import digest


def plan_and_approval():
    p=dict(Worker=1,Threads=1,dates=may_dates(),automatic_start=False,release_sha='frozen')
    a=dict(approved=True,scope='MAY31_ALL_FROZEN_STAGES',release_sha='frozen',plan_sha=digest(p),Native_limit_seconds=1000.)
    return p,a


def ready():
    return dict(status='CAMPAIGN_READY',May01_integrated_Full96_Fresh='PASS',
        representative_dates={d:'PASS' for d in ('2025-05-02','2025-05-10','2025-05-12')})


def test_default_plan_and_single_p1_permission_cannot_launch_month():
    p,a=plan_and_approval()
    with pytest.raises(PermissionError):launch_gate(p,a,dict(status='CAMPAIGN_BLOCKED_WITH_EXACT_REASONS'))
    with pytest.raises(PermissionError):launch_gate(p,dict(approved=True,Native_limit_seconds=180.),dict(status='CAMPAIGN_READY'))


def test_copied_may01_initial_and_future_forecast_fail_date_gate():
    with pytest.raises(ValueError,match='DATE_SPECIFIC'):
        input_gate('2025-05-02',dict(day='2025-05-02',initial_state_day='2025-05-01'))


def test_failure_continues_next_date_without_executing_or_filling_tail(tmp_path):
    p,a=plan_and_approval();calls=[]
    def fail_input(**kw):
        calls.append((kw['day'],'INPUT'));return dict(day=kw['day'],status='INPUT_UNAVAILABLE')
    def forbidden(**kw):raise AssertionError('upstream failed; downstream must not execute')
    run_serial(p,approval=a,gate=ready(),folder=tmp_path,
        executors={s:fail_input if s=='INPUT' else forbidden for s in STAGES})
    assert len(calls)==31
    for day in may_dates():
        state=json.loads((tmp_path/day/'DATE_LEDGER.json').read_text())
        assert state['stages']['A1']==dict(executed=False,status='NOT_RUN',reason='UPSTREAM_STAGE_NOT_ACCEPTED')
        assert not (tmp_path/day/'A1').exists()


def test_unreconciled_stage_attempt_is_preserved_and_not_rerun(tmp_path):
    p,a=plan_and_approval();attempt=tmp_path/'2025-05-01/INPUT';attempt.mkdir(parents=True)
    raw=attempt/'RAW';raw.write_bytes(b'partial output')
    def fail(**kw):return dict(day=kw['day'],status='INPUT_UNAVAILABLE')
    run_serial(p,approval=a,gate=ready(),folder=tmp_path,executors={s:fail for s in STAGES})
    state=json.loads((tmp_path/'2025-05-01/DATE_LEDGER.json').read_text())
    assert state['status']=='NOT_CERTIFIED' and raw.read_bytes()==b'partial output'
    assert not state['stages']['INPUT']['executed']


def test_resume_rejects_changed_release_and_tampered_result(tmp_path):
    p,a=plan_and_approval()
    def fail(**kw):return dict(day=kw['day'],status='INPUT_UNAVAILABLE')
    e={s:fail for s in STAGES};run_serial(p,approval=a,gate=ready(),folder=tmp_path,executors=e)
    path=tmp_path/'2025-05-01/DATE_LEDGER.json';state=json.loads(path.read_text())
    state['stages']['INPUT']['result']['status']='FULL_PASS';path.write_text(json.dumps(state))
    with pytest.raises(ValueError,match='RECEIPT'):run_serial(p,approval=a,gate=ready(),folder=tmp_path,executors=e)

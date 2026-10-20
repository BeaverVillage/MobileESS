from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pytest
from v44_recovery_r030 import m1_voltage as policy
from v44_recovery_r030 import operations as op
from v42_native import voltage
from v44.common import atomic, record


@pytest.mark.parametrize('day', ['2025-05-01','2025-05-02','2025-05-07'])
def test_all_b3_m1_dates_use_new_band_and_restore(day):
    before = dict(voltage._MAPPING)
    with policy.scope(dict(day=day, arm='B3', stage='M1')):
        value = voltage.voltage_for(voltage.Stage.M1)
        assert (value.lower_pu,value.upper_pu,value.lower_squared,value.upper_squared) == (.955,1.045,.912025,1.092025)
        for stage in (voltage.Stage.A1,voltage.Stage.A2,voltage.Stage.M2,voltage.Stage.ACTUAL):
            assert voltage.voltage_for(stage) == before[stage]
    assert voltage._MAPPING == before


@pytest.mark.parametrize('arm,stage', [('B2','M1'),('B3','M2'),('B1','A1'),('B3','A2'),('B3','ACTUAL')])
def test_other_stages_keep_original_authorities(arm,stage):
    before = dict(voltage._MAPPING)
    with policy.scope(dict(arm=arm,stage=stage)):
        assert voltage._MAPPING == before
    assert voltage._MAPPING == before


def test_exception_restores_scope_and_legacy_checkpoints_are_rejected():
    before = dict(voltage._MAPPING)
    with pytest.raises(RuntimeError):
        with policy.scope(dict(arm='B3',stage='M1')): raise RuntimeError('test')
    assert voltage._MAPPING == before
    with pytest.raises(PermissionError,match='FRESH_NATIVE_CLOCKS'):
        with policy.scope(dict(arm='B3',stage='M1',resume_parent='old')): pass


def case(tmp_path):
    coeff=SimpleNamespace(voltage_constant=np.array([.98]), voltage_matrix=np.array([[.02]]))
    return SimpleNamespace(original_d=dict(row_names=np.array(['voltage_lower[0,0]','voltage_upper[0,0]']),
        rhs=np.array([.912025-1.,1.092025-1.]),sense=np.array(['>','<'])),coefficients=[coeff],
        anchor=dict(controls=[[1.]]),identity=dict(day='2025-05-02'),case_sha='case',output=tmp_path)


def test_full_rows_are_checked_against_anchor_and_wrong_rhs_is_rejected(tmp_path):
    c=case(tmp_path); proof=policy.check_rows(c)
    assert proof['PASS'] and proof['lower_rows']==proof['upper_rows']==1
    c.original_d['rhs'][0] -= .009525
    with pytest.raises(ValueError,match='RHS_DRIFT'): policy.check_rows(c)


def test_missing_or_reversed_voltage_rows_are_rejected(tmp_path):
    c=case(tmp_path);c.original_d['sense'][0]='<'
    with pytest.raises(ValueError,match='ROW_SENSE'): policy.check_rows(c)
    c.original_d['row_names'][1]='other'
    with pytest.raises(ValueError,match='ROW_AXIS'): policy.check_rows(c)


def test_only_pending_old_b3_cases_restart_once(tmp_path,monkeypatch):
    amendment=tmp_path/'amendment.json';atomic(amendment,{'policy':'test'})
    monkeypatch.setattr(op,'AMENDMENT',amendment)
    parent=tmp_path/'2025-05-02/B3/attempt013';parent.mkdir(parents=True)
    atomic(parent/'START.json',dict(sources=[]))
    assert op.model_restart(parent,dict(PASS=False,status='FAILED'))
    assert not op.model_restart(parent,dict(PASS=True,status='COMPLETE'))
    atomic(parent/'START.json',dict(sources=[record(amendment)]))
    assert not op.model_restart(parent,dict(PASS=False,status='FAILED'))
    assert not op.model_restart(parent.parent.with_name('B1')/'attempt001',dict(PASS=False))


def test_child_commands_keep_base_algorithm_boundary_token():
    args=['python','-u','-m',op.ALGORITHM,'--worker','request.json']
    routed=op.command(args)
    assert routed[3]==op.ENTRY and routed[-2:]==['--algorithm',op.ALGORITHM]
    assert op.command('shell command')=='shell command'


def test_request_decoration_requires_fresh_b3_without_breaking_may07(monkeypatch,tmp_path):
    from v44_recovery_r029_switch import operations as previous
    from contextlib import nullcontext
    amendment=tmp_path/'amendment.json';atomic(amendment,{})
    monkeypatch.setattr(op,'AMENDMENT',amendment)
    monkeypatch.setattr(op,'authority',lambda: {})
    monkeypatch.setattr(previous,'install',nullcontext)
    monkeypatch.setattr(op.base,'decorate',lambda case,permit:case)
    with op.install():
        b3=op.base.decorate(dict(day='2025-05-02',arm='B3',sources=[],fresh_a2_parent='old',wall_resume_parent='old'),{})
        b1=op.base.decorate(dict(day='2025-05-07',arm='B1',sources=[],wall_resume_parent='old'),{})
        assert b3['B3_new_M1_A2_M2_required'] and 'fresh_a2_parent' not in b3 and 'wall_resume_parent' not in b3
        assert b1['wall_resume_parent']=='old'
        assert b3['source_sha']==op.digest(b3['sources'])


def test_tight_plan_check_rejects_original_095_boundary(tmp_path,monkeypatch):
    from v44_recovery_r029 import strict_recovery
    monkeypatch.setattr(strict_recovery,'voltage_report',lambda *a:{'strict_PASS':True})
    c=SimpleNamespace(coefficients=[SimpleNamespace(control_names=['aidc_load_kw[AIDC01]'],
        voltage_constant=np.array([.9025]),voltage_matrix=np.zeros((1,1)))],output=tmp_path,case_sha='case')
    payload=dict(planning=dict(sites=np.array(['AIDC01']),PCC_P_kw=np.zeros((1,1))))
    with pytest.raises(ValueError,match='TIGHT_M1_PLAN_VOLTAGE_FAILED'):
        policy.check_plan(c,payload,dict(plan_sha='plan'))


def test_worker_scope_covers_case_binding_then_restores_on_failure(tmp_path,monkeypatch):
    from v44 import worker,q250_m4_v2 as q
    c=case(tmp_path);calls=[]
    def bind(current,request):
        current.case_sha='final_Q250_case'
        return current
    def stage(request,payload):
        assert voltage.voltage_for(voltage.Stage.M1).lower_pu==.955
        q.bind_case(c,request)
        return dict(allow_downstream=False,status='NO_FULL_FEASIBLE_INCUMBENT')
    monkeypatch.setattr(worker,'m_stage',stage);monkeypatch.setattr(q,'bind_case',bind)
    request=dict(arm='B3',stage='M1',root=str(tmp_path),day='2025-05-02')
    with policy.install(lambda request:calls.append(request)):
        result=worker.m_stage(request,{})
    assert not result['allow_downstream'] and len(calls)==1
    from v44.common import read
    assert read(tmp_path/'R030_M1_FULL_VOLTAGE_ROWS.json')['case_sha']=='final_Q250_case'
    assert voltage.voltage_for(voltage.Stage.M1).lower_pu==.95
    assert worker.m_stage is stage and q.bind_case is bind


def test_nested_physical_authority_cannot_reset_tight_m1(monkeypatch):
    from contextlib import contextmanager
    from v42_integrated import contract
    before=dict(voltage._MAPPING)
    calls=[]
    @contextmanager
    def original_authority():
        saved=dict(voltage._MAPPING)
        for stage in (voltage.Stage.A1,voltage.Stage.M1,voltage.Stage.A2,voltage.Stage.M2):
            voltage._MAPPING[stage]=voltage.ROBUST_PLANNING
        calls.append('original_equipment_checks')
        try: yield {'equipment_checked':True}
        finally:
            voltage._MAPPING.clear();voltage._MAPPING.update(saved)
    monkeypatch.setattr(contract,'physical_authority',original_authority)
    with policy.scope(dict(arm='B3',stage='M1')):
        with contract.physical_authority() as authority:
            assert authority['equipment_checked']
            assert voltage.voltage_for(voltage.Stage.M1).lower_pu==.955
            assert voltage.voltage_for(voltage.Stage.M2).lower_pu==.95
    assert calls==['original_equipment_checks'] and voltage._MAPPING==before
    assert contract.physical_authority is original_authority

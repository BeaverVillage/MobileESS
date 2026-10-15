"""Named Native0 campaign fixtures; real public dispatch, zero solver work."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from v42_integration import table_v_campaign as mod
from v42_integration.m_engine import _write


def test_prepared_124_case_inventory_cannot_launch_native(tmp_path,monkeypatch):
    from v42_integration.release_production_campaign import run_production
    monkeypatch.setattr(mod,'preflight_table_v_plan',lambda *a,**k:{'blockers':[]})
    plan=dict(schema=mod.SCHEMA,execution_scope='PREPARED_ONLY',dates=['2025-05-01'])
    with pytest.raises(PermissionError,match='NO_HEAVY'):
        run_production(plan,authorization={},gate={},folder=tmp_path,budget_ledger={})
    assert not list(tmp_path.iterdir())
    with pytest.raises(ValueError,match='DUMMY'):
        run_production(plan,authorization={},gate={},folder=tmp_path,budget_ledger={},executor=lambda:None)


def test_cross_date_source_or_shared_execution_root_fails_native0(tmp_path,monkeypatch):
    import v42_integration.table_v_flex_planning as flex
    monkeypatch.setattr(flex,'require_flex_case',lambda m:m)
    manifest=dict(day='2025-05-02',source_sha='source',identity={'case_sha':'May02'})
    _write(tmp_path/'INPUTS/FULL_FLEX/TABLE_V_FLEX_CASE_MANIFEST.json',manifest)
    plan=dict(schema=mod.SCHEMA,dates=['2025-05-02','2025-05-12'],Worker=1,Threads=1,P2_calls=0,
        R2='HOLD',automatic_start=False,execution_roots={d:str(tmp_path) for d in ['2025-05-02','2025-05-12']},
        case_bindings={'2025-05-02':dict(day='2025-05-02',source_sha='source',source_identity={'case_sha':'May02'}),
            '2025-05-12':dict(day='2025-05-12',source_sha='source',source_identity={'case_sha':'May02'})})
    result=mod.preflight_table_v_plan(plan)
    assert any('EXACT_INDEPENDENT_DATE' in r for r in result['blockers'])
    assert 'DATE_EXECUTION_ROOTS_MUST_BE_INDEPENDENT' in result['blockers']


def test_real_arm_dispatch_continues_other_arm_next_date_and_resumes_without_calls(tmp_path,monkeypatch):
    from v42_integration import table_v_run as runner
    dates=['2025-05-01','2025-05-02'];calls=[]
    roots={d:tmp_path/'executions'/d for d in dates}
    plan=dict(schema=mod.SCHEMA,dates=dates,execution_scope='NAMED_NATIVE0_FIXTURE',
        execution_roots={d:str(p) for d,p in roots.items()},
        case_bindings={d:dict(day=d,source_sha=d,source_identity={'case_sha':d}) for d in dates})
    monkeypatch.setattr(mod,'preflight_table_v_plan',lambda *a,**k:{'blockers':[]})
    monkeypatch.setattr(mod,'_launch_gate',lambda *a:None)
    monkeypatch.setattr(runner,'verify_adapters',lambda *a:None)
    monkeypatch.setattr(runner,'budget',lambda root,kind:SimpleNamespace(authorization={'fixture':True},path=root/(kind+'.json')))
    def real_arm_fixture(arm,output,**kwargs):
        import numpy as np
        day=output.name;calls.append((day,arm))
        value=dict(arm=arm,day=day,status='INFEASIBLE_REPORTED_CURRENT_MATRIX' if arm=='B1' else 'FULL_PASS')
        _write(output/arm/'ARM_OUTCOME.json',value)
        np.savez_compressed(output/arm/'BINARY_RAW.npz',trace=np.zeros((96,12)))
        return value
    monkeypatch.setattr(runner,'run_arm',real_arm_fixture)
    approval={d:{k:{'fixture':True} for k in ['PLANNING','K48']} for d in dates}
    ledgers={d:{k:str(roots[d]/(k+'.json')) for k in ['PLANNING','K48']} for d in dates}
    result=mod.run_table_v_production(plan,authorization=approval,gate={},folder=tmp_path/'checkpoint',budget_ledger=ledgers)
    assert calls==[(d,a) for d in dates for a in mod.ARMS]
    assert len(result['reports'])==8
    mod.run_table_v_production(plan,authorization=approval,gate={},folder=tmp_path/'checkpoint',budget_ledger=ledgers)
    assert len(calls)==8
    assert (tmp_path/'checkpoint/B2/2025-05-02/DATE_LEDGER.json').is_file()


def test_direct_later_date_arm_is_blocked_before_output_or_native(tmp_path):
    from v42_integration.table_v_run import run_arm
    _write(tmp_path/'INPUTS/FULL_FLEX/TABLE_V_FLEX_CASE_MANIFEST.json',dict(day='2025-05-12'))
    with pytest.raises(PermissionError,match='LATER_DATE'):
        run_arm('B2',tmp_path)
    assert not (tmp_path/'B2').exists()


def test_wrong_source_may01_pass_header_cannot_authorize_later_dates(tmp_path):
    from v42_integration.m_engine import file_record
    expected=dict(day='2025-05-01',source_sha='CURRENT',source_identity={'case_sha':'CURRENT'})
    _write(tmp_path/'ARM_OUTCOME.json',dict(day='2025-05-01',arm='B0',status='FULL_PASS'))
    _write(tmp_path/'ACTUAL_RESULT.json',dict(result=dict(day='2025-05-01',arm='B0',status='FULL_PASS',
        source_sha='OLD',source_identity={'case_sha':'OLD'})))
    _write(tmp_path/'FRESH_AC_RESULT.json',dict(result=dict(arm='B0',status='FULL_PASS',executed_slots=96)))
    with pytest.raises((ValueError,FileNotFoundError)):
        mod.validate_arm_full96(file_record(tmp_path/'ARM_OUTCOME.json'),expected,'B0',expected_policy_sha='CURRENT')


def test_m_and_k48_builds_require_live_memory_and_worker_gate(tmp_path,monkeypatch):
    from v42_integration.table_v_run import current_build_admission
    import v42_integration.table_v_resources as resources
    budget=SimpleNamespace(worker_lock=tmp_path/'HEAVY.lock')
    monkeypatch.setattr(resources,'_snapshot',lambda:dict(memory=dict(AvailableMBytes=8000,PercentCommittedBytesInUse=20)))
    accepted=current_build_admission(budget,arm='B2',stage='M1',operation='CURRENT_M_NATIVE0_BUILD')
    assert accepted['status']=='PASS'  # RAM is telemetry after the user's removal request.
    monkeypatch.setattr(resources,'_snapshot',lambda:dict(memory=dict(AvailableMBytes=16000,PercentCommittedBytesInUse=20)))
    budget.worker_lock.write_text('owned-another-worker')
    with pytest.raises(RuntimeError,match='RESOURCE_ADMISSION_DENIED'):
        current_build_admission(budget,arm='B2',stage='M1',operation='CURRENT_K48_NATIVE_BUILD')
    assert budget.worker_lock.read_text()=='owned-another-worker'


def test_date_bound_stage_budget_does_not_spend_another_day(tmp_path,monkeypatch):
    from test_v42_table_v_budget import setup,context
    from v42_integration.table_v_budget import TableVStageBudget
    b,auth,hist,Model=setup(tmp_path,monkeypatch)
    auth['authorization_id']='TWO_DATE_NAMED_FIXTURE'
    auth['authorized_ledger_path']=str(tmp_path/'TWO.json')
    auth['source_cases'].append(dict(day='2025-05-12',source_sha='May12',source_identity={'fixture':12}))
    b=TableVStageBudget(tmp_path/'TWO.json',authorization=auth,historical_ledgers=hist,worker_lock=b.worker_lock)
    with b.arm_context('B1'),context(b,'B1','A1'),b.capture_native_methods():
        model=Model();model.seconds=100.
        b.solve(model,label='RELEASE_P1:A1:FIXTURE',cap=5400.)
    c=dict(day='2025-05-12',arm='B1',stage='A1',stage_case_sha='May12',source_sha='May12',parent_result_sha='parent12')
    b.derived_bindings.append(c)
    with b.arm_context('B1'),b.phase('A1','May12','May12','parent12'):
        assert b.context['day']=='2025-05-12'
        assert b.remaining()==5400.
    with b.arm_context('B1'),context(b,'B1','A1'):
        assert b.remaining()==5300.

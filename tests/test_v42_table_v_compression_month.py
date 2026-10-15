"""Month/stage guards and original algorithm routing; no Native optimization."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from v42_integration import table_v_compression_adapter as adapter
from v42_integration import table_v_dw as dw
from v42_integration.a_engine import digest


@pytest.mark.parametrize('day',[f'2025-05-{n:02d}' for n in range(1,32)])
@pytest.mark.parametrize('arm,stage',[('B1','A1'),('B3','A1'),('B3','A2')])
def test_every_date_and_flexible_stage_uses_one_common_verified_path(day,arm,stage,tmp_path,monkeypatch):
    context=dict(manifest=dict(day=day,Table_V_full_flex=True))
    case=SimpleNamespace(arm=arm,stage=stage)
    calls=[]
    def prepare(c,k,b,o,**kwargs):
        calls.append((c,k));return dict(day=c['manifest']['day'],arm=k.arm,stage=k.stage)
    monkeypatch.setattr(adapter,'prepare_exact_dw',prepare)
    result=dw.prepare_current_dw(context,case,None,tmp_path)
    assert result==dict(day=day,arm=arm,stage=stage) and calls==[(context,case)]


def binding_fixture(stage='A2',arm='B3'):
    fixed=dict(P_by_site={'A':[2.]*96},Q_by_site={'A':[1.]*96},SOC=[3.]*97,route=['A']*96)
    fixed['plan_sha']=digest(fixed)
    context=dict(manifest=dict(day='2025-05-10',identity={'case_sha':'day10'}),
        input_audit={'a_input_sha':'day10-input'})
    case=SimpleNamespace(arm=arm,stage=stage,case_sha='stage',grid=SimpleNamespace(fixed_mess=fixed))
    capture=dict(objective_sha='objective',native_binding={'matrix_sha':'actual'},input_sha='day10-input')
    return context,case,capture


@pytest.mark.parametrize('field',['fixed_MESS_sha','objective_sha','case_sha','day','stage','source_identity','native_binding'])
def test_a2_cannot_reuse_a1_or_other_fixed_mess_objective_source(field):
    context,case,capture=binding_fixture()
    capture['stage_binding']=adapter.stage_binding(context,case,capture)
    capture['stage_binding'][field]='different'
    with pytest.raises(ValueError,match='DATE_STAGE_FIXED_MESS_OBJECTIVE'):
        adapter.stage_binding(context,case,capture)


@pytest.mark.parametrize('arm,stage',[('B0','A1'),('B2','A1'),('B1','A2')])
def test_reference_or_unsupported_stage_cannot_enter_compression(arm,stage):
    context,case,capture=binding_fixture(stage,arm)
    with pytest.raises(ValueError,match='EXACT_FLEX_ARM_STAGE'):
        adapter.stage_binding(context,case,capture)


def test_fixed_mess_bytes_require_their_current_seal():
    context,case,capture=binding_fixture()
    case.grid.fixed_mess['P_by_site']['A'][0]=3.
    with pytest.raises(ValueError,match='FIXED_MESS_SEAL'):
        adapter.stage_binding(context,case,capture)


def test_a1_b3_same_input_does_not_authorize_a2_stage_cache():
    context,case,capture=binding_fixture('A1')
    capture['stage_binding']=adapter.stage_binding(context,case,capture)
    case.stage='A2'
    with pytest.raises(ValueError,match='BINDING_DRIFT'):
        adapter.stage_binding(context,case,capture)


def test_narrow_native_authorization_rejects_other_arms_and_stages(tmp_path,monkeypatch):
    from test_v42_table_v_budget import setup,context as phase_context
    budget,auth,_,_=setup(tmp_path,monkeypatch)
    budget.authorization['authorized_arm_stages']=['B1:A1']
    for arm,stage in [('B2','M1'),('B3','A1'),('B3','A2')]:
        with budget.arm_context(arm),pytest.raises(PermissionError,match='NOT_AUTHORIZED'):
            with phase_context(budget,arm,stage):pass
    assert not budget.document['calls']


@pytest.mark.parametrize('restriction',[['B1:A1','B1:A1'],['B1:A2'],['P2'],[{}],'B1:A1'])
def test_native_subset_authorization_rejects_malformed_scope(restriction,tmp_path,monkeypatch):
    from test_v42_table_v_budget import setup
    from v42_integration.table_v_budget import require_authorization
    _,auth,_,_=setup(tmp_path,monkeypatch);auth['authorized_arm_stages']=restriction
    with pytest.raises(PermissionError,match='SUBSET'):require_authorization(auth)


def test_dw_resource_denial_precedes_any_model_materialization(tmp_path,monkeypatch):
    from v42_integration import table_v_resources as resources
    from v42_a_stage_domain_v2 import stress_backend
    from test_v42_table_v_class_aggregation import fixture
    snapshot,_,_,_=fixture()
    dw._freeze_sources(tmp_path)
    budget=SimpleNamespace(remaining=lambda:1.)
    case=SimpleNamespace(stage='A1',data=({'day':'2025-05-10'},))
    worker=dw.CurrentNative(budget,case,tmp_path)
    materialized=[]
    monkeypatch.setattr(stress_backend,'materialize',lambda *args:materialized.append(args))
    def deny(current,*,phase):
        assert current is budget and phase=='PRE_DW_MODEL_BUILD:PHASE_I'
        raise RuntimeError('FIXTURE_RAM_OR_WORKER_DENIED')
    monkeypatch.setattr(resources,'admit_resources',deny)
    with pytest.raises(RuntimeError,match='RAM_OR_WORKER_DENIED'):
        worker.solve(snapshot,tmp_path/'NATIVE','PHASE_I')
    assert not materialized and not worker.calls

"""Operational call-cap and original-grid restore checks; no Native calls."""
from pathlib import Path
import pytest
from v44.common import read,atomic,record,digest,RUNTIME,DOC
from v44 import cap300

@pytest.fixture
def permit(tmp_path):
    value=read(RUNTIME/'v43_planning_svr12_actual_v1/APPROVED_EXECUTION_PERMIT.json')
    overlay=dict(policy=cap300.POLICY,Joint_call_cap=300.,K48_total=300.,Joint_total=900.,Threads=1,
        Native_clock_reset=False,source=record(cap300.__file__))
    value.update(operational_overlay=overlay,execution_policy_sha=digest(overlay),
        base_source_freeze=record(DOC/'SCIENTIFIC_FREEZE_MANIFEST.json'))
    path=tmp_path/'PERMIT.json';atomic(path,value);return path

def test_cap300_changes_both_limits_without_modifying_frozen_algorithm(permit):
    from v44 import config,budget
    from v44.frozen.v43_mess.library import load
    modules=load();adaptive=modules['m_adaptive'];before=record(adaptive.__file__)
    old=(config.JOINT_CALL_CAP,budget.JOINT_CALL_CAP,adaptive.JOINT_CAP_SECONDS)
    with cap300.install(permit):
        assert (config.JOINT_CALL_CAP,budget.JOINT_CALL_CAP,adaptive.JOINT_CAP_SECONDS)==(300.,300.,300.)
        assert config.K48_SECONDS==300. and config.JOINT_SECONDS==900.
        assert record(adaptive.__file__)==before
    assert (config.JOINT_CALL_CAP,budget.JOINT_CALL_CAP,adaptive.JOINT_CAP_SECONDS)==old

@pytest.mark.parametrize('field,value',[('Joint_call_cap',140.),('Joint_total',1800.),('K48_total',0.),('Native_clock_reset',True)])
def test_policy_drift_rejected(permit,field,value):
    doc=read(permit);doc['operational_overlay'][field]=value
    doc['execution_policy_sha']=digest(doc['operational_overlay']);atomic(permit,doc)
    with pytest.raises(PermissionError):cap300.validate(permit)

def test_restore_adapter_only_routes_original_v43_coefficients():
    from v44.m_restore import restore
    adapted=cap300.restore_adapter(restore)
    assert 'v42_svr11.model' not in adapted.__code__.co_consts
    assert 'outputs' in adapted.__code__.co_consts and 'planning_coefficients' in adapted.__code__.co_consts
    with pytest.raises(PermissionError):cap300.coefficient_loader(dict(model_version='SVR11'), '2025-05-01')

def test_default_other_stage_route_preserved():
    calls=[]
    original=lambda c,s,f:calls.append((c,s,f)) or 'original'
    assert cap300.resumed_stage(original,dict(day='2025-05-03',arm='B2'),'M1',None)=='original'
    assert len(calls)==1

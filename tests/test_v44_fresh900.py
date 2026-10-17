from types import SimpleNamespace
from v44.common import read,digest
from v44.budget import StageBudget,resume
from v44.fresh900 import fresh_budget

def test_explicit_fresh_joint_starts_zero_and_old_ledger_is_immutable(tmp_path):
    case=SimpleNamespace(identity=dict(day='2025-05-01',arm='B2',stage='M1',source_sha=digest('source')),
        case_sha=digest('case'),fresh900_authorized=True,fresh900_policy_sha=digest('policy'))
    old=StageBudget(tmp_path/'old.json',case=case,kind='PLANNING_NATIVE')
    old.calls=[dict(status='FINISHED',Native_Runtime=560.957)];old.charge(560.957)
    before=old.path.read_bytes()
    new=fresh_budget(resume,old.path,case=case,kind='PLANNING_NATIVE',destination=tmp_path/'new.json')
    assert new.used()==0 and new.remaining()==900 and new.calls==[]
    assert new.authorization['new_Joint_clock_started_at_zero']
    assert not new.authorization['prior_calls_imported']
    new.calls.append(dict(status='FINISHED',Native_Runtime=300.));new.charge(300.)
    assert new.used()==300 and new.remaining()==600
    assert old.path.read_bytes()==before

def test_without_fresh_authority_original_remaining_budget_is_preserved(tmp_path):
    case=SimpleNamespace(identity=dict(day='2025-05-01',arm='B2',stage='M1',source_sha=digest('source')),
        case_sha=digest('case'),fresh900_authorized=False)
    old=StageBudget(tmp_path/'old.json',case=case,kind='PLANNING_NATIVE')
    old.calls=[dict(status='FINISHED',Native_Runtime=560.)];old.charge(560.)
    new=fresh_budget(resume,old.path,case=case,kind='PLANNING_NATIVE',destination=tmp_path/'new.json')
    assert new.used()==560 and new.remaining()==340

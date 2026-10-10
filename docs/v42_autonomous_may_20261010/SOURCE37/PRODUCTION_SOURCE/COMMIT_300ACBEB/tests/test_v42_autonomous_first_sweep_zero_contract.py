"""First-sweep requests must carry the repaired deployment's zero contract."""
from pathlib import Path

import pytest

from v42_autonomous import recovery as r
from v42_autonomous import supervisor as s
from v42_autonomous_b2 import pricing_cache


def deployed(tmp_path, monkeypatch):
    code=tmp_path/'immutable';code.mkdir()
    auth=tmp_path/'USER_ZERO_START_RETRY_AUTHORIZATION.json'
    r.atomic(auth,dict(schema='V42_USER_AUTHORIZED_ZERO_START_RETRY_V1',campaign_root=str(tmp_path),
        user_instruction='해결하고 재실행할 때는 0초부터 처음부터 다시 돌려야돼. 알지?',
        scope='VERIFIED_SOURCE_REPAIR_FRESH_DATE_RETRY',restart_from_zero=True,native_budget_seconds=5400,
        B3_native_budget_per_stage_seconds=5400,previous_checkpoint_reuse=False,
        previous_native_budget_carry=False,old_attempts_and_accounting_preserved=True,
        normal_workers_must_continue=True,applies_to_hourly_verified_repairs=True))
    m=dict(schema='V42_AUTONOMOUS_B2_V20',run_id='fresh',attempt_id='fresh_01',source_commit='c'*40,
        execution_SHA='b'*64,input_folders={d:str(tmp_path/'inputs'/d) for d in s.DAYS},
        prior_attempts={},restart_from_zero=True,historical_bound_point_reuse=False,
        reset_authorization=r.record(auth))
    path=tmp_path/'DEPLOYMENT.json';r.atomic(path,m)
    manifest=dict(run_id='fresh',code_root=str(tmp_path/'control'),B2_code_root=str(code),
        B2_worker_module='v42_autonomous_b2.worker',B2_deployment_manifest=r.record(path))
    checked=[]
    monkeypatch.setattr(s.subprocess,'run',lambda command,**kwargs:checked.append((command,kwargs)))
    return m,path,manifest,checked


def seal(path,m,manifest):
    r.atomic(path,m);manifest['B2_deployment_manifest']=r.record(path)


@pytest.mark.parametrize('day,slot',[(s.DAYS[9],1),(s.DAYS[10],2),(s.DAYS[30],3)])
def test_ordinary_birth_satisfies_existing_zero_authority(tmp_path,monkeypatch,day,slot):
    m,path,manifest,checked=deployed(tmp_path,monkeypatch)
    request_path,request,_,_,_=s.b2_request(tmp_path,manifest,day,slot)
    assert request['restart_from_zero'] is True and request['previous_attempts']==[]
    assert request['reset_authorization']==m['reset_authorization']
    assert request['native_budget_seconds']==5400 and request['P2_calls']==0
    assert r.read(request_path)==request and len(checked)==1
    # The unchanged projection guard is exercised on the owned D: test root.
    if tmp_path.drive.upper()=='D:':
        assert pricing_cache._fresh_authorization(request,m,tmp_path)==m['reset_authorization']
        broken=dict(request);broken.pop('restart_from_zero');broken.pop('previous_attempts');broken.pop('reset_authorization')
        with pytest.raises(ValueError,match='FRESH_ZERO_CURRENT_REQUEST_REQUIRED'):
            pricing_cache._fresh_authorization(broken,m,tmp_path)
    before=request_path.read_bytes()
    with pytest.raises(PermissionError,match='NEVER_OVERWRITTEN'):
        s.b2_request(tmp_path,manifest,day,slot)
    assert request_path.read_bytes()==before


@pytest.mark.parametrize('mutation',['missing','tampered','wrong_root','carry','history'])
def test_invalid_zero_deployment_fails_before_request_creation(tmp_path,monkeypatch,mutation):
    m,path,manifest,checked=deployed(tmp_path,monkeypatch)
    if mutation=='missing':m.pop('reset_authorization')
    elif mutation=='tampered':
        auth=Path(m['reset_authorization']['path']);doc=r.read(auth);doc['native_budget_seconds']=6000;r.atomic(auth,doc)
    elif mutation=='wrong_root':
        auth=Path(m['reset_authorization']['path']);doc=r.read(auth);doc['campaign_root']=str(tmp_path/'other');r.atomic(auth,doc)
        m['reset_authorization']=r.record(auth)
    elif mutation=='carry':m['prior_attempts']={'2025-05-10':{'Native_Runtime':12.}}
    else:m['historical_bound_point_reuse']=True
    seal(path,m,manifest)
    with pytest.raises(PermissionError,match='ZERO_START'):
        s.b2_request(tmp_path,manifest,s.DAYS[9],1)
    assert not (tmp_path/'dates').exists() and checked==[]


def test_legacy_cold_deployment_retains_original_request_schema(tmp_path,monkeypatch):
    m,path,manifest,checked=deployed(tmp_path,monkeypatch)
    for key in ('restart_from_zero','reset_authorization','historical_bound_point_reuse'):m.pop(key)
    seal(path,m,manifest)
    _,request,_,_,_=s.b2_request(tmp_path,manifest,s.DAYS[9],1)
    assert all(k not in request for k in ('restart_from_zero','reset_authorization','previous_attempts'))
    assert len(checked)==1

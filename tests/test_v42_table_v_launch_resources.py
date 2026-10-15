"""Public launch/resume/resource negative fixtures; no solver invocation."""
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import numpy as np
import pytest

from v42_integration.a_engine import digest
from v42_integration.m_engine import _write, file_record
from v42_integration import table_v_launch as launch
from v42_integration import table_v_campaign as campaign
from v42_integration import table_v_resources as resources
from v42_integration import table_v_budget as budget_module


def launch_fixture(tmp_path,monkeypatch,day='2025-05-01'):
    import v42_integration.table_v_flex_planning as flex
    monkeypatch.setattr(flex,'require_flex_case',lambda m:m)
    identity=dict(release_sha='exact-source',release_sources=[{'fixture':'public-authorized'}],release_git_sha='exact-git')
    monkeypatch.setattr(launch,'release_identity',lambda:deepcopy(identity))
    root=tmp_path/day;policy=dict(E1=True,FLEX30=True,R1=True,R2='HOLD')
    expected=dict(day=day,source_sha='source-'+day,source_identity=dict(science_sha='science',case_sha=day))
    manifest=dict(day=day,source_sha=expected['source_sha'],identity=expected['source_identity'],science_derivation={'policy':policy})
    _write(root/'INPUTS/FULL_FLEX/TABLE_V_FLEX_CASE_MANIFEST.json',manifest)
    _write(root/'INPUTS/FULL_FLEX/TABLE_V_FLEXIBILITY_POLICY_FREEZE.json',dict(spec=policy))
    authorities={}
    for kind in ('PLANNING','K48'):
        authority=dict(schema=budget_module.SCHEMA,approved=True,
            budget_kind='PLANNING_NATIVE' if kind=='PLANNING' else 'K48_SEPARATE',
            stage_caps_seconds=deepcopy(budget_module.MAIN_CAPS if kind=='PLANNING' else budget_module.K48_CAPS),
            total_limit_seconds=None,total_limit_enabled=False,
            timeout_basis='CUMULATIVE_GUROBI_NATIVE_OPTIMIZE_PER_ARM_STAGE',P2_calls=0,Worker=1,Threads=1,
            authorization_id='NAMED_NATIVE0_'+kind,authorized_ledger_path=str(root/(kind+'_NATIVE_LEDGER.json')),
            human_approval_reference='NAMED_NATIVE0_FIXTURE',source_cases=[expected])
        _write(root/(kind+'_AUTHORIZATION.json'),authority)
        _write(root/(kind+'_NATIVE_LEDGER.json'),dict(authorization_document=authority,
            release_identity={'authorization_sha':digest(authority)},inflight=None,active_stage_context=None))
        authorities[kind]=file_record(root/(kind+'_AUTHORIZATION.json'))
    plan=dict(schema=campaign.SCHEMA,dates=[day],execution_scope='MAY01_VALIDATION',
        Worker=1,Threads=1,P2_calls=0,R2='HOLD',automatic_start=False,actual_slots=96,
        execution_roots={day:str(root)},case_bindings={day:expected},policy_bindings={day:digest(policy)},
        budget_authorizations={day:authorities},**identity)
    def approve():
        document=dict(schema='TABLE_V_EXPLICIT_RELEASE_LAUNCH_APPROVAL_V1',approved=True,
            human_approval_reference='NAMED_NATIVE0_FIXTURE',approved_plan_sha=digest(plan),dates=plan['dates'],
            execution_scope=plan['execution_scope'],approved_release_sha=plan['release_sha'],
            approved_release_git_sha=plan['release_git_sha'],approved_policy_bindings_sha=digest(plan['policy_bindings']),
            approved_budget_bindings_sha=digest(plan['budget_authorizations']))
        _write(tmp_path/'APPROVAL.json',document)
        return dict(launch_authorization=file_record(tmp_path/'APPROVAL.json'))
    return plan,approve,root


def test_release_identity_includes_original_dw_and_mess_sources():
    identity=launch.release_identity();paths={Path(r['path']).as_posix() for r in identity['release_sources']}
    assert identity['release_sha']==digest(identity['release_sources'])
    assert any(p.endswith('/v42_a_stage_phase1/backend.py') for p in paths)
    assert any(p.endswith('/v42_common_mess/engine.py') for p in paths)


def test_exact_may01_approved_route_native0(tmp_path,monkeypatch):
    from v42_integration.table_v_run import require_arm_launch
    plan,approve,root=launch_fixture(tmp_path,monkeypatch);gate=approve()
    campaign._launch_gate(plan,gate)
    assert require_arm_launch(root,dict(plan=plan,gate=gate),actual_slots=96)=='2025-05-01'
    with pytest.raises(PermissionError,match='SLOT_CLI_OPTION'):
        require_arm_launch(root,dict(plan=plan,gate=gate),actual_slots=16)
    plan['run_arms']=['B1','B2','B3'];gate=approve()
    with pytest.raises(PermissionError,match='ARM_NOT_IN_EXACT_APPROVED'):
        require_arm_launch(root,dict(plan=plan,gate=gate),actual_slots=96,arm='B0')


@pytest.mark.parametrize('field,value',[
    ('release_sha','other-source'),('release_git_sha','old-git'),('Worker',2),('Threads',2),
    ('R2','RUN'),('P2_calls',1),('execution_scope','MAY31_APPROVED')])
def test_plan_option_mutation_cannot_bypass_gate(tmp_path,monkeypatch,field,value):
    plan,approve,_=launch_fixture(tmp_path,monkeypatch);gate=approve();plan[field]=value
    with pytest.raises(PermissionError):campaign._launch_gate(plan,gate)


def test_release_policy_budget_and_inflight_rechecked_independently(tmp_path,monkeypatch):
    plan,approve,root=launch_fixture(tmp_path,monkeypatch)
    gate=approve();path=root/'INPUTS/FULL_FLEX/TABLE_V_FLEXIBILITY_POLICY_FREEZE.json'
    _write(path,dict(spec={'R2':'RUN'}))
    with pytest.raises(PermissionError,match='SCIENCE_CASE_SOURCE_POLICY'):launch.validate_launch_identity(plan,gate)
    _write(path,dict(spec=dict(E1=True,FLEX30=True,R1=True,R2='HOLD')))
    path=root/'PLANNING_NATIVE_LEDGER.json';ledger=json.loads(path.read_text());old=path.read_bytes()
    ledger['inflight']={'pid':123};_write(path,ledger)
    with pytest.raises(PermissionError,match='UNRECONCILED'):launch.validate_launch_identity(plan,gate)
    path.write_bytes(old)
    authority=root/'PLANNING_AUTHORIZATION.json';authority.write_bytes(authority.read_bytes()+b' ')
    with pytest.raises(ValueError,match='BYTES_DRIFT'):launch.validate_launch_identity(plan,gate)


def test_later_date_cannot_use_may01_scope_or_only_header_approval(tmp_path,monkeypatch):
    plan,approve,_=launch_fixture(tmp_path,monkeypatch,'2025-05-12')
    with pytest.raises(PermissionError,match='CANNOT_LAUNCH_OTHER_DATES'):
        campaign._launch_gate(plan,approve())
    plan['execution_scope']='MAY31_APPROVED'
    with pytest.raises(KeyError):campaign._launch_gate(plan,approve())


def test_month_gate_rejects_representative_approval_headers_without_raw(tmp_path,monkeypatch):
    plan,approve,_=launch_fixture(tmp_path,monkeypatch);plan['execution_scope']='MAY31_APPROVED'
    monkeypatch.setattr(launch,'validate_launch_identity',lambda *a:None)
    checked=[]
    monkeypatch.setattr(campaign,'validate_arm_full96',lambda *a,**k:checked.append(a[2]))
    plan['actual_policy_bindings']={'2025-05-01':dict.fromkeys(campaign.ARMS,'policy')}
    gate=dict(May01_four_arm_Full96=dict.fromkeys(campaign.ARMS,{}),representative_canary_approvals={})
    day='2025-05-02';plan['case_bindings'][day]={'day':day};plan['policy_bindings'][day]='policy'
    path=tmp_path/'CANARY.json';_write(path,dict(day=day,approved=True,human_approval_reference='fixture',
        source_case=plan['case_bindings'][day],release_sha=plan['release_sha'],release_git_sha=plan['release_git_sha'],
        policy_sha='policy'))
    gate['representative_canary_approvals'][day]=file_record(path)
    with pytest.raises(PermissionError,match='SETTLED_CANARY_RAW'):campaign._launch_gate(plan,gate)
    assert checked==list(campaign.ARMS)


def test_future_representative_canary_needs_separate_approval_and_all_may01_full96(tmp_path,monkeypatch):
    plan,approve,_=launch_fixture(tmp_path,monkeypatch,'2025-05-12')
    plan.update(execution_scope='REPRESENTATIVE_CANARY16_APPROVED',actual_slots=16)
    plan['case_bindings']['2025-05-01']={'day':'2025-05-01'}
    plan['actual_policy_bindings']={'2025-05-01':dict.fromkeys(campaign.ARMS,'policy')}
    gate=approve();gate['May01_four_arm_Full96']=dict.fromkeys(campaign.ARMS,{})
    called=[];monkeypatch.setattr(campaign,'validate_arm_full96',lambda *a,**k:called.append(a[2]))
    campaign._launch_gate(plan,gate)
    assert called==list(campaign.ARMS)
    plan['actual_slots']=96
    with pytest.raises(PermissionError,match='CANARY16_SCOPE'):campaign._launch_gate(plan,approve())
    plan['actual_slots']=16;plan['dates']=['2025-05-03']
    plan['execution_roots']['2025-05-03']=plan['execution_roots']['2025-05-12']
    with pytest.raises(PermissionError,match='CANARY16_SCOPE'):campaign._launch_gate(plan,approve())


def test_serial_arms_also_require_the_shared_gate(tmp_path,monkeypatch):
    from tools.run_v42_table_v_serial_arms import run
    from v42_integration import table_v_run
    monkeypatch.setattr(table_v_run,'verify_adapters',lambda root:None)
    with pytest.raises(PermissionError,match='NO_HEAVY'):
        run(tmp_path,dict(execution_scope='PREPARED_ONLY'),{},['B1','B2','B3'])
    assert not (tmp_path/'SERIAL_ARM_RUN.json').exists()


def test_planning_only_option_cannot_route_table_v_through_legacy_gate(tmp_path):
    from v42_integration.release_production_campaign import run_planning_p1
    with pytest.raises(PermissionError,match='TABLE_V_REQUIRES_FULL_ARM'):
        run_planning_p1(dict(schema=campaign.SCHEMA),authorization={},folder=tmp_path,budget_ledger={})
    plan=tmp_path/'PLAN.json';approval=tmp_path/'AUTH.json';ledgers=tmp_path/'LEDGERS.json'
    _write(plan,dict(schema=campaign.SCHEMA));_write(approval,{});_write(ledgers,{})
    output=tmp_path/'NEVER_CREATED'
    script=Path(__file__).resolve().parents[1]/'tools/run_v42_production_campaign.py'
    result=subprocess.run([sys.executable,str(script),'--execute','--planning-only','--plan',str(plan),
        '--approval',str(approval),'--output',str(output),'--budget-ledger',str(ledgers)],capture_output=True,text=True)
    assert result.returncode!=0 and 'TABLE_V_REQUIRES_FULL_ARM' in result.stderr
    assert not output.exists()


@pytest.mark.parametrize('day',['2025-05-01','2025-05-12'])
def test_cli_and_direct_api_deny_without_authority_before_side_effects(tmp_path,day):
    from v42_integration.table_v_run import run_arm
    _write(tmp_path/'INPUTS/FULL_FLEX/TABLE_V_FLEX_CASE_MANIFEST.json',dict(day=day))
    with pytest.raises(PermissionError,match='PRODUCTION_LAUNCH_APPROVAL'):
        run_arm('B2',tmp_path)
    script=Path(__file__).resolve().parents[1]/'tools/run_v42_table_v.py'
    result=subprocess.run([sys.executable,str(script),'B2','--output',str(tmp_path),'--day',day,
        '--actual-slots','16'],capture_output=True,text=True)
    assert result.returncode!=0 and 'PRODUCTION_LAUNCH_APPROVAL' in result.stderr
    assert not (tmp_path/'B2').exists()


def resume_fixture(tmp_path):
    expected=dict(day='2025-05-01',source_sha='current',source_identity={'case_sha':'current'})
    outcome=tmp_path/'ARM_OUTCOME.json'
    _write(outcome,dict(day=expected['day'],arm='B1',status='FULL_PASS'))
    np.savez_compressed(tmp_path/'ACTUAL.npz',trace=np.zeros((96,12)))
    (tmp_path/'native.log').write_bytes(b'Native\x00log\xff\n')
    row=dict(result=dict(source_case=expected,status='FULL_PASS',outcome=file_record(outcome)),
        raw_records=[file_record(p) for p in sorted(tmp_path.iterdir())])
    executor=campaign.RealTableVExecutor(dict(case_bindings={expected['day']:expected}))
    return executor,row


def test_actual_npz_log_resume_pass_and_raw_ledger_bytes_preserved(tmp_path):
    executor,row=resume_fixture(tmp_path)
    before={p:p.read_bytes() for p in tmp_path.iterdir()}
    executor.restore('2025-05-01','B1',row)
    assert {p:p.read_bytes() for p in tmp_path.iterdir()}==before


@pytest.mark.parametrize('name,mutation',[
    ('ACTUAL.npz','tamper'),('ACTUAL.npz','missing'),('native.log','tamper'),('native.log','missing'),
    ('ARM_OUTCOME.json','tamper'),('ARM_OUTCOME.json','missing')])
def test_resume_binary_or_json_missing_and_tamper_fail(tmp_path,name,mutation):
    executor,row=resume_fixture(tmp_path);path=tmp_path/name
    if mutation=='tamper':path.write_bytes(path.read_bytes()+b'corrupt')
    else:path.unlink()
    before={p:p.read_bytes() for p in tmp_path.iterdir()}
    with pytest.raises((ValueError,FileNotFoundError)):executor.restore('2025-05-01','B1',row)
    assert {p:p.read_bytes() for p in tmp_path.iterdir()}==before


def test_resume_json_scalar_rejected_even_with_matching_bytes(tmp_path):
    executor,row=resume_fixture(tmp_path);path=tmp_path/'scalar.json';path.write_text('42')
    row['raw_records'].append(file_record(path))
    with pytest.raises(ValueError,match='JSON_STRUCTURE'):executor.restore('2025-05-01','B1',row)


def live_snapshot():
    return dict(memory=dict(AvailableMBytes=20000,PercentCommittedBytesInUse=20,
        CommitLimit=1000000,CommittedBytes=200000),process={'RSS_bytes':100000},workers=[])


def test_serial_launcher_foreign_pid_is_detected_during_model_build(monkeypatch):
    import psutil
    worker=SimpleNamespace(pid=os.getpid()+100,info=dict(name='python.exe',
        cmdline=['python','D:/repo/tools/run_v42_table_v_serial_arms.py','--arms','B1','B2','B3']))
    monkeypatch.setattr(psutil,'process_iter',lambda fields:[worker])
    snapshot=resources._snapshot()
    assert snapshot['workers']==[dict(pid=worker.pid,name='python.exe',heavy_worker=True)]


@pytest.mark.parametrize('fault',['ram','commit','rss','foreign_pid','lock','missing_metric'])
def test_m_k48_live_prebuild_resource_denials_recorded(tmp_path,monkeypatch,fault):
    from v42_integration.table_v_run import current_build_admission
    sample=live_snapshot();budget=SimpleNamespace(path=tmp_path/'ledger.json',worker_lock=tmp_path/'worker.lock',authorization={})
    if fault=='ram':sample['memory']['AvailableMBytes']=8191
    elif fault=='commit':sample['memory']['CommittedBytes']=800000
    elif fault=='rss':sample['process']['RSS_bytes']=None
    elif fault=='foreign_pid':sample['workers']=[dict(pid=os.getpid()+100,heavy_worker=True)]
    elif fault=='lock':budget.worker_lock.write_text('{}')
    else:sample['memory']['PercentCommittedBytesInUse']=None
    monkeypatch.setattr(resources,'_snapshot',lambda:sample)
    for operation in ('CURRENT_M_NATIVE0_BUILD','CURRENT_K48_NATIVE_BUILD'):
        with pytest.raises(RuntimeError,match='RESOURCE_ADMISSION_DENIED'):
            current_build_admission(budget,arm='B2',stage='M1',operation=operation)
    receipts=list((tmp_path/'RESOURCE_ADMISSIONS').glob('*.json'))
    assert len(receipts)==2 and all(json.loads(p.read_text())['status']=='DENIED' for p in receipts)
    assert not budget.path.exists()


def test_pre_native_race_rechecked_without_native_or_double_charge(tmp_path,monkeypatch):
    from test_v42_table_v_budget import setup,context
    b,_,history,Model=setup(tmp_path,monkeypatch);samples=iter([live_snapshot(),live_snapshot()])
    def snapshot():
        value=next(samples)
        # The second check happens after the durable owned lock is acquired.
        if b.worker_lock.exists():value['memory']['AvailableMBytes']=100
        return value
    monkeypatch.setattr(resources,'_snapshot',snapshot)
    model=Model();model.Runtime=1234.;model.Status=2
    old=[p.read_bytes() for p in history]
    with b.arm_context('B2'),context(b,'B2','M1'),b.capture_native_methods():
        with pytest.raises(RuntimeError,match='RESOURCE_ADMISSION_DENIED'):
            b.solve(model,label='RELEASE_P1:M1:FIXTURE',cap=1800.)
    assert b.used()==0. and b.calls[-1]['native_execution_entered'] is False
    assert b.calls[-1]['Native_Runtime']==0. and b.document['inflight'] is None
    assert not b.worker_lock.exists() and [p.read_bytes() for p in history]==old


@pytest.mark.parametrize('field,value',[('pid',-1),('nonce',''),('ledger_path','foreign'),('authorization_sha','foreign')])
def test_immediate_native_owned_lock_pid_and_identity_required(tmp_path,field,value):
    b=SimpleNamespace(path=tmp_path/'ledger.json',worker_lock=tmp_path/'worker.lock',authorization={'approved':'fixture'})
    owner=dict(schema='V42_RELEASE_OWNED_LOCK_V1',kind='HEAVY_WORKER',pid=os.getpid(),nonce='exact',
        ledger_path=str(b.path.resolve()),authorization_sha=digest(b.authorization))
    owner[field]=value;_write(b.worker_lock,owner);before=b.worker_lock.read_bytes()
    with pytest.raises(RuntimeError,match='PID_OR_OWNERSHIP'):
        resources.admit_resources(b,phase='IMMEDIATELY_BEFORE_NATIVE_OPTIMIZE',owned_lock=True,snapshot=live_snapshot())
    assert b.worker_lock.read_bytes()==before

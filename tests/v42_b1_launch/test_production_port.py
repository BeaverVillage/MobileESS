import copy
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from v42_b1_production.common import Config,STAGES,identity,atomic,read,record,admission,ROOT,CHECKER
from v42_b1_production.worker import valid_receipt,physical_validation,guard_gurobi
from v42_b1_production.coordinator import Campaign,process_identity,same_process,atomic_csv
from v42_b1_production.telemetry import is_heavy_command


@pytest.mark.parametrize('change',[dict(arm='B2'),dict(arm='B3'),dict(B1_DAY_WORKERS=2),dict(GUROBI_THREADS=2),
    dict(A1_TIME_LIMIT=1799),dict(MESS_OFF=False),dict(ML_OFF=True),dict(AUTO_ADVANCE=True)])
def test_production_scope(change):
    with pytest.raises(PermissionError): Config(**change)


def test_resource_wait_and_automatic_resume(monkeypatch):
    c=Campaign.__new__(Campaign); rows=iter(['WAIT_RESOURCE','WAIT_RESOURCE','SAFE'])
    c.resource_state=lambda: next(rows); slept=[]
    monkeypatch.setattr('v42_b1_production.coordinator.time.sleep',lambda n:slept.append(n))
    c.wait_admission('2025-05-01','A1')
    assert len(slept)==2 and c.status=='WAIT_RESOURCE'


@pytest.mark.parametrize('change,expected',[(dict(available_GiB=.9),'HARD_GUARD'),
    (dict(commit_percent=95),'HARD_GUARD'),(dict(catastrophic_sustained_paging=True),'HARD_GUARD'),
    (dict(foreign_heavy=[dict(PID=999)]),'WAIT_RESOURCE'),({},'SAFE')])
def test_guards(change,expected):
    row=dict(available_GiB=5,commit_percent=60,catastrophic_sustained_paging=False,foreign_heavy=[])
    assert admission(dict(row,**change))==expected


def test_real_heavy_classifier_exempts_verification():
    dll=['C:/gurobi130.dll']; rss=2**30
    assert is_heavy_command(['python.exe','-m','v42_dw_accelerated.cg'],rss,dll,1)
    assert is_heavy_command(['python.exe','-m','v42_single_thread','a1'],rss,dll,1)
    for cmd in (['python.exe','-m','pytest'],['python.exe','-m','v42_dw_accelerated.base'],['python.exe','-m','v42_orchestrator','mock']):
        assert not is_heavy_command(cmd,rss,dll,1)
    assert not is_heavy_command(['python.exe','codex.py'],rss,[],1)
    assert not is_heavy_command(['python.exe','-m','v42_dw_accelerated.cg'],rss,dll,0)


def test_completed_stage_recovery_reuses_only_matching_receipt(tmp_path):
    p=tmp_path/'output.json';atomic(p,dict(real=True));expected=dict(run_id='new',arm='B1',day='2025-05-01',stage='ACTUAL')
    r=dict(PASS=True,mode='B1_PRODUCTION',identity=expected,files=[record(p)])
    assert valid_receipt(r,expected,tmp_path)
    assert not valid_receipt(r,dict(expected,run_id='old'),tmp_path)
    assert not valid_receipt(dict(r,mode='MOCK_ONLY'),expected,tmp_path)
    atomic(p,dict(real=False));assert not valid_receipt(r,expected,tmp_path)


def test_pid_creation_command_identity(monkeypatch):
    import os
    row=process_identity(os.getpid());assert same_process(row)
    assert not same_process(dict(row,creation_time=row['creation_time']-4))
    assert not same_process(dict(row,command=['foreign']))
    assert not same_process(dict(row,PID=2147483647))


def test_fresh_convergence_is_not_day_pass():
    row=dict(converged=True,summary=dict(convergence_count=96,voltage_violation_count=0,line_current_violation_count=0,
        transformer_current_violation_count=0,transformer_kva_violation_count=0),checker_SHA=CHECKER,
        all_MESS_PQ_zero=True,NormalAmps_current=True,Planning_tap_replay=False,
        Actual_reoptimization=0,local_PQ_repair=0,global_PQ_repair=0)
    assert physical_validation(row)
    for key in ('voltage_violation_count','line_current_violation_count','transformer_current_violation_count','transformer_kva_violation_count'):
        bad=copy.deepcopy(row);bad['summary'][key]=1;assert not physical_validation(bad)
    assert not physical_validation(dict(row,Planning_tap_replay=True))
    assert not physical_validation(dict(row,Actual_reoptimization=1))


def test_post_freeze_native_optimizer_firewall(monkeypatch):
    import gurobipy as gp
    original=gp.Model
    try:
        calls=guard_gurobi('ACTUAL'); m=gp.Model();assert m.Params.Threads==1
        with pytest.raises(PermissionError):m.optimize()
        assert calls==[]
        with pytest.raises(PermissionError):m.setParam('Threads',2)
        m.dispose()
    finally: gp.Model=original


def test_atomic_csv_and_json(tmp_path):
    p=tmp_path/'state.json';atomic(p,dict(state='A'));atomic(p,dict(state='B'));assert read(p)==dict(state='B')
    atomic_csv(tmp_path/'day.csv',[dict(day='2025-05-01',status='PASS')],('day','status'))
    assert (tmp_path/'day.csv').read_text()=='day,status\n2025-05-01,PASS\n'
    assert not list(tmp_path.glob('*.tmp'))


def test_monitor_is_readonly_and_exact_title():
    source=(ROOT/'tools/v42/monitor_b1_may.ps1').read_text(encoding='utf-8-sig')
    assert "WindowTitle='Mobile ESS V42 May B1 Production Monitor'" in source
    for token in ('Set-Content','Out-File','Start-Process','Stop-Process','schtasks','Start-ScheduledTask','Register-ScheduledTask'):
        assert token not in source
    assert 'Read-AtomicSnapshot' in source and 'orchestrator_creation_time_utc' in source


def test_monitor_liveness_pass_disappearance_failure_retention():
    source=ROOT/'tools/v42/monitor_b1_may.ps1'
    script=f". '{source}' -LibraryOnly; " + r'''
    $m=[pscustomobject]@{orchestrator_pid=123;heartbeat_timestamp_utc=[DateTime]::UtcNow.ToString('o');orchestrator_creation_time_utc=[DateTime]::UtcNow.ToString('o');orchestrator_command_match_tokens=@('production','ROOT');completed_days=@('2025-05-01');running_days=@('2025-05-02');failed_days=@('2025-05-03')}
    $p=[pscustomobject]@{CreationDate=[DateTime]::UtcNow;CommandLine='production ROOT'}
    $good=Get-CampaignLiveness $m -ProcessInfo $p
    $m.heartbeat_timestamp_utc=[DateTime]::UtcNow.AddSeconds(-60).ToString('o');$stale=Get-CampaignLiveness $m -ProcessInfo $p
    $p.CommandLine='foreign ROOT';$dead=Get-CampaignLiveness $m -ProcessInfo $p
    $details=@{'2025-05-01'=[pscustomobject]@{status='PASS';case='B1';stage='VALIDATION_FREEZE'};'2025-05-02'=[pscustomobject]@{status='RUNNING';case='B1';stage='A1'};'2025-05-03'=[pscustomobject]@{status='FAIL';case='B1';stage='ACTUAL';error='failure'}}
    $fail=@{};$v=Get-MonitorView $m $details $fail $good
    $m.failed_days=@();$v2=Get-MonitorView $m $details $fail $good
    [pscustomobject]@{good=$good.State;stale=$stale.State;dead=$dead.State;rows=@($v.Rows.Date);failures=$v2.Failures.Count}|ConvertTo-Json -Compress
    '''
    p=subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-Command',script],capture_output=True,text=True)
    assert p.returncode==0,p.stderr
    result=json.loads(p.stdout)
    assert (result['good'],result['stale'],result['dead'])==('RUNNING','STALE','DEAD')
    assert '2025-05-01' not in result['rows'] and result['failures']==1


def test_a1_stage_identity_rejects_old_arm_and_wrong_stage():
    f=dict(days=['2025-05-01'],run_id='new',Git_SHA='a'*40,scientific_SHA='b'*64,day_input_SHA={'2025-05-01':'c'*64})
    assert identity(f,'2025-05-01','A1')['arm']=='B1'
    with pytest.raises(PermissionError):identity(f,'2025-05-02','A1')
    with pytest.raises(PermissionError):identity(f,'2025-05-01','M1')


def test_scientific_failure_blocks_dependents_and_continues_independent_day(tmp_path):
    c=Campaign.__new__(Campaign)
    c.root=tmp_path;c.freeze=dict(days=['2025-05-01','2025-05-02'],run_id='UNIT_TEST_ONLY')
    c.state=dict(stages={d+'/'+s:dict(status='NOT_RUN') for d in c.freeze['days'] for s in STAGES})
    c.verify_sources=lambda:None;c.checkpoint=lambda:None;c.publish=lambda:None
    c.stop=SimpleNamespace(set=lambda:None);c.thread=SimpleNamespace(join=lambda **kw:None)
    c.telemetry=SimpleNamespace(close=lambda:None);c.lock=SimpleNamespace(close=lambda:None)
    calls=[]
    def stage(day,name):
        calls.append((day,name));passed=day!='2025-05-01'
        c.state['stages'][day+'/'+name].update(status='PASS' if passed else 'FAIL',failure_kind='SCIENTIFIC')
        return passed
    c.run_stage=stage
    assert c.run()==0
    assert calls==[('2025-05-01','A1')]+[('2025-05-02',s) for s in STAGES]
    assert c.state['stages']['2025-05-01/ACTUAL']['status']=='BLOCKED_BY_FAILED_STAGE'
    assert read(tmp_path/'B1_CAMPAIGN_FINAL.json')['scientific_PASS'] is False


def test_source_freeze_configuration_and_manifest_hash_are_bound():
    from dataclasses import asdict
    from v42_b1_production.common import verify_freeze,digest,BASE,VERSION
    config=asdict(Config());days=[f'2025-05-{i:02d}' for i in range(1,32)]
    f=dict(mode='B1_PRODUCTION',configuration=config,checker_SHA=CHECKER,base_Git_SHA=BASE,
           days=days,stage_order=list(STAGES),run_id='B1_202505_UNIT_TEST_ONLY',sources=[])
    f['scientific_SHA']=digest(dict(configuration=config,checker=CHECKER,version=VERSION,sources=[],stage_order=list(STAGES),days=days))
    assert verify_freeze(f,config)
    bad=copy.deepcopy(f);bad['sources']=[dict(path='different')]
    with pytest.raises(PermissionError):verify_freeze(bad,config)
    bad=copy.deepcopy(f);bad['configuration']['CATASTROPHIC_PAGES_INPUT_PER_SECOND']=999999
    with pytest.raises(PermissionError):verify_freeze(bad,config)

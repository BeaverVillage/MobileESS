from pathlib import Path
from datetime import datetime,timezone,timedelta
from types import SimpleNamespace
import copy, json, os, subprocess, sys, time
import pytest
from contextlib import nullcontext
from v42_may_campaign.common import atomic,read,sha,process,same_process,LockBusy
from v42_may_campaign.coordinator import AXIS,TERMINAL
from v42_may_maintenance import check,session,monitor,resolution


def test_runtime_uses_dispatch_clock_not_stale_progress():
    request=dict(started_UTC=(datetime.now(timezone.utc)-timedelta(seconds=600)).isoformat())
    ledger=dict(calls=[dict(Native_Runtime=13.,effective_TimeLimit=42.,component='P1')],
        measured_Native_Runtime=13.,P2_calls=0,wall_ceiling_seconds=5400,Native_ceiling_seconds=5400,wall_seconds=3)
    audit=check.runtime_audit(ledger,request,True)
    assert audit['PASS'] and 599<audit['actual_dispatch_wall_seconds']<602
    assert 4798<audit['remaining_wall_seconds']<4801 and audit['Native_Runtime_completed']==13


@pytest.mark.parametrize('mutation',[dict(measured_Native_Runtime=14),dict(P2_calls=1),dict(Native_ceiling_seconds=5401),dict(measured_Native_Runtime=6000)])
def test_ledger_corruption_never_passes(mutation):
    ledger=dict(calls=[dict(Native_Runtime=13,effective_TimeLimit=42,component='P1')],
        measured_Native_Runtime=13,P2_calls=0,wall_ceiling_seconds=5400,Native_ceiling_seconds=5400)
    ledger.update(mutation)
    assert check.runtime_audit(ledger,{},False)['PASS'] is False


def test_source_audit_reports_drift_without_modifying_file(tmp_path):
    p=tmp_path/'frozen.py';p.write_text('old');m=dict(sources={'frozen.py':sha(p)},source_HEAD='old')
    assert check.source_audit(tmp_path,m)['PASS']
    p.write_text('changed');before=p.read_bytes()
    assert not check.source_audit(tmp_path,m)['PASS'] and p.read_bytes()==before


@pytest.fixture
def case(tmp_path,monkeypatch):
    campaign=tmp_path/'project/runtime/v42_may_campaign/run';campaign.mkdir(parents=True)
    manifest=dict(run_id='test',source_HEAD='frozen',sources={},input_folders={},tasks=dict(coordinator='own_C',monitor='own_M',watchdog='own_W'))
    cp=dict(run_id='test',state='RUNNING',dates={a+'/'+d:dict(arm=a,day=d,status='PENDING',attempts=0) for a,d in AXIS})
    identity=dict(PID=123,created=1,command=['test'],parent=4)
    atomic(campaign/'CAMPAIGN_MANIFEST.json',manifest);atomic(campaign/'CHECKPOINT.json',cp)
    atomic(campaign/'COORDINATOR_HEARTBEAT.json',dict(process=identity,timestamp_UTC=check.now()))
    atomic(campaign/'MONITOR_PROCESS.json',identity)
    monkeypatch.setattr(check,'same_process',lambda x:bool(x and x.get('PID')))
    monkeypatch.setattr(check.psutil,'process_iter',lambda *args:[])
    monkeypatch.setattr(check.psutil,'Process',lambda pid:SimpleNamespace(cpu_times=lambda:SimpleNamespace(user=10,system=2),memory_info=lambda:SimpleNamespace(rss=100)))
    class HTTP:
        status=200
        def __enter__(self):return self
        def __exit__(self,*args):pass
    monkeypatch.setattr(check.urllib.request,'urlopen',lambda *args,**kw:HTTP())
    def inspect():return check.inspect(campaign,source_checker=lambda *args:dict(PASS=True),
        task_reader=lambda name:dict(name=name,state='Running'),owner_reader=lambda p:dict(PASS=True),manifest_validator=lambda p:True)
    return campaign,manifest,cp,inspect


def add_worker(campaign,manifest,cp,arm,day,slot,pid):
    name=arm+'/'+day;attempt=campaign/'dates'/arm/day;attempt.mkdir(parents=True)
    folder=campaign/'inputs'/arm/day;folder.mkdir(parents=True);atomic(folder/'NATIVE_INPUT.json',dict(arm=arm,day=day))
    manifest['input_folders'][name]=str(folder);atomic(campaign/'CAMPAIGN_MANIFEST.json',manifest)
    request=dict(run_id='test',arm=arm,day=day,root=str(campaign),worker_slot=slot,
        manifest_SHA=sha(campaign/'CAMPAIGN_MANIFEST.json'),input_folder=str(folder),worker_command=['test'],started_UTC=check.now())
    request.update({k:str(attempt/v) for k,v in [('output','output'),('progress','progress.json'),('result','RESULT.json'),('error','error.json')]})
    atomic(attempt/'request.json',request)
    identity=dict(PID=pid,created=1,command=['test'],parent=4)
    atomic(attempt/'HEARTBEAT.json',dict(worker=identity,identity=dict(arm=arm,day=day),timestamp_UTC=check.now()))
    atomic(attempt/'progress.json',dict(phase='MODEL_BUILD',timestamp_UTC=(datetime.now(timezone.utc)-timedelta(hours=2)).isoformat(),Native_Runtime=0))
    atomic(attempt/'NATIVE_RUNTIME_LEDGER.json',dict(calls=[],measured_Native_Runtime=0,P2_calls=0,wall_ceiling_seconds=5400,Native_ceiling_seconds=5400))
    actives=check.optional(campaign/'ACTIVES.json',dict(run_id='test',workers={}))
    actives['workers'][name]=dict(arm=arm,day=day,worker_slot=slot,worker=identity,request=str(attempt/'request.json'))
    atomic(campaign/'ACTIVES.json',actives)
    cp['dates'][name].update(status='RUNNING',attempts=1,request=str(attempt/'request.json'));atomic(campaign/'CHECKPOINT.json',cp)
    # A frozen manifest normally never changes. Update all fixture requests to
    # this final fixture-only SHA as more distinct fake workers are added.
    for r in campaign.glob('dates/*/*/request.json'):
        data=read(r);data['manifest_SHA']=sha(campaign/'CAMPAIGN_MANIFEST.json');atomic(r,data)


def test_long_model_build_and_zero_cpu_are_not_error(case):
    campaign,m,cp,inspect=case;add_worker(campaign,m,cp,'B1','2025-05-01',1,101)
    health=inspect()
    assert health['issues']==[] and health['workers'][0]['progress_age_seconds']>7000
    assert health['workers'][0]['low_CPU_or_unchanged_gap_is_not_error']


def test_early_b2_and_duplicate_slot_detected(case):
    c,m,cp,inspect=case
    add_worker(c,m,cp,'B2','2025-05-01',1,101);add_worker(c,m,cp,'B2','2025-05-02',1,102)
    codes={i['code'] for i in inspect()['issues']}
    assert 'B2_STARTED_BEFORE_B1_TERMINAL' in codes and 'DUPLICATE_DATE_OR_SLOT' in codes


def test_three_b2_after_terminal_failures_is_valid(case):
    c,m,cp,inspect=case
    for row in cp['dates'].values():
        if row['arm']=='B1':row.update(status='TIME_LIMIT_NO_VALID_INCUMBENT',attempts=1)
    for i in range(1,4):add_worker(c,m,cp,'B2',f'2025-05-{i:02d}',i,100+i)
    health=inspect();assert health['issues']==[] and health['B1']['completed']==31 and len(health['workers'])==3


def test_active_path_mixing_is_rejected_without_recovery(case):
    c,m,cp,inspect=case;add_worker(c,m,cp,'B1','2025-05-01',1,101)
    p=c/'dates/B1/2025-05-01/request.json';r=read(p);r['result']=str(c/'dates/B2/2025-05-01/RESULT.json');atomic(p,r)
    before=p.read_bytes();health=inspect()
    assert any(i['code']=='ACTIVE_WORKER_REQUEST_IDENTITY_MISMATCH' for i in health['issues'])
    assert p.read_bytes()==before


def test_corrupt_checkpoint_is_evidence_not_reset(case):
    c,m,cp,inspect=case;(c/'CHECKPOINT.json').write_text('{broken')
    h=inspect();assert not h['checkpoint_valid'] and h['issues']
    assert (c/'CHECKPOINT.json').read_text()=='{broken'


def test_recovery_never_starts_task_for_live_coordinator(case,monkeypatch):
    c,m,cp,inspect=case;h=inspect()
    monkeypatch.setattr(check,'run_task',lambda name:pytest.fail('healthy host restart'))
    assert check.recover_dead_hosts(c,h)==[]


def test_source_or_identity_failure_blocks_recovery(case,monkeypatch):
    c,m,cp,inspect=case;h=inspect();h['source_audit']['PASS']=False
    monkeypatch.setattr(check,'run_task',lambda name:pytest.fail('unverified recovery'))
    assert check.recover_dead_hosts(c,h)[0]['action']=='RECOVERY_BLOCKED'


def test_entire_maintenance_turn_os_lock_and_parent_exit(tmp_path,monkeypatch):
    storage=tmp_path/'sessions';monkeypatch.setenv('CODEX_THREAD_ID','test_owner')
    helper=subprocess.run([sys.executable,'-B','-c',
        'import json;from v42_may_maintenance.session import begin;print(json.dumps(begin('+repr(str(storage))+',"test_owner")))'],
        capture_output=True,text=True,cwd=Path(__file__).resolve().parents[1],check=True)
    first=json.loads(helper.stdout)
    try:
        assert first['status']=='ACTIVE' and same_process(first['guardian'])
        second=session.begin(storage,'test_owner2')
        assert second['status']=='SKIP_PREVIOUS_MAINTENANCE_ACTIVE'
        with pytest.raises(LockBusy):
            with session.check_lock(storage):pass
        with session.check_lock(storage,first['token']):assert session.valid(storage,first['token'])
        # begin's actual launching subprocess has exited; guardian retains the OS
        # lock and its exact PID identity across changing heartbeat samples.
        deadline=time.monotonic()+5;stamps=set()
        while time.monotonic()<deadline and len(stamps)<2:
            hb=check.optional(storage/'SESSION_HEARTBEAT.json');stamps.add(hb.get('UTC'))
            time.sleep(.05)
        stamps.discard(None);assert len(stamps)>=2 and same_process(first['guardian'])
    finally:
        session.end(storage,first['token'])


def test_other_owner_cannot_release_without_authoritative_terminal_evidence(tmp_path,monkeypatch):
    storage=tmp_path/'guard';monkeypatch.setenv('CODEX_THREAD_ID','owner1');first=session.begin(storage,'owner1')
    try:
        monkeypatch.setenv('CODEX_THREAD_ID','owner2')
        with pytest.raises(PermissionError):session.end(storage,first['token'])
        proof=tmp_path/'owner.json';atomic(proof,dict(owner_thread_id='owner1',owner_status='running',source='mcp__codex_app__read_thread',response={'status':'running'}))
        with pytest.raises(PermissionError):session.end(storage,first['token'],proof)
        assert same_process(first['guardian'])
    finally:
        monkeypatch.setenv('CODEX_THREAD_ID','owner1');session.end(storage,first['token'])


def test_readonly_monitor_elapsed_time_and_maintenance_section(tmp_path):
    attempt=tmp_path/'date';attempt.mkdir();atomic(attempt/'NATIVE_RUNTIME_LEDGER.json',dict(measured_Native_Runtime=0,inflight=None))
    value=dict(workers=[dict(arm='B1',worker_slot=1,request=str(attempt/'request.json'),started_UTC=(datetime.now(timezone.utc)-timedelta(seconds=100)).isoformat(),wall_seconds=1)],worker_slots=[])
    fixed=monitor.enrich(tmp_path,value)
    assert fixed['wall_seconds']>=99 and fixed['Native_Runtime_seconds']==0
    assert 'maintenance-last' in monitor.SECTION and '/api/maintenance' in monitor.SCRIPT


def test_builtin_heuristics_are_explicitly_enabled_without_policy_change(case):
    c,m,cp,inspect=case;policy=c.parents[2]/'docs/v42_a_stage_fast_active_domain_20261007/SOLVER_POLICY.json'
    policy.parent.mkdir(parents=True);atomic(policy,dict(parameters=dict(Heuristics=.05)))
    original=policy.read_bytes();audit=inspect()['heuristic_audit']
    assert audit['builtin_MIP_heuristics_enabled'] is True
    assert audit['compatible_with_zero_builtin_heuristics'] is False
    assert audit['active_worker_parameter_changes']==0 and not audit['new_heuristic_added']
    assert audit['policy_candidate_validation'].startswith('NOT_TESTED') and policy.read_bytes()==original


def test_terminal_triage_persists_and_completion_requires_evidence(case,tmp_path,monkeypatch):
    c,m,cp,inspect=case;storage=tmp_path/'reports';health=inspect()
    monkeypatch.setattr(check.subprocess,'check_output',lambda *args,**kw:'test_head')
    for row in health['date_rows'].values():row['status']='PASS'
    failure=health['date_rows']['B1/2025-05-01'];failure.update(status='TIME_LIMIT_NO_VALID_INCUMBENT',result_SHA='original')
    health['B1']['completed']=31;health['B2']['completed']=31
    state=check.write_reports(storage,health,{},[])
    assert not state['completion_ready'] and len(state['pending_issues'])==1
    key=next(iter(state['pending_issues']));state2=check.write_reports(storage,health,health,[])
    assert state2['pending_issues'][key]['status']=='OPEN' and not state2['completion_ready']
    assert len(list(check.csv.DictReader((storage/'FAILURE_ROOT_CAUSE.csv').open(encoding='utf-8'))))==1
    assert read(storage/'HEURISTICS_POLICY_COMPATIBILITY_AUDIT.json')['active_worker_parameter_changes']==0
    state2['pending_issues'][key].update(status='RESOLVED_CLASSIFIED',resolution={'sha256':'test_evidence'})
    atomic(storage/'MAINTENANCE_STATE.json',state2)
    assert check.write_reports(storage,health,health,[])['completion_ready']


def test_pending_version_release_prevents_automation_completion(case,tmp_path,monkeypatch):
    c,m,cp,inspect=case;storage=tmp_path/'pending';storage.mkdir();health=inspect()
    monkeypatch.setattr(check.subprocess,'check_output',lambda *args,**kw:'test_head')
    for row in health['date_rows'].values():row['status']='PASS'
    health['B1']['completed']=31;health['B2']['completed']=31
    atomic(storage/'MAINTENANCE_STATE.json',dict(pending_releases=['unvalidated_version']))
    assert not check.write_reports(storage,health,{},[])['completion_ready']


def test_dead_coordinator_recovery_validates_then_starts_only_host(case,monkeypatch):
    c,m,cp,inspect=case;h=inspect();h['coordinator'].update(alive=False,process={})
    h['issues']=[dict(code='COORDINATOR_DEAD')];events=[]
    import v42_may_campaign.common as original_common
    import v42_may_campaign.coordinator as original_coordinator
    monkeypatch.setattr(original_common,'verify_manifest',lambda *args:events.append('manifest'))
    monkeypatch.setattr(original_coordinator,'load_checkpoint',lambda *args:cp)
    monkeypatch.setattr(original_coordinator,'recovery_requests',lambda *args:events.append('checkpoint_and_peers'))
    monkeypatch.setattr(check,'reuse_registered_task',lambda *args,**kw:events.append('registration'))
    monkeypatch.setattr(check,'run_task',lambda name:events.append(name))
    before=(c/'CHECKPOINT.json').read_bytes();actions=check.recover_dead_hosts(c,h)
    assert events==['manifest','checkpoint_and_peers','registration','own_C']
    assert [a['action'] for a in actions]==['START_VERIFIED_DEAD_COORDINATOR']
    assert (c/'CHECKPOINT.json').read_bytes()==before and not actions[0]['healthy_workers_terminated']


def test_original_recovery_rejection_starts_no_os_task(case,monkeypatch):
    c,m,cp,inspect=case;h=inspect();h['coordinator'].update(alive=False,process={});h['issues']=[dict(code='COORDINATOR_DEAD')]
    import v42_may_campaign.common as original_common
    import v42_may_campaign.coordinator as original_coordinator
    monkeypatch.setattr(original_common,'verify_manifest',lambda *args:True)
    monkeypatch.setattr(original_coordinator,'load_checkpoint',lambda *args:cp)
    def reject(*args):raise PermissionError('unverified peer identity')
    monkeypatch.setattr(original_coordinator,'recovery_requests',reject)
    monkeypatch.setattr(check,'run_task',lambda name:pytest.fail('unsafe OS task restart'))
    with pytest.raises(PermissionError,match='unverified peer'):check.recover_dead_hosts(c,h)


def test_root_cause_resolution_preserves_result_and_csv_evidence(tmp_path,monkeypatch):
    storage=tmp_path/'resolution';storage.mkdir();original=tmp_path/'RESULT.json';atomic(original,dict(status='TIME_LIMIT_NO_VALID_INCUMBENT'))
    receipt=original.read_bytes();proof=tmp_path/'proof.json';atomic(proof,dict(root_cause='Expected finite budget exhaustion',
        original_results_preserved=True,source_evidence=[dict(path=str(original),sha256=sha(original))]))
    cause=dict(arm='B1',day='2025-05-01',result_SHA=sha(original),status='TIME_LIMIT_NO_VALID_INCUMBENT')
    atomic(storage/'MAINTENANCE_STATE.json',dict(pending_issues={'test':dict(kind='TERMINAL_TRIAGE',issue=cause,status='OPEN')}))
    check.table(storage/'FAILURE_ROOT_CAUSE.csv',[cause],list(cause))
    monkeypatch.setattr(resolution,'check_lock',lambda *args:nullcontext())
    assert resolution.resolve(storage,'test_token','test',proof)['status']=='RESOLVED_CLASSIFIED'
    row=next(check.csv.DictReader((storage/'FAILURE_ROOT_CAUSE.csv').open(encoding='utf-8')))
    assert row['diagnosis']=='Expected finite budget exhaustion' and row['resolution_SHA']==sha(proof)
    assert original.read_bytes()==receipt and row['status']=='TIME_LIMIT_NO_VALID_INCUMBENT'

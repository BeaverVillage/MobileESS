from copy import deepcopy
from pathlib import Path
import pytest
from v42_autonomous import supervisor as s
from v42_autonomous import recovery as r
from v42_autonomous.supervisor import sweep_complete, transition, next_day, DAYS

def checkpoint():
    return dict(state='B2_RUNNING',workers={},dates={a+'/'+d:dict(status='PENDING') for a in ('B2','B3') for d in DAYS})


def test_retry_refresh_real_queue_lock_contention_keeps_every_current_state(tmp_path):
    cp=checkpoint();cp['dates']['B2/'+DAYS[0]]['status']='PASS'
    cp['dates']['B2/'+DAYS[1]].update(status='FAIL',Native_Runtime=10.)
    cp['workers']['B2/'+DAYS[3]]=dict(day=DAYS[3],worker_slot=1,PID=123,request='sealed.json')
    r.atomic(tmp_path/'RECOVERY_QUEUE.json',dict(entries=[dict(arm='B2',date=DAYS[0],verification_status='READY_VERIFIED_REPAIR')]))
    before=deepcopy(cp);queue_before=(tmp_path/'RECOVERY_QUEUE.json').read_bytes()
    with r.os_lock(tmp_path/'RECOVERY_QUEUE.lock'):
        s.refresh_retries(tmp_path,cp)
    assert cp==before
    assert (tmp_path/'RECOVERY_QUEUE.json').read_bytes()==queue_before


def test_cycle_survives_real_operator_queue_lock_and_keeps_all_three_workers(tmp_path,monkeypatch):
    cp=checkpoint()
    for slot,day in enumerate(DAYS[3:6],1):
        key='B2/'+day;cp['dates'][key]['status']='RUNNING'
        cp['workers'][key]=dict(day=day,arm='B2',worker_slot=slot,PID=100+slot,request='sealed_'+str(slot)+'.json')
    cp['dates']['B2/'+DAYS[0]].update(status='PASS',Native_Runtime=1.)
    workers=deepcopy(cp['workers']);monkeypatch.setattr(s,'same_process',lambda worker:True)
    monkeypatch.setattr(r,'sync_worker',lambda root,worker:(_ for _ in ()).throw(r.LeaseBusy('REAL_OPERATOR_UPDATE')))
    monkeypatch.setattr(s,'dispatch',lambda *args:pytest.fail('HEALTHY_SLOT_REPLACED'))
    r.atomic(tmp_path/'RECOVERY_QUEUE.json',dict(entries=[]))
    with r.os_lock(tmp_path/'RECOVERY_QUEUE.lock'):
        s.cycle(tmp_path,{},cp)
    assert cp['state']=='B2_RUNNING' and cp['parallel_workers']==3
    assert cp['workers']==workers and cp['dates']['B2/'+DAYS[0]]['status']=='PASS'
    s.cycle(tmp_path,{},cp)
    assert cp['workers']==workers and cp['dates']['B2/'+DAYS[0]]['status']=='PASS'

def test_failure_quarantine_and_budget_terminal_do_not_block_sweep():
    cp=checkpoint()
    for row in cp['dates'].values():row['status']='PASS'
    cp['dates']['B2/'+DAYS[2]]['status']='QUARANTINE'
    cp['dates']['B2/'+DAYS[0]]['status']='TIME_LIMIT_FEASIBLE_NOT_CERTIFIED'
    assert sweep_complete(cp,'B2')
    cp['dates']['B2/'+DAYS[4]]['status']='RUNNING'
    assert not sweep_complete(cp,'B2')

def test_transition_is_idempotent_and_history_is_preserved():
    cp=checkpoint();transition(cp,'B2_FINALIZING');transition(cp,'B2_FINALIZING')
    assert len(cp['transition_history'])==1
    transition(cp,'B2_SWEEP_COMPLETE_WITH_FAILURES');transition(cp,'B3_STARTING')
    assert len(cp['transition_history'])==3

def test_dates_are_ordered_and_terminal_dates_are_never_redispatched():
    cp=checkpoint();cp['dates']['B2/'+DAYS[0]]['status']='QUARANTINE'
    assert next_day(cp,'B2')==DAYS[1]

def deployment(tmp_path):
    code_root=tmp_path/'immutable_code';code_root.mkdir()
    path=tmp_path/'FRESH_B2_MANIFEST.json'
    m=dict(schema='V42_AUTONOMOUS_B2_V20',run_id='fresh_run',attempt_id='fresh_b2_01',source_commit='c'*40,
        execution_SHA='b'*64,input_folders={day:str(tmp_path/'original_inputs'/day) for day in DAYS},prior_attempts={})
    r.atomic(path,m)
    manifest=dict(run_id='fresh_run',code_root=str(tmp_path/'control'),source_commit='d'*40,
        B2_worker_module='v42_autonomous_b2.worker',B2_deployment_manifest=r.record(path),
        B2_code_root=str(code_root),B2_source_commit='c'*40)
    return m,manifest

def test_fresh_b2_requests_use_declared_immutable_adapter(tmp_path,monkeypatch):
    m,manifest=deployment(tmp_path);checked=[]
    monkeypatch.setattr(s.subprocess,'run',lambda command,**kwargs:checked.append((command,kwargs)))
    path,request,module,code_root,commit=s.b2_request(tmp_path,manifest,DAYS[1],2)
    assert request['day']==DAYS[1] and request['worker_slot']==2
    assert module=='v42_autonomous_b2.worker' and code_root==manifest['B2_code_root'] and commit=='c'*40
    assert request['implementation_SHA']=='b'*64 and request['attempt_id']=='fresh_b2_01'
    assert checked[0][1]['cwd']==code_root
    assert 'v42_autonomous_b2.worker import verify_request' in checked[0][0][-2]
    assert r.read(Path(request['manifest']))['prior_attempts']=={}
    with pytest.raises(PermissionError,match='NEVER_OVERWRITTEN'):
        s.b2_request(tmp_path,manifest,DAYS[1],2)

def test_b3_later_dates_bind_qualification_and_source_root(tmp_path,monkeypatch):
    seal=tmp_path/'seal.json';r.atomic(seal,dict(source_sha='b'*64))
    checked=[]
    def preflight(command,**kwargs):
        checked.append((command,kwargs));request=__import__('json').loads(kwargs['input'])
        mode=dict(status='ABSENT',qualified=False,global_source_block=False)
        if len(checked)>1:
            mode.update(status='QUALIFIED',qualified=True,qualified_day=DAYS[0],
                qualification=dict(path=str(tmp_path/'autonomous/B3_PRODUCTION_QUALIFICATION.json')))
        return type('Result',(),{'stdout':__import__('json').dumps(dict(
            qualification_status=mode,scientific_run_id=request['scientific_run_id']))})()
    monkeypatch.setattr(s.subprocess,'run',preflight)
    manifest=dict(run_id='fresh_run',code_root=str(tmp_path/'control'),B1_campaign_root=str(tmp_path/'original_b1'),
        B3_code_root=str(tmp_path/'immutable_b3'),B3_source_seal=r.record(seal),B3_attempt_id='qualified_b3_01')
    _,first=s.b3_request(tmp_path,manifest,DAYS[0],1)
    _,later=s.b3_request(tmp_path,manifest,DAYS[1],1)
    assert first['canary'] is True and later['canary'] is False
    assert first['source_seal']==str(seal)
    assert first['implementation_SHA']==first['source_SHA']=='b'*64
    assert first['b1_campaign_root']==str(tmp_path/'original_b1')
    assert checked[0][1]['cwd']==manifest['B3_code_root']
    assert later['qualification']==str(tmp_path/'autonomous/B3_PRODUCTION_QUALIFICATION.json')
    assert Path(later['output']).is_relative_to(Path(manifest['B3_code_root'])/'runtime/b3')

def test_b3_source_sha_must_match_declared_seal(tmp_path):
    seal=tmp_path/'seal.json';r.atomic(seal,dict(source_sha='b'*64))
    manifest=dict(run_id='fresh_run',code_root=str(tmp_path/'control'),B3_source_SHA='c'*64,
        B3_code_root=str(tmp_path/'immutable_b3'),B3_source_seal=r.record(seal))
    with pytest.raises(PermissionError,match='B3_DECLARED_SOURCE_SHA_DRIFT'):
        s.b3_request(tmp_path,manifest,DAYS[0],1)

def test_request_without_saved_launch_is_quarantined_not_overwritten(tmp_path,monkeypatch):
    m,manifest=deployment(tmp_path)
    path=tmp_path/'dates/B2'/DAYS[0]/'attempts/fresh_b2_01/request.json'
    r.atomic(path,dict(arm='B2',day=DAYS[0],attempt_id='fresh_b2_01',worker_slot=1,
        result=str(path.parent/'RESULT.json'),implementation_SHA='b'*64))
    cp=checkpoint();monkeypatch.setattr(r,'_request_workers',lambda value:[])
    s.adopt_unjournaled_requests(tmp_path,cp,manifest)
    worker=cp['workers']['B2/'+DAYS[0]]
    assert worker['launch_intent'] is True
    s.collect(tmp_path,cp,'B2/'+DAYS[0],worker)
    assert cp['dates']['B2/'+DAYS[0]]['status']=='QUARANTINE'
    assert cp['dates']['B2/'+DAYS[0]]['Native_Runtime'] is None
    assert path.exists() and (path.parent/'WORKER_EXIT_WITHOUT_RESULT.json').exists()

def test_ready_queue_blocks_transition_but_terminal_failure_does_not(tmp_path):
    r.atomic(tmp_path/'RECOVERY_QUEUE.json',dict(entries=[dict(arm='B2',verification_status='READY_VERIFIED_REPAIR')]))
    assert s.recovery_pending(tmp_path,'B2')
    r.atomic(tmp_path/'RECOVERY_QUEUE.json',dict(entries=[dict(arm='B2',verification_status='RECOVERY_FAILED')]))
    assert not s.recovery_pending(tmp_path,'B2')


def b3_deployment(tmp_path):
    seal=tmp_path/'seal.json';r.atomic(seal,dict(source_sha='b'*64))
    return dict(run_id='fresh_run',code_root=str(tmp_path/'control'),source_commit='c'*40,B1_campaign_root=str(tmp_path/'original_b1'),
        B3_code_root=str(tmp_path/'immutable_b3'),B3_source_seal=r.record(seal),B3_attempt_id='b3_first_01',
        B3_source_SHA='b'*64)


def b2_finished_checkpoint():
    cp=checkpoint()
    for day in DAYS:cp['dates']['B2/'+day]['status']='PASS'
    return cp


def mock_b3_execution(tmp_path,monkeypatch,*,bad_day=None,terminal_status=None):
    import json
    launched=[]
    def preflight(command,**kwargs):
        request=json.loads(kwargs['input'])
        if request['day']==bad_day:
            raise s.subprocess.CalledProcessError(1,command,stderr='B1_A1_SAME_DAY_MODEL_DOMAIN_MISMATCH')
        return type('Result',(),{'stdout':json.dumps(dict(
            qualification_status=dict(status='ABSENT',qualified=False,global_source_block=False),
            scientific_run_id=request['scientific_run_id']))})()
    def popen(command,**kwargs):
        request=r.read(command[-1]);launched.append(request)
        if terminal_status:
            status=terminal_status(request['day']);passed=status=='PASS'
            r.atomic(request['result'],dict(identity={key:request[key] for key in ('arm','day','attempt_id')},
                source_SHA=request['implementation_SHA'],status=status,PASS=passed,Native_Runtime=0.))
        return type('Child',(),{'pid':1000+len(launched)})()
    monkeypatch.setattr(s.subprocess,'run',preflight)
    monkeypatch.setattr(s.subprocess,'Popen',popen)
    monkeypatch.setattr(s,'process',lambda pid=None:dict(PID=pid or 999,created=1.,command=['test',str(pid)]))
    monkeypatch.setattr(s,'same_process',lambda worker:False if terminal_status else True)
    monkeypatch.setattr(s,'external_workers',lambda cp:[])
    return launched


def test_actual_controller_failed_first_b3_preflight_continues_next_scoped_canary(tmp_path,monkeypatch):
    cp=b2_finished_checkpoint();manifest=b3_deployment(tmp_path)
    launched=mock_b3_execution(tmp_path,monkeypatch,bad_day=DAYS[0])
    s.cycle(tmp_path,manifest,cp)
    failed=cp['dates']['B3/'+DAYS[0]]
    assert failed['status']=='FAIL' and failed['Native_Runtime']==0.
    proof=r.read(failed['failure_receipt']['path'])
    assert proof['before_Popen'] and proof['before_Native'] and proof['new_attempt_native_runtime']==0.
    s.cycle(tmp_path,manifest,cp)
    assert len(launched)==1 and launched[0]['day']==DAYS[1]
    assert launched[0]['canary'] is True and 'qualification' not in launched[0]
    assert len(cp['workers'])==1 and cp['parallel_workers']==1
    assert failed['first_attempt_terminal']['status']=='FAIL'
    assert cp['state']!='SOURCE_BLOCKED'


def test_b2_first_sweep_yields_to_b3_even_when_b2_ready_repair_exists(tmp_path,monkeypatch):
    cp=b2_finished_checkpoint();cp['dates']['B2/'+DAYS[0]]['status']='TIME_LIMIT_FEASIBLE_NOT_CERTIFIED'
    r.atomic(tmp_path/'RECOVERY_QUEUE.json',dict(entries=[dict(queue_id='b2_retry',arm='B2',date=DAYS[0],
        verification_status='READY_VERIFIED_REPAIR',retry_priority=100,queued_UTC='2026-01-01')]))
    launched=mock_b3_execution(tmp_path,monkeypatch)
    s.cycle(tmp_path,b3_deployment(tmp_path),cp)
    assert 'B2' in cp['first_sweeps_completed'] and cp['state']=='B3_RUNNING'
    assert launched[0]['arm']=='B3' and launched[0]['day']==DAYS[0]
    row=cp['dates']['B2/'+DAYS[0]]
    assert row['status']=='RETRY_PENDING'
    assert row['first_attempt_terminal']['status']=='FAIL'
    assert row['first_attempt_terminal']['worker_status']=='TIME_LIMIT_FEASIBLE_NOT_CERTIFIED'
    assert all(worker['arm']=='B3' for worker in cp['workers'].values())


def test_controller_visits_all_31_b3_dates_despite_mixed_daily_failures(tmp_path,monkeypatch):
    cp=b2_finished_checkpoint()
    statuses=('FAIL','TIME_LIMIT_FEASIBLE_NOT_CERTIFIED','INFEASIBLE','NUMERICAL','QUARANTINE','PASS')
    launched=mock_b3_execution(tmp_path,monkeypatch,
        terminal_status=lambda day:statuses[(int(day[-2:])-1)%len(statuses)])
    manifest=b3_deployment(tmp_path)
    for _ in range(33):
        s.cycle(tmp_path,manifest,cp)
        assert len(cp['workers'])<=1
    assert [request['day'] for request in launched]==list(DAYS)
    assert all(request['canary'] is True for request in launched)
    assert set(cp['first_sweeps_completed'])=={'B2','B3'}
    assert cp['state']=='CAMPAIGN_SWEEP_COMPLETE_WITH_FAILURES'
    assert all(cp['dates']['B3/'+day]['first_attempt_terminal']['status']==s.public_status(statuses[(int(day[-2:])-1)%len(statuses)]) for day in DAYS)
    assert not cp['workers']


def test_idle_sweep_accepts_future_priority_repair_without_cross_arm_parallelism(tmp_path,monkeypatch):
    cp=checkpoint()
    for row in cp['dates'].values():row['status']='PASS'
    cp['dates']['B2/'+DAYS[0]]['status']='FAIL'
    cp['dates']['B3/'+DAYS[0]]['status']='QUARANTINE'
    monkeypatch.setattr(s,'external_workers',lambda cp:[])
    monkeypatch.setattr(s,'same_process',lambda worker:True)
    manifest=b3_deployment(tmp_path)
    s.cycle(tmp_path,manifest,cp)
    assert cp['state']=='CAMPAIGN_SWEEP_COMPLETE_WITH_FAILURES'
    entries=[dict(queue_id='b2_retry',arm='B2',date=DAYS[0],verification_status='READY_VERIFIED_REPAIR',
        retry_priority=200,queued_UTC='2026-01-01'),dict(queue_id='b3_retry',arm='B3',date=DAYS[0],
        verification_status='READY_VERIFIED_REPAIR',retry_priority=100,queued_UTC='2026-01-01')]
    r.atomic(tmp_path/'RECOVERY_QUEUE.json',dict(entries=entries));called=[]
    request=tmp_path/'retry/request.json';r.atomic(request,dict(attempt_id='repaired_01'))
    def retry(root,arm,slot,manifest):
        called.append((arm,slot))
        if arm=='B2' and slot==1 and not cp['workers']:
            return dict(arm='B2',day=DAYS[0],worker_slot=1,PID=222,created=1.,command=['test'],request=str(request),recovery_queue_id='b2_retry')
    monkeypatch.setattr(r,'dispatch_ready',retry)
    s.cycle(tmp_path,manifest,cp)
    assert cp['state']=='B2_REPAIRING'
    assert cp['dates']['B2/'+DAYS[0]]['first_attempt_terminal']['status']=='FAIL'
    assert cp['dates']['B2/'+DAYS[0]]['status']=='RUNNING'
    assert all(arm=='B2' for arm,slot in called)
    assert cp['dates']['B3/'+DAYS[0]]['status']=='RETRY_PENDING'


def test_common_source_integrity_failure_blocks_future_admission_with_scope(tmp_path,monkeypatch):
    cp=b2_finished_checkpoint();manifest=b3_deployment(tmp_path)
    monkeypatch.setattr(s,'external_workers',lambda cp:[])
    monkeypatch.setattr(s,'dispatch',lambda *args:(_ for _ in ()).throw(PermissionError('B3_SOURCE_SEAL_FILE_DRIFT:shared.py')))
    s.cycle(tmp_path,manifest,cp)
    assert cp['state']=='SOURCE_BLOCKED'
    block=cp['source_block']
    assert block['affectedScope']=='COMMON_SOURCE_OR_ENVIRONMENT_FUTURE_ADMISSION'
    assert 'B3_SOURCE_SEAL_FILE_DRIFT' in block['reasonCode']
    assert block['manifestSourceFreeze']['B3_source_SHA']=='b'*64
    assert all(cp['dates']['B3/'+day]['status']=='PENDING' for day in DAYS)
    assert 'first_attempt_terminal' not in cp['dates']['B3/'+DAYS[0]]


def test_same_day_b1_reuse_mismatch_remains_local_quarantine(tmp_path,monkeypatch):
    cp=b2_finished_checkpoint();manifest=b3_deployment(tmp_path)
    launched=mock_b3_execution(tmp_path,monkeypatch)
    original=s.dispatch
    def dispatch(root,manifest,cp,arm,day,slot):
        if day==DAYS[0]:raise PermissionError('B1_A1_SAME_DAY_MODEL_DOMAIN_MISMATCH')
        return original(root,manifest,cp,arm,day,slot)
    monkeypatch.setattr(s,'dispatch',dispatch)
    s.cycle(tmp_path,manifest,cp);s.cycle(tmp_path,manifest,cp)
    assert cp['dates']['B3/'+DAYS[0]]['status']=='QUARANTINE'
    assert launched[0]['day']==DAYS[1] and launched[0]['canary']
    assert cp['state']!='SOURCE_BLOCKED'


@pytest.mark.parametrize('status,passed',[('PASS',False),('FAIL',True)])
def test_collect_never_turns_inconsistent_status_or_pass_boolean_into_pass(tmp_path,status,passed):
    cp=checkpoint();day=DAYS[0];key='B3/'+day
    folder=tmp_path/'attempt';request=folder/'request.json';result=folder/'RESULT.json'
    r.atomic(request,dict(arm='B3',day=day,attempt_id='first_01',result=str(result)))
    r.atomic(result,dict(identity=dict(arm='B3',day=day,attempt_id='first_01'),source_sha='b'*64,
        status=status,PASS=passed,Native_Runtime=0.))
    worker=dict(request=str(request),source_SHA='b'*64);cp['workers'][key]=worker
    s.collect(tmp_path,cp,key,worker)
    assert cp['dates'][key]['status']=='QUARANTINE'
    assert cp['dates'][key]['terminal_policy_error']=='RESULT_PASS_STATUS_DISAGREEMENT'
    assert r.read(result)['status']==status and r.read(result)['PASS']==passed


def test_timeout_and_implementation_failure_have_fail_public_status_and_preserved_original_status():
    cp=checkpoint();cp['dates']['B2/'+DAYS[0]]['status']='TIME_LIMIT_FEASIBLE_NOT_CERTIFIED'
    cp['dates']['B2/'+DAYS[1]]['status']='IMPLEMENTATION_FAILURE'
    s.initialize_history(cp)
    assert cp['dates']['B2/'+DAYS[0]]['status']=='FAIL'
    assert cp['dates']['B2/'+DAYS[0]]['worker_status']=='TIME_LIMIT_FEASIBLE_NOT_CERTIFIED'
    assert cp['dates']['B2/'+DAYS[1]]['status']=='FAIL'
    assert cp['dates']['B2/'+DAYS[1]]['first_attempt_terminal']['worker_status']=='IMPLEMENTATION_FAILURE'


def test_retry_activation_archives_old_evidence_and_clears_current_fields(tmp_path):
    cp=checkpoint();key='B2/'+DAYS[0];row=cp['dates'][key]
    row.update(status='FAIL',current_attempt='old_01',request='old_request',result='old_result',result_SHA='a'*64,
        Native_Runtime=353.,source_SHA='a'*64,worker_status='IMPLEMENTATION_FAILURE',error='old_error',
        failure_receipt={'path':'old_failure','sha256':'f'*64},finished_UTC='2026-01-01',terminal_policy_error='old_policy')
    s.first_terminal(cp,key);first=deepcopy(row['first_attempt_terminal'])
    request=tmp_path/'new/request.json';r.atomic(request,dict(attempt_id='fresh_23',implementation_SHA='b'*64))
    worker=dict(request=str(request),worker_slot=2,source_SHA='b'*64,source_commit='c'*40,recovery_queue_id='retry')
    s.activate_retry(cp,key,worker)
    assert row['current_attempt']=='fresh_23' and row['status']=='RUNNING'
    assert row['source_SHA']=='b'*64 and row['Native_Runtime'] is None
    assert row['first_attempt_terminal']==first
    assert row['attempt_history'][0]['result']=='old_result' and row['attempt_history'][0]['Native_Runtime']==353.
    assert all(field not in row for field in ('result','result_SHA','worker_status','error','failure_receipt','finished_UTC','terminal_policy_error'))
    s.activate_retry(cp,key,worker)
    assert len(row['attempt_history'])==1


def test_retry_adoption_uses_same_clean_activation(tmp_path,monkeypatch):
    cp=checkpoint();key='B2/'+DAYS[0]
    cp['dates'][key].update(status='FAIL',current_attempt='old',result='old_result',result_SHA='a'*64,Native_Runtime=353.)
    s.first_terminal(cp,key)
    request=tmp_path/'new/request.json';r.atomic(request,dict(attempt_id='fresh_23'))
    worker=dict(arm='B2',day=DAYS[0],request=str(request),worker_slot=1,source_SHA='b'*64,recovery_queue_id='retry')
    monkeypatch.setattr(r,'reconcile_workers',lambda root:[worker]);monkeypatch.setattr(r,'queue',lambda root:dict(entries=[]))
    s.adopt_recovery_workers(tmp_path,cp)
    assert cp['dates'][key]['current_attempt']=='fresh_23'
    assert 'result' not in cp['dates'][key] and cp['dates'][key]['Native_Runtime'] is None
    assert cp['dates'][key]['attempt_history'][0]['result']=='old_result'


@pytest.mark.parametrize('status,passed',[('PASS',False),('FAIL',True),('TIME_LIMIT',False)])
def test_adopted_terminal_normalizes_status_and_rejects_pass_disagreement(tmp_path,monkeypatch,status,passed):
    cp=checkpoint();key='B2/'+DAYS[0]
    request=tmp_path/'request.json';r.atomic(request,dict(attempt_id='fresh_23'))
    result=tmp_path/'RESULT.json';r.atomic(result,dict(status=status,PASS=passed))
    cp['dates'][key].update(status='RUNNING',request=str(request))
    entry=dict(arm='B2',date=DAYS[0],retry_request_receipt=r.record(request),final_result_receipt=r.record(result),
        verification_status='RECOVERY_FAILED',final_Native_Runtime=1.,repair_source_SHA='b'*64)
    monkeypatch.setattr(r,'reconcile_workers',lambda root:[]);monkeypatch.setattr(r,'queue',lambda root:dict(entries=[entry]))
    s.adopt_recovery_workers(tmp_path,cp)
    assert cp['dates'][key]['status']==('FAIL' if status=='TIME_LIMIT' else 'QUARANTINE')
    assert cp['dates'][key]['worker_status']==status and cp['dates'][key]['current_attempt']=='fresh_23'

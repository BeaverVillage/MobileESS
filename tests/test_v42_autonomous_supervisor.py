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

def test_cycle_heartbeat_access_failure_keeps_all_workers_and_other_dates_observed(tmp_path,monkeypatch):
    cp=checkpoint()
    for slot,day in enumerate(DAYS[3:6],1):
        key='B2/'+day;cp['dates'][key].update(status='RUNNING',Native_Runtime=40.+slot)
        cp['workers'][key]=dict(day=day,arm='B2',worker_slot=slot,PID=100+slot,created=10.+slot,request='sealed_'+str(slot)+'.json')
    workers=deepcopy(cp['workers']);dates=deepcopy(cp['dates']);calls=[]
    fault_key='B2/'+DAYS[4];fault_path=tmp_path/'HEARTBEAT.json';failed=True;missing=False
    def observe(root,worker):
        calls.append(worker['day'])
        if failed and worker['day']==DAYS[4]:
            raise r.HeartbeatObservationDeferred(fault_path,PermissionError(13,'fixture Windows access denied',str(fault_path)))
        if missing and worker['day']==DAYS[4]:return dict(verification_status='WORKER_ENTERED')
        return r.HeartbeatObservationRead(dict(verification_status='WORKER_ENTERED'))
    monkeypatch.setattr(s,'same_process',lambda worker:True);monkeypatch.setattr(r,'sync_worker',observe)
    monkeypatch.setattr(s,'dispatch',lambda *a:pytest.fail('HEALTHY_WORKER_REPLACED'))
    r.atomic(tmp_path/'RECOVERY_QUEUE.json',dict(entries=[]))
    queue_bytes=(tmp_path/'RECOVERY_QUEUE.json').read_bytes()
    for iteration in range(3):
        s.cycle(tmp_path,{},cp)
        assert calls[-3:]==list(DAYS[3:6])
        assert cp['workers']==workers and cp['dates']==dates
        assert cp['worker_observation_errors'][fault_key]['consecutive_failures']==iteration+1
    error=cp['worker_observation_errors'][fault_key]
    assert error['status']=='PERSISTENT_WORKER_HEARTBEAT_IO_ERROR'
    assert error['original_read_error']['errno']==13 and error['original_read_error']['path']==str(fault_path.resolve())
    assert len(cp['worker_observation_error_history'])==2
    failed=False;missing=True;s.cycle(tmp_path,{},cp)
    assert cp['worker_observation_errors'][fault_key]==error and len(cp['worker_observation_error_history'])==2
    missing=False;s.cycle(tmp_path,{},cp)
    assert not cp['worker_observation_errors'] and len(cp['worker_observation_error_history'])==3
    assert cp['worker_observation_error_history'][-1]['observation_resolved_UTC']
    assert cp['worker_observation_error_history'][-1]['original_read_error']==error['original_read_error']
    assert cp['workers']==workers and cp['dates']==dates
    assert (tmp_path/'RECOVERY_QUEUE.json').read_bytes()==queue_bytes


def test_cycle_never_swallows_general_permission_or_global_source_failure(tmp_path,monkeypatch):
    cp=checkpoint();key='B2/'+DAYS[4]
    cp['workers'][key]=dict(day=DAYS[4],arm='B2',worker_slot=1,PID=101,request='sealed.json')
    cp['dates'][key].update(status='RUNNING',Native_Runtime=31.)
    before=deepcopy(cp);monkeypatch.setattr(s,'same_process',lambda worker:True)
    for error in (PermissionError(13,'sealed manifest inaccessible','manifest.json'),r.SourceBlocked('GLOBAL_SOURCE_INTEGRITY_FAILURE:shared')):
        monkeypatch.setattr(r,'sync_worker',lambda *a:(_ for _ in ()).throw(error))
        with pytest.raises(PermissionError) as caught:s.cycle(tmp_path,{},cp)
        assert caught.value is error and cp['workers']==before['workers'] and cp['dates']==before['dates']
        assert 'worker_observation_errors' not in cp


def test_clean_heartbeat_for_different_attempt_cannot_resolve_previous_worker_fault(tmp_path):
    cp=checkpoint();key='B2/'+DAYS[4]
    worker=dict(PID=101,created=11.,request='original-request.json',recovery_queue_id='original-queue')
    error=r.HeartbeatObservationDeferred(tmp_path/'HEARTBEAT.json',PermissionError(13,'original denied',str(tmp_path/'HEARTBEAT.json')))
    s.record_heartbeat_observation_error(cp,key,worker,error)
    original=deepcopy(cp['worker_observation_errors'][key]);history=deepcopy(cp['worker_observation_error_history'])
    newer=dict(worker,PID=102,created=12.,request='new-request.json',recovery_queue_id='new-queue')
    assert s.resolve_heartbeat_observation_error(cp,key,newer) is False
    assert cp['worker_observation_errors'][key]==original and cp['worker_observation_error_history']==history
    assert s.resolve_heartbeat_observation_error(cp,key,worker) is True
    assert not cp['worker_observation_errors']
    assert cp['worker_observation_error_history'][-1]['resolution']=='CLEAN_OWNED_HEARTBEAT_READ_FOR_SAME_WORKER_IDENTITY'
    assert cp['worker_observation_error_history'][-1]['original_read_error']==original['original_read_error']


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



def _startup_lock_error(root,number=13,path=None):
    from v42_may_campaign_native90.common import LockBusy
    error=LockBusy('LIVE_OS_LOCK:'+str(path or root/'AUTONOMOUS_SUPERVISOR.lock'))
    error.__cause__=OSError(number,'isolated lock refusal')
    return error


def _duplicate_owner_fixture(tmp_path,monkeypatch,age=0):
    import sys
    from datetime import datetime,timezone,timedelta
    owner=dict(PID=22001,created=10.,command=[sys.executable,'-B','-X','utf8','-m','v42_autonomous.supervisor',str(tmp_path)])
    heartbeat=dict(process=owner,timestamp_UTC=(datetime.now(timezone.utc)-timedelta(seconds=age)).isoformat(),state='B2_RUNNING')
    s.atomic(tmp_path/'SUPERVISOR_PROCESS.json',owner);s.atomic(tmp_path/'SUPERVISOR_HEARTBEAT.json',heartbeat)
    s.atomic(tmp_path/'SUPERVISOR_STATE.json',dict(workers={'B2/2025-05-01':dict(PID=12,request='unchanged sealed fixture')},status='RUNNING'))
    s.atomic(tmp_path/'SUPERVISOR_ERROR.json',dict(error='actual earlier error retained',UTC='2026-01-01'))
    class Live:
        pid=owner['PID']
        def create_time(self):return owner['created']
        def cmdline(self):return owner['command']
        def cwd(self):return str(Path(s.__file__).resolve().parents[1])
        def exe(self):return sys.executable
        def is_running(self):return True
    live=Live()
    monkeypatch.setattr(s.psutil,'Process',lambda pid=None:live if pid is not None else type('Caller',(),{'pid':99001})())
    monkeypatch.setattr(s,'process',lambda:dict(PID=99001,command=['isolated test caller']))
    return owner,heartbeat,live


def test_duplicate_startup_immutable_event_preserves_public_error_cp_and_worker_evidence(tmp_path,monkeypatch):
    owner,heartbeat,live=_duplicate_owner_fixture(tmp_path,monkeypatch)
    paths=[tmp_path/n for n in ('SUPERVISOR_PROCESS.json','SUPERVISOR_HEARTBEAT.json','SUPERVISOR_STATE.json','SUPERVISOR_ERROR.json')]
    before={p:p.read_bytes() for p in paths};error=_startup_lock_error(tmp_path)
    for _ in range(2):assert s.reject_verified_duplicate_startup(tmp_path,error) is True
    events=list((tmp_path/'autonomous/startup_rejections').glob('*.json'));assert len(events)==2
    assert all(p.read_bytes()==raw for p,raw in before.items())
    for p in events:
        event=s.read(p)
        assert event['existing_owner']['PID']==owner['PID']
        assert event['reason']=='DUPLICATE_STARTUP_REJECTED_EXISTING_OWNED_LIVE_SUPERVISOR'
        assert event['SUPERVISOR_ERROR_not_written'] and event['CP_worker_Native_files_not_written']
        assert not event['lock_removed_or_lease_broken']


@pytest.mark.parametrize('kind',['wrong_lock','wrong_type','unsupported_errno','no_cause'])
def test_only_canonical_startup_lock_error_can_use_duplicate_rejection(tmp_path,monkeypatch,kind):
    _duplicate_owner_fixture(tmp_path,monkeypatch);error=_startup_lock_error(tmp_path)
    if kind=='wrong_lock':error=_startup_lock_error(tmp_path,path=tmp_path/'RECOVERY_QUEUE.lock')
    elif kind=='wrong_type':error=RuntimeError(str(error));error.__cause__=OSError(13,'not canonical')
    elif kind=='unsupported_errno':error=_startup_lock_error(tmp_path,number=5)
    else:error.__cause__=None
    assert s.reject_verified_duplicate_startup(tmp_path,error) is False
    assert not (tmp_path/'autonomous/startup_rejections').exists()


@pytest.mark.parametrize('kind',['stale_heartbeat','future_heartbeat','different_created','different_command','different_cwd','different_heartbeat_owner','dead_owner'])
def test_unproven_or_stalled_owner_never_silences_startup_lock_failure(tmp_path,monkeypatch,kind):
    import sys
    owner,heartbeat,live=_duplicate_owner_fixture(tmp_path,monkeypatch,age=120 if kind=='stale_heartbeat' else -120 if kind=='future_heartbeat' else 0)
    if kind=='different_created':monkeypatch.setattr(live,'create_time',lambda:11.)
    elif kind=='different_command':monkeypatch.setattr(live,'cmdline',lambda:[sys.executable,'unrelated'])
    elif kind=='different_cwd':monkeypatch.setattr(live,'cwd',lambda:str(tmp_path))
    elif kind=='different_heartbeat_owner':heartbeat['process']['PID']=99001;s.atomic(tmp_path/'SUPERVISOR_HEARTBEAT.json',heartbeat)
    elif kind=='dead_owner':monkeypatch.setattr(live,'is_running',lambda:False)
    error=_startup_lock_error(tmp_path)
    assert s.reject_verified_duplicate_startup(tmp_path,error) is False
    assert not (tmp_path/'autonomous/startup_rejections').exists()


@pytest.mark.parametrize('kind',['missing','corrupt','access_denied'])
def test_startup_owner_proof_reads_remain_strict(tmp_path,monkeypatch,kind):
    _duplicate_owner_fixture(tmp_path,monkeypatch);p=tmp_path/'SUPERVISOR_HEARTBEAT.json'
    if kind=='missing':p.unlink();expected=FileNotFoundError
    elif kind=='corrupt':p.write_bytes(b'{bad');expected=ValueError
    else:
        original=Path.read_bytes
        def denied(path):
            if path==p:raise PermissionError(13,'isolated ACL denial',str(p))
            return original(path)
        monkeypatch.setattr(Path,'read_bytes',denied);expected=PermissionError
    with pytest.raises(expected):s.reject_verified_duplicate_startup(tmp_path,_startup_lock_error(tmp_path))
    assert not (tmp_path/'autonomous/startup_rejections').exists()


def test_lockbusy_inside_acquired_controller_body_is_not_duplicate_startup(tmp_path):
    error=_startup_lock_error(tmp_path)
    with pytest.raises(type(error)) as raised:
        with s.startup_supervisor_lock(tmp_path) as acquired:
            assert acquired
            raise error
    assert raised.value is error and not (tmp_path/'autonomous/startup_rejections').exists()


def test_actual_windows_owned_supervisor_mutex_duplicate_keeps_error_cp_and_native_fixtures(tmp_path):
    import os,sys,json,time,subprocess
    if sys.platform!='win32':pytest.skip('real Windows supervisor mutex required')
    repo=Path(s.__file__).resolve().parents[1]
    site=tmp_path/'denial_site';site.mkdir()
    attempts=tmp_path/'CHILD_NATIVE_ENTRY_ATTEMPTS.json';installed=tmp_path/'CHILD_NATIVE_DENIAL_INSTALLED.json'
    site_code=("import gurobipy as gp\nfrom pathlib import Path\nimport json\n"
        "def denied(*args,**kwargs):\n    Path("+repr(str(attempts))+").write_text('DENIED ENTRY',encoding='utf-8')\n    raise AssertionError('ISOLATED_CHILD_NATIVE_MODEL_ENTRY_DENIED')\n"
        "gp.Model.__init__=denied\ngp.Model.optimize=denied\nPath("+repr(str(installed))+").write_text(json.dumps({'Model_init_denied':True,'Model_optimize_denied':True}),encoding='utf-8')\n")
    (site/'sitecustomize.py').write_text(site_code,encoding='utf-8')
    s.atomic(tmp_path/'AUTONOMOUS_MANIFEST.json',dict(B2_workers=3,B3_workers=1))
    s.atomic(tmp_path/'CONTINUATION_V19_MANIFEST.json',dict(attempt_id='no_native_fixture'))
    cp=checkpoint()
    for row in cp['dates'].values():row['status']='PASS' # Operational fixture, no scientific PASS evidence.
    s.atomic(tmp_path/'SUPERVISOR_STATE.json',cp)
    prior_error=tmp_path/'SUPERVISOR_ERROR.json';s.atomic(prior_error,dict(error='prior true error fixture',Native_Runtime=None))
    evidence=[prior_error]
    for day in DAYS[:3]:
        folder=tmp_path/'dates/B2'/day/'attempts/isolated_fixture';s.atomic(folder/'request.json',dict(day=day,fixture_only=True))
        s.atomic(folder/'NATIVE_RUNTIME_LEDGER.json',dict(fixture_only=True,calls=[],no_real_Native_measurements=True))
        evidence.extend([folder/'request.json',folder/'NATIVE_RUNTIME_LEDGER.json'])
    env=dict(os.environ);env['PYTHONPATH']=str(site)+os.pathsep+str(repo);env['PYTHONDONTWRITEBYTECODE']='1'
    command=[sys.executable,'-B','-X','utf8','-m','v42_autonomous.supervisor',str(tmp_path)]
    child=None;expected_created=None
    with (tmp_path/'child_stdout.log').open('wb') as out,(tmp_path/'child_stderr.log').open('wb') as err:
        try:
            child=subprocess.Popen(command,cwd=repo,env=env,stdin=subprocess.DEVNULL,stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW)
            for _ in range(500):
                if child.poll() is not None:pytest.fail('ISOLATED_OWNER_EXITED:'+str(child.returncode))
                if (tmp_path/'SUPERVISOR_HEARTBEAT.json').exists():break
                time.sleep(.02)
            else:pytest.fail('ISOLATED_OWNER_HEARTBEAT_MISSING')
            owner=s.read(tmp_path/'SUPERVISOR_PROCESS.json');expected_created=owner['created'];assert owner['PID']==child.pid and owner['command']==command
            assert s.read(installed)==dict(Model_init_denied=True,Model_optimize_denied=True)
            evidence.append(tmp_path/'SUPERVISOR_STATE.json');before={p:p.read_bytes() for p in evidence}
            s.run(tmp_path)
            assert child.poll() is None and all(p.read_bytes()==raw for p,raw in before.items())
            events=list((tmp_path/'autonomous/startup_rejections').glob('*.json'));assert len(events)==1
            event=s.read(events[0]);assert event['existing_owner']['PID']==child.pid
            assert event['startup_error'].startswith("LockBusy('LIVE_OS_LOCK:") and event['errno']==13
            assert not attempts.exists()
            with pytest.raises(s.LockBusy):
                with s.exclusive_lock(tmp_path/'AUTONOMOUS_SUPERVISOR.lock'):pytest.fail('ORIGINAL_OWNER_MUTEX_RELEASED')
            s.atomic(tmp_path/'REAL_WINDOWS_STARTUP_DUPLICATE_NATIVE_DENIED_PROOF.json',dict(PASS=True,fixture_only=True,actual_canonical_owner=owner,actual_live_mutex_rejection=event,
                prior_error_CP_three_sealed_worker_and_Native_fixture_bytes_unchanged=True,real_Native_model_constructions=0,Native_optimize_calls=0,child_Model_init_and_optimize_denied=True,
                production_process_actions=0,isolated_fixture_child_launch_count=1,isolated_fixture_child_termination_required_for_teardown=True))
        finally:
            if child is not None and child.poll() is None:
                actual=s.psutil.Process(child.pid)
                assert actual.cmdline()==command and Path(actual.cwd()).resolve()==repo
                if expected_created is not None:assert actual.create_time()==expected_created
                child.terminate();child.wait(timeout=10)

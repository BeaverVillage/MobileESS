from copy import deepcopy
from pathlib import Path
import pytest
from v42_autonomous import supervisor as s
from v42_autonomous import recovery as r
from v42_autonomous.supervisor import sweep_complete, transition, next_day, DAYS

def checkpoint():
    return dict(state='B2_RUNNING',workers={},dates={a+'/'+d:dict(status='PENDING') for a in ('B2','B3') for d in DAYS})

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
    monkeypatch.setattr(s.subprocess,'run',lambda command,**kwargs:checked.append((command,kwargs)))
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

"""Native=0 recovery ordering, restart adoption and scientific isolation."""
from pathlib import Path
from fractions import Fraction
from contextlib import contextmanager
import json, sys, uuid
from unittest.mock import patch
import numpy as np
import pytest
from v42_pr134_b1.common import atomic, read, sha, process, ROOT
from v42_may_mess_build_v7 import coordinator as co
from v42_may_mess_build_v7.policy import MANIFEST, ATTEMPT, VERSION, attempt_path
from v42_may_build_v6.construction import ReferenceReuse
from v42_may_build_v6.numerical import apply_precision


@pytest.fixture
def campaign():
    root=ROOT/'tmp/mess_v7_tests'/uuid.uuid4().hex
    root.mkdir(parents=True)
    manifest=dict(run_id='fake_'+root.name,Python=sys.executable,monitor_port=8794,
        implementation=dict(source_SHA='fixture',version=VERSION),
        scientific_authority=dict(path=str(root/'authority.json')),
        axis=[dict(arm=a,day=d) for a,d in co.AXIS],input_folders={})
    cp=dict(run_id=manifest['run_id'],state='READY',dates={},last_error=None)
    for arm,day in co.AXIS:
        folder=root/'inputs'/arm/day;folder.mkdir(parents=True)
        atomic(folder/'INPUT_IDENTITY.json',dict(arm=arm,day=day))
        atomic(folder/'NATIVE_INPUT.json',dict(arm=arm,day=day,Native_calls=0))
        manifest['input_folders'][arm+'/'+day]=str(folder)
        done=arm=='B1' and day<='2025-05-22' and day not in co.RETRY_DATES
        cp['dates'][arm+'/'+day]=dict(arm=arm,day=day,status='PASS' if done else 'PENDING',attempts=int(done))
    atomic(root/MANIFEST,manifest);co.save_checkpoint(root,cp)
    with patch('v42_may_mess_build_v7.policy.verify_request',return_value={}), patch('v42_may_mess_build_v7.deferred_validation.ready',return_value=True):
        yield root,manifest,cp


FAKE=r'''
import os,json,pathlib,hashlib,sys,datetime
r=json.loads(pathlib.Path(sys.argv[1]).read_text());out=pathlib.Path(r['output']);out.mkdir()
p=out/'payload.json';p.write_text(json.dumps(dict(day=r['day'],Native_calls=0)))
with (pathlib.Path(r['root'])/'order.jsonl').open('a') as f:f.write(json.dumps(dict(arm=r['arm'],day=r['day'],slot=r['worker_slot'],PID=os.getpid()))+'\n')
status='NUMERICAL_FAILURE' if r['day']=='2025-05-11' and r['arm']=='B1' else 'PASS'
x=dict(identity={k:r[k] for k in ('run_id','arm','day','attempt_id','algorithm_version')},status=status,PASS=status=='PASS',Native_calls=0,files=[dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest())],finished_UTC=datetime.datetime.now(datetime.timezone.utc).isoformat())
t=pathlib.Path(r['result']+'.tmp');t.write_text(json.dumps(x));os.replace(t,r['result'])
'''


def factory(root):
    p=root/'fake.py';p.write_text(FAKE)
    return lambda manifest,request:[sys.executable,'-B',str(p),str(request)]


def test_current_date_owns_only_b1_slot_and_blocks_retries(campaign):
    root,m,cp=campaign
    row=cp['dates']['B1/2025-05-22'];row['status']='RUNNING'
    active={'B1/2025-05-22':dict(arm='B1',day='2025-05-22',worker_slot=1,worker=process())}
    with patch.object(co.subprocess,'Popen',side_effect=AssertionError('CURRENT_WORKER_REPLACED')):
        assert co.dispatch_available(root,m,cp,active,{},factory(root))==[]


def test_exact_order_23_through_31_then_three_b2_and_no_retries(campaign):
    root,m,cp=campaign
    original=root/'CHECKPOINT.json';atomic(original,dict(original_immutable=True));original_sha=sha(original)
    co.run(root,worker_command=factory(root),verify=False,poll_seconds=.01)
    rows=[json.loads(s) for s in (root/'order.jsonl').read_text().splitlines()]
    expected=list(co.DAYS[22:])
    assert [r['day'] for r in rows if r['arm']=='B1']==expected
    assert all(r['slot']==1 for r in rows if r['arm']=='B1')
    assert sorted(r['day'] for r in rows if r['arm']=='B2')==list(co.DAYS)
    assert sorted((r['day'],r['slot']) for r in rows[len(expected):len(expected)+3])==list(zip(co.DAYS[:3],(1,2,3)))
    assert len({(r['arm'],r['day']) for r in rows})==len(rows)
    assert sha(original)==original_sha
    with patch.object(co.subprocess,'Popen',side_effect=AssertionError('SECOND_RECOVERY_ATTEMPT')):
        co.run(root,verify=False)
    assert len((root/'order.jsonl').read_text().splitlines())==len(rows)
    assert co.counts(read(root/'CHECKPOINT_V7R2.json'),'B1')['completed']==31


def test_restart_adopts_same_recovery_process_and_cannot_dispatch_19(campaign):
    root,m,cp=campaign
    path,r=co.new_request(root,m,'B1','2025-05-23')
    owner=process();r['worker_command']=owner['command'];atomic(path,r)
    cp['dates']['B1/2025-05-23'].update(status='RUNNING',attempts=1,request=str(path),worker_slot=1)
    co.save_checkpoint(root,cp)
    co.persist_actives(root,m,{'B1/2025-05-23':dict(arm='B1',day='2025-05-23',request=str(path),worker=owner,worker_slot=1)})
    active=co.recover_actives(root,m,cp)
    assert active['B1/2025-05-23']['worker']['PID']==owner['PID']
    assert active['B1/2025-05-23']['adopted']
    assert co.dispatch_available(root,m,cp,active,{},factory(root))==[]


def test_attempt_and_input_paths_are_independent(campaign):
    root,m,cp=campaign
    _,a=co.new_request(root,m,'B1','2025-05-23')
    _,b=co.new_request(root,m,'B1','2025-05-24')
    for name in ('output','result','progress','error','input_folder'):
        assert a[name]!=b[name]
    assert Path(a['result']).parent==attempt_path(root,'B1','2025-05-23')
    assert a['native_budget_seconds']==5400 and a['wall_budget_seconds'] is None
    assert a['Threads']==1 and a['P2_calls']==0 and a['target_gap']==.005
    changed=dict(a,day=b['day'])
    with pytest.raises(PermissionError):co.validate_request(root,m,changed)


def test_reference_reuse_requires_same_current_reference_data_rows_and_axes():
    calls=[];data=object();ref=object();axes={('GPU','A',0):0}
    result=(ref,{},(0,),{}, {},axes)
    reuse=ReferenceReuse(lambda *args:(calls.append(args) or result))
    reuse(object(),(4,),1,{},data)
    assert reuse(ref,(0,),1,axes,data) is result and len(calls)==1
    reuse(ref,(0,),1,axes,object());assert len(calls)==2


def test_precision_is_tighter_without_changing_integer_heuristics_or_other_dates():
    class Model:
        def __init__(self):self.Params=type('Params',(),{})()
        def setParam(self,n,v):setattr(self.Params,n,v)
    import v42_may_build_v6.numerical as numerical
    baseline=dict(Threads=1,Heuristics=.05,MIPGap=.005,FeasibilityTol=1e-6)
    def apply(model,policy,gp):
        for n,v in baseline.items():model.setParam(n,v)
        return dict(baseline)
    with patch.object(numerical,'original_apply',side_effect=apply):
        m=Model();p=apply_precision(m,{},None,day='2025-05-11',component='PHASE_I')
        assert p['FeasibilityTol']==1e-9 and p['Heuristics']==.05 and p['MIPGap']==.005
        assert apply_precision(Model(),{},None,day='2025-05-19',component='PHASE_I')==baseline
        assert apply_precision(Model(),{},None,day='2025-05-11',component='INTEGER_CONTROL')==baseline


def test_native_admission_queries_cmdline_only_for_python(monkeypatch):
    from types import SimpleNamespace
    from v42_may_mess_build_v7 import worker
    queried=[]
    class Candidate:
        def __init__(self,pid,name):self.pid=pid;self.info={'pid':pid,'name':name}
        def cmdline(self):queried.append(self.pid);return ['python.exe','-m','unrelated']
    candidates=[Candidate(2,'svchost.exe'),Candidate(3,'python.exe'),Candidate(4,'explorer.exe')]
    monkeypatch.setattr(worker.psutil,'process_iter',lambda attrs:candidates)
    monkeypatch.setattr(worker.psutil,'Process',lambda:SimpleNamespace(pid=1))
    assert worker.assert_no_other_native_worker() == []
    assert queried == [3]


def test_may19_graph_admission_uses_fresh_original_data(tmp_path):
    from v42_may_build_v6.input_cache import seed_input_cache
    module=object()
    request=dict(day='2025-05-19',output=str(tmp_path),
                 _current_date_physical_cache='unread-original-graph-cache')
    assert seed_input_cache(request,module,tmp_path) is False
    receipt=read(tmp_path/'INPUT_GRAPH_CACHE_VERIFICATION.json')
    assert receipt['PASS'] and receipt['mode']=='FRESH_ORIGINAL_DATA_PRODUCER'
    assert receipt['Native_calls']==0 and receipt['graph_cache_reused'] is False


def test_monitor_reads_completed_ledger_instead_of_stale_solver_clock(tmp_path):
    from v42_may_mess_build_v7.monitor import enrich_worker
    atomic(tmp_path/'input/NATIVE_INPUT.json',dict(day='2025-05-11'))
    atomic(tmp_path/'request.json',dict(result=str(tmp_path/'RESULT.json'),
        output=str(tmp_path/'output'),input_folder=str(tmp_path/'input'),started_UTC='2026-10-09T00:00:00+00:00'))
    atomic(tmp_path/'NATIVE_RUNTIME_LEDGER.json',dict(measured_Native_Runtime=123.,
        calls=[dict(component='PHASE_I')],inflight=None))
    row=dict(arm='B1',day='2025-05-11',request=str(tmp_path/'request.json'),
        worker_alive=False,resource={},progress=dict(Native_Runtime=0,phase='PHASE_I'))
    result=enrich_worker(row,0)
    assert result['Native_Runtime_seconds']==123
    assert result['native_remaining_seconds']==5277
    assert result['Native_calls']==1 and result['latest_native_component']=='PHASE_I'
    assert result['input_SHA']==sha(tmp_path/'input/NATIVE_INPUT.json')


def test_three_v5_peer_paths_and_slots_are_admitted_but_same_date_rejected(campaign,monkeypatch):
    from types import SimpleNamespace
    from v42_may_mess_build_v7 import worker
    root,m,cp=campaign
    requests=[]
    for slot,day in enumerate(co.DAYS[:3],1):
        path,r=co.new_request(root,m,'B2',day,worker_slot=slot)
        r['worker_command']=co.default_worker_command(m,path);atomic(path,r)
        requests.append((path,r))
    class Candidate:
        def __init__(self,pid,args):self.pid=pid;self.info={'pid':pid,'name':'python.exe'};self.args=args
        def cmdline(self):return self.args
    candidates=[Candidate(slot,r['worker_command']) for slot,(_,r) in enumerate(requests[1:],2)]
    monkeypatch.setattr(worker.psutil,'process_iter',lambda attrs:candidates)
    monkeypatch.setattr(worker.psutil,'Process',lambda:SimpleNamespace(pid=1))
    peers=worker.assert_no_other_native_worker(requests[0][1])
    assert {p['worker_slot'] for p in peers}=={2,3}
    assert len({p['day'] for p in peers})==2
    own=requests[0][1]
    with pytest.raises(worker.LockBusy,match='DUPLICATE'):
        worker._peer_request(own['worker_command'],own)


def test_running_23_is_preserved_and_completed_11_19_22_are_not_reset(campaign):
    from v42_may_mess_build_v7.storage import initialize_checkpoint
    root,m,cp=campaign
    cp['dates']['B1/2025-05-23'].update(status='RUNNING',attempts=1)
    old=root/'BASE_BOUNDARY.json';atomic(old,cp);before=sha(old)
    m['base_checkpoint']=dict(path=str(old),sha256=before)
    atomic(root/'MAY23_V5_USER_RESTART_RECEIPT.json',dict(user_requested_from='2025-05-23',
        old_worker_no_longer_alive=True,Native_calls_before_stop=0,Native_Runtime_before_stop=0))
    initialized=initialize_checkpoint(root,m)
    assert sha(old)==before
    assert initialized['dates']['B1/2025-05-23']['status']=='RUNNING'
    assert initialized['dates']['B1/2025-05-23']['attempts']==1
    for day in ('2025-05-11','2025-05-19','2025-05-22'):
        assert initialized['dates']['B1/'+day]['status']=='PASS'
    assert co.pending_phase(initialized)=='B1'


def test_30_terminal_days_block_b2_and_31_with_failures_allow_three(campaign):
    root,m,cp=campaign
    for row in cp['dates'].values():
        if row['arm']=='B1':row.update(status='PASS',attempts=1)
    cp['dates']['B1/2025-05-31'].update(status='PENDING',attempts=0)
    assert co.pending_phase(cp)=='B1'
    with pytest.raises(PermissionError):co.ensure_phase(cp,'B2')
    cp['dates']['B1/2025-05-31'].update(status='TIME_LIMIT_NO_VALID_INCUMBENT',attempts=1)
    cp['dates']['B1/2025-05-30'].update(status='PHYSICAL_FAILURE',attempts=1)
    assert co.pending_phase(cp)=='B2'
    started=co.dispatch_available(root,m,cp,{}, {},factory(root))
    assert started==['B2/'+day for day in co.DAYS[:3]]


def test_hold_prevents_new_dispatch_without_touching_live_worker(campaign):
    root,m,cp=campaign
    atomic(root/'HOLD_V7R2.json',dict(block_new_dispatch_only=True))
    with patch.object(co.subprocess,'Popen',side_effect=AssertionError('HOLD_DISPATCH')):
        assert co.dispatch_available(root,m,cp,{}, {},factory(root))==[]
